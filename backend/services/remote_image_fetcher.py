"""SSRF-resistant retrieval of untrusted third-party image originals.

Every request is manually redirected and DNS-pinned. Hostname resolution is
validated before connecting, and the selected public IP is placed in the actual
request URL while the original Host header and TLS SNI are retained. This avoids
a validate-then-resolve DNS rebinding gap.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TypeAlias

import httpx

from services.generation_errors import (
    GenerationError,
    ImageRetrievalError,
    ImageValidationError,
)
from services.media_service import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    MediaAssetService,
    MediaValidationError,
)
from services.provider_controls import (
    PROVIDER_CONTROL_CONFIG,
    OperationScope,
    RetryPolicy,
)

MAX_REMOTE_IMAGE_BYTES = MAX_UPLOAD_BYTES
MAX_REMOTE_REDIRECTS = 3
MAX_REMOTE_FETCH_ATTEMPTS = 2
REMOTE_IMAGE_TIMEOUT_SECONDS = 15.0
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_METADATA_HOSTNAMES = {
    "instance-data.ec2.internal",
    "metadata.azure.internal",
    "metadata.google.internal",
    "metadata.goog",
}

Resolver: TypeAlias = Callable[[str, int], Awaitable[Sequence[str]]]
Sleep: TypeAlias = Callable[[float], Awaitable[None]]


class RemoteImageError(ImageRetrievalError):
    """A safe, stable remote retrieval failure."""

    reason = "remote_image_failed"


class RemoteImageURLRejectedError(RemoteImageError):
    reason = "remote_image_url_rejected"


class RemoteImageDestinationBlockedError(RemoteImageError):
    reason = "remote_image_destination_blocked"


class RemoteImageDNSFailureError(RemoteImageError):
    reason = "remote_image_dns_failed"


class RemoteImageRedirectLimitError(RemoteImageError):
    reason = "remote_image_redirect_limit"


class RemoteImageNetworkError(RemoteImageError):
    reason = "remote_image_network_failed"


class RemoteImageTimeoutError(RemoteImageError):
    reason = "remote_image_timeout"


class RemoteImageHTTPError(RemoteImageError):
    reason = "remote_image_http_failed"

    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(details={"http_status": status_code})


class RemoteImageContentTypeError(ImageValidationError):
    reason = "remote_image_content_type_rejected"


class RemoteImageTooLargeError(ImageValidationError):
    reason = "remote_image_too_large"


@dataclass(frozen=True)
class FetchedRemoteImage:
    data: bytes
    content_type: str


@dataclass(frozen=True)
class _Destination:
    original_url: httpx.URL
    pinned_url: httpx.URL
    host_header: str
    sni_hostname: str


async def default_resolver(host: str, port: int) -> Sequence[str]:
    """Resolve A/AAAA records asynchronously using the runtime resolver."""

    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    addresses: list[str] = []
    for _family, _type, _proto, _canonname, sockaddr in records:
        address = sockaddr[0]
        if address not in addresses:
            addresses.append(address)
    return addresses


class RemoteImageFetcher:
    """Fetch one original with bounded redirects, retries, time, and bytes."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = default_resolver,
        retry_policy: RetryPolicy | None = None,
        sleep: Sleep = asyncio.sleep,
        timeout_seconds: float | None = None,
        max_redirects: int = MAX_REMOTE_REDIRECTS,
        max_bytes: int = MAX_REMOTE_IMAGE_BYTES,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("pass either client or transport, not both")
        self.timeout_seconds = (
            PROVIDER_CONTROL_CONFIG.image_fetch_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_redirects < 0 or max_redirects > MAX_REMOTE_REDIRECTS:
            raise ValueError("max_redirects must be between zero and three")
        if max_bytes <= 0 or max_bytes > MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("max_bytes must be between one byte and 10 MiB")
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self._resolver = resolver
        self._sleep = sleep
        self._retry_policy = retry_policy or RetryPolicy(max_attempts=2)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            # DNS-pinned origins are keyed by IP in httpcore. Disabling
            # keepalive prevents a connection with one Host/SNI from being
            # reused for a different hostname that resolves to the same IP.
            limits=httpx.Limits(max_keepalive_connections=0),
        )

    async def __aenter__(self) -> "RemoteImageFetcher":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(
        self,
        original_url: str,
        *,
        scope: OperationScope | None = None,
    ) -> FetchedRemoteImage:
        """Fetch the same original at most twice for transient failures only."""

        # Parse before the retry loop: permanent URL failures are never retried.
        _validated_url(original_url)
        attempts = min(MAX_REMOTE_FETCH_ATTEMPTS, self._retry_policy.max_attempts)
        last_transient: BaseException | None = None

        for attempt in range(1, attempts + 1):
            if scope is not None:
                scope.raise_if_stopped()
            try:
                return await self._run_attempt(original_url, scope)
            except (RemoteImageURLRejectedError, RemoteImageDestinationBlockedError):
                raise
            except (RemoteImageContentTypeError, RemoteImageTooLargeError):
                raise
            except RemoteImageRedirectLimitError:
                raise
            except RemoteImageHTTPError as exc:
                if not RetryPolicy.is_retryable_status(exc.status_code):
                    raise
                last_transient = exc
                retry_after = exc.retry_after
            except RemoteImageDNSFailureError as exc:
                last_transient = exc
                retry_after = None
            except (httpx.TransportError, OSError) as exc:
                last_transient = exc
                retry_after = None
            except TimeoutError as exc:
                last_transient = exc
                retry_after = None

            if attempt >= attempts:
                break
            delay = self._retry_policy.delay_seconds(attempt, retry_after)
            await self._sleep_before_retry(delay, scope)

        if isinstance(last_transient, RemoteImageHTTPError):
            raise last_transient
        if isinstance(last_transient, TimeoutError):
            raise RemoteImageTimeoutError() from last_transient
        if isinstance(last_transient, RemoteImageDNSFailureError):
            raise last_transient
        raise RemoteImageNetworkError() from last_transient

    async def _run_attempt(
        self,
        original_url: str,
        scope: OperationScope | None,
    ) -> FetchedRemoteImage:
        timeout = self.timeout_seconds
        if scope is not None and scope.remaining() is not None:
            timeout = min(timeout, scope.remaining() or 0.0)
        if timeout <= 0:
            assert scope is not None
            scope.raise_if_stopped()

        task = asyncio.create_task(self._fetch_once(original_url))
        cancellation_wait = (
            asyncio.create_task(scope.cancellation.wait()) if scope is not None else None
        )
        waiting = {task}
        if cancellation_wait is not None:
            waiting.add(cancellation_wait)
        try:
            done, _pending = await asyncio.wait(
                waiting,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                result = task.result()
                if scope is not None:
                    scope.raise_if_stopped()
                return result

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if cancellation_wait is not None and cancellation_wait in done:
                assert scope is not None
                scope.raise_if_stopped()
            if scope is not None and scope.remaining() == 0:
                scope.raise_if_stopped()
            raise TimeoutError("remote image attempt timed out")
        except asyncio.CancelledError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise
        finally:
            if cancellation_wait is not None:
                cancellation_wait.cancel()
                try:
                    await cancellation_wait
                except asyncio.CancelledError:
                    pass

    async def _fetch_once(self, original_url: str) -> FetchedRemoteImage:
        current_url = _validated_url(original_url)
        redirect_count = 0

        while True:
            destination = await self._resolve_destination(current_url)
            request = httpx.Request(
                "GET",
                destination.pinned_url,
                headers={
                    "Host": destination.host_header,
                    "Accept": "image/png, image/jpeg, image/webp",
                    "Accept-Encoding": "identity",
                    "User-Agent": "ViratRot-ImageFetcher/1.0",
                },
                extensions={
                    "sni_hostname": destination.sni_hostname,
                    "timeout": {
                        "connect": self.timeout_seconds,
                        "read": self.timeout_seconds,
                        "write": self.timeout_seconds,
                        "pool": self.timeout_seconds,
                    },
                },
            )
            response = await self._client.send(
                request,
                stream=True,
                auth=None,
                follow_redirects=False,
            )
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    if redirect_count >= self.max_redirects:
                        raise RemoteImageRedirectLimitError()
                    location = response.headers.get("location")
                    if not location:
                        raise RemoteImageURLRejectedError()
                    try:
                        current_url = _validated_url(str(current_url.join(location)))
                    except (httpx.InvalidURL, UnicodeError) as exc:
                        raise RemoteImageURLRejectedError() from exc
                    redirect_count += 1
                    continue

                if response.status_code < 200 or response.status_code >= 300:
                    raise RemoteImageHTTPError(
                        response.status_code,
                        response.headers.get("retry-after"),
                    )

                content_encoding = response.headers.get("content-encoding", "identity")
                if content_encoding.strip().lower() not in ("", "identity"):
                    raise RemoteImageContentTypeError(
                        details={"reason": "encoded_response_not_supported"}
                    )
                content_type = response.headers.get("content-type", "")
                normalized_content_type = content_type.split(";", 1)[0].strip().lower()
                if normalized_content_type not in ALLOWED_CONTENT_TYPES:
                    raise RemoteImageContentTypeError(
                        details={"reason": "unsupported_content_type"}
                    )

                content_length = _content_length(response.headers.get("content-length"))
                if content_length is not None and content_length > self.max_bytes:
                    raise RemoteImageTooLargeError()

                if response.is_stream_consumed:
                    # Some transports (notably httpx.MockTransport fixtures,
                    # and any transport that hands back a fully buffered
                    # body) mark the stream consumed before this point. The
                    # buffered bytes remain synchronously available even
                    # though re-iterating the raw stream would raise.
                    buffered = response.content
                    if len(buffered) > self.max_bytes:
                        raise RemoteImageTooLargeError()
                    return FetchedRemoteImage(
                        data=buffered,
                        content_type=normalized_content_type,
                    )

                body = bytearray()
                async for chunk in response.aiter_raw():
                    if len(body) + len(chunk) > self.max_bytes:
                        raise RemoteImageTooLargeError()
                    body.extend(chunk)
                return FetchedRemoteImage(
                    data=bytes(body),
                    content_type=normalized_content_type,
                )
            finally:
                await response.aclose()

    async def _resolve_destination(self, url: httpx.URL) -> _Destination:
        host = url.host
        if not host or "%" in host:
            raise RemoteImageURLRejectedError()
        normalized_host = host.rstrip(".").lower()
        if normalized_host in _METADATA_HOSTNAMES:
            raise RemoteImageDestinationBlockedError()

        try:
            literal = ipaddress.ip_address(normalized_host)
        except ValueError:
            port = url.port or (443 if url.scheme == "https" else 80)
            try:
                resolved = await self._resolver(normalized_host, port)
            except (OSError, UnicodeError) as exc:
                raise RemoteImageDNSFailureError() from exc
            if not resolved:
                raise RemoteImageDNSFailureError()
            addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            for value in resolved:
                try:
                    address = ipaddress.ip_address(value)
                except ValueError as exc:
                    raise RemoteImageDNSFailureError() from exc
                _require_public_address(address)
                if address not in addresses:
                    addresses.append(address)
            selected = addresses[0]
        else:
            _require_public_address(literal)
            selected = literal

        pinned_url = url.copy_with(host=str(selected), userinfo=b"", fragment=None)
        return _Destination(
            original_url=url,
            pinned_url=pinned_url,
            host_header=_host_header(url),
            sni_hostname=normalized_host,
        )

    async def _sleep_before_retry(
        self, delay: float, scope: OperationScope | None
    ) -> None:
        if scope is None:
            await self._sleep(delay)
            return
        scope.raise_if_stopped()
        sleep_task = asyncio.create_task(self._sleep(delay))
        cancellation_wait = asyncio.create_task(scope.cancellation.wait())
        try:
            done, _pending = await asyncio.wait(
                {sleep_task, cancellation_wait},
                timeout=scope.remaining(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if sleep_task in done:
                sleep_task.result()
                scope.raise_if_stopped()
                return
            sleep_task.cancel()
            try:
                await sleep_task
            except asyncio.CancelledError:
                pass
            scope.raise_if_stopped()
        finally:
            cancellation_wait.cancel()
            try:
                await cancellation_wait
            except asyncio.CancelledError:
                pass


class RemoteImageIngestionService:
    """Fetch an original, then persist only MediaAssetService's owned WebP."""

    def __init__(
        self,
        fetcher: RemoteImageFetcher,
        media_assets: MediaAssetService,
    ) -> None:
        self._fetcher = fetcher
        self._media_assets = media_assets

    async def ingest(
        self,
        project_id,
        user_id: int,
        original_url: str,
        *,
        scope: OperationScope | None = None,
    ) -> dict[str, object]:
        fetched = await self._fetcher.fetch(original_url, scope=scope)
        try:
            return self._media_assets.upload_discovered_image(
                project_id=project_id,
                user_id=user_id,
                data=fetched.data,
                declared_content_type=fetched.content_type,
            )
        except MediaValidationError as exc:
            raise ImageValidationError(
                details={"reason": "downloaded_image_failed_validation"}
            ) from exc


def _validated_url(value: str) -> httpx.URL:
    if not isinstance(value, str) or not value:
        raise RemoteImageURLRejectedError()
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, UnicodeError) as exc:
        raise RemoteImageURLRejectedError() from exc
    if url.scheme not in ("http", "https") or not url.host or url.userinfo:
        raise RemoteImageURLRejectedError()
    return url


def _require_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    embedded: list[ipaddress.IPv4Address] = []
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            embedded.append(address.ipv4_mapped)
        if address.sixtofour is not None:
            embedded.append(address.sixtofour)
        if address.teredo is not None:
            embedded.extend(address.teredo)

    blocked = (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
        or not address.is_global
    )
    if blocked:
        raise RemoteImageDestinationBlockedError()
    for embedded_address in embedded:
        if (
            embedded_address.is_loopback
            or embedded_address.is_private
            or embedded_address.is_link_local
            or embedded_address.is_reserved
            or embedded_address.is_unspecified
            or embedded_address.is_multicast
            or not embedded_address.is_global
        ):
            raise RemoteImageDestinationBlockedError()


def _host_header(url: httpx.URL) -> str:
    host = url.host
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{url.port}" if url.port is not None else host


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


__all__ = [
    "FetchedRemoteImage",
    "MAX_REMOTE_FETCH_ATTEMPTS",
    "MAX_REMOTE_IMAGE_BYTES",
    "MAX_REMOTE_REDIRECTS",
    "REMOTE_IMAGE_TIMEOUT_SECONDS",
    "RemoteImageContentTypeError",
    "RemoteImageDNSFailureError",
    "RemoteImageDestinationBlockedError",
    "RemoteImageError",
    "RemoteImageFetcher",
    "RemoteImageHTTPError",
    "RemoteImageIngestionService",
    "RemoteImageNetworkError",
    "RemoteImageRedirectLimitError",
    "RemoteImageTimeoutError",
    "RemoteImageTooLargeError",
    "RemoteImageURLRejectedError",
    "default_resolver",
]
