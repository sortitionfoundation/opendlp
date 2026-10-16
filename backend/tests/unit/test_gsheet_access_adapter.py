"""ABOUTME: Unit tests for the gspread client used by the Google Sheets access check
ABOUTME: Checks the client fails fast with the documented timeout, without calling Google"""

import gspread

from opendlp.adapters import gsheet_access


class TestGSheetAccessClientFactory:
    def test_timeout_is_connect_then_read(self) -> None:
        """The timeout is a (connect, read) pair, and its worst case fits the 60s worker timeout."""
        connect, read = gsheet_access.GSHEET_CHECK_TIMEOUT
        max_requests_per_check = 4
        assert (connect + read) * max_requests_per_check < 60

    def test_client_fails_fast_with_check_timeout(self, monkeypatch) -> None:
        """A check runs inside a web request, so the client must not retry and must time out."""
        calls: list[dict] = []
        fake_client = object()

        def fake_make(auth_json_path, request_timeout, http_client):
            calls.append({"path": auth_json_path, "timeout": request_timeout, "http_client": http_client})
            return fake_client

        monkeypatch.setattr(gsheet_access, "make_gsheet_client", fake_make)
        monkeypatch.setattr(gsheet_access.config, "get_google_auth_json_path", lambda: "/creds.json")

        client = gsheet_access.make_check_client()

        assert client is fake_client
        assert calls == [
            {"path": "/creds.json", "timeout": gsheet_access.GSHEET_CHECK_TIMEOUT, "http_client": gspread.HTTPClient}
        ]
