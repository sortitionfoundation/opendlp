"""Unit tests for the dynamically-built edit-respondent form."""

import uuid

import pytest
from flask import Flask
from wtforms import IntegerField, RadioField, SelectField, StringField, TextAreaField

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.respondents import Respondent
from opendlp.entrypoints.edit_respondent_form import build_edit_respondent_form


def _field(field_key: str, field_type: FieldType = FieldType.TEXT, options=None) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=uuid.uuid4(),
        field_key=field_key,
        label=field_key.replace("_", " ").title(),
        group=RespondentFieldGroup.OTHER,
        sort_order=10,
        field_type=field_type,
        options=options,
    )


def _email_fixed() -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=uuid.uuid4(),
        field_key="email",
        label="Email",
        group=RespondentFieldGroup.NAME_AND_CONTACT,
        sort_order=10,
        is_fixed=True,
        field_type=FieldType.EMAIL,
    )


def _bool_or_none_fixed(key: str) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=uuid.uuid4(),
        field_key=key,
        label=key.replace("_", " ").title(),
        group=RespondentFieldGroup.ELIGIBILITY,
        sort_order=10,
        is_fixed=True,
        field_type=FieldType.BOOL_OR_NONE,
    )


def _respondent(email: str = "", attributes: dict | None = None, **flags) -> Respondent:
    return Respondent(
        assembly_id=uuid.uuid4(),
        external_id="R1",
        email=email,
        attributes=attributes or {},
        **flags,
    )


@pytest.fixture
def app_ctx():
    # Flask-WTF needs an app context for CSRF; use a minimal test app.
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "testkey"  # pragma: allowlist secret
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context():
        yield


class TestBuildFormFieldRendering:
    def test_text_renders_string_field(self, app_ctx):
        schema = [_field("note", FieldType.TEXT)]
        form, warnings = build_edit_respondent_form(schema, _respondent(attributes={"note": "n"}))
        assert isinstance(form["attr_note"], StringField)
        assert form["attr_note"].data == "n"
        assert warnings == []

    def test_longtext_renders_textarea(self, app_ctx):
        schema = [_field("bio", FieldType.LONGTEXT)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"bio": "long"}))
        assert isinstance(form["attr_bio"], TextAreaField)

    def test_integer_renders_integer_field(self, app_ctx):
        schema = [_field("age", FieldType.INTEGER)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"age": "42"}))
        assert isinstance(form["attr_age"], IntegerField)

    def test_bool_renders_two_radios(self, app_ctx):
        schema = [_field("attending", FieldType.BOOL)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"attending": "true"}))
        assert isinstance(form["attr_attending"], RadioField)
        values = [v for v, _label in form["attr_attending"].choices]
        assert values == ["true", "false"]

    def test_bool_or_none_renders_three_radios_with_not_set(self, app_ctx):
        schema = [_bool_or_none_fixed("eligible")]
        form, _ = build_edit_respondent_form(schema, _respondent(eligible=None))
        assert isinstance(form["eligible"], RadioField)
        values = [v for v, _label in form["eligible"].choices]
        assert values == ["true", "false", ""]
        assert form["eligible"].data == ""

    def test_bool_or_none_renders_yes_when_true(self, app_ctx):
        schema = [_bool_or_none_fixed("eligible")]
        form, _ = build_edit_respondent_form(schema, _respondent(eligible=True))
        assert form["eligible"].data == "true"

    def test_choice_radio_renders_radio_field(self, app_ctx):
        options = [ChoiceOption(value="a", help_text="A-help"), ChoiceOption(value="b")]
        schema = [_field("pick", FieldType.CHOICE_RADIO, options=options)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"pick": "a"}))
        assert isinstance(form["attr_pick"], RadioField)
        values = [v for v, _label in form["attr_pick"].choices]
        assert values == ["", "a", "b"]

    def test_choice_dropdown_renders_select_field_with_empty_first(self, app_ctx):
        options = [ChoiceOption(value="x"), ChoiceOption(value="y")]
        schema = [_field("zone", FieldType.CHOICE_DROPDOWN, options=options)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"zone": "x"}))
        assert isinstance(form["attr_zone"], SelectField)
        values = [v for v, _label in form["attr_zone"].choices]
        assert values[0] == ""
        assert set(values[1:]) == {"x", "y"}

    def test_choice_help_text_on_option_reachable(self, app_ctx):
        options = [ChoiceOption(value="a", help_text="first"), ChoiceOption(value="b")]
        schema = [_field("pick", FieldType.CHOICE_RADIO, options=options)]
        form, _ = build_edit_respondent_form(schema, _respondent(attributes={"pick": "a"}))
        # help_text is attached as a property on the form field for template use
        helps = form["attr_pick"].option_help_text
        assert helps == {"a": "first", "b": ""}

    def test_email_renders_string_field(self, app_ctx):
        schema = [_email_fixed()]
        form, _ = build_edit_respondent_form(schema, _respondent(email="a@b.com"))
        assert isinstance(form["email"], StringField)
        assert form["email"].data == "a@b.com"

    def test_comment_field_always_required(self, app_ctx):
        schema = [_email_fixed()]
        form, _ = build_edit_respondent_form(schema, _respondent(email="a@b.com"))
        assert isinstance(form["comment"], TextAreaField)


class TestBuildFormDrift:
    def test_current_value_not_in_options_merged_in(self, app_ctx):
        options = [ChoiceOption(value="a"), ChoiceOption(value="b")]
        schema = [_field("pick", FieldType.CHOICE_RADIO, options=options)]
        form, warnings = build_edit_respondent_form(schema, _respondent(attributes={"pick": "outsider"}))
        values = [v for v, _label in form["attr_pick"].choices]
        assert "outsider" in values
        assert any("outsider" in w for w in warnings)

    def test_no_warning_when_value_in_options(self, app_ctx):
        options = [ChoiceOption(value="a"), ChoiceOption(value="b")]
        schema = [_field("pick", FieldType.CHOICE_RADIO, options=options)]
        _form, warnings = build_edit_respondent_form(schema, _respondent(attributes={"pick": "a"}))
        assert warnings == []
