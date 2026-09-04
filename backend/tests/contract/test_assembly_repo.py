"""ABOUTME: Contract tests for AssemblyRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from tests.contract.conftest import ContractBackend, make_assembly

if TYPE_CHECKING:
    from opendlp.domain.assembly import Assembly


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


class TestGetAssembliesByStatus:
    def test_returns_matching_status(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Active 1", status=AssemblyStatus.ACTIVE)
        _add_assembly(assembly_repo_backend, title="Active 2", status=AssemblyStatus.ACTIVE)
        _add_assembly(assembly_repo_backend, title="Archived", status=AssemblyStatus.ARCHIVED)

        active = list(assembly_repo_backend.repo.get_assemblies_by_status(AssemblyStatus.ACTIVE))
        assert len(active) == 2

        archived = list(assembly_repo_backend.repo.get_assemblies_by_status(AssemblyStatus.ARCHIVED))
        assert len(archived) == 1
        assert archived[0].title == "Archived"

    def test_returns_empty_when_none_match(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Active", status=AssemblyStatus.ACTIVE)

        results = list(assembly_repo_backend.repo.get_assemblies_by_status(AssemblyStatus.ARCHIVED))
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


class TestGetAssembliesForUser:
    """A role lookup, deliberately not a permission check.

    Who is entitled to see more than the assemblies they hold a role on is
    decided in service_layer.permissions, so no global role - admin included -
    changes what this returns.
    """

    def test_returns_the_assemblies_the_user_holds_a_role_on(self, assembly_repo_backend: ContractBackend):
        user = assembly_repo_backend.make_user()
        theirs = _add_assembly(assembly_repo_backend, title="Theirs")
        _add_assembly(assembly_repo_backend, title="Someone else's")
        assembly_repo_backend.grant_assembly_role(user, theirs)

        results = list(assembly_repo_backend.repo.get_assemblies_for_user(user.id))
        assert [assembly.title for assembly in results] == ["Theirs"]

    def test_returns_empty_for_a_user_with_no_roles(self, assembly_repo_backend: ContractBackend):
        user = assembly_repo_backend.make_user()
        _add_assembly(assembly_repo_backend, title="Someone else's")

        assert list(assembly_repo_backend.repo.get_assemblies_for_user(user.id)) == []

    def test_an_admin_gets_no_special_treatment(self, assembly_repo_backend: ContractBackend):
        """The global role is not this method's business."""
        admin = assembly_repo_backend.make_user(global_role=GlobalRole.ADMIN)
        _add_assembly(assembly_repo_backend, title="Not theirs")

        assert list(assembly_repo_backend.repo.get_assemblies_for_user(admin.id)) == []

    def test_returns_empty_for_a_user_id_that_names_nobody(self, assembly_repo_backend: ContractBackend):
        _add_assembly(assembly_repo_backend, title="Someone else's")

        assert list(assembly_repo_backend.repo.get_assemblies_for_user(uuid.uuid4())) == []

    def test_excludes_archived_assemblies(self, assembly_repo_backend: ContractBackend):
        user = assembly_repo_backend.make_user()
        archived = _add_assembly(assembly_repo_backend, title="Archived", status=AssemblyStatus.ARCHIVED)
        assembly_repo_backend.grant_assembly_role(user, archived)

        assert list(assembly_repo_backend.repo.get_assemblies_for_user(user.id)) == []

    def test_orders_newest_first(self, assembly_repo_backend: ContractBackend):
        user = assembly_repo_backend.make_user()
        older = _add_assembly(
            assembly_repo_backend,
            title="Older",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        newer = _add_assembly(
            assembly_repo_backend,
            title="Newer",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        assembly_repo_backend.grant_assembly_role(user, older)
        assembly_repo_backend.grant_assembly_role(user, newer)

        results = list(assembly_repo_backend.repo.get_assemblies_for_user(user.id))
        assert [assembly.title for assembly in results] == ["Newer", "Older"]


class TestCreatedByUserId:
    def test_round_trips_the_creator(self, assembly_repo_backend: ContractBackend):
        creator = assembly_repo_backend.make_user()
        assembly = _add_assembly(assembly_repo_backend, created_by_user_id=creator.id)

        retrieved = assembly_repo_backend.repo.get(assembly.id)
        assert retrieved is not None
        assert retrieved.created_by_user_id == creator.id

    def test_round_trips_no_creator(self, assembly_repo_backend: ContractBackend):
        """Assemblies made before the column existed, and any whose creator was deleted."""
        assembly = _add_assembly(assembly_repo_backend)

        retrieved = assembly_repo_backend.repo.get(assembly.id)
        assert retrieved is not None
        assert retrieved.created_by_user_id is None
