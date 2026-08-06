"""Focused SerpApi Google Images Light discovery tests."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "serpapi"

from services.candidate_token_service import CandidateBinding, CandidateTokenSigner
from services.generation_errors import ImageSearchError
from services.image_discovery_service import SerpApiGoogleImagesClient
from services.provider_controls import ProviderController, RetryPolicy


def run(coroutine):
    return asyncio.run(coroutine)


def controller():
    return ProviderController(
        retry_policy=RetryPolicy(max_attempts=1),
    )


def result(position, original, **overrides):
    value = {
        "position": position,
        "original": original,
        "serpapi_thumbnail": f"https://serpapi.example/thumb-{position}.jpg",
        "thumbnail": f"https://google.example/thumb-{position}.jpg",
        "title": f"Result {position}",
        "source": "Example",
        "link": f"https://source.example/page-{position}",
        "original_width": 800,
        "original_height": 600,
    }
    value.update(overrides)
    return value


def test_search_sends_exact_safe_light_request_without_pagination_and_returns_four_ranked_eligible():
    seen_requests = []
    payload = {
        "search_metadata": {"status": "Success", "id": "search-id"},
        "images_results": [
            result(8, "https://images.example/8.jpg"),
            result(1, "https://images.example/unsafe.jpg", unsafe=True),
            result(2, "x-raw-image://pdf/2"),
            result(3, "https://images.example/small.jpg", original_width=299),
            result(4, "https://user:password@images.example/credential.jpg"),
            result(7, "https://images.example/7.jpg", serpapi_thumbnail=None),
            result(5, "https://images.example/5.jpg"),
            result(6, "https://images.example/6.jpg"),
            result(9, "https://images.example/9.jpg"),
        ],
    }

    def handler(request):
        seen_requests.append(request)
        return httpx.Response(200, json=payload)

    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(handler),
            controller=controller(),
        )
        try:
            return await service.search_images("  Saturn V launch  ")
        finally:
            await service.aclose()

    candidates = run(scenario())

    assert [candidate.position for candidate in candidates] == [5, 6, 7, 8]
    assert candidates[2].thumbnail_url == "https://google.example/thumb-7.jpg"
    assert len(seen_requests) == 1
    params = seen_requests[0].url.params
    assert dict(params) == {
        "engine": "google_images_light",
        "q": "Saturn V launch",
        "safe": "active",
        "api_key": "private-key",
    }
    assert all(name not in params for name in ("start", "ijn", "num"))


def test_manual_review_search_logs_query_origin_and_curated_ranked_results():
    records = []
    payload = {
        "search_metadata": {"status": "Success"},
        "images_results": [result(1, "https://images.example/private-original.jpg")],
    }

    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=payload)
            ),
            controller=controller(),
            content_logger=SimpleNamespace(emit=records.append),
        )
        try:
            await service.search_images(
                "reaction meme",
                job_id="job",
                project_id="project",
                user_id=42,
                search_origin="review_manual",
                slot_id="slot-1",
            )
        finally:
            await service.aclose()

    run(scenario())

    assert len(records) == 1
    record = records[0]
    assert record.search_origin == "review_manual"
    assert record.slot_id == "slot-1"
    assert record.response["query"] == "reaction meme"
    assert record.response["results"][0] == {
        "position": 1,
        "title": "Result 1",
        "source": "Example",
        "original_width": 800,
        "original_height": 600,
    }
    serialized = str(record.to_dict())
    assert "https://" not in serialized
    assert "private-original" not in serialized
    assert "private-key" not in serialized


def test_review_candidates_expose_stable_metadata_and_signed_token_but_not_original():
    payload = {
        "search_metadata": {"status": "Success"},
        "images_results": [result(1, "https://images.example/original.jpg")],
    }

    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=payload)
            ),
            controller=controller(),
        )
        binding = CandidateBinding(
            user_id=42,
            project_id="project",
            composition_id="composition",
            slot_id=3,
            query="Saturn V launch",
        )
        signer = CandidateTokenSigner(b"x" * 32, clock=lambda: 1_800_000_000)
        try:
            candidates = await service.discover_review_candidates(binding, signer)
        finally:
            await service.aclose()
        return candidates[0], signer, binding

    candidate, signer, binding = run(scenario())
    dto = candidate.to_dict()

    assert set(dto) == {
        "token",
        "position",
        "thumbnail_url",
        "title",
        "source",
        "source_page_url",
        "original_width",
        "original_height",
        "license_details_url",
    }
    assert "original_url" not in dto
    assert signer.verify(candidate.token, binding).original_url == (
        "https://images.example/original.jpg"
    )


def test_successful_empty_search_is_a_valid_zero_candidate_result():
    payload = {
        "search_metadata": {"status": "Success"},
        "error": "Google has not returned any results",
    }

    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=payload)
            ),
            controller=controller(),
        )
        try:
            return await service.search_images("no matching image")
        finally:
            await service.aclose()

    assert run(scenario()) == ()


def test_real_google_images_light_response_shape_is_parsed_correctly():
    """Regression fixture captured from a live Google Images Light response.

    Locks in the actual field names (``original``, ``original_width``,
    ``serpapi_thumbnail``, ``link``, ...) and confirms an out-of-range
    original (4900px wide, over the 4096px ingestion ceiling) is excluded
    while pagination metadata is never followed.
    """
    payload = json.loads((FIXTURES_DIR / "google_images_light_coffee.json").read_text())
    seen_requests = []

    def handler(request):
        seen_requests.append(request)
        return httpx.Response(200, json=payload)

    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(handler),
            controller=controller(),
        )
        try:
            return await service.search_images("Coffee")
        finally:
            await service.aclose()

    candidates = run(scenario())

    assert [candidate.position for candidate in candidates] == [1, 2, 3, 4]
    assert candidates[0].original_width == 3200
    assert candidates[0].source == "Wikipedia, the free encyclopedia"
    assert candidates[0].source_page_url == "https://en.wikipedia.org/wiki/Coffee"
    assert candidates[0].thumbnail_url == (
        "https://serpapi.com/images/url/H0cLdXicu5mVUVJSUGylr5-al1xUWVCSmqJbkpRnoJdeXJJYkpmsl5yfq5-"
        "Zm5ieWmxfaAuUsXL0S7F0Tw50dHYrL8k0zTUKdg6vyMkKM3E3i6woD87xCXdL93PL1TWPt6zy8k2xKPM0cUvxzYsqVisGAHtVJjI"
    )
    assert len(seen_requests) == 1
    assert "serpapi_pagination" not in {p for p in seen_requests[0].url.params}


@pytest.mark.parametrize(
    "payload",
    [
        {"search_metadata": {"status": "Error"}, "error": "provider detail"},
        {"search_metadata": {"status": "Success"}, "images_results": {}},
        ["not", "an", "object"],
    ],
)
def test_provider_level_or_schema_failure_is_typed(payload):
    async def scenario():
        service = SerpApiGoogleImagesClient(
            api_key="private-key",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=payload)
            ),
            controller=controller(),
        )
        try:
            await service.search_images("Saturn V")
        finally:
            await service.aclose()

    with pytest.raises(ImageSearchError):
        run(scenario())
