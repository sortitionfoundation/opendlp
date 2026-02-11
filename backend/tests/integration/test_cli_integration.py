"""ABOUTME: Integration tests for CLI commands using real database
ABOUTME: Tests actual user creation, invite generation, and database operations"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from opendlp.adapters.database import start_mappers
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

    def test_add_and_list_user_flow(self, sqlite_session_factory, cli_with_session_factory):
        """Test complete user creation and listing flow."""
        # Add a user using the CLI
        result = cli_with_session_factory(
            cli,
            [
                "users",
                "add",
                "--email",
                "integration-test@example.com",
                "--password",
                "pass123dfsaio",
            ],
        )

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "✓ User created successfully:" in result.output
        assert "integration-test@example.com" in result.output

        # List users and verify the new user appears
        result = cli_with_session_factory(cli, ["users", "list"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "integration-test@example.com" in result.output

        # Verify user was actually created in database
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user = uow.users.get_by_email("integration-test@example.com")
            assert user is not None
            assert user.global_role == GlobalRole.ADMIN
            assert user.is_active

    def test_deactivate_user_flow(self, sqlite_session_factory, cli_with_session_factory):
        """Test user deactivation flow."""

        # Create a user first
        user_email = "deactivate-test@example.com"
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user, _ = create_user(
                uow=uow,
                email=user_email,
                password="pass123oiua",
                first_name="Deactivate",
                last_name="Test",
                global_role=GlobalRole.USER,
            )

        # Deactivate the user
        result = cli_with_session_factory(cli, ["users", "deactivate", user_email, "--confirm"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert f"✓ User '{user_email}' has been deactivated." in result.output

        # Verify user is deactivated
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user = uow.users.get_by_email(user_email)
            assert user is not None
            assert not user.is_active

    def test_reset_password_flow(self, sqlite_session_factory, cli_with_session_factory, monkeypatch):
        """Test user password reset flow."""
        user_email = "reset-password-test@example.com"
        original_password = "original123abc"
        new_password = "newpassword456def"

        # Create a user first
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user, _ = create_user(
                uow=uow,
                email=user_email,
                password=original_password,
                first_name="Reset",
                last_name="Test",
                global_role=GlobalRole.USER,
            )
            original_hash = user.password_hash

        # Reset the password using CLI with explicit password
        result = cli_with_session_factory(cli, ["users", "reset-password", user_email, "--password", new_password])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert f"✓ Password reset for user '{user_email}'." in result.output

        # Verify password was changed
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user = uow.users.get_by_email(user_email)
            assert user is not None
            assert user.password_hash != original_hash
            # Verify new password hash is set
            assert user.password_hash is not None


class TestCliInvitesIntegration:
    """Integration tests for invite management CLI commands."""

    def test_generate_and_list_invites_flow(self, sqlite_session_factory, cli_with_session_factory):
        """Test complete invite generation and listing flow."""
        user_email = "gen-invite-test@example.com"
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            create_user(uow=uow, email=user_email, password="pass123oiua", global_role=GlobalRole.ADMIN)

        # Generate invites
        result = cli_with_session_factory(
            cli, ["invites", "generate", "--role", "user", "--inviter-email", user_email, "--count", "2"]
        )

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "✓ Generated 2 invite(s) successfully:" in result.output

        # List invites and verify they appear
        result = cli_with_session_factory(cli, ["invites", "list"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        # Should show the 2 invites we just created
        lines = result.output.split("\n")
        invite_lines = [line for line in lines if "user" in line and "Valid" in line]
        assert len(invite_lines) >= 2

    def test_revoke_invite_flow(self, sqlite_session_factory, cli_with_session_factory):
        """Test invite revocation flow."""
        # Create an admin user and invite
        admin_email = "revoke-admin@example.com"
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            admin_user, _ = create_user(
                uow=uow, email=admin_email, password="pass123oiua", global_role=GlobalRole.ADMIN
            )
            uow.flush()  # make sqlalchemy commit enough to get a user ID
            invite = generate_invite(
                uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, expires_in_hours=168
            )
            invite_code = invite.code

        # Revoke the invite using the admin user
        result = cli_with_session_factory(
            cli, ["invites", "revoke", invite_code, "--admin-email", admin_email, "--confirm"]
        )

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert f"✓ Invite '{invite_code}' has been revoked by {admin_email}." in result.output

        # Verify invite is no longer valid
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            invite = uow.user_invites.get_by_code(invite_code)
            assert invite is not None
            # Revoked invites should not be valid
            assert not invite.is_valid()
            # Should be marked as used by the admin user
            assert invite.used_by == admin_user.id

    def test_revoke_invite_non_admin_fails(self, sqlite_session_factory, cli_with_session_factory):
        """Test that non-admin users cannot revoke invites."""
        admin_email = "revoke-admin2@example.com"
        non_admin_email = "regular-user@example.com"
        # Create admin user and invite
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            admin_user, _ = create_user(
                uow=uow, email=admin_email, password="pass123oiua", global_role=GlobalRole.ADMIN
            )

            # Create non-admin user
            create_user(uow=uow, email=non_admin_email, password="pass123oiua", global_role=GlobalRole.USER)
            uow.flush()  # make sqlalchemy commit enough to get a user ID

            invite = generate_invite(
                uow=uow, created_by_user_id=admin_user.id, global_role=GlobalRole.USER, expires_in_hours=168
            )
            invite_code = invite.code

        # Try to revoke with non-admin user - should fail
        result = cli_with_session_factory(
            cli, ["invites", "revoke", invite_code, "--admin-email", non_admin_email, "--confirm"]
        )

        assert result.exit_code == 1, f"Expected failure but got exit code: {result.exit_code}. Output: {result.output}"
        assert f"✗ User '{non_admin_email}' must have ADMIN role to revoke invites." in result.output

        # Verify invite is still valid
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            invite = uow.user_invites.get_by_code(invite_code)
            assert invite is not None
            assert invite.is_valid()  # Should still be valid since revoke failed
            assert invite.used_by is None

    def test_cleanup_expired_invites(self, sqlite_session_factory, cli_with_session_factory):
        """Test cleanup of expired invites."""
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user, _ = create_user(
                uow=uow, email="gen-invite-test@example.com", password="pass123oiua", global_role=GlobalRole.ADMIN
            )

        # Create an expired invite directly
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            expired_invite = UserInvite(
                invite_id=uuid.uuid4(),
                code=generate_invite_code(),
                global_role=GlobalRole.USER,
                created_by=user.id,
                created_at=datetime.now(UTC),
                expires_at=datetime(2023, 1, 1, tzinfo=UTC),  # Expired
            )
            uow.user_invites.add(expired_invite)
            uow.commit()

            expired_code = expired_invite.code

        # Run cleanup
        result = cli_with_session_factory(cli, ["invites", "cleanup", "--confirm"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "✓ Cleaned up" in result.output and "expired invite(s)." in result.output

        # Verify expired invite was removed
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            invite = uow.user_invites.get_by_code(expired_code)
            assert invite is None


class TestCliDatabaseIntegration:
    """Integration tests for database CLI commands."""

    def test_seed_database_flow(self, sqlite_session_factory, cli_with_session_factory):
        """Test database seeding flow."""

        # Seed the database
        result = cli_with_session_factory(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "✓ Database seeded successfully with test data:" in result.output
        assert "admin@opendlp.example" in result.output

        # Verify seeded data exists
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
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
            invites = uow.user_invites.all()
            assert len(invites) >= 3  # At least the 3 we created

            # Check assembly exists
            assemblies = uow.assemblies.all()
            assert len(assemblies) >= 1  # At least the sample assembly

    def test_seed_already_seeded_database(self, sqlite_session_factory, cli_with_session_factory):
        """Test seeding when database already has data."""

        # Create a user first to simulate existing data
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            create_user(
                uow=uow,
                email="existing@example.com",
                password="pass123,muq",
                first_name="Existing",
                last_name="User",
                global_role=GlobalRole.USER,
            )

        # Try to seed - should skip
        result = cli_with_session_factory(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
        assert "Database already contains users. Skipping seed." in result.output

    def test_reset_database_flow(self, sqlite_session_factory, cli_with_session_factory, monkeypatch):
        """Test database reset flow."""
        # Enable dangerous reset operation
        monkeypatch.setenv("ALLOW_RESET_DB", "DANGEROUS")

        # Create some initial data
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            create_user(
                uow=uow,
                email="before-reset@example.com",
                password="pass123oiua",
                global_role=GlobalRole.USER,
            )

        # Verify initial data exists
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user = uow.users.get_by_email("before-reset@example.com")
            assert user is not None

        # Mock the confirmation input to "delete everything"
        with monkeypatch.context() as m:
            m.setattr("click.prompt", lambda msg: "delete everything")

            # Reset the database
            result = cli_with_session_factory(cli, ["database", "reset"])

            assert result.exit_code == 0, f"exit code non-zero: {result.exit_code}. Output: {result.output}"
            assert "✓ Database reset successfully." in result.output

        # Verify data was cleared
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user = uow.users.get_by_email("before-reset@example.com")
            assert user is None  # Should be gone after reset


class TestCliCeleryIntegration:
    """Integration tests for Celery management CLI commands."""

    # list-tasks command tests
    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_list_tasks_no_workers(self, mock_celery_app, cli_with_session_factory):
        """Test list-tasks when no Celery workers are running."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = None
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "list-tasks"])

        assert result.exit_code == 0, f"Expected exit code 0 but got {result.exit_code}. Output: {result.output}"
        assert "⚠️  Warning: No Celery workers are running" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_list_tasks_no_active_tasks(self, mock_celery_app, cli_with_session_factory):
        """Test list-tasks when workers are running but no tasks are active."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {"celery@worker1": []}
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "list-tasks"])

        assert result.exit_code == 0, f"Expected exit code 0 but got {result.exit_code}. Output: {result.output}"
        assert "✓ No tasks currently running" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_list_tasks_with_active_tasks(self, mock_celery_app, cli_with_session_factory):
        """Test list-tasks shows tasks but always exits 0."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [
                {
                    "id": "def456-task-id-0987654321",
                    "name": "opendlp.entrypoints.celery.tasks.load_gsheet",
                    "args": [],
                    "kwargs": {},
                }
            ]
        }
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "list-tasks"])

        assert result.exit_code == 0, f"Expected exit code 0 but got {result.exit_code}. Output: {result.output}"
        assert "⚙  1 task(s) currently running:" in result.output
        assert "load_gsheet" in result.output

    # check-tasks command tests
    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_check_tasks_no_workers(self, mock_celery_app, cli_with_session_factory):
        """Test check-tasks when no Celery workers are running."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = None
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "check-tasks"])

        assert result.exit_code == 2, f"Expected exit code 2 but got {result.exit_code}. Output: {result.output}"
        assert "⚠️  Warning: No Celery workers are running" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_check_tasks_no_active_tasks(self, mock_celery_app, cli_with_session_factory):
        """Test check-tasks when workers are running but no tasks are active."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {"celery@worker1": []}
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "check-tasks"])

        assert result.exit_code == 0, f"Expected exit code 0 but got {result.exit_code}. Output: {result.output}"
        assert "✓ No tasks currently running" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_check_tasks_with_active_tasks(self, mock_celery_app, cli_with_session_factory):
        """Test check-tasks when tasks are actively running."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [
                {
                    "id": "abc123-task-id-1234567890",
                    "name": "opendlp.entrypoints.celery.tasks.run_select",
                    "args": [],
                    "kwargs": {},
                }
            ]
        }
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "check-tasks"])

        assert result.exit_code == 1, f"Expected exit code 1 but got {result.exit_code}. Output: {result.output}"
        assert "✗ Tasks are running (deployment blocked)" in result.output
        assert "⚙  1 task(s) currently running:" in result.output
        assert "Worker: celery@worker1" in result.output
        assert "run_select" in result.output
        assert "abc123-t" in result.output  # First 8 chars of task ID

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_check_tasks_multiple_workers(self, mock_celery_app, cli_with_session_factory):
        """Test check-tasks with multiple workers each running multiple tasks."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [
                {
                    "id": "task1-aaaa-bbbb",
                    "name": "opendlp.entrypoints.celery.tasks.run_select",
                    "args": [],
                    "kwargs": {},
                },
                {
                    "id": "task2-cccc-dddd",
                    "name": "opendlp.entrypoints.celery.tasks.load_gsheet",
                    "args": [],
                    "kwargs": {},
                },
            ],
            "celery@worker2": [
                {
                    "id": "task3-eeee-ffff",
                    "name": "opendlp.entrypoints.celery.tasks.manage_old_tabs",
                    "args": [],
                    "kwargs": {},
                }
            ],
        }
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "check-tasks"])

        assert result.exit_code == 1, f"Expected exit code 1 but got {result.exit_code}. Output: {result.output}"
        assert "⚙  3 task(s) currently running:" in result.output
        assert "Worker: celery@worker1" in result.output
        assert "Worker: celery@worker2" in result.output
        assert "run_select" in result.output
        assert "load_gsheet" in result.output
        assert "manage_old_tabs" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_check_tasks_connection_error(self, mock_celery_app, cli_with_session_factory):
        """Test check-tasks handles connection errors gracefully."""
        mock_inspect = MagicMock()
        mock_inspect.active.side_effect = Exception("Connection refused to Redis")
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "check-tasks"])

        assert result.exit_code == 2, f"Expected exit code 2 but got {result.exit_code}. Output: {result.output}"
        assert "✗ Error connecting to Celery:" in result.output
        assert "Connection refused to Redis" in result.output
        assert "Make sure Redis is accessible and Celery is configured correctly" in result.output

    # wait-tasks command tests
    @patch("opendlp.entrypoints.cli.celery.time")
    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_wait_tasks_completes(self, mock_celery_app, mock_time, cli_with_session_factory):
        """Test wait-tasks that waits for tasks to complete."""
        mock_inspect = MagicMock()
        mock_inspect.active.side_effect = [
            # First check: task running
            {
                "celery@worker1": [
                    {
                        "id": "ghi789-task-id-1111111111",
                        "name": "opendlp.entrypoints.celery.tasks.manage_old_tabs",
                        "args": [],
                        "kwargs": {},
                    }
                ]
            },
            # Second check: task completed
            {"celery@worker1": []},
        ]
        mock_celery_app.control.inspect.return_value = mock_inspect
        mock_time.sleep = MagicMock()

        result = cli_with_session_factory(cli, ["celery", "wait-tasks", "--timeout", "30"])

        assert result.exit_code == 0, f"Expected exit code 0 but got {result.exit_code}. Output: {result.output}"
        assert "✓ All tasks completed" in result.output
        assert "Waiting up to 30s for tasks to complete" in result.output
        assert mock_time.sleep.call_count == 1
        mock_time.sleep.assert_called_with(5)  # 5 second poll interval

    @patch("opendlp.entrypoints.cli.celery.time")
    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_wait_tasks_timeout(self, mock_celery_app, mock_time, cli_with_session_factory):
        """Test wait-tasks times out if tasks don't complete."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "celery@worker1": [
                {
                    "id": "jkl012-task-id-2222222222",
                    "name": "opendlp.entrypoints.celery.tasks.run_select",
                    "args": [],
                    "kwargs": {},
                }
            ]
        }
        mock_celery_app.control.inspect.return_value = mock_inspect
        mock_time.sleep = MagicMock()

        result = cli_with_session_factory(cli, ["celery", "wait-tasks", "--timeout", "10"])

        assert result.exit_code == 1, f"Expected exit code 1 but got {result.exit_code}. Output: {result.output}"
        assert "✗ Tasks still running after 10s timeout (deployment blocked)" in result.output

    @patch("opendlp.entrypoints.cli.celery.celery_app")
    def test_wait_tasks_no_workers(self, mock_celery_app, cli_with_session_factory):
        """Test wait-tasks when no Celery workers are running."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = None
        mock_celery_app.control.inspect.return_value = mock_inspect

        result = cli_with_session_factory(cli, ["celery", "wait-tasks"])

        assert result.exit_code == 2, f"Expected exit code 2 but got {result.exit_code}. Output: {result.output}"
        assert "⚠️  Warning: No Celery workers are running" in result.output
