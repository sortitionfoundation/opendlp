# ABOUTME: Component tests for respondent CSV export over a FakeUnitOfWork
# ABOUTME: Drives the real export route + service against a seeded fake store, no PostgreSQL

import csv
from io import StringIO

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from tests.fakes import FakeStore, FakeUnitOfWork


def _add_respondent(fake_store: FakeStore, assembly_id, external_id: str, status: RespondentStatus) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=external_id, selection_status=status))
        uow.commit()


def _export(client: FlaskClient, assembly_id, status: str = ""):
    return client.get(f"/backoffice/assembly/{assembly_id}/respondents/export?status={status}")


def _parse(response) -> list[dict[str, str]]:
    body = response.get_data(as_text=True).lstrip("﻿")
    return list(csv.DictReader(StringIO(body)))


class TestRespondentExportCsv:
    def test_exports_all_as_csv_download(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)

        response = _export(logged_in_admin, existing_assembly.id)

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-pool", "R-selected"}

    def test_single_status_filter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)

        response = _export(logged_in_admin, existing_assembly.id, status="SELECTED")

        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-selected"}

    def test_selected_or_confirmed_filter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-pool", RespondentStatus.POOL)
        _add_respondent(fake_store, existing_assembly.id, "R-selected", RespondentStatus.SELECTED)
        _add_respondent(fake_store, existing_assembly.id, "R-confirmed", RespondentStatus.CONFIRMED)

        response = _export(logged_in_admin, existing_assembly.id, status="selected_or_confirmed")

        ids = {row["external_id"] for row in _parse(response)}
        assert ids == {"R-selected", "R-confirmed"}

    def test_deleted_never_exported(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _add_respondent(fake_store, existing_assembly.id, "R-deleted", RespondentStatus.DELETED)

        response = _export(logged_in_admin, existing_assembly.id)

        assert _parse(response) == []

    def test_invalid_status_redirects_with_flash(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _export(logged_in_admin, existing_assembly.id, status="not-a-status")
        assert response.status_code == 302

    def test_permission_denied_for_regular_user(self, logged_in_user: FlaskClient, existing_assembly: Assembly) -> None:
        response = _export(logged_in_user, existing_assembly.id)
        assert response.status_code == 302
