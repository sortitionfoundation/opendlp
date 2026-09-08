"""ABOUTME: Service layer for derived respondent fields — CRUD, dispatch, recompute and mapping upload.
ABOUTME: Owns everything that turns a derivation rule plus source data into stored attribute values.

The rule classes live in ``domain/respondent_derivation`` and know nothing about
storage; this module is where a derived ``RespondentFieldDefinition`` is
created, its rule dispatched against a respondent's source values, the whole
pool recomputed, and a large mapping's lookup table uploaded. The four
respondent write paths call ``apply_derivations``; everything else here exists
to serve the (future) config UI."""

import csv
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from io import StringIO
from typing import Any

from opendlp.domain.respondent_derivation import (
    AgeBracketRule,
    DerivationRule,
    LargeMappingRule,
    SmallMappingRule,
    normalise_lookup_key,
    output_options,
    rule_from_field,
)
from opendlp.domain.respondent_field_schema import (
    CHOICE_TYPES,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
)
from opendlp.domain.respondents import Respondent, normalise_field_name
from opendlp.domain.validators import parse_date_text
from opendlp.domain.value_objects import SelectionRunStatus
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import lazy_gettext as _l

# A real Scotland table held 220k+ full postcodes; the cap stays well clear of
# real invite lists while keeping a request-cycle upload sane.
MAX_MAPPING_ROWS = 500_000

# How many distinct unmatched source values a recompute report carries.
UNMATCHED_SAMPLE_SIZE = 20

# Which source field types each rule class can derive from.
_COMPATIBLE_SOURCE_TYPES: dict[type, frozenset[FieldType]] = {
    AgeBracketRule: frozenset({FieldType.DATE, FieldType.INTEGER}),
    SmallMappingRule: CHOICE_TYPES,
    LargeMappingRule: frozenset({FieldType.TEXT}),
}

_DERIVATION_TYPE_FOR_RULE: dict[type, DerivationType] = {
    AgeBracketRule: DerivationType.AGE_BRACKET,
    SmallMappingRule: DerivationType.SMALL_MAPPING,
    LargeMappingRule: DerivationType.LARGE_MAPPING,
}


@dataclass(frozen=True)
class RecomputeReport:
    """What a pool recompute did, in the numbers an organiser needs to act on."""

    total: int
    changed: int
    fell_back: int
    unmatched_sample: list[str] = dataclass_field(default_factory=list)
    completed_selection_runs: int = 0


@dataclass(frozen=True)
class MappingUploadReport:
    """What a large-mapping CSV upload stored, and what it had to flag."""

    row_count: int
    duplicate_keys: list[str] = dataclass_field(default_factory=list)
    unknown_outputs: dict[str, int] = dataclass_field(default_factory=dict)
    used_positional_headers: bool = False


@dataclass(frozen=True)
class DerivationOutcome:
    """Per-respondent record of what apply_derivations decided.

    ``derived`` holds every derived field's final value. ``overwrote_supplied``
    lists fields where a differing supplied value was replaced by a derived one
    (the import path reports these); ``kept_supplied`` lists fields where the
    source could not derive and the supplied value survived.
    ``fallback_sources`` maps a field that fell back to the raw source value
    that failed to derive — the recompute report's unmatched sample.
    """

    derived: dict[str, str] = dataclass_field(default_factory=dict)
    overwrote_supplied: list[str] = dataclass_field(default_factory=list)
    kept_supplied: list[str] = dataclass_field(default_factory=list)
    fallback_sources: dict[str, str] = dataclass_field(default_factory=dict)


def _ensure_manage_permission(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> None:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="configure derived fields",
            required_role="assembly-manager or admin",
        )


def _get_derived_field(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, field_id: uuid.UUID
) -> RespondentFieldDefinition:
    field: RespondentFieldDefinition | None = uow.respondent_field_definitions.get(field_id)
    if field is None or field.assembly_id != assembly_id:
        raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
    if not field.is_derived:
        raise FieldDefinitionConflictError(_l("Field '%(key)s' is not a derived field", key=field.field_key))
    return field


