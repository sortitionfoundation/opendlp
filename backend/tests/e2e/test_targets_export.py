"""ABOUTME: End-to-end smoke tests for the targets export routes
ABOUTME: Real Flask + PostgreSQL round trip for the modal fragment, CSV download, and gsheet write"""

import csv
from io import StringIO

import pytest

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeGSheetExportTarget

DESTINATION = "https://docs.google.com/spreadsheets/d/1234567890abcdef/edit"


def _seed_gender_targets(postgres_session_factory, assembly_id):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=assembly_id,
                name="Gender",
                comment="from the census",
                values=[
                    TargetValue(value="Male", min=14, max=16, percentage_target=50.0, comment="first\nsecond"),
                    TargetValue(value="Female", min=14, max=16, percentage_target=50.0),
                ],
            )
        )
        uow.commit()


class TestTargetsExportSmoke:
    def test_export_modal_fragment(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/targets/export/modal")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/backoffice/project/{existing_assembly.id}/targets/export/run" in body
        assert 'name="file_type"' in body

    def test_export_targets_csv(self, logged_in_admin, existing_assembly, postgres_session_factory):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)

        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/targets/export/run",
            data={"file_type": "csv"},
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        body = response.get_data(as_text=True).lstrip("﻿")
        rows = list(csv.DictReader(StringIO(body)))
        assert [(row["feature"], row["value"], row["percentage"]) for row in rows] == [
            ("Gender", "Male", "50"),
            ("Gender", "Female", "50"),
        ]
        assert rows[0]["comment"] == "first\nsecond"
        assert {row["category_comment"] for row in rows} == {"from the census"}


class TestTargetsGSheetExportSmoke:
    @pytest.fixture(autouse=True)
    def _service_account_configured(self, monkeypatch):
        """The gsheet option is gated on a configured service account."""
        for target in (
            "opendlp.entrypoints.blueprints.targets.get_service_account_email",
            "opendlp.entrypoints.gsheet_export_flow.get_service_account_email",
        ):
            monkeypatch.setattr(target, lambda: "sheets-writer@example.iam.gserviceaccount.com")

    def test_export_writes_the_supplied_spreadsheet_and_saves_config(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)
        captured = []

        def factory(url):
            target = FakeGSheetExportTarget()
            captured.append((url, target))
            return target

        logged_in_admin.application.extensions["gsheet_export_target_factory"] = factory

        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/targets/export/run",
            data={"file_type": "gsheet", "spreadsheet_url": DESTINATION, "worksheet_name": ""},
        )

        assert response.status_code == 302
        assert captured and captured[0][0] == DESTINATION
        (title, table) = captured[0][1].writes[0]
        assert title == "Targets"
        assert table.headers[:2] == ["feature", "value"]

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                existing_assembly.id, GSheetExportKind.TARGETS
            )
            assert config is not None
            assert config.url == DESTINATION
            assert config.worksheet_name == "Targets"
