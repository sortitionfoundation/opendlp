"""ABOUTME: Service layer wiring target categories to the respondent fields that feed them.
ABOUTME: Configure a target's data source, report per-target status, adopt/re-sync/unlink linked fields.

This is the orchestration behind the "target data sources" step: one save
creates (or reuses) the source registration field and the derived field for a
target, links the feeding field via ``target_category_id``, and recomputes the
pool. ``derivation_service`` keeps owning the derivation mechanics; this module
only composes it with the field schema and the target categories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from opendlp.domain.respondent_derivation import (
    AgeBracketRule,
    DerivationRule,
    LargeMappingRule,
    SmallMappingRule,
    rule_from_field,
)
from opendlp.domain.respondent_field_schema import (
    CHOICE_TYPES,
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)
from opendlp.service_layer.constants import SORT_ORDER_STEP
from opendlp.service_layer.derivation_service import (
    RecomputeReport,
    compatible_source_fields,
    create_derived_field,
    update_derivation,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    InsufficientPermissions,
    NotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.respondent_field_schema_heuristics import classify_field_key
from opendlp.service_layer.respondent_field_schema_service import delete_derived_field
from opendlp.service_layer.respondent_service import get_respondent_attribute_columns
from opendlp.translations import lazy_gettext as _l

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from opendlp.domain.targets import TargetCategory
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

_MAX_RADIO_OPTIONS = 6

_DERIVATION_TYPE_FOR_RULE: dict[type, DerivationType] = {
    AgeBracketRule: DerivationType.AGE_BRACKET,
    SmallMappingRule: DerivationType.SMALL_MAPPING,
    LargeMappingRule: DerivationType.LARGE_MAPPING,
}


@dataclass(frozen=True)
class SourceFieldSpec:
    """Create-or-reuse for the registration field a target's data comes from.

    With ``reuse_field_id`` set, the named existing field is used and every
    other attribute is ignored. Otherwise a new field is created from
    ``field_key`` (label defaults to the humanised key, group to the
    ``classify_field_key`` heuristics). ``options`` is only meaningful when
    ``field_type`` is a choice type — the small-mapping source case.
    """

    reuse_field_id: uuid.UUID | None = None
    field_key: str = ""
    label: str = ""
    help_text: str = ""
    group: RespondentFieldGroup | None = None
    field_type: FieldType = FieldType.TEXT
    options: tuple[ChoiceOption, ...] | None = None


@dataclass(frozen=True)
class ExactCopySpec:
    """The registration field is an exact copy of the target's values.

    ``source`` may name an existing choice field to reuse; with no reuse id a
    new choice field is created carrying the target's name verbatim and its
    values as options.
    """

    source: SourceFieldSpec = SourceFieldSpec()


@dataclass(frozen=True)
class AgeBracketSpec:
    """Derive the target's brackets from a date-of-birth (or year) source field."""

    rule: AgeBracketRule
    source: SourceFieldSpec = SourceFieldSpec()


@dataclass(frozen=True)
class SmallMappingSpec:
    """Derive the target's values by mapping a choice field with more options."""

    rule: SmallMappingRule
    source: SourceFieldSpec = SourceFieldSpec()


@dataclass(frozen=True)
class LargeMappingSpec:
    """Derive the target's values via an uploaded lookup table (e.g. postcode)."""

    rule: LargeMappingRule
    source: SourceFieldSpec = SourceFieldSpec()


TargetSourceSpec = ExactCopySpec | AgeBracketSpec | SmallMappingSpec | LargeMappingSpec


class TargetSourceState(Enum):
    """Where one target category's data comes from, as the checklist reports it."""

    LINKED_EXACT = "linked_exact"
    LINKED_DERIVED = "linked_derived"
    MATCHED_NOT_LINKED = "matched_not_linked"
    IMPORT_COVERED = "import_covered"
    NONE = "none"


@dataclass(frozen=True)
class TargetSourceStatus:
    """One checklist row: a target category and the field (if any) feeding it.

    ``field`` is the linked or name-matched field; ``source_field`` is the
    field a linked derivation reads from (None for an exact copy).
    ``stale`` means the field's option values no longer mirror the target's
    values — computed by comparison, never stored.
    """

    category: TargetCategory
    state: TargetSourceState
    field: RespondentFieldDefinition | None = None
    source_field: RespondentFieldDefinition | None = None
    mapping_row_count: int | None = None
    stale: bool = False


