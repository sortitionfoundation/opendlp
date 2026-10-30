# ABOUTME: Component tests for the targets export routes over a FakeUnitOfWork
# ABOUTME: The Export button, the modal, the CSV download, the Google Sheets write, and who may use them

import csv
import re
from io import BytesIO, StringIO

import pytest
from flask.testing import FlaskClient

from opendlp.adapters import database
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GSheetExportKind
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from tests.fakes import FakeGSheetExportTarget, FakeStore, FakeUnitOfWork

SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"

TARGETS_CSV = (
    "feature,value,min,max,percentage,comment,category_comment\n"
    "Gender,Woman,3,7,51,boosted,from the census\n"
    "Gender,Man,3,7,49,,from the census\n"
)


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Target services call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture(autouse=True)
def _service_account_configured(monkeypatch):
    """The gsheet option is gated on a configured service account."""
    for target in (
        "opendlp.entrypoints.blueprints.targets.get_service_account_email",
        "opendlp.entrypoints.gsheet_export_flow.get_service_account_email",
    ):
        monkeypatch.setattr(target, lambda: "sheets-writer@example.iam.gserviceaccount.com")


def _url(assembly_id, suffix=""):
    return f"/backoffice/project/{assembly_id}/targets{suffix}"


def _seed_targets(fake_store: FakeStore, admin_user, assembly_id) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        import_targets_from_csv(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, csv_content=TARGETS_CSV)


def _give_user_a_role(fake_store: FakeStore, assembly_id) -> None:
    """Let the regular user see the assembly, without the right to manage it."""
    with FakeUnitOfWork(store=fake_store) as uow:
        regular = uow.users.get_by_email("user@example.com")
        regular.assembly_roles.append(
            UserAssemblyRole(user_id=regular.id, assembly_id=assembly_id, role=AssemblyRole.CONFIRMATION_CALLER)
        )
        uow.commit()


def _parse(response) -> list[dict[str, str]]:
    body = response.get_data(as_text=True).lstrip("﻿")
    return list(csv.DictReader(StringIO(body)))


def _export_button(html_text):
    return re.search(r"<button[^>]*targets/export/modal[^>]*>", html_text)


