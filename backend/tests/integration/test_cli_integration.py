"""ABOUTME: Integration tests for CLI commands using real database
ABOUTME: Tests actual user creation, invite generation, and database operations"""

import uuid
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from opendlp.adapters.database import start_mappers
from opendlp.config import SQLITE_DB_URI
from opendlp.domain.user_invites import UserInvite, generate_invite_code
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.cli import cli
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user


@pytest.fixture(autouse=True)
def setup_mappers():
    """Ensure database mappers are started before tests."""
    start_mappers()


class TestCliUsersIntegration:
    """Integration tests for user management CLI commands."""

    def test_add_and_list_user_flow(self, temp_env_vars):
        """Test complete user creation and listing flow."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # First, create an invite to use for user creation
        with SqlAlchemyUnitOfWork() as uow:
            # Create a system invite (created_by=None for CLI usage)
            invite = generate_invite(
                uow=uow, created_by_user_id=None, global_role=GlobalRole.USER, expires_in_hours=168
            )
            invite_code = invite.code

        # Add a user using the CLI
        result = runner.invoke(
            cli,
            [
                "users",
                "add",
                "--email",
                "integration-test@example.com",
                "--first-name",
                "Integration",
                "--last-name",
                "Test",
                "--password",
                "password123",
                "--invite-code",
                invite_code,
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created successfully:" in result.output
        assert "integration-test@example.com" in result.output

        # List users and verify the new user appears
        result = runner.invoke(cli, ["users", "list"])

        assert result.exit_code == 0
        assert "integration-test@example.com" in result.output
        assert "Integration Test" in result.output

        # Verify user was actually created in database
        with SqlAlchemyUnitOfWork() as uow:
            user = uow.users.get_by_email("integration-test@example.com")
            assert user is not None
            assert user.first_name == "Integration"
            assert user.last_name == "Test"
            assert user.global_role == GlobalRole.USER
            assert user.is_active

    def test_add_admin_user_without_invite(self, temp_env_vars):
        """Test creating admin user without invite code."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        result = runner.invoke(
            cli,
            [
                "users",
                "add",
                "--email",
                "admin-test@example.com",
                "--first-name",
                "Admin",
                "--last-name",
                "Test",
                "--role",
                "admin",
                "--password",
                "adminpass123",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created successfully:" in result.output

        # Verify admin user was created
        with SqlAlchemyUnitOfWork() as uow:
            user = uow.users.get_by_email("admin-test@example.com")
            assert user is not None
            assert user.global_role == GlobalRole.ADMIN

    def test_deactivate_user_flow(self, temp_env_vars):
        """Test user deactivation flow."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Create a user first
        with SqlAlchemyUnitOfWork() as uow:
            invite = generate_invite(
                uow=uow, created_by_user_id=None, global_role=GlobalRole.USER, expires_in_hours=168
            )

            user = create_user(
                uow=uow,
                email="deactivate-test@example.com",
                password="password123",
                invite_code=invite.code,
                first_name="Deactivate",
                last_name="Test",
            )
            user_email = user.email

        # Deactivate the user
        result = runner.invoke(cli, ["users", "deactivate", user_email, "--confirm"])

        assert result.exit_code == 0
        assert f"✓ User '{user_email}' has been deactivated." in result.output

        # Verify user is deactivated
        with SqlAlchemyUnitOfWork() as uow:
            user = uow.users.get_by_email(user_email)
            assert user is not None
            assert not user.is_active


class TestCliInvitesIntegration:
    """Integration tests for invite management CLI commands."""

    def test_generate_and_list_invites_flow(self, temp_env_vars):
        """Test complete invite generation and listing flow."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Generate invites
        result = runner.invoke(cli, ["invites", "generate", "--role", "user", "--expires-in", "168", "--count", "2"])

        assert result.exit_code == 0
        assert "✓ Generated 2 invite(s) successfully:" in result.output

        # List invites and verify they appear
        result = runner.invoke(cli, ["invites", "list"])

        assert result.exit_code == 0
        # Should show the 2 invites we just created
        lines = result.output.split("\n")
        invite_lines = [line for line in lines if "user" in line and "Valid" in line]
        assert len(invite_lines) >= 2

    def test_revoke_invite_flow(self, temp_env_vars):
        """Test invite revocation flow."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Create an invite first
        with SqlAlchemyUnitOfWork() as uow:
            invite = generate_invite(
                uow=uow, created_by_user_id=None, global_role=GlobalRole.USER, expires_in_hours=168
            )
            invite_code = invite.code

        # Revoke the invite
        result = runner.invoke(cli, ["invites", "revoke", invite_code, "--confirm"])

        assert result.exit_code == 0
        assert f"✓ Invite '{invite_code}' has been revoked." in result.output

        # Verify invite is no longer valid
        with SqlAlchemyUnitOfWork() as uow:
            invite = uow.user_invites.get_by_code(invite_code)
            assert invite is not None
            # Revoked invites should not be valid
            assert not invite.is_valid()

    def test_cleanup_expired_invites(self, temp_env_vars):
        """Test cleanup of expired invites."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Create an expired invite directly
        with SqlAlchemyUnitOfWork() as uow:
            expired_invite = UserInvite(
                invite_id=uuid.uuid4(),
                code=generate_invite_code(),
                global_role=GlobalRole.USER,
                created_by=None,
                created_at=datetime.now(UTC),
                expires_at=datetime(2023, 1, 1, tzinfo=UTC),  # Expired
            )
            uow.user_invites.add(expired_invite)
            uow.commit()

            expired_code = expired_invite.code

        # Run cleanup
        result = runner.invoke(cli, ["invites", "cleanup", "--confirm"])

        assert result.exit_code == 0
        assert "✓ Cleaned up" in result.output and "expired invite(s)." in result.output

        # Verify expired invite was removed
        with SqlAlchemyUnitOfWork() as uow:
            invite = uow.user_invites.get_by_code(expired_code)
            assert invite is None


class TestCliDatabaseIntegration:
    """Integration tests for database CLI commands."""

    def test_seed_database_flow(self, temp_env_vars):
        """Test database seeding flow."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Seed the database
        result = runner.invoke(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0
        assert "✓ Database seeded successfully with test data:" in result.output
        assert "admin@opendlp.example" in result.output

        # Verify seeded data exists
        with SqlAlchemyUnitOfWork() as uow:
            # Check admin user exists
            admin_user = uow.users.get_by_email("admin@opendlp.example")
            assert admin_user is not None
            assert admin_user.global_role == GlobalRole.ADMIN

            # Check organiser exists
            organiser_user = uow.users.get_by_email("organiser@opendlp.example")
            assert organiser_user is not None
            assert organiser_user.global_role == GlobalRole.GLOBAL_ORGANISER

            # Check regular user exists
            regular_user = uow.users.get_by_email("user@opendlp.example")
            assert regular_user is not None
            assert regular_user.global_role == GlobalRole.USER

            # Check invites exist
            invites = uow.user_invites.list()
            assert len(invites) >= 3  # At least the 3 we created

            # Check assembly exists
            assemblies = uow.assemblies.list()
            assert len(assemblies) >= 1  # At least the sample assembly

    def test_seed_already_seeded_database(self, temp_env_vars):
        """Test seeding when database already has data."""
        temp_env_vars(DB_URI=SQLITE_DB_URI)
        runner = CliRunner()

        # Create a user first to simulate existing data
        with SqlAlchemyUnitOfWork() as uow:
            invite = generate_invite(
                uow=uow, created_by_user_id=None, global_role=GlobalRole.USER, expires_in_hours=168
            )

            create_user(
                uow=uow,
                email="existing@example.com",
                password="password123",
                invite_code=invite.code,
                first_name="Existing",
                last_name="User",
            )

        # Try to seed - should skip
        result = runner.invoke(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0
        assert "Database already contains users. Skipping seed." in result.output