def _validate_source(source: RespondentFieldDefinition | None, source_field_key: str, rule: DerivationRule) -> None:
    if source is None:
        raise FieldDefinitionConflictError(
            _l("Source field '%(key)s' does not exist in this assembly", key=source_field_key)
        )
    if source.is_derived:
        raise FieldDefinitionConflictError(
            _l("Source field '%(key)s' is itself derived — derivations cannot chain", key=source.field_key)
        )
    compatible = _COMPATIBLE_SOURCE_TYPES[type(rule)]
    if source.effective_field_type not in compatible:
        raise FieldDefinitionConflictError(
            _l(
                "A '%(source_type)s' field cannot be derived from with this rule — it needs one of: %(allowed)s",
                source_type=source.effective_field_type.value,
                allowed=", ".join(sorted(t.value for t in compatible)),
            )
        )


def _options_for(rule: DerivationRule, output_values: list[str] | None) -> "list[Any]":
    try:
        return output_options(rule, declared_outputs=output_values)
    except ValueError as exc:
        raise FieldDefinitionConflictError(
            _l("A large mapping needs its output values declared when the field is created")
        ) from exc


def derivations_depending_on(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, field_key: str
) -> list[RespondentFieldDefinition]:
    """The derived fields whose ``derived_from`` names this field.

    Returns live (session-attached) objects, because the schema mutators use
    them to rewrite mapping keys in step with a source-option rename.
    """
    return [
        f
        for f in uow.respondent_field_definitions.list_by_assembly(assembly_id)
        if f.is_derived and f.derived_from and field_key in f.derived_from
    ]


def load_mapping_lookups(
    uow: AbstractUnitOfWork, field_defs: list[RespondentFieldDefinition]
) -> dict[uuid.UUID, Callable[[str], str | None]]:
    """Per-field lookup callables for every large-mapping derived field.

    Each callable hits the mapping-entries index for its one key — right for
    single-respondent writes. Batch paths (import, recompute) should prefetch
    with ``get_many`` instead of calling these once per row.
    """
    lookups: dict[uuid.UUID, Callable[[str], str | None]] = {}
    for field in field_defs:
        if field.is_derived and field.derivation_type == DerivationType.LARGE_MAPPING:
            lookups[field.id] = _single_key_lookup(uow, field.id)
    return lookups


def _single_key_lookup(uow: AbstractUnitOfWork, field_id: uuid.UUID) -> Callable[[str], str | None]:
    def lookup(key: str) -> str | None:
        entries = uow.respondent_field_mapping_entries.get_many(field_id, [key])
        return entries[0].output_value if entries else None

    return lookup


def _prefetched_lookup(
    uow: AbstractUnitOfWork, field: RespondentFieldDefinition, raw_source_values: list[str]
) -> Callable[[str], str | None]:
    """One get_many for a whole batch's distinct keys, closed over an in-memory dict."""
    distinct = sorted({key for value in raw_source_values if (key := normalise_lookup_key(str(value)))})
    entries = uow.respondent_field_mapping_entries.get_many(field.id, distinct)
    table = {entry.lookup_key: entry.output_value for entry in entries}
    return table.get


def derived_value_for(
    field_def: RespondentFieldDefinition,
    rule: DerivationRule,
    source_def: RespondentFieldDefinition,
    source_value: Any,
    lookup: Callable[[str], str | None] | None = None,
) -> str:
    """Pure dispatch: one derived value from one source value.

    The three rules take genuinely different inputs, so this is the one place
    that reads the field metadata and calls the right method with the right
    arguments. Unusable input comes back as the rule's fallback.
    """
    text = str(source_value).strip() if source_value is not None else ""
    match rule:
        case AgeBracketRule():
            if source_def.effective_field_type == FieldType.DATE:
                born = parse_date_text(text)
                return rule.derive_from_date(born) if born is not None else rule.fallback
            try:
                year = int(text)
            except ValueError:
                return rule.fallback
            return rule.derive_from_year(year)
        case SmallMappingRule():
            return rule.derive(text)
        case LargeMappingRule():
            if lookup is None:
                raise ValueError(f"large mapping derivation for '{field_def.field_key}' requires a lookup")
            return rule.derive(text, lookup)
    raise ValueError(f"Unknown rule type: {type(rule)}")  # pragma: no cover


