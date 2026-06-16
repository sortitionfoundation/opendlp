"""ABOUTME: Unit tests for assembly reply-to and registration-page auto-reply links
ABOUTME: Covers reply-to validation and the nullable auto-reply template FK"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage


def test_assembly_defaults_have_empty_reply_to() -> None:
    assembly = Assembly(title="A")
    assert assembly.reply_to_name == ""
    assert assembly.reply_to_email == ""


def test_assembly_accepts_valid_reply_to() -> None:
    assembly = Assembly(title="A", reply_to_name="The Team", reply_to_email="team@example.com")
    assert assembly.reply_to_email == "team@example.com"


def test_assembly_rejects_invalid_reply_to_email() -> None:
    with pytest.raises(ValueError):
        Assembly(title="A", reply_to_email="not-an-email")


def test_set_reply_to_validates_and_updates() -> None:
    assembly = Assembly(title="A")
    assembly.set_reply_to(name="The Team", email="team@example.com")
    assert assembly.reply_to_name == "The Team"
    assert assembly.reply_to_email == "team@example.com"


def test_set_reply_to_rejects_invalid_email() -> None:
    assembly = Assembly(title="A")
    with pytest.raises(ValueError):
        assembly.set_reply_to(email="nope")


def test_assembly_detached_copy_preserves_reply_to() -> None:
    assembly = Assembly(title="A", reply_to_name="The Team", reply_to_email="team@example.com")
    copy = assembly.create_detached_copy()
    assert copy.reply_to_name == "The Team"
    assert copy.reply_to_email == "team@example.com"


def test_registration_page_auto_reply_template_id_defaults_none() -> None:
    page = RegistrationPage(assembly_id=uuid.uuid4())
    assert page.auto_reply_email_template_id is None


def test_registration_page_set_auto_reply_template() -> None:
    page = RegistrationPage(assembly_id=uuid.uuid4())
    template_id = uuid.uuid4()
    page.set_auto_reply_template(template_id)
    assert page.auto_reply_email_template_id == template_id
    page.set_auto_reply_template(None)
    assert page.auto_reply_email_template_id is None


def test_registration_page_detached_copy_preserves_auto_reply() -> None:
    template_id = uuid.uuid4()
    page = RegistrationPage(assembly_id=uuid.uuid4(), auto_reply_email_template_id=template_id)
    copy = page.create_detached_copy()
    assert copy.auto_reply_email_template_id == template_id
