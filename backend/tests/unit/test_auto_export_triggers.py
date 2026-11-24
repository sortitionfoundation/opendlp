# ABOUTME: Checks that every service that changes the respondent export records the event that schedules one
# ABOUTME: Drives the real services over a FakeUnitOfWork and reads the events it collected

from collections.abc import Iterator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.events import RespondentsChanged, RespondentSchemaChanged
from opendlp.domain.registration_content_block import form_item_ref
from opendlp.domain.respondent_derivation import AgeBracket, AgeBracketRule
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, GSheetExportKind, RespondentStatus
from opendlp.service_layer import handlers, respondent_auto_export
from opendlp.service_layer.assembly_service import delete_respondents_for_assembly
from opendlp.service_layer.derivation_service import create_derived_field
from opendlp.service_layer.registration_submission_service import submit_registration_by_assembly_id
from opendlp.service_layer.respondent_field_schema_service import (
    ReconciliationDiff,
    add_choice_option,
    add_field,
    apply_reconciliation,
    delete_derived_field,
    delete_field,
    initialise_empty_schema,
    move_form_item,
    populate_schema_from_headers,
    remove_choice_option,
    rename_derived_field,
    reorder_form_items,
    update_choice_option,
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
    """An admin and an assembly with auto-export on."""
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
        sort_order=10,
        field_type=FieldType.CHOICE_RADIO,
        options=[ChoiceOption(value="Red"), ChoiceOption(value="Blue")],
    )
    uow.respondent_field_definitions.add(field)
    return field


class TestRespondentChangesTriggerAnExport:
    def test_registration_submission(self, uow):
        _user, assembly = _seed(uow, with_fixed_schema=True)

        result = submit_registration_by_assembly_id(
            uow,
            assembly_id=assembly.id,
            form_data={"email": "a@example.com", "consent": "true", "eligible": "true", "can_attend": "true"},
        )

        assert result.respondent is not None, result.field_errors
        assert RespondentsChanged(assembly.id) in uow.events

    def test_create_respondent(self, uow):
        user, assembly = _seed(uow)
        create_respondent(uow, user.id, assembly.id, "R1", {})
        assert RespondentsChanged(assembly.id) in uow.events

    def test_update_respondent(self, uow):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly)
        update_respondent(uow, user.id, assembly.id, respondent.id, "fix", email="b@example.com")
        assert RespondentsChanged(assembly.id) in uow.events

    def test_status_transition(self, uow):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly, RespondentStatus.SELECTED)
        transition_respondent_status(uow, user.id, assembly.id, respondent.id, RespondentStatus.CONFIRMED, "called")
        assert RespondentsChanged(assembly.id) in uow.events

    def test_delete_respondent(self, uow):
        user, assembly = _seed(uow)
        respondent = _add_respondent(uow, assembly)
        delete_respondent(uow, user.id, assembly.id, respondent.id, "asked to be removed")
        assert RespondentsChanged(assembly.id) in uow.events

    def test_csv_import(self, uow):
        user, assembly = _seed(uow)
        import_respondents_from_csv(uow=uow, user_id=user.id, assembly_id=assembly.id, csv_content="id,colour\n1,Red\n")
        assert RespondentsChanged(assembly.id) in uow.events

    def test_reset_selection_status(self, uow):
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, RespondentStatus.SELECTED)
        reset_selection_status(uow, user.id, assembly.id)
        assert RespondentsChanged(assembly.id) in uow.events

    def test_delete_all_respondents(self, uow):
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly)
        delete_respondents_for_assembly(uow, user.id, assembly.id)
        assert RespondentsChanged(assembly.id) in uow.events

    def test_derived_field_recompute(self, uow):
        user, assembly = _seed(uow)
        source = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="date_of_birth",
            label="Date of birth",
            sort_order=10,
            field_type=FieldType.DATE,
        )
        uow.respondent_field_definitions.add(source)
        rule = AgeBracketRule(as_of_date=date(2026, 1, 1), brackets=(AgeBracket(16, "16-29"), AgeBracket(30, "30+")))

        create_derived_field(
            uow, user.id, assembly.id, field_key="age", label="Age", source_field_key="date_of_birth", rule=rule
        )

        assert RespondentsChanged(assembly.id) in uow.events


