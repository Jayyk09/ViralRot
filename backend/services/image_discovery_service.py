"""SerpApi Google Images Light discovery and stable review candidate DTOs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

import httpx

from services.candidate_token_service import CandidateBinding, CandidateTokenSigner
from services.generation_errors import ImageSearchError, ProviderAuthConfigurationError
from services.provider_controls import (
    PROVIDER_CONTROL_CONFIG,
    OperationScope,
    ProviderController,
    ProviderTelemetry,
)
from services.provider_logging import (
    ContentLogSink,
    ProviderContentRecord,
    ProviderOperationMetadata,
    StructuredContentLogger,
    StructuredOperationLogger,
)

SERPAPI_IMAGES_ENDPOINT = "https://serpapi.com/search.json"
MAX_DISCOVERY_CANDIDATES = 4
MIN_DISCOVERED_IMAGE_DIMENSION = 300
MAX_DISCOVERED_IMAGE_DIMENSION = 4096
SearchOrigin = Literal["automatic", "review_initial", "review_manual", "review_retry"]


@dataclass(frozen=True)
class RankedImageCandidate:
    """Internal ranked result. The original URL never belongs in a public DTO."""

    position: int
    original_url: str
    thumbnail_url: str | None
    title: str | None
    source: str | None
    source_page_url: str | None
    original_width: int | None
    original_height: int | None
    license_details_url: str | None


@dataclass(frozen=True)
class ReviewImageCandidate:
    """Stable client-facing candidate; selection is authorized only by token."""

    token: str
    position: int
    thumbnail_url: str | None
    title: str | None
    source: str | None
    source_page_url: str | None
    original_width: int | None
    original_height: int | None
    license_details_url: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "token": self.token,
            "position": self.position,
            "thumbnail_url": self.thumbnail_url,
            "title": self.title,
            "source": self.source,
            "source_page_url": self.source_page_url,
            "original_width": self.original_width,
            "original_height": self.original_height,
            "license_details_url": self.license_details_url,
        }


class SerpApiGoogleImagesClient:
    """One-page Google Images Light client behind shared SerpApi controls."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        controller: ProviderController | None = None,
        endpoint: str = SERPAPI_IMAGES_ENDPOINT,
        request_timeout_seconds: float | None = None,
        content_logger: ContentLogSink | None = None,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("pass either client or transport, not both")
        self._api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self._endpoint = endpoint
        self._content_logger = content_logger or StructuredContentLogger()
        self.request_timeout_seconds = (
            PROVIDER_CONTROL_CONFIG.serpapi_search_timeout_seconds
            if request_timeout_seconds is None
            else request_timeout_seconds
        )
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than zero")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self.request_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        self._controller = controller or ProviderController(
            logger=StructuredOperationLogger(),
            telemetry_getter=serpapi_response_telemetry,
        )

    async def __aenter__(self) -> "SerpApiGoogleImagesClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_images(
        self,
        query: str,
        *,
        job_id: str | None = None,
        project_id: str | None = None,
        user_id: str | int | None = None,
        scope: OperationScope | None = None,
        search_origin: SearchOrigin = "automatic",
        slot_id: str | None = None,
    ) -> tuple[RankedImageCandidate, ...]:
        normalized_query = _validated_query(query)
        if not self._api_key:
            raise ProviderAuthConfigurationError()

        params = {
            "engine": "google_images_light",
            "q": normalized_query,
            "safe": "active",
            "api_key": self._api_key,
        }

        async def search_attempt(_attempt: int) -> httpx.Response:
            response = await self._client.get(
                self._endpoint,
                params=params,
                headers={"Accept": "application/json"},
                follow_redirects=False,
                timeout=self.request_timeout_seconds,
            )
            # HTTP failures are classified by ProviderController. Provider-level
            # Search API failures often arrive as HTTP 200 and are checked here so
            # the attempt is logged as failed without logging response content.
            if response.status_code < 400:
                _validated_response_payload(response)
            return response

        response = await self._controller.execute(
            search_attempt,
            metadata=ProviderOperationMetadata(
                provider="serpapi",
                operation="image_search",
                job_id=job_id,
                project_id=project_id,
                user_id=user_id,
            ),
            request_timeout_seconds=self.request_timeout_seconds,
            scope=scope,
        )
        payload = _validated_response_payload(response)
        candidates = ranked_eligible_candidates(payload.get("images_results", []))
        self._content_logger.emit(
            ProviderContentRecord(
                provider="serpapi",
                operation="image_search_response",
                job_id=job_id,
                project_id=project_id,
                user_id=user_id,
                search_origin=search_origin,
                slot_id=slot_id,
                response={
                    "query": normalized_query,
                    "results": [_candidate_log_dict(candidate) for candidate in candidates],
                },
            )
        )
        return candidates

    async def discover_review_candidates(
        self,
        binding: CandidateBinding,
        signer: CandidateTokenSigner,
        *,
        job_id: str | None = None,
        scope: OperationScope | None = None,
        search_origin: SearchOrigin = "review_initial",
    ) -> tuple[ReviewImageCandidate, ...]:
        candidates = await self.search_images(
            binding.query,
            job_id=job_id,
            project_id=binding.project_id,
            user_id=binding.user_id,
            scope=scope,
            search_origin=search_origin,
            slot_id=binding.slot_id,
        )
        return build_review_candidates(candidates, binding, signer)


