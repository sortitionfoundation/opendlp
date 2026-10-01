"""ABOUTME: Unit tests for the templated-email context view-objects
ABOUTME: Covers best-effort name derivation and raw attribute passthrough"""

import uuid

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_context import (
    AssemblyContext,
    RespondentContext,
    build_context,
    sample_respondent_context,
)
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
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


_ASSEMBLY_ID = uuid.uuid4()


def _field(key: str, ftype: FieldType = FieldType.TEXT, **kwargs) -> RespondentFieldDefinition:
    kwargs.setdefault("label", key.replace("_", " ").capitalize())
    kwargs.setdefault("group", RespondentFieldGroup.OTHER)
    kwargs.setdefault("sort_order", 10)
    return RespondentFieldDefinition(assembly_id=_ASSEMBLY_ID, field_key=key, field_type=ftype, **kwargs)


def test_sample_respondent_derives_a_recognisable_name() -> None:
    ctx = sample_respondent_context([_field("first_name"), _field("last_name")], "me@example.com")
    assert ctx.first_name == "Alex"
    assert ctx.last_name == "Example"
    assert ctx.full_name == "Alex Example"
    assert ctx.first_name_or_friend == "Alex"


def test_sample_respondent_email_is_the_recipient() -> None:
    ctx = sample_respondent_context([_field("contact_email", FieldType.EMAIL)], "me@example.com")
    assert ctx.email == "me@example.com"
    assert ctx.attributes["contact_email"] == "me@example.com"


def test_sample_values_by_field_type() -> None:
    fields = [
        _field("newsletter", FieldType.BOOL),
        _field("gender", FieldType.CHOICE_RADIO, options=[ChoiceOption("Female"), ChoiceOption("Male")]),
        _field("year_of_birth", FieldType.INTEGER),
        _field("available_from", FieldType.DATE),
        _field("postcode", FieldType.TEXT),
        _field("access_needs", FieldType.LONGTEXT),
    ]
    ctx = sample_respondent_context(fields, "me@example.com")
    assert ctx.attributes["newsletter"] is True
    assert ctx.attributes["gender"] == "Female"
    assert ctx.attributes["year_of_birth"] == 1985
    assert ctx.attributes["available_from"] == "1985-06-15"
    assert ctx.attributes["postcode"] == "[Postcode]"
    assert ctx.attributes["access_needs"] == "[Access needs]"


def test_sample_skips_fixed_and_off_page_fields_but_placeholders_derived() -> None:
    fields = [
        _field("email", FieldType.EMAIL, is_fixed=True),
        _field("internal_note", on_registration_page=FieldOnRegistrationPage.NO),
        _field(
            "age_bracket",
            is_derived=True,
            derived_from=["year_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={},
        ),
    ]
    ctx = sample_respondent_context(fields, "me@example.com")
    assert "email" not in ctx.attributes
    assert "internal_note" not in ctx.attributes
    assert ctx.attributes["age_bracket"] == "[Age bracket]"
