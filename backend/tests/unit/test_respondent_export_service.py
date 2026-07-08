"""ABOUTME: Unit tests for the respondent export service
ABOUTME: Covers table building, status-filter resolution and the export orchestration"""

import csv
import uuid
from datetime import UTC, datetime
from io import StringIO

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition, RespondentFieldGroup
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentSourceType, RespondentStatus
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    UserNotFoundError,
)
from opendlp.service_layer.respondent_export_service import (
    STATUS_FILTER_ALL,
    STATUS_FILTER_SELECTED_OR_CONFIRMED,
    build_respondent_table,
    export_respondents,
    export_respondents_to_gsheet,
    get_respondent_gsheet_config,
    resolve_status_filter,
)
from tests.fakes import FakeGSheetExportTarget, FakeUnitOfWork


def _parse_export(target: CsvExportTarget) -> list[dict[str, str]]:
    content = target.getvalue().lstrip("﻿")
    return list(csv.DictReader(StringIO(content)))


class TestResolveStatusFilter:
    def test_empty_means_all(self):
        assert resolve_status_filter("") is None

    def test_all_token_means_all(self):
        assert resolve_status_filter(STATUS_FILTER_ALL) is None

    def test_selected_or_confirmed(self):
        assert resolve_status_filter(STATUS_FILTER_SELECTED_OR_CONFIRMED) == [
            RespondentStatus.SELECTED,
            RespondentStatus.CONFIRMED,
        ]

    def test_single_status(self):
        assert resolve_status_filter("POOL") == [RespondentStatus.POOL]

    def test_deleted_is_rejected(self):
        with pytest.raises(InvalidSelection):
            resolve_status_filter("DELETED")

    def test_invalid_value_is_rejected(self):
        with pytest.raises(InvalidSelection):
            resolve_status_filter("not-a-status")


def _field(field_key: str, *, is_fixed: bool = False, is_derived: bool = False) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=uuid.uuid4(),
        field_key=field_key,
        label=field_key.replace("_", " ").title(),
        group=RespondentFieldGroup.OTHER,
        sort_order=10,
        is_fixed=is_fixed,
        is_derived=is_derived,
        derived_from=["age_range"] if is_derived else None,
    )


