import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.dialogue_models import CharacterDefinition, DialogueData, DialogueLine, DialogueResponse
from services.grok_dialogue_service import (
    GrokDialogueService,
    InvalidGrokOutputError,
    MissingRequiredSearchError,
    OpenAIResponsesClient,
    validate_dialogue_domain,
    xai_response_telemetry,
)
from services.provider_controls import ProviderController


class FakeResponsesClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def create(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def generate(service, *args, **kwargs):
    return asyncio.run(service.generate_dialogue(*args, **kwargs))


def dialogue_payload(*, valid=True, extra_line_field=False, repetitive=False):
    topics = [
        "indexes", "transactions", "locks", "schemas", "caches",
        "queues", "replicas", "shards", "backups", "queries",
        "latency", "timeouts", "retries", "tokens", "workers",
        "buffers", "streams", "batches", "signals", "metrics",
    ]
    actions = [
        "accelerate", "protect", "coordinate", "describe", "remember",
        "schedule", "duplicate", "partition", "restore", "filter",
        "delays", "interrupt", "recover", "authorize", "execute",
        "absorb", "deliver", "combine", "notify", "measure",
    ]
    contexts = [
        "searches", "updates", "writers", "records", "answers",
        "tasks", "reads", "datasets", "failures", "results",
        "requests", "calls", "outages", "sessions", "jobs",
        "bursts", "events", "changes", "clients", "systems",
    ]
    lines = []
    for index in range(20 if valid else 15):
        if valid:
            topic, action, context = topics[index], actions[index], contexts[index]
            if index % 2:
                caption = (
                    f"Why do {topic} {action} those {context} without creating another ridiculous disaster?"
                )
                speaker = "STEWIE"
            else:
                caption = (
                    f"Peter shows how {topic} {action} busy {context} with one useful example today."
                )
                speaker = "PETER"
            if repetitive:
                caption = (
                    "Why does this important idea work so reliably in practice?"
                    if speaker == "STEWIE"
                    else "Peter explains this useful concept clearly while keeping everyone completely entertained."
                )
        else:
            caption = "Far too short."
            speaker = "PETER" if index % 2 == 0 else "STEWIE"
        line = {
            "caption": caption,
            "speaker": speaker,
            "emotion": "neutral",
            "audio_effects": [],
        }
        if extra_line_field:
            line["duration_estimate"] = 2.0
        lines.append(line)
    return {"dialogue_data": {"title": "A Useful Lesson", "dialogue": lines}}


def completed_response(payload, *, x_calls=0, web_calls=0):
    return {
        "id": "resp_test",
        "status": "completed",
        "error": None,
        "output": [
            {"type": "x_search_call", "status": "completed"},
            {
                "type": "message",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(payload)}],
            },
        ],
        "usage": {
            "server_side_tool_usage_details": {
                "x_search_calls": x_calls,
                "web_search_calls": web_calls,
            }
        },
    }


def test_models_are_strict_and_contain_only_editor_fields():
    parsed = DialogueResponse.model_validate(dialogue_payload())
    assert parsed.dialogue_data.dialogue[0].model_dump() == {
        "caption": "Peter shows how indexes accelerate busy searches with one useful example today.",
        "speaker": "PETER",
        "emotion": "neutral",
        "audio_effects": [],
    }

    with pytest.raises(ValidationError):
        DialogueResponse.model_validate(dialogue_payload(extra_line_field=True))

    too_few = dialogue_payload()
    too_few["dialogue_data"]["dialogue"] = too_few["dialogue_data"]["dialogue"][:14]
    with pytest.raises(ValidationError):
        DialogueResponse.model_validate(too_few)


