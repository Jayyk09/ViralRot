"""Privacy-safe structured logging for external provider operations."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProviderOperationMetadata:
    """Allowlisted correlation data; provider content deliberately has no field."""

    provider: str
    operation: str
    model: str | None = None
    job_id: str | None = None
    project_id: str | None = None
    user_id: str | int | None = None


@dataclass(frozen=True)
class ProviderOperationRecord:
    """One safe log record for one actual provider request attempt."""

    provider: str
    operation: str
    attempt: int
    status: str
    model: str | None = None
    job_id: str | None = None
    project_id: str | None = None
    user_id: str | int | None = None
    queue_wait_ms: int | None = None
    request_duration_ms: int | None = None
    http_status: int | None = None
    provider_request_id: str | None = None
    error_code: str | None = None

    # Grok usage (all optional because failed responses may omit usage).
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    x_search_calls: int | None = None
    web_search_calls: int | None = None

    # SerpApi operation metadata.  No result/source URLs are accepted here.
    search_result_count: int | None = None
    serpapi_cache_hit: bool | None = None
    serpapi_billing_units: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ProviderContentRecord:
    """Curated provider output used to improve generation and search quality.

    Prompts, API credentials, signed candidate tokens, and image/source URLs
    must never be placed in ``response``.
    """

    provider: str
    operation: str
    response: Mapping[str, object] | Sequence[object]
    model: str | None = None
    job_id: str | None = None
    project_id: str | None = None
    user_id: str | int | None = None
    search_origin: str | None = None
    slot_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class OperationLogSink(Protocol):
    def emit(self, record: ProviderOperationRecord) -> None:
        """Emit an allowlisted provider-operation record."""


class ContentLogSink(Protocol):
    def emit(self, record: ProviderContentRecord) -> None:
        """Emit one curated provider-output or user-selection record."""


class StructuredOperationLogger:
    """Write provider records as compact JSON through the standard logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("viralrot.provider_operations")

    def emit(self, record: ProviderOperationRecord) -> None:
        # separators and sorted keys make local logs easy to diff and test.
        self._logger.info(
            json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
        )


class StructuredContentLogger:
    """Write curated provider outputs separately from operational telemetry."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("viralrot.provider_content")

    def emit(self, record: ProviderContentRecord) -> None:
        self._logger.info(
            json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )


class NullOperationLogger:
    """Useful when a caller supplies another metrics/logging integration."""

    def emit(self, record: ProviderOperationRecord) -> None:
        del record


class NullContentLogger:
    """Disable curated content logging for a test or alternate integration."""

    def emit(self, record: ProviderContentRecord) -> None:
        del record
