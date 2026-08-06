"""Short-lived, server-signed identities for review image candidates.

The token is an opaque API value: clients may retain and return it, but selection
code must verify it and must never accept a client-provided replacement URL.
The signed claims bind a candidate to the exact review context that produced it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Callable

import httpx

CANDIDATE_TOKEN_TTL_SECONDS = 2 * 60 * 60
CANDIDATE_TOKEN_VERSION = 1
CANDIDATE_SIGNING_KEY_ENV = "IMAGE_CANDIDATE_SIGNING_KEY"
_MAX_TOKEN_BYTES = 32 * 1024
_MAX_ORIGINAL_URL_LENGTH = 16 * 1024


class CandidateTokenError(Exception):
    """Base class for a candidate token that cannot authorize selection."""

    code = "invalid_candidate_token"


class CandidateTokenConfigurationError(CandidateTokenError):
    code = "candidate_token_not_configured"


class InvalidCandidateTokenError(CandidateTokenError):
    code = "invalid_candidate_token"


class ExpiredCandidateTokenError(CandidateTokenError):
    code = "expired_candidate_token"


class CandidateBindingMismatchError(CandidateTokenError):
    code = "candidate_binding_mismatch"


@dataclass(frozen=True)
class CandidateBinding:
    """Server-known fields a review selection must still match."""

    user_id: str
    project_id: str
    composition_id: str
    slot_id: str
    query: str

    def __post_init__(self) -> None:
        for field_name in ("user_id", "project_id", "composition_id", "slot_id"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} must not be blank")
            object.__setattr__(self, field_name, value)

        query = str(self.query).strip()
        if not query:
            raise ValueError("query must not be blank")
        if len(query) > 160:
            raise ValueError("query must be at most 160 characters")
        object.__setattr__(self, "query", query)


@dataclass(frozen=True)
class VerifiedCandidate:
    binding: CandidateBinding
    original_url: str
    issued_at: int
    expires_at: int


class CandidateTokenSigner:
    """Create and verify versioned HMAC-SHA256 review candidate tokens."""

    def __init__(
        self,
        secret: str | bytes,
        *,
        clock: Callable[[], float] = time.time,
        ttl_seconds: int = CANDIDATE_TOKEN_TTL_SECONDS,
    ) -> None:
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(secret_bytes, bytes) or len(secret_bytes) < 32:
            raise CandidateTokenConfigurationError(
                "Candidate signing key must contain at least 32 bytes"
            )
        if ttl_seconds != CANDIDATE_TOKEN_TTL_SECONDS:
            raise ValueError("candidate token TTL is fixed at two hours")
        self._secret = secret_bytes
        self._clock = clock
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> "CandidateTokenSigner":
        values = os.environ if env is None else env
        secret = values.get(CANDIDATE_SIGNING_KEY_ENV)
        if not secret:
            raise CandidateTokenConfigurationError(
                f"{CANDIDATE_SIGNING_KEY_ENV} is required"
            )
        return cls(secret, clock=clock)

    def sign(self, binding: CandidateBinding, original_url: str) -> str:
        original_url = _validated_original_url(original_url)
        issued_at = int(self._clock())
        payload = {
            "v": CANDIDATE_TOKEN_VERSION,
            "iat": issued_at,
            "exp": issued_at + self._ttl_seconds,
            "user_id": binding.user_id,
            "project_id": binding.project_id,
            "composition_id": binding.composition_id,
            "slot_id": binding.slot_id,
            "query": binding.query,
            "original_url": original_url,
        }
        encoded_payload = _base64url_encode(_canonical_json(payload))
        signed_value = f"v{CANDIDATE_TOKEN_VERSION}.{encoded_payload}".encode("ascii")
        signature = hmac.new(self._secret, signed_value, hashlib.sha256).digest()
        return f"{signed_value.decode('ascii')}.{_base64url_encode(signature)}"

    def verify(
        self,
        token: str,
        expected_binding: CandidateBinding,
    ) -> VerifiedCandidate:
        if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_BYTES:
            raise InvalidCandidateTokenError()

        try:
            version, encoded_payload, encoded_signature = token.split(".")
        except ValueError as exc:
            raise InvalidCandidateTokenError() from exc
        if version != f"v{CANDIDATE_TOKEN_VERSION}":
            raise InvalidCandidateTokenError()

        signed_value = f"{version}.{encoded_payload}".encode("ascii")
        try:
            supplied_signature = _base64url_decode(encoded_signature)
        except (ValueError, UnicodeError) as exc:
            raise InvalidCandidateTokenError() from exc
        expected_signature = hmac.new(
            self._secret, signed_value, hashlib.sha256
        ).digest()
        if len(supplied_signature) != hashlib.sha256().digest_size or not hmac.compare_digest(
            supplied_signature, expected_signature
        ):
            raise InvalidCandidateTokenError()

        try:
            payload_bytes = _base64url_decode(encoded_payload)
            payload = json.loads(payload_bytes)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidCandidateTokenError() from exc
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "iat",
            "exp",
            "user_id",
            "project_id",
            "composition_id",
            "slot_id",
            "query",
            "original_url",
        }:
            raise InvalidCandidateTokenError()
        if payload.get("v") != CANDIDATE_TOKEN_VERSION:
            raise InvalidCandidateTokenError()

        issued_at = payload.get("iat")
        expires_at = payload.get("exp")
        if (
            not isinstance(issued_at, int)
            or isinstance(issued_at, bool)
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or expires_at != issued_at + self._ttl_seconds
        ):
            raise InvalidCandidateTokenError()

        now = int(self._clock())
        if issued_at > now:
            raise InvalidCandidateTokenError()
        if now >= expires_at:
            raise ExpiredCandidateTokenError()

        try:
            actual_binding = CandidateBinding(
                user_id=payload["user_id"],
                project_id=payload["project_id"],
                composition_id=payload["composition_id"],
                slot_id=payload["slot_id"],
                query=payload["query"],
            )
        except (TypeError, ValueError) as exc:
            raise InvalidCandidateTokenError() from exc

        if not hmac.compare_digest(
            _canonical_json(_binding_dict(actual_binding)),
            _canonical_json(_binding_dict(expected_binding)),
        ):
            raise CandidateBindingMismatchError()

        original_url = _validated_original_url(payload.get("original_url"))
        return VerifiedCandidate(
            binding=actual_binding,
            original_url=original_url,
            issued_at=issued_at,
            expires_at=expires_at,
        )


def _binding_dict(binding: CandidateBinding) -> dict[str, str]:
    return {
        "user_id": binding.user_id,
        "project_id": binding.project_id,
        "composition_id": binding.composition_id,
        "slot_id": binding.slot_id,
        "query": binding.query,
    }


def _validated_original_url(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_ORIGINAL_URL_LENGTH:
        raise InvalidCandidateTokenError()
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, UnicodeError) as exc:
        raise InvalidCandidateTokenError() from exc
    if url.scheme not in ("http", "https") or not url.host or url.userinfo:
        raise InvalidCandidateTokenError()
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("invalid base64 value")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        (value + padding).encode("ascii"),
        altchars=b"-_",
        validate=True,
    )


__all__ = [
    "CANDIDATE_SIGNING_KEY_ENV",
    "CANDIDATE_TOKEN_TTL_SECONDS",
    "CandidateBinding",
    "CandidateBindingMismatchError",
    "CandidateTokenConfigurationError",
    "CandidateTokenError",
    "CandidateTokenSigner",
    "ExpiredCandidateTokenError",
    "InvalidCandidateTokenError",
    "VerifiedCandidate",
]
