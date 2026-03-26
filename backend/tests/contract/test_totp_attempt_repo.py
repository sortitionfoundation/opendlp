"""ABOUTME: Contract tests for TotpVerificationAttemptRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.totp_attempts import TotpVerificationAttempt
from tests.contract.conftest import ContractBackend


def _make_attempt(
    backend: ContractBackend,
    user_id: uuid.UUID,
    success: bool = False,
    attempted_at: datetime | None = None,
) -> TotpVerificationAttempt:
    attempt = TotpVerificationAttempt(user_id=user_id, success=success, attempted_at=attempted_at)
    backend.repo.add(attempt)
    backend.commit()
    return attempt


class TestAddAndGet:
    def test_add_and_get_by_id(self, totp_attempt_backend: ContractBackend):
        user = totp_attempt_backend.make_user()
        attempt = _make_attempt(totp_attempt_backend, user.id, success=True)

        retrieved = totp_attempt_backend.repo.get(attempt.id)
        assert retrieved is not None
        assert retrieved.id == attempt.id
        assert retrieved.success is True

    def test_get_nonexistent_returns_none(self, totp_attempt_backend: ContractBackend):
        assert totp_attempt_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_attempts(self, totp_attempt_backend: ContractBackend):
        user = totp_attempt_backend.make_user()
        a1 = _make_attempt(totp_attempt_backend, user.id, success=True)
        a2 = _make_attempt(totp_attempt_backend, user.id, success=False)

        all_attempts = list(totp_attempt_backend.repo.all())
        ids = {a.id for a in all_attempts}
        assert a1.id in ids
        assert a2.id in ids


class TestGetAttemptsSince:
    def test_returns_attempts_since_datetime(self, totp_attempt_backend: ContractBackend):
        user = totp_attempt_backend.make_user()

        old = datetime.now(UTC) - timedelta(hours=2)
        _make_attempt(totp_attempt_backend, user.id, attempted_at=old)
        recent = _make_attempt(totp_attempt_backend, user.id)

        since = datetime.now(UTC) - timedelta(hours=1)
        attempts = list(totp_attempt_backend.repo.get_attempts_since(user.id, since))
        assert len(attempts) == 1
        assert attempts[0].id == recent.id

    def test_returns_empty_for_other_user(self, totp_attempt_backend: ContractBackend):
        user1 = totp_attempt_backend.make_user()
        user2 = totp_attempt_backend.make_user()
        _make_attempt(totp_attempt_backend, user1.id)

        since = datetime.now(UTC) - timedelta(hours=1)
        assert list(totp_attempt_backend.repo.get_attempts_since(user2.id, since)) == []

    def test_returns_most_recent_first(self, totp_attempt_backend: ContractBackend):
        user = totp_attempt_backend.make_user()
        older = _make_attempt(totp_attempt_backend, user.id, attempted_at=datetime.now(UTC) - timedelta(minutes=5))
        newer = _make_attempt(totp_attempt_backend, user.id, attempted_at=datetime.now(UTC))

        since = datetime.now(UTC) - timedelta(hours=1)
        attempts = list(totp_attempt_backend.repo.get_attempts_since(user.id, since))
        assert attempts[0].id == newer.id
        assert attempts[1].id == older.id
