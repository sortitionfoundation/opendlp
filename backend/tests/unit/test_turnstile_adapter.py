"""ABOUTME: Unit tests for the Cloudflare Turnstile siteverify adapter
ABOUTME: Pins the fail-closed behaviour: reject on missing inputs, API failure, action or hostname mismatch"""

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from opendlp.adapters.turnstile import verify_turnstile_token


class _FakeResponse:
    """Stand-in for the urlopen context manager, yielding a JSON body."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def __enter__(self) -> io.BytesIO:
        return io.BytesIO(json.dumps(self._payload).encode())

    def __exit__(self, *args: object) -> bool:
        return False


def _verify(**overrides: Any) -> bool:
    kwargs: dict[str, Any] = {
        "secret": "test-secret",  # pragma: allowlist secret
        "token": "test-token",
        "expected_action": "signup",
        "expected_hostnames": {"127.0.0.1", "localhost"},
    }
    kwargs.update(overrides)
    return verify_turnstile_token(**kwargs)


def _patch_siteverify(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> list[urllib.request.Request]:
    """Replace urlopen with a fake returning payload; captures the outgoing request."""
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        seen.append(request)
        return _FakeResponse(payload)

    monkeypatch.setattr("opendlp.adapters.turnstile.urllib.request.urlopen", fake_urlopen)
    return seen


def _forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("siteverify must not be called")

    monkeypatch.setattr("opendlp.adapters.turnstile.urllib.request.urlopen", explode)


class TestVerifyTurnstileToken:
    def test_accepts_valid_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _patch_siteverify(monkeypatch, {"success": True, "action": "signup", "hostname": "127.0.0.1"})
        assert _verify() is True
        body = seen[0].data.decode()
        assert "secret=test-secret" in body  # pragma: allowlist secret
        assert "response=test-token" in body

    def test_sends_remote_ip_when_given(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _patch_siteverify(monkeypatch, {"success": True, "action": "signup", "hostname": "127.0.0.1"})
        assert _verify(remote_ip="203.0.113.9") is True
        assert "remoteip=203.0.113.9" in seen[0].data.decode()

    def test_rejects_empty_token_without_calling_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _forbid_network(monkeypatch)
        assert _verify(token="") is False

    def test_rejects_empty_secret_without_calling_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _forbid_network(monkeypatch)
        assert _verify(secret="") is False

    def test_rejects_empty_hostname_allowlist_without_calling_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _forbid_network(monkeypatch)
        assert _verify(expected_hostnames=set()) is False

    def test_rejects_oversized_token_without_calling_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _forbid_network(monkeypatch)
        assert _verify(token="x" * 2049) is False

    def test_rejects_unsuccessful_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_siteverify(monkeypatch, {"success": False, "error-codes": ["invalid-input-response"]})
        assert _verify() is False

    def test_rejects_action_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_siteverify(monkeypatch, {"success": True, "action": "login", "hostname": "127.0.0.1"})
        assert _verify() is False

    def test_rejects_hostname_not_in_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_siteverify(monkeypatch, {"success": True, "action": "signup", "hostname": "evil.example.com"})
        assert _verify() is False

    def test_fails_closed_on_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_urlerror(*args: object, **kwargs: object) -> None:
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("opendlp.adapters.turnstile.urllib.request.urlopen", raise_urlerror)
        assert _verify() is False

    def test_fails_closed_on_invalid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BadBody:
            def __enter__(self) -> io.BytesIO:
                return io.BytesIO(b"not json")

            def __exit__(self, *args: object) -> bool:
                return False

        monkeypatch.setattr("opendlp.adapters.turnstile.urllib.request.urlopen", lambda *a, **kw: _BadBody())
        assert _verify() is False
