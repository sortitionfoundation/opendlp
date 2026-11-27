"""ABOUTME: Email adapter that records the emails it is asked to send
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

from typing import Any

from opendlp.adapters.email import EmailAdapter


class FakeEmailAdapter(EmailAdapter):
    """In-memory email adapter that records what would have been sent.

    Lets tests assert on the recipient, subject and body of a real rendered
    email without an SMTP server or a console full of PII.
    """

    def __init__(self, succeed: bool = True, sender: str = "", error: Exception | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        # When False, send_email records nothing and reports failure, so tests
        # can drive the "we could not email them" path.
        self.succeed = succeed
        self.sender = sender
        # When set, send_email raises it, as an adapter that hits an unexpected
        # error (a dropped SMTP connection) would.
        self.error = error

    def sender_email(self) -> str:
        return self.sender

    def send_email(
        self,
        to: list[str | tuple[str, str]],
        subject: str,
        text_body: str,
        html_body: str | None = None,
        from_email: str | tuple[str, str] | None = None,
        reply_to: str | tuple[str, str] | None = None,
        on_behalf_of: str = "",
    ) -> bool:
        if self.error is not None:
            raise self.error
        if not self.succeed:
            return False

        self.sent.append({
            "to": to,
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
            "from_email": from_email,
            "reply_to": reply_to,
            "on_behalf_of": on_behalf_of,
        })
        return True
