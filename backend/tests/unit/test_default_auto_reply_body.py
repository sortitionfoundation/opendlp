"""ABOUTME: Tests that the default auto-reply body stays something the visual email editor can open
ABOUTME: Ties the JS round-trip fixture to the code, and checks every translation uses the same markup"""

import re
from pathlib import Path

import pytest
from babel.messages.pofile import read_po

from opendlp.entrypoints.blueprints.backoffice_registration import _default_email_template_content

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND / "tests" / "fixtures" / "registration_auto_replies" / "default_auto_reply.html"
CATALOGUES = sorted((BACKEND / "translations").glob("*/LC_MESSAGES/messages.po"))


def _tags(html: str) -> list[str]:
    return re.findall(r"</?[a-z][^>]*>", html)


def test_fixture_matches_the_default_body() -> None:
    """The JS test proves the fixture opens in Visual mode, so it must be the real default."""
    assert FIXTURE.read_text().strip() == _default_email_template_content()["body_html"]


@pytest.mark.parametrize("catalogue", CATALOGUES, ids=lambda path: path.parts[-3])
def test_translated_default_body_uses_the_same_markup(catalogue: Path) -> None:
    """A translation that adds markup the editor lacks would open a new template in HTML mode."""
    english = _default_email_template_content()["body_html"]
    with catalogue.open("rb") as po_file:
        message = read_po(po_file).get(english)
    assert message is not None
    if message.string:
        assert _tags(message.string) == _tags(english)
