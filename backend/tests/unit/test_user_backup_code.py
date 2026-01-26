"""Unit tests for UserBackupCode domain model."""

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.user_backup_codes import UserBackupCode


class TestUserBackupCode:
    """Test UserBackupCode domain model."""

    def test_creates_with_required_fields(self):
        """Test that UserBackupCode can be created with required fields."""
        user_id = uuid.uuid4()
        code_hash = "hashed_code_abc123"

        backup_code = UserBackupCode(user_id=user_id, code_hash=code_hash)

        assert backup_code.user_id == user_id
        assert backup_code.code_hash == code_hash
        assert isinstance(backup_code.id, uuid.UUID)
        assert isinstance(backup_code.created_at, datetime)
        assert backup_code.created_at.tzinfo == UTC
        assert backup_code.used_at is None

    def test_creates_with_custom_id(self):
        """Test that custom ID is preserved."""
        user_id = uuid.uuid4()
        custom_id = uuid.uuid4()

        backup_code = UserBackupCode(
            user_id=user_id,
            code_hash="hash",
            backup_code_id=custom_id,
        )

        assert backup_code.id == custom_id

    def test_is_used_returns_false_for_unused_code(self):
        """Test that is_used() returns False for unused codes."""
        backup_code = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash",
        )

        assert backup_code.is_used() is False

    def test_is_used_returns_true_for_used_code(self):
        """Test that is_used() returns True for used codes."""
        backup_code = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash",
            used_at=datetime.now(UTC),
        )

        assert backup_code.is_used() is True

    def test_mark_as_used_sets_timestamp(self):
        """Test that mark_as_used() sets the used_at timestamp."""
        backup_code = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash",
        )

        backup_code.mark_as_used()

        assert isinstance(backup_code.used_at, datetime)
        assert backup_code.used_at.tzinfo == UTC
        assert backup_code.is_used() is True

    def test_mark_as_used_raises_if_already_used(self):
        """Test that mark_as_used() raises an error if code is already used."""
        backup_code = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash",
            used_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError, match="already been used"):
            backup_code.mark_as_used()

    def test_equality_based_on_id(self):
        """Test that equality is based on ID."""
        backup_id = uuid.uuid4()
        code1 = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash1",
            backup_code_id=backup_id,
        )
        code2 = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash2",
            backup_code_id=backup_id,
        )

        assert code1 == code2

    def test_inequality_different_ids(self):
        """Test that codes with different IDs are not equal."""
        code1 = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash1",
        )
        code2 = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash2",
        )

        assert code1 != code2

    def test_hash_based_on_id(self):
        """Test that hash is based on ID."""
        backup_id = uuid.uuid4()
        code = UserBackupCode(
            user_id=uuid.uuid4(),
            code_hash="hash",
            backup_code_id=backup_id,
        )

        assert hash(code) == hash(backup_id)
