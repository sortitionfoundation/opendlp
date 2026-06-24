"""ABOUTME: Unit tests for registration form timing token helpers
ABOUTME: Verifies generation and validation of signed timestamps used to detect bot submissions"""

import pytest
import time_machine
from itsdangerous import BadSignature, SignatureExpired

from opendlp.entrypoints.blueprints.registration import (
    _generate_timing_token,
    _validate_timing_token,
)

SECRET = "test-secret-key-for-timing"  # pragma: allowlist secret


def test_generate_timing_token_returns_string() -> None:
    token = _generate_timing_token(SECRET)
    assert isinstance(token, str)
    assert len(token) > 0


def test_validate_accepts_valid_token_after_min_age() -> None:
    token = _generate_timing_token(SECRET)
    _validate_timing_token(token, SECRET, min_fill_seconds=0, max_age_seconds=86400)


def test_validate_raises_value_error_when_submitted_too_fast() -> None:
    token = _generate_timing_token(SECRET)
    with pytest.raises(ValueError, match="too fast"):
        _validate_timing_token(token, SECRET, min_fill_seconds=9999, max_age_seconds=86400)


def test_validate_raises_signature_expired_when_stale() -> None:
    with time_machine.travel(0):
        token = _generate_timing_token(SECRET)
    with time_machine.travel(1000), pytest.raises(SignatureExpired):
        _validate_timing_token(token, SECRET, min_fill_seconds=0, max_age_seconds=500)


def test_validate_raises_bad_signature_when_tampered() -> None:
    token = _generate_timing_token(SECRET)
    tampered = token[:-4] + "XXXX"
    with pytest.raises(BadSignature):
        _validate_timing_token(tampered, SECRET, min_fill_seconds=0, max_age_seconds=86400)


def test_validate_raises_bad_signature_with_wrong_secret() -> None:
    token = _generate_timing_token(SECRET)
    with pytest.raises(BadSignature):
        _validate_timing_token(token, "wrong-secret", min_fill_seconds=0, max_age_seconds=86400)
