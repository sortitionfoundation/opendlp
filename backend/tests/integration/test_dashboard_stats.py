"""ABOUTME: Integration tests for the assembly results dashboard services.
ABOUTME: Exercises the real respondent counting against a database."""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentStatus
from opendlp.service_layer.dashboard_stats import get_assembly_dashboard_summary
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import grant_user_assembly_role


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
