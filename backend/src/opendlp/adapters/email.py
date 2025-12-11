"""ABOUTME: Email adapter implementations for sending emails via various backends
ABOUTME: Supports SMTP, console logging, and future transactional email services"""

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)


class EmailAdapter(ABC):
    """Abstract base class for email sending adapters."""

    @abstractmethod
    def send_email(
        self,
        to: list[str | tuple[str, str]],
        subject: str,
        text_body: str,
        html_body: str | None = None,
        from_email: str | tuple[str, str] | None = None,
    ) -> bool:
        """Send an email to one or more recipients.

        Args:
            to: List of recipient email addresses. Can be strings ('email@example.com')
                or tuples (('Display Name', 'email@example.com'))
            subject: Email subject line
            text_body: Plain text version of the email body
            html_body: Optional HTML version of the email body
            from_email: Optional override for the sender address. Uses default if None.

        Returns:
            True if email sent successfully, False otherwise
        """
        pass

    @staticmethod
    def _parse_address(addr: str | tuple[str, str]) -> tuple[str, str]:
        """Parse an email address into (name, email) tuple.

        Args:
            addr: Email address as string or tuple

        Returns:
            Tuple of (display_name, email_address). If input is a string,
            display_name will be empty string.
        """
        if isinstance(addr, tuple):
            return addr
        return ("", addr)

    @staticmethod
    def _format_address(addr: str | tuple[str, str]) -> str:
        """Format an email address for use in email headers.

        Args:
            addr: Email address as string or tuple

        Returns:
            Formatted address string suitable for email headers
        """
        name, email = EmailAdapter._parse_address(addr)
        if name:
            return formataddr((name, email))
        return email


class ConsoleEmailAdapter(EmailAdapter):
    """Email adapter that logs emails to console instead of sending them.

    Useful for development and testing environments.
    """

    def send_email(
        self,
        to: list[str | tuple[str, str]],
        subject: str,
        text_body: str,
        html_body: str | None = None,
        from_email: str | tuple[str, str] | None = None,
    ) -> bool:
        """Log email details to console.

        Args:
            to: List of recipient email addresses
            subject: Email subject line
            text_body: Plain text version of the email body
            html_body: Optional HTML version of the email body
            from_email: Optional override for the sender address

        Returns:
            Always returns True
        """
        from_addr = self._format_address(from_email) if from_email else "noreply@opendlp.local"
        to_addrs = [self._format_address(addr) for addr in to]

        # Truncate text body for logging
        text_preview = text_body[:400] + ("..." if len(text_body) > 400 else "")
        has_html = "Yes" if html_body else "No"

        logger.info(
            "EMAIL (Console):\n"
            f"  From: {from_addr}\n"
            f"  To: {', '.join(to_addrs)}\n"
            f"  Subject: {subject}\n"
            f"  Has HTML: {has_html}\n"
            f"  Text Body Preview: {text_preview}"
        )

        return True


class SMTPEmailAdapter(EmailAdapter):
    """Email adapter that sends emails via SMTP."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool = True,
        default_from_email: str = "",
        default_from_name: str = "",
    ):
        """Initialize SMTP email adapter.

        Args:
            host: SMTP server hostname
            port: SMTP server port
            username: SMTP authentication username
            password: SMTP authentication password
            use_tls: Whether to use TLS encryption (default: True)
            default_from_email: Default sender email address
            default_from_name: Default sender display name
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.default_from_email = default_from_email
        self.default_from_name = default_from_name

    def send_email(
        self,
        to: list[str | tuple[str, str]],
        subject: str,
        text_body: str,
        html_body: str | None = None,
        from_email: str | tuple[str, str] | None = None,
    ) -> bool:
        """Send an email via SMTP.

        Args:
            to: List of recipient email addresses
            subject: Email subject line
            text_body: Plain text version of the email body
            html_body: Optional HTML version of the email body
            from_email: Optional override for the sender address

        Returns:
            True if email sent successfully, False if an error occurred
        """
        try:
            # Determine sender address
            if from_email:
                from_name, from_addr = self._parse_address(from_email)
            else:
                from_name = self.default_from_name
                from_addr = self.default_from_email

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._format_address((from_name, from_addr))
            msg["To"] = ", ".join([self._format_address(addr) for addr in to])

            # Attach plain text part
            msg.attach(MIMEText(text_body, "plain"))

            # Attach HTML part if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Extract email addresses for SMTP (no display names)
            to_addresses = [self._parse_address(addr)[1] for addr in to]

            # Send email
            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(from_addr, to_addresses, msg.as_string())

            logger.info(f"Email sent successfully to {len(to_addresses)} recipient(s)")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False