def _ensure_manage_permission(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> None:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="configure target data sources",
            required_role="assembly-manager or admin",
        )


def _ensure_view_permission(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> None:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="view target data sources",
            required_role="assembly role or admin",
        )


def _get_category(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, category_id: uuid.UUID) -> TargetCategory:
    category: TargetCategory | None = uow.target_categories.get(category_id)
    if category is None or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")
    if not category.values:
        raise FieldDefinitionConflictError(
            _l("Target '%(name)s' has no values yet — add its values before wiring a data source", name=category.name)
        )
    return category


def _target_option_values(category: TargetCategory) -> list[str]:
    return [value.value for value in category.values]


def _fields_linked_to(uow: AbstractUnitOfWork, category: TargetCategory) -> list[RespondentFieldDefinition]:
    return [
        field
        for field in uow.respondent_field_definitions.list_by_assembly(category.assembly_id)
        if field.target_category_id == category.id
    ]


def _choice_type_for(n_options: int) -> FieldType:
    return FieldType.CHOICE_RADIO if n_options <= _MAX_RADIO_OPTIONS else FieldType.CHOICE_DROPDOWN


def _next_sort_order_in_group(existing: list[RespondentFieldDefinition], group: RespondentFieldGroup) -> int:
    return max((f.sort_order for f in existing if f.group == group), default=0) + SORT_ORDER_STEP


def _require_target_values_covered(field: RespondentFieldDefinition, category: TargetCategory) -> None:
    """Refuse a field whose options cannot represent every target value."""
    option_values = {option.value for option in field.options or []}
    missing = [value for value in _target_option_values(category) if value not in option_values]
    if missing:
        raise FieldDefinitionConflictError(
            _l(
                "Field '%(key)s' is missing options for these target values: %(values)s",
                key=field.field_key,
                values=", ".join(missing),
            )
        )


def _relink(uow: AbstractUnitOfWork, category: TargetCategory, field: RespondentFieldDefinition) -> None:
    """Point the category's link at ``field``, clearing it from any other field."""
    for other in _fields_linked_to(uow, category):
        if other.id != field.id:
            other.target_category_id = None
    field.target_category_id = category.id


def _resolve_source_field(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    spec: SourceFieldSpec,
    derivation_type: DerivationType | None,
) -> RespondentFieldDefinition:
    """Fetch the reused source field, or create the described one.

    For a derivation, a reused field must be type-compatible with the rule;
    a created one is validated the same way so a bad spec fails here rather
    than deep inside ``create_derived_field``.
    """
    if spec.reuse_field_id is not None:
        field: RespondentFieldDefinition | None = uow.respondent_field_definitions.get(spec.reuse_field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {spec.reuse_field_id} not found in assembly {assembly_id}")
        if derivation_type is not None and field not in compatible_source_fields([field], derivation_type):
            raise FieldDefinitionConflictError(
                _l("Field '%(key)s' cannot feed this kind of derivation", key=field.field_key)
            )
        return field

    field_key = spec.field_key.strip()
    if not field_key:
        raise FieldDefinitionConflictError(_l("Field key cannot be empty"))
    if uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, field_key) is not None:
        raise FieldDefinitionConflictError(
            _l(
                "Field '%(key)s' already exists in this assembly — choose it instead of creating a new one",
                key=field_key,
            )
        )
    existing = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    group = spec.group or classify_field_key(field_key, [category.name])
    field = RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=field_key,
        label=spec.label.strip() or humanise_field_key(field_key),
        group=group,
        sort_order=_next_sort_order_in_group(existing, group),
        field_type=spec.field_type,
        options=list(spec.options) if spec.options else None,
        on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
        help_text=spec.help_text,
    )
    if derivation_type is not None and field not in compatible_source_fields([field], derivation_type):
        raise FieldDefinitionConflictError(
            _l("A '%(type)s' field cannot feed this kind of derivation", type=spec.field_type.value)
        )
    uow.respondent_field_definitions.add(field)
    return field


