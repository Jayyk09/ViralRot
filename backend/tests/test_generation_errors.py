"""Public generation failures expose stable, content-free envelopes."""

import json
import logging

from services.generation_errors import (
    GenerationCancelledError,
    ImageRetrievalError,
    InvalidProviderOutputError,
    MissingRequiredSearchError,
    StaleNarrationError,
)
from services.provider_logging import (
    ProviderOperationRecord,
    StructuredOperationLogger,
)


def test_generation_error_envelopes_are_stable_and_hide_private_details():
    error = InvalidProviderOutputError(
        details={"raw_response": "secret dialogue", "api_key": "secret-key"}
    )
    assert error.to_dict() == {
        "code": "invalid_provider_output",
        "message": "The provider returned an invalid generation. Try again.",
        "retry_action": "retry_now",
    }
    assert "secret" not in str(error)


def test_diagnostic_message_cannot_change_the_public_envelope():
    error = InvalidProviderOutputError("raw Grok schema failure: secret output")

    assert error.to_dict() == {
        "code": "invalid_provider_output",
        "message": "The provider returned an invalid generation. Try again.",
        "retry_action": "retry_now",
    }
    assert "secret" not in str(error)
    assert "secret" in error.details["diagnostic_message"]


def test_domain_errors_expose_actionable_retry_actions():
    assert MissingRequiredSearchError().to_dict()["retry_action"] == "retry_now"
    assert ImageRetrievalError().to_dict()["retry_action"] == "retry_failed_slot"
    assert StaleNarrationError().to_dict()["retry_action"] == (
        "regenerate_from_current_narration"
    )
    assert GenerationCancelledError().to_dict() == {
        "code": "cancelled",
        "message": "Generation was cancelled.",
        "retry_action": "none",
    }


def test_structured_logger_emits_only_allowlisted_non_null_fields(caplog):
    logger = logging.getLogger("test.provider.operations")
    sink = StructuredOperationLogger(logger)
    with caplog.at_level(logging.INFO, logger=logger.name):
        sink.emit(
            ProviderOperationRecord(
                provider="serpapi",
                operation="image_search",
                attempt=1,
                status="succeeded",
                job_id="job-1",
                search_result_count=4,
                serpapi_cache_hit=True,
            )
        )

    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "attempt": 1,
        "job_id": "job-1",
        "operation": "image_search",
        "provider": "serpapi",
        "search_result_count": 4,
        "serpapi_cache_hit": True,
        "status": "succeeded",
    }
    assert not ({"prompt", "dialogue", "url", "citation", "api_key"} & payload.keys())
