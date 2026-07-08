"""ABOUTME: Service layer for exporting respondents to CSV or Google Sheets
ABOUTME: Builds tabular data, resolves status filters, orchestrates the export"""

from opendlp.adapters.tabular_export import TabularData
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition
from opendlp.domain.respondents import Respondent

# Reserved top-level fields read directly off the Respondent rather than
# from its attributes dict. Kept in sync with the fixed schema fields.
_TOP_LEVEL_FIELD_KEYS = frozenset({"email", "eligible", "can_attend", "consent", "stay_on_db"})

# Internal-only columns appended after the schema and attribute columns.
_INTERNAL_COLUMNS = ("selection_status", "source_type", "selection_run_id", "created_at", "updated_at")


def _serialise_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _serialise_field(respondent: Respondent, field_key: str) -> str:
    """Serialise one schema field for a respondent as a CSV-ready string."""
    if field_key == "email":
        return respondent.email
    if field_key in _TOP_LEVEL_FIELD_KEYS:
        return _serialise_bool(getattr(respondent, field_key))
    value = respondent.attributes.get(field_key)
    return "" if value is None else str(value)


def _serialise_internal(respondent: Respondent, column: str) -> str:
    if column == "selection_status":
        return respondent.selection_status.value
    if column == "source_type":
        return respondent.source_type.value
    if column == "selection_run_id":
        return str(respondent.selection_run_id) if respondent.selection_run_id else ""
    if column == "created_at":
        return respondent.created_at.isoformat()
    return respondent.updated_at.isoformat()


def build_respondent_table(
    respondents: list[Respondent],
    schema: list[RespondentFieldDefinition],
    id_column_header: str,
) -> TabularData:
    """Turn respondents into a table: id column, schema fields, leftover
    attributes (sorted), then internal columns.

    Pure: takes already-fetched domain objects and the resolved id-column
    header, so it can be unit-tested without a UnitOfWork.
    """
    schema_keys = [f.field_key for f in schema]
    schema_key_set = set(schema_keys)

    leftover_keys: set[str] = set()
    for respondent in respondents:
        leftover_keys.update(k for k in respondent.attributes if k not in schema_key_set)
    leftover = sorted(leftover_keys)

    headers = [id_column_header, *schema_keys, *leftover, *_INTERNAL_COLUMNS]

    rows: list[list[str]] = []
    for respondent in respondents:
        row = [respondent.external_id]
        row.extend(_serialise_field(respondent, key) for key in schema_keys)
        row.extend(_serialise_field(respondent, key) for key in leftover)
        row.extend(_serialise_internal(respondent, column) for column in _INTERNAL_COLUMNS)
        rows.append(row)

    return TabularData(headers=headers, rows=rows)
