"""ABOUTME: Target category and value service layer for stratified selection quotas
ABOUTME: Provides CRUD, CSV import and percentage-driven min/max for assembly targets"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from sortition_algorithms.adapters import SelectionData
from sortition_algorithms.features import FeatureCollection
from sqlalchemy.orm.attributes import flag_modified

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import (
    MAX_COMMENT_LENGTH,
    MAX_SOURCE_URL_LENGTH,
    TargetCategory,
    TargetValue,
    validate_comment,
    validate_source_url,
)
from opendlp.translations import gettext as _

from .constants import MAX_DISTINCT_VALUES_FOR_AUTO_ADD, SORT_ORDER_STEP
from .exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    NotFoundError,
    ServiceLayerError,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly
from .respondent_service import get_respondent_attribute_columns, get_respondent_attribute_value_counts
from .unit_of_work import AbstractUnitOfWork

# Distinguishes "not submitted, leave alone" from a submitted None, which for a
# percentage legitimately means "clear it".
UNSET: Any = object()

# How much of a conflicting CSV cell to echo back in a warning.


@dataclass(frozen=True)
class TargetValueChange:
    """A value whose min/max moved, with the numbers before and after."""

    category_id: uuid.UUID
    value_id: uuid.UUID
    value: str
    old_min: int
    old_max: int
    new_min: int
    new_max: int


@dataclass
class TargetValueEdit:
    """One value in a bulk save. `value_id` of None means a new value.

    `form_id` is the id the row was submitted under, which is what ties an error
    back to the field that caused it. It is not the same as `value_id`: a row the
    user has just added has no `value_id` at all, and two of them would otherwise
    be indistinguishable.
    """

    value: str
    value_id: uuid.UUID | None = None
    percentage: float | None = None
    min: int | None = None
    max: int | None = None
    comment: str = ""
    deleted: bool = False
    relink: bool = False
    form_id: str = ""


@dataclass
class TargetCategoryEdit:
    """One category in a bulk save, with all of its submitted values.

    A `category_id` of None means a category the user added in the form and that
    does not exist yet. `form_id` is the id it was submitted under - see
    `TargetValueEdit`.
    """

    category_id: uuid.UUID | None
    name: str
    comment: str = ""
    source_url: str = ""
    values: list[TargetValueEdit] = field(default_factory=list)
    deleted: bool = False
    sort_order: int | None = None
    form_id: str = ""


@dataclass
class TargetEditError:
    """One problem with a submitted edit, tied to the field that caused it.

    The ids are the submitted `form_id`s and `field` is a bare name like "max".
    Turning those into a form field name is the entrypoint's job: the service
    knows which value is wrong, not what the input was called.
    """

    message: str
    category_form_id: str = ""
    value_form_id: str = ""
    field: str = ""


class TargetsNotSaved(ServiceLayerError):
    """Nothing was saved, because one or more edits are invalid.

    Carries every error found rather than the first, so a page of edits can be
    fixed in one pass instead of one round trip per mistake. Raising rolls the
    unit of work back, which is what makes "nothing was saved" true.
    """

    def __init__(self, errors: list[TargetEditError]) -> None:
        super().__init__("targets not saved")
        self.errors = errors


def _load_user_and_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    action: str,
) -> Assembly:
    """Load the assembly, checking the user may manage it."""
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action=action,
            required_role="assembly-manager or admin",
        )
    return cast("Assembly", assembly)


def _get_category(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
) -> TargetCategory:
    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")
    return category


def _get_value(category: TargetCategory, value_id: uuid.UUID) -> TargetValue:
    existing = next((v for v in category.values if v.value_id == value_id), None)
    if not existing:
        raise NotFoundError(f"Target value {value_id} not found")
    return existing


def create_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    name: str,
    sort_order: int | None = None,
    comment: str = "",
    source_url: str = "",
) -> TargetCategory:
    """Create a new target category for an assembly.

    When `sort_order` is not supplied the category is placed after the existing
    ones. That is policy, so it belongs here rather than in the entrypoint.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="create target category",
            required_role="assembly-manager or admin",
        )

    existing = uow.target_categories.get_by_assembly_id(assembly_id)
    if any(c.name.lower() == name.lower() for c in existing):
        raise ValueError(f"A category named '{name}' already exists")

    if sort_order is None:
        sort_order = max((c.sort_order for c in existing), default=0) + SORT_ORDER_STEP

    category = TargetCategory(
        assembly_id=assembly_id,
        name=name,
        sort_order=sort_order,
        comment=comment,
        source_url=source_url,
    )

    # Auto-add values if category name matches a low-cardinality respondent column
    attribute_columns = get_respondent_attribute_columns(uow, assembly_id)
    columns_lower = {col.lower(): col for col in attribute_columns}
    matched_col = columns_lower.get(name.lower())
    if matched_col is not None:
        value_counts = get_respondent_attribute_value_counts(uow, assembly_id, matched_col)
        if 0 < len(value_counts) < MAX_DISTINCT_VALUES_FOR_AUTO_ADD:
            for value_name in sorted(value_counts.keys()):
                category.add_value(TargetValue(value=value_name, min=0, max=0))

    uow.target_categories.add(category)
    return category.create_detached_copy()


