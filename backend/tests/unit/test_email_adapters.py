"""ABOUTME: Unit tests for email adapter implementations
ABOUTME: Tests console logging, SMTP message construction, and address parsing"""

import logging
import smtplib
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from opendlp.adapters.email import ConsoleEmailAdapter, EmailAdapter, SMTPEmailAdapter


class TestEmailAdapter:
    """Tests for EmailAdapter base class static methods."""

    def test_parse_address_with_string(self) -> None:
        """Test parsing a plain email string."""
        result = EmailAdapter._parse_address("test@example.com")
        assert result == ("", "test@example.com")

    def test_parse_address_with_tuple(self) -> None:
        """Test parsing an email tuple with display name."""
        result = EmailAdapter._parse_address(("John Doe", "john@example.com"))
        assert result == ("John Doe", "john@example.com")

    def test_format_address_with_string(self) -> None:
        """Test formatting a plain email string."""
        result = EmailAdapter._format_address("test@example.com")
        assert result == "test@example.com"

    def test_format_address_with_tuple(self) -> None:
        """Test formatting an email tuple with display name."""
        result = EmailAdapter._format_address(("John Doe", "john@example.com"))
        assert result == "John Doe <john@example.com>"


class TestConsoleEmailAdapter:
    """Tests for ConsoleEmailAdapter.

    The console adapter is dev-only and intentionally shows the real recipient
    address. It writes to sys.stdout (not the logging system), so it neither
    triggers the email-in-log audit nor gets scrubbed by the redaction processor.
    """

    def test_send_email_writes_to_output_stream(self) -> None:
        """Test that ConsoleEmailAdapter writes email details to its output stream."""
        stream = StringIO()
        adapter = ConsoleEmailAdapter(output_stream=stream)

        result = adapter.send_email(
            to=["recipient@example.com"],
            subject="Test Subject",
            text_body="This is the email body",
        )

        out = stream.getvalue()
        assert result is True
        assert "EMAIL (Console):" in out
        assert "To: recipient@example.com" in out
        assert "Subject: Test Subject" in out
        assert "This is the email body" in out
        assert "Has HTML: No" in out

    def test_send_email_defaults_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that ConsoleEmailAdapter writes to stdout when no stream is given."""
        adapter = ConsoleEmailAdapter()

        result = adapter.send_email(
            to=["recipient@example.com"],
            subject="Test Subject",
            text_body="This is the email body",
        )

        out = capsys.readouterr().out
        assert result is True
        assert "EMAIL (Console):" in out
        assert "To: recipient@example.com" in out

    def test_send_email_does_not_use_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """The recipient address must not be routed through the logging system."""
        adapter = ConsoleEmailAdapter()

        with caplog.at_level(logging.DEBUG):
            adapter.send_email(
                to=["recipient@example.com"],
                subject="Subject",
                text_body="Body",
            )

        assert "recipient@example.com" not in caplog.text

    def test_send_email_writes_reply_to(self) -> None:
        """ConsoleEmailAdapter includes the reply-to address when provided."""
        stream = StringIO()
        adapter = ConsoleEmailAdapter(output_stream=stream)

        adapter.send_email(
            to=["recipient@example.com"],
            subject="Subject",
            text_body="Body",
            reply_to="team@example.com",
        )

        assert "Reply-To: team@example.com" in stream.getvalue()

    def test_send_email_with_html(self) -> None:
        """Test console output with HTML body."""
        stream = StringIO()
        adapter = ConsoleEmailAdapter(output_stream=stream)

        result = adapter.send_email(
            to=["recipient@example.com"],
            subject="Test Subject",
            text_body="Plain text",
            html_body="<p>HTML content</p>",
        )

        assert result is True
        assert "Has HTML: Yes" in stream.getvalue()

    def test_send_email_with_multiple_recipients(self) -> None:
        """Test console output with multiple recipients."""
        stream = StringIO()
        adapter = ConsoleEmailAdapter(output_stream=stream)

        result = adapter.send_email(
            to=["user1@example.com", ("User Two", "user2@example.com")],
            subject="Test",
            text_body="Body",
        )

        out = stream.getvalue()
        assert result is True
        assert "user1@example.com" in out
        assert "User Two <user2@example.com>" in out

    def test_send_email_truncates_long_body(self) -> None:
        """Test that long email bodies are truncated in console output."""
        stream = StringIO()
        adapter = ConsoleEmailAdapter(output_stream=stream)
        long_body = "A" * 500

        adapter.send_email(
            to=["recipient@example.com"],
            subject="Test",
            text_body=long_body,
        )

        out = stream.getvalue()
        assert "..." in out
        # Should show first 200 chars plus "..."
        assert long_body[:200] in out
        assert len(long_body) > 200  # Verify we actually had a long body


class TestSMTPEmailAdapter:
    """Tests for SMTPEmailAdapter."""

    def test_send_email_success(self) -> None:
        """Test successful email sending via SMTP."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="password",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
            default_from_name="Sender Name",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test Subject",
                text_body="Plain text body",
            )

            assert result is True
            mock_smtp.assert_called_once_with("smtp.example.com", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user@example.com", "password")
            mock_server.sendmail.assert_called_once()

    def test_send_email_with_html_body(self) -> None:
        """Test sending email with both plain text and HTML."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Plain text",
                html_body="<p>HTML content</p>",
            )

            assert result is True
            # Verify sendmail was called with message containing both parts
            call_args = mock_server.sendmail.call_args
            message_str = call_args[0][2]
            assert "Plain text" in message_str
            assert "<p>HTML content</p>" in message_str

    def test_send_email_sets_reply_to_header(self) -> None:
        """Reply-To header is set when reply_to is provided."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Plain text",
                reply_to=("The Team", "team@example.com"),
            )

            message_str = mock_server.sendmail.call_args[0][2]
            assert "Reply-To: The Team <team@example.com>" in message_str

    def test_send_email_without_reply_to_has_no_header(self) -> None:
        """No Reply-To header is added when reply_to is omitted."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            adapter.send_email(to=["recipient@example.com"], subject="Test", text_body="Plain text")

            message_str = mock_server.sendmail.call_args[0][2]
            assert "Reply-To:" not in message_str

    def test_send_email_with_multiple_recipients(self) -> None:
        """Test sending email to multiple recipients."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["user1@example.com", ("User Two", "user2@example.com")],
                subject="Test",
                text_body="Body",
            )

            assert result is True
            # Verify sendmail was called with correct recipient list
            call_args = mock_server.sendmail.call_args
            _from_addr, to_addrs, _ = call_args[0]
            assert to_addrs == ["user1@example.com", "user2@example.com"]

    def test_send_email_with_custom_from_address(self) -> None:
        """Test overriding the default from address."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="default@example.com",
            default_from_name="Default Name",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Body",
                from_email=("Custom Name", "custom@example.com"),
            )

            assert result is True
            # Verify the custom from address was used
            call_args = mock_server.sendmail.call_args
            from_addr, _, message = call_args[0]
            assert from_addr == "custom@example.com"
            assert "Custom Name <custom@example.com>" in message

    def test_send_email_without_tls(self) -> None:
        """Test sending email without TLS."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=25,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=False,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Body",
            )

            assert result is True
            mock_server.starttls.assert_not_called()

    def test_send_email_smtp_exception(self, capture_json_handler: StringIO) -> None:
        """Test error handling when SMTP raises an exception."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value.sendmail.side_effect = smtplib.SMTPException("SMTP error")

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Body",
            )

            assert result is False
            assert "SMTP error sending email" in capture_json_handler.getvalue()

    def test_send_email_general_exception(self, capture_json_handler: StringIO) -> None:
        """Test error handling for unexpected exceptions."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",  # pragma: allowlist secret
            use_tls=True,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value.sendmail.side_effect = ValueError("Unexpected error")

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Body",
            )

            assert result is False
            assert "Unexpected error sending email" in capture_json_handler.getvalue()

    def test_send_email_without_authentication(self) -> None:
        """Test sending email without authentication (empty username/password)."""
        adapter = SMTPEmailAdapter(
            host="smtp.example.com",
            port=25,
            username="",
            password="",  # pragma: allowlist secret
            use_tls=False,
            default_from_email="sender@example.com",
            default_from_name="",
        )

        with patch("opendlp.adapters.email.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = adapter.send_email(
                to=["recipient@example.com"],
                subject="Test",
                text_body="Body",
            )

            assert result is True
            # Verify login was not called when username/password are empty
            mock_server.login.assert_not_called()
