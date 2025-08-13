"""ABOUTME: Unit tests for UserInvite domain model
ABOUTME: Tests invite creation, validation, usage, expiry, and code generation"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.user_invites import UserInvite, generate_invite_code
from opendlp.domain.value_objects import GlobalRole


class TestGenerateInviteCode:
    def test_generate_invite_code_default_length(self):
        code = generate_invite_code()
        assert len(code) == 12
        assert code.isalnum()
        assert code.isupper()

    def test_generate_invite_code_custom_length(self):
        code = generate_invite_code(length=8)
        assert len(code) == 8

        code = generate_invite_code(length=20)
        assert len(code) == 20

    def test_generate_invite_code_excludes_confusing_chars(self):
        # Generate many codes to ensure confusing characters are excluded
        for _ in range(100):
            code = generate_invite_code()
            assert "O" not in code
            assert "I" not in code
            assert "0" not in code
            assert "1" not in code

    def test_generate_invite_code_uniqueness(self):
        # Generate many codes to test uniqueness (extremely likely to be unique)
        codes = [generate_invite_code() for _ in range(1000)]
        assert len(set(codes)) == 1000  # All unique


class TestUserInvite:
    def test_create_user_invite(self):
        created_by = uuid.uuid4()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by)

        assert invite.global_role == GlobalRole.USER
        assert invite.created_by == created_by
        assert isinstance(invite.id, uuid.UUID)
        assert isinstance(invite.code, str)
        assert len(invite.code) == 12
        assert isinstance(invite.created_at, datetime)
        assert isinstance(invite.expires_at, datetime)
        assert invite.used_by is None
        assert invite.used_at is None

        # Default expiry is 7 days
        expected_expiry = invite.created_at + timedelta(hours=168)
        assert abs((invite.expires_at - expected_expiry).total_seconds()) < 1

    def test_create_user_invite_with_custom_values(self):
        invite_id = uuid.uuid4()
        created_by = uuid.uuid4()
        used_by = uuid.uuid4()
        created_time = datetime(2023, 1, 1, 10, 0, 0)
        expires_time = datetime(2023, 1, 8, 10, 0, 0)
        used_time = datetime(2023, 1, 2, 15, 30, 0)

        invite = UserInvite(
            invite_id=invite_id,
            code="CUSTOM123",
            global_role=GlobalRole.ADMIN,
            created_by=created_by,
            created_at=created_time,
            expires_at=expires_time,
            used_by=used_by,
            used_at=used_time,
        )

        assert invite.id == invite_id
        assert invite.code == "CUSTOM123"
        assert invite.global_role == GlobalRole.ADMIN
        assert invite.created_at == created_time
        assert invite.expires_at == expires_time
        assert invite.used_by == used_by
        assert invite.used_at == used_time

    def test_create_user_invite_custom_expiry(self):
        created_by = uuid.uuid4()

        invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=created_by,
            expires_in_hours=48,  # 2 days
        )

        expected_expiry = invite.created_at + timedelta(hours=48)
        assert abs((invite.expires_at - expected_expiry).total_seconds()) < 1

    def test_create_user_invite_invalid_expiry(self):
        created_by = uuid.uuid4()

        with pytest.raises(ValueError, match="Expiry hours must be positive"):
            UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=0)

        with pytest.raises(ValueError, match="Expiry hours must be positive"):
            UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=-1)

    def test_is_valid_unused_not_expired(self):
        created_by = uuid.uuid4()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=24)

        assert invite.is_valid() is True

    def test_is_valid_expired(self):
        created_by = uuid.uuid4()
        past_time = datetime.now(UTC) - timedelta(hours=2)

        invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=created_by,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),  # Expired 1 hour ago
        )

        assert invite.is_valid() is False

    def test_is_valid_used(self):
        created_by = uuid.uuid4()
        used_by = uuid.uuid4()

        invite = UserInvite(
            global_role=GlobalRole.USER, created_by=created_by, used_by=used_by, used_at=datetime.now(UTC)
        )

        assert invite.is_valid() is False

    def test_use_valid_invite(self):
        created_by = uuid.uuid4()
        user_id = uuid.uuid4()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=24)

        assert invite.used_by is None
        assert invite.used_at is None

        invite.use(user_id)

        assert invite.used_by == user_id
        assert isinstance(invite.used_at, datetime)
        assert invite.is_valid() is False  # Now invalid because it's used

    def test_use_already_used_invite(self):
        created_by = uuid.uuid4()
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=24)

        invite.use(user1_id)

        with pytest.raises(ValueError, match="Invite has already been used"):
            invite.use(user2_id)

    def test_use_expired_invite(self):
        created_by = uuid.uuid4()
        user_id = uuid.uuid4()
        past_time = datetime.now(UTC) - timedelta(hours=2)

        invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=created_by,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),  # Expired
        )

        with pytest.raises(ValueError, match="Cannot use invalid invite"):
            invite.use(user_id)

    def test_is_expired(self):
        created_by = uuid.uuid4()

        # Not expired
        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=24)
        assert invite.is_expired() is False

        # Expired
        past_time = datetime.now(UTC) - timedelta(hours=2)
        expired_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=created_by,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )
        assert expired_invite.is_expired() is True

    def test_is_used(self):
        created_by = uuid.uuid4()
        user_id = uuid.uuid4()

        # Not used
        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by)
        assert invite.is_used() is False

        # Used
        used_invite = UserInvite(
            global_role=GlobalRole.USER, created_by=created_by, used_by=user_id, used_at=datetime.now(UTC)
        )
        assert used_invite.is_used() is True

    def test_time_until_expiry(self):
        created_by = uuid.uuid4()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=created_by, expires_in_hours=24)

        time_until_expiry = invite.time_until_expiry()

        # Should be close to 24 hours
        assert 23.9 < time_until_expiry.total_seconds() / 3600 < 24.1

        # For expired invite, should be negative
        past_time = datetime.now(UTC) - timedelta(hours=2)
        expired_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=created_by,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )

        expired_time_until_expiry = expired_invite.time_until_expiry()
        assert expired_time_until_expiry.total_seconds() < 0

    def test_user_invite_equality_and_hash(self):
        invite_id = uuid.uuid4()
        created_by = uuid.uuid4()

        invite1 = UserInvite(invite_id=invite_id, global_role=GlobalRole.USER, created_by=created_by)

        invite2 = UserInvite(
            invite_id=invite_id,
            global_role=GlobalRole.ADMIN,  # Different role but same ID
            created_by=uuid.uuid4(),  # Different creator but same ID
        )

        invite3 = UserInvite(global_role=GlobalRole.USER, created_by=created_by)

        assert invite1 == invite2  # Same ID
        assert invite1 != invite3  # Different ID
        assert hash(invite1) == hash(invite2)
        assert hash(invite1) != hash(invite3)
