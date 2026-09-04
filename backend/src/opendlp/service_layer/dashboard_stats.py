"""ABOUTME: Service layer for the assembly results dashboard (ticket 886).
ABOUTME: Headline respondent counts, the per-category results table, and its export."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opendlp.adapters.tabular_export import (
    AbstractGSheetExportTarget,
    AbstractTabularExportTarget,
    TabularData,
)
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet, default_worksheet_name
from opendlp.domain.respondents import normalise_field_name
from opendlp.domain.targets import percentage_of
from opendlp.domain.value_objects import (
    COUNTED_RESPONDENT_STATUSES,
    HEADLINE_RESPONDENT_STATUSES,
    SELECTED_RESPONDENT_STATUSES,
    GSheetExportKind,
    RespondentStatus,
)
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.export_gsheet_config import save_export_gsheet_config
from opendlp.service_layer.permissions import (
    can_manage_assembly,
    can_view_assembly,
    require_assembly_permission,
)
from opendlp.translations import gettext as _

if TYPE_CHECKING:
    import uuid

    from opendlp.domain.assembly import Assembly
    from opendlp.domain.targets import TargetCategory, TargetValue
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


EXPORT_KIND = GSheetExportKind.DASHBOARD


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


def _format_pct(value: float) -> str:
    return f"{value:.1f}"


def _export_row(category_name: str, row: CategoryValueRow, totals: tuple[int, int, int]) -> list[str]:
    pool_total, selected_total, confirmed_total = totals
    return [
        category_name,
        row.value,
        _format_pct(row.target_pct),
        str(row.target_min),
        str(row.target_max),
        str(row.pool_count),
        _format_pct(percentage_of(row.pool_count, pool_total)),
        str(row.available_count),
        str(row.selected_count),
        _format_pct(percentage_of(row.selected_count, selected_total)),
        str(row.confirmed_count),
        _format_pct(percentage_of(row.confirmed_count, confirmed_total)),
        str(row.shortfall),
    ]


def _unmatched_row(category: DashboardCategory) -> list[str]:
    """Respondents whose value the category does not declare.

    Carried into the export rather than dropped, so the sheet does not quietly
    understate how many respondents the category covers. No target band applies.
    """
    blanks = [""] * 7
    return [category.name, _("Not in targets"), "", "", "", str(category.unmatched_count), *blanks]


def build_dashboard_table(report: DashboardReport) -> TabularData:
    """Flatten a report into one row per target value, ready for any export target.

    Flat rather than a block per category: ``write_sheet`` takes a single table of
    uniform width, and preamble rows above the header would break sorting and
    filtering in the Google Sheet this shares its export path with.

    Percentages are computed here rather than stored on the row, over the
    category's declared values - the same denominator the pie charts use.
    """
    headers = [
        _("Category"),
        _("Value"),
        _("Target %"),
        _("Target min"),
        _("Target max"),
        _("Respondents"),
        _("Respondents %"),
        _("Available to select"),
        _("Selected"),
        _("Selected %"),
        _("Confirmed"),
        _("Confirmed %"),
        _("Shortfall"),
    ]

    rows: list[list[str]] = []
    for category in report.categories:
        totals = (
            sum(row.pool_count for row in category.rows),
            sum(row.selected_count for row in category.rows),
            sum(row.confirmed_count for row in category.rows),
        )
        rows.extend(_export_row(category.name, row, totals) for row in category.rows)
        if category.unmatched_count:
            rows.append(_unmatched_row(category))

    return TabularData(headers=headers, rows=rows)


@require_assembly_permission(can_manage_assembly)
def export_dashboard_report(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    target: AbstractTabularExportTarget,
    sheet_title: str = "",
) -> None:
    """Write the results table to the given target.

    The format is the target: a CsvExportTarget yields CSV, a Google Sheets one
    writes a worksheet. Requires manage permission, matching the respondent
    export.

    An empty ``sheet_title`` means the default for this export kind, resolved
    here rather than as a default argument so it lands in the caller's language.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    sheet_title = sheet_title or default_worksheet_name(EXPORT_KIND)
    report = get_assembly_dashboard_report(uow, user_id, assembly_id)
    target.write_sheet(sheet_title, build_dashboard_table(report))


@require_assembly_permission(can_manage_assembly)
def export_dashboard_report_to_gsheet(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    spreadsheet_url: str,
    worksheet_name: str,
    target: AbstractGSheetExportTarget,
) -> None:
    """Write the results table to a Google Sheet and save the sheet config.

    The config is saved under its own export kind, so this export can have its own
    spreadsheet rather than inheriting the respondent export's - useful because
    this table is aggregate counts an organiser may publish, while that one is
    personal data. Pointing both at one spreadsheet is allowed; keeping the
    personal data private is a matter of how that sheet is shared.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    worksheet_name = worksheet_name.strip() or default_worksheet_name(EXPORT_KIND)

    # Write first so the target's result_title/result_url are populated; only
    # then persist the config, so a failed write saves nothing.
    export_dashboard_report(uow, user_id, assembly_id, target=target, sheet_title=worksheet_name)

    save_export_gsheet_config(
        uow,
        assembly_id,
        EXPORT_KIND,
        spreadsheet_url=spreadsheet_url,
        worksheet_name=worksheet_name,
        target=target,
    )


@require_assembly_permission(can_view_assembly)
def get_dashboard_gsheet_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> AssemblyExportGSheet | None:
    """The saved dashboard-export sheet config, or None before the first export.

    View permission, not manage - deliberately looser than the respondent
    equivalent. That export carries personal data, which is sensitive; this one is
    aggregate counts, which is not. Either way the config is a link to a sheet
    rather than the data in it: whoever the sheet is shared with is what decides
    who can read it.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    return config.create_detached_copy() if config else None
