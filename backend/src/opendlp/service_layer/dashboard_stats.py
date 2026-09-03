"""ABOUTME: Service layer for the assembly results dashboard (ticket 886).
ABOUTME: Headline respondent counts, the per-category results table, and its export."""

# =============================================================================
# ⚠️  export_assembly_dashboard is still a MOCK — ticket 886, phase 5.
# The summary and report services below are real. See
# docs/agent/886-dashboard/service_layer_plan.md.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opendlp.domain.respondents import normalise_field_name
from opendlp.domain.value_objects import (
    COUNTED_RESPONDENT_STATUSES,
    HEADLINE_RESPONDENT_STATUSES,
    SELECTED_RESPONDENT_STATUSES,
    RespondentStatus,
)
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InvalidSelection
from opendlp.service_layer.permissions import can_view_assembly, require_assembly_permission

if TYPE_CHECKING:
    import uuid

    from opendlp.domain.assembly import Assembly
    from opendlp.domain.targets import TargetCategory, TargetValue
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


# The formats the export control offers. gsheet writes to Google Sheets; csv and
# xlsx are file downloads. xlsx has no backend yet — see export_assembly_dashboard.
EXPORT_FORMATS = ("csv", "xlsx", "gsheet")


# -----------------------------------------------------------------------------
# The contract: dataclasses the front-end binds to (serialised with asdict()).
# -----------------------------------------------------------------------------


@dataclass
class StatusCount:
    """How many respondents sit in one RespondentStatus for this assembly."""

    status: str
    count: int


@dataclass
class DashboardSummary:
    """Headline numbers for the stat-tile row at the top of the dashboard."""

    assembly_id: str
    assembly_title: str
    number_to_select: int
    target_category_count: int
    total_respondents: int
    # Every RespondentStatus, in a stable order, so the front-end can render a
    # "number in each state" breakdown without inventing the list itself.
    status_counts: list[StatusCount] = field(default_factory=list)


@dataclass
class CategoryValueRow:
    """One value of one target category: its target band and how the pool fills it.

    Three different populations are counted here and none is interchangeable.
    ``pool_count`` is everyone this value covers who is still one of the
    assembly's respondents; ``available_count`` is the narrower set a selection
    run would actually have to draw on; ``selected_count`` and
    ``confirmed_count`` are what has been drawn so far.
    """

    value: str
    target_min: int
    target_max: int
    # TargetValue.percentage_target where it is set, else the share the band
    # implies within its category.
    target_pct: float
    # COUNTED_RESPONDENT_STATUSES: pool, selected and confirmed.
    pool_count: int
    # In the pool, and neither ineligible nor unable to attend.
    available_count: int
    selected_count: int
    confirmed_count: int
    # max(0, target_min - available_count). > 0 means we cannot yet meet this
    # target - measured over the respondents a selection run could actually pick.
    shortfall: int
    meetable: bool


@dataclass
class DashboardCategory:
    """A target category (e.g. Gender) and the rows for each of its values.

    ``rows`` doubles as the pie-chart series for this category: value -> pool_count.
    """

    name: str
    rows: list[CategoryValueRow] = field(default_factory=list)
    # Respondents holding a value this category does not declare. A miscategorised
    # respondent is invisible in ``rows``, so the count says how many there are
    # rather than letting the table quietly understate itself.
    unmatched_count: int = 0


@dataclass
class UnmetTarget:
    """A single (category, value) whose minimum target the pool cannot yet meet."""

    category: str
    value: str
    target_min: int
    # The count the shortfall was measured over, so the two always agree.
    available_count: int
    shortfall: int


@dataclass
class DashboardReport:
    """The full results table plus the derived "targets we cannot meet" list."""

    assembly_id: str
    assembly_title: str
    number_to_select: int
    pool_size: int
    categories: list[DashboardCategory] = field(default_factory=list)
    unmet_targets: list[UnmetTarget] = field(default_factory=list)


@dataclass
class DashboardExport:
    """The result of asking for the results table in a downloadable form."""

    assembly_id: str
    export_format: str
    filename: str
    # A short human-readable note about what the real service will return for
    # this format (a file blob, a GSheet URL, ...). Mock returns no real bytes.
    note: str
    download_ready: bool


@dataclass
class _DashboardContext:
    """The assembly and its targets, which every dashboard service starts from."""

    assembly: Assembly
    categories: list[TargetCategory]


