"""Retry, timeout, deadline, cancellation, and logging for provider calls.

Provider calls intentionally have no application-imposed concurrency or queue
caps until the distributed architecture is finalized.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import random
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, Mapping, TypeVar, cast

from services.generation_errors import (
    GenerationCancelledError,
    GenerationDeadlineExceededError,
    GenerationError,
    ProviderAuthConfigurationError,
    ProviderRateLimitError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from services.provider_logging import (
    NullOperationLogger,
    OperationLogSink,
    ProviderOperationMetadata,
    ProviderOperationRecord,
)

T = TypeVar("T")
Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class ProviderControlConfig:
    grok_dialogue_timeout_seconds: float = 120.0
    grok_visual_planning_timeout_seconds: float = 90.0
    serpapi_search_timeout_seconds: float = 20.0
    image_fetch_timeout_seconds: float = 15.0

    dialogue_deadline_seconds: float = 300.0
    visual_planning_deadline_seconds: float = 180.0
    automatic_visual_deadline_seconds: float = 600.0
    review_visual_deadline_seconds: float = 600.0
    failed_slot_retry_deadline_seconds: float = 300.0

    max_attempts: int = 3
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 30.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProviderControlConfig":
        values = os.environ if env is None else env

        def first(names: tuple[str, ...], default: str) -> str:
            return next((values[name] for name in names if name in values), default)

        def positive_int(names: tuple[str, ...], default: int) -> int:
            raw = first(names, str(default))
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{names[0]} must be an integer") from exc
            if value <= 0:
                raise ValueError(f"{names[0]} must be greater than zero")
            return value

        def positive_float(names: tuple[str, ...], default: float) -> float:
            raw = first(names, str(default))
            try:
                value = float(raw)
            except ValueError as exc:
                raise ValueError(f"{names[0]} must be a number") from exc
            if value <= 0:
                raise ValueError(f"{names[0]} must be greater than zero")
            return value

        return cls(
            grok_dialogue_timeout_seconds=positive_float(
                ("GROK_DIALOGUE_TIMEOUT_SECONDS",), 120
            ),
            grok_visual_planning_timeout_seconds=positive_float(
                ("GROK_VISUAL_PLANNING_TIMEOUT_SECONDS",), 90
            ),
            serpapi_search_timeout_seconds=positive_float(
                ("SERPAPI_SEARCH_TIMEOUT_SECONDS",), 20
            ),
            image_fetch_timeout_seconds=positive_float(
                ("IMAGE_FETCH_TIMEOUT_SECONDS",), 15
            ),
            dialogue_deadline_seconds=positive_float(
                ("DIALOGUE_GENERATION_DEADLINE_SECONDS",), 300
            ),
            visual_planning_deadline_seconds=positive_float(
                ("VISUAL_PLANNING_DEADLINE_SECONDS",), 180
            ),
            automatic_visual_deadline_seconds=positive_float(
                ("AUTOMATIC_VISUAL_GENERATION_DEADLINE_SECONDS",), 600
            ),
            review_visual_deadline_seconds=positive_float(
                ("REVIEW_VISUAL_GENERATION_DEADLINE_SECONDS",), 600
            ),
            failed_slot_retry_deadline_seconds=positive_float(
                ("FAILED_SLOT_RETRY_DEADLINE_SECONDS",), 300
            ),
            max_attempts=positive_int(("PROVIDER_MAX_ATTEMPTS",), 3),
            retry_base_delay_seconds=positive_float(
                ("PROVIDER_RETRY_BASE_DELAY_SECONDS",), 0.5
            ),
            retry_max_delay_seconds=positive_float(
                ("PROVIDER_RETRY_MAX_DELAY_SECONDS",), 30
            ),
        )


CancelCallback = Callable[[], object]


class CancellationToken:
    """Idempotent cooperative cancellation signal with best-effort abort hooks."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._callbacks: list[CancelCallback] = []
        self.reason: str | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    def cancel(self, reason: str = "cancelled") -> bool:
        if self.cancelled:
            return False
        self.reason = reason
        self._event.set()
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            self._invoke_callback(callback)
        return True

    def add_cancel_callback(self, callback: CancelCallback) -> Callable[[], None]:
        """Register a hook (for example, closing an active HTTP response)."""
        if self.cancelled:
            self._invoke_callback(callback)
            return lambda: None
        self._callbacks.append(callback)

        def remove() -> None:
            with suppress(ValueError):
                self._callbacks.remove(callback)

        return remove

    @staticmethod
    def _invoke_callback(callback: CancelCallback) -> None:
        try:
            result = callback()
            if inspect.isawaitable(result):
                try:
                    asyncio.ensure_future(result)
                except RuntimeError:
                    # Avoid leaking an un-awaited coroutine when cancellation occurs
                    # before an event loop starts.
                    close = getattr(result, "close", None)
                    if close is not None:
                        close()
        except Exception:
            # Cancellation must not be blocked by a provider-specific abort hook.
            return