def apply_derivations(
    respondent: Respondent,
    field_defs: list[RespondentFieldDefinition],
    lookups: Mapping[uuid.UUID, Callable[[str], str | None]],
    keep_supplied_on_fallback: bool = True,
) -> DerivationOutcome:
    """Compute every derived field in ``field_defs`` and write the results into
    ``respondent.attributes``. Pure in-memory: no repository, no commit.

    Precedence per derived field: a real derived value always wins; when
    derivation can only offer its fallback and a supplied value is already
    present, the supplied value survives (``keep_supplied_on_fallback=True``,
    the import/write behaviour) or is overwritten (recompute behaviour).
    """
    defs_by_key = {f.field_key: f for f in field_defs}
    outcome = DerivationOutcome()
    updates: dict[str, str] = {}

    for field in field_defs:
        if not field.is_derived:
            continue
        if field.derivation_type is None or field.derivation_config is None or not field.derived_from:
            continue  # a malformed row must not break a registration submission
        derived, fallback, raw_text = _resolve_derived_value(respondent, field, defs_by_key, lookups)

        existing = str(respondent.attributes.get(field.field_key, "") or "")
        if derived == fallback and keep_supplied_on_fallback and existing and existing != fallback:
            outcome.kept_supplied.append(field.field_key)
            outcome.derived[field.field_key] = existing
            continue
        if derived == fallback and raw_text:
            outcome.fallback_sources[field.field_key] = raw_text
        if existing and existing != derived:
            outcome.overwrote_supplied.append(field.field_key)
        outcome.derived[field.field_key] = derived
        if existing != derived or field.field_key not in respondent.attributes:
            updates[field.field_key] = derived

    if updates:
        # Reassign rather than mutate so the JSON column change is detected.
        respondent.attributes = {**respondent.attributes, **updates}
    return outcome


def _resolve_derived_value(
    respondent: Respondent,
    field: RespondentFieldDefinition,
    defs_by_key: Mapping[str, RespondentFieldDefinition],
    lookups: Mapping[uuid.UUID, Callable[[str], str | None]],
) -> tuple[str, str, str]:
    """Returns (derived value, the rule's fallback, the raw source text)."""
    assert field.derivation_type is not None
    assert field.derivation_config is not None
    rule = rule_from_field(field.derivation_type, field.derivation_config)
    source_def = defs_by_key.get((field.derived_from or [""])[0])
    if source_def is None:
        return rule.fallback, rule.fallback, ""
    raw_source = _source_value(respondent, source_def)
    derived = derived_value_for(field, rule, source_def, raw_source, lookup=lookups.get(field.id))
    raw_text = str(raw_source).strip() if raw_source is not None else ""
    return derived, rule.fallback, raw_text


def _source_value(respondent: Respondent, source_def: RespondentFieldDefinition) -> Any:
    if source_def.is_fixed:
        return getattr(respondent, source_def.field_key, "")
    return respondent.attributes.get(source_def.field_key, "")


