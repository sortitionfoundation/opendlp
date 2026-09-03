"""ABOUTME: Unit tests for invite service layer operations
ABOUTME: Tests invite generation, listing, revocation, and cleanup with fake repositories"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import invite_service
from opendlp.service_layer.exceptions import InsufficientPermissions, InviteNotFoundError, UserNotFoundError


class TestGenerateInvite:
    """Test invite generation functionality."""

    def test_generate_invite_success_admin(self, uow):
        """Test successful invite generation by admin."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invite = invite_service.generate_invite(
            uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, expires_in_hours=48
        )

        assert invite.global_role == GlobalRole.USER
        assert invite.created_by == admin_user.id
        assert invite.code is not None
        assert len(invite.code) > 0
        assert invite.expires_at > datetime.now(UTC)
        assert len(uow.user_invites.all()) == 1

    def test_generate_invite_refused_for_organiser(self, uow):
        """Invites are administered by admins only, so an organiser is refused."""
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser_user)

        with pytest.raises(InsufficientPermissions):
            invite_service.generate_invite(uow=uow, created_by_user_id=organiser_user.id, global_role=GlobalRole.USER)

    def test_generate_invite_insufficient_permissions(self, uow):
        """Test invite generation fails for regular user."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            invite_service.generate_invite(uow=uow, created_by_user_id=regular_user.id, global_role=GlobalRole.USER)

    def test_generate_invite_with_email(self, uow):
        """Test that generate_invite accepts email and stores it on the invite."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invite = invite_service.generate_invite(
            uow=uow,
            created_by_user_id=admin_user.id,
            global_role=GlobalRole.USER,
            email="invitee@example.com",
        )

        assert invite.email == "invitee@example.com"

    def test_generate_invite_email_defaults_to_empty_string(self, uow):
        """Test that generate_invite email defaults to empty string."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invite = invite_service.generate_invite(
            uow=uow,
            created_by_user_id=admin_user.id,
            global_role=GlobalRole.USER,
        )

        assert invite.email == ""

    def test_generate_invite_user_not_found(self, uow):
        """Test invite generation fails when user not found."""

        with pytest.raises(UserNotFoundError) as exc_info:
            invite_service.generate_invite(uow=uow, created_by_user_id=uuid.uuid4(), global_role=GlobalRole.USER)

        assert "not found" in str(exc_info.value)


class TestGenerateBatchInvites:
    """Test batch invite generation functionality."""

    def test_generate_batch_invites_success(self, uow):
        """Test successful batch invite generation."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invites = invite_service.generate_batch_invites(
            uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, count=5
        )

        assert len(invites) == 5
        assert len(uow.user_invites.all()) == 5
        # Check all codes are unique
        codes = {invite.code for invite in invites}
        assert len(codes) == 5

    def test_generate_batch_invites_with_email(self, uow):
        """Test that generate_batch_invites accepts email and stores it on all invites."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invites = invite_service.generate_batch_invites(
            uow=uow,
            created_by_user_id=admin_user.id,
            global_role=GlobalRole.USER,
            count=3,
            email="batch@example.com",
        )

        assert all(invite.email == "batch@example.com" for invite in invites)

    def test_generate_batch_invites_invalid_count(self, uow):
        """Test batch invite generation fails with invalid count."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        with pytest.raises(ValueError) as exc_info:
            invite_service.generate_batch_invites(
                uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, count=0
            )

        assert "Count must be between 1 and 100" in str(exc_info.value)

        with pytest.raises(ValueError):
            invite_service.generate_batch_invites(
                uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, count=101
            )

    def test_generate_batch_invites_insufficient_permissions(self, uow):
        """Test batch invite generation fails for regular user."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            invite_service.generate_batch_invites(
                uow=uow, created_by_user_id=regular_user.id, global_role=GlobalRole.USER, count=5
            )


class TestListInvites:
    """Test invite listing functionality."""

    def test_list_invites_success(self, uow):
        """Test successful invite listing."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Add some invites
        invite1 = UserInvite(
            code="VALID1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        invite2 = UserInvite(
            code="EXPIRED1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired
        )
        uow.user_invites.add(invite1)
        uow.user_invites.add(invite2)

        # List valid invites only
        invites = invite_service.list_invites(uow=uow, user_id=admin_user.id, include_expired=False)
        assert len(invites) == 1
        assert invites[0].code == "VALID1"

        # List all invites
        all_invites = invite_service.list_invites(uow=uow, user_id=admin_user.id, include_expired=True)
        assert len(all_invites) == 2

    def test_list_invites_insufficient_permissions(self, uow):
        """Test invite listing fails for regular user."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            invite_service.list_invites(uow=uow, user_id=regular_user.id)


class TestRevokeInvite:
    """Test invite revocation functionality."""

    def test_revoke_invite_success(self, uow):
        """Test successful invite revocation."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        invite = UserInvite(
            code="REVOKE1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        revoked_invite = invite_service.revoke_invite(uow=uow, invite_id=invite.id, user_id=admin_user.id)

        assert revoked_invite.used_by == admin_user.id
        assert revoked_invite.used_at is not None
        assert not revoked_invite.is_valid()

    def test_revoke_invite_insufficient_permissions(self, uow):
        """Test invite revocation fails for regular user."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(admin_user)
        uow.users.add(regular_user)

        invite = UserInvite(
            code="REVOKE2",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        with pytest.raises(InsufficientPermissions):
            invite_service.revoke_invite(uow=uow, invite_id=invite.id, user_id=regular_user.id)

    def test_revoke_invite_not_found(self, uow):
        """Test invite revocation fails when invite not found."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        with pytest.raises(InviteNotFoundError) as exc_info:
            invite_service.revoke_invite(uow=uow, invite_id=uuid.uuid4(), user_id=admin_user.id)

        assert "Invite" in str(exc_info.value)
        assert "not found" in str(exc_info.value)


