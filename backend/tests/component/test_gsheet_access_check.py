"""ABOUTME: Component tests for the Google Sheets access check panel on the Assembly Data page
ABOUTME: Drives the real routes over a FakeUnitOfWork, with a fake gspread client and an in-memory cache"""

from datetime import UTC, datetime, timedelta

import gspread
import pytest
from flask.testing import FlaskClient

from opendlp.adapters import database
from opendlp.domain.value_objects import AssemblyRole
from opendlp.entrypoints.flask_app import default_gsheet_access_client_factory
from opendlp.service_layer import gsheet_access_check
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from opendlp.service_layer.gsheet_access_check import GSheetAccessResult, GSheetAccessStatus
from opendlp.service_layer.user_service import assign_assembly_role
from tests.fakes import (
    GOOGLE_DRIVE_NOT_FOUND,
    GOOGLE_QUOTA_EXCEEDED,
    FakeGSpreadClient,
    FakeRedis,
    FakeUnitOfWork,
    google_api_error,
)

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1234567890abcdef/edit"
_SERVICE_ACCOUNT = "sheets-reader@example.iam.gserviceaccount.com"
_HTMX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """GSheet/settings writes call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def cache(_in_memory_gsheet_access_cache: FakeRedis) -> FakeRedis:
    return _in_memory_gsheet_access_cache


@pytest.fixture
def service_account(monkeypatch) -> None:
    monkeypatch.setattr("opendlp.entrypoints.blueprints.gsheets.get_service_account_email", lambda: _SERVICE_ACCOUNT)


@pytest.fixture
def google(monkeypatch, app):
    """Make the check talk to a fake gspread client; returns a setter for what Google says."""
    clients: list[FakeGSpreadClient] = []

    def use(client: FakeGSpreadClient) -> FakeGSpreadClient:
        clients.append(client)
        return client

    monkeypatch.setitem(app.extensions, "gsheet_access_client_factory", lambda: clients[-1])
    return use


@pytest.fixture
def assembly_with_gsheet(fake_store, admin_user):
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with GSheet",
            created_by_user_id=admin_user.id,
            question="What should we configure?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        detached_assembly = assembly.create_detached_copy()

    with FakeUnitOfWork(store=fake_store) as uow:
        add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url=_SHEET_URL,
            team="uk",
            select_registrants_tab="Respondents",
            select_targets_tab="Categories",
            replace_registrants_tab="Remaining",
            replace_targets_tab="Replacement Categories",
            already_selected_tab="Selected",
        )
    return detached_assembly


def _check_url(assembly_id) -> str:
    return f"/backoffice/assembly/{assembly_id}/gsheet/check"


def _data_url(assembly_id) -> str:
    return f"/backoffice/assembly/{assembly_id}/data?source=gsheet"


_ALL_TABS = ["Respondents", "Categories", "Remaining", "Replacement Categories", "Selected"]


@pytest.mark.usefixtures("cache", "service_account")
class TestCheckRoute:
    def test_ok_shows_title_and_check_again(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(FakeGSpreadClient(title="Leeds Assembly Respondents", tabs=_ALL_TABS))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Leeds Assembly Respondents" in body
        assert "Check again" in body
        assert "missing" not in body.lower()

    def test_result_is_cached_for_page_views(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet, google, cache: FakeRedis
    ):
        google(FakeGSpreadClient(title="Leeds Assembly Respondents", tabs=_ALL_TABS))

        logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        cached = gsheet_access_check.fetch_cached_result(assembly_with_gsheet.id, _SHEET_URL, redis_client=cache)
        assert cached is not None
        assert cached.status == GSheetAccessStatus.OK

    def test_check_never_reads_the_cache(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet, google, cache: FakeRedis
    ):
        """After sharing the sheet in Google, Check again must give a new answer."""
        stale = GSheetAccessResult(status=GSheetAccessStatus.NOT_SHARED, url=_SHEET_URL, checked_at=datetime.now(UTC))
        gsheet_access_check.store_cached_result(assembly_with_gsheet.id, stale, redis_client=cache)
        client = google(FakeGSpreadClient(title="Now Shared", tabs=_ALL_TABS))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert client.http_client.requests_made == 1
        assert "Now Shared" in response.get_data(as_text=True)

    def test_not_shared_names_the_service_account(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(
            FakeGSpreadClient(
                drive_error=google_api_error(GOOGLE_DRIVE_NOT_FOUND),
                open_error=PermissionError(),
                service_account_email=_SERVICE_ACCOUNT,
            )
        )

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        body = response.get_data(as_text=True)
        assert "not shared" in body
        assert _SERVICE_ACCOUNT in body

    def test_not_found(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(
            FakeGSpreadClient(
                drive_error=google_api_error(GOOGLE_DRIVE_NOT_FOUND),
                open_error=gspread.exceptions.SpreadsheetNotFound(),
            )
        )

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert "not found" in response.get_data(as_text=True)

    def test_read_only_asks_for_edit_access(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(FakeGSpreadClient(title="Viewer Share", tabs=_ALL_TABS, can_edit=False))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        body = response.get_data(as_text=True)
        assert "Viewer Share" in body
        assert "read-only" in body

    def test_not_native_explains_how_to_convert(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(
            FakeGSpreadClient(
                title="data.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        )

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert "Save as Google Sheets" in response.get_data(as_text=True)

    def test_google_busy(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(FakeGSpreadClient(drive_error=google_api_error(GOOGLE_QUOTA_EXCEEDED)))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert "Google is busy" in response.get_data(as_text=True)

    def test_unavailable(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(FakeGSpreadClient(drive_error=TimeoutError("slow")))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert "Could not check the spreadsheet" in response.get_data(as_text=True)

    def test_missing_tabs_are_listed_with_near_miss(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        google(FakeGSpreadClient(tabs=["respondents ", "Selected"]))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        body = response.get_data(as_text=True)
        assert "Categories" in body
        assert "Replacement Categories" in body
        assert "respondents " in body

    def test_title_is_escaped(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        """The title is text anyone with edit access to the sheet can set."""
        google(FakeGSpreadClient(title="<script>alert(1)</script>", tabs=_ALL_TABS))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        body = response.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body

    def test_without_htmx_redirects_to_the_data_page(self, logged_in_admin: FlaskClient, assembly_with_gsheet, google):
        """Without JavaScript the form still posts; the cached result then shows on the page."""
        google(FakeGSpreadClient(title="Leeds Assembly Respondents", tabs=_ALL_TABS))

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id))

        assert response.status_code == 302
        assert f"/assembly/{assembly_with_gsheet.id}/data" in response.location
        page = logged_in_admin.get(response.location).get_data(as_text=True)
        assert "Leeds Assembly Respondents" in page


@pytest.mark.usefixtures("cache")
class TestCheckRouteRefusals:
    def test_regular_user_is_refused(self, logged_in_user: FlaskClient, assembly_with_gsheet, google):
        client = google(FakeGSpreadClient())

        response = logged_in_user.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert response.status_code == 403
        assert client.http_client.requests_made == 0

    def test_no_service_account_does_not_call_google(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet, google, monkeypatch
    ):
        monkeypatch.setattr("opendlp.entrypoints.blueprints.gsheets.get_service_account_email", lambda: "")
        client = google(FakeGSpreadClient())

        response = logged_in_admin.post(_check_url(assembly_with_gsheet.id), headers=_HTMX)

        assert response.status_code == 200
        assert "no Google service account is configured" in response.get_data(as_text=True)
        assert client.http_client.requests_made == 0

    @pytest.mark.usefixtures("service_account")
    def test_no_gsheet_configuration_is_not_found(self, logged_in_admin: FlaskClient, existing_assembly, google):
        client = google(FakeGSpreadClient())

        response = logged_in_admin.post(_check_url(existing_assembly.id), headers=_HTMX)

        assert response.status_code == 404
        assert client.http_client.requests_made == 0


@pytest.mark.usefixtures("cache", "service_account")
class TestDataPagePanel:
    def test_nothing_cached_offers_check_access_without_calling_google(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet, google
    ):
        client = google(FakeGSpreadClient())

        body = logged_in_admin.get(_data_url(assembly_with_gsheet.id)).get_data(as_text=True)

        assert "Check access" in body
        assert 'hx-trigger="load' not in body
        assert client.http_client.requests_made == 0

    def test_cached_result_is_shown(self, logged_in_admin: FlaskClient, assembly_with_gsheet, cache: FakeRedis):
        result = GSheetAccessResult(
            status=GSheetAccessStatus.OK, url=_SHEET_URL, checked_at=datetime.now(UTC), title="Cached Title"
        )
        gsheet_access_check.store_cached_result(assembly_with_gsheet.id, result, redis_client=cache)

        body = logged_in_admin.get(_data_url(assembly_with_gsheet.id)).get_data(as_text=True)

        assert "Cached Title" in body
        assert "Check again" in body

    def test_check_param_fires_the_check_on_load(self, logged_in_admin: FlaskClient, assembly_with_gsheet):
        body = logged_in_admin.get(_data_url(assembly_with_gsheet.id) + "&check=1").get_data(as_text=True)

        assert 'hx-trigger="load' in body
        assert "Checking access to the spreadsheet" in body
        assert 'aria-live="polite"' in body

    def test_panel_not_shown_in_edit_mode(self, logged_in_admin: FlaskClient, assembly_with_gsheet):
        body = logged_in_admin.get(_data_url(assembly_with_gsheet.id) + "&mode=edit").get_data(as_text=True)

        assert "gsheet-access-status" not in body

    def test_read_only_viewer_sees_cached_result_but_no_button(
        self, logged_in_user: FlaskClient, assembly_with_gsheet, fake_store, regular_user, cache
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, assembly_with_gsheet.id, AssemblyRole.READ_ONLY)
        result = GSheetAccessResult(
            status=GSheetAccessStatus.OK, url=_SHEET_URL, checked_at=datetime.now(UTC), title="Cached Title"
        )
        gsheet_access_check.store_cached_result(assembly_with_gsheet.id, result, redis_client=cache)

        body = logged_in_user.get(_data_url(assembly_with_gsheet.id)).get_data(as_text=True)

        assert "Cached Title" in body
        assert "Check again" not in body
        assert "Check access" not in body


@pytest.mark.usefixtures("service_account")
class TestSaveTriggersCheck:
    def test_save_redirects_with_check_and_forgets_the_cached_result(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet, cache: FakeRedis
    ):
        old = GSheetAccessResult(status=GSheetAccessStatus.OK, url=_SHEET_URL, checked_at=datetime.now(UTC))
        gsheet_access_check.store_cached_result(assembly_with_gsheet.id, old, redis_client=cache)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_gsheet.id}/gsheet/save",
            data={
                "url": _SHEET_URL,
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "nationbuilder_id",
            },
        )

        assert response.status_code == 302
        assert "check=1" in response.location
        assert gsheet_access_check.fetch_cached_result(assembly_with_gsheet.id, _SHEET_URL, cache) is None


def test_app_registers_the_real_client_factory(app):
    assert app.extensions["gsheet_access_client_factory"] is default_gsheet_access_client_factory