def test_forced_search_request_has_strict_bounded_responses_contract():
    fake = FakeResponsesClient(completed_response(dialogue_payload(), web_calls=1))
    service = GrokDialogueService(fake)

    result = generate(service, "Explain database indexes")

    assert result.title == "A Useful Lesson"
    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request["model"] == "grok-4.5"
    assert request["tools"] == [{"type": "x_search"}, {"type": "web_search"}]
    assert request["tool_choice"] == "required"
    assert request["max_output_tokens"] == 4096
    assert request["max_turns"] == 4
    assert request["store"] is False
    assert request["include"] == ["no_inline_citations"]
    assert request["text"]["format"]["strict"] is True
    schema = request["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["DialogueLine"]["additionalProperties"] is False
    assert "audio_effects" in schema["$defs"]["DialogueLine"]["required"]
    assert "virality-first" in request["instructions"]
    assert "SUPPLIED CAST" in request["instructions"]
    assert schema["$defs"]["DialogueData"]["properties"]["dialogue"]["minItems"] == 15
    assert schema["$defs"]["DialogueData"]["properties"]["dialogue"]["maxItems"] == 25


def test_auto_search_does_not_require_successful_tool_usage(monkeypatch):
    monkeypatch.setenv("XAI_MODEL", "grok-test-pinned")
    fake = FakeResponsesClient(completed_response(dialogue_payload()))
    service = GrokDialogueService(fake)

    generate(service, "An evergreen supplied draft", force_latest_search=False)

    assert fake.requests[0]["model"] == "grok-test-pinned"
    assert fake.requests[0]["tool_choice"] == "auto"


def test_forced_search_retries_once_when_the_first_response_skips_search():
    fake = FakeResponsesClient(
        completed_response(dialogue_payload()),
        completed_response(dialogue_payload(), web_calls=1),
    )

    result = generate(GrokDialogueService(fake), "Current AI news")

    assert result.title == "A Useful Lesson"
    assert len(fake.requests) == 2
    assert fake.requests[1]["tool_choice"] == "required"
    assert "previous attempt returned without a successful search" in fake.requests[1]["instructions"]


def test_forced_search_uses_successful_counters_not_attempted_items():
    fake = FakeResponsesClient(
        completed_response(dialogue_payload()),
        completed_response(dialogue_payload()),
    )

    with pytest.raises(MissingRequiredSearchError) as exc_info:
        generate(GrokDialogueService(fake), "Current AI news")

    assert exc_info.value.code == "missing_required_search"
    assert exc_info.value.retryable is True
    assert len(fake.requests) == 2


def test_trivial_numeric_suffixes_are_rejected_as_near_duplicates():
    payload = dialogue_payload(repetitive=True)
    for index, line in enumerate(payload["dialogue_data"]["dialogue"]):
        line["caption"] = f"{line['caption'].rstrip('?')} lesson {index}?"
    dialogue = DialogueResponse.model_validate(payload).dialogue_data

    errors = validate_dialogue_domain(dialogue)

    assert any("near-duplicate" in error for error in errors)


def test_repetitive_dialogue_triggers_one_semantic_repair():
    initial = completed_response(dialogue_payload(repetitive=True), x_calls=1)
    repaired = completed_response(dialogue_payload())
    fake = FakeResponsesClient(initial, repaired)

    result = asyncio.run(
        GrokDialogueService(fake).generate_dialogue("Explain transactions")
    )

    assert len(result.dialogue) == 20
    assert len(fake.requests) == 2
    repair_errors = json.loads(fake.requests[1]["input"][0]["content"])[
        "validation_errors"
    ]
    assert any("duplicate" in error for error in repair_errors)


def test_one_tool_free_semantic_repair_receives_draft_and_errors():
    initial = completed_response(dialogue_payload(valid=False), x_calls=1)
    repaired = completed_response(dialogue_payload())
    fake = FakeResponsesClient(initial, repaired)

    result = generate(GrokDialogueService(fake), "Explain transactions")

    assert len(result.dialogue) == 20
    assert len(fake.requests) == 2
    repair = fake.requests[1]
    # xAI rejects tool_choice when no tools are supplied, so a tool-free
    # repair request omits both keys entirely rather than sending empties.
    assert "tools" not in repair
    assert "tool_choice" not in repair
    repair_body = json.loads(repair["input"][0]["content"])
    assert repair_body["draft"] == dialogue_payload(valid=False)
    assert any("200-300" in error for error in repair_body["validation_errors"])
    assert any("8-15" in error for error in repair_body["validation_errors"])


def test_repair_is_attempted_only_once_then_returns_typed_error():
    invalid = completed_response(dialogue_payload(valid=False), x_calls=1)
    fake = FakeResponsesClient(invalid, completed_response(dialogue_payload(valid=False)))

    with pytest.raises(InvalidGrokOutputError) as exc_info:
        generate(GrokDialogueService(fake), "Explain transactions")

    assert exc_info.value.code == "invalid_provider_output"
    assert exc_info.value.retryable is True
    assert len(fake.requests) == 2


def test_structural_failure_is_not_sent_for_semantic_repair():
    fake = FakeResponsesClient(
        completed_response(dialogue_payload(extra_line_field=True), x_calls=1)
    )

    with pytest.raises(InvalidGrokOutputError):
        generate(GrokDialogueService(fake), "Explain transactions")

    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": [], "usage": {}},
        {
            "status": "completed",
            "error": None,
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "content": [{"type": "refusal", "refusal": "No."}],
                }
            ],
            "usage": {},
        },
    ],
)
def test_incomplete_and_refusal_outputs_are_rejected(response):
    with pytest.raises(InvalidGrokOutputError):
        generate(
            GrokDialogueService(FakeResponsesClient(response)),
            "Explain transactions",
            force_latest_search=False,
        )


def test_domain_validator_reports_all_required_semantic_rules():
    lines = [
        DialogueLine(caption="Only six words appear in this caption.", speaker="PETER", emotion="neutral")
        for _ in range(15)
    ]
    dialogue = DialogueData(title="Broken", dialogue=lines)

    errors = validate_dialogue_domain(dialogue)

    assert any("200-300" in error for error in errors)
    assert any("8-15" in error for error in errors)
    assert any("at least 2 supplied cast members" in error for error in errors)
    assert not any("Stewie" in error for error in errors)