class TestCleanupExpiredInvites:
    """Test expired invite cleanup functionality."""

    def test_cleanup_expired_invites_success(self, uow):
        """Test successful cleanup of expired invites."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Add expired unused invite
        expired_invite = UserInvite(
            code="EXPIRED1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        # Add used invite that is now expired (should not be cleaned up)
        used_expired_invite = UserInvite(
            code="EXPIRED_USED",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),  # Valid when used
        )
        used_expired_invite.use(admin_user.id)
        # Manually expire it after use for test purposes
        used_expired_invite.expires_at = datetime.now(UTC) - timedelta(hours=1)

        # Add valid invite
        valid_invite = UserInvite(
            code="VALID1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

        uow.user_invites.add(expired_invite)
        uow.user_invites.add(used_expired_invite)
        uow.user_invites.add(valid_invite)

        # Run cleanup
        count = invite_service.cleanup_expired_invites(uow=uow)

        # Should have deleted only the expired unused invite
        assert count == 1

        # Verify the expired unused invite was deleted
        remaining_invites = list(uow.user_invites.all())
        assert len(remaining_invites) == 2
        assert expired_invite not in remaining_invites

        # Used expired invite and valid invite should remain
        assert used_expired_invite in remaining_invites
        assert valid_invite in remaining_invites


class TestGetInviteDetails:
    """Test invite details retrieval functionality."""

    def test_get_invite_details_success(self, uow):
        """Test successful retrieval of invite details."""
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        invite = UserInvite(
            code="DETAILS1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        retrieved_invite = invite_service.get_invite_details(uow=uow, invite_id=invite.id, user_id=admin_user.id)

        assert retrieved_invite.id == invite.id
        assert retrieved_invite.code == "DETAILS1"
        assert retrieved_invite.global_role == GlobalRole.USER

    def test_get_invite_details_refused_for_organiser(self, uow):
        """An organiser cannot read invite details - invites are admin-only."""
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser_user)

        invite = UserInvite(
            code="DETAILS2",
            global_role=GlobalRole.USER,
            created_by=organiser_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        with pytest.raises(InsufficientPermissions):
            invite_service.get_invite_details(uow=uow, invite_id=invite.id, user_id=organiser_user.id)

    def test_get_invite_details_insufficient_permissions(self, uow):
        """Test invite details retrieval fails for regular user."""
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        regular_user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)
        uow.users.add(regular_user)

        invite = UserInvite(
            code="DETAILS3",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        with pytest.raises(InsufficientPermissions):
            invite_service.get_invite_details(uow=uow, invite_id=invite.id, user_id=regular_user.id)

    def test_get_invite_details_invite_not_found(self, uow):
        """Test invite details retrieval fails when invite not found."""
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        with pytest.raises(InviteNotFoundError) as exc_info:
            invite_service.get_invite_details(uow=uow, invite_id=uuid.uuid4(), user_id=admin_user.id)

        assert "Invite" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_get_invite_details_user_not_found(self, uow):
        """Test invite details retrieval fails when user not found."""

        with pytest.raises(UserNotFoundError) as exc_info:
            invite_service.get_invite_details(uow=uow, invite_id=uuid.uuid4(), user_id=uuid.uuid4())

        assert "User" in str(exc_info.value)
        assert "not found" in str(exc_info.value)


class TestGetInviteStatistics:
    """Test invite statistics functionality."""

    def test_get_invite_statistics_success(self, uow):
        """Test successful invite statistics retrieval."""
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Add various invites
        used_invite = UserInvite(
            code="USED1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        used_invite.use(admin_user.id)

        expired_invite = UserInvite(
            code="EXPIRED1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )

        valid_invite = UserInvite(
            code="VALID1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

        uow.user_invites.add(used_invite)
        uow.user_invites.add(expired_invite)
        uow.user_invites.add(valid_invite)

        stats = invite_service.get_invite_statistics(uow=uow, user_id=admin_user.id)

        assert stats["total_invites"] == 3
        assert stats["used_invites"] == 1
        assert stats["expired_invites"] == 1
        assert stats["active_invites"] == 1
        assert stats["conversion_rate"] == 33.33

    def test_get_invite_statistics_empty(self, uow):
        """Test invite statistics with no invites."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        stats = invite_service.get_invite_statistics(uow=uow, user_id=admin_user.id)

        assert stats["total_invites"] == 0
        assert stats["used_invites"] == 0
        assert stats["expired_invites"] == 0
        assert stats["active_invites"] == 0
        assert stats["conversion_rate"] == 0

    def test_get_invite_statistics_insufficient_permissions(self, uow):
        """Test invite statistics fails for regular user."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            invite_service.get_invite_statistics(uow=uow, user_id=regular_user.id)
