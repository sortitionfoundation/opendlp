"""ABOUTME: Contract tests for AssemblyRespondentGSheetRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.assembly_respondent_gsheet import AssemblyRespondentGSheet
from tests.contract.conftest import ContractBackend

TEST_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


def _add(backend: ContractBackend, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> AssemblyRespondentGSheet:
    if assembly_id is None:
        assembly = backend.make_assembly()
        assembly_id = assembly.id
    config = AssemblyRespondentGSheet(
        assembly_id=assembly_id,
        assembly_respondent_gsheet_id=uuid.uuid4(),
        url=kwargs.pop("url", TEST_GSHEET_URL),
        **kwargs,
    )
    backend.repo.add(config)
    backend.commit()
    return config


class TestAddAndGet:
    def test_add_and_get_by_id(self, assembly_respondent_gsheet_backend: ContractBackend):
        assembly = assembly_respondent_gsheet_backend.make_assembly()
        config = _add(assembly_respondent_gsheet_backend, assembly_id=assembly.id, worksheet_name="Export")

        retrieved = assembly_respondent_gsheet_backend.repo.get(config.assembly_respondent_gsheet_id)
        assert retrieved is not None
        assert retrieved.assembly_respondent_gsheet_id == config.assembly_respondent_gsheet_id
        assert retrieved.assembly_id == assembly.id
        assert retrieved.worksheet_name == "Export"

    def test_get_nonexistent_returns_none(self, assembly_respondent_gsheet_backend: ContractBackend):
        assert assembly_respondent_gsheet_backend.repo.get(uuid.uuid4()) is None

    def test_result_fields_round_trip(self, assembly_respondent_gsheet_backend: ContractBackend):
        assembly = assembly_respondent_gsheet_backend.make_assembly()
        config = _add(
            assembly_respondent_gsheet_backend,
            assembly_id=assembly.id,
            spreadsheet_title="Assembly Data",
            worksheet_url="https://docs.google.com/spreadsheets/d/abc#gid=1",
        )

        retrieved = assembly_respondent_gsheet_backend.repo.get(config.assembly_respondent_gsheet_id)
        assert retrieved is not None
        assert retrieved.spreadsheet_title == "Assembly Data"
        assert retrieved.worksheet_url == "https://docs.google.com/spreadsheets/d/abc#gid=1"

    def test_all_returns_added(self, assembly_respondent_gsheet_backend: ContractBackend):
        c1 = _add(assembly_respondent_gsheet_backend)
        c2 = _add(assembly_respondent_gsheet_backend)

        ids = {c.assembly_respondent_gsheet_id for c in assembly_respondent_gsheet_backend.repo.all()}
        assert c1.assembly_respondent_gsheet_id in ids
        assert c2.assembly_respondent_gsheet_id in ids


class TestGetByAssemblyId:
    def test_finds_by_assembly_id(self, assembly_respondent_gsheet_backend: ContractBackend):
        assembly = assembly_respondent_gsheet_backend.make_assembly()
        config = _add(assembly_respondent_gsheet_backend, assembly_id=assembly.id)

        retrieved = assembly_respondent_gsheet_backend.repo.get_by_assembly_id(assembly.id)
        assert retrieved is not None
        assert retrieved.assembly_respondent_gsheet_id == config.assembly_respondent_gsheet_id

    def test_returns_none_for_nonexistent(self, assembly_respondent_gsheet_backend: ContractBackend):
        assert assembly_respondent_gsheet_backend.repo.get_by_assembly_id(uuid.uuid4()) is None


class TestDelete:
    def test_delete_removes_config(self, assembly_respondent_gsheet_backend: ContractBackend):
        config = _add(assembly_respondent_gsheet_backend)

        assembly_respondent_gsheet_backend.repo.delete(config)
        assembly_respondent_gsheet_backend.commit()

        assert assembly_respondent_gsheet_backend.repo.get(config.assembly_respondent_gsheet_id) is None