def _configure_exact_copy(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    spec: ExactCopySpec,
) -> RespondentFieldDefinition:
    if spec.source.reuse_field_id is not None:
        field: RespondentFieldDefinition | None = uow.respondent_field_definitions.get(spec.source.reuse_field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(
                f"Field {spec.source.reuse_field_id} not found in assembly {assembly_id}"
            )
        if field.is_derived:
            raise FieldDefinitionConflictError(
                _l("Field '%(key)s' is derived — an exact copy must be a directly collected field", key=field.field_key)
            )
        if field.effective_field_type not in CHOICE_TYPES:
            raise FieldDefinitionConflictError(
                _l(
                    "Field '%(key)s' is not a choice field, so it cannot be an exact copy of a target",
                    key=field.field_key,
                )
            )
        _require_target_values_covered(field, category)
        return field

    target_values = _target_option_values(category)
    if uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, category.name) is not None:
        raise FieldDefinitionConflictError(
            _l(
                "Field '%(key)s' already exists in this assembly — choose it instead of creating a new one",
                key=category.name,
            )
        )
    existing = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    group = spec.source.group or classify_field_key(category.name, [category.name])
    field = RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=category.name,
        label=spec.source.label.strip() or humanise_field_key(category.name),
        group=group,
        sort_order=_next_sort_order_in_group(existing, group),
        field_type=_choice_type_for(len(target_values)),
        options=[ChoiceOption(value=value) for value in target_values],
        on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
        help_text=spec.source.help_text,
    )
    uow.respondent_field_definitions.add(field)
    return field


def _configure_derivation(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    rule: DerivationRule,
    source_spec: SourceFieldSpec,
) -> tuple[RespondentFieldDefinition, RecomputeReport]:
    derivation_type = _DERIVATION_TYPE_FOR_RULE[type(rule)]
    source = _resolve_source_field(uow, assembly_id, category, source_spec, derivation_type)

    # An age rule's outputs are its bracket labels; mapping rules output the
    # target's values (the fallback is appended by the derivation machinery).
    output_values = None if isinstance(rule, AgeBracketRule) else _target_option_values(category)

    existing = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, category.name)
    if existing is not None and not existing.is_derived:
        raise FieldDefinitionConflictError(
            _l(
                "Field '%(key)s' already exists and is not derived — use the exact copy method, or rename it first",
                key=category.name,
            )
        )
    if existing is not None:
        # Re-configuring: repoint the derivation at the requested source, then
        # let update_derivation validate it, regenerate options and recompute.
        existing.derived_from = [source.field_key]
        _detached, report = update_derivation(uow, user_id, assembly_id, existing.id, rule, output_values)
        return existing, report

    _detached, report = create_derived_field(
        uow,
        user_id,
        assembly_id,
        field_key=category.name,
        label=humanise_field_key(category.name),
        source_field_key=source.field_key,
        rule=rule,
        output_values=output_values,
    )
    created = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, category.name)
    assert created is not None  # create_derived_field just added it
    return created, report


def configure_target_source(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    target_category_id: uuid.UUID,
    spec: TargetSourceSpec,
) -> tuple[list[RespondentFieldDefinition], RecomputeReport | None]:
    """Wire one target category to its data source, in one transaction.

    Creates or reuses the registration field, creates or updates the derived
    field for the derivation methods, links the feeding field to the category,
    and recomputes the pool where a derivation is involved. Returns the fields
    the checklist should show (source first where there is one) as detached
    copies, plus the recompute report (None for an exact copy).

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    category = _get_category(uow, assembly_id, target_category_id)

    if isinstance(spec, ExactCopySpec):
        field = _configure_exact_copy(uow, assembly_id, category, spec)
        _relink(uow, category, field)
        return [field.create_detached_copy()], None

    derived, report = _configure_derivation(uow, user_id, assembly_id, category, spec.rule, spec.source)
    _relink(uow, category, derived)
    source = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, (derived.derived_from or [""])[0])
    fields = [source.create_detached_copy()] if source is not None else []
    fields.append(derived.create_detached_copy())
    return fields, report


def _stale_for_exact(field: RespondentFieldDefinition, category: TargetCategory) -> bool:
    return [option.value for option in field.options or []] != _target_option_values(category)


def _stale_for_derived(field: RespondentFieldDefinition, category: TargetCategory) -> bool:
    """A derived field is stale when its outputs (minus the fallback) drift from the target's values."""
    fallback = ""
    if field.derivation_type is not None and field.derivation_config is not None:
        try:
            fallback = rule_from_field(field.derivation_type, field.derivation_config).fallback
        except ValueError:
            # A config that no longer parses is definitely stale.
            return True
    outputs = {option.value for option in field.options or []} - {fallback}
    return outputs != set(_target_option_values(category))


