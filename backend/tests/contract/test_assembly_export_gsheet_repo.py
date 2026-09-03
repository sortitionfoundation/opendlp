"""ABOUTME: Contract tests for AssemblyExportGSheetRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.value_objects import GSheetExportKind

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend

TEST_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
OTHER_GSHEET_URL = "https://docs.google.com/spreadsheets/d/2CyjNWt1YSB6oGNeLwCeCakhnVVrqumct85PhWF3vqnt/edit"


def _add(backend: ContractBackend, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> AssemblyExportGSheet:
    if assembly_id is None:
        assembly = backend.make_assembly()
        assembly_id = assembly.id
    config = AssemblyExportGSheet(
        assembly_id=assembly_id,
        assembly_export_gsheet_id=uuid.uuid4(),
        url=kwargs.pop("url", TEST_GSHEET_URL),
        **kwargs,
    )
    backend.repo.add(config)
    backend.commit()
    return config


class TestAddAndGet:
    def test_add_and_get_by_id(self, assembly_export_gsheet_backend: ContractBackend):
        assembly = assembly_export_gsheet_backend.make_assembly()
        config = _add(assembly_export_gsheet_backend, assembly_id=assembly.id, worksheet_name="Export")

        retrieved = assembly_export_gsheet_backend.repo.get(config.assembly_export_gsheet_id)
        assert retrieved is not None
        assert retrieved.assembly_export_gsheet_id == config.assembly_export_gsheet_id
        assert retrieved.assembly_id == assembly.id
        assert retrieved.worksheet_name == "Export"

    def test_get_nonexistent_returns_none(self, assembly_export_gsheet_backend: ContractBackend):
        assert assembly_export_gsheet_backend.repo.get(uuid.uuid4()) is None

    def test_result_fields_round_trip(self, assembly_export_gsheet_backend: ContractBackend):
        assembly = assembly_export_gsheet_backend.make_assembly()
        config = _add(
            assembly_export_gsheet_backend,
            assembly_id=assembly.id,
            spreadsheet_title="Assembly Data",
            worksheet_url="https://docs.google.com/spreadsheets/d/abc#gid=1",
        )

        retrieved = assembly_export_gsheet_backend.repo.get(config.assembly_export_gsheet_id)
        assert retrieved is not None
        assert retrieved.spreadsheet_title == "Assembly Data"
        assert retrieved.worksheet_url == "https://docs.google.com/spreadsheets/d/abc#gid=1"

    def test_all_returns_added(self, assembly_export_gsheet_backend: ContractBackend):
        c1 = _add(assembly_export_gsheet_backend)
        c2 = _add(assembly_export_gsheet_backend)

        ids = {c.assembly_export_gsheet_id for c in assembly_export_gsheet_backend.repo.all()}
        assert c1.assembly_export_gsheet_id in ids
        assert c2.assembly_export_gsheet_id in ids


class TestGetByAssemblyAndKind:
    def test_finds_the_row_for_that_kind(self, assembly_export_gsheet_backend: ContractBackend):
        assembly = assembly_export_gsheet_backend.make_assembly()
        config = _add(assembly_export_gsheet_backend, assembly_id=assembly.id)

        retrieved = assembly_export_gsheet_backend.repo.get_by_assembly_and_kind(
            assembly.id, GSheetExportKind.RESPONDENTS
        )
        assert retrieved is not None
        assert retrieved.assembly_export_gsheet_id == config.assembly_export_gsheet_id

    def test_returns_none_for_a_kind_with_no_row(self, assembly_export_gsheet_backend: ContractBackend):
        assembly = assembly_export_gsheet_backend.make_assembly()
        _add(assembly_export_gsheet_backend, assembly_id=assembly.id)

        assert (
            assembly_export_gsheet_backend.repo.get_by_assembly_and_kind(assembly.id, GSheetExportKind.DASHBOARD)
            is None
        )

    def test_returns_none_for_nonexistent(self, assembly_export_gsheet_backend: ContractBackend):
        assert (
            assembly_export_gsheet_backend.repo.get_by_assembly_and_kind(uuid.uuid4(), GSheetExportKind.RESPONDENTS)
            is None
        )

    def test_two_kinds_coexist_on_one_assembly(self, assembly_export_gsheet_backend: ContractBackend):
        """Each kind owns its own spreadsheet, not just its own worksheet."""
        assembly = assembly_export_gsheet_backend.make_assembly()
        respondents = _add(
            assembly_export_gsheet_backend,
            assembly_id=assembly.id,
            export_kind=GSheetExportKind.RESPONDENTS,
            url=TEST_GSHEET_URL,
        )
        dashboard = _add(
            assembly_export_gsheet_backend,
            assembly_id=assembly.id,
            export_kind=GSheetExportKind.DASHBOARD,
            url=OTHER_GSHEET_URL,
        )

        by_kind = {
            kind: assembly_export_gsheet_backend.repo.get_by_assembly_and_kind(assembly.id, kind)
            for kind in (GSheetExportKind.RESPONDENTS, GSheetExportKind.DASHBOARD)
        }
        assert by_kind[GSheetExportKind.RESPONDENTS].assembly_export_gsheet_id == (
            respondents.assembly_export_gsheet_id
        )
        assert by_kind[GSheetExportKind.DASHBOARD].assembly_export_gsheet_id == dashboard.assembly_export_gsheet_id
        assert by_kind[GSheetExportKind.RESPONDENTS].url != by_kind[GSheetExportKind.DASHBOARD].url

    def test_each_kind_gets_its_own_default_worksheet_name(self, assembly_export_gsheet_backend: ContractBackend):
        assembly = assembly_export_gsheet_backend.make_assembly()
        _add(assembly_export_gsheet_backend, assembly_id=assembly.id, export_kind=GSheetExportKind.DASHBOARD)

        saved = assembly_export_gsheet_backend.repo.get_by_assembly_and_kind(assembly.id, GSheetExportKind.DASHBOARD)
        assert saved is not None
        assert saved.worksheet_name == "Results"


class TestDelete:
    def test_delete_removes_config(self, assembly_export_gsheet_backend: ContractBackend):
        config = _add(assembly_export_gsheet_backend)

        assembly_export_gsheet_backend.repo.delete(config)
        assembly_export_gsheet_backend.commit()

        assert assembly_export_gsheet_backend.repo.get(config.assembly_export_gsheet_id) is None
