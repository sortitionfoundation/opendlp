"""ABOUTME: Contract tests for EmailConfirmationTokenRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.email_confirmation import EmailConfirmationToken
from tests.contract.conftest import ContractBackend


def _make_token(
    backend: ContractBackend,
    user_id: uuid.UUID,
    expires_in_hours: int = 24,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> EmailConfirmationToken:
    token = EmailConfirmationToken(
        user_id=user_id,
        expires_in_hours=expires_in_hours,
        created_at=created_at,
        expires_at=expires_at,
        used_at=used_at,
    )
    backend.repo.add(token)
    backend.commit()
    return token


class TestAddAndGet:
    def test_add_and_get_by_id(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        token = _make_token(email_confirmation_backend, user.id)

        retrieved = email_confirmation_backend.repo.get(token.id)
        assert retrieved is not None
        assert retrieved.id == token.id
        assert retrieved.user_id == user.id

    def test_get_nonexistent_returns_none(self, email_confirmation_backend: ContractBackend):
        assert email_confirmation_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_tokens(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        t1 = _make_token(email_confirmation_backend, user.id)
        t2 = _make_token(email_confirmation_backend, user.id)

        all_tokens = list(email_confirmation_backend.repo.all())
        ids = {t.id for t in all_tokens}
        assert t1.id in ids
        assert t2.id in ids


class TestGetByToken:
    def test_get_by_token_string(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        token = _make_token(email_confirmation_backend, user.id)

        retrieved = email_confirmation_backend.repo.get_by_token(token.token)
        assert retrieved is not None
        assert retrieved.id == token.id

    def test_get_by_nonexistent_token_returns_none(self, email_confirmation_backend: ContractBackend):
        assert email_confirmation_backend.repo.get_by_token("nonexistent") is None


class TestCountRecentRequests:
    def test_counts_tokens_since_datetime(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()

        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        _make_token(email_confirmation_backend, user.id, created_at=two_hours_ago)
        _make_token(email_confirmation_backend, user.id)

        since = datetime.now(UTC) - timedelta(hours=1)
        assert email_confirmation_backend.repo.count_recent_requests(user.id, since) == 1

    def test_counts_zero_for_no_tokens(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        since = datetime.now(UTC) - timedelta(hours=1)
        assert email_confirmation_backend.repo.count_recent_requests(user.id, since) == 0

    def test_does_not_count_other_users_tokens(self, email_confirmation_backend: ContractBackend):
        user1 = email_confirmation_backend.make_user()
        user2 = email_confirmation_backend.make_user()
        _make_token(email_confirmation_backend, user1.id)

        since = datetime.now(UTC) - timedelta(hours=1)
        assert email_confirmation_backend.repo.count_recent_requests(user2.id, since) == 0


class TestDeleteOldTokens:
    def test_deletes_tokens_before_cutoff(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()

        old_time = datetime.now(UTC) - timedelta(days=30)
        _make_token(email_confirmation_backend, user.id, created_at=old_time)
        recent = _make_token(email_confirmation_backend, user.id)

        cutoff = datetime.now(UTC) - timedelta(days=7)
        deleted = email_confirmation_backend.repo.delete_old_tokens(cutoff)
        email_confirmation_backend.commit()

        assert deleted == 1
        all_tokens = list(email_confirmation_backend.repo.all())
        assert len(all_tokens) == 1
        assert all_tokens[0].id == recent.id

    def test_returns_zero_when_nothing_to_delete(self, email_confirmation_backend: ContractBackend):
        cutoff = datetime.now(UTC) - timedelta(days=7)
        assert email_confirmation_backend.repo.delete_old_tokens(cutoff) == 0


class TestInvalidateUserTokens:
    def test_invalidates_active_tokens(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        _make_token(email_confirmation_backend, user.id)
        _make_token(email_confirmation_backend, user.id)

        count = email_confirmation_backend.repo.invalidate_user_tokens(user.id)
        email_confirmation_backend.commit()

        assert count == 2

    def test_does_not_invalidate_other_users_tokens(self, email_confirmation_backend: ContractBackend):
        user1 = email_confirmation_backend.make_user()
        user2 = email_confirmation_backend.make_user()
        _make_token(email_confirmation_backend, user1.id)
        _make_token(email_confirmation_backend, user2.id)

        count = email_confirmation_backend.repo.invalidate_user_tokens(user1.id)
        assert count == 1

    def test_returns_zero_when_no_active_tokens(self, email_confirmation_backend: ContractBackend):
        user = email_confirmation_backend.make_user()
        assert email_confirmation_backend.repo.invalidate_user_tokens(user.id) == 0
