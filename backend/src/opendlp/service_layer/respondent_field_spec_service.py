"""ABOUTME: Builds the machine-readable respondent field spec for one assembly.
ABOUTME: Joins the field schema, its matching target values and the CSV column layout into a JSON-ready dict.

The spec answers the two questions a script outside the app has to ask before it
can write a respondent CSV: which columns does this assembly expect, and what
values are valid in each. See docs/respondent_field_spec.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.respondent_export_service import resolve_id_column_header
from opendlp.service_layer.respondent_field_schema_service import get_schema
from opendlp.service_layer.respondent_service import INTERNAL_IMPORT_SKIP_COLUMNS

if TYPE_CHECKING:
    import uuid

    from opendlp.domain.respondent_field_schema import RespondentFieldDefinition
    from opendlp.domain.targets import TargetCategory, TargetValue
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

# Bumped when the shape changes in a way a consumer has to notice. Consumers are
# outside this repo, so they cannot be updated in the same commit as the change.
SPEC_VERSION = 1


def _target_value_payload(value: TargetValue) -> dict[str, Any]:
    return {
        "value": value.value,
        "min": value.min,
        "max": value.max,
        "min_flex": value.min_flex,
        "max_flex": value.max_flex,
        "percentage_target": value.percentage_target,
        "description": value.description,
    }


def _target_category_payload(category: TargetCategory) -> dict[str, Any]:
    return {
        "name": category.name,
        "description": category.description,
        "values": [_target_value_payload(v) for v in category.values],
    }


def _field_payload(field: RespondentFieldDefinition, category: TargetCategory | None) -> dict[str, Any]:
    """Serialise one schema field, with the target values that constrain it.

    ``field_type`` is the *effective* type: for a fixed field the stored type is
    unreachable (the domain refuses to change it) and FIXED_FIELD_TYPES wins, so
    reporting the stored one would describe a field the app does not have.
    """
    return {
        "id": str(field.id),
        "field_key": field.field_key,
        "label": field.label,
        "group": field.group.value,
        "sort_order": field.sort_order,
        "is_fixed": field.is_fixed,
        "is_derived": field.is_derived,
        "derived_from": list(field.derived_from) if field.derived_from else None,
        "derivation_kind": field.derivation_kind,
        "field_type": field.effective_field_type.value,
        "options": [option.to_dict() for option in field.options] if field.options else None,
        "on_registration_page": field.on_registration_page.value,
        "target_values": [_target_value_payload(v) for v in category.values] if category is not None else None,
    }


def build_field_spec(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> dict[str, Any]:
    """Describe an assembly's respondent fields as a JSON-ready dict.

    Requires view permission on the assembly, which ``get_schema`` enforces.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    fields = get_schema(uow, user_id, assembly_id)

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    categories = list(uow.target_categories.get_by_assembly_id(assembly_id))

    # Selection hands target category names to sortition-algorithms as feature
    # names and respondent attribute keys as the people columns, and the library
    # pairs the two by exact string match. So the join here is exact as well: a
    # category that only matched loosely would find no column at selection time
    # either, and reporting it as matched here would hide that.
    categories_by_name = {category.name: category for category in categories}
    matched_names: set[str] = set()

    id_column = resolve_id_column_header(assembly)

    field_payloads: list[dict[str, Any]] = []
    columns = [id_column]
    for field in fields:
        category = categories_by_name.get(field.field_key)
        if category is not None:
            matched_names.add(category.name)
        field_payloads.append(_field_payload(field, category))
        # Derived fields are computed rather than collected, and the id column is
        # already the first column, so neither is a column to write a value into.
        if not field.is_derived and field.field_key != id_column:
            columns.append(field.field_key)

    return {
        "spec_version": SPEC_VERSION,
        "assembly": {
            "id": str(assembly.id),
            "title": assembly.title,
            "number_to_select": assembly.number_to_select,
        },
        "csv": {
            "id_column": id_column,
            "columns": columns,
            "internal_columns_ignored_on_import": list(INTERNAL_IMPORT_SKIP_COLUMNS),
        },
        "fields": field_payloads,
        "unmatched_target_categories": [
            _target_category_payload(category) for category in categories if category.name not in matched_names
        ],
    }
