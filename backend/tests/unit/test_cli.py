"""ABOUTME: Unit tests for CLI commands with mocked dependencies
ABOUTME: Tests command parsing, output formatting, and error handling without external dependencies"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from click.testing import CliRunner

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.cli import cli
from opendlp.service_layer.exceptions import UserAlreadyExists


class TestCliUsers:
    """Test user management CLI commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.mock_uow = Mock()
        self.mock_user = User(
            user_id=uuid.uuid4(),
            email="test@example.com",
            password_hash="hashed_password",
            first_name="Test",
            last_name="User",
            global_role=GlobalRole.USER,
            created_at=datetime.now(UTC),
            is_active=True,
        )

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.users.create_user")
    def test_add_user_success(self, mock_create_user, mock_uow_class):
        """Test successful user creation."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        mock_create_user.return_value = self.mock_user

        result = self.runner.invoke(
            cli,
            [
                "users",
                "add",
                "--email",
                "test@example.com",
                "--first-name",
                "Test",
                "--last-name",
                "User",
                "--password",
                "password123",
                "--invite-code",
                "test-invite",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created successfully:" in result.output
        assert "test@example.com" in result.output
        mock_create_user.assert_called_once()

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.users.create_user")
    def test_add_user_already_exists(self, mock_create_user, mock_uow_class):
        """Test user creation when user already exists."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        mock_create_user.side_effect = UserAlreadyExists("test@example.com")

        result = self.runner.invoke(
            cli,
            [
                "users",
                "add",
                "--email",
                "test@example.com",
                "--password",
                "password123",
                "--invite-code",
                "test-invite",
            ],
        )

        assert result.exit_code == 1
        assert "✗ Error: User with email 'test@example.com' already exists" in result.output

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    def test_list_users_success(self, mock_uow_class):
        """Test successful user listing."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        self.mock_uow.users.list.return_value = [self.mock_user]

        result = self.runner.invoke(cli, ["users", "list"])

        assert result.exit_code == 0
        assert "test@example.com" in result.output
        assert "Test User" in result.output

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    def test_list_users_empty(self, mock_uow_class):
        """Test user listing when no users exist."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        self.mock_uow.users.list.return_value = []

        result = self.runner.invoke(cli, ["users", "list"])

        assert result.exit_code == 0
        assert "No users found matching criteria." in result.output

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    def test_deactivate_user_success(self, mock_uow_class):
        """Test successful user deactivation."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        self.mock_uow.users.get_by_email.return_value = self.mock_user

        result = self.runner.invoke(cli, ["users", "deactivate", "test@example.com", "--confirm"])

        assert result.exit_code == 0
        assert "✓ User 'test@example.com' has been deactivated." in result.output
        assert not self.mock_user.is_active

    @patch("opendlp.entrypoints.cli.users.SqlAlchemyUnitOfWork")
    def test_deactivate_user_not_found(self, mock_uow_class):
        """Test user deactivation when user not found."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        self.mock_uow.users.get_by_email.return_value = None

        result = self.runner.invoke(cli, ["users", "deactivate", "nonexistent@example.com", "--confirm"])

        assert result.exit_code == 1
        assert "✗ User with email 'nonexistent@example.com' not found." in result.output


