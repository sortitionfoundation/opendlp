"""ABOUTME: Integration tests for the assembly results dashboard services.
ABOUTME: Exercises the real respondent counting against a database."""

import uuid

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget, ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, GSheetExportKind, RespondentStatus
from opendlp.service_layer.dashboard_stats import (
    EXPORT_KIND,
    export_dashboard_report,
    export_dashboard_report_to_gsheet,
    get_assembly_dashboard_report,
    get_assembly_dashboard_summary,
    get_dashboard_gsheet_config,
)
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import grant_user_assembly_role
from tests.fakes import FakeGSheetExportTarget


@pytest.fixture
def uow(postgres_session_factory):
    """An already-entered UnitOfWork; the whole test is one transaction."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as entered:
        yield entered


@pytest.fixture
def admin_user(uow):
    user = User(email="dash-admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    uow.users.add(user)
    detached = user.create_detached_copy()
    uow.commit()
    return detached


@pytest.fixture
def outsider(uow):
    """A user with no global role and no role on the assembly."""
    user = User(email="dash-outsider@test.com", global_role=GlobalRole.USER, password_hash="hash123")
    uow.users.add(user)
    detached = user.create_detached_copy()
    uow.commit()
    return detached


@pytest.fixture
def assembly(uow):
    assembly = Assembly(title="Dashboard Assembly", question="Should we?", number_to_select=30)
    uow.assemblies.add(assembly)
    detached = assembly.create_detached_copy()
    uow.commit()
    return detached


@pytest.fixture
def gender_category(uow, assembly):
    category = TargetCategory(
        assembly_id=assembly.id,
        name="Gender",
        values=[
            TargetValue(value="Male", min=14, max=16, percentage_target=50.0),
            TargetValue(value="Female", min=14, max=16, percentage_target=50.0),
        ],
    )
    uow.target_categories.add(category)
    detached = category.create_detached_copy()
    uow.commit()
    return detached


def _add_respondents(uow, assembly_id, status, count, attributes=None):
    for index in range(count):
        uow.respondents.add(
            Respondent(
                assembly_id=assembly_id,
                external_id=f"{status.value}-{index}-{uuid.uuid4().hex[:6]}",
                selection_status=status,
                attributes=attributes,
            )
        )
    uow.commit()


class TestTheSummaryCounts:
    def test_totals_the_headline_statuses_only(self, uow, admin_user, assembly):
        """Test submissions and deleted respondents are not registrations we report."""
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 5)
        _add_respondents(uow, assembly.id, RespondentStatus.SELECTED, 3)
        _add_respondents(uow, assembly.id, RespondentStatus.CONFIRMED, 2)
        _add_respondents(uow, assembly.id, RespondentStatus.WITHDRAWN, 1)
        _add_respondents(uow, assembly.id, RespondentStatus.TEST_SUBMISSION, 4)
        _add_respondents(uow, assembly.id, RespondentStatus.DELETED, 6)

        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert summary.total_respondents == 11

    def test_reports_every_status_including_the_empty_ones(self, uow, admin_user, assembly):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 2)

        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert [(row.status, row.count) for row in summary.status_counts] == [
            ("TEST_SUBMISSION", 0),
            ("POOL", 2),
            ("SELECTED", 0),
            ("CONFIRMED", 0),
            ("WITHDRAWN", 0),
            ("DELETED", 0),
        ]

    def test_counts_deleted_respondents_in_the_breakdown(self, uow, admin_user, assembly):
        """They are excluded from the total but still shown, so the numbers explain themselves."""
        _add_respondents(uow, assembly.id, RespondentStatus.DELETED, 3)

        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert summary.total_respondents == 0
        assert {row.status: row.count for row in summary.status_counts}["DELETED"] == 3

    def test_counts_only_this_assembly(self, uow, admin_user, assembly):
        other = Assembly(title="Other", question="?", number_to_select=10)
        uow.assemblies.add(other)
        uow.commit()
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 2)
        _add_respondents(uow, other.id, RespondentStatus.POOL, 7)

        assert get_assembly_dashboard_summary(uow, admin_user.id, assembly.id).total_respondents == 2

    def test_an_assembly_with_no_respondents_is_all_zeros(self, uow, admin_user, assembly):
        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert summary.total_respondents == 0
        assert all(row.count == 0 for row in summary.status_counts)


class TestTheSummaryAssemblyFacts:
    def test_reads_the_title_and_seat_count_from_the_assembly(self, uow, admin_user, assembly):
        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert summary.assembly_id == str(assembly.id)
        assert summary.assembly_title == "Dashboard Assembly"
        assert summary.number_to_select == 30

    def test_counts_the_target_categories(self, uow, admin_user, assembly, gender_category):
        summary = get_assembly_dashboard_summary(uow, admin_user.id, assembly.id)

        assert summary.target_category_count == 1

    def test_an_assembly_with_no_targets_has_no_categories(self, uow, admin_user, assembly):
        assert get_assembly_dashboard_summary(uow, admin_user.id, assembly.id).target_category_count == 0

    def test_a_missing_assembly_is_reported_as_not_found(self, uow, admin_user):
        with pytest.raises(AssemblyNotFoundError):
            get_assembly_dashboard_summary(uow, admin_user.id, uuid.uuid4())


class TestTheSummaryPermissions:
    def test_a_user_with_no_role_on_the_assembly_is_refused(self, uow, outsider, assembly):
        with pytest.raises(InsufficientPermissions):
            get_assembly_dashboard_summary(uow, outsider.id, assembly.id)

    def test_a_confirmation_caller_may_view(self, uow, outsider, assembly, admin_user):
        """View permission is the lowest bar - any role on the assembly is enough."""
        grant_user_assembly_role(uow, outsider.id, assembly.id, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        assert get_assembly_dashboard_summary(uow, outsider.id, assembly.id).assembly_title == "Dashboard Assembly"


class TestTheReportCounts:
    def test_counts_the_respondents_holding_each_target_value(self, uow, admin_user, assembly, gender_category):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 6, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 9, attributes={"Gender": "Female"})
        _add_respondents(uow, assembly.id, RespondentStatus.CONFIRMED, 2, attributes={"Gender": "Male"})

        report = get_assembly_dashboard_report(uow, admin_user.id, assembly.id)

        rows = {row.value: row for row in report.categories[0].rows}
        assert rows["Male"].pool_count == 8
        assert rows["Male"].confirmed_count == 2
        assert rows["Female"].pool_count == 9

    def test_the_available_count_excludes_those_ruled_out(self, uow, admin_user, assembly, gender_category):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 4, attributes={"Gender": "Male"})
        uow.respondents.add(
            Respondent(
                assembly_id=assembly.id,
                external_id="INELIGIBLE",
                selection_status=RespondentStatus.POOL,
                attributes={"Gender": "Male"},
                eligible=False,
            )
        )
        uow.commit()

        rows = {
            row.value: row for row in get_assembly_dashboard_report(uow, admin_user.id, assembly.id).categories[0].rows
        }
        assert rows["Male"].pool_count == 5
        assert rows["Male"].available_count == 4

    def test_the_shortfall_follows_the_available_count(self, uow, admin_user, assembly, gender_category):
        """Target min is 14; four available means ten short, whatever the wider pool says."""
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 4, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.WITHDRAWN, 20, attributes={"Gender": "Male"})

        rows = {
            row.value: row for row in get_assembly_dashboard_report(uow, admin_user.id, assembly.id).categories[0].rows
        }
        assert rows["Male"].shortfall == 10
        assert rows["Male"].meetable is False

    def test_matches_the_attribute_column_loosely(self, uow, admin_user, assembly):
        """A "Gender Identity" category finds a gender_identity column."""
        category = TargetCategory(
            assembly_id=assembly.id,
            name="Gender Identity",
            values=[TargetValue(value="Male", min=1, max=2)],
        )
        uow.target_categories.add(category)
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 3, attributes={"gender_identity": "Male"})

        report = get_assembly_dashboard_report(uow, admin_user.id, assembly.id)

        assert report.categories[0].rows[0].pool_count == 3

    def test_reports_respondents_whose_value_is_not_a_target(self, uow, admin_user, assembly, gender_category):
        """An unknown value is counted, not raised over - one bad cell must not break the page."""
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 2, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 3, attributes={"Gender": "Prefer not to say"})

        report = get_assembly_dashboard_report(uow, admin_user.id, assembly.id)

        assert report.categories[0].unmatched_count == 3
        assert [row.value for row in report.categories[0].rows] == ["Male", "Female"]

    def test_the_pool_size_counts_the_whole_assembly_once(self, uow, admin_user, assembly, gender_category):
        """Not a sum over categories, which would multiply-count a respondent."""
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 5, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.WITHDRAWN, 3, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.DELETED, 2, attributes={"Gender": "Male"})

        assert get_assembly_dashboard_report(uow, admin_user.id, assembly.id).pool_size == 5

    def test_an_assembly_with_no_targets_has_no_categories(self, uow, admin_user, assembly):
        report = get_assembly_dashboard_report(uow, admin_user.id, assembly.id)

        assert report.categories == []
        assert report.unmet_targets == []


class TestTheUnmetTargets:
    def test_lists_every_value_short_of_its_minimum(self, uow, admin_user, assembly, gender_category):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 2, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 14, attributes={"Gender": "Female"})

        report = get_assembly_dashboard_report(uow, admin_user.id, assembly.id)

        assert [(t.value, t.shortfall, t.available_count) for t in report.unmet_targets] == [("Male", 12, 2)]

    def test_is_empty_once_every_target_can_be_met(self, uow, admin_user, assembly, gender_category):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 14, attributes={"Gender": "Male"})
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 14, attributes={"Gender": "Female"})

        assert get_assembly_dashboard_report(uow, admin_user.id, assembly.id).unmet_targets == []


class TestTheReportPermissions:
    def test_a_user_with_no_role_on_the_assembly_is_refused(self, uow, outsider, assembly):
        with pytest.raises(InsufficientPermissions):
            get_assembly_dashboard_report(uow, outsider.id, assembly.id)

    def test_a_missing_assembly_is_reported_as_not_found(self, uow, admin_user):
        with pytest.raises(AssemblyNotFoundError):
            get_assembly_dashboard_report(uow, admin_user.id, uuid.uuid4())


_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


class TestExportingToCsv:
    def test_writes_a_row_per_target_value(self, uow, admin_user, assembly, gender_category):
        _add_respondents(uow, assembly.id, RespondentStatus.POOL, 3, attributes={"Gender": "Male"})
        target = CsvExportTarget()

        export_dashboard_report(uow, admin_user.id, assembly.id, target=target)

        lines = [line for line in target.getvalue().splitlines() if line]
        assert len(lines) == 3
        assert lines[0].lstrip("\ufeff").startswith("Category,Value,")
        assert lines[1].startswith("Gender,Male,")

    def test_an_assembly_with_no_targets_exports_headers_only(self, uow, admin_user, assembly):
        target = CsvExportTarget()

        export_dashboard_report(uow, admin_user.id, assembly.id, target=target)

        assert len([line for line in target.getvalue().splitlines() if line]) == 1

    def test_a_user_who_can_only_view_may_not_export(self, uow, outsider, assembly, admin_user):
        """Export is a manage action, matching the respondent export."""
        grant_user_assembly_role(uow, outsider.id, assembly.id, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        with pytest.raises(InsufficientPermissions):
            export_dashboard_report(uow, outsider.id, assembly.id, target=CsvExportTarget())


class TestExportingToGoogleSheets:
    def test_writes_the_sheet_and_saves_the_config(self, uow, admin_user, assembly, gender_category):
        target = FakeGSheetExportTarget()

        export_dashboard_report_to_gsheet(
            uow,
            admin_user.id,
            assembly.id,
            spreadsheet_url=_SHEET_URL,
            worksheet_name="Q3 results",
            target=target,
        )

        assert [title for title, _table in target.writes] == ["Q3 results"]
        saved = get_dashboard_gsheet_config(uow, admin_user.id, assembly.id)
        assert saved is not None
        assert saved.url == _SHEET_URL
        assert saved.worksheet_name == "Q3 results"
        assert saved.worksheet_url == target.result_url

    def test_an_empty_worksheet_name_falls_back_to_the_default(self, uow, admin_user, assembly, gender_category):
        target = FakeGSheetExportTarget()

        export_dashboard_report_to_gsheet(
            uow, admin_user.id, assembly.id, spreadsheet_url=_SHEET_URL, worksheet_name="  ", target=target
        )

        assert [title for title, _table in target.writes] == ["Results"]

    def test_a_failed_write_saves_no_config(self, uow, admin_user, assembly, gender_category):
        target = FakeGSheetExportTarget(error=ExportTargetError("no access"))

        with pytest.raises(ExportTargetError):
            export_dashboard_report_to_gsheet(
                uow, admin_user.id, assembly.id, spreadsheet_url=_SHEET_URL, worksheet_name="Results", target=target
            )

        assert uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, EXPORT_KIND) is None

    def test_a_second_export_updates_the_saved_config(self, uow, admin_user, assembly, gender_category):
        for worksheet_name in ("First", "Second"):
            export_dashboard_report_to_gsheet(
                uow,
                admin_user.id,
                assembly.id,
                spreadsheet_url=_SHEET_URL,
                worksheet_name=worksheet_name,
                target=FakeGSheetExportTarget(),
            )

        assert len(list(uow.assembly_export_gsheets.all())) == 1
        saved = get_dashboard_gsheet_config(uow, admin_user.id, assembly.id)
        assert saved.worksheet_name == "Second"

    def test_the_dashboard_sheet_is_separate_from_the_respondent_sheet(
        self,
        uow,
        admin_user,
        assembly,
        gender_category,
    ):
        """Respondent data is personal; dashboard data may be published. Never one row."""
        export_dashboard_report_to_gsheet(
            uow,
            admin_user.id,
            assembly.id,
            spreadsheet_url=_SHEET_URL,
            worksheet_name="Results",
            target=FakeGSheetExportTarget(),
        )

        assert uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, GSheetExportKind.RESPONDENTS) is None
        assert uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, GSheetExportKind.DASHBOARD) is not None

    def test_there_is_no_saved_config_before_the_first_export(self, uow, admin_user, assembly):
        assert get_dashboard_gsheet_config(uow, admin_user.id, assembly.id) is None
