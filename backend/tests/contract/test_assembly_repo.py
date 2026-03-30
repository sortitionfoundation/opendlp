"""ABOUTME: Contract tests for AssemblyRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyStatus
from tests.contract.conftest import ContractBackend, make_assembly


def _add_assembly(backend: ContractBackend, **kwargs: Any) -> Assembly:
    assembly = make_assembly(**kwargs)
    backend.repo.add(assembly)
    backend.commit()
    return assembly


class TestAddAndGet:
    def test_add_and_get_by_id(self, assembly_repo_backend: ContractBackend):
        assembly = _add_assembly(assembly_repo_backend, title="Test Assembly")

        retrieved = assembly_repo_backend.repo.get(assembly.id)
        assert retrieved is not None
        assert retrieved.title == "Test Assembly"

    def test_get_nonexistent_returns_none(self, assembly_repo_backend: ContractBackend):
        assert assembly_repo_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_assemblies(self, assembly_repo_backend: ContractBackend):
        a1 = _add_assembly(assembly_repo_backend, title="Assembly 1")
        a2 = _add_assembly(assembly_repo_backend, title="Assembly 2")

        all_assemblies = list(assembly_repo_backend.repo.all())
        ids = {a.id for a in all_assemblies}
        assert a1.id in ids
        assert a2.id in ids


class TestGetActiveAssemblies:
    def test_returns_only_active(self, assembly_repo_backend: ContractBackend):
        active = _add_assembly(assembly_repo_backend, title="Active", status=AssemblyStatus.ACTIVE)
        _add_assembly(assembly_repo_backend, title="Archived", status=AssemblyStatus.ARCHIVED)

        results = list(assembly_repo_backend.repo.get_active_assemblies())
        assert len(results) == 1
        assert results[0].id == active.id

    def test_returns_empty_when_none_active(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Archived", status=AssemblyStatus.ARCHIVED)

        results = list(assembly_repo_backend.repo.get_active_assemblies())
        assert len(results) == 0


class TestSearchByTitle:
    def test_finds_by_partial_match(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Climate Change Assembly")
        _add_assembly(assembly_repo_backend, title="Healthcare Assembly")

        results = list(assembly_repo_backend.repo.search_by_title("climate"))
        assert len(results) == 1
        assert results[0].title == "Climate Change Assembly"

    def test_case_insensitive(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Healthcare Assembly")

        results = list(assembly_repo_backend.repo.search_by_title("HEALTHCARE"))
        assert len(results) == 1
        assert results[0].title == "Healthcare Assembly"

    def test_matches_all_containing_term(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Climate Assembly")
        _add_assembly(assembly_repo_backend, title="Healthcare Assembly")
        _add_assembly(assembly_repo_backend, title="Education Assembly")

        results = list(assembly_repo_backend.repo.search_by_title("assembly"))
        assert len(results) == 3

    def test_returns_empty_for_no_match(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Climate Assembly")

        results = list(assembly_repo_backend.repo.search_by_title("nonexistent"))
        assert len(results) == 0