class TestCliInvites:
    """Test invite management CLI commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.mock_uow = Mock()
        self.mock_invite = UserInvite(
            invite_id=uuid.uuid4(),
            code="TEST-INVITE-123",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )

    @patch("opendlp.entrypoints.cli.invites.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.invites.generate_invite")
    def test_generate_invite_success(self, mock_generate_invite, mock_uow_class):
        """Test successful invite generation."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        mock_generate_invite.return_value = self.mock_invite

        result = self.runner.invoke(cli, ["invites", "generate", "--role", "user", "--expires-in", "168"])

        assert result.exit_code == 0
        assert "✓ Generated 1 invite(s) successfully:" in result.output
        assert "TEST-INVITE-123" in result.output

    @patch("opendlp.entrypoints.cli.invites.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.invites.list_invites")
    def test_list_invites_success(self, mock_list_invites, mock_uow_class):
        """Test successful invite listing."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        mock_list_invites.return_value = [self.mock_invite]

        result = self.runner.invoke(cli, ["invites", "list"])

        assert result.exit_code == 0
        assert "TEST-INVITE-123" in result.output
        assert "user" in result.output

    @patch("opendlp.entrypoints.cli.invites.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.invites.revoke_invite")
    def test_revoke_invite_success(self, mock_revoke_invite, mock_uow_class):
        """Test successful invite revocation."""
        mock_uow_class.return_value.__enter__.return_value = self.mock_uow
        self.mock_uow.user_invites.get_by_code.return_value = self.mock_invite

        result = self.runner.invoke(cli, ["invites", "revoke", "TEST-INVITE-123", "--confirm"])

        assert result.exit_code == 0
        assert "✓ Invite 'TEST-INVITE-123' has been revoked." in result.output
        mock_revoke_invite.assert_called_once()


class TestCliDatabase:
    """Test database CLI commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("opendlp.entrypoints.cli.database.command")
    @patch("opendlp.entrypoints.cli.database.Config")
    @patch("opendlp.entrypoints.cli.start_mappers")
    def test_init_db_success(self, mock_start_mappers, mock_config, mock_command):
        """Test successful database initialization."""
        result = self.runner.invoke(cli, ["database", "init", "--confirm"])

        assert result.exit_code == 0
        assert "✓ Database initialized successfully." in result.output
        mock_command.upgrade.assert_called_once()

    @patch("opendlp.entrypoints.cli.database.command")
    @patch("opendlp.entrypoints.cli.database.Config")
    def test_upgrade_db_success(self, mock_config, mock_command):
        """Test successful database upgrade."""
        result = self.runner.invoke(cli, ["database", "upgrade"])

        assert result.exit_code == 0
        assert "✓ Database upgraded to head." in result.output
        mock_command.upgrade.assert_called_once_with(mock_config.return_value, "head")

    @patch("opendlp.entrypoints.cli.database.SqlAlchemyUnitOfWork")
    @patch("opendlp.entrypoints.cli.start_mappers")
    def test_seed_db_success(self, mock_start_mappers, mock_uow_class):
        """Test successful database seeding."""
        mock_uow = Mock()
        mock_uow_class.return_value.__enter__.return_value = mock_uow
        mock_uow.users.list.return_value = []  # No existing users

        result = self.runner.invoke(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0
        assert "✓ Database seeded successfully with test data:" in result.output
        assert "admin@opendlp.example" in result.output

    @patch("opendlp.entrypoints.cli.database.SqlAlchemyUnitOfWork")
    def test_seed_db_already_seeded(self, mock_uow_class):
        """Test database seeding when data already exists."""
        mock_uow = Mock()
        mock_uow_class.return_value.__enter__.return_value = mock_uow
        mock_uow.users.list.return_value = [Mock()]  # Existing users

        result = self.runner.invoke(cli, ["database", "seed", "--confirm"])

        assert result.exit_code == 0
        assert "Database already contains users. Skipping seed." in result.output


class TestCliMain:
    """Test main CLI functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("opendlp.entrypoints.cli.start_mappers")
    @patch("opendlp.entrypoints.cli.get_config")
    def test_version_command(self, mock_get_config, mock_start_mappers):
        """Test version command."""
        result = self.runner.invoke(cli, ["version"])

        assert result.exit_code == 0
        assert "OpenDLP 0.1.0" in result.output

    @patch("opendlp.entrypoints.cli.start_mappers")
    @patch("opendlp.entrypoints.cli.get_config")
    def test_help_command(self, mock_get_config, mock_start_mappers):
        """Test help command."""
        result = self.runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "OpenDLP system administration CLI." in result.output
        assert "users" in result.output
        assert "invites" in result.output
        assert "database" in result.output
