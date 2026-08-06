"""Deterministic tests for shared provider-control foundations."""

import asyncio
from dataclasses import dataclass, field

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from services.generation_errors import (
    GenerationCancelledError,
    GenerationDeadlineExceededError,
    ProviderAuthConfigurationError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from services.provider_controls import (
    CancellationToken,
    OperationScope,
    ProviderControlConfig,
    ProviderController,
    ProviderTelemetry,
    ProviderTransportError,
    RetryPolicy,
    parse_retry_after,
)
from services.provider_logging import ProviderOperationMetadata, ProviderOperationRecord


@dataclass
class FakeResponse:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = "sensitive provider response"


class MemoryLogSink:
    def __init__(self):
        self.records: list[ProviderOperationRecord] = []

    def emit(self, record: ProviderOperationRecord) -> None:
        self.records.append(record)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def run(coroutine):
    return asyncio.run(coroutine)


def test_config_defaults_and_environment_overrides():
    defaults = ProviderControlConfig.from_env({})
    assert defaults.max_attempts == 3
    assert defaults.grok_dialogue_timeout_seconds == 120
    assert defaults.grok_visual_planning_timeout_seconds == 90
    assert defaults.serpapi_search_timeout_seconds == 20
    assert defaults.image_fetch_timeout_seconds == 15

    configured = ProviderControlConfig.from_env({"PROVIDER_MAX_ATTEMPTS": "2"})
    assert configured.max_attempts == 2


@pytest.mark.parametrize("status", [408, 429, 500, 503, 599])
def test_retry_policy_classifies_only_resolved_http_statuses(status):
    assert RetryPolicy.is_retryable_status(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_retry_policy_does_not_retry_permanent_http_statuses(status):
    assert not RetryPolicy.is_retryable_status(status)


def test_retry_policy_retries_only_transient_statuses_and_honors_retry_after():
    async def scenario():
        sleeps = []
        responses = [
            FakeResponse(429, {"Retry-After": "2"}),
            FakeResponse(503),
            FakeResponse(200, {"X-Request-Id": "request-3"}),
        ]
        sink = MemoryLogSink()
        controller = ProviderController(
            retry_policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=1,
                max_delay_seconds=10,
                jitter=lambda: 0,
            ),
            logger=sink,
            sleep=lambda seconds: _record_sleep(sleeps, seconds),
        )

        result = await controller.execute(
            lambda attempt: _return(responses[attempt - 1]),
            metadata=ProviderOperationMetadata("grok", "dialogue", model="grok-4.5"),
            request_timeout_seconds=1,
        )
        assert result.status_code == 200
        assert sleeps == [2.0, 1.0]
        assert [record.status for record in sink.records] == [
            "retrying",
            "retrying",
            "succeeded",
        ]
        assert [record.http_status for record in sink.records] == [429, 503, 200]
        assert sink.records[-1].provider_request_id == "request-3"

    run(scenario())


def test_non_transient_http_failure_is_not_retried():
    async def scenario():
        calls = 0

        async def operation(_attempt):
            nonlocal calls
            calls += 1
            return FakeResponse(422)

        with pytest.raises(ProviderRequestRejectedError):
            await ProviderController().execute(
                operation,
                metadata=ProviderOperationMetadata("grok", "dialogue"),
                request_timeout_seconds=1,
            )
        assert calls == 1

    run(scenario())


def test_unknown_attempt_is_safely_logged_then_reraised_for_job_boundary():
    async def scenario():
        sink = MemoryLogSink()

        async def operation(_attempt):
            raise ValueError("secret client implementation detail")

        with pytest.raises(ValueError, match="secret client"):
            await ProviderController(
                logger=sink
            ).execute(
                operation,
                metadata=ProviderOperationMetadata("grok", "dialogue_initial"),
                request_timeout_seconds=1,
            )

        assert len(sink.records) == 1
        assert sink.records[0].status == "failed"
        assert sink.records[0].error_code == "generation_failed"
        assert "secret" not in str(sink.records[0].to_dict())

    run(scenario())


def test_auth_failure_is_stable_and_not_retried():
    async def scenario():
        with pytest.raises(ProviderAuthConfigurationError) as raised:
            await ProviderController().execute(
                lambda _attempt: _return(FakeResponse(401)),
                metadata=ProviderOperationMetadata("serpapi", "image_search"),
                request_timeout_seconds=1,
            )
        assert raised.value.code == "provider_auth_configuration"

    run(scenario())


def test_transport_failures_retry_up_to_three_total_attempts():
    async def scenario():
        attempts = []

        async def operation(attempt):
            attempts.append(attempt)
            raise ProviderTransportError("secret URL must not be logged")

        sink = MemoryLogSink()
        controller = ProviderController(
            retry_policy=RetryPolicy(jitter=lambda: 0),
            logger=sink,
            sleep=lambda _seconds: _return(None),
        )
        with pytest.raises(Exception) as raised:
            await controller.execute(
                operation,
                metadata=ProviderOperationMetadata("serpapi", "image_search"),
                request_timeout_seconds=1,
            )
        assert raised.value.code == "provider_unavailable"
        assert attempts == [1, 2, 3]
        assert [record.status for record in sink.records] == [
            "retrying",
            "retrying",
            "failed",
        ]

    run(scenario())


@pytest.mark.parametrize("exception_type", [APIConnectionError, APITimeoutError])
def test_openai_248_transport_errors_are_translated_and_retried(exception_type):
    async def scenario():
        request = httpx.Request("POST", "https://api.x.ai/v1/responses")
        attempts = []

        async def operation(attempt):
            attempts.append(attempt)
            if attempt == 1:
                if exception_type is APITimeoutError:
                    raise APITimeoutError(request)
                raise APIConnectionError(request=request)
            return FakeResponse(200)

        await ProviderController(
            retry_policy=RetryPolicy(jitter=lambda: 0),
            sleep=lambda _seconds: _return(None),
        ).execute(
            operation,
            metadata=ProviderOperationMetadata("grok", "dialogue_initial"),
            request_timeout_seconds=1,
        )
        assert attempts == [1, 2]

    run(scenario())


def test_openai_248_timeout_exhaustion_returns_typed_timeout():
    async def scenario():
        request = httpx.Request("POST", "https://api.x.ai/v1/responses")

        async def operation(_attempt):
            raise APITimeoutError(request)

        with pytest.raises(ProviderTimeoutError):
            await ProviderController(
                    retry_policy=RetryPolicy(max_attempts=1),
            ).execute(
                operation,
                metadata=ProviderOperationMetadata("grok", "dialogue_initial"),
                request_timeout_seconds=1,
            )

    run(scenario())


def test_openai_248_api_status_error_uses_status_headers_and_retries():
    async def scenario():
        attempts = []
        sleeps = []

        async def operation(attempt):
            attempts.append(attempt)
            if attempt == 1:
                request = httpx.Request("POST", "https://api.x.ai/v1/responses")
                response = httpx.Response(
                    429,
                    headers={"retry-after": "2"},
                    request=request,
                )
                raise APIStatusError("rate limited", response=response, body={})
            return FakeResponse(200)

        await ProviderController(
            retry_policy=RetryPolicy(jitter=lambda: 0),
            sleep=lambda seconds: _record_sleep(sleeps, seconds),
        ).execute(
            operation,
            metadata=ProviderOperationMetadata("grok", "dialogue_initial"),
            request_timeout_seconds=1,
        )
        assert attempts == [1, 2]
        assert sleeps == [2.0]

    run(scenario())


def test_openai_248_connection_exhaustion_returns_unavailable():
    async def scenario():
        request = httpx.Request("POST", "https://api.x.ai/v1/responses")

        async def operation(_attempt):
            raise APIConnectionError(request=request)

        with pytest.raises(ProviderUnavailableError):
            await ProviderController(
                    retry_policy=RetryPolicy(max_attempts=1),
            ).execute(
                operation,
                metadata=ProviderOperationMetadata("grok", "dialogue_initial"),
                request_timeout_seconds=1,
            )

    run(scenario())


def test_request_timeout_is_retried_then_returns_typed_timeout():
    async def scenario():
        attempts = []

        async def never_finishes(attempt):
            attempts.append(attempt)
            await asyncio.Event().wait()

        controller = ProviderController(
            retry_policy=RetryPolicy(jitter=lambda: 0),
            sleep=lambda _seconds: _return(None),
        )
        with pytest.raises(ProviderTimeoutError):
            await controller.execute(
                never_finishes,
                metadata=ProviderOperationMetadata("grok", "visual_planning"),
                request_timeout_seconds=0.005,
            )
        assert attempts == [1, 2, 3]

    run(scenario())


def test_cancellation_interrupts_backoff_and_prevents_new_attempt():
    async def scenario():
        token = CancellationToken()
        backoff_started = asyncio.Event()

        async def blocking_sleep(_seconds):
            backoff_started.set()
            await asyncio.Event().wait()

        attempts = []

        async def operation(attempt):
            attempts.append(attempt)
            raise ProviderTransportError()

        controller = ProviderController(
            retry_policy=RetryPolicy(jitter=lambda: 0),
            sleep=blocking_sleep,
        )
        task = asyncio.create_task(
            controller.execute(
                operation,
                metadata=ProviderOperationMetadata("grok", "dialogue"),
                request_timeout_seconds=1,
                scope=OperationScope(token),
            )
        )
        await backoff_started.wait()
        token.cancel()
        with pytest.raises(GenerationCancelledError):
            await task
        assert attempts == [1]

    run(scenario())


def test_operation_deadline_ignores_late_response_through_cancellation_path():
    async def scenario():
        clock = FakeClock()
        token = CancellationToken()
        aborted = []
        token.add_cancel_callback(lambda: aborted.append(True))
        controller = ProviderController(
            clock=clock
        )

        async def late_response(_attempt):
            clock.advance(2)
            return FakeResponse(200)

        with pytest.raises(GenerationDeadlineExceededError):
            await controller.execute(
                late_response,
                metadata=ProviderOperationMetadata("grok", "dialogue"),
                request_timeout_seconds=5,
                scope=OperationScope.with_timeout(1, cancellation=token, clock=clock),
            )
        assert token.cancelled
        assert aborted == [True]

    run(scenario())


def test_injected_telemetry_is_allowlisted_in_operation_record():
    async def scenario():
        sink = MemoryLogSink()
        controller = ProviderController(
            logger=sink,
            telemetry_getter=lambda _response: ProviderTelemetry(
                provider_request_id="provider-id",
                input_tokens=10,
                output_tokens=20,
                reasoning_tokens=5,
                x_search_calls=1,
                web_search_calls=2,
            ),
        )
        await controller.execute(
            lambda _attempt: _return(FakeResponse(200)),
            metadata=ProviderOperationMetadata(
                "grok", "dialogue", "grok-4.5", "job", "project", 42
            ),
            request_timeout_seconds=1,
        )
        record = sink.records[0]
        assert record.input_tokens == 10
        assert record.x_search_calls == 1
        assert record.project_id == "project"
        serialized = str(record.to_dict()).lower()
        assert "prompt" not in serialized
        assert "sensitive provider response" not in serialized
        assert "url" not in serialized

    run(scenario())


def test_retry_after_parser_supports_seconds_and_ignores_invalid_values():
    assert parse_retry_after("2.5", now=0) == 2.5
    assert parse_retry_after("invalid", now=0) is None


async def _return(value):
    return value


async def _record_sleep(target, seconds):
    target.append(seconds)