def _status_for_category(
    uow: AbstractUnitOfWork,
    category: TargetCategory,
    fields: list[RespondentFieldDefinition],
    attribute_columns: set[str],
) -> TargetSourceStatus:
    linked = next((f for f in fields if f.target_category_id == category.id), None)
    detached_category = category.create_detached_copy()
    if linked is not None and linked.is_derived:
        source = next((f for f in fields if f.field_key == (linked.derived_from or [""])[0]), None)
        row_count = None
        if linked.derivation_type == DerivationType.LARGE_MAPPING:
            row_count = uow.respondent_field_mapping_entries.count_for_field(linked.id)
        return TargetSourceStatus(
            category=detached_category,
            state=TargetSourceState.LINKED_DERIVED,
            field=linked.create_detached_copy(),
            source_field=source.create_detached_copy() if source else None,
            mapping_row_count=row_count,
            stale=_stale_for_derived(linked, category),
        )
    if linked is not None:
        return TargetSourceStatus(
            category=detached_category,
            state=TargetSourceState.LINKED_EXACT,
            field=linked.create_detached_copy(),
            stale=_stale_for_exact(linked, category),
        )
    matched = next((f for f in fields if f.field_key.casefold() == category.name.casefold()), None)
    if matched is not None:
        return TargetSourceStatus(
            category=detached_category,
            state=TargetSourceState.MATCHED_NOT_LINKED,
            field=matched.create_detached_copy(),
        )
    if category.name.casefold() in attribute_columns:
        return TargetSourceStatus(category=detached_category, state=TargetSourceState.IMPORT_COVERED)
    return TargetSourceStatus(category=detached_category, state=TargetSourceState.NONE)


@dataclass(frozen=True)
class TargetSetupData:
    """What the set-up dialog for one target needs to know before it can ask anything."""

    target_id: uuid.UUID
    target_name: str
    target_values: list[str]
    fields: list[RespondentFieldDefinition]
    first_assembly_date: date | None
    is_linked: bool
    # Rows in the linked field's lookup table; 0 unless the target is fed by a large mapping.
    mapping_row_count: int


def target_setup_data(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    target_category_id: uuid.UUID,
) -> TargetSetupData:
    """The target, and the assembly's fields, that a set-up dialog is built from.

    Unlike ``configure_target_source`` this accepts a target with no values yet:
    the dialog should open and let the save explain what is missing.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_view_permission(uow, user_id, assembly_id)
    assembly = uow.assemblies.get(assembly_id)
    category: TargetCategory | None = uow.target_categories.get(target_category_id)
    if category is None or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {target_category_id} not found")
    fields = [f.create_detached_copy() for f in uow.respondent_field_definitions.list_by_assembly(assembly_id)]
    linked = next((f for f in fields if f.target_category_id == category.id), None)
    mapping_row_count = (
        uow.respondent_field_mapping_entries.count_for_field(linked.id)
        if linked is not None and linked.derivation_type == DerivationType.LARGE_MAPPING
        else 0
    )
    return TargetSetupData(
        target_id=category.id,
        target_name=category.name,
        target_values=_target_option_values(category),
        fields=fields,
        first_assembly_date=assembly.first_assembly_date if assembly else None,
        is_linked=linked is not None,
        mapping_row_count=mapping_row_count,
    )


def reusable_source_fields(
    fields: list[RespondentFieldDefinition],
    derivation_type: DerivationType | None,
    target_values: list[str],
) -> list[RespondentFieldDefinition]:
    """The existing fields a target could take its data from, by field key.

    ``derivation_type`` None asks for an exact copy: a question someone answers,
    whose options already cover every value of the target. Otherwise it is
    whatever the derivation can be computed from.
    """
    if derivation_type is None:
        candidates = [
            field
            for field in fields
            if not field.is_derived
            and field.effective_field_type in CHOICE_TYPES
            and set(target_values) <= {option.value for option in field.options or []}
        ]
    else:
        candidates = compatible_source_fields(fields, derivation_type)
    return sorted(candidates, key=lambda f: f.field_key.casefold())


def target_source_status(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[TargetSourceStatus]:
    """One status row per target category, in target sort order.

    The checklist's single data source: linked (exact or derived, with
    staleness), name-matched but unlinked (offers adopt), covered by an
    imported respondent column, or nothing.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_view_permission(uow, user_id, assembly_id)
    categories = list(uow.target_categories.get_by_assembly_id(assembly_id))
    fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    field_keys = {f.field_key.casefold() for f in fields}
    attribute_columns = {
        column.casefold()
        for column in get_respondent_attribute_columns(uow, assembly_id)
        if column.casefold() not in field_keys
    }
    return [_status_for_category(uow, category, fields, attribute_columns) for category in categories]