def build_review_candidates(
    candidates: Sequence[RankedImageCandidate],
    binding: CandidateBinding,
    signer: CandidateTokenSigner,
) -> tuple[ReviewImageCandidate, ...]:
    """Sign internal originals and project only safe review-display fields."""

    return tuple(
        ReviewImageCandidate(
            token=signer.sign(binding, candidate.original_url),
            position=candidate.position,
            thumbnail_url=candidate.thumbnail_url,
            title=candidate.title,
            source=candidate.source,
            source_page_url=candidate.source_page_url,
            original_width=candidate.original_width,
            original_height=candidate.original_height,
            license_details_url=candidate.license_details_url,
        )
        for candidate in candidates[:MAX_DISCOVERY_CANDIDATES]
    )


def ranked_eligible_candidates(
    raw_results: object,
) -> tuple[RankedImageCandidate, ...]:
    """Adapt ranked provider objects, discarding only known technical failures."""

    if not isinstance(raw_results, list):
        raise ImageSearchError(details={"reason": "images_results_not_array"})

    ranked: list[tuple[int, int, Mapping[str, Any]]] = []
    for response_index, raw in enumerate(raw_results):
        if not isinstance(raw, Mapping):
            continue
        position = _positive_int(raw.get("position")) or response_index + 1
        ranked.append((position, response_index, raw))
    ranked.sort(key=lambda item: (item[0], item[1]))

    candidates: list[RankedImageCandidate] = []
    for position, _response_index, raw in ranked:
        if raw.get("unsafe") is True:
            continue
        original_url = _optional_http_url(raw.get("original"), reject_credentials=True)
        if original_url is None:
            continue

        width = _positive_int(raw.get("original_width"))
        height = _positive_int(raw.get("original_height"))
        if _known_dimension_is_ineligible(width) or _known_dimension_is_ineligible(height):
            continue

        candidates.append(
            RankedImageCandidate(
                position=position,
                original_url=original_url,
                thumbnail_url=_optional_http_url(
                    raw.get("serpapi_thumbnail") or raw.get("thumbnail"),
                    reject_credentials=True,
                ),
                title=_optional_text(raw.get("title")),
                source=_optional_text(raw.get("source")),
                source_page_url=_optional_http_url(
                    raw.get("link"), reject_credentials=True
                ),
                original_width=width,
                original_height=height,
                license_details_url=_optional_http_url(
                    raw.get("license_details_url"), reject_credentials=True
                ),
            )
        )
        if len(candidates) == MAX_DISCOVERY_CANDIDATES:
            break

    return tuple(candidates)


def _candidate_log_dict(candidate: RankedImageCandidate) -> dict[str, object]:
    """Return useful ranking data without hidden originals or signed tokens."""

    return {
        key: value
        for key, value in {
            "position": candidate.position,
            "title": candidate.title,
            "source": candidate.source,
            "original_width": candidate.original_width,
            "original_height": candidate.original_height,
        }.items()
        if value is not None
    }


def serpapi_response_telemetry(response: object) -> ProviderTelemetry:
    if not isinstance(response, httpx.Response):
        return ProviderTelemetry()
    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        return ProviderTelemetry()
    if not isinstance(payload, Mapping):
        return ProviderTelemetry()
    metadata = payload.get("search_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    results = payload.get("images_results")
    return ProviderTelemetry(
        provider_request_id=_optional_text(metadata.get("id")),
        search_result_count=len(results) if isinstance(results, list) else None,
        serpapi_cache_hit=_optional_bool(
            metadata.get("cache_hit", metadata.get("cached"))
        ),
        serpapi_billing_units=_nonnegative_int(metadata.get("billing_units")),
    )


def _validated_response_payload(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except (ValueError, UnicodeError) as exc:
        raise ImageSearchError(details={"reason": "invalid_json"}) from exc
    if not isinstance(payload, Mapping):
        raise ImageSearchError(details={"reason": "response_not_object"})

    metadata = payload.get("search_metadata")
    status = metadata.get("status") if isinstance(metadata, Mapping) else None
    if status != "Success":
        raise ImageSearchError(details={"reason": "provider_search_not_successful"})

    results = payload.get("images_results", [])
    if not isinstance(results, list):
        raise ImageSearchError(details={"reason": "images_results_not_array"})
    # A successful empty search is a valid zero-candidate slot even when SerpApi
    # includes its human-readable top-level `error` explanation.
    if payload.get("error") and results:
        raise ImageSearchError(details={"reason": "provider_reported_error"})
    return payload


def _validated_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-blank string")
    normalized = query.strip()
    if len(normalized) > 160:
        raise ValueError("query must be at most 160 characters")
    return normalized


def _optional_http_url(value: object, *, reject_credentials: bool) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, UnicodeError):
        return None
    if url.scheme not in ("http", "https") or not url.host:
        return None
    if reject_credentials and url.userinfo:
        return None
    return value


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _known_dimension_is_ineligible(value: int | None) -> bool:
    return value is not None and not (
        MIN_DISCOVERED_IMAGE_DIMENSION
        <= value
        <= MAX_DISCOVERED_IMAGE_DIMENSION
    )


__all__ = [
    "MAX_DISCOVERY_CANDIDATES",
    "MIN_DISCOVERED_IMAGE_DIMENSION",
    "RankedImageCandidate",
    "ReviewImageCandidate",
    "SERPAPI_IMAGES_ENDPOINT",
    "SerpApiGoogleImagesClient",
    "build_review_candidates",
    "ranked_eligible_candidates",
    "serpapi_response_telemetry",
]