class TestBuildRespondentTable:
    def test_id_column_header_and_value(self):
        respondent = Respondent(assembly_id=uuid.uuid4(), external_id="R1")
        table = build_respondent_table([respondent], [], id_column_header="nationbuilder_id")

        assert table.headers[0] == "nationbuilder_id"
        assert table.rows[0][0] == "R1"

    def test_schema_fields_in_order_fixed_and_attributes_and_derived(self):
        schema = [
            _field("email", is_fixed=True),
            _field("age_range"),
            _field("eligible", is_fixed=True),
            _field("derived_field", is_derived=True),
        ]
        respondent = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R1",
            email="alice@example.com",
            eligible=True,
            attributes={"age_range": "30-40", "derived_field": "middle"},
        )

        table = build_respondent_table([respondent], schema, id_column_header="external_id")

        assert table.headers[:5] == ["external_id", "email", "age_range", "eligible", "derived_field"]
        assert table.rows[0][:5] == ["R1", "alice@example.com", "30-40", "true", "middle"]

    def test_leftover_attribute_keys_appended_sorted(self):
        schema = [_field("age_range")]
        respondent = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R1",
            attributes={"age_range": "30-40", "zeta": "z", "alpha": "a"},
        )

        table = build_respondent_table([respondent], schema, id_column_header="external_id")

        # external_id, age_range (schema), then leftover alpha, zeta sorted, then internal cols
        assert table.headers[:4] == ["external_id", "age_range", "alpha", "zeta"]
        assert table.rows[0][:4] == ["R1", "30-40", "a", "z"]

    def test_internal_columns_appended_last(self):
        run_id = uuid.uuid4()
        created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        updated = datetime(2026, 6, 7, 8, 9, 10, tzinfo=UTC)
        respondent = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R1",
            selection_status=RespondentStatus.SELECTED,
            selection_run_id=run_id,
            source_type=RespondentSourceType.CSV_IMPORT,
            created_at=created,
            updated_at=updated,
        )

        table = build_respondent_table([respondent], [], id_column_header="external_id")

        assert table.headers[-5:] == [
            "selection_status",
            "source_type",
            "selection_run_id",
            "created_at",
            "updated_at",
        ]
        assert table.rows[0][-5:] == [
            "SELECTED",
            "CSV_IMPORT",
            str(run_id),
            created.isoformat(),
            updated.isoformat(),
        ]

    def test_bool_and_none_serialisation(self):
        schema = [
            _field("eligible", is_fixed=True),
            _field("can_attend", is_fixed=True),
            _field("consent", is_fixed=True),
            _field("stay_on_db", is_fixed=True),
        ]
        respondent = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R1",
            eligible=True,
            can_attend=False,
            consent=None,
            stay_on_db=None,
        )

        table = build_respondent_table([respondent], schema, id_column_header="external_id")

        assert table.rows[0][1:5] == ["true", "false", "", ""]

    def test_missing_attribute_value_is_blank(self):
        schema = [_field("age_range")]
        respondent = Respondent(assembly_id=uuid.uuid4(), external_id="R1", attributes={})

        table = build_respondent_table([respondent], schema, id_column_header="external_id")

        assert table.headers[1] == "age_range"
        assert table.rows[0][1] == ""

    def test_empty_selection_run_id_is_blank(self):
        respondent = Respondent(assembly_id=uuid.uuid4(), external_id="R1", selection_run_id=None)
        table = build_respondent_table([respondent], [], id_column_header="external_id")
        run_id_index = table.headers.index("selection_run_id")
        assert table.rows[0][run_id_index] == ""

    def test_row_length_matches_headers(self):
        schema = [_field("email", is_fixed=True), _field("age_range")]
        respondent = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R1",
            email="a@b.com",
            attributes={"age_range": "30-40", "extra": "e"},
        )
        table = build_respondent_table([respondent], schema, id_column_header="external_id")
        assert all(len(row) == len(table.headers) for row in table.rows)

    def test_rows_preserve_input_order(self):
        first = Respondent(assembly_id=uuid.uuid4(), external_id="R1")
        second = Respondent(assembly_id=uuid.uuid4(), external_id="R2")
        third = Respondent(assembly_id=uuid.uuid4(), external_id="R3")

        table = build_respondent_table([first, second, third], [], id_column_header="external_id")

        assert [row[0] for row in table.rows] == ["R1", "R2", "R3"]