class TestExportButton:
    def test_a_manager_is_offered_the_export(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)

        html_text = logged_in_admin.get(_url(existing_assembly.id)).get_data(as_text=True)

        button = _export_button(html_text)
        assert button is not None
        assert 'hx-target="#export-modal-container"' in button.group(0)
        assert 'id="export-modal-container"' in html_text

    def test_the_export_steps_aside_while_editing(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """It exports what is saved, so it goes with "Edit targets" while the form is open."""
        _seed_targets(fake_store, admin_user, existing_assembly.id)

        html_text = logged_in_admin.get(_url(existing_assembly.id)).get_data(as_text=True)

        wrapper = re.search(r'<span x-show="!editingAll">\s*' + _export_button(html_text).group(0), html_text)
        assert wrapper is not None

    def test_nothing_to_export_offers_no_export(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html_text = logged_in_admin.get(_url(existing_assembly.id)).get_data(as_text=True)

        assert _export_button(html_text) is None

    def test_a_viewer_is_not_offered_the_export(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)
        _give_user_a_role(fake_store, existing_assembly.id)

        response = logged_in_user.get(_url(existing_assembly.id))

        assert response.status_code == 200
        assert _export_button(response.get_data(as_text=True)) is None


class TestExportModal:
    def test_offers_csv_and_google_sheets(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.get(_url(existing_assembly.id, "/export/modal"))

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert _url(existing_assembly.id, "/export/run") in body
        assert '<input type="radio" name="file_type" value="csv" x-model="fileType" checked>' in body
        assert '<input type="radio" name="file_type" value="gsheet" x-model="fileType">' in body
        assert 'name="spreadsheet_url"' in body

    def test_has_no_filter_and_no_automatic_export(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        body = logged_in_admin.get(_url(existing_assembly.id, "/export/modal")).get_data(as_text=True)

        assert 'name="status"' not in body
        assert 'name="auto_export"' not in body

    def test_defaults_the_worksheet_to_targets(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        body = logged_in_admin.get(_url(existing_assembly.id, "/export/modal")).get_data(as_text=True)

        assert 'value="Targets"' in body

    def test_prefills_the_saved_targets_sheet_not_another_exports(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assembly_export_gsheets.add(
                AssemblyExportGSheet(
                    assembly_id=existing_assembly.id,
                    export_kind=GSheetExportKind.RESPONDENTS,
                    url="https://docs.google.com/spreadsheets/d/respondentsSheetId/edit",
                    worksheet_name="People",
                )
            )
            uow.assembly_export_gsheets.add(
                AssemblyExportGSheet(
                    assembly_id=existing_assembly.id,
                    export_kind=GSheetExportKind.TARGETS,
                    url=SHEET_URL,
                    worksheet_name="Quotas",
                )
            )
            uow.commit()

        body = logged_in_admin.get(_url(existing_assembly.id, "/export/modal")).get_data(as_text=True)

        assert SHEET_URL in body
        assert 'value="Quotas"' in body
        assert "respondentsSheetId" not in body

    def test_a_viewer_is_refused_the_modal(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _give_user_a_role(fake_store, existing_assembly.id)

        response = logged_in_user.get(_url(existing_assembly.id, "/export/modal"))

        assert response.status_code == 302


class TestRunExport:
    def test_csv_downloads_the_targets(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)

        response = logged_in_admin.post(_url(existing_assembly.id, "/export/run"), data={"file_type": "csv"})

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert 'filename="targets-' in response.headers["Content-Disposition"]
        rows = _parse(response)
        assert [(r["feature"], r["value"], r["min"], r["max"], r["percentage"]) for r in rows] == [
            ("Gender", "Woman", "3", "7", "51"),
            ("Gender", "Man", "3", "7", "49"),
        ]
        assert rows[0]["comment"] == "boosted"
        assert {r["category_comment"] for r in rows} == {"from the census"}

    def test_a_download_uploads_back_through_the_upload_form(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """The point of the format: export, edit, and upload again."""
        _seed_targets(fake_store, admin_user, existing_assembly.id)
        exported = logged_in_admin.post(_url(existing_assembly.id, "/export/run"), data={"file_type": "csv"})
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.target_categories.delete_all_for_assembly(existing_assembly.id)
            uow.commit()

        response = logged_in_admin.post(
            _url(existing_assembly.id, "/upload"),
            data={"csv_file": (BytesIO(exported.get_data()), "targets.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            (category,) = uow.target_categories.get_by_assembly_id(existing_assembly.id)
            assert category.name == "Gender"
            assert category.comment == "from the census"
            assert [(v.value, v.percentage_target, v.comment) for v in category.values] == [
                ("Woman", 51.0, "boosted"),
                ("Man", 49.0, ""),
            ]

    def test_google_sheets_writes_the_sheet_and_saves_it_as_the_targets_sheet(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)
        captured: list = []

        def factory(url: str) -> FakeGSheetExportTarget:
            target = FakeGSheetExportTarget()
            captured.append((url, target))
            return target

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory

        response = logged_in_admin.post(
            _url(existing_assembly.id, "/export/run"),
            data={"file_type": "gsheet", "spreadsheet_url": SHEET_URL, "worksheet_name": ""},
            follow_redirects=True,
        )

        assert "Targets exported to Google Sheets." in response.get_data(as_text=True)
        ((url, target),) = captured
        assert url == SHEET_URL
        ((title, table),) = target.writes
        assert title == "Targets"
        assert table.headers[:4] == ["feature", "value", "min", "max"]
        with FakeUnitOfWork(store=fake_store) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                existing_assembly.id, GSheetExportKind.TARGETS
            )
            assert config is not None
            assert config.url == SHEET_URL
            assert config.auto_export is False

    def test_google_sheets_needs_a_spreadsheet_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)

        response = logged_in_admin.post(
            _url(existing_assembly.id, "/export/run"),
            data={"file_type": "gsheet", "spreadsheet_url": ""},
            follow_redirects=True,
        )

        assert "A spreadsheet URL is required" in response.get_data(as_text=True)

    def test_an_unknown_file_type_is_refused(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.post(_url(existing_assembly.id, "/export/run"), data={"file_type": "xlsx"})

        assert response.status_code == 302
        assert response.headers["Location"].endswith(_url(existing_assembly.id))

    def test_a_viewer_may_not_export(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        _seed_targets(fake_store, admin_user, existing_assembly.id)
        _give_user_a_role(fake_store, existing_assembly.id)

        response = logged_in_user.post(
            _url(existing_assembly.id, "/export/run"), data={"file_type": "csv"}, follow_redirects=True
        )

        body = response.get_data(as_text=True)
        assert "permission to export these targets" in body
        assert "Gender,Woman" not in body
