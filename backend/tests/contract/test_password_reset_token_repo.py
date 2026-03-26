"""ABOUTME: Contract tests for PasswordResetTokenRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from tests.contract.conftest import RepoBackend


class TestAddAndGet:
    def test_add_and_get_by_id(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        token = password_reset_backend.make_token(user.id)

        retrieved = password_reset_backend.repo.get(token.id)
        assert retrieved is not None
        assert retrieved.id == token.id
        assert retrieved.user_id == user.id

    def test_get_nonexistent_returns_none(self, password_reset_backend: RepoBackend):
        result = password_reset_backend.repo.get(uuid.uuid4())
        assert result is None

    def test_all_returns_added_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        t1 = password_reset_backend.make_token(user.id)
        t2 = password_reset_backend.make_token(user.id)

        all_tokens = list(password_reset_backend.repo.all())
        ids = {t.id for t in all_tokens}
        assert t1.id in ids
        assert t2.id in ids


class TestGetByToken:
    def test_get_by_token_string(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        token = password_reset_backend.make_token(user.id)

        retrieved = password_reset_backend.repo.get_by_token(token.token)
        assert retrieved is not None
        assert retrieved.id == token.id

    def test_get_by_nonexistent_token_returns_none(self, password_reset_backend: RepoBackend):
        result = password_reset_backend.repo.get_by_token("nonexistent-token-string")
        assert result is None


class TestGetActiveTokensForUser:
    def test_returns_only_active_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()

        # Active token (not expired, not used)
        active = password_reset_backend.make_token(user.id, expires_in_hours=24)

        # Expired token
        past = datetime.now(UTC) - timedelta(hours=5)
        password_reset_backend.make_token(
            user.id,
            created_at=past,
            expires_at=past + timedelta(hours=1),
        )

        # Used token
        used = password_reset_backend.make_token(user.id, expires_in_hours=24)
        used.use()
        password_reset_backend.commit()

        active_tokens = list(password_reset_backend.repo.get_active_tokens_for_user(user.id))
        assert len(active_tokens) == 1
        assert active_tokens[0].id == active.id

    def test_returns_empty_for_other_user(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        password_reset_backend.make_token(user.id)

        other_user = password_reset_backend.make_user()
        active_tokens = list(password_reset_backend.repo.get_active_tokens_for_user(other_user.id))
        assert active_tokens == []


class TestCountRecentRequests:
    def test_counts_tokens_since_datetime(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()

        # Token created 2 hours ago
        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        password_reset_backend.make_token(user.id, created_at=two_hours_ago)

        # Token created now
        password_reset_backend.make_token(user.id)

        # Count since 1 hour ago — should only find the recent one
        since = datetime.now(UTC) - timedelta(hours=1)
        count = password_reset_backend.repo.count_recent_requests(user.id, since)
        assert count == 1

    def test_counts_zero_for_no_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        since = datetime.now(UTC) - timedelta(hours=1)
        count = password_reset_backend.repo.count_recent_requests(user.id, since)
        assert count == 0

    def test_does_not_count_other_users_tokens(self, password_reset_backend: RepoBackend):
        user1 = password_reset_backend.make_user()
        user2 = password_reset_backend.make_user()

        password_reset_backend.make_token(user1.id)

        since = datetime.now(UTC) - timedelta(hours=1)
        count = password_reset_backend.repo.count_recent_requests(user2.id, since)
        assert count == 0


class TestDeleteOldTokens:
    def test_deletes_tokens_before_cutoff(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()

        # Old token
        old_time = datetime.now(UTC) - timedelta(days=30)
        password_reset_backend.make_token(user.id, created_at=old_time)

        # Recent token
        recent = password_reset_backend.make_token(user.id)

        cutoff = datetime.now(UTC) - timedelta(days=7)
        deleted_count = password_reset_backend.repo.delete_old_tokens(cutoff)
        password_reset_backend.commit()

        assert deleted_count == 1
        all_tokens = list(password_reset_backend.repo.all())
        assert len(all_tokens) == 1
        assert all_tokens[0].id == recent.id

    def test_returns_zero_when_nothing_to_delete(self, password_reset_backend: RepoBackend):
        cutoff = datetime.now(UTC) - timedelta(days=7)
        deleted_count = password_reset_backend.repo.delete_old_tokens(cutoff)
        assert deleted_count == 0


class TestInvalidateUserTokens:
    def test_invalidates_active_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()

        password_reset_backend.make_token(user.id, expires_in_hours=24)
        password_reset_backend.make_token(user.id, expires_in_hours=24)

        count = password_reset_backend.repo.invalidate_user_tokens(user.id)
        password_reset_backend.commit()

        assert count == 2

        # All tokens should now be used
        active = list(password_reset_backend.repo.get_active_tokens_for_user(user.id))
        assert active == []

    def test_does_not_invalidate_other_users_tokens(self, password_reset_backend: RepoBackend):
        user1 = password_reset_backend.make_user()
        user2 = password_reset_backend.make_user()

        password_reset_backend.make_token(user1.id, expires_in_hours=24)
        password_reset_backend.make_token(user2.id, expires_in_hours=24)

        count = password_reset_backend.repo.invalidate_user_tokens(user1.id)
        password_reset_backend.commit()

        assert count == 1
        # user2's token should still be active
        active = list(password_reset_backend.repo.get_active_tokens_for_user(user2.id))
        assert len(active) == 1

    def test_returns_zero_when_no_active_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        count = password_reset_backend.repo.invalidate_user_tokens(user.id)
        assert count == 0


class TestDelete:
    def test_delete_removes_token(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        token = password_reset_backend.make_token(user.id)

        password_reset_backend.repo.delete(token)
        password_reset_backend.commit()

        assert password_reset_backend.repo.get(token.id) is None

    def test_delete_leaves_other_tokens(self, password_reset_backend: RepoBackend):
        user = password_reset_backend.make_user()
        t1 = password_reset_backend.make_token(user.id)
        t2 = password_reset_backend.make_token(user.id)

        password_reset_backend.repo.delete(t1)
        password_reset_backend.commit()

        assert password_reset_backend.repo.get(t1.id) is None
        assert password_reset_backend.repo.get(t2.id) is not None
