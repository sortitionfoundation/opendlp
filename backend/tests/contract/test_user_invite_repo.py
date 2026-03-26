"""ABOUTME: Contract tests for UserInviteRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.value_objects import GlobalRole
from tests.contract.conftest import ContractBackend


def _make_invite(
    backend: ContractBackend,
    created_by: uuid.UUID,
    global_role: GlobalRole = GlobalRole.USER,
    expires_in_hours: int = 168,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    used_by: uuid.UUID | None = None,
    code: str | None = None,
) -> UserInvite:
    invite = UserInvite(
        global_role=global_role,
        created_by=created_by,
        expires_in_hours=expires_in_hours,
        created_at=created_at,
        expires_at=expires_at,
        used_by=used_by,
        code=code,
    )
    backend.repo.add(invite)
    backend.commit()
    return invite


class TestAddAndGet:
    def test_add_and_get_by_id(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()
        invite = _make_invite(user_invite_backend, created_by=user.id)

        retrieved = user_invite_backend.repo.get(invite.id)
        assert retrieved is not None
        assert retrieved.id == invite.id
        assert retrieved.global_role == GlobalRole.USER

    def test_get_nonexistent_returns_none(self, user_invite_backend: ContractBackend):
        assert user_invite_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_invites(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()
        i1 = _make_invite(user_invite_backend, created_by=user.id)
        i2 = _make_invite(user_invite_backend, created_by=user.id)

        all_invites = list(user_invite_backend.repo.all())
        ids = {i.id for i in all_invites}
        assert i1.id in ids
        assert i2.id in ids


class TestGetByCode:
    def test_get_by_code(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()
        invite = _make_invite(user_invite_backend, created_by=user.id, code="TESTCODE123")

        retrieved = user_invite_backend.repo.get_by_code("TESTCODE123")
        assert retrieved is not None
        assert retrieved.id == invite.id

    def test_get_by_nonexistent_code_returns_none(self, user_invite_backend: ContractBackend):
        assert user_invite_backend.repo.get_by_code("NONEXISTENT") is None


class TestGetValidInvites:
    def test_returns_only_valid_invites(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()

        # Valid invite
        valid = _make_invite(user_invite_backend, created_by=user.id, expires_in_hours=24)

        # Expired invite
        past = datetime.now(UTC) - timedelta(hours=5)
        _make_invite(user_invite_backend, created_by=user.id, created_at=past, expires_at=past + timedelta(hours=1))

        # Used invite
        _make_invite(user_invite_backend, created_by=user.id, used_by=user.id)

        valid_invites = list(user_invite_backend.repo.get_valid_invites())
        assert len(valid_invites) == 1
        assert valid_invites[0].id == valid.id


class TestGetInvitesCreatedBy:
    def test_returns_invites_by_creator(self, user_invite_backend: ContractBackend):
        user1 = user_invite_backend.make_user()
        user2 = user_invite_backend.make_user()

        _make_invite(user_invite_backend, created_by=user1.id)
        _make_invite(user_invite_backend, created_by=user1.id)
        _make_invite(user_invite_backend, created_by=user2.id)

        invites = list(user_invite_backend.repo.get_invites_created_by(user1.id))
        assert len(invites) == 2
        assert all(i.created_by == user1.id for i in invites)


class TestGetExpiredInvites:
    def test_returns_expired_invites(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()

        # Expired invite
        past = datetime.now(UTC) - timedelta(hours=5)
        expired = _make_invite(
            user_invite_backend, created_by=user.id, created_at=past, expires_at=past + timedelta(hours=1)
        )

        # Valid invite
        _make_invite(user_invite_backend, created_by=user.id, expires_in_hours=24)

        expired_invites = list(user_invite_backend.repo.get_expired_invites())
        assert len(expired_invites) == 1
        assert expired_invites[0].id == expired.id


class TestDelete:
    def test_delete_removes_invite(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()
        invite = _make_invite(user_invite_backend, created_by=user.id)

        user_invite_backend.repo.delete(invite)
        user_invite_backend.commit()

        assert user_invite_backend.repo.get(invite.id) is None

    def test_delete_leaves_other_invites(self, user_invite_backend: ContractBackend):
        user = user_invite_backend.make_user()
        i1 = _make_invite(user_invite_backend, created_by=user.id)
        i2 = _make_invite(user_invite_backend, created_by=user.id)

        user_invite_backend.repo.delete(i1)
        user_invite_backend.commit()

        assert user_invite_backend.repo.get(i1.id) is None
        assert user_invite_backend.repo.get(i2.id) is not None