class TestSchemaChangesTriggerAnExport:
    def test_add_field(self, uow):
        user, assembly = _seed(uow)
        add_field(uow, user.id, assembly.id, "colour")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_update_field(self, uow):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        update_field(uow, user.id, assembly.id, field.id, label="Favourite colour")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_reorder_form_items(self, uow):
        """The export's column order follows the questions list."""
        user, assembly = _seed(uow)
        first = _add_field(uow, assembly, "colour")
        second = _add_field(uow, assembly, "shape")
        reorder_form_items(uow, user.id, assembly.id, [form_item_ref(second), form_item_ref(first)])
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_move_form_item(self, uow):
        user, assembly = _seed(uow)
        _add_field(uow, assembly, "colour")
        second = _add_field(uow, assembly, "shape")
        move_form_item(uow, user.id, assembly.id, form_item_ref(second), "up")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_add_choice_option(self, uow):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        add_choice_option(uow, user.id, assembly.id, field.id, "Green")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_delete_field(self, uow):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        delete_field(uow, user.id, assembly.id, field.id)
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_populate_schema_from_headers(self, uow):
        _user, assembly = _seed(uow)
        populate_schema_from_headers(uow, assembly.id, ["id", "colour"], "id")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_initialise_empty_schema(self, uow):
        user, assembly = _seed(uow)
        initialise_empty_schema(uow, user.id, assembly.id)
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_update_choice_option(self, uow):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        update_choice_option(uow, user.id, assembly.id, field.id, "Red", "Crimson")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_remove_choice_option(self, uow):
        user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        remove_choice_option(uow, user.id, assembly.id, field.id, "Red")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_delete_derived_field(self, uow):
        """The field's values leave every respondent, so its column leaves the export."""
        _user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        delete_derived_field(uow, assembly.id, field)
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_rename_derived_field(self, uow):
        _user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        rename_derived_field(uow, assembly.id, field, "hue")
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_rename_derived_field_to_the_same_key_records_nothing(self, uow):
        _user, assembly = _seed(uow)
        field = _add_field(uow, assembly)
        rename_derived_field(uow, assembly.id, field, "colour")
        assert uow.events == []

    def test_apply_reconciliation(self, uow):
        _user, assembly = _seed(uow)
        apply_reconciliation(uow, assembly.id, ReconciliationDiff(assembly_id=assembly.id, new_keys=["shape"]))
        assert RespondentSchemaChanged(assembly.id) in uow.events

    def test_apply_reconciliation_with_nothing_new_records_nothing(self, uow):
        _user, assembly = _seed(uow)
        apply_reconciliation(uow, assembly.id, ReconciliationDiff(assembly_id=assembly.id))
        assert uow.events == []

    def test_moving_an_item_to_where_it_already_is_records_nothing(self, uow):
        user, assembly = _seed(uow)
        first = _add_field(uow, assembly, "colour")
        _add_field(uow, assembly, "shape")
        move_form_item(uow, user.id, assembly.id, form_item_ref(first), "top")
        assert uow.events == []


class TestRecordedEventsReachTheExport:
    """One service end to end with the application's handlers; the handler itself is tested on its own."""

    def test_a_respondent_change_schedules_the_export_once_committed(self, dispatch):
        with FakeUnitOfWork(event_handlers=handlers.EVENT_HANDLERS) as uow:
            user, assembly = _seed(uow)

            create_respondent(uow, user.id, assembly.id, "R1", {})

            dispatch.assert_not_called()
            uow.commit()

        dispatch.assert_called_once()

    def test_a_respondent_change_on_an_assembly_without_auto_export_schedules_nothing(self, dispatch):
        with FakeUnitOfWork(event_handlers=handlers.EVENT_HANDLERS) as uow:
            user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
            uow.users.add(user)
            assembly = Assembly(title="No auto export")
            uow.assemblies.add(assembly)

            create_respondent(uow, user.id, assembly.id, "R1", {})

        dispatch.assert_not_called()