def _load_dashboard_context(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> _DashboardContext:
    assembly = uow.assemblies.get(assembly_id)
    if assembly is None:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return _DashboardContext(
        assembly=assembly,
        categories=list(uow.target_categories.get_by_assembly_id(assembly_id)),
    )


@require_assembly_permission(can_view_assembly)
def get_assembly_dashboard_summary(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> DashboardSummary:
    """Headline stats for the dashboard's stat-tile row.

    ``status_counts`` carries every RespondentStatus, zeros included, so the
    front-end never has to invent the list. ``total_respondents`` counts the
    headline statuses only, which is wider than the pool the per-category counts
    in the report are measured over — see HEADLINE_RESPONDENT_STATUSES.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    context = _load_dashboard_context(uow, assembly_id)
    counts = uow.respondents.count_by_status(assembly_id)

    return DashboardSummary(
        assembly_id=str(assembly_id),
        assembly_title=context.assembly.title,
        number_to_select=context.assembly.number_to_select,
        target_category_count=len(context.categories),
        total_respondents=sum(counts.get(status, 0) for status in HEADLINE_RESPONDENT_STATUSES),
        status_counts=[StatusCount(status=status.value, count=counts.get(status, 0)) for status in RespondentStatus],
    )


def _matching_attribute(category_name: str, attribute_columns: list[str]) -> str:
    """The respondent attribute a target category is about, or "" if there is none.

    Matched loosely, so a "Age Range" category finds an ``age_range`` column. The
    targets page matches the same names case-insensitively but not loosely, so a
    category can have counts here and none there.
    """
    wanted = normalise_field_name(category_name)
    for column in attribute_columns:
        if normalise_field_name(column) == wanted:
            return column
    return ""


def _value_row(
    target: TargetValue,
    target_pct: float,
    by_status: dict[RespondentStatus, int],
    available_count: int,
) -> CategoryValueRow:
    pool_count = sum(by_status.get(status, 0) for status in COUNTED_RESPONDENT_STATUSES)
    shortfall = max(0, target.min - available_count)
    return CategoryValueRow(
        value=target.value,
        target_min=target.min,
        target_max=target.max,
        target_pct=target_pct,
        pool_count=pool_count,
        available_count=available_count,
        selected_count=sum(by_status.get(status, 0) for status in SELECTED_RESPONDENT_STATUSES),
        confirmed_count=by_status.get(RespondentStatus.CONFIRMED, 0),
        shortfall=shortfall,
        meetable=shortfall == 0,
    )


def _build_category(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    attribute_columns: list[str],
) -> DashboardCategory:
    """One category's rows, counted from the respondents holding each of its values.

    A category whose name matches no respondent attribute yields its declared
    values with zero counts rather than disappearing: the targets are still set,
    there is just nothing to measure them against yet.
    """
    attribute_name = _matching_attribute(category.name, attribute_columns)
    counts_by_value: dict[str, dict[RespondentStatus, int]] = {}
    available_by_value: dict[str, int] = {}
    if attribute_name:
        counts_by_value = uow.respondents.get_attribute_value_counts_by_status(assembly_id, attribute_name)
        available_by_value = uow.respondents.get_attribute_value_available_counts(assembly_id, attribute_name)

    target_pcts = category.percentages_from_minmax()
    rows = [
        _value_row(
            target,
            target.percentage_target if target.percentage_target is not None else fallback_pct,
            counts_by_value.get(target.value, {}),
            available_by_value.get(target.value, 0),
        )
        for target, fallback_pct in zip(category.values, target_pcts, strict=True)
    ]

    declared = {target.value for target in category.values}
    unmatched_count = sum(
        by_status.get(status, 0)
        for value, by_status in counts_by_value.items()
        if value not in declared
        for status in COUNTED_RESPONDENT_STATUSES
    )
    return DashboardCategory(name=category.name, rows=rows, unmatched_count=unmatched_count)


@require_assembly_permission(can_view_assembly)
def get_assembly_dashboard_report(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> DashboardReport:
    """The full per-category results table plus the unmet-targets list.

    A live view of the respondents as they are now - it never reads a
    SelectionRunRecord. Counts come from the respondents' attributes, so a
    category is only populated once respondents carry the matching column.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    context = _load_dashboard_context(uow, assembly_id)
    attribute_columns = uow.respondents.get_attribute_columns(assembly_id)
    categories = [_build_category(uow, assembly_id, category, attribute_columns) for category in context.categories]

    unmet_targets = [
        UnmetTarget(
            category=category.name,
            value=row.value,
            target_min=row.target_min,
            available_count=row.available_count,
            shortfall=row.shortfall,
        )
        for category in categories
        for row in category.rows
        if row.shortfall > 0
    ]

    status_counts = uow.respondents.count_by_status(assembly_id)

    return DashboardReport(
        assembly_id=str(assembly_id),
        assembly_title=context.assembly.title,
        number_to_select=context.assembly.number_to_select,
        pool_size=sum(status_counts.get(status, 0) for status in COUNTED_RESPONDENT_STATUSES),
        categories=categories,
        unmet_targets=unmet_targets,
    )


def export_assembly_dashboard(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    export_format: str,
) -> DashboardExport:
    """MOCK: turn the results table into a downloadable/exported form.

    REAL implementation (Hamish): reuse the tabular_export.py targets.
      * ``csv``    -> CsvExportTarget (exists).
      * ``gsheet`` -> the GSheet export target (exists).
      * ``xlsx``   -> NO BACKEND YET. tabular_export.py has no xlsx target; one
        needs adding behind AbstractTabularExportTarget.write_sheet(). This mock
        returns download_ready=False for xlsx to surface that gap in the UI.
    """
    if export_format not in EXPORT_FORMATS:
        raise InvalidSelection(f"Unknown export format '{export_format}'. Expected one of {EXPORT_FORMATS}.")

    context = _load_dashboard_context(uow, assembly_id)
    slug = context.assembly.title.lower().replace(" ", "-") or "assembly"

    notes = {
        "csv": "Real service returns CSV bytes via CsvExportTarget.",
        "gsheet": "Real service writes a worksheet and returns its URL.",
        "xlsx": "NOT IMPLEMENTED: no xlsx export target exists in tabular_export.py yet.",
    }
    # gsheet has no downloadable file; csv/xlsx name a file with the matching suffix.
    extensions = {"csv": "csv", "xlsx": "xlsx", "gsheet": "gsheet-link"}

    return DashboardExport(
        assembly_id=str(assembly_id),
        export_format=export_format,
        filename=f"{slug}-results.{extensions[export_format]}",
        note=notes[export_format],
        download_ready=export_format != "xlsx",
    )
