"""ABOUTME: Contract tests for AssemblyGSheetRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.assembly import AssemblyGSheet
from tests.contract.conftest import ContractBackend

# A valid Google Spreadsheet URL for testing
TEST_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


def _add_gsheet(backend: ContractBackend, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> AssemblyGSheet:
    if assembly_id is None:
        assembly = backend.make_assembly()
        assembly_id = assembly.id
    gsheet = AssemblyGSheet(
        assembly_id=assembly_id,
        assembly_gsheet_id=uuid.uuid4(),
        url=kwargs.pop("url", TEST_GSHEET_URL),
        **kwargs,
    )
    backend.repo.add(gsheet)
    backend.commit()
    return gsheet


class TestAddAndGet:
    def test_add_and_get_by_id(self, assembly_gsheet_backend: ContractBackend):
        assembly = assembly_gsheet_backend.make_assembly()
        gsheet = _add_gsheet(assembly_gsheet_backend, assembly_id=assembly.id)

        retrieved = assembly_gsheet_backend.repo.get(gsheet.assembly_gsheet_id)
        assert retrieved is not None
        assert retrieved.assembly_gsheet_id == gsheet.assembly_gsheet_id
        assert retrieved.assembly_id == assembly.id

    def test_get_nonexistent_returns_none(self, assembly_gsheet_backend: ContractBackend):
        assert assembly_gsheet_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_gsheets(self, assembly_gsheet_backend: ContractBackend):
        g1 = _add_gsheet(assembly_gsheet_backend)
        g2 = _add_gsheet(assembly_gsheet_backend)

        all_gsheets = list(assembly_gsheet_backend.repo.all())
        ids = {g.assembly_gsheet_id for g in all_gsheets}
        assert g1.assembly_gsheet_id in ids
        assert g2.assembly_gsheet_id in ids


class TestGetByAssemblyId:
    def test_finds_by_assembly_id(self, assembly_gsheet_backend: ContractBackend):
        assembly = assembly_gsheet_backend.make_assembly()
        gsheet = _add_gsheet(assembly_gsheet_backend, assembly_id=assembly.id)

        retrieved = assembly_gsheet_backend.repo.get_by_assembly_id(assembly.id)
        assert retrieved is not None
        assert retrieved.assembly_gsheet_id == gsheet.assembly_gsheet_id

    def test_returns_none_for_nonexistent(self, assembly_gsheet_backend: ContractBackend):
        assert assembly_gsheet_backend.repo.get_by_assembly_id(uuid.uuid4()) is None


class TestDelete:
    def test_delete_removes_gsheet(self, assembly_gsheet_backend: ContractBackend):
        gsheet = _add_gsheet(assembly_gsheet_backend)

        assembly_gsheet_backend.repo.delete(gsheet)
        assembly_gsheet_backend.commit()

        assert assembly_gsheet_backend.repo.get(gsheet.assembly_gsheet_id) is None
