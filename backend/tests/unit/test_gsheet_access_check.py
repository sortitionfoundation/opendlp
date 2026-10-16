"""ABOUTME: Unit tests for the Google Sheets access check and its short-lived cache
ABOUTME: Uses a fake gspread client and FakeRedis, so no Google or Redis access is needed"""

import uuid
from datetime import UTC, datetime

import gspread
import pytest
import redis
import requests

from opendlp.service_layer import gsheet_access_check
from opendlp.service_layer.gsheet_access_check import (
    GSheetAccessResult,
    GSheetAccessStatus,
    check_gsheet_access,
    fetch_cached_result,
    forget_cached_result,
    store_cached_result,
)
from tests.fakes import (
    GOOGLE_DRIVE_NOT_FOUND,
    GOOGLE_QUOTA_EXCEEDED,
    GOOGLE_SERVER_ERROR,
    FakeGSpreadClient,
    FakeRedis,
    google_api_error,
)

_URL = "https://docs.google.com/spreadsheets/d/abc/edit"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EMAIL = "robot@example.com"
_NOW = datetime(2026, 10, 16, 14, 2, tzinfo=UTC)


def _check(client: FakeGSpreadClient, selection_tabs=("Respondents", "Categories"), replacement_tabs=()):
    return check_gsheet_access(client, _URL, selection_tabs=selection_tabs, replacement_tabs=replacement_tabs, now=_NOW)


class TestCheckGSheetAccessStatus:
    def test_editable_sheet_is_ok_with_title(self) -> None:
        result = _check(FakeGSpreadClient(tabs=["Respondents", "Categories"]))

        assert result.status == GSheetAccessStatus.OK
        assert result.title == "Leeds Assembly"
        assert result.url == _URL
        assert result.checked_at == _NOW
        assert result.error_code == ""

    def test_read_only_sheet_reports_title_and_read_only_error(self) -> None:
        """A Viewer share opens fine, but a selection could not write its output tabs."""
        result = _check(FakeGSpreadClient(tabs=["Respondents", "Categories"], can_edit=False))

        assert result.status == GSheetAccessStatus.READ_ONLY
        assert result.title == "Leeds Assembly"
        assert result.error_code == "spreadsheet_read_only"
        assert result.error_params["service_account_email"] == _EMAIL

    def test_not_shared_names_the_service_account(self) -> None:
        client = FakeGSpreadClient(
            drive_error=google_api_error(GOOGLE_DRIVE_NOT_FOUND),
            open_error=PermissionError(),
        )

        result = _check(client)

        assert result.status == GSheetAccessStatus.NOT_SHARED
        assert result.error_code == "spreadsheet_not_shared"
        assert result.error_params["service_account_email"] == _EMAIL
        assert result.title == ""

    def test_missing_sheet_is_not_found(self) -> None:
        client = FakeGSpreadClient(
            drive_error=google_api_error(GOOGLE_DRIVE_NOT_FOUND),
            open_error=gspread.exceptions.SpreadsheetNotFound(),
        )

        result = _check(client)

        assert result.status == GSheetAccessStatus.NOT_FOUND
        assert result.error_code == "spreadsheet_not_found"

    def test_uploaded_excel_file_is_not_native(self) -> None:
        result = _check(FakeGSpreadClient(title="data.xlsx", mimetype=_XLSX))

        assert result.status == GSheetAccessStatus.NOT_NATIVE
        assert result.error_code == "not_native_gsheet"
        assert result.error_params["file_name"] == "data.xlsx"

    def test_quota_exceeded_is_google_busy(self) -> None:
        result = _check(FakeGSpreadClient(drive_error=google_api_error(GOOGLE_QUOTA_EXCEEDED)))

        assert result.status == GSheetAccessStatus.GOOGLE_BUSY

    def test_server_error_is_unavailable(self) -> None:
        result = _check(FakeGSpreadClient(drive_error=google_api_error(GOOGLE_SERVER_ERROR)))

        assert result.status == GSheetAccessStatus.UNAVAILABLE

    @pytest.mark.parametrize(
        "error",
        [requests.exceptions.ReadTimeout("slow"), requests.exceptions.ConnectionError("unreachable")],
    )
    def test_timeout_or_connection_failure_is_unavailable(self, error: Exception) -> None:
        result = _check(FakeGSpreadClient(drive_error=error))

        assert result.status == GSheetAccessStatus.UNAVAILABLE

    def test_unexpected_exception_propagates(self) -> None:
        """Anything we did not anticipate is a bug, so the route's outer handler must see it."""
        with pytest.raises(ZeroDivisionError):
            _check(FakeGSpreadClient(drive_error=ZeroDivisionError()))


