"""ABOUTME: Integration tests for email system including bootstrap factory
ABOUTME: Tests email adapter configuration and multiple recipient handling"""

import os
from unittest.mock import patch

import pytest

from opendlp.adapters.email import ConsoleEmailAdapter, SMTPEmailAdapter
from opendlp.bootstrap import get_email_adapter
from opendlp.config import InvalidConfig


class TestEmailAdapterBootstrap:
    """Integration tests for email adapter bootstrap."""

    def test_get_console_adapter_by_default(self) -> None:
        """Test that console adapter is returned by default in development."""
        with patch.dict(os.environ, {"FLASK_ENV": "development", "EMAIL_ADAPTER": "console"}, clear=False):
            adapter = get_email_adapter()
            assert isinstance(adapter, ConsoleEmailAdapter)

    def test_get_smtp_adapter_when_configured(self) -> None:
        """Test that SMTP adapter is returned when configured."""
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "development",
                "EMAIL_ADAPTER": "smtp",
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "user@example.com",
                "SMTP_PASSWORD": "password",  # pragma: allowlist secret
                "SMTP_USE_TLS": "true",
                "SMTP_FROM_EMAIL": "sender@example.com",
                "SMTP_FROM_NAME": "Sender Name",
            },
            clear=False,
        ):
            adapter = get_email_adapter()
            assert isinstance(adapter, SMTPEmailAdapter)
            assert adapter.host == "smtp.example.com"
            assert adapter.port == 587
            assert adapter.username == "user@example.com"
            assert adapter.use_tls is True
            assert adapter.default_from_email == "sender@example.com"

    def test_get_email_adapter_unknown_type(self) -> None:
        """Test that ValueError is raised for unknown adapter type."""
        with (
            patch.dict(os.environ, {"FLASK_ENV": "development", "EMAIL_ADAPTER": "unknown"}, clear=False),
            pytest.raises(ValueError, match="Unknown email adapter type"),
        ):
            get_email_adapter()

    def test_production_config_requires_email_adapter(self) -> None:
        """Test that production config requires EMAIL_ADAPTER to be set."""
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "SECRET_KEY": "production-secret-key",  # pragma: allowlist secret
                "REDIS_HOST": "redis",
            },
            clear=True,
        ):
            # Remove EMAIL_ADAPTER if it exists
            os.environ.pop("EMAIL_ADAPTER", None)

            with pytest.raises(InvalidConfig, match="EMAIL_ADAPTER must be set in production"):
                get_email_adapter()


class TestEmailAdapterSendingIntegration:
    """Integration tests for sending emails with multiple recipients."""

    def test_console_adapter_with_multiple_recipients(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test sending email to multiple recipients via console adapter."""
        import logging

        adapter = ConsoleEmailAdapter()

        with caplog.at_level(logging.INFO):
            result = adapter.send_email(
                to=[
                    "user1@example.com",
                    ("User Two", "user2@example.com"),
                    ("User Three", "user3@example.com"),
                ],
                subject="Multi-recipient test",
                text_body="This is a test email sent to multiple recipients",
                html_body="<p>This is a test email sent to multiple recipients</p>",
            )

        assert result is True
        assert "user1@example.com" in caplog.text
        assert "User Two <user2@example.com>" in caplog.text
        assert "User Three <user3@example.com>" in caplog.text
        assert "Multi-recipient test" in caplog.text
        assert "Has HTML: Yes" in caplog.text

    def test_smtp_adapter_configuration_from_env(self) -> None:
        """Test SMTP adapter configuration is correctly loaded from environment."""
        with patch.dict(
            os.environ,
            {
                "EMAIL_ADAPTER": "smtp",
                "SMTP_HOST": "mail.example.com",
                "SMTP_PORT": "465",
                "SMTP_USERNAME": "admin@example.com",
                "SMTP_PASSWORD": "secret123",  # pragma: allowlist secret
                "SMTP_USE_TLS": "false",
                "SMTP_FROM_EMAIL": "noreply@example.com",
                "SMTP_FROM_NAME": "Example Service",
            },
            clear=False,
        ):
            adapter = get_email_adapter()

            assert isinstance(adapter, SMTPEmailAdapter)
            assert adapter.host == "mail.example.com"
            assert adapter.port == 465
            assert adapter.username == "admin@example.com"
            assert adapter.password == "secret123"  # pragma: allowlist secret
            assert adapter.use_tls is False
            assert adapter.default_from_email == "noreply@example.com"
            assert adapter.default_from_name == "Example Service"

    def test_email_adapter_case_insensitive(self) -> None:
        """Test that EMAIL_ADAPTER value is case-insensitive."""
        # Test uppercase
        with patch.dict(os.environ, {"EMAIL_ADAPTER": "CONSOLE"}, clear=False):
            adapter = get_email_adapter()
            assert isinstance(adapter, ConsoleEmailAdapter)

        # Test mixed case
        with patch.dict(os.environ, {"EMAIL_ADAPTER": "Console"}, clear=False):
            adapter = get_email_adapter()
            assert isinstance(adapter, ConsoleEmailAdapter)

    def test_email_adapter_whitespace_handling(self) -> None:
        """Test that EMAIL_ADAPTER value handles whitespace correctly."""
        with patch.dict(os.environ, {"EMAIL_ADAPTER": "  console  "}, clear=False):
            adapter = get_email_adapter()
            assert isinstance(adapter, ConsoleEmailAdapter)