def _seed(uow: FakeUnitOfWork, *, global_role: GlobalRole = GlobalRole.ADMIN) -> tuple[User, Assembly]:
    user = User(email="admin@example.com", global_role=global_role, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Test Assembly")
    uow.assemblies.add(assembly)
    return user, assembly


def _add_respondent(uow: FakeUnitOfWork, assembly: Assembly, external_id: str, status: RespondentStatus) -> None:
    uow.respondents.add(Respondent(assembly_id=assembly.id, external_id=external_id, selection_status=status))


class TestExportRespondents:
    def test_rows_ordered_oldest_first(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        uow.respondents.add(
            Respondent(assembly_id=assembly.id, external_id="R-new", created_at=datetime(2026, 3, 1, tzinfo=UTC))
        )
        uow.respondents.add(
            Respondent(assembly_id=assembly.id, external_id="R-old", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        )
        uow.respondents.add(
            Respondent(assembly_id=assembly.id, external_id="R-mid", created_at=datetime(2026, 2, 1, tzinfo=UTC))
        )

        target = CsvExportTarget()
        export_respondents(uow, user.id, assembly.id, status_filter=None, target=target)

        assert [row["external_id"] for row in _parse_export(target)] == ["R-old", "R-mid", "R-new"]

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly = _seed(uow)
        with pytest.raises(UserNotFoundError):
            export_respondents(uow, uuid.uuid4(), assembly.id, status_filter=None, target=CsvExportTarget())

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _ = _seed(uow)
        with pytest.raises(AssemblyNotFoundError):
            export_respondents(uow, user.id, uuid.uuid4(), status_filter=None, target=CsvExportTarget())

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow, global_role=GlobalRole.USER)
        with pytest.raises(InsufficientPermissions):
            export_respondents(uow, user.id, assembly.id, status_filter=None, target=CsvExportTarget())

    def test_all_exports_every_non_deleted_respondent(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R-pool", RespondentStatus.POOL)
        _add_respondent(uow, assembly, "R-selected", RespondentStatus.SELECTED)
        _add_respondent(uow, assembly, "R-deleted", RespondentStatus.DELETED)

        target = CsvExportTarget()
        export_respondents(uow, user.id, assembly.id, status_filter=None, target=target)

        ids = {row["external_id"] for row in _parse_export(target)}
        assert ids == {"R-pool", "R-selected"}

    def test_single_status_filter(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R-pool", RespondentStatus.POOL)
        _add_respondent(uow, assembly, "R-selected", RespondentStatus.SELECTED)

        target = CsvExportTarget()
        export_respondents(uow, user.id, assembly.id, status_filter=[RespondentStatus.SELECTED], target=target)

        ids = {row["external_id"] for row in _parse_export(target)}
        assert ids == {"R-selected"}

    def test_selected_or_confirmed_filter(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R-pool", RespondentStatus.POOL)
        _add_respondent(uow, assembly, "R-selected", RespondentStatus.SELECTED)
        _add_respondent(uow, assembly, "R-confirmed", RespondentStatus.CONFIRMED)

        target = CsvExportTarget()
        export_respondents(
            uow,
            user.id,
            assembly.id,
            status_filter=[RespondentStatus.SELECTED, RespondentStatus.CONFIRMED],
            target=target,
        )

        ids = {row["external_id"] for row in _parse_export(target)}
        assert ids == {"R-selected", "R-confirmed"}

    def test_uses_configured_id_column_header(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id, csv_id_column="nationbuilder_id")
        _add_respondent(uow, assembly, "R1", RespondentStatus.POOL)

        target = CsvExportTarget()
        export_respondents(uow, user.id, assembly.id, status_filter=None, target=target)

        rows = _parse_export(target)
        assert "nationbuilder_id" in rows[0]
        assert rows[0]["nationbuilder_id"] == "R1"


class TestExportToGSheetTarget:
    def test_records_single_write_with_table(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R1", RespondentStatus.POOL)
        _add_respondent(uow, assembly, "R2", RespondentStatus.SELECTED)

        target = FakeGSheetExportTarget()
        export_respondents(uow, user.id, assembly.id, status_filter=None, target=target, sheet_title="Respondents")

        assert len(target.writes) == 1
        title, table = target.writes[0]
        assert title == "Respondents"
        assert table.headers[0] == "external_id"
        exported_ids = {row[0] for row in table.rows}
        assert exported_ids == {"R1", "R2"}


_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


class TestExportRespondentsToGSheet:
    def test_writes_and_saves_config(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R1", RespondentStatus.SELECTED)

        target = FakeGSheetExportTarget()
        export_respondents_to_gsheet(
            uow,
            user.id,
            assembly.id,
            status_filter=[RespondentStatus.SELECTED],
            spreadsheet_url=_SHEET_URL,
            worksheet_name="Export tab",
            target=target,
        )

        assert len(target.writes) == 1
        title, table = target.writes[0]
        assert title == "Export tab"
        assert {row[0] for row in table.rows} == {"R1"}

        saved = get_respondent_gsheet_config(uow, user.id, assembly.id)
        assert saved is not None
        assert saved.url == _SHEET_URL
        assert saved.worksheet_name == "Export tab"

    def test_updates_existing_config(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R1", RespondentStatus.POOL)

        export_respondents_to_gsheet(
            uow,
            user.id,
            assembly.id,
            status_filter=None,
            spreadsheet_url=_SHEET_URL,
            worksheet_name="First",
            target=FakeGSheetExportTarget(),
        )
        export_respondents_to_gsheet(
            uow,
            user.id,
            assembly.id,
            status_filter=None,
            spreadsheet_url=_SHEET_URL,
            worksheet_name="Second",
            target=FakeGSheetExportTarget(),
        )

        saved = get_respondent_gsheet_config(uow, user.id, assembly.id)
        assert saved is not None
        assert saved.worksheet_name == "Second"
        # Still one config row for the assembly.
        assert len(list(uow.assembly_respondent_gsheets.all())) == 1

    def test_get_config_returns_none_when_unset(self):
        uow = FakeUnitOfWork()
        user, assembly = _seed(uow)
        assert get_respondent_gsheet_config(uow, user.id, assembly.id) is None
