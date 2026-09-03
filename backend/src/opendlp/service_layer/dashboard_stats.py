"""ABOUTME: MOCK service layer for the assembly results dashboard (ticket 886).
ABOUTME: Returns representative fixture data so the front-end can be built before Hamish writes the real queries."""

# =============================================================================
# ⚠️  MOCK / STUB MODULE — ticket 886 (results dashboard)
# =============================================================================
# Every function here returns DETERMINISTIC FIXTURE DATA. None of it queries the
# respondent pool or computes real target feasibility — that business logic is
# Hamish's to implement when he is back. The value of this module is the *shape*
# it pins down: the dataclasses below are the contract the dashboard front-end
# binds to, so the two halves can be built in parallel and reconciled later.
#
# What is real vs. mocked:
#   * assembly title + number_to_select are read from the existing repository
#     (no new logic — these fields already exist on the Assembly aggregate);
#   * per-status respondent counts, per-category pool breakdowns, unmet targets
#     and the export payload are ALL fabricated fixtures.
#
# Decisions that still need Hamish / a human (documented in
# docs/agent/886-dashboard/service_layer_spec.md — kept as CONFIRM notes):
#   1. Pool-vs-run scope: is the dashboard a live view of the current pool, or a
#      post-selection report? The mock assumes LIVE POOL (matches "only 8 have
#      signed up so far"), with selected counts omitted until a run exists.
#   2. Which RespondentStatus values count toward the headline pool total.
#   3. Feasibility semantics: simple per-value shortfall (mocked here) vs. the
#      joint-quota InfeasibleQuotasError machinery in target_checking.py.
#   4. xlsx export is a genuine gap — tabular_export.py has CSV + GSheet targets
#      but no xlsx one. export_assembly_dashboard() documents this.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InvalidSelection

if TYPE_CHECKING:
    import uuid

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


def _assembly_facts(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> tuple[str, int]:
    """Read the two real, already-persisted fields the dashboard needs.

    This is the only part of the mock that touches the database, and it adds no
    new business logic — ``title`` and ``number_to_select`` are plain columns on
    the Assembly aggregate.
    """
    assembly = uow.assemblies.get(assembly_id)
    if assembly is None:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return assembly.title, assembly.number_to_select


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


def get_assembly_dashboard_summary(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> DashboardSummary:
    """MOCK: headline stats for the dashboard's stat-tile row.

    REAL implementation (Hamish): count respondents per RespondentStatus for the
    assembly and total the live-pool statuses. Assumes the caller has already
    checked can_view_assembly()/permissions in the entrypoint.
    """
    title, number_to_select = _assembly_facts(uow, assembly_id)

    # Fixture per-status counts — one entry per status so the shape is complete.
    mock_counts = {
        RespondentStatus.TEST_SUBMISSION: 3,
        RespondentStatus.POOL: 42,
        RespondentStatus.SELECTED: 0,
        RespondentStatus.CONFIRMED: 0,
        RespondentStatus.WITHDRAWN: 2,
        RespondentStatus.DELETED: 1,
    }
    status_counts = [StatusCount(status=status.value, count=count) for status, count in mock_counts.items()]

    categories = _mock_categories()

    return DashboardSummary(
        assembly_id=str(assembly_id),
        assembly_title=title,
        number_to_select=number_to_select,
        target_category_count=len(categories),
        # CONFIRM (decision 2): which statuses count. Mock counts the live pool.
        total_respondents=mock_counts[RespondentStatus.POOL] + mock_counts[RespondentStatus.WITHDRAWN],
        status_counts=status_counts,
    )


def get_assembly_dashboard_report(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> DashboardReport:
    """MOCK: the full per-category results table plus the unmet-targets list.

    REAL implementation (Hamish): for each recorded target category, count the
    pool respondents holding each value and derive the shortfall. The rows are
    also what the front-end draws the pie charts from.
    """
    title, number_to_select = _assembly_facts(uow, assembly_id)
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

    title, _number_to_select = _assembly_facts(uow, assembly_id)
    slug = title.lower().replace(" ", "-") or "assembly"

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