def adopt_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    target_category_id: uuid.UUID,
    field_id: uuid.UUID,
) -> RespondentFieldDefinition:
    """Link an existing name-matched field to the target category it mirrors.

    Validates the match rather than rewriting anything: the names must agree
    (case-insensitively — selection matches that way) and a choice field must
    carry an option for every target value.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    category = _get_category(uow, assembly_id, target_category_id)
    field: RespondentFieldDefinition | None = uow.respondent_field_definitions.get(field_id)
    if field is None or field.assembly_id != assembly_id:
        raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
    if field.field_key.casefold() != category.name.casefold():
        raise FieldDefinitionConflictError(
            _l(
                "Field '%(key)s' does not share the target's name '%(name)s', so selection would not pair them",
                key=field.field_key,
                name=category.name,
            )
        )
    if field.effective_field_type in CHOICE_TYPES and not field.is_derived:
        _require_target_values_covered(field, category)
    _relink(uow, category, field)
    return field.create_detached_copy()


def resync_from_target(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    target_category_id: uuid.UUID,
) -> tuple[RespondentFieldDefinition, RecomputeReport | None]:
    """Regenerate a linked field's options from the target's current values.

    Exact copies get their options replaced (help texts preserved for values
    that survive); mapping derivations get their outputs regenerated and the
    pool recomputed. Age brackets are refused — their outputs come from the
    bracket configuration, so the fix is editing the brackets or the target.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    category = _get_category(uow, assembly_id, target_category_id)
    linked = next(iter(_fields_linked_to(uow, category)), None)
    if linked is None:
        raise FieldDefinitionNotFoundError(f"No field is linked to target category {target_category_id}")

    if not linked.is_derived:
        help_texts = {option.value: option.help_text for option in linked.options or []}
        linked.resync_options([
            ChoiceOption(value=value, help_text=help_texts.get(value, "")) for value in _target_option_values(category)
        ])
        return linked.create_detached_copy(), None

    if linked.derivation_type == DerivationType.AGE_BRACKET:
        raise FieldDefinitionConflictError(
            _l("Age brackets come from the field's configuration — edit the age ranges or the target values instead")
        )
    assert linked.derivation_type is not None
    assert linked.derivation_config is not None
    rule = rule_from_field(linked.derivation_type, linked.derivation_config)
    detached, report = update_derivation(
        uow, user_id, assembly_id, linked.id, rule, output_values=_target_option_values(category)
    )
    return detached, report


def unlink(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    target_category_id: uuid.UUID,
) -> tuple[list[RespondentFieldDefinition], list[RespondentFieldDefinition]]:
    """Break the link between a target category and its fields.

    A question someone answers stays, fully editable again; only the link goes.
    A derived field is deleted, along with its lookup table and the values it
    wrote: it exists only to feed this target, and no screen lists one that
    feeds nothing. Returns the unlinked questions and the deleted derived
    fields, as detached copies.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _ensure_manage_permission(uow, user_id, assembly_id)
    category: TargetCategory | None = uow.target_categories.get(target_category_id)
    if category is None or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {target_category_id} not found")
    unlinked = []
    deleted = []
    for field in _fields_linked_to(uow, category):
        if field.is_derived:
            deleted.append(field.create_detached_copy())
            delete_derived_field(uow, assembly_id, field)
            continue
        field.target_category_id = None
        unlinked.append(field.create_detached_copy())
    return unlinked, deleted
