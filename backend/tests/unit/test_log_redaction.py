"""ABOUTME: Tests for log_redaction - email/secret redaction helpers and the censor_pii processor.
ABOUTME: Covers redact_emails, is_sensitive_key, censor_pii, and hash_email (TDD for issue 617)."""

import pytest

from opendlp.config import get_secret_key
from opendlp.log_redaction import (
    EMAIL_PLACEHOLDER,
    REDACTED,
    censor_pii,
    hash_email,
    is_sensitive_key,
    redact_emails,
)


class TestGetSecretKey:
    def test_get_secret_key_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_KEY", "abc")
        assert get_secret_key() == "abc"

    def test_get_secret_key_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert get_secret_key() == "dev-secret-key-change-in-production"  # pragma: allowlist secret


class TestRedactEmails:
    def test_redact_emails_replaces_address(self) -> None:
        assert redact_emails("contact a@b.com now") == f"contact {EMAIL_PLACEHOLDER} now"

    def test_redact_emails_handles_multiple_and_plus_addressing(self) -> None:
        out = redact_emails("x@y.com and a.b+tag@sub.example.co.uk")
        assert "@" not in out
        assert out.count(EMAIL_PLACEHOLDER) == 2

    def test_redact_emails_leaves_plain_text_untouched(self) -> None:
        assert redact_emails("no address here") == "no address here"


class TestIsSensitiveKey:
    @pytest.mark.parametrize(
        "key",
        ["password", "secret", "token", "api_key", "Authorization", "client_secret", "csrf_token", "email"],
    )
    def test_is_sensitive_key_true(self, key: str) -> None:
        assert is_sensitive_key(key)

    @pytest.mark.parametrize("key", ["email_hash", "user_id", "request_id", "view", "status"])
    def test_is_sensitive_key_false(self, key: str) -> None:
        assert not is_sensitive_key(key)


class TestCensorPii:
    def test_censor_pii_redacts_email_in_message(self) -> None:
        ed = censor_pii(None, "info", {"event": "sent to a@b.com"})
        assert ed["event"] == f"sent to {EMAIL_PLACEHOLDER}"

    def test_censor_pii_redacts_email_in_string_values(self) -> None:
        ed = censor_pii(None, "info", {"event": "x", "to": "a@b.com"})
        assert ed["to"] == EMAIL_PLACEHOLDER

    def test_censor_pii_redacts_sensitive_keys_by_name(self) -> None:
        ed = censor_pii(None, "info", {"event": "x", "password": "hunter2", "api_key": "k"})
        assert ed["password"] == REDACTED
        assert ed["api_key"] == REDACTED

    def test_censor_pii_preserves_non_sensitive_fields(self) -> None:
        ed = censor_pii(None, "info", {"event": "x", "user_id": "uuid", "email_hash": "email#abcd"})
        assert ed["user_id"] == "uuid"
        assert ed["email_hash"] == "email#abcd"

    def test_censor_pii_handles_non_string_values(self) -> None:
        ed = censor_pii(None, "info", {"event": "x", "count": 3, "ok": True})
        assert ed["count"] == 3
        assert ed["ok"] is True


class TestHashEmail:
    def test_hash_email_is_stable_and_case_insensitive(self) -> None:
        assert hash_email("A@B.com", secret="k") == hash_email("a@b.com ", secret="k")

    def test_hash_email_changes_with_secret(self) -> None:
        assert hash_email("a@b.com", secret="k1") != hash_email("a@b.com", secret="k2")

    def test_hash_email_does_not_contain_plaintext(self) -> None:
        out = hash_email("alice@example.com", secret="k")
        assert "alice" not in out
        assert "@" not in out
        assert out.startswith("email#")
