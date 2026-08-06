"""Search-grounded Grok dialogue generation through an injected Responses boundary."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, Protocol

from pydantic import ValidationError

from .dialogue_models import CharacterDefinition, DialogueData, DialogueResponse
from .generation_errors import (
    GenerationError,
    InvalidProviderOutputError,
    MissingRequiredSearchError as BaseMissingRequiredSearchError,
    ProviderAuthConfigurationError,
)
from .provider_controls import (
    PROVIDER_CONTROL_CONFIG,
    OperationScope,
    ProviderController,
    ProviderTelemetry,
)
from .provider_logging import (
    ContentLogSink,
    ProviderContentRecord,
    ProviderOperationMetadata,
    StructuredContentLogger,
    StructuredOperationLogger,
)

DEFAULT_MODEL = "grok-4.5"
MAX_OUTPUT_TOKENS = 4096
MAX_TURNS = 4
XAI_BASE_URL = "https://api.x.ai/v1"

_SEARCH_TOOLS = [{"type": "x_search"}, {"type": "web_search"}]
_WORD_RE = re.compile(r"\b[^\W_]+(?:['’-][^\W_]+)*\b", re.UNICODE)
_INLINE_CITATION_RE = re.compile(r"\[\[\d+\]\]\(https?://|https?://", re.IGNORECASE)

DEFAULT_CAST = (
    CharacterDefinition(
        id="PETER",
        display_name="Peter Griffin",
        persona="Confidently foolish, impulsive, edgy, and committed to the bit.",
    ),
    CharacterDefinition(
        id="STEWIE",
        display_name="Stewie Griffin",
        persona="Incisive, theatrical, impatient, and quick with cutting reactions.",
    ),
)

_GENERATION_INSTRUCTIONS = """Create one roughly two-minute, virality-first conversation from the user's topic or draft using only the supplied cast.
Open with an immediate hook. Prioritize fast pacing, escalating absurdity, sharp reactions, quotable lines, recognizable internet humor, and a strong final payoff. Minimize exposition and do not turn the result into a lesson. When the topic involves real people or current events, do not invent factual claims merely to make a joke. A supplied draft is editable source material: aggressively improve its hook, pacing, comedic escalation, and meme potential.
Return 15-25 dialogue lines and 200-300 spoken words total. Target 8-15 words in every subtitle-friendly caption and use at least two cast members when two are available. Prefer neutral emotion unless angry, excited, or confused clearly improves delivery. Add zero to two concise audio-effect cues per line only when a record scratch, impact, censor beep, crowd reaction, or similarly recognizable sound materially improves the joke; these cues are metadata for a future audio layer and must not be written into the spoken caption. Do not discuss visual planning, images, citations, or the output format outside the structured result."""

_FORCED_SEARCH_RETRY_INSTRUCTIONS = """A current-source search is mandatory for this request, and the previous attempt returned without a successful search. Before writing the dialogue, call x_search or web_search successfully and ground every time-sensitive factual claim in those results. Do not answer from model memory alone."""

_REPAIR_INSTRUCTIONS = """Repair the supplied structured dialogue using only the cast, draft, and validation errors in the user message. Preserve its strongest jokes and intent; change only wording, line breaks, pacing, cast participation, audio-effect cues, and persona details needed to satisfy every error. Do not research or introduce current facts. Return only the repaired structured result."""


class XAIResponsesClient(Protocol):
    """Small injectable boundary around one non-streaming xAI Responses call."""

    async def create(self, request: Mapping[str, Any]) -> Any:
        """Submit a Responses API request and return the provider response."""


class OpenAIResponsesClient:
    """xAI Responses adapter using the asynchronous OpenAI SDK boundary."""

    def __init__(self, responses: Any):
        self._responses = responses

    async def create(self, request: Mapping[str, Any]) -> Any:
        payload = dict(request)
        # max_turns is an xAI Responses extension, so the OpenAI SDK sends it
        # through extra_body while retaining normal typed Responses fields.
        max_turns = payload.pop("max_turns")
        return await self._responses.create(
            **payload,
            extra_body={"max_turns": max_turns},
        )


DialogueGenerationError = GenerationError


class InvalidGrokOutputError(InvalidProviderOutputError):
    """A structurally or semantically invalid Grok dialogue response."""

    @property
    def retryable(self) -> bool:
        return True


class MissingRequiredSearchError(BaseMissingRequiredSearchError):
    """A forced-search response with no successful X or web usage."""

    @property
    def retryable(self) -> bool:
        return True


def create_xai_responses_client(
    *, api_key: str | None = None, timeout_seconds: float | None = None
) -> XAIResponsesClient:
    """Build the production Responses boundary without coupling models to an SDK."""

    resolved_key = api_key or os.getenv("XAI_API_KEY")
    if not resolved_key:
        raise ProviderAuthConfigurationError()
    resolved_timeout = (
        PROVIDER_CONTROL_CONFIG.grok_dialogue_timeout_seconds
        if timeout_seconds is None
        else timeout_seconds
    )
    if resolved_timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    # Imported lazily so pure model/domain tests do not need provider setup.
    from openai import AsyncOpenAI

    sdk_client = AsyncOpenAI(
        api_key=resolved_key,
        base_url=XAI_BASE_URL,
        timeout=resolved_timeout,
        # Attempt retries belong to the process-local provider-controls boundary.
        max_retries=0,
    )
    return OpenAIResponsesClient(sdk_client.responses)


def _validated_cast(
    cast: Sequence[CharacterDefinition],
) -> tuple[CharacterDefinition, ...]:
    resolved = tuple(cast)
    if not resolved:
        raise ValueError("cast must contain at least one character")
    ids = [character.id for character in resolved]
    if len(ids) != len(set(ids)):
        raise ValueError("cast character IDs must be unique")
    return resolved


class GrokDialogueService:
    """Generate and semantically validate a virality-first cast dialogue."""

    def __init__(
        self,
        client: XAIResponsesClient,
        *,
        model: str | None = None,
        controller: ProviderController | None = None,
        request_timeout_seconds: float | None = None,
        operation_deadline_seconds: float | None = None,
        cast: Sequence[CharacterDefinition] | None = None,
        content_logger: ContentLogSink | None = None,
    ) -> None:
        self._client = client
        self.model = model or os.getenv("XAI_MODEL") or DEFAULT_MODEL
        self.cast = _validated_cast(cast or DEFAULT_CAST)
        self._content_logger = content_logger or StructuredContentLogger()
        self.request_timeout_seconds = (
            PROVIDER_CONTROL_CONFIG.grok_dialogue_timeout_seconds
            if request_timeout_seconds is None
            else request_timeout_seconds
        )
        self.operation_deadline_seconds = (
            PROVIDER_CONTROL_CONFIG.dialogue_deadline_seconds
            if operation_deadline_seconds is None
            else operation_deadline_seconds
        )
        if self.request_timeout_seconds <= 0 or self.operation_deadline_seconds <= 0:
            raise ValueError("provider timeout and operation deadline must be greater than zero")
        self._controller = controller or ProviderController(
            logger=StructuredOperationLogger(),
            telemetry_getter=xai_response_telemetry,
        )

    async def generate_dialogue(
        self,
        topic_or_draft: str,
        force_latest_search: bool = True,
        *,
        job_id: str | None = None,
        user_id: str | int | None = None,
        scope: OperationScope | None = None,
    ) -> DialogueData:
        if not isinstance(topic_or_draft, str) or not topic_or_draft.strip():
            raise ValueError("topic_or_draft must be a non-blank string")

        # One scope is deliberately shared by the initial request, retry
        # backoffs, local validation, and the optional semantic-repair request.
        operation_scope = scope or OperationScope.with_timeout(
            self.operation_deadline_seconds
        )
        initial_response = await self._create_response(
            self._request(
                instructions=self._instructions(_GENERATION_INSTRUCTIONS),
                user_input=topic_or_draft,
                tools=_SEARCH_TOOLS,
                tool_choice="required" if force_latest_search else "auto",
            ),
            operation="dialogue_initial",
            scope=operation_scope,
            job_id=job_id,
            user_id=user_id,
        )
        initial = _validated_structured_output(initial_response)
        self._log_response(
            initial,
            operation="dialogue_initial_response",
            job_id=job_id,
            user_id=user_id,
        )

        if force_latest_search and _successful_search_count(initial_response) < 1:
            retry_response = await self._create_response(
                self._request(
                    instructions=self._instructions(
                        _GENERATION_INSTRUCTIONS
                        + "\n\n"
                        + _FORCED_SEARCH_RETRY_INSTRUCTIONS
                    ),
                    user_input=topic_or_draft,
                    tools=_SEARCH_TOOLS,
                    tool_choice="required",
                ),
                operation="dialogue_search_retry",
                scope=operation_scope,
                job_id=job_id,
                user_id=user_id,
            )
            retried = _validated_structured_output(retry_response)
            self._log_response(
                retried,
                operation="dialogue_search_retry_response",
                job_id=job_id,
                user_id=user_id,
            )
            if _successful_search_count(retry_response) < 1:
                raise MissingRequiredSearchError()
            initial = retried

        errors = validate_dialogue_domain(initial.dialogue_data, self.cast)
        if not errors:
            operation_scope.raise_if_stopped()
            return initial.dialogue_data

        repair_input = json.dumps(
            {
                "cast": [character.model_dump(mode="json") for character in self.cast],
                "draft": initial.model_dump(mode="json"),
                "validation_errors": errors,
            },
            ensure_ascii=False,
        )
        repair_response = await self._create_response(
            self._request(
                instructions=self._instructions(_REPAIR_INSTRUCTIONS),
                user_input=repair_input,
                tools=[],
                tool_choice="none",
            ),
            operation="dialogue_semantic_repair",
            scope=operation_scope,
            job_id=job_id,
            user_id=user_id,
        )
        repaired = _validated_structured_output(repair_response)
        self._log_response(
            repaired,
            operation="dialogue_semantic_repair_response",
            job_id=job_id,
            user_id=user_id,
        )
        repair_errors = validate_dialogue_domain(repaired.dialogue_data, self.cast)
        if repair_errors:
            raise InvalidGrokOutputError(
                "Grok dialogue failed domain validation after one repair: "
                + "; ".join(repair_errors)
            )
        operation_scope.raise_if_stopped()
        return repaired.dialogue_data

    def _instructions(self, base: str) -> str:
        cast_payload = json.dumps(
            [character.model_dump(mode="json") for character in self.cast],
            ensure_ascii=False,
        )
        return f"{base}\n\nSUPPLIED CAST (speaker must equal an id):\n{cast_payload}"

    def _log_response(
        self,
        response: DialogueResponse,
        *,
        operation: str,
        job_id: str | None,
        user_id: str | int | None,
    ) -> None:
        self._content_logger.emit(
            ProviderContentRecord(
                provider="grok",
                operation=operation,
                model=self.model,
                job_id=job_id,
                user_id=user_id,
                response=response.model_dump(mode="json"),
            )
        )

    async def _create_response(
        self,
        request: Mapping[str, Any],
        *,
        operation: str,
        scope: OperationScope,
        job_id: str | None,
        user_id: str | int | None,
    ) -> Any:
        async def create_attempt(_attempt: int) -> Any:
            return await self._client.create(request)

        return await self._controller.execute(
            create_attempt,
            metadata=ProviderOperationMetadata(
                provider="grok",
                operation=operation,
                model=self.model,
                job_id=job_id,
                user_id=user_id,
            ),
            request_timeout_seconds=self.request_timeout_seconds,
            scope=scope,
        )

    def _request(
        self,
        *,
        instructions: str,
        user_input: str,
        tools: list[dict[str, str]],
        tool_choice: str,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": user_input}],
            # xAI rejects tool_choice when no tools are supplied (used by the
            # tool-free semantic repair request), so omit both together.
            **(
                {"tools": [dict(tool) for tool in tools], "tool_choice": tool_choice}
                if tools
                else {}
            ),
            "parallel_tool_calls": True,
            "max_turns": MAX_TURNS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "include": ["no_inline_citations"],
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "viral_dialogue",
                    "strict": True,
                    "schema": _strict_dialogue_schema(),
                }
            },
        }


def _strict_dialogue_schema() -> dict[str, Any]:
    """Require future-facing cue arrays in provider output while parsing legacy data."""

    schema = DialogueResponse.model_json_schema()
    line_schema = schema.get("$defs", {}).get("DialogueLine", {})
    required = line_schema.setdefault("required", [])
    if "audio_effects" not in required:
        required.append("audio_effects")
    return schema


def validate_dialogue_domain(
    dialogue: DialogueData,
    cast: Sequence[CharacterDefinition] = DEFAULT_CAST,
) -> list[str]:
    """Return deterministic semantic errors not guaranteed by JSON Schema."""

    validated_cast = _validated_cast(cast)
    cast_ids = {character.id for character in validated_cast}
    errors: list[str] = []
    line_count = len(dialogue.dialogue)
    if not 15 <= line_count <= 25:
        errors.append(f"dialogue must contain 15-25 lines; got {line_count}")

    line_word_counts = [_word_count(line.caption) for line in dialogue.dialogue]
    total_words = sum(line_word_counts)
    if not 200 <= total_words <= 300:
        errors.append(f"dialogue must contain 200-300 spoken words; got {total_words}")

    invalid_lines = [
        f"{index} ({count} words)"
        for index, count in enumerate(line_word_counts, start=1)
        if not 8 <= count <= 15
    ]
    if invalid_lines:
        errors.append(
            "every caption must contain 8-15 words; invalid lines: "
            + ", ".join(invalid_lines)
        )

    speakers = {line.speaker for line in dialogue.dialogue}
    unknown_speakers = sorted(speakers - cast_ids)
    if unknown_speakers:
        errors.append(
            "dialogue contains speakers outside the supplied cast: "
            + ", ".join(unknown_speakers)
        )
    required_speaker_count = min(2, len(validated_cast))
    known_speaker_count = len(speakers & cast_ids)
    if known_speaker_count < required_speaker_count:
        errors.append(
            f"dialogue must use at least {required_speaker_count} supplied cast members; "
            f"got {known_speaker_count}"
        )

    normalized_captions = [
        " ".join(_WORD_RE.findall(line.caption.lower())) for line in dialogue.dialogue
    ]
    duplicate_count = len(normalized_captions) - len(set(normalized_captions))
    if duplicate_count:
        errors.append(
            f"dialogue must not repeat captions; found {duplicate_count} duplicate lines"
        )

    # Ignore numeric suffixes so trivial template variations ("lesson 1", "lesson 2")
    # cannot masquerade as a coherent conversation.
    similarity_captions = [
        " ".join(word for word in caption.split() if not word.isdigit())
        for caption in normalized_captions
    ]
    near_duplicate_pairs = sum(
        SequenceMatcher(None, left, right).ratio() >= 0.88
        for index, left in enumerate(similarity_captions)
        for right in similarity_captions[index + 1 :]
    )
    if near_duplicate_pairs:
        errors.append(
            "dialogue must not use near-duplicate template lines; "
            f"found {near_duplicate_pairs} overly similar pairs"
        )

    speaker_transitions = sum(
        previous.speaker != current.speaker
        for previous, current in zip(dialogue.dialogue, dialogue.dialogue[1:])
    )
    if speaker_transitions < 6:
        errors.append(
            f"dialogue must be conversational; found only {speaker_transitions} speaker turns"
        )

    if any(_INLINE_CITATION_RE.search(line.caption) for line in dialogue.dialogue):
        errors.append("spoken captions must not contain inline citations or URLs")

    return errors


def _word_count(value: str) -> int:
    return len(_WORD_RE.findall(value))


def _validated_structured_output(response: Any) -> DialogueResponse:
    if _value(response, "status") != "completed":
        raise InvalidGrokOutputError("Grok response was not completed.")
    if _value(response, "error") is not None:
        raise InvalidGrokOutputError("Grok response contained a provider error.")

    output_texts: list[str] = []
    for item in _value(response, "output", ()) or ():
        item_type = _value(item, "type")
        if item_type == "refusal":
            raise InvalidGrokOutputError("Grok refused the dialogue request.")
        if item_type != "message":
            continue
        if _value(item, "status") != "completed":
            raise InvalidGrokOutputError("Grok output message was not completed.")
        for content in _value(item, "content", ()) or ():
            content_type = _value(content, "type")
            if content_type == "refusal":
                raise InvalidGrokOutputError("Grok refused the dialogue request.")
            if content_type == "output_text":
                text = _value(content, "text")
                if isinstance(text, str):
                    output_texts.append(text)

    if len(output_texts) != 1:
        raise InvalidGrokOutputError(
            f"Expected exactly one completed output_text item; got {len(output_texts)}."
        )

    try:
        return DialogueResponse.model_validate_json(output_texts[0])
    except (ValidationError, ValueError) as exc:
        raise InvalidGrokOutputError(
            "Grok output did not match the strict dialogue schema."
        ) from exc


def xai_response_telemetry(response: object) -> ProviderTelemetry:
    """Extract only allowlisted xAI Responses usage and correlation fields."""

    usage = _value(response, "usage")
    output_details = _value(usage, "output_tokens_details")
    search_details = _search_usage_details(usage)
    response_id = _value(response, "id")
    return ProviderTelemetry(
        provider_request_id=(
            str(response_id) if isinstance(response_id, (str, int)) else None
        ),
        input_tokens=_optional_nonnegative_int(_value(usage, "input_tokens")),
        output_tokens=_optional_nonnegative_int(_value(usage, "output_tokens")),
        reasoning_tokens=_optional_nonnegative_int(
            _value(
                output_details,
                "reasoning_tokens",
                _value(usage, "reasoning_tokens"),
            )
        ),
        x_search_calls=_optional_nonnegative_int(
            _value(search_details, "x_search_calls")
        ),
        web_search_calls=_optional_nonnegative_int(
            _value(search_details, "web_search_calls")
        ),
    )


def _successful_search_count(response: Any) -> int:
    details = _search_usage_details(_value(response, "usage"))
    return _nonnegative_int(_value(details, "x_search_calls")) + _nonnegative_int(
        _value(details, "web_search_calls")
    )


def _search_usage_details(usage: Any) -> Any:
    # xAI has used both names across Responses revisions; both contain counters
    # for successful server-side calls rather than merely emitted tool items.
    return _value(
        usage,
        "server_side_tool_usage_details",
        _value(usage, "server_side_tool_usage"),
    )


def _optional_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _nonnegative_int(value: Any) -> int:
    return _optional_nonnegative_int(value) or 0


def _value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, Mapping):
        return container.get(key, default)
    return getattr(container, key, default)


__all__ = [
    "DEFAULT_MODEL",
    "DialogueGenerationError",
    "GrokDialogueService",
    "InvalidGrokOutputError",
    "MissingRequiredSearchError",
    "OpenAIResponsesClient",
    "XAIResponsesClient",
    "create_xai_responses_client",
    "validate_dialogue_domain",
    "xai_response_telemetry",
]
