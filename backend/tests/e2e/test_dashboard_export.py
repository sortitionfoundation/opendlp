"""ABOUTME: End-to-end smoke tests for the dashboard CSV export routes
ABOUTME: Real Flask + PostgreSQL round trip for the modal fragment and the download"""

import csv
from io import StringIO

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


def _seed_gender_targets(postgres_session_factory, assembly_id):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=assembly_id,
                name="Gender",
                values=[
                    TargetValue(value="Male", min=14, max=16, percentage_target=50.0),
                    TargetValue(value="Female", min=14, max=16, percentage_target=50.0),
                ],
            )
        )
        uow.commit()


class TestDashboardExportSmoke:
    def test_export_modal_fragment(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/modal")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run" in body
        assert 'name="file_type"' in body

    def test_export_dashboard_csv(self, logged_in_admin, existing_assembly, postgres_session_factory):
        _seed_gender_targets(postgres_session_factory, existing_assembly.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "csv"},
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        body = response.get_data(as_text=True).lstrip("﻿")
        rows = list(csv.DictReader(StringIO(body)))
        assert {row["Value"] for row in rows} == {"Male", "Female"}
        assert rows[0]["Target"] == "Gender"

    def test_export_rejects_disabled_file_type(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/dashboard/export/run",
            data={"file_type": "xlsx"},
        )

        assert response.status_code == 302
