"""Stable, provider-independent errors for generation operations.

Provider diagnostics belong in private backend logs.  These exceptions expose only
short, actionable messages and stable codes that are safe to return to clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class RetryAction(str, Enum):
    """The next action a client may safely offer."""

    RETRY_NOW = "retry_now"
    RETRY_LATER = "retry_later"
    RETRY_FAILED_SLOT = "retry_failed_slot"
    REGENERATE_FROM_CURRENT_NARRATION = "regenerate_from_current_narration"
    CONTACT_OPERATOR = "contact_operator"
    NONE = "none"


@dataclass(frozen=True)
class GenerationErrorEnvelope:
    code: str
    message: str
    retry_action: RetryAction

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "retry_action": self.retry_action.value,
        }


class GenerationError(Exception):
    """Base class for failures crossing the generation service boundary."""

    code = "generation_failed"
    default_message = "Generation could not be completed."
    retry_action = RetryAction.RETRY_NOW

    def __init__(
        self,
        diagnostic_message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        # The exception string and envelope are deliberately fixed to the safe,
        # class-level message. Provider diagnostics remain backend-only even when
        # a caller supplies them positionally.
        self.message = self.default_message
        self.details = dict(details or {})
        if diagnostic_message is not None:
            self.details.setdefault("diagnostic_message", diagnostic_message)
        super().__init__(self.message)

    @property
    def envelope(self) -> GenerationErrorEnvelope:
        return GenerationErrorEnvelope(self.code, self.message, self.retry_action)

    @property
    def retryable(self) -> bool:
        return self.retry_action not in (RetryAction.CONTACT_OPERATOR, RetryAction.NONE)

    def to_dict(self) -> dict[str, str]:
        return self.envelope.to_dict()


class ProviderTimeoutError(GenerationError):
    code = "provider_timeout"
    default_message = "The generation provider timed out. Try again."
    retry_action = RetryAction.RETRY_NOW


class ProviderUnavailableError(GenerationError):
    code = "provider_unavailable"
    default_message = "The generation provider is temporarily unavailable."
    retry_action = RetryAction.RETRY_LATER


class ProviderRateLimitError(GenerationError):
    code = "provider_rate_limited"
    default_message = "The generation provider is busy. Try again later."
    retry_action = RetryAction.RETRY_LATER


class ProviderRequestRejectedError(GenerationError):
    code = "provider_request_rejected"
    default_message = "The generation provider rejected the request."
    retry_action = RetryAction.CONTACT_OPERATOR


class ProviderAuthConfigurationError(GenerationError):
    code = "provider_auth_configuration"
    default_message = "Generation is not configured correctly."
    retry_action = RetryAction.CONTACT_OPERATOR


class InvalidProviderOutputError(GenerationError):
    code = "invalid_provider_output"
    default_message = "The provider returned an invalid generation. Try again."
    retry_action = RetryAction.RETRY_NOW


class MissingRequiredSearchError(GenerationError):
    code = "missing_required_search"
    default_message = "The required source search did not complete. Try again."
    retry_action = RetryAction.RETRY_NOW


class ImageSearchError(GenerationError):
    code = "image_search_failed"
    default_message = "Image search could not be completed."
    retry_action = RetryAction.RETRY_FAILED_SLOT


class ImageRetrievalError(GenerationError):
    code = "image_retrieval_failed"
    default_message = "The selected image could not be retrieved."
    retry_action = RetryAction.RETRY_FAILED_SLOT


class ImageValidationError(GenerationError):
    code = "image_validation_failed"
    default_message = "The selected image could not be used."
    retry_action = RetryAction.RETRY_FAILED_SLOT


class MediaAssetQuotaExceededError(GenerationError):
    code = "media_asset_quota_exceeded"
    default_message = (
        "This project has reached its image limit. Delete unused images and try again."
    )
    retry_action = RetryAction.CONTACT_OPERATOR


class EditorProjectUnavailableError(GenerationError):
    code = "editor_project_unavailable"
    default_message = "This project is no longer available."
    retry_action = RetryAction.NONE


class StaleNarrationError(GenerationError):
    code = "stale_narration_composition"
    default_message = "Narration changed. Regenerate visuals from the current narration."
    retry_action = RetryAction.REGENERATE_FROM_CURRENT_NARRATION


class GenerationCancelledError(GenerationError):
    code = "cancelled"
    default_message = "Generation was cancelled."
    retry_action = RetryAction.NONE


class GenerationDeadlineExceededError(GenerationError):
    code = "deadline_exceeded"
    default_message = "Generation took too long. Try again."
    retry_action = RetryAction.RETRY_NOW
