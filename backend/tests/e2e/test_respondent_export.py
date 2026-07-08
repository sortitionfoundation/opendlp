"""ABOUTME: End-to-end smoke test for the respondent CSV export route
ABOUTME: Real Flask + PostgreSQL round trip for the export download"""

import csv
from io import StringIO

from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

_CSV = "external_id,email,consent,eligible\nR001,alice@example.com,true,true\nR002,bob@example.com,true,true\n"


def _parse(response):
    body = response.get_data(as_text=True).lstrip("﻿")
    return list(csv.DictReader(StringIO(body)))


class TestRespondentExportSmoke:
    def test_export_all_respondents_csv(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=_CSV,
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/export")

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        rows = _parse(response)
        assert {row["external_id"] for row in rows} == {"R001", "R002"}
        # Internal columns present in the export.
        assert "selection_status" in rows[0]
