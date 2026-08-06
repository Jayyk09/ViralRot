"""Deterministic tests for context-bound review candidate tokens."""

import base64
import json

import pytest

from services.candidate_token_service import (
    CANDIDATE_TOKEN_TTL_SECONDS,
    CandidateBinding,
    CandidateBindingMismatchError,
    CandidateTokenConfigurationError,
    CandidateTokenSigner,
    ExpiredCandidateTokenError,
    InvalidCandidateTokenError,
)

SECRET = b"candidate-signing-secret-that-is-long-enough"
NOW = 1_800_000_000


def binding(**changes):
    values = {
        "user_id": "42",
        "project_id": "project-1",
        "composition_id": "composition-1",
        "slot_id": "slot-3",
        "query": "Saturn V launch",
    }
    values.update(changes)
    return CandidateBinding(**values)


def test_token_round_trip_is_bound_for_exactly_two_hours():
    signer = CandidateTokenSigner(SECRET, clock=lambda: NOW)
    token = signer.sign(binding(), "https://images.example/launch.jpg?size=original")

    verified = signer.verify(token, binding())

    assert verified.original_url == "https://images.example/launch.jpg?size=original"
    assert verified.issued_at == NOW
    assert verified.expires_at == NOW + CANDIDATE_TOKEN_TTL_SECONDS
    assert "images.example" not in token


def test_token_is_invalid_at_two_hour_expiry_boundary():
    token = CandidateTokenSigner(SECRET, clock=lambda: NOW).sign(
        binding(), "https://images.example/launch.jpg"
    )
    verifier = CandidateTokenSigner(
        SECRET, clock=lambda: NOW + CANDIDATE_TOKEN_TTL_SECONDS
    )

    with pytest.raises(ExpiredCandidateTokenError):
        verifier.verify(token, binding())


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": "43"},
        {"project_id": "project-2"},
        {"composition_id": "composition-2"},
        {"slot_id": "slot-4"},
        {"query": "Apollo 11 launch"},
    ],
)
def test_token_rejects_every_mismatched_server_context_field(change):
    signer = CandidateTokenSigner(SECRET, clock=lambda: NOW)
    token = signer.sign(binding(), "https://images.example/launch.jpg")

    with pytest.raises(CandidateBindingMismatchError):
        signer.verify(token, binding(**change))


def test_token_rejects_payload_or_signature_tampering():
    signer = CandidateTokenSigner(SECRET, clock=lambda: NOW)
    token = signer.sign(binding(), "https://images.example/launch.jpg")
    version, payload, signature = token.split(".")
    decoded = json.loads(_decode(payload))
    decoded["original_url"] = "https://attacker.example/replacement.jpg"
    tampered_payload = _encode(
        json.dumps(decoded, separators=(",", ":"), sort_keys=True).encode()
    )

    with pytest.raises(InvalidCandidateTokenError):
        signer.verify(f"{version}.{tampered_payload}.{signature}", binding())

    changed_signature = signature[:-1] + ("A" if signature[-1] != "A" else "B")
    with pytest.raises(InvalidCandidateTokenError):
        signer.verify(f"{version}.{payload}.{changed_signature}", binding())


def test_signer_rejects_short_secret_and_unfetchable_original():
    with pytest.raises(CandidateTokenConfigurationError):
        CandidateTokenSigner(b"too-short")

    signer = CandidateTokenSigner(SECRET, clock=lambda: NOW)
    with pytest.raises(InvalidCandidateTokenError):
        signer.sign(binding(), "file:///etc/passwd")
    with pytest.raises(InvalidCandidateTokenError):
        signer.sign(binding(), "https://user:pass@example.com/image.jpg")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
