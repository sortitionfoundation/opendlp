"""ABOUTME: BDD tests for Selection History (Phase 5)
ABOUTME: Tests the selection history display, pagination, and view details functionality"""

import uuid
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/selection-history.feature")


# =============================================================================
# Given Steps
# =============================================================================


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: ensure admin user is logged in."""
    # The admin_logged_in_page fixture handles the login
    pass


@given("an assembly with gsheet configured but no selection runs", target_fixture="test_assembly")
def assembly_with_no_history(assembly_gsheet_creator):
    """Create an assembly with gsheet but no selection runs."""
    assembly, _gsheet = assembly_gsheet_creator(title="Empty History Assembly")
    return assembly


@given("an assembly with several selection runs", target_fixture="test_assembly")
def assembly_with_selection_runs(assembly_gsheet_creator, test_database, admin_user):
    """Create an assembly with 3 selection run records."""
    assembly, _gsheet = assembly_gsheet_creator(title="History Test Assembly")
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    with uow:
        for i in range(3):
            run_record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.COMPLETED if i % 2 == 0 else SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.SELECT_GSHEET if i == 0 else SelectionTaskType.LOAD_GSHEET,
                user_id=admin_user.id,
                comment=f"Test run {i}",
                created_at=datetime.now(UTC) - timedelta(hours=i),
                completed_at=datetime.now(UTC) - timedelta(hours=i) + timedelta(minutes=5),
            )
            uow.selection_run_records.add(run_record)
        uow.commit()

    return assembly


@given("an assembly with more than 15 selection runs", target_fixture="test_assembly")
def assembly_with_many_runs(assembly_with_many_runs_and_gsheet):
    """Use fixture that creates an assembly with 100 selection runs."""
    return assembly_with_many_runs_and_gsheet


@given("an assembly with a completed selection run", target_fixture="test_assembly")
def assembly_with_completed_run(assembly_gsheet_creator, test_database, admin_user, request):
    """Create an assembly with a single completed selection run."""
    assembly, _gsheet = assembly_gsheet_creator(title="View Details Assembly")
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    run_id = uuid.uuid4()
    with uow:
        run_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            user_id=admin_user.id,
            comment="Completed test run",
            created_at=datetime.now(UTC) - timedelta(hours=1),
            completed_at=datetime.now(UTC),
        )
        uow.selection_run_records.add(run_record)
        uow.commit()

    # Store run_id on the request for use in verification step
    request.node.run_id = run_id
    return assembly


@given("an assembly with runs in different statuses", target_fixture="test_assembly")
def assembly_with_various_statuses(assembly_gsheet_creator, test_database, admin_user):
    """Create an assembly with runs in all possible statuses."""
    assembly, _gsheet = assembly_gsheet_creator(title="Status Tags Assembly")
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    statuses = [
        SelectionRunStatus.COMPLETED,
        SelectionRunStatus.FAILED,
        SelectionRunStatus.CANCELLED,
        SelectionRunStatus.RUNNING,
        SelectionRunStatus.PENDING,
    ]

    with uow:
        for i, status in enumerate(statuses):
            run_record = SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=status,
                task_type=SelectionTaskType.SELECT_GSHEET,
                user_id=admin_user.id,
                comment=f"{status.value} run",
                created_at=datetime.now(UTC) - timedelta(hours=i),
            )
            uow.selection_run_records.add(run_record)
        uow.commit()

    return assembly


# =============================================================================
# When Steps
# =============================================================================


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    """Navigate to the selection page for the test assembly."""
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(test_assembly.id))


@when("the user clicks the Next pagination link")
def user_clicks_next(admin_logged_in_page: Page):
    """Click the Next pagination link."""
    page = admin_logged_in_page
    page.get_by_role("link", name="Next").click()
    page.wait_for_load_state()


@when("the user clicks the Previous pagination link")
def user_clicks_previous(admin_logged_in_page: Page):
    """Click the Previous pagination link."""
    page = admin_logged_in_page
    page.get_by_role("link", name="Previous").click()
    page.wait_for_load_state()


@when("the user clicks View on a history record")
def user_clicks_view_link(admin_logged_in_page: Page):
    """Click the View link on a history record."""
    page = admin_logged_in_page
    # Use exact=True to match only "View" and not "View Details Assembly..."
    page.get_by_role("link", name="View", exact=True).click()
    page.wait_for_load_state()


# =============================================================================
# Then Steps
# =============================================================================


@then("the empty state message is displayed")
def empty_state_displayed(admin_logged_in_page: Page):
    """Verify the empty state message is shown."""
    page = admin_logged_in_page
    expect(page.get_by_text("No selection runs yet")).to_be_visible()
    expect(page.get_by_text("Run your first selection above to see the history here.")).to_be_visible()


@then("the history table displays all runs with correct details")
def history_table_displayed(admin_logged_in_page: Page):
    """Verify the history table is visible with correct headers."""
    page = admin_logged_in_page
    expect(page.get_by_role("heading", name="Selection History")).to_be_visible()

    # Verify table headers
    expect(page.get_by_role("columnheader", name="Status")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Task Type")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Started By")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Started At")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Completed At")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Comment")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Actions")).to_be_visible()

    # Verify first run is displayed with correct status
    expect(page.get_by_text("Completed").first).to_be_visible()
    expect(page.get_by_text("Test run 0")).to_be_visible()


@then("the View links are present")
def view_links_present(admin_logged_in_page: Page):
    """Verify View links are present in the history table."""
    page = admin_logged_in_page
    view_links = page.get_by_role("link", name="View")
    expect(view_links.first).to_be_visible()


@then("the first page is displayed with 15 runs")
@then("the first page is displayed")
def first_page_displayed(admin_logged_in_page: Page):
    """Verify first page of pagination is displayed."""
    page = admin_logged_in_page
    expect(page.get_by_text("Showing 1-15 of 100 runs")).to_be_visible()


@then("the Next pagination link is visible")
def next_link_visible(admin_logged_in_page: Page):
    """Verify Next pagination link is visible."""
    page = admin_logged_in_page
    expect(page.get_by_role("link", name="Next")).to_be_visible()


@then("the Previous pagination is disabled")
def previous_disabled(admin_logged_in_page: Page):
    """Verify Previous pagination is disabled (shown as span, not link)."""
    page = admin_logged_in_page
    expect(page.locator("nav span").filter(has_text="Previous")).to_be_visible()


@then("the second page is displayed")
def second_page_displayed(admin_logged_in_page: Page):
    """Verify second page of pagination is displayed."""
    page = admin_logged_in_page
    expect(page.get_by_text("Showing 16-30 of 100 runs")).to_be_visible()


@then("the Previous pagination link is visible")
def previous_link_visible(admin_logged_in_page: Page):
    """Verify Previous pagination link is visible."""
    page = admin_logged_in_page
    expect(page.get_by_role("link", name="Previous")).to_be_visible()


@then("the user is redirected to the selection run details page")
def redirected_to_run_details(admin_logged_in_page: Page, request):
    """Verify user is redirected to the selection run details page."""
    page = admin_logged_in_page
    run_id = request.node.run_id
    # The URL format is /assembly/{assembly_id}/selection/history/{run_id}
    assert str(run_id) in page.url


@then("each status is displayed in the history table")
def all_statuses_displayed(admin_logged_in_page: Page):
    """Verify all status texts are visible in the history table."""
    page = admin_logged_in_page
    history_table = page.locator("table")
    expect(history_table.get_by_text("Completed").first).to_be_visible()
    expect(history_table.get_by_text("Failed").first).to_be_visible()
    expect(history_table.get_by_text("Cancelled").first).to_be_visible()
    expect(history_table.get_by_text("Running").first).to_be_visible()
    expect(history_table.get_by_text("Pending").first).to_be_visible()
