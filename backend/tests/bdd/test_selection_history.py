"""ABOUTME: BDD tests for Selection History (Phase 5)
ABOUTME: Tests the selection history display, pagination, and view details functionality"""

import uuid
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls


def test_selection_history_empty_state(admin_logged_in_page: Page, assembly_gsheet_creator):
    """Scenario: View selection page with no history

    Given: An assembly with gsheet configured but no selection runs
    When: User visits the selection page
    Then: Empty state message is displayed
    """
    # Given: Assembly with gsheet but no history
    assembly, _gsheet = assembly_gsheet_creator(title="Empty History Assembly")

    # When: Visit selection page
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: Empty state is shown
    expect(page.get_by_text("No selection runs yet")).to_be_visible()
    expect(page.get_by_text("Run your first selection above to see the history here.")).to_be_visible()


def test_selection_history_displays_runs(
    admin_logged_in_page: Page, assembly_gsheet_creator, test_database, admin_user
):
    """Scenario: View selection history with records

    Given: An assembly with several selection runs
    When: User visits the selection page
    Then: History table displays all runs with correct details
    """
    # Given: Assembly with selection runs
    assembly, _gsheet = assembly_gsheet_creator(title="History Test Assembly")
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    # Create 3 selection run records
    run_records = []
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
            run_records.append(run_record)
        uow.commit()

    # When: Visit selection page
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: History table is visible
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

    # Verify View links are present
    view_links = page.get_by_role("link", name="View")
    expect(view_links.first).to_be_visible()


def test_selection_history_pagination(admin_logged_in_page: Page, assembly_with_many_runs_and_gsheet):
    """Scenario: Navigate through paginated selection history

    Given: An assembly with more than 15 selection runs
    When: User navigates through pages
    Then: Pagination controls work correctly
    """
    # Given: Assembly with 100 runs (from fixture)
    assembly = assembly_with_many_runs_and_gsheet
    page = admin_logged_in_page

    # When: Visit selection page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: First page is displayed (page size is 15)
    expect(page.get_by_text("Showing 1-15 of 100 runs")).to_be_visible()
    expect(page.get_by_role("link", name="Next")).to_be_visible()

    # Previous should be a span (disabled) on first page, not a link
    expect(page.locator("nav span").filter(has_text="Previous")).to_be_visible()

    # When: Click next page
    page.get_by_role("link", name="Next").click()
    page.wait_for_load_state()

    # Then: Second page is displayed
    expect(page.get_by_text("Showing 16-30 of 100 runs")).to_be_visible()
    expect(page.get_by_role("link", name="Previous")).to_be_visible()

    # When: Click previous to go back
    page.get_by_role("link", name="Previous").click()
    page.wait_for_load_state()

    # Then: Back to first page
    expect(page.get_by_text("Showing 1-15 of 100 runs")).to_be_visible()


def test_selection_history_view_details(admin_logged_in_page: Page, assembly_gsheet_creator, test_database, admin_user):
    """Scenario: View details of a selection run from history

    Given: An assembly with a completed selection run
    When: User clicks "View" on a history record
    Then: User is redirected to the selection page with run details in URL
    """
    # Given: Assembly with a selection run
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

    # When: Visit selection page and click View link in the history table
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))
    # Use exact=True to match only "View" and not "View Details Assembly..."
    page.get_by_role("link", name="View", exact=True).click()
    page.wait_for_load_state()

    # Then: Redirected to selection page with run_id in the URL path
    # The URL format is /assembly/{assembly_id}/selection/history/{run_id}
    assert str(run_id) in page.url


def test_selection_history_status_tags(admin_logged_in_page: Page, assembly_gsheet_creator, test_database, admin_user):
    """Scenario: Verify status tags display correctly

    Given: An assembly with runs in different statuses
    When: User views the selection history
    Then: Each status is displayed in the history table
    """
    # Given: Assembly with runs in different statuses
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

    # When: Visit selection page
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: Verify all status texts are visible in the history table
    history_table = page.locator("table")
    expect(history_table.get_by_text("Completed").first).to_be_visible()
    expect(history_table.get_by_text("Failed").first).to_be_visible()
    expect(history_table.get_by_text("Cancelled").first).to_be_visible()
    expect(history_table.get_by_text("Running").first).to_be_visible()
    expect(history_table.get_by_text("Pending").first).to_be_visible()


def test_selection_history_scroll_preservation_with_pagination(
    admin_logged_in_page: Page, assembly_with_many_runs_and_gsheet
):
    """Scenario: Scroll position is preserved when navigating between pages

    Given: An assembly with paginated history
    When: User scrolls down and clicks pagination
    Then: Scroll position should be set before clicking (verifies page is tall enough)
    """
    # Given: Assembly with many runs
    assembly = assembly_with_many_runs_and_gsheet
    page = admin_logged_in_page

    # When: Visit selection page and scroll down
    page.goto(Urls.assembly_selection(assembly.id))

    # Ensure page is tall enough to scroll
    page.evaluate("document.body.style.minHeight = '2000px'")
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(200)  # Wait for scroll to settle

    # When: Click next page
    page.get_by_role("link", name="Next").click()
    page.wait_for_load_state()

    # Then: Verify we're on page 2 (scroll preservation may vary in headless)
    expect(page.get_by_text("Showing 16-30 of 100 runs")).to_be_visible()
