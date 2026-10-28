"""ABOUTME: Unit tests for the templated-email context view-objects
ABOUTME: Covers best-effort name derivation and raw attribute passthrough"""

import uuid
from datetime import date

import pytest

from opendlp.domain import email_context as email_context_module
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


def test_first_name_falls_back_to_the_whole_name() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"Name": "Kovács Anna"})
    assert ctx.first_name == "Kovács Anna"
    assert ctx.first_name_or_friend == "Kovács Anna"
    assert ctx.last_name == ""


def test_first_name_field_wins_over_name() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"name": "Sam Sample", "first_name": "Sammy"})
    assert ctx.first_name == "Sammy"
    assert ctx.full_name == "Sam Sample"


def test_last_name_alone_is_not_a_first_name() -> None:
    ctx = RespondentContext(email="a@b.com", attributes={"surname": "Sample"})
    assert ctx.first_name == ""
    assert ctx.full_name == "Sample"


def test_first_name_or_friend_fallback() -> None:
    with_name = RespondentContext(email="a@b.com", attributes={"firstname": "Sam"})
    without_name = RespondentContext(email="a@b.com", attributes={"age": "40"})
    assert with_name.first_name_or_friend == "Sam"
    assert without_name.first_name_or_friend == "Friend"


def test_first_name_or_friend_fallback_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_context_module, "_", lambda message: {"Friend": "Résztvevő"}.get(message, message))
    without_name = RespondentContext(email="a@b.com", attributes={"age": "40"})
    assert without_name.first_name_or_friend == "Résztvevő"


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
    assert ctx.first_assembly_date_text == ""


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("en", "November 14, 2026"), ("en_GB", "14 November 2026"), ("hu", "2026. november 14.")],
)
def test_first_assembly_date_is_written_out_in_the_readers_language(locale: str, expected: str) -> None:
    assembly = Assembly(title="A", first_assembly_date=date(2026, 11, 14))
    ctx = AssemblyContext.from_assembly(assembly, locale=locale)
    assert ctx.first_assembly_date == "2026-11-14"
    assert ctx.first_assembly_date_text == expected


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


def test_project_is_the_same_object_as_assembly() -> None:
    """Saved emails say assembly; the editor now offers project. Both must work."""
    assembly = AssemblyContext(title="A")
    context = build_context(assembly, RespondentContext(email="a@b.com", attributes={}))
    assert context["project"] is context["assembly"]


def test_first_event_date_reads_the_same_as_first_assembly_date() -> None:
    assembly = Assembly(title="My Project", number_to_select=5, first_assembly_date=date(2026, 11, 14))
    ctx = AssemblyContext.from_assembly(assembly)
    assert ctx.first_event_date == ctx.first_assembly_date == "2026-11-14"
    assert ctx.first_event_date_text == ctx.first_assembly_date_text


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


def test_sample_respondent_supports_full_name_fields() -> None:
    ctx = sample_respondent_context([_field("full_name")], "me@example.com")
    assert ctx.attributes["full_name"] == "Alex Example"
    assert ctx.full_name == "Alex Example"


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


def test_sample_skips_off_page_fields_but_fixed_kept_and_placeholders_derived() -> None:
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
    assert "email" in ctx.attributes
    assert "internal_note" not in ctx.attributes
    assert ctx.attributes["age_bracket"] == "[Age bracket]"


def test_sample_respondent_falls_back_to_canonical_person_without_a_schema() -> None:
    ctx = sample_respondent_context([], "me@example.com")
    assert ctx.email == "me@example.com"
    assert ctx.full_name == "Alex Example"
