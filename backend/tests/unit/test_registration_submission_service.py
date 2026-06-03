"""ABOUTME: Unit tests for the registration submission service
ABOUTME: Covers per-type field validators and the field-error result path"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.service_layer.registration_submission_service import (
    _validate_bool,
    _validate_choice,
    _validate_email,
    _validate_integer,
    submit_registration_by_assembly_id,
)
from tests.fakes import FakeUnitOfWork


class TestValidateBool:
    @pytest.mark.parametrize("raw", ["yes", "true", "1", "Yes", "TRUE"])
    def test_accepts_truthy_values(self, raw):
        cleaned, error = _validate_bool(raw, allow_none=False)
        assert cleaned is True
        assert error is None

    @pytest.mark.parametrize("raw", ["no", "false", "0", "No"])
    def test_accepts_falsy_values(self, raw):
        cleaned, error = _validate_bool(raw, allow_none=False)
        assert cleaned is False
        assert error is None

    def test_blank_returns_none_when_allowed(self):
        cleaned, error = _validate_bool("", allow_none=True)
        assert cleaned is None
        assert error is None


class TestValidateEmail:
    def test_accepts_email_with_at(self):
        cleaned, error = _validate_email("alice@example.com")
        assert cleaned == "alice@example.com"
        assert error is None

    def test_missing_at_returns_error(self):
        cleaned, error = _validate_email("not-an-email")
        assert cleaned is None
        assert error is not None
        assert "valid email" in error.lower()


class TestValidateChoice:
    def test_accepts_value_in_set(self):
        cleaned, error = _validate_choice("blue", {"blue", "green"})
        assert cleaned == "blue"
        assert error is None

    def test_accepts_value_when_no_constraints(self):
        cleaned, error = _validate_choice("anything", None)
        assert cleaned == "anything"
        assert error is None

    def test_unknown_value_returns_error(self):
        cleaned, error = _validate_choice("purple", {"blue", "green"})
        assert cleaned is None
        assert error is not None
        assert "valid option" in error.lower()


class TestValidateInteger:
    def test_accepts_integer_string(self):
        cleaned, error = _validate_integer("42")
        assert cleaned == 42
        assert error is None


def _populated_uow_with_text_field() -> tuple[FakeUnitOfWork, Assembly]:
    uow = FakeUnitOfWork()
    admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(admin)
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    uow.respondent_field_definitions.add(
        RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="name",
            label="Name",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=100,
            field_type=FieldType.TEXT,
        )
    )
    return uow, assembly


class TestSubmitRegistrationValidationErrors:
    """The validation-error result path: invalid form data yields field errors,
    no respondent is created, and the submitted values are echoed back so the
    re-rendered form can preserve what the user typed."""

    def test_missing_required_field_returns_field_errors(self):
        uow, assembly = _populated_uow_with_text_field()

        result = submit_registration_by_assembly_id(
            uow,
            assembly_id=assembly.id,
            form_data={},
            is_test=True,
        )

        assert result.respondent is None
        assert "name" in result.field_errors
        assert result.is_test is True
        assert result.form_errors == []
        assert not uow.committed

    def test_invalid_field_value_echoed_back_in_values(self):
        uow, assembly = _populated_uow_with_text_field()

        result = submit_registration_by_assembly_id(
            uow,
            assembly_id=assembly.id,
            form_data={"name": ""},
            is_test=True,
        )

        assert result.respondent is None
        assert result.values == {"name": ""}
        assert "name" in result.field_errors
