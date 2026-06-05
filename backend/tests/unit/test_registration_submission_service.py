"""ABOUTME: Unit tests for the registration submission service
ABOUTME: Covers the validation-error and success paths for submit_registration_by_assembly_id"""

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.service_layer.registration_submission_service import (
    submit_registration_by_assembly_id,
)
from tests.fakes import FakeUnitOfWork


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