def get_targets_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[TargetCategory]:
    """Get all target categories for an assembly.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="view targets",
            required_role="assembly role or global privileges",
        )

    categories = uow.target_categories.get_by_assembly_id(assembly_id)
    return [c.create_detached_copy() for c in categories]


def update_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str,
    comment: str = "",
    source_url: str = "",
) -> TargetCategory:
    """Update a target category's name, comment and source URL.

    An invalid `source_url` raises ValueError from the domain; the route turns
    that into a field error rather than a 500.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="update target category",
            required_role="assembly-manager or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    category.name = name.strip()
    category.comment = validate_comment(comment)
    category.source_url = validate_source_url(source_url)
    category.updated_at = datetime.now(UTC)

    return category.create_detached_copy()


def delete_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
) -> None:
    """Delete a target category.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete target category",
            required_role="assembly-manager or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    uow.target_categories.delete(category)


def add_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value: str,
    min_count: int = 0,
    max_count: int = 0,
    percentage: float | None = None,
    comment: str = "",
) -> TargetCategory:
    """Add a value to a target category. Returns the updated category.

    A percentage drives min/max on construction; explicit min/max without a
    percentage are left exactly as given.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="add target value",
            required_role="assembly-manager or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    target_val = TargetValue(
        value=value,
        min=min_count,
        max=max_count,
        percentage_target=percentage,
        comment=comment,
    )
    target_val.apply_percentage(assembly.number_to_select)
    category.add_value(target_val)
    flag_modified(category, "values")

    return category.create_detached_copy()


def update_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    value: str,
    min_count: int | None = None,
    max_count: int | None = None,
    percentage: float | None = UNSET,
    comment: str | None = None,
) -> TargetCategory:
    """Update a value within a target category. Returns the updated category.

    Every optional parameter means "not submitted, leave alone" when omitted.
    `percentage` uses the UNSET sentinel rather than None, because a submitted
    None legitimately means "clear the percentage".

    The rules that matter:

    - min/max supplied and *different* from the stored values breaks the
      auto-calculate link, via `set_manual_min_max`.
    - min/max supplied and *identical* to the stored values changes nothing and
      does **not** break the link. Without this a bulk save that round-trips
      every field would break every link in the assembly on first use.
    - A percentage is applied first, so an explicit min/max in the same
      submission wins and breaks the link.
    - Clearing the percentage leaves min/max and `minmax_manual` alone.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="update target value",
            required_role="assembly-manager or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    existing = _get_value(category, value_id)

    if value != existing.value and any(v.value == value for v in category.values):
        raise ValueError(f"Value '{value}' already exists in category '{category.name}'")

    number_to_select = assembly.number_to_select

    existing.value = value.strip()
    if comment is not None:
        existing.comment = comment
    _apply_value_numbers(existing, min_count, max_count, percentage, number_to_select)
    existing._validate()
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


def _apply_value_numbers(
    target_value: TargetValue,
    min_count: int | None,
    max_count: int | None,
    percentage: float | None,
    number_to_select: int,
) -> None:
    """Apply a submitted percentage and min/max to one value, in that order.

    Shared by `update_target_value` and `save_all_targets` so there is exactly
    one implementation of the link-breaking rules.
    """
    # Captured before the percentage is applied. Comparing against the
    # recalculated numbers instead would break the link every time a form
    # round-tripped the min/max it had displayed, which is the whole thing the
    # "identical means leave it alone" rule exists to prevent.
    submitted_against = (target_value.min, target_value.max)

    if percentage is not UNSET:
        target_value.percentage_target = percentage
        target_value.apply_percentage(number_to_select)

    if min_count is None and max_count is None:
        return

    new_min = submitted_against[0] if min_count is None else min_count
    new_max = submitted_against[1] if max_count is None else max_count
    if (new_min, new_max) != submitted_against:
        target_value.set_manual_min_max(new_min, new_max)


def delete_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
) -> TargetCategory:
    """Delete a value from a target category. Returns the updated category.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete target value",
            required_role="assembly-manager or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    if not category.remove_value(value_id):
        raise NotFoundError(f"Target value {value_id} not found")
    flag_modified(category, "values")

    return category.create_detached_copy()