class TestCheckGSheetAccessTabs:
    def test_all_tabs_present_reports_nothing_missing(self) -> None:
        result = _check(
            FakeGSpreadClient(tabs=["Respondents", "Categories", "Remaining"]),
            replacement_tabs=("Remaining",),
        )

        assert result.missing_selection_tabs == ()
        assert result.missing_replacement_tabs == ()
        assert result.tab_suggestions == {}

    def test_missing_selection_and_replacement_tabs_are_reported_separately(self) -> None:
        result = _check(
            FakeGSpreadClient(tabs=["Respondents"]),
            replacement_tabs=("Remaining", "Selected"),
        )

        assert result.missing_selection_tabs == ("Categories",)
        assert result.missing_replacement_tabs == ("Remaining", "Selected")

    def test_empty_tab_name_is_not_looked_for(self) -> None:
        """An empty already-selected tab means replacements do not read one."""
        result = _check(FakeGSpreadClient(tabs=["Respondents", "Categories"]), replacement_tabs=("",))

        assert result.missing_replacement_tabs == ()

    def test_near_miss_ignoring_case_and_surrounding_spaces_is_suggested(self) -> None:
        result = _check(FakeGSpreadClient(tabs=["respondents ", "Categories"]))

        assert result.missing_selection_tabs == ("Respondents",)
        assert result.tab_suggestions == {"Respondents": "respondents "}

    def test_no_suggestion_for_a_different_name(self) -> None:
        result = _check(FakeGSpreadClient(tabs=["People", "Categories"]))

        assert result.tab_suggestions == {}

    def test_tabs_not_checked_when_sheet_cannot_be_opened(self) -> None:
        client = FakeGSpreadClient(
            drive_error=google_api_error(GOOGLE_DRIVE_NOT_FOUND),
            open_error=gspread.exceptions.SpreadsheetNotFound(),
        )

        result = _check(client)

        assert result.missing_selection_tabs == ()

    def test_read_only_sheet_still_checks_tabs(self) -> None:
        result = _check(FakeGSpreadClient(tabs=["Respondents"], can_edit=False))

        assert result.missing_selection_tabs == ("Categories",)


class TestGSheetAccessResultSerialisation:
    def test_round_trips_through_json(self) -> None:
        result = _check(
            FakeGSpreadClient(tabs=["respondents"], can_edit=False),
            replacement_tabs=("Remaining",),
        )

        assert GSheetAccessResult.from_json(result.to_json()) == result


class TestCache:
    def _result(self, status: GSheetAccessStatus = GSheetAccessStatus.OK, url: str = _URL) -> GSheetAccessResult:
        return GSheetAccessResult(status=status, url=url, checked_at=_NOW, title="Leeds Assembly")

    def test_stored_result_is_fetched_for_the_same_url(self) -> None:
        fake_redis = FakeRedis()
        assembly_id = uuid.uuid4()

        store_cached_result(assembly_id, self._result(), redis_client=fake_redis)

        assert fetch_cached_result(assembly_id, _URL, redis_client=fake_redis) == self._result()

    def test_result_for_a_different_url_is_a_miss(self) -> None:
        """Guards against the URL changing without the save route dropping the cache."""
        fake_redis = FakeRedis()
        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, self._result(), redis_client=fake_redis)

        assert fetch_cached_result(assembly_id, "https://docs.google.com/spreadsheets/d/other", fake_redis) is None

    def test_nothing_cached_is_a_miss(self) -> None:
        assert fetch_cached_result(uuid.uuid4(), _URL, redis_client=FakeRedis()) is None

    def test_cache_is_per_assembly(self) -> None:
        fake_redis = FakeRedis()
        store_cached_result(uuid.uuid4(), self._result(), redis_client=fake_redis)

        assert fetch_cached_result(uuid.uuid4(), _URL, redis_client=fake_redis) is None

    @pytest.mark.parametrize("status", [GSheetAccessStatus.GOOGLE_BUSY, GSheetAccessStatus.UNAVAILABLE])
    def test_transient_results_are_not_stored(self, status: GSheetAccessStatus) -> None:
        """They describe Google right now, not the sheet, so the last real answer stays."""
        fake_redis = FakeRedis()
        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, self._result(), redis_client=fake_redis)

        store_cached_result(assembly_id, self._result(status=status), redis_client=fake_redis)

        assert fetch_cached_result(assembly_id, _URL, redis_client=fake_redis) == self._result()

    def test_forget_drops_the_result(self) -> None:
        fake_redis = FakeRedis()
        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, self._result(), redis_client=fake_redis)

        forget_cached_result(assembly_id, redis_client=fake_redis)

        assert fetch_cached_result(assembly_id, _URL, redis_client=fake_redis) is None

    def test_stored_with_a_ttl(self) -> None:
        calls: list[dict] = []

        class _RecordingRedis(FakeRedis):
            def set(self, key, value, nx=False, ex=None):
                calls.append({"key": key, "ex": ex})
                return super().set(key, value, nx=nx, ex=ex)

        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, self._result(), redis_client=_RecordingRedis())

        assert calls == [{"key": f"gsheet_access_check:{assembly_id}", "ex": gsheet_access_check.CACHE_TTL_SECONDS}]
        assert gsheet_access_check.CACHE_TTL_SECONDS == 10 * 60

    def test_redis_failure_is_tolerated(self) -> None:
        """The check still works without Redis; it just is not remembered."""

        class _BrokenRedis:
            def get(self, key):
                raise redis.exceptions.ConnectionError("down")

            def set(self, key, value, nx=False, ex=None):
                raise redis.exceptions.ConnectionError("down")

            def delete(self, key):
                raise redis.exceptions.ConnectionError("down")

        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, self._result(), redis_client=_BrokenRedis())
        forget_cached_result(assembly_id, redis_client=_BrokenRedis())

        assert fetch_cached_result(assembly_id, _URL, redis_client=_BrokenRedis()) is None
