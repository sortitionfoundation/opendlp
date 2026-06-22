"""ABOUTME: Unit tests for the templated-email context view-objects
ABOUTME: Covers best-effort name derivation and raw attribute passthrough"""

import uuid

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_context import (
    AssemblyContext,
    RespondentContext,
    build_context,
)
from opendlp.domain.respondents import Respondent


def test_first_last_name_derived_from_attribute_keys() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"First Name": "Sam", "Last Name": "Sample"})
    assert ctx.first_name == "Sam"
    assert ctx.last_name == "Sample"
    assert ctx.full_name == "Sam Sample"


def test_surname_key_supported() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"firstname": "Sam", "surname": "Sample"})
    assert ctx.last_name == "Sample"
    assert ctx.full_name == "Sam Sample"


def test_fullname_key_supported() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"full_name": "Sam Sample"})
    assert ctx.full_name == "Sam Sample"


def test_name_key_supported() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"name": "Sam Sample"})
    assert ctx.full_name == "Sam Sample"


def test_first_name_or_friend_fallback() -> None:
    with_name = RespondentContext(email="a@b.com", attributes={"firstname": "Sam"})
    without_name = RespondentContext(email="a@b.com", attributes={"age": "40"})
    assert with_name.first_name_or_friend == "Sam"
    assert without_name.first_name_or_friend == "Friend"


def test_raw_attributes_passthrough() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"age": "40"})
    assert ctx.attributes["age"] == "40"


def test_assembly_context_from_assembly() -> None:
    assembly = Assembly(title="My Assembly", question="Should we?", number_to_select=50)
    ctx = AssemblyContext.from_assembly(assembly)
    assert ctx.title == "My Assembly"
    assert ctx.question == "Should we?"
    assert ctx.number_to_select == 50
    assert ctx.first_assembly_date == ""


def test_respondent_context_from_respondent() -> None:
    respondent = Respondent(
        assembly_id=uuid.uuid4(),
        external_id="ext-1",
        email="person@example.com",
        attributes={"firstname": "Sam"},
    )
    ctx = RespondentContext.from_respondent(respondent)
    assert ctx.email == "person@example.com"
    assert ctx.first_name == "Sam"


def test_build_context_shape() -> None:
    assembly = AssemblyContext(title="A")
    respondent = RespondentContext(email="a@b.com", attributes={})
    context = build_context(assembly, respondent)
    assert context["assembly"] is assembly
    assert context["respondent"] is respondent
