"""ABOUTME: Replacement selection over the database: the targets still to fill, and the organiser's edits to them
ABOUTME: Builds the review plan from the stored targets and respondent statuses, then validates the submitted numbers"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sortition_algorithms import adapters
from sortition_algorithms.committee_generation.common import setup_committee_generation
from sortition_algorithms.errors import InfeasibleQuotasError, SortitionBaseError
from sortition_algorithms.features import (
    MAX_FLEX_UNSET,
    iterate_feature_collection,
    report_min_max_against_number_to_select_structured,
    report_min_max_error_details_structured,
)
from sortition_algorithms.people import check_people_per_feature_value, exclude_matching_selected_addresses

from opendlp.adapters.sortition_data_adapter import DB_ID_COLUMN, OpenDLPDataAdapter
from opendlp.domain.respondents import matching_attribute_column
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import ReplacementMinMax, replacement_min_max
from opendlp.domain.value_objects import SELECTED_RESPONDENT_STATUSES
from opendlp.service_layer.error_translation import translate_sortition_error
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.translations import gettext as _

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sortition_algorithms.features import FeatureCollection
    from sortition_algorithms.people import People
    from sortition_algorithms.settings import Settings

    from opendlp.domain.targets import TargetCategory, TargetValue
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

# A pool with this many spare people or fewer for a value is close enough to
# its minimum that the dialog draws attention to it.
SPARE_WARNING_THRESHOLD = 1


@dataclass
class ReplacementValueRow:
    """One target value: what it holds, what is still to fill, and what the pool can offer."""

    value: str
    value_id: uuid.UUID
    overall_min: int
    overall_max: int
    held: int
    calculated: ReplacementMinMax
    available: int
    percentage_target: float | None = None
    comment: str = ""
    minmax_manual: bool = False

    @property
    def shortfall(self) -> int:
        return max(0, self.calculated.min - self.available)

    @property
    def spare(self) -> int:
        return self.available - self.calculated.min

    @property
    def over_held(self) -> bool:
        """More places held than the overall maximum allows."""
        return self.held > self.overall_max

    @property
    def is_short(self) -> bool:
        return self.shortfall > 0

    @property
    def is_tight(self) -> bool:
        return not self.is_short and self.calculated.min > 0 and self.spare <= SPARE_WARNING_THRESHOLD

    @property
    def min_field(self) -> str:
        return f"min-{self.value_id}"

    @property
    def max_field(self) -> str:
        return f"max-{self.value_id}"


@dataclass
class ReplacementCategory:
    name: str
    category_id: uuid.UUID
    sort_order: int
    comment: str
    source_url: str
    attribute_matched: bool
    rows: list[ReplacementValueRow] = field(default_factory=list)

    @property
    def has_problem(self) -> bool:
        return not self.attribute_matched or any(r.is_short or r.over_held for r in self.rows)

    @property
    def calculated_min_sum(self) -> int:
        return sum(r.calculated.min for r in self.rows)

    @property
    def calculated_max_sum(self) -> int:
        return sum(r.calculated.max for r in self.rows)


@dataclass
class ReplacementPlan:
    """Everything the review dialog shows before a replacement selection runs."""

    number_to_select: int
    held_total: int
    categories: list[ReplacementCategory]

    @property
    def calculated_number(self) -> int:
        return max(0, self.number_to_select - self.held_total)

    @property
    def min_select(self) -> int:
        """The library's rule: the largest sum of minimums across categories."""
        if not self.categories:
            return 0
        return max(c.calculated_min_sum for c in self.categories)

    @property
    def max_select(self) -> int:
        """The library's rule: the smallest sum of maximums across categories."""
        if not self.categories:
            return 0
        return min(c.calculated_max_sum for c in self.categories)

    @property
    def number_in_range(self) -> bool:
        return self.min_select <= self.calculated_number <= self.max_select

    @property
    def default_number(self) -> int:
        """The places to fill, pulled to the nearest end of the allowed range if outside it."""
        return min(max(self.calculated_number, self.min_select), self.max_select)

    @property
    def nothing_to_fill(self) -> bool:
        return self.calculated_number == 0

    @property
    def targets_conflict(self) -> bool:
        return self.min_select > self.max_select

    def row_by_value_id(self, value_id: uuid.UUID) -> ReplacementValueRow | None:
        for category in self.categories:
            for row in category.rows:
                if row.value_id == value_id:
                    return row
        return None

    def replacement_info(self, number_used: int, edited: bool) -> dict[str, Any]:
        """The headline arithmetic, stored under settings_used["replacement"] on the run record."""
        return {
            "number_to_select_overall": self.number_to_select,
            "held_total": self.held_total,
            "calculated_number": self.calculated_number,
            "number_to_select_used": number_used,
            "edited": edited,
        }