def test_dynamic_cast_replaces_character_specific_validation():
    payload = dialogue_payload()
    for line in payload["dialogue_data"]["dialogue"]:
        line["speaker"] = "HOST" if line["speaker"] == "PETER" else "GREMLIN"
    cast = (
        CharacterDefinition(id="HOST", display_name="Host", persona="Deadpan setup."),
        CharacterDefinition(id="GREMLIN", display_name="Gremlin", persona="Chaotic payoff."),
    )
    fake = FakeResponsesClient(completed_response(payload, x_calls=1))

    result = generate(GrokDialogueService(fake, cast=cast), "Make database indexes viral")

    assert {line.speaker for line in result.dialogue} == {"HOST", "GREMLIN"}
    assert '"id": "HOST"' in fake.requests[0]["instructions"]


def test_curated_grok_response_is_logged_without_the_user_prompt():
    records = []
    payload = dialogue_payload()
    payload["dialogue_data"]["dialogue"][0]["audio_effects"] = [
        {"description": "record scratch", "placement": "before"}
    ]
    service = GrokDialogueService(
        FakeResponsesClient(completed_response(payload, x_calls=1)),
        content_logger=SimpleNamespace(emit=records.append),
    )

    generate(service, "private user prompt", job_id="job-1", user_id=7)

    assert len(records) == 1
    record = records[0]
    assert record.operation == "dialogue_initial_response"
    assert record.job_id == "job-1"
    assert record.response["dialogue_data"]["dialogue"][0]["audio_effects"] == [
        {"description": "record scratch", "placement": "before"}
    ]
    assert "private user prompt" not in str(record.to_dict())


def test_initial_and_repair_calls_have_independent_controls_and_shared_deadline():
    class RecordingController:
        def __init__(self):
            self.calls = []

        async def execute(
            self,
            operation,
            *,
            metadata,
            request_timeout_seconds,
            scope,
        ):
            self.calls.append((metadata, request_timeout_seconds, scope))
            return await operation(1)

    controller = RecordingController()
    fake = FakeResponsesClient(
        completed_response(dialogue_payload(valid=False), x_calls=1),
        completed_response(dialogue_payload()),
    )
    service = GrokDialogueService(fake, controller=controller)

    result = generate(
        service,
        "Explain transactions",
        job_id="job-42",
        user_id=7,
    )

    assert len(result.dialogue) == 20
    assert [call[0].operation for call in controller.calls] == [
        "dialogue_initial",
        "dialogue_semantic_repair",
    ]
    assert all(call[0].job_id == "job-42" for call in controller.calls)
    assert all(call[0].user_id == 7 for call in controller.calls)
    assert [call[1] for call in controller.calls] == [120, 120]
    assert controller.calls[0][2] is controller.calls[1][2]
    assert 0 < controller.calls[0][2].remaining() <= 300
def test_controlled_call_emits_structured_xai_metadata_and_telemetry():
    response = completed_response(dialogue_payload(), x_calls=1)
    response["usage"].update(
        {
            "input_tokens": 101,
            "output_tokens": 202,
            "output_tokens_details": {"reasoning_tokens": 33},
        }
    )
    records = []
    controller = ProviderController(
        logger=SimpleNamespace(emit=records.append),
        telemetry_getter=xai_response_telemetry,
    )

    generate(
        GrokDialogueService(FakeResponsesClient(response), controller=controller),
        "Explain transactions",
        job_id="job-telemetry",
        user_id=9,
    )

    assert len(records) == 1
    record = records[0]
    assert record.operation == "dialogue_initial"
    assert record.job_id == "job-telemetry"
    assert record.user_id == 9
    assert record.provider_request_id == "resp_test"
    assert record.input_tokens == 101
    assert record.output_tokens == 202
    assert record.reasoning_tokens == 33
    assert record.x_search_calls == 1
    assert record.web_search_calls == 0


def test_xai_telemetry_includes_response_usage_and_successful_search_calls():
    telemetry = xai_response_telemetry(
        {
            "id": "resp_xai_123",
            "usage": {
                "input_tokens": 101,
                "output_tokens": 202,
                "output_tokens_details": {"reasoning_tokens": 33},
                "server_side_tool_usage_details": {
                    "x_search_calls": 2,
                    "web_search_calls": 1,
                },
            },
        }
    )

    assert telemetry.provider_request_id == "resp_xai_123"
    assert telemetry.input_tokens == 101
    assert telemetry.output_tokens == 202
    assert telemetry.reasoning_tokens == 33
    assert telemetry.x_search_calls == 2
    assert telemetry.web_search_calls == 1


def test_openai_adapter_sends_xai_max_turns_as_extra_body():
    async def create(**kwargs):
        return kwargs

    responses = SimpleNamespace(create=create)
    adapter = OpenAIResponsesClient(responses)

    result = asyncio.run(
        adapter.create({"model": "grok-4.5", "input": "hello", "max_turns": 4})
    )

    assert result == {
        "model": "grok-4.5",
        "input": "hello",
        "extra_body": {"max_turns": 4},
    }