def create_derived_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_key: str,
    label: str,
    source_field_key: str,
    rule: DerivationRule,
    output_values: list[str] | None = None,
    group: RespondentFieldGroup = RespondentFieldGroup.DERIVED,
) -> tuple[RespondentFieldDefinition, RecomputeReport]:
    """Create a derived field and recompute the existing pool.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    field_key = field_key.strip()
    if not field_key:
        raise FieldDefinitionConflictError(_l("Field key cannot be empty"))
    if uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, field_key) is not None:
        raise FieldDefinitionConflictError(_l("Field '%(key)s' already exists in this assembly", key=field_key))

    source = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, source_field_key)
    _validate_source(source, source_field_key, rule)
    assert source is not None  # _validate_source raised otherwise

    schema = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    next_sort_order = max((f.sort_order for f in schema if f.group == group), default=0) + 10
    field = RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=field_key,
        label=label,
        group=group,
        sort_order=next_sort_order,
        is_derived=True,
        derived_from=[source.field_key],
        derivation_type=_DERIVATION_TYPE_FOR_RULE[type(rule)],
        derivation_config=rule.to_config(),
        field_type=FieldType.CHOICE_RADIO,
        options=_options_for(rule, output_values),
    )
    uow.respondent_field_definitions.add(field)

    report = _recompute(uow, assembly_id, field, [*schema, field])
    return field.create_detached_copy(), report


def update_derivation(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
    rule: DerivationRule,
    output_values: list[str] | None = None,
) -> tuple[RespondentFieldDefinition, RecomputeReport]:
    """Replace a derived field's rule, regenerate its options, and recompute the pool.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    field = _get_derived_field(uow, assembly_id, field_id)
    source = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, (field.derived_from or [""])[0])
    _validate_source(source, (field.derived_from or [""])[0], rule)

    if isinstance(rule, LargeMappingRule) and output_values is None:
        # A rule edit (say, a new fallback) should not force re-declaring the
        # output list — the existing options carry it.
        options = list(field.options or [])
    else:
        options = _options_for(rule, output_values)
    field.set_derivation(
        derivation_type=_DERIVATION_TYPE_FOR_RULE[type(rule)],
        derivation_config=rule.to_config(),
        options=options,
    )

    schema = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    report = _recompute(uow, assembly_id, field, schema)
    return field.create_detached_copy(), report