def get_feature_collection_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> tuple[FeatureCollection, str]:
    """
    Load target categories as FeatureCollection using sortition-algorithms.
    Used internally for selection operations.

    Returns: (FeatureCollection, report_text)

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="get feature collection",
            required_role="assembly role or global privileges",
        )

    # Use SelectionData with our custom adapter
    adapter = OpenDLPDataAdapter(uow, assembly_id)
    select_data = SelectionData(adapter)

    # Load features using sortition-algorithms
    features, report = select_data.load_features(assembly.number_to_select)

    return features, report.as_text()


def delete_targets_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> int:
    """Delete all target categories for an assembly.

    Returns the number of categories deleted.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete targets",
            required_role="assembly-manager or admin",
        )

    return uow.target_categories.delete_all_for_assembly(assembly_id)


def relink_target_value_to_percentage(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
) -> TargetCategory:
    """Restore auto-calculation for one value and recalculate it now.

    Refuses when the value has no percentage: re-linking is meaningless without
    one, and silently clearing the flag would leave a value claiming to be
    linked while showing hand-typed numbers.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "relink target value")
    category = _get_category(uow, assembly_id, category_id)
    target_value = _get_value(category, value_id)

    target_value.relink_to_percentage(assembly.number_to_select)
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


def recalculate_minmax_for_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
) -> list[TargetValueChange]:
    """Re-derive min/max for every value with an intact auto-calculate link.

    Returns the values that moved, with their old and new min/max. No permission
    check: this is an internal consequence of an already-authorised change, not a
    user action.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    changes: list[TargetValueChange] = []
    for category in uow.target_categories.get_by_assembly_id(assembly_id):
        touched = False
        for target_value in category.values:
            old_min, old_max = target_value.min, target_value.max
            if not target_value.apply_percentage(assembly.number_to_select):
                continue
            touched = True
            changes.append(
                TargetValueChange(
                    category_id=category.id,
                    value_id=cast("uuid.UUID", target_value.value_id),
                    value=target_value.value,
                    old_min=old_min,
                    old_max=old_max,
                    new_min=target_value.min,
                    new_max=target_value.max,
                )
            )
        if touched:
            category.updated_at = datetime.now(UTC)
            flag_modified(category, "values")

    return changes


