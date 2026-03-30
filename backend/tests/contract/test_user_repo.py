"""ABOUTME: Contract tests for UserRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from tests.contract.conftest import ContractBackend, make_user


def _add_user(backend: ContractBackend, **kwargs: Any) -> User:
    user = make_user(**kwargs)
    backend.repo.add(user)
    backend.commit()
    return user


class TestAddAndGet:
    def test_add_and_get_by_id(self, user_repo_backend: ContractBackend):
        user = _add_user(
            user_repo_backend,
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        retrieved = user_repo_backend.repo.get(user.id)
        assert retrieved is not None
        assert retrieved.email == "test@example.com"
        assert retrieved.first_name == "Test"
        assert retrieved.last_name == "User"

    def test_get_nonexistent_returns_none(self, user_repo_backend: ContractBackend):
        assert user_repo_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_users(self, user_repo_backend: ContractBackend):
        u1 = _add_user(user_repo_backend, email="user1@example.com")
        u2 = _add_user(user_repo_backend, email="user2@example.com")

        all_users = list(user_repo_backend.repo.all())
        ids = {u.id for u in all_users}
        assert u1.id in ids
        assert u2.id in ids


class TestGetByEmail:
    def test_finds_by_email(self, user_repo_backend: ContractBackend):
        user = _add_user(user_repo_backend, email="test@example.com")

        retrieved = user_repo_backend.repo.get_by_email("test@example.com")
        assert retrieved is not None
        assert retrieved.id == user.id

    def test_returns_none_for_nonexistent(self, user_repo_backend: ContractBackend):
        assert user_repo_backend.repo.get_by_email("nonexistent@example.com") is None


class TestGetByOauthCredentials:
    def test_finds_by_provider_and_id(self, user_repo_backend: ContractBackend):
        user = _add_user(
            user_repo_backend,
            email="oauth@example.com",
            oauth_provider="google",
            oauth_id="12345",
        )

        retrieved = user_repo_backend.repo.get_by_oauth_credentials("google", "12345")
        assert retrieved is not None
        assert retrieved.id == user.id

    def test_returns_none_for_nonexistent(self, user_repo_backend: ContractBackend):
        assert user_repo_backend.repo.get_by_oauth_credentials("google", "nonexistent") is None


class TestFilter:
    def test_filters_by_role(self, user_repo_backend: ContractBackend):
        _add_user(user_repo_backend, email="admin@example.com", global_role=GlobalRole.ADMIN)
        _add_user(user_repo_backend, email="user@example.com", global_role=GlobalRole.USER)

        admins = list(user_repo_backend.repo.filter(role="admin"))
        assert len(admins) == 1
        assert admins[0].email == "admin@example.com"

    def test_filters_by_active(self, user_repo_backend: ContractBackend):
        _add_user(user_repo_backend, email="active@example.com", is_active=True)
        _add_user(user_repo_backend, email="inactive@example.com", is_active=False)

        active = list(user_repo_backend.repo.filter(active=True))
        assert len(active) == 1
        assert active[0].email == "active@example.com"

    def test_filters_by_role_and_active(self, user_repo_backend: ContractBackend):
        _add_user(user_repo_backend, email="active-admin@example.com", global_role=GlobalRole.ADMIN, is_active=True)
        _add_user(user_repo_backend, email="inactive-admin@example.com", global_role=GlobalRole.ADMIN, is_active=False)
        _add_user(user_repo_backend, email="active-user@example.com", global_role=GlobalRole.USER, is_active=True)

        results = list(user_repo_backend.repo.filter(role="admin", active=True))
        assert len(results) == 1
        assert results[0].email == "active-admin@example.com"

    def test_no_filters_returns_all(self, user_repo_backend: ContractBackend):
        _add_user(user_repo_backend, email="user1@example.com")
        _add_user(user_repo_backend, email="user2@example.com")

        results = list(user_repo_backend.repo.filter())
        assert len(results) == 2
