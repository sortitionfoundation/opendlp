# ABOUTME: Checks that every service that changes the respondent export asks for an auto-export
# ABOUTME: Drives the real services over a FakeUnitOfWork with a fake Redis and a patched Celery dispatch

from collections.abc import Iterator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.respondent_derivation import AgeBracket, AgeBracketRule
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, GSheetExportKind, RespondentStatus
from opendlp.service_layer import respondent_auto_export
from opendlp.service_layer.assembly_service import delete_respondents_for_assembly
from opendlp.service_layer.derivation_service import create_derived_field
from opendlp.service_layer.registration_submission_service import submit_registration_by_assembly_id
from opendlp.service_layer.respondent_field_schema_service import (
    add_choice_option,
    add_field,
    delete_field,
    initialise_empty_schema,
    reorder_group,
    update_field,
)
from opendlp.service_layer.respondent_service import (
    create_respondent,
    delete_respondent,
    import_respondents_from_csv,
    reset_selection_status,
    transition_respondent_status,
    update_respondent,
)
from tests.fakes import FakeRedis, FakeUnitOfWork

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
_DISPATCH = "opendlp.service_layer.respondent_auto_export.tasks.auto_export_respondents.apply_async"


@pytest.fixture
def dispatch() -> Iterator[MagicMock]:
    """The Celery dispatch, patched out, with Redis replaced by a fresh in-memory fake."""
    with (
        patch.object(respondent_auto_export, "_get_redis", return_value=FakeRedis()),
        patch(_DISPATCH) as mock,
    ):
        yield mock


def _seed(uow: FakeUnitOfWork, *, with_fixed_schema: bool = False) -> tuple[User, Assembly]:
    """An admin and an assembly with auto-export on; the schema is seeded before the config so it fires nothing."""
    user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Test Assembly")
    uow.assemblies.add(assembly)
    if with_fixed_schema:
        initialise_empty_schema(uow, user.id, assembly.id)
    uow.assembly_export_gsheets.add(
        AssemblyExportGSheet(
            assembly_id=assembly.id,
            export_kind=GSheetExportKind.RESPONDENTS,
            url=_SHEET_URL,
            auto_export=True,
        )
    )
    return user, assembly


def _add_respondent(uow: FakeUnitOfWork, assembly: Assembly, status=RespondentStatus.POOL) -> Respondent:
    respondent = Respondent(assembly_id=assembly.id, external_id="R1", selection_status=status)
    uow.respondents.add(respondent)
    return respondent


def _add_field(uow: FakeUnitOfWork, assembly: Assembly, field_key: str = "colour") -> RespondentFieldDefinition:
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=field_key,
        label=field_key.capitalize(),
        group=RespondentFieldGroup.ABOUT_YOU,
        sort_order=10,
        field_type=FieldType.CHOICE_RADIO,
        options=[ChoiceOption(value="Red"), ChoiceOption(value="Blue")],
    )
    uow.respondent_field_definitions.add(field)
    return field


class TestRespondentChangesTriggerAnExport:
    def test_registration_submission(self, uow, dispatch):
        _user, assembly = _seed(uow, with_fixed_schema=True)

        result = submit_registration_by_assembly_id(
            uow,
            assembly_id=assembly.id,
            form_data={"email": "a@example.com", "consent": "true", "eligible": "true", "can_attend": "true"},
        )

        assert result.respondent is not None, result.field_errors
        dispatch.assert_called_once()

    def test_create_respondent(self, uow, dispatch):
        user, assembly = _seed(uow)
        create_respondent(uow, user.id, assembly.id, "R1", {})
        dispatch.assert_called_once()

    def test_update_respondent(self, uow, dispatch):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly)
        update_respondent(uow, user.id, assembly.id, respondent.id, "fix", email="b@example.com")
        dispatch.assert_called_once()

    def test_status_transition(self, uow, dispatch):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly, RespondentStatus.SELECTED)
        transition_respondent_status(uow, user.id, assembly.id, respondent.id, RespondentStatus.CONFIRMED, "called")
        dispatch.assert_called_once()

    def test_delete_respondent(self, uow, dispatch):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly)
        delete_respondent(uow, user.id, assembly.id, respondent.id, "asked to be removed")
        dispatch.assert_called_once()

    def test_csv_import(self, uow, dispatch):
        user, assembly = _seed(uow)
        import_respondents_from_csv(uow=uow, user_id=user.id, assembly_id=assembly.id, csv_content="id,colour\n1,Red\n")
        assert dispatch.call_count >= 1

    def test_reset_selection_status(self, uow, dispatch):
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, RespondentStatus.SELECTED)
        reset_selection_status(uow, user.id, assembly.id)
        dispatch.assert_called_once()

    def test_delete_all_respondents(self, uow, dispatch):
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly)
        delete_respondents_for_assembly(uow, user.id, assembly.id)
        dispatch.assert_called_once()

    def test_derived_field_recompute(self, uow, dispatch):
        user, assembly = _seed(uow)
        source = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="date_of_birth",
            label="Date of birth",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.DATE,
        )
        uow.respondent_field_definitions.add(source)
        rule = AgeBracketRule(as_of_date=date(2026, 1, 1), brackets=(AgeBracket(16, "16-29"), AgeBracket(30, "30+")))

        create_derived_field(
            uow, user.id, assembly.id, field_key="age", label="Age", source_field_key="date_of_birth", rule=rule
        )

        dispatch.assert_called_once()


class TestSchemaChangesTriggerAnExport:
    def test_add_field(self, uow, dispatch):
        user, assembly = _seed(uow)
        add_field(uow, user.id, assembly.id, "colour")
        dispatch.assert_called_once()

    def test_update_field(self, uow, dispatch):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        update_field(uow, user.id, assembly.id, field.id, label="Favourite colour")
        dispatch.assert_called_once()

    def test_reorder_group(self, uow, dispatch):
        user, assembly = _seed(uow)
        first = _add_field(uow, assembly, "colour")
        second = _add_field(uow, assembly, "shape")
        reorder_group(uow, user.id, assembly.id, RespondentFieldGroup.ABOUT_YOU, [second.id, first.id])
        dispatch.assert_called_once()

    def test_add_choice_option(self, uow, dispatch):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        add_choice_option(uow, user.id, assembly.id, field.id, "Green")
        dispatch.assert_called_once()

    def test_delete_field(self, uow, dispatch):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        delete_field(uow, user.id, assembly.id, field.id)
        dispatch.assert_called_once()


class TestNothingFiresWhenAutoExportIsOff:
    def test_respondent_change_on_a_plain_assembly(self, uow, dispatch):
        user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(user)
        assembly = Assembly(title="No auto export")
        uow.assemblies.add(assembly)

        create_respondent(uow, user.id, assembly.id, "R1", {})

        dispatch.assert_not_called()