def save_all_targets(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    edits: list[TargetCategoryEdit],
) -> list[TargetCategory]:
    """Apply edits to many categories and values in one operation.

    One permission check, one pass, all-or-nothing - the entrypoint's single
    `with uow:` provides the transaction, so if any edit raises nothing commits.
    Reuses the per-value logic from `update_target_value`, so the link-breaking
    rules have exactly one implementation.

    Deletion is explicit: a category or value goes only when its edit says so.
    Absence from the payload still means "leave alone", so a partial submission
    cannot silently destroy anything.

    An edit with no `category_id` creates a category. Unlike
    `create_target_category` this does not auto-populate values from a matching
    respondent column: the user is looking at the form where they would add them,
    and rows appearing under a name they had just typed would be a surprise.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "save targets")
    number_to_select = assembly.number_to_select
    naming = _CategoryNaming(uow, assembly_id, edits)

    saved = []
    errors: list[TargetEditError] = []
    now = datetime.now(UTC)
    for category_edit in edits:
        if category_edit.deleted:
            if category_edit.category_id is not None:
                uow.target_categories.delete(_get_category(uow, assembly_id, category_edit.category_id))
            continue

        category = _save_one_category(uow, assembly_id, category_edit, naming, number_to_select, now, errors)
        if category is not None:
            saved.append(category)

    if errors:
        raise TargetsNotSaved(errors)
    return saved


def _save_one_category(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category_edit: TargetCategoryEdit,
    naming: "_CategoryNaming",
    number_to_select: int,
    now: datetime,
    errors: list[TargetEditError],
) -> TargetCategory | None:
    """Apply one category edit, recording rather than raising what goes wrong.

    Carrying on after a bad category is what lets the whole form come back
    annotated in one pass. `save_all_targets` raises at the end, so none of the
    work done here survives when anything failed.
    """
    try:
        naming.claim(category_edit.name, category_edit.category_id)
    except ValueError:
        errors.append(
            TargetEditError(
                _("A target called '%(name)s' already exists", name=category_edit.name.strip()),
                category_edit.form_id,
                field="name",
            )
        )
        return None

    is_new = category_edit.category_id is None
    if is_new:
        try:
            category = TargetCategory(
                assembly_id=assembly_id,
                name=category_edit.name.strip(),
                sort_order=naming.next_sort_order(),
            )
        except ValueError:
            errors.append(TargetEditError(_("Enter a name for this target"), category_edit.form_id, field="name"))
            return None
        uow.target_categories.add(category)
    else:
        category = _get_category(uow, assembly_id, cast("uuid.UUID", category_edit.category_id))

    _apply_category_edit(category, category_edit, number_to_select, errors)
    category.updated_at = now
    if not is_new:
        # A category being inserted has no stored JSON to mark dirty.
        flag_modified(category, "values")
    return category.create_detached_copy()


class _CategoryNaming:
    """Guards category names and hands out sort orders during a bulk save.

    `(assembly_id, name)` carries a unique index, so a clash is a database error
    rather than a mistake we can shrug at. Checking here turns it into a
    `ValueError` the route can flash.

    A name in use at the start of the save stays claimed for its own category
    even when this save deletes or renames it away. Freeing it properly would
    mean flushing the deletes before the inserts, and SQLAlchemy orders an INSERT
    ahead of the DELETE that would make room for it. So deleting "Gender" and
    adding a new "Gender" in one go is refused; do it in two saves.
    """

    def __init__(
        self,
        uow: AbstractUnitOfWork,
        assembly_id: uuid.UUID,
        edits: list[TargetCategoryEdit],
    ) -> None:
        existing = uow.target_categories.get_by_assembly_id(assembly_id)
        self._taken = {c.name.strip().lower() for c in existing}
        self._own: dict[uuid.UUID | None, str] = {c.id: c.name.strip().lower() for c in existing}
        self._next = max((c.sort_order for c in existing), default=0) + SORT_ORDER_STEP

    def claim(self, name: str, category_id: uuid.UUID | None) -> None:
        """Reserve a name, refusing one that belongs to a different category."""
        key = name.strip().lower()
        if key in self._taken and key != self._own.get(category_id):
            raise ValueError(f"A category named '{name.strip()}' already exists")
        self._taken.add(key)

    def next_sort_order(self) -> int:
        """The next free sort order, placing new categories after the existing ones."""
        value = self._next
        self._next += SORT_ORDER_STEP
        return value


def _apply_category_edit(
    category: TargetCategory,
    category_edit: TargetCategoryEdit,
    number_to_select: int,
    errors: list[TargetEditError],
) -> None:
    """Apply one category's own fields and every value edit beneath it."""
    category.name = category_edit.name.strip()
    try:
        category.comment = validate_comment(category_edit.comment)
    except ValueError:
        errors.append(
            TargetEditError(
                _("Comment must be %(limit)s characters or fewer", limit=MAX_COMMENT_LENGTH),
                category_edit.form_id,
                field="comment",
            )
        )
    try:
        category.source_url = validate_source_url(category_edit.source_url)
    except ValueError:
        errors.append(
            TargetEditError(
                _(
                    "Enter a full http:// or https:// address, %(limit)s characters or fewer",
                    limit=MAX_SOURCE_URL_LENGTH,
                ),
                category_edit.form_id,
                field="source_url",
            )
        )
    if category_edit.sort_order is not None:
        category.sort_order = category_edit.sort_order

    errors.extend(_duplicate_value_errors(category_edit))

    for value_edit in category_edit.values:
        _apply_value_edit(category, value_edit, number_to_select, category_edit.form_id, errors)


