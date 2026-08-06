"""Deterministic SSRF, redirect, retry, timeout, and streaming tests."""

import asyncio
from io import BytesIO
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image

from services.remote_image_fetcher import (
    RemoteImageContentTypeError,
    RemoteImageDestinationBlockedError,
    RemoteImageFetcher,
    RemoteImageHTTPError,
    RemoteImageIngestionService,
    RemoteImageRedirectLimitError,
    RemoteImageTimeoutError,
    RemoteImageTooLargeError,
    RemoteImageURLRejectedError,
)
from services.provider_controls import RetryPolicy

PUBLIC_IP = "93.184.216.34"
SECOND_PUBLIC_IP = "1.1.1.1"


def run(coroutine):
    return asyncio.run(coroutine)


def png_bytes(width=300, height=300):
    output = BytesIO()
    Image.new("RGB", (width, height), "blue").save(output, format="PNG")
    return output.getvalue()


class RecordingResolver:
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    async def __call__(self, host, port):
        self.calls.append((host, port))
        answer = self.answers.get(host, PUBLIC_IP)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, list) else [answer]


class AsyncChunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


async def no_sleep(_seconds):
    return None


def make_fetcher(handler, resolver, **overrides):
    return RemoteImageFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver,
        retry_policy=RetryPolicy(
            max_attempts=2,
            base_delay_seconds=0.001,
            max_delay_seconds=0.001,
            jitter=lambda: 0,
        ),
        sleep=no_sleep,
        **overrides,
    )


def test_request_is_dns_pinned_with_original_host_sni_and_no_credentials_or_cookies():
    seen = []
    resolver = RecordingResolver()

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "set-cookie": "tracker=yes"},
            content=png_bytes(),
        )

    async def scenario():
        fetcher = make_fetcher(handler, resolver)
        try:
            return await fetcher.fetch("https://images.example/photo.png?size=large")
        finally:
            await fetcher.aclose()

    fetched = run(scenario())

    assert fetched.content_type == "image/png"
    assert fetched.data.startswith(b"\x89PNG")
    assert resolver.calls == [("images.example", 443)]
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].url.path == "/photo.png"
    assert seen[0].url.query == b"size=large"
    assert seen[0].headers["host"] == "images.example"
    assert seen[0].extensions["sni_hostname"] == "images.example"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@example.com/image.jpg",
        "https:///missing-host.jpg",
    ],
)
def test_rejects_non_http_credentials_and_missing_hosts_without_network(url):
    calls = []

    async def scenario():
        fetcher = make_fetcher(
            lambda request: calls.append(request), RecordingResolver()
        )
        try:
            await fetcher.fetch(url)
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageURLRejectedError):
        run(scenario())
    assert calls == []


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::",
        "::ffff:127.0.0.1",
        "2002:7f00:0001::",
    ],
)
def test_blocks_non_global_ipv4_ipv6_and_transition_destinations(address):
    calls = []

    async def scenario():
        fetcher = make_fetcher(
            lambda request: calls.append(request), RecordingResolver()
        )
        host = f"[{address}]" if ":" in address else address
        try:
            await fetcher.fetch(f"http://{host}/image.jpg")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageDestinationBlockedError):
        run(scenario())
    assert calls == []


def test_rejects_mixed_public_private_dns_answers_before_connecting():
    calls = []
    resolver = RecordingResolver(
        {"mixed.example": [PUBLIC_IP, "169.254.169.254"]}
    )

    async def scenario():
        fetcher = make_fetcher(
            lambda request: calls.append(request), resolver
        )
        try:
            await fetcher.fetch("https://mixed.example/image.jpg")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageDestinationBlockedError):
        run(scenario())
    assert calls == []


def test_validates_and_pins_every_redirect_and_never_forwards_set_cookie():
    resolver = RecordingResolver(
        {"first.example": PUBLIC_IP, "second.example": SECOND_PUBLIC_IP}
    )
    seen = []

    def handler(request):
        seen.append(request)
        if request.headers["host"] == "first.example":
            return httpx.Response(
                302,
                headers={
                    "location": "https://second.example/final.png",
                    "set-cookie": "do-not-forward=yes",
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=png_bytes(),
        )

    async def scenario():
        fetcher = make_fetcher(handler, resolver)
        try:
            return await fetcher.fetch("https://first.example/start")
        finally:
            await fetcher.aclose()

    run(scenario())

    assert resolver.calls == [
        ("first.example", 443),
        ("second.example", 443),
    ]
    assert [request.url.host for request in seen] == [PUBLIC_IP, SECOND_PUBLIC_IP]
    assert "cookie" not in seen[1].headers
    assert seen[1].headers["host"] == "second.example"


def test_private_redirect_is_rejected_before_second_request_and_not_retried():
    calls = []
    resolver = RecordingResolver({"first.example": PUBLIC_IP})

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/x"})

    async def scenario():
        fetcher = make_fetcher(handler, resolver)
        try:
            await fetcher.fetch("https://first.example/start")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageDestinationBlockedError):
        run(scenario())
    assert len(calls) == 1


