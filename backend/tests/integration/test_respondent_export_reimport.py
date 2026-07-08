"""ABOUTME: Integration test for export -> re-import round-trip safety
ABOUTME: An exported respondent CSV must re-import without crashing on internal columns"""

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget
from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer import respondent_export_service, respondent_service
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow):
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


@pytest.fixture
def test_assembly(uow):
    assembly = Assembly(title="Round Trip Assembly", question="Test?", number_to_select=30)
    with uow:
        uow.assemblies.add(assembly)
        detached = assembly.create_detached_copy()
        uow.commit()
        return detached


class TestExportReimportRoundTrip:
    def test_exported_csv_reimports_without_crashing(self, uow, admin_user, test_assembly):
        # Seed respondents in varied states, then mark one selected so the
        # export carries a non-default selection_status column.
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,email,stay_on_db,Gender\nR1,a@b.com,true,Female\nR2,c@d.com,false,Male\n",
        )
        with uow:
            respondents = uow.respondents.get_by_assembly_id(test_assembly.id)
            selected = respondents[0]
            selected.selection_status = RespondentStatus.SELECTED
            uow.commit()

        export_target = CsvExportTarget()
        respondent_export_service.export_respondents(
            uow, admin_user.id, test_assembly.id, status_filter=None, target=export_target
        )
        exported_csv = export_target.getvalue()
        assert "selection_status" in exported_csv

        # Re-import the exported file into a fresh assembly: it must not crash.
        fresh = Assembly(title="Fresh Assembly", question="Test?", number_to_select=30)
        with uow:
            uow.assemblies.add(fresh)
            fresh_id = fresh.id
            uow.commit()

        respondents_out, errors, _id_col = respondent_service.import_respondents_from_csv(
            uow, admin_user.id, fresh_id, exported_csv.lstrip("﻿")
        )

        assert {r.external_id for r in respondents_out} == {"R1", "R2"}
        # Internal columns are skipped, not stored as attributes.
        for r in respondents_out:
            assert "selection_status" not in r.attributes
            assert "source_type" not in r.attributes
            # Re-imported afresh, status resets to POOL.
            assert r.selection_status == RespondentStatus.POOL
        # stay_on_db round-trips on a fresh create.
        by_id = {r.external_id: r for r in respondents_out}
        assert by_id["R1"].stay_on_db is True
        assert by_id["R2"].stay_on_db is False
        # Skipped internal columns are reported.
        assert any("selection_status" in e for e in errors)