def recompute_derived_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
) -> RecomputeReport:
    """Recompute one derived field across the whole pool (DELETED respondents excluded).

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    field = _get_derived_field(uow, assembly_id, field_id)
    schema = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    return _recompute(uow, assembly_id, field, schema)


def _recompute(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    derived_field: RespondentFieldDefinition,
    schema: list[RespondentFieldDefinition],
) -> RecomputeReport:
    """Apply one derived field to every non-deleted respondent, counting as it goes.

    No comment is written on the respondents — derivation is not a user edit —
    and the derivation always wins over whatever value the attribute held.
    """
    respondents = uow.respondents.get_by_assembly_id(assembly_id)
    assert derived_field.derivation_type is not None
    assert derived_field.derivation_config is not None
    rule = rule_from_field(derived_field.derivation_type, derived_field.derivation_config)
    source_key = (derived_field.derived_from or [""])[0]

    lookups: dict[uuid.UUID, Callable[[str], str | None]] = {}
    if derived_field.derivation_type == DerivationType.LARGE_MAPPING:
        raw_values = [str(r.attributes.get(source_key, "")) for r in respondents]
        lookups[derived_field.id] = _prefetched_lookup(uow, derived_field, raw_values)

    # Only this field is recomputed; other derived fields keep their values.
    field_defs = [f for f in schema if not f.is_derived or f.id == derived_field.id]

    changed = 0
    fell_back = 0
    unmatched: list[str] = []
    for respondent in respondents:
        old = respondent.attributes.get(derived_field.field_key)
        outcome = apply_derivations(respondent, field_defs, lookups, keep_supplied_on_fallback=False)
        new = respondent.attributes.get(derived_field.field_key)
        if new != old:
            changed += 1
        if new == rule.fallback:
            fell_back += 1
            raw = outcome.fallback_sources.get(derived_field.field_key, "")
            if raw and raw not in unmatched and len(unmatched) < UNMATCHED_SAMPLE_SIZE:
                unmatched.append(raw)

    completed_runs = sum(
        1
        for record in uow.selection_run_records.get_by_assembly_id(assembly_id)
        if record.status == SelectionRunStatus.COMPLETED
    )
    return RecomputeReport(
        total=len(respondents),
        changed=changed,
        fell_back=fell_back,
        unmatched_sample=unmatched,
        completed_selection_runs=completed_runs,
    )


def upload_large_mapping(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
    csv_content: str,
    allow_new_outputs: bool = False,
) -> MappingUploadReport:
    """Replace a large-mapping field's lookup table from a two-column CSV.

    Headers are matched by normalised name against the source and derived field
    keys; unmatched headers fall back to positional (first = input, second =
    output). The uploaded content is parsed in memory and never persisted —
    only the normalised rows are stored.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    field = _get_derived_field(uow, assembly_id, field_id)
    if field.derivation_type != DerivationType.LARGE_MAPPING:
        raise FieldDefinitionConflictError(_l("Field '%(key)s' does not use a large mapping", key=field.field_key))

    rows = [row for row in csv.reader(StringIO(csv_content)) if any(cell.strip() for cell in row)]
    if not rows:
        raise FieldDefinitionConflictError(_l("The mapping file is empty"))
    headers, data_rows = rows[0], rows[1:]
    if len(data_rows) > MAX_MAPPING_ROWS:
        raise FieldDefinitionConflictError(
            _l(
                "The mapping file has too many rows (%(count)s) — the limit is %(limit)s",
                count=len(data_rows),
                limit=MAX_MAPPING_ROWS,
            )
        )

    in_idx, out_idx, used_positional = _resolve_mapping_columns(headers, field)

    table: dict[str, str] = {}
    duplicates: set[str] = set()
    output_counts: Counter[str] = Counter()
    for row in data_rows:
        if len(row) <= max(in_idx, out_idx):
            continue
        key = normalise_lookup_key(row[in_idx])
        value = row[out_idx].strip()
        if not key or not value:
            continue
        if key in table:
            duplicates.add(key)
        table[key] = value
        output_counts[value] += 1

    allowed_outputs = {option.value for option in field.options or []}
    unknown_outputs = {value: count for value, count in output_counts.items() if value not in allowed_outputs}
    if unknown_outputs and not allow_new_outputs:
        raise FieldDefinitionConflictError(
            _l(
                "The mapping file contains output values not in the field's options: %(values)s",
                values=", ".join(sorted(unknown_outputs)),
            )
        )
    if unknown_outputs:
        _extend_output_options(field, sorted(unknown_outputs))

    uow.respondent_field_mapping_entries.delete_all_for_field(field.id)
    uow.respondent_field_mapping_entries.bulk_add([
        RespondentFieldMappingEntry(field_id=field.id, lookup_key=key, output_value=value)
        for key, value in table.items()
    ])
    return MappingUploadReport(
        row_count=len(table),
        duplicate_keys=sorted(duplicates)[:UNMATCHED_SAMPLE_SIZE],
        unknown_outputs=unknown_outputs,
        used_positional_headers=used_positional,
    )


def _resolve_mapping_columns(headers: list[str], field: RespondentFieldDefinition) -> tuple[int, int, bool]:
    """Match CSV headers to the source/derived field keys, else fall back to position."""
    normalised = [normalise_field_name(header) for header in headers]
    source_key = normalise_field_name((field.derived_from or [""])[0])
    derived_key = normalise_field_name(field.field_key)
    if source_key in normalised and derived_key in normalised:
        return normalised.index(source_key), normalised.index(derived_key), False
    if len(headers) < 2:
        raise FieldDefinitionConflictError(_l("The mapping file needs two columns: input value and output value"))
    return 0, 1, True


def _extend_output_options(field: RespondentFieldDefinition, new_values: list[str]) -> None:
    """Append newly-seen output values to the field's options, keeping the fallback last."""
    assert field.derivation_type is not None
    assert field.derivation_config is not None
    rule = rule_from_field(field.derivation_type, field.derivation_config)
    existing = [option.value for option in field.options or []]
    values = [value for value in existing if value != rule.fallback] + new_values + [rule.fallback]
    field.set_derivation(
        derivation_type=field.derivation_type,
        derivation_config=field.derivation_config,
        options=output_options(
            rule, declared_outputs=[value for value in dict.fromkeys(values) if value != rule.fallback]
        ),
    )