def test_allows_three_redirects_but_rejects_a_fourth():
    calls = []

    def handler(request):
        calls.append(request)
        step = int(request.url.path.removeprefix("/step/"))
        return httpx.Response(302, headers={"location": f"/step/{step + 1}"})

    async def scenario():
        fetcher = make_fetcher(handler, RecordingResolver())
        try:
            await fetcher.fetch("https://images.example/step/0")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageRedirectLimitError):
        run(scenario())
    assert len(calls) == 4


def test_stream_cap_is_enforced_even_without_content_length():
    def handler(_request):
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            stream=AsyncChunks([b"a" * 8, b"b" * 9]),
        )

    async def scenario():
        fetcher = make_fetcher(
            handler, RecordingResolver(), max_bytes=16
        )
        try:
            await fetcher.fetch("https://images.example/image.png")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageTooLargeError):
        run(scenario())


def test_requires_supported_mime_and_rejects_content_encoding():
    responses = [
        {"content-type": "text/html"},
        {"content-type": "image/png", "content-encoding": "gzip"},
    ]

    for headers in responses:
        async def scenario():
            fetcher = make_fetcher(
                lambda _request: httpx.Response(200, headers=headers, content=b"x"),
                RecordingResolver(),
            )
            try:
                await fetcher.fetch("https://images.example/image")
            finally:
                await fetcher.aclose()

        with pytest.raises(RemoteImageContentTypeError):
            run(scenario())


def test_retries_current_original_once_after_transient_transport_failure():
    attempts = []
    resolver = RecordingResolver()

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("connection failed", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=png_bytes(),
        )

    async def scenario():
        fetcher = make_fetcher(handler, resolver)
        try:
            return await fetcher.fetch("https://images.example/image.png")
        finally:
            await fetcher.aclose()

    assert run(scenario()).data.startswith(b"\x89PNG")
    assert len(attempts) == 2
    assert resolver.calls == [
        ("images.example", 443),
        ("images.example", 443),
    ]


def test_retries_retryable_http_status_once_but_not_permanent_status():
    attempts = []

    def transient_handler(_request):
        attempts.append(True)
        if len(attempts) == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=png_bytes(),
        )

    async def transient_scenario():
        fetcher = make_fetcher(transient_handler, RecordingResolver())
        try:
            return await fetcher.fetch("https://images.example/image.png")
        finally:
            await fetcher.aclose()

    run(transient_scenario())
    assert len(attempts) == 2

    permanent_attempts = []

    async def permanent_scenario():
        fetcher = make_fetcher(
            lambda _request: (
                permanent_attempts.append(True) or httpx.Response(404)
            ),
            RecordingResolver(),
        )
        try:
            await fetcher.fetch("https://images.example/missing.png")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageHTTPError) as raised:
        run(permanent_scenario())
    assert raised.value.status_code == 404
    assert len(permanent_attempts) == 1


def test_total_attempt_timeout_is_enforced_and_retried_only_once():
    attempts = []

    async def handler(_request):
        attempts.append(True)
        await asyncio.Event().wait()

    async def scenario():
        fetcher = make_fetcher(
            handler,
            RecordingResolver(),
            timeout_seconds=0.005,
        )
        try:
            await fetcher.fetch("https://images.example/slow.png")
        finally:
            await fetcher.aclose()

    with pytest.raises(RemoteImageTimeoutError):
        run(scenario())
    assert len(attempts) == 2


def test_ingestion_passes_only_fetched_bytes_to_media_asset_service():
    class FakeFetcher:
        async def fetch(self, _url, *, scope=None):
            del scope
            from services.remote_image_fetcher import FetchedRemoteImage

            return FetchedRemoteImage(png_bytes(), "image/png")

    media_assets = MagicMock()
    media_assets.upload_discovered_image.return_value = {"id": "asset"}
    service = RemoteImageIngestionService(FakeFetcher(), media_assets)

    asset = run(service.ingest("project", 42, "https://images.example/image.png"))

    assert asset == {"id": "asset"}
    media_assets.upload_discovered_image.assert_called_once()
    kwargs = media_assets.upload_discovered_image.call_args.kwargs
    assert kwargs["project_id"] == "project"
    assert kwargs["user_id"] == 42
    assert kwargs["declared_content_type"] == "image/png"
    assert kwargs["data"].startswith(b"\x89PNG")
