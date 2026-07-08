"""ABOUTME: Unit tests for the respondent export service
ABOUTME: Covers table building, status-filter resolution and the export orchestration"""

import uuid
from datetime import UTC, datetime

from opendlp.domain.respondent_field_schema import RespondentFieldDefinition, RespondentFieldGroup
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentSourceType, RespondentStatus
from opendlp.service_layer.respondent_export_service import build_respondent_table


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