@dataclass
class OperationScope:
    """A shared cancellation token and absolute monotonic deadline."""

    cancellation: CancellationToken
    deadline: float | None = None
    clock: Clock = time.monotonic

    @classmethod
    def with_timeout(
        cls,
        timeout_seconds: float,
        *,
        cancellation: CancellationToken | None = None,
        clock: Clock = time.monotonic,
    ) -> "OperationScope":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return cls(cancellation or CancellationToken(), clock() + timeout_seconds, clock)

    def remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.clock())

    def raise_if_stopped(self) -> None:
        if self.deadline is not None and self.clock() >= self.deadline:
            self.cancellation.cancel("deadline_exceeded")
            raise GenerationDeadlineExceededError()
        if self.cancellation.cancelled:
            if self.cancellation.reason == "deadline_exceeded":
                raise GenerationDeadlineExceededError()
            raise GenerationCancelledError()


PROVIDER_CONTROL_CONFIG = ProviderControlConfig.from_env()


class ProviderTransportError(Exception):
    """Provider clients may wrap retryable network/transport failures with this."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    jitter: Callable[[], float] = random.random
    wall_clock: Clock = time.time

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if self.base_delay_seconds <= 0 or self.max_delay_seconds <= 0:
            raise ValueError("retry delays must be greater than zero")

    @staticmethod
    def is_retryable_status(status: int | None) -> bool:
        return status == 408 or status == 429 or (status is not None and status >= 500)

    def delay_seconds(
        self, attempt: int, retry_after: str | int | float | None = None
    ) -> float:
        exponential = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(0, attempt - 1)),
        )
        jittered = exponential * (0.5 + 0.5 * min(1.0, max(0.0, self.jitter())))
        parsed_retry_after = parse_retry_after(retry_after, now=self.wall_clock())
        return max(jittered, parsed_retry_after or 0.0)


def parse_retry_after(value: str | int | float | None, *, now: float | None = None) -> float | None:
    """Parse either Retry-After seconds or an RFC HTTP date."""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, parsed.timestamp() - (time.time() if now is None else now))
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class ProviderTelemetry:
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    x_search_calls: int | None = None
    web_search_calls: int | None = None
    search_result_count: int | None = None
    serpapi_cache_hit: bool | None = None
    serpapi_billing_units: int | None = None


class ProviderController:
    """Execute provider attempts with retry and safe operation logs."""

    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        logger: OperationLogSink | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        status_getter: Callable[[object], int | None] | None = None,
        headers_getter: Callable[[object], Mapping[str, object]] | None = None,
        telemetry_getter: Callable[[object], ProviderTelemetry] | None = None,
        transport_error_predicate: Callable[[Exception], bool] | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy(
            max_attempts=PROVIDER_CONTROL_CONFIG.max_attempts,
            base_delay_seconds=PROVIDER_CONTROL_CONFIG.retry_base_delay_seconds,
            max_delay_seconds=PROVIDER_CONTROL_CONFIG.retry_max_delay_seconds,
        )
        self.logger = logger or NullOperationLogger()
        self.clock = clock
        self.sleep = sleep
        self.status_getter = status_getter or _default_status_getter
        self.headers_getter = headers_getter or _default_headers_getter
        self.telemetry_getter = telemetry_getter or _default_telemetry_getter
        self.transport_error_predicate = (
            transport_error_predicate or _default_transport_error_predicate
        )

    async def execute(
        self,
        operation: Callable[[int], Awaitable[T]],
        *,
        metadata: ProviderOperationMetadata,
        request_timeout_seconds: float,
        scope: OperationScope | None = None,
    ) -> T:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than zero")
        scope = scope or OperationScope(CancellationToken())

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            scope.raise_if_stopped()
            response: T | None = None
            error: GenerationError | None = None
            raw_error: Exception | None = None
            unhandled_error: Exception | None = None
            http_status: int | None = None
            headers: Mapping[str, object] = {}
            started_at = self.clock()
            try:
                response = await self._run_request(
                    lambda: operation(attempt), request_timeout_seconds, scope
                )
                http_status = self.status_getter(response)
                headers = self.headers_getter(response)
                if http_status is not None and http_status >= 400:
                    error = error_for_http_status(http_status)
            except GenerationError as exc:
                error = exc
            except Exception as exc:
                raw_error = exc
                exception_status, exception_headers = _status_and_headers_from_exception(exc)
                http_status = exception_status
                headers = exception_headers
                # OpenAI 2.48's APITimeoutError subclasses APIConnectionError, so
                # classify the timeout first. APIStatusError carries its HTTP
                # response on the exception rather than returning it.
                if _is_openai_exception(exc, "APITimeoutError"):
                    error = ProviderTimeoutError()
                elif exception_status is not None:
                    error = error_for_http_status(exception_status)
                elif _is_openai_exception(exc, "APIStatusError"):
                    error = ProviderRequestRejectedError()
                elif self.transport_error_predicate(exc):
                    error = ProviderUnavailableError()
                else:
                    # Log this actual attempt with a generic code, then preserve
                    # the unknown exception for the job boundary to log privately.
                    error = GenerationError()
                    unhandled_error = exc
            finally:
                request_duration = max(0.0, self.clock() - started_at)

            telemetry = self._safe_telemetry(response)
            if telemetry.provider_request_id is None:
                telemetry = ProviderTelemetry(
                    provider_request_id=_request_id_from_headers(headers),
                    **{
                        key: value
                        for key, value in asdict(telemetry).items()
                        if key != "provider_request_id"
                    },
                )

            if error is None:
                self._emit(
                    metadata,
                    attempt,
                    "succeeded",
                    request_duration=request_duration,
                    http_status=http_status,
                    telemetry=telemetry,
                )
                return cast(T, response)

            retryable = (
                self.retry_policy.is_retryable_status(http_status)
                or isinstance(error, (ProviderTimeoutError, ProviderUnavailableError))
                and (raw_error is None or self.transport_error_predicate(raw_error))
            )
            will_retry = retryable and attempt < self.retry_policy.max_attempts
            self._emit(
                metadata,
                attempt,
                "retrying" if will_retry else _status_for_error(error),
                request_duration=request_duration,
                http_status=http_status,
                telemetry=telemetry,
                error=error,
            )
            if unhandled_error is not None:
                raise unhandled_error.with_traceback(unhandled_error.__traceback__)
            if not will_retry:
                raise error from raw_error

            retry_after = _case_insensitive_header(headers, "retry-after")
            delay = self.retry_policy.delay_seconds(attempt, retry_after)
            await self._sleep_cooperatively(delay, scope)

        raise RuntimeError("retry loop exited unexpectedly")

    async def _run_request(
        self,
        operation: Callable[[], Awaitable[T]],
        timeout_seconds: float,
        scope: OperationScope,
    ) -> T:
        remaining = scope.remaining()
        effective_timeout = timeout_seconds if remaining is None else min(timeout_seconds, remaining)
        if effective_timeout <= 0:
            scope.raise_if_stopped()

        request_task = asyncio.ensure_future(operation())
        cancel_wait = asyncio.create_task(scope.cancellation.wait())
        try:
            done, _ = await asyncio.wait(
                {request_task, cancel_wait},
                timeout=effective_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if request_task in done:
                result = request_task.result()
                # A transport may complete at the same moment cancellation/deadline
                # wins. Ignore that late response rather than starting more work.
                scope.raise_if_stopped()
                return result
            request_task.cancel()
            with suppress(asyncio.CancelledError):
                await request_task
            if cancel_wait in done:
                scope.raise_if_stopped()
            if scope.remaining() == 0:
                scope.raise_if_stopped()
            raise ProviderTimeoutError()
        except asyncio.CancelledError:
            request_task.cancel()
            with suppress(asyncio.CancelledError):
                await request_task
            raise
        finally:
            cancel_wait.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_wait

    async def _sleep_cooperatively(self, delay: float, scope: OperationScope) -> None:
        scope.raise_if_stopped()
        sleep_task = asyncio.ensure_future(self.sleep(delay))
        cancel_wait = asyncio.create_task(scope.cancellation.wait())
        try:
            done, _ = await asyncio.wait(
                {sleep_task, cancel_wait},
                timeout=scope.remaining(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if sleep_task in done:
                sleep_task.result()
                scope.raise_if_stopped()
                return
            sleep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sleep_task
            scope.raise_if_stopped()
        finally:
            cancel_wait.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_wait

    def _safe_telemetry(self, response: object | None) -> ProviderTelemetry:
        if response is None:
            return ProviderTelemetry()
        try:
            return self.telemetry_getter(response)
        except Exception:
            return ProviderTelemetry()

    def _emit(
        self,
        metadata: ProviderOperationMetadata,
        attempt: int,
        status: str,
        *,
        request_duration: float | None = None,
        http_status: int | None = None,
        telemetry: ProviderTelemetry | None = None,
        error: GenerationError | None = None,
    ) -> None:
        telemetry = telemetry or ProviderTelemetry()
        self.logger.emit(
            ProviderOperationRecord(
                **asdict(metadata),
                attempt=attempt,
                status=status,
                queue_wait_ms=None,
                request_duration_ms=(
                    round(request_duration * 1000)
                    if request_duration is not None
                    else None
                ),
                http_status=http_status,
                error_code=error.code if error is not None else None,
                **asdict(telemetry),
            )
        )


def error_for_http_status(status: int) -> GenerationError:
    if status in (401, 403):
        return ProviderAuthConfigurationError(details={"http_status": status})
    if status == 429:
        return ProviderRateLimitError(details={"http_status": status})
    if status == 408:
        return ProviderTimeoutError(details={"http_status": status})
    if status >= 500:
        return ProviderUnavailableError(details={"http_status": status})
    return ProviderRequestRejectedError(details={"http_status": status})


def _default_status_getter(response: object) -> int | None:
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _default_headers_getter(response: object) -> Mapping[str, object]:
    headers = getattr(response, "headers", {})
    return headers if isinstance(headers, Mapping) else {}


def _default_telemetry_getter(response: object) -> ProviderTelemetry:
    del response
    return ProviderTelemetry()


def _default_transport_error_predicate(error: Exception) -> bool:
    if isinstance(error, (ProviderTransportError, ConnectionError, TimeoutError, OSError)):
        return True
    if _is_openai_exception(error, "APIConnectionError"):
        return True
    # Keep this module import-safe without requiring a provider SDK at startup,
    # while recognizing the transport base classes used by supported clients.
    return any(
        (base.__module__.startswith(("httpx", "httpcore")) and base.__name__ == "TransportError")
        or (base.__module__.startswith("aiohttp") and base.__name__ == "ClientError")
        for base in type(error).__mro__
    )


def _is_openai_exception(error: Exception, class_name: str) -> bool:
    """Recognize OpenAI SDK errors without importing the optional SDK here."""

    return any(
        base.__module__.split(".", 1)[0] == "openai" and base.__name__ == class_name
        for base in type(error).__mro__
    )


def _status_and_headers_from_exception(
    error: Exception,
) -> tuple[int | None, Mapping[str, object]]:
    response = getattr(error, "response", None)
    status = getattr(error, "status_code", None)
    if not isinstance(status, int) and response is not None:
        status = _default_status_getter(response)
    headers = _default_headers_getter(response) if response is not None else {}
    return status if isinstance(status, int) else None, headers


def _case_insensitive_header(headers: Mapping[str, object], name: str) -> object | None:
    lowered = name.lower()
    return next((value for key, value in headers.items() if str(key).lower() == lowered), None)


def _request_id_from_headers(headers: Mapping[str, object]) -> str | None:
    for name in ("x-request-id", "request-id", "x-serpapi-request-id"):
        value = _case_insensitive_header(headers, name)
        if value is not None:
            return str(value)
    return None


def _status_for_error(error: GenerationError) -> str:
    if isinstance(error, GenerationCancelledError):
        return "cancelled"
    if isinstance(error, GenerationDeadlineExceededError):
        return "deadline_exceeded"
    return "failed"
