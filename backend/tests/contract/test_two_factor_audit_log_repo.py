"""ABOUTME: Contract tests for TwoFactorAuditLogRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from tests.contract.conftest import ContractBackend


def _make_log(
    backend: ContractBackend,
    user_id: uuid.UUID,
    action: str = "2fa_enabled",
    timestamp: datetime | None = None,
) -> TwoFactorAuditLog:
    log = TwoFactorAuditLog(user_id=user_id, action=action, timestamp=timestamp)
    backend.repo.add(log)
    backend.commit()
    return log


class TestAddAndGet:
    def test_add_and_get_by_id(self, two_factor_audit_backend: ContractBackend):
        user = two_factor_audit_backend.make_user()
        log = _make_log(two_factor_audit_backend, user.id)

        retrieved = two_factor_audit_backend.repo.get(log.id)
        assert retrieved is not None
        assert retrieved.id == log.id
        assert retrieved.action == "2fa_enabled"

    def test_get_nonexistent_returns_none(self, two_factor_audit_backend: ContractBackend):
        assert two_factor_audit_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_logs(self, two_factor_audit_backend: ContractBackend):
        user = two_factor_audit_backend.make_user()
        l1 = _make_log(two_factor_audit_backend, user.id, action="2fa_enabled")
        l2 = _make_log(two_factor_audit_backend, user.id, action="2fa_disabled")

        all_logs = list(two_factor_audit_backend.repo.all())
        ids = {log.id for log in all_logs}
        assert l1.id in ids
        assert l2.id in ids


class TestGetLogsForUser:
    def test_returns_logs_for_user(self, two_factor_audit_backend: ContractBackend):
        user = two_factor_audit_backend.make_user()
        _make_log(two_factor_audit_backend, user.id, action="2fa_enabled")
        _make_log(two_factor_audit_backend, user.id, action="2fa_disabled")

        logs = list(two_factor_audit_backend.repo.get_logs_for_user(user.id))
        assert len(logs) == 2

    def test_does_not_return_other_users_logs(self, two_factor_audit_backend: ContractBackend):
        user1 = two_factor_audit_backend.make_user()
        user2 = two_factor_audit_backend.make_user()
        _make_log(two_factor_audit_backend, user1.id)

        logs = list(two_factor_audit_backend.repo.get_logs_for_user(user2.id))
        assert logs == []

    def test_respects_limit(self, two_factor_audit_backend: ContractBackend):
        user = two_factor_audit_backend.make_user()
        for i in range(5):
            _make_log(
                two_factor_audit_backend,
                user.id,
                action=f"action_{i}",
                timestamp=datetime.now(UTC) + timedelta(seconds=i),
            )

        logs = list(two_factor_audit_backend.repo.get_logs_for_user(user.id, limit=3))
        assert len(logs) == 3

    def test_returns_most_recent_first(self, two_factor_audit_backend: ContractBackend):
        user = two_factor_audit_backend.make_user()
        older = _make_log(
            two_factor_audit_backend,
            user.id,
            action="older",
            timestamp=datetime.now(UTC) - timedelta(hours=1),
        )
        newer = _make_log(
            two_factor_audit_backend,
            user.id,
            action="newer",
            timestamp=datetime.now(UTC),
        )

        logs = list(two_factor_audit_backend.repo.get_logs_for_user(user.id))
        assert logs[0].id == newer.id
        assert logs[1].id == older.id
