"""ABOUTME: End-to-end tests for checking Google Sheets access when a configuration is saved
ABOUTME: Real Flask, PostgreSQL and Redis; only the gspread client is a fake"""

import pytest

from opendlp.service_layer.gsheet_access_check import fetch_cached_result
from tests.fakes import FakeGSpreadClient

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1234567890abcdef/edit"


@pytest.fixture(autouse=True)
def _service_account_configured(monkeypatch):
    monkeypatch.setattr(
        "opendlp.entrypoints.blueprints.gsheets.get_service_account_email",
        lambda: "sheets-reader@example.iam.gserviceaccount.com",
    )


@pytest.fixture
def redis_flush(test_redis_client):
    """The cache lives in this worker's Redis database; start and end each test empty."""
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestGSheetAccessCheckEndToEnd:
    def test_save_then_check_then_page_shows_cached_title(self, logged_in_admin, assembly_with_gsheet, redis_flush):
        assembly, _gsheet = assembly_with_gsheet
        logged_in_admin.application.extensions["gsheet_access_client_factory"] = lambda: FakeGSpreadClient(
            title="Leeds Assembly Respondents", tabs=["TestRespondents", "TestCategories"], url=_SHEET_URL
        )

        saved = logged_in_admin.post(
            f"/backoffice/project/{assembly.id}/gsheet/save",
            data={
                "url": _SHEET_URL,
                "team": "uk",
                "select_registrants_tab": "TestRespondents",
                "select_targets_tab": "TestCategories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id_column",
            },
        )
        assert saved.status_code == 302
        assert "check=1" in saved.location
        page = logged_in_admin.get(saved.location).get_data(as_text=True)
        assert 'hx-trigger="load"' in page

        checked = logged_in_admin.post(
            f"/backoffice/project/{assembly.id}/gsheet/check", headers={"HX-Request": "true"}
        )

        assert checked.status_code == 200
        assert "Leeds Assembly Respondents" in checked.get_data(as_text=True)
        assert fetch_cached_result(assembly.id, _SHEET_URL) is not None
        later = logged_in_admin.get(f"/backoffice/project/{assembly.id}/data?source=gsheet").get_data(as_text=True)
        assert "Leeds Assembly Respondents" in later
