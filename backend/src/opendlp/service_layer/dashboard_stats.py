"""ABOUTME: Service layer for the assembly results dashboard (ticket 886).
ABOUTME: Headline respondent counts, the per-category results table, and its export."""

# =============================================================================
# ⚠️  PARTIALLY MOCKED MODULE — ticket 886 (results dashboard)
# =============================================================================
# get_assembly_dashboard_summary is real. get_assembly_dashboard_report and
# export_assembly_dashboard still return fixture data; see
# docs/agent/886-dashboard/service_layer_plan.md for the phases that replace them.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opendlp.domain.value_objects import HEADLINE_RESPONDENT_STATUSES, RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InvalidSelection
from opendlp.service_layer.permissions import can_view_assembly, require_assembly_permission

if TYPE_CHECKING:
    import uuid

    from opendlp.domain.assembly import Assembly
    from opendlp.domain.targets import TargetCategory
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
    """One value of one target category: its target band and how the pool fills it."""

    value: str
    target_min: int
    target_max: int
    pool_count: int
    # max(0, target_min - pool_count). > 0 means we cannot yet meet this target.
    shortfall: int
    meetable: bool


@dataclass
class DashboardCategory:
    """A target category (e.g. Gender) and the rows for each of its values.

    ``rows`` doubles as the pie-chart series for this category: value -> pool_count.
    """

    name: str
    rows: list[CategoryValueRow] = field(default_factory=list)


@dataclass
class UnmetTarget:
    """A single (category, value) whose minimum target the pool cannot yet meet."""

    category: str
    value: str
    target_min: int
    pool_count: int
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


# -----------------------------------------------------------------------------
# Mock services. Real signatures are preserved so Hamish only swaps the bodies.
# -----------------------------------------------------------------------------


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


def _mock_categories() -> list[DashboardCategory]:
    """Deterministic fixture categories, including one deliberately unmet target."""
    return [
        DashboardCategory(
            name="Gender",
            rows=[
                CategoryValueRow("Male", target_min=10, target_max=12, pool_count=8, shortfall=2, meetable=False),
                CategoryValueRow("Female", target_min=10, target_max=12, pool_count=14, shortfall=0, meetable=True),
                CategoryValueRow("Non-binary", target_min=1, target_max=2, pool_count=3, shortfall=0, meetable=True),
            ],
        ),
        DashboardCategory(
            name="Age",
            rows=[
                CategoryValueRow("16-29", target_min=5, target_max=7, pool_count=9, shortfall=0, meetable=True),
                CategoryValueRow("30-44", target_min=5, target_max=7, pool_count=6, shortfall=0, meetable=True),
                CategoryValueRow("45-59", target_min=5, target_max=7, pool_count=5, shortfall=0, meetable=True),
                CategoryValueRow("60+", target_min=5, target_max=7, pool_count=4, shortfall=1, meetable=False),
            ],
        ),
    ]


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


def get_assembly_dashboard_report(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> DashboardReport:
    """MOCK: the full per-category results table plus the unmet-targets list.

    REAL implementation (Hamish): for each recorded target category, count the
    pool respondents holding each value and derive the shortfall. The rows are
    also what the front-end draws the pie charts from.
    """
    context = _load_dashboard_context(uow, assembly_id)
    title, number_to_select = context.assembly.title, context.assembly.number_to_select
    categories = _mock_categories()

    # Unmet targets are a pure projection of the rows: anything with a shortfall.
    unmet_targets = [
        UnmetTarget(
            category=category.name,
            value=row.value,
            target_min=row.target_min,
            pool_count=row.pool_count,
            shortfall=row.shortfall,
        )
        for category in categories
        for row in category.rows
        if row.shortfall > 0
    ]

    pool_size = sum(row.pool_count for category in categories for row in category.rows) // max(len(categories), 1)

    return DashboardReport(
        assembly_id=str(assembly_id),
        assembly_title=title,
        number_to_select=number_to_select,
        pool_size=pool_size,
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
