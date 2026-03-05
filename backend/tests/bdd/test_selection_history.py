"""ABOUTME: BDD tests for Selection History (Phase 5)
ABOUTME: Tests the selection history display, pagination, and view details functionality"""

import uuid
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls


def test_selection_history_empty_state(admin_logged_in_page: Page, assembly_creator):
    """Scenario: View selection page with no history

    Given: An assembly with no selection runs
    When: User visits the selection page
    Then: Empty state message is displayed
    """
    # Given: Assembly with no history
    assembly = assembly_creator(title="Empty History Assembly")

    # When: Visit selection page
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: Empty state is shown
    expect(page.get_by_text("No selection runs yet")).to_be_visible()
    expect(page.get_by_text("Run your first selection above to see the history here.")).to_be_visible()


def test_selection_history_displays_runs(admin_logged_in_page: Page, assembly_creator, test_database, admin_user):
    """Scenario: View selection history with records

    Given: An assembly with several selection runs
    When: User visits the selection page
    Then: History table displays all runs with correct details
    """
    # Given: Assembly with selection runs
    assembly = assembly_creator(title="History Test Assembly")
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


def test_selection_history_pagination(admin_logged_in_page: Page, assembly_with_many_runs: tuple):
    """Scenario: Navigate through paginated selection history

    Given: An assembly with more than 50 selection runs
    When: User navigates through pages
    Then: Pagination controls work correctly and scroll position is preserved
    """
    # Given: Assembly with 100 runs (from fixture)
    assembly = assembly_with_many_runs
    page = admin_logged_in_page

    # When: Visit selection page
    page.goto(Urls.assembly_selection(assembly.id))

    # Then: First page is displayed
    expect(page.get_by_text("Showing 1-50 of 100 runs")).to_be_visible()
    expect(page.get_by_role("link", name="Next")).to_be_visible()

    # Previous button should be disabled on first page
    previous_button = page.locator("span", has_text="Previous").filter(has=page.locator('[style*="opacity: 0.5"]'))
    expect(previous_button).to_be_visible()

    # When: Click next page
    page.get_by_role("link", name="Next").click()
    page.wait_for_load_state()

    # Then: Second page is displayed
    expect(page.get_by_text("Showing 51-100 of 100 runs")).to_be_visible()
    expect(page.get_by_role("link", name="Previous")).to_be_visible()

    # Next button should be disabled on last page
    next_button = page.locator("span", has_text="Next").filter(has=page.locator('[style*="opacity: 0.5"]'))
    expect(next_button).to_be_visible()

    # When: Click previous to go back
    page.get_by_role("link", name="Previous").click()
    page.wait_for_load_state()

    # Then: Back to first page
    expect(page.get_by_text("Showing 1-50 of 100 runs")).to_be_visible()


def test_selection_history_view_details(admin_logged_in_page: Page, assembly_creator, test_database, admin_user):
    """Scenario: View details of a selection run from history

    Given: An assembly with a completed selection run
    When: User clicks "View" on a history record
    Then: User is redirected to the selection page with run details
    """
    # Given: Assembly with a selection run
    assembly = assembly_creator(title="View Details Assembly")
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

    # When: Visit selection page and click View
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(assembly.id))
    page.get_by_role("link", name="View").click()
    page.wait_for_load_state()

    # Then: Redirected to selection page with run_id parameter
    # The URL should contain run_id parameter
    assert f"run_id={run_id}" in page.url


def test_selection_history_status_tags(admin_logged_in_page: Page, assembly_creator, test_database, admin_user):
    """Scenario: Verify status tags display correctly with appropriate colors

    Given: An assembly with runs in different statuses
    When: User views the selection history
    Then: Each status is displayed with the correct color
    """
    # Given: Assembly with runs in different statuses
    assembly = assembly_creator(title="Status Tags Assembly")
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

    # Then: Verify status tags are visible with appropriate styling
    # Completed should have success colors
    completed_tag = page.locator('span:has-text("Completed")').filter(
        has=page.locator('[style*="color-success-background"]')
    )
    expect(completed_tag.first).to_be_visible()

    # Failed should have error colors
    failed_tag = page.locator('span:has-text("Failed")').filter(has=page.locator('[style*="color-error-background"]'))
    expect(failed_tag.first).to_be_visible()

    # Cancelled should have warning colors
    cancelled_tag = page.locator('span:has-text("Cancelled")').filter(
        has=page.locator('[style*="color-warning-background"]')
    )
    expect(cancelled_tag.first).to_be_visible()

    # Running should have info colors
    running_tag = page.locator('span:has-text("Running")').filter(has=page.locator('[style*="color-info-background"]'))
    expect(running_tag.first).to_be_visible()


def test_selection_history_scroll_preservation_with_pagination(
    admin_logged_in_page: Page, assembly_with_many_runs: tuple
):
    """Scenario: Scroll position is preserved when navigating between pages

    Given: An assembly with paginated history
    When: User scrolls down and clicks pagination
    Then: Scroll position is preserved after page reload
    """
    # Given: Assembly with many runs
    assembly = assembly_with_many_runs
    page = admin_logged_in_page

    # When: Visit selection page and scroll down
    page.goto(Urls.assembly_selection(assembly.id))
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(100)  # Wait for scroll to settle

    # Get current scroll position
    scroll_before = page.evaluate("window.scrollY")
    assert scroll_before == 500

    # When: Click next page
    page.get_by_role("link", name="Next").click()
    page.wait_for_load_state()

    # Then: Scroll position should be preserved (approximately)
    scroll_after = page.evaluate("window.scrollY")
    # Allow some tolerance for browser rendering differences
    assert abs(scroll_after - scroll_before) < 50
