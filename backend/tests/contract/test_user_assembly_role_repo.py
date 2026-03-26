"""ABOUTME: Contract tests for UserAssemblyRoleRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole
from tests.contract.conftest import ContractBackend


def _make_role(
    backend: ContractBackend,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    role: AssemblyRole = AssemblyRole.ASSEMBLY_MANAGER,
) -> UserAssemblyRole:
    role_obj = UserAssemblyRole(user_id=user_id, assembly_id=assembly_id, role=role)
    backend.repo.add(role_obj)
    backend.commit()
    return role_obj


class TestAddAndGet:
    def test_add_and_get_by_id(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        assembly = user_assembly_role_backend.make_assembly()
        role = _make_role(user_assembly_role_backend, user.id, assembly.id)

        retrieved = user_assembly_role_backend.repo.get(role.id)
        assert retrieved is not None
        assert retrieved.id == role.id
        assert retrieved.role == AssemblyRole.ASSEMBLY_MANAGER

    def test_get_nonexistent_returns_none(self, user_assembly_role_backend: ContractBackend):
        assert user_assembly_role_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_roles(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        a1 = user_assembly_role_backend.make_assembly()
        a2 = user_assembly_role_backend.make_assembly()
        r1 = _make_role(user_assembly_role_backend, user.id, a1.id)
        r2 = _make_role(user_assembly_role_backend, user.id, a2.id)

        all_roles = list(user_assembly_role_backend.repo.all())
        ids = {r.id for r in all_roles}
        assert r1.id in ids
        assert r2.id in ids


class TestGetByUserAndAssembly:
    def test_finds_existing_role(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        assembly = user_assembly_role_backend.make_assembly()
        role = _make_role(user_assembly_role_backend, user.id, assembly.id)

        retrieved = user_assembly_role_backend.repo.get_by_user_and_assembly(user.id, assembly.id)
        assert retrieved is not None
        assert retrieved.id == role.id

    def test_returns_none_for_nonexistent(self, user_assembly_role_backend: ContractBackend):
        result = user_assembly_role_backend.repo.get_by_user_and_assembly(uuid.uuid4(), uuid.uuid4())
        assert result is None


class TestGetRolesForUser:
    def test_returns_all_roles_for_user(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        a1 = user_assembly_role_backend.make_assembly()
        a2 = user_assembly_role_backend.make_assembly()
        _make_role(user_assembly_role_backend, user.id, a1.id)
        _make_role(user_assembly_role_backend, user.id, a2.id, role=AssemblyRole.CONFIRMATION_CALLER)

        roles = list(user_assembly_role_backend.repo.get_roles_for_user(user.id))
        assert len(roles) == 2

    def test_does_not_return_other_users_roles(self, user_assembly_role_backend: ContractBackend):
        user1 = user_assembly_role_backend.make_user()
        user2 = user_assembly_role_backend.make_user()
        assembly = user_assembly_role_backend.make_assembly()
        _make_role(user_assembly_role_backend, user1.id, assembly.id)

        roles = list(user_assembly_role_backend.repo.get_roles_for_user(user2.id))
        assert roles == []


class TestGetRolesForAssembly:
    def test_returns_all_roles_for_assembly(self, user_assembly_role_backend: ContractBackend):
        user1 = user_assembly_role_backend.make_user()
        user2 = user_assembly_role_backend.make_user()
        assembly = user_assembly_role_backend.make_assembly()
        _make_role(user_assembly_role_backend, user1.id, assembly.id)
        _make_role(user_assembly_role_backend, user2.id, assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)

        roles = list(user_assembly_role_backend.repo.get_roles_for_assembly(assembly.id))
        assert len(roles) == 2

    def test_does_not_return_other_assembly_roles(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        a1 = user_assembly_role_backend.make_assembly()
        a2 = user_assembly_role_backend.make_assembly()
        _make_role(user_assembly_role_backend, user.id, a1.id)

        roles = list(user_assembly_role_backend.repo.get_roles_for_assembly(a2.id))
        assert roles == []


class TestRemoveRole:
    def test_removes_existing_role(self, user_assembly_role_backend: ContractBackend):
        user = user_assembly_role_backend.make_user()
        assembly = user_assembly_role_backend.make_assembly()
        _make_role(user_assembly_role_backend, user.id, assembly.id)

        success = user_assembly_role_backend.repo.remove_role(user.id, assembly.id)
        user_assembly_role_backend.commit()

        assert success is True
        assert user_assembly_role_backend.repo.get_by_user_and_assembly(user.id, assembly.id) is None

    def test_returns_false_for_nonexistent_role(self, user_assembly_role_backend: ContractBackend):
        success = user_assembly_role_backend.repo.remove_role(uuid.uuid4(), uuid.uuid4())
        assert success is False
