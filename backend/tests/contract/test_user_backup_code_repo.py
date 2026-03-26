"""ABOUTME: Contract tests for UserBackupCodeRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from opendlp.domain.user_backup_codes import UserBackupCode
from tests.contract.conftest import ContractBackend


def _make_code(backend: ContractBackend, user_id: uuid.UUID, code_hash: str = "") -> UserBackupCode:
    if not code_hash:
        code_hash = f"hash-{uuid.uuid4().hex[:8]}"
    code = UserBackupCode(user_id=user_id, code_hash=code_hash)
    backend.repo.add(code)
    backend.commit()
    return code


class TestAddAndGet:
    def test_add_and_get_by_id(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        code = _make_code(user_backup_code_backend, user.id)

        retrieved = user_backup_code_backend.repo.get(code.id)
        assert retrieved is not None
        assert retrieved.id == code.id
        assert retrieved.user_id == user.id

    def test_get_nonexistent_returns_none(self, user_backup_code_backend: ContractBackend):
        assert user_backup_code_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_codes(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        c1 = _make_code(user_backup_code_backend, user.id)
        c2 = _make_code(user_backup_code_backend, user.id)

        all_codes = list(user_backup_code_backend.repo.all())
        ids = {c.id for c in all_codes}
        assert c1.id in ids
        assert c2.id in ids


class TestGetCodesForUser:
    def test_returns_codes_for_user(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        c1 = _make_code(user_backup_code_backend, user.id)
        c2 = _make_code(user_backup_code_backend, user.id)

        codes = list(user_backup_code_backend.repo.get_codes_for_user(user.id))
        ids = {c.id for c in codes}
        assert c1.id in ids
        assert c2.id in ids

    def test_does_not_return_other_users_codes(self, user_backup_code_backend: ContractBackend):
        user1 = user_backup_code_backend.make_user()
        user2 = user_backup_code_backend.make_user()
        _make_code(user_backup_code_backend, user1.id)

        codes = list(user_backup_code_backend.repo.get_codes_for_user(user2.id))
        assert codes == []


class TestGetUnusedCodesForUser:
    def test_returns_only_unused_codes(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        unused = _make_code(user_backup_code_backend, user.id)
        used = _make_code(user_backup_code_backend, user.id)
        used.mark_as_used()
        user_backup_code_backend.commit()

        result = list(user_backup_code_backend.repo.get_unused_codes_for_user(user.id))
        assert len(result) == 1
        assert result[0].id == unused.id

    def test_returns_empty_when_all_used(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        code = _make_code(user_backup_code_backend, user.id)
        code.mark_as_used()
        user_backup_code_backend.commit()

        assert list(user_backup_code_backend.repo.get_unused_codes_for_user(user.id)) == []


class TestDeleteCodesForUser:
    def test_deletes_all_codes_for_user(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        _make_code(user_backup_code_backend, user.id)
        _make_code(user_backup_code_backend, user.id)

        count = user_backup_code_backend.repo.delete_codes_for_user(user.id)
        user_backup_code_backend.commit()

        assert count == 2
        assert list(user_backup_code_backend.repo.get_codes_for_user(user.id)) == []

    def test_does_not_delete_other_users_codes(self, user_backup_code_backend: ContractBackend):
        user1 = user_backup_code_backend.make_user()
        user2 = user_backup_code_backend.make_user()
        _make_code(user_backup_code_backend, user1.id)
        _make_code(user_backup_code_backend, user2.id)

        user_backup_code_backend.repo.delete_codes_for_user(user1.id)
        user_backup_code_backend.commit()

        assert len(list(user_backup_code_backend.repo.get_codes_for_user(user2.id))) == 1

    def test_returns_zero_when_no_codes(self, user_backup_code_backend: ContractBackend):
        user = user_backup_code_backend.make_user()
        assert user_backup_code_backend.repo.delete_codes_for_user(user.id) == 0
