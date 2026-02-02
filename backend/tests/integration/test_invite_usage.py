"""ABOUTME: Integration tests for invite usage during user registration
ABOUTME: Tests that invites are properly marked as used after successful user creation"""

import pytest

from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import InvalidInvite
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user


class TestInviteUsage:
    """Test that invites are properly marked as used during user registration."""

    def test_invite_is_marked_as_used_after_successful_user_creation(self, postgres_session_factory):
        """Test that an invite is properly marked as used after successful user registration."""
        # Create an admin user first to generate invites
        admin_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        admin_user, _ = create_user(
            uow=admin_uow,
            email="admin@test.com",
            password="secure_password123",
            first_name="Admin",
            last_name="User",
            global_role=GlobalRole.ADMIN,
        )

        # Generate an invite using the admin user
        invite_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        invite = generate_invite(
            uow=invite_uow,
            created_by_user_id=admin_user.id,
            global_role=GlobalRole.USER,
            expires_in_hours=24,
        )

        # Verify invite is initially valid and not used
        fresh_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with fresh_uow:
            fresh_invite = fresh_uow.user_invites.get_by_code(invite.code)
            assert fresh_invite is not None
            assert fresh_invite.is_valid()
            assert fresh_invite.used_by is None
            assert fresh_invite.used_at is None

        # Create a new user using the invite
        user_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        new_user, _ = create_user(
            uow=user_uow,
            email="newuser@test.com",
            password="secure_password456",
            first_name="New",
            last_name="User",
            invite_code=invite.code,
        )

        # Verify the user was created successfully
        assert new_user.email == "newuser@test.com"
        assert new_user.global_role == GlobalRole.USER

        # Check that the invite is now marked as used - this should pass but currently fails
        final_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with final_uow:
            used_invite = final_uow.user_invites.get_by_code(invite.code)
            assert used_invite is not None, "Invite should still exist in database"

            # This is the failing assertion - invite should be marked as used
            assert used_invite.used_by == new_user.id, "Invite should be marked as used by the new user"
            assert used_invite.used_at is not None, "Invite should have a used_at timestamp"
            assert not used_invite.is_valid(), "Used invite should no longer be valid"

    def test_invite_cannot_be_reused_after_being_marked_as_used(self, postgres_session_factory):
        """Test that an invite cannot be reused after being marked as used."""
        # Create an admin user first to generate invites
        admin_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        admin_user, _ = create_user(
            uow=admin_uow,
            email="admin2@test.com",
            password="secure_password123",
            first_name="Admin",
            last_name="User",
            global_role=GlobalRole.ADMIN,
        )

        # Generate an invite
        invite_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        invite = generate_invite(
            uow=invite_uow,
            created_by_user_id=admin_user.id,
            global_role=GlobalRole.USER,
            expires_in_hours=24,
        )

        # Create first user with the invite
        first_user_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        create_user(
            uow=first_user_uow,
            email="firstuser@test.com",
            password="secure_password456",
            first_name="First",
            last_name="User",
            invite_code=invite.code,
        )

        # Try to create second user with the same invite - this should fail
        second_user_uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(InvalidInvite):
            create_user(
                uow=second_user_uow,
                email="seconduser@test.com",
                password="secure_password789",
                first_name="Second",
                last_name="User",
                invite_code=invite.code,
            )