def _duplicate_value_errors(category_edit: TargetCategoryEdit) -> list[TargetEditError]:
    """Refuse two values in one category sharing a name.

    `to_feature_dict` keys the selection run by value name, so a duplicate does
    not fail loudly - it drops one of the two targets from the run. The per-value
    routes have always guarded this; the bulk form is now the only way in, so the
    check has to live here as well.

    The error goes on every row of a clashing group: the user chose which one to
    rename, and the form cannot know which of them they meant to keep.
    """
    seen: dict[str, list[TargetValueEdit]] = {}
    for value_edit in category_edit.values:
        if value_edit.deleted:
            continue
        seen.setdefault(value_edit.value.strip(), []).append(value_edit)

    errors: list[TargetEditError] = []
    for name, group in seen.items():
        if not name or len(group) < 2:
            continue
        errors.extend(
            TargetEditError(
                _("Two values in this category are both called '%(name)s'", name=name),
                category_edit.form_id,
                value_edit.form_id,
                "value",
            )
            for value_edit in group
        )
    return errors


def _value_problem(value_edit: TargetValueEdit) -> tuple[str, str] | None:
    """The first problem with a submitted value that we can pin to one field.

    The domain enforces all of these, but it raises on the first one it meets
    with a message written for a developer. Naming them here is what lets the
    form say which box is wrong, in words aimed at the person filling it in.
    """
    if value_edit.deleted or value_edit.relink:
        return None
    if value_edit.min is not None and value_edit.min < 0:
        return "min", _("Min cannot be negative")
    if value_edit.max is not None and value_edit.max < 0:
        return "max", _("Max cannot be negative")
    if value_edit.min is not None and value_edit.max is not None and value_edit.max < value_edit.min:
        return "max", _("Max must be at least the min")
    if value_edit.percentage is not None and not 0 <= value_edit.percentage <= 100:
        return "percentage", _("Population share must be between 0 and 100")
    return None


def _apply_value_edit(
    category: TargetCategory,
    value_edit: TargetValueEdit,
    number_to_select: int,
    category_form_id: str,
    errors: list[TargetEditError],
) -> None:
    """Add, update or remove one value, recording rather than raising a problem."""
    problem = _value_problem(value_edit)
    if problem is not None:
        errors.append(TargetEditError(problem[1], category_form_id, value_edit.form_id, problem[0]))
        return

    try:
        _write_value_edit(category, value_edit, number_to_select)
    except ValueError:
        # Whatever `_value_problem` did not anticipate. Without a field to blame
        # it goes against the row, which is still where the reader needs it.
        # TypeError is deliberately not caught: it means a bug rather than bad
        # input, and belongs in the log via the route's handler, not on the page.
        errors.append(TargetEditError(_("Check the numbers in this row"), category_form_id, value_edit.form_id))


def _write_value_edit(
    category: TargetCategory,
    value_edit: TargetValueEdit,
    number_to_select: int,
) -> None:
    """Add, update or remove one value, per its edit."""
    if value_edit.value_id is None:
        if value_edit.deleted:
            return
        target_value = TargetValue(
            value=value_edit.value,
            min=value_edit.min or 0,
            max=value_edit.max or 0,
            percentage_target=value_edit.percentage,
            comment=value_edit.comment,
        )
        target_value.apply_percentage(number_to_select)
        category.add_value(target_value)
        return

    if value_edit.deleted:
        category.remove_value(value_edit.value_id)
        return

    target_value = _get_value(category, value_edit.value_id)
    target_value.value = value_edit.value.strip()
    target_value.comment = value_edit.comment
    if value_edit.relink:
        target_value.percentage_target = value_edit.percentage
        target_value.relink_to_percentage(number_to_select)
    else:
        _apply_value_numbers(
            target_value,
            value_edit.min,
            value_edit.max,
            value_edit.percentage,
            number_to_select,
        )
    target_value._validate()