def _value_row(target: TargetValue, held: int, available: int) -> ReplacementValueRow:
    assert target.value_id is not None
    return ReplacementValueRow(
        value=target.value,
        value_id=target.value_id,
        overall_min=target.min,
        overall_max=target.max,
        held=held,
        calculated=replacement_min_max(target, held),
        available=available,
        percentage_target=target.percentage_target,
        comment=target.comment,
        minmax_manual=target.minmax_manual,
    )


def _build_category(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    attribute_columns: list[str],
) -> ReplacementCategory:
    attribute_name = matching_attribute_column(category.name, attribute_columns)
    held_by_value: dict[str, int] = {}
    available_by_value: dict[str, int] = {}
    if attribute_name:
        held_by_value = uow.respondents.get_selected_attribute_value_counts(assembly_id, attribute_name)
        available_by_value = uow.respondents.get_attribute_value_available_counts(assembly_id, attribute_name)
    return ReplacementCategory(
        name=category.name,
        category_id=category.id,
        sort_order=category.sort_order,
        comment=category.comment,
        source_url=category.source_url,
        attribute_matched=bool(attribute_name),
        rows=[
            _value_row(target, held_by_value.get(target.value, 0), available_by_value.get(target.value, 0))
            for target in category.values
        ],
    )


@require_assembly_permission(can_manage_assembly)
def build_replacement_plan(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> ReplacementPlan:
    """The replacement targets derived from the stored targets and who already holds a place.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if assembly is None:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    status_counts = uow.respondents.count_by_status(assembly_id)
    held_total = sum(status_counts.get(status, 0) for status in SELECTED_RESPONDENT_STATUSES)
    attribute_columns = uow.respondents.get_attribute_columns(assembly_id)
    categories = [
        _build_category(uow, assembly_id, category, attribute_columns)
        for category in uow.target_categories.get_by_assembly_id(assembly_id)
    ]
    return ReplacementPlan(
        number_to_select=assembly.number_to_select,
        held_total=held_total,
        categories=categories,
    )


@dataclass(frozen=True)
class ReplacementSuggestion:
    """One relaxation the algorithm proposes: a minimum lowered or a maximum raised."""

    value_id: uuid.UUID
    category: str
    value: str
    field: str
    current: int
    suggested: int

    @property
    def input_id(self) -> str:
        return f"{self.field}-{self.value_id}"


@dataclass
class FeasibilityResult:
    """Whether the algorithm can meet the targets from the pool, and what it suggests if not.

    ``checked`` is false when an earlier error stopped the solver from running.
    ``message`` carries the library's own text when it found no relaxation,
    or failed for another reason.
    """

    checked: bool = False
    feasible: bool = False
    message: str = ""
    suggestions: list[ReplacementSuggestion] = field(default_factory=list)

    def suggestions_for(self, value_id: uuid.UUID) -> list[ReplacementSuggestion]:
        return [s for s in self.suggestions if s.value_id == value_id]


@dataclass
class ReplacementValidation:
    """The outcome of checking the organiser's submitted numbers.

    ``errors`` are for the top of the dialog; ``value_errors`` sit beside the
    cell they concern, keyed by the value id. ``targets_snapshot`` is what the
    task runs on when there are no errors, in the shape the run record stores.
    ``feasibility`` is set only when the caller asked for the solver check.
    """

    number_to_select: int = 0
    edited: bool = False
    errors: list[str] = field(default_factory=list)
    value_errors: dict[uuid.UUID, list[str]] = field(default_factory=dict)
    targets_snapshot: list[dict[str, Any]] = field(default_factory=list)
    feasibility: FeasibilityResult | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and not self.value_errors

    def add_value_error(self, value_id: uuid.UUID, message: str) -> None:
        self.value_errors.setdefault(value_id, []).append(message)


def _parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_cells(
    plan: ReplacementPlan, form: Mapping[str, str], result: ReplacementValidation
) -> dict[uuid.UUID, tuple[int, int]]:
    """The submitted (min, max) per value id, recording a cell error for anything unusable."""
    submitted: dict[uuid.UUID, tuple[int, int]] = {}
    for category in plan.categories:
        for row in category.rows:
            if row.min_field not in form or row.max_field not in form:
                result.errors.append(_("The targets have changed since this dialog opened. Review them again."))
                return {}
            low = _parse_int(form.get(row.min_field))
            high = _parse_int(form.get(row.max_field))
            if low is None or high is None or low < 0 or high < 0:
                result.add_value_error(row.value_id, _("Enter whole numbers of zero or more"))
                continue
            if high < low:
                result.add_value_error(row.value_id, _("Maximum must be at least the minimum"))
                continue
            submitted[row.value_id] = (low, high)
    return submitted


def _snapshot(plan: ReplacementPlan, submitted: dict[uuid.UUID, tuple[int, int]]) -> list[dict[str, Any]]:
    """The run record's targets snapshot: the used numbers, with the calculated ones beside them."""
    snapshot = []
    for category in plan.categories:
        values = []
        for row in category.rows:
            low, high = submitted[row.value_id]
            calc = row.calculated
            values.append({
                "value": row.value,
                "min": low,
                "max": high,
                "min_flex": min(calc.min_flex, low),
                "max_flex": MAX_FLEX_UNSET if calc.max_flex == MAX_FLEX_UNSET else max(calc.max_flex, high),
                "percentage_target": row.percentage_target,
                "comment": row.comment,
                "minmax_manual": row.minmax_manual,
                "overall_min": row.overall_min,
                "overall_max": row.overall_max,
                "held": row.held,
                "calculated_min": calc.min,
                "calculated_max": calc.max,
                "calculated_min_flex": calc.min_flex,
                "calculated_max_flex": calc.max_flex,
            })
        snapshot.append({
            "name": category.name,
            "sort_order": category.sort_order,
            "comment": category.comment,
            "source_url": category.source_url,
            "values": values,
        })
    return snapshot


def _cross_category_messages(issues: list[Any]) -> list[str]:
    messages: list[str] = []
    for issue in issues:
        if issue.issue_type == "inconsistent_min_max":
            messages.append(
                _(
                    "The targets cannot all be met at once: %(needs)s needs at least %(min)s "
                    "but %(allows)s allows at most %(max)s",
                    needs=issue.largest_minimum_feature,
                    min=issue.largest_minimum_value,
                    allows=issue.smallest_maximum_feature,
                    max=issue.smallest_maximum_value,
                )
            )
        elif issue.issue_type == "min_exceeds_number_to_select":
            messages.append(
                _(
                    "%(category)s needs at least %(sum)s replacements, more than the %(number)s to select",
                    category=issue.feature_name,
                    sum=issue.feature_sum,
                    number=issue.limit,
                )
            )
        elif issue.issue_type == "max_below_number_to_select":
            messages.append(
                _(
                    "%(category)s allows at most %(sum)s replacements, fewer than the %(number)s to select",
                    category=issue.feature_name,
                    sum=issue.feature_sum,
                    number=issue.limit,
                )
            )
    return messages


def _selection_settings(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> SelectionSettings:
    assembly = uow.assemblies.get(assembly_id)
    assert assembly is not None
    stored: SelectionSettings | None = assembly.selection_settings
    if stored is not None:
        return stored
    return SelectionSettings.for_assembly(assembly)


def validate_replacement_form(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    plan: ReplacementPlan,
    form: Mapping[str, str],
    *,
    check_feasibility: bool = False,
) -> ReplacementValidation:
    """Check the submitted replacement targets and number the way the algorithm will.

    Structural problems (bad cells, a bad number) come back first. Then the
    edited targets are loaded through the same adapter the task uses, and the
    library's own checks run over them and over the pool: categories that
    conflict, a number outside their range, and values the pool cannot fill.
    Every one of these would fail the task moments later, so they all block.

    With ``check_feasibility`` the solver then tries the targets together over
    the pool the run will see, and reports the relaxations it suggests. It runs
    even when a value falls short of the pool, since the suggestion is how to
    get past that; only errors the library itself would refuse stop it. That
    outcome informs rather than blocks: the organiser may still run.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    result = ReplacementValidation()
    if check_feasibility:
        result.feasibility = FeasibilityResult()

    number = _parse_int(form.get("number_to_select"))
    if number is None or number < 1:
        result.errors.append(_("Enter a whole number of replacements to select, one or more"))
    else:
        result.number_to_select = number

    submitted = _parse_cells(plan, form, result)
    if not result.ok:
        return result

    result.edited = any(
        submitted[row.value_id] != (row.calculated.min, row.calculated.max)
        for category in plan.categories
        for row in category.rows
    )
    result.targets_snapshot = _snapshot(plan, submitted)

    try:
        settings_obj = _selection_settings(uow, assembly_id).to_settings(id_column=DB_ID_COLUMN)
    except SortitionBaseError as e:
        result.errors.append(translate_sortition_error(e))
        return result

    select_data = adapters.SelectionData(OpenDLPDataAdapter(uow, assembly_id, targets_snapshot=result.targets_snapshot))
    try:
        features, _f_report = select_data.load_features(number_to_select=0)
    except SortitionBaseError as e:
        result.errors.append(translate_sortition_error(e))
        return result

    issues = report_min_max_error_details_structured(features)
    issues += report_min_max_against_number_to_select_structured(features, result.number_to_select)
    result.errors.extend(_cross_category_messages(issues))

    try:
        people, _p_report = select_data.load_people(settings_obj, features)
        already_selected, _a_report = select_data.load_already_selected(settings_obj)
    except SortitionBaseError as e:
        result.errors.append(translate_sortition_error(e))
        return result
    people = exclude_matching_selected_addresses(people, already_selected, settings_obj)

    for issue in check_people_per_feature_value(features, people):
        row = _row_by_name(plan, issue.feature_name, issue.value_name)
        message = _(
            "Needs at least %(min)s but only %(count)s eligible people with this value remain in the pool",
            min=issue.min_required,
            count=issue.actual_count,
        )
        if row is None:
            result.errors.append(message)
        else:
            result.add_value_error(row.value_id, message)

    if result.feasibility is not None and not result.errors:
        result.feasibility = _check_feasibility(plan, features, people, result.number_to_select, settings_obj)
    return result


def check_replacement_plan(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, plan: ReplacementPlan
) -> ReplacementValidation:
    """Validate the dialog as it opens: the calculated targets, the default number, and the solver check.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    form = {"number_to_select": str(plan.default_number)}
    for category in plan.categories:
        for row in category.rows:
            form[row.min_field] = str(row.calculated.min)
            form[row.max_field] = str(row.calculated.max)
    return validate_replacement_form(uow, assembly_id, plan, form, check_feasibility=True)


def _check_feasibility(
    plan: ReplacementPlan,
    features: FeatureCollection,
    people: People,
    number_to_select: int,
    settings_obj: Settings,
) -> FeasibilityResult:
    result = FeasibilityResult(checked=True)
    if people.count < number_to_select:
        result.message = _(
            "Only %(count)s eligible people are in the pool, fewer than the %(number)s to select",
            count=people.count,
            number=number_to_select,
        )
        return result
    try:
        setup_committee_generation(
            features=features,
            people=people,
            number_people_wanted=number_to_select,
            check_same_address_columns=settings_obj.check_same_address_columns
            if settings_obj.check_same_address
            else [],
            solver_backend=settings_obj.solver_backend,
        )
    except InfeasibleQuotasError as e:
        result.suggestions = _suggestions(plan, features, e.features)
        if not result.suggestions:
            result.message = translate_sortition_error(e)
    except SortitionBaseError as e:
        result.message = translate_sortition_error(e)
    else:
        result.feasible = True
    return result


def _suggestions(
    plan: ReplacementPlan, original: FeatureCollection, relaxed: FeatureCollection
) -> list[ReplacementSuggestion]:
    suggestions: list[ReplacementSuggestion] = []
    for category_name, value_name, original_fv in iterate_feature_collection(original):
        row = _row_by_name(plan, category_name, value_name)
        if row is None or category_name not in relaxed or value_name not in relaxed[category_name]:
            continue
        relaxed_fv = relaxed[category_name][value_name]
        if relaxed_fv.min < original_fv.min:
            suggestions.append(
                ReplacementSuggestion(row.value_id, category_name, value_name, "min", original_fv.min, relaxed_fv.min)
            )
        if relaxed_fv.max > original_fv.max:
            suggestions.append(
                ReplacementSuggestion(row.value_id, category_name, value_name, "max", original_fv.max, relaxed_fv.max)
            )
    return suggestions


def _row_by_name(plan: ReplacementPlan, category_name: str, value_name: str) -> ReplacementValueRow | None:
    for category in plan.categories:
        if category.name.lower() != category_name.lower():
            continue
        for row in category.rows:
            if row.value == value_name:
                return row
    return None
