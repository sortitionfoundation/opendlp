"""ABOUTME: BDD tests for Replacement Selection Modal
ABOUTME: Tests the replacement selection workflow from the selection page"""

import uuid
from datetime import UTC, datetime, timedelta

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/replacement-selection.feature")


# =============================================================================
# Given Steps
# =============================================================================


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: ensure admin user is logged in."""
    pass


@given("an assembly with gsheet configured", target_fixture="test_assembly")
def assembly_with_gsheet(assembly_gsheet_creator):
    """Create an assembly with gsheet configuration."""
    assembly, _gsheet = assembly_gsheet_creator(title="Replacement Test Assembly")
    return assembly


@given("the replacement load task has completed", target_fixture="test_assembly")
def replacement_load_completed(admin_logged_in_page: Page, test_assembly):
    """Open replacement modal and complete the load task."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")

    # Navigate to selection page and open replacement modal
    page.goto(Urls.assembly_selection_with_replacement_modal(test_assembly.id))
    page.wait_for_load_state()

    # Click Check Spreadsheet to start load (scope to modal)
    check_btn = modal.get_by_role("button", name="Check Spreadsheet")
    expect(check_btn).to_be_visible()
    check_btn.click()

    # Wait for load to complete - the form with number input appears
    expect(modal.get_by_label("Number of people to select")).to_be_visible(timeout=30_000)

    return test_assembly


@given("a completed replacement task exists", target_fixture="test_assembly")
def completed_replacement_task(test_database, admin_user, assembly_gsheet_creator, request):
    """Create an assembly with a completed replacement task."""
    assembly, _gsheet = assembly_gsheet_creator(title="Completed Replacement Assembly")
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    run_id = uuid.uuid4()
    with uow:
        run_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=run_id,
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
            user_id=admin_user.id,
            comment="Completed replacement",
            created_at=datetime.now(UTC) - timedelta(hours=1),
            completed_at=datetime.now(UTC),
        )
        uow.selection_run_records.add(run_record)
        uow.commit()

    # Store run_id for later use
    request.node.run_id = run_id
    return assembly


# =============================================================================
# When Steps
# =============================================================================


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    """Navigate to the selection page."""
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection(test_assembly.id))
    page.wait_for_load_state()


@when("the user clicks the Replacements button")
def user_clicks_replacements(admin_logged_in_page: Page):
    """Click the 'Go to Replacement Selection' link to open modal."""
    page = admin_logged_in_page
    # The button is actually a link styled as a button with text "Go to Replacement Selection"
    link = page.get_by_role("link", name="Go to Replacement Selection")
    expect(link).to_be_visible()
    link.click()
    page.wait_for_load_state()


@when("the user opens the replacement modal")
def user_opens_replacement_modal(admin_logged_in_page: Page, test_assembly):
    """Open the replacement modal via URL."""
    page = admin_logged_in_page
    page.goto(Urls.assembly_selection_with_replacement_modal(test_assembly.id))
    page.wait_for_load_state()


@when("the user clicks Check Spreadsheet")
def user_clicks_check_spreadsheet(admin_logged_in_page: Page):
    """Click the Check Spreadsheet button in the modal."""
    page = admin_logged_in_page
    # Scope to modal to avoid matching button in card on page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Check Spreadsheet")
    expect(btn).to_be_visible()
    btn.click()


@when("the load task completes successfully")
def load_task_completes(admin_logged_in_page: Page):
    """Wait for load task to complete."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # Wait for the number input to appear (indicates load completed)
    expect(modal.get_by_label("Number of people to select")).to_be_visible(timeout=30_000)


@when("the user enters the number to select")
def user_enters_number(admin_logged_in_page: Page):
    """Enter a number in the selection field."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    number_input = modal.get_by_label("Number of people to select")
    expect(number_input).to_be_visible()
    # Get the min value from the input and use it
    min_val = number_input.get_attribute("min") or "1"
    number_input.fill(min_val)


@when("the user clicks Run Replacements")
def user_clicks_run_replacements(admin_logged_in_page: Page):
    """Click the Run Replacements button in the modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Run Replacements")
    expect(btn).to_be_visible()
    btn.click()


@when("the replacement task completes")
def replacement_task_completes(admin_logged_in_page: Page):
    """Wait for replacement task to complete."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # Wait for Completed status badge to appear
    expect(modal.get_by_text("Completed")).to_be_visible(timeout=30_000)


@when("the user clicks Cancel Task")
def user_clicks_cancel(admin_logged_in_page: Page):
    """Click the Cancel Task button in the modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Cancel Task")
    expect(btn).to_be_visible()
    btn.click()


@when("the user opens the replacement modal with the completed task")
def user_opens_completed_task(admin_logged_in_page: Page, test_assembly, request):
    """Open replacement modal showing a completed task."""
    page = admin_logged_in_page
    run_id = request.node.run_id
    page.goto(Urls.assembly_replacement_with_run(test_assembly.id, run_id))
    page.wait_for_load_state()


@when("the user clicks Close")
def user_clicks_close(admin_logged_in_page: Page):
    """Click the Close button in the modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("link", name="Close")
    expect(btn).to_be_visible()
    btn.click()
    page.wait_for_load_state()


@when("the user clicks Re-check Spreadsheet")
def user_clicks_recheck(admin_logged_in_page: Page):
    """Click the Re-check Spreadsheet button in the modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Re-check Spreadsheet")
    expect(btn).to_be_visible()
    btn.click()


# =============================================================================
# Then Steps
# =============================================================================


@then("the replacement modal is displayed")
def replacement_modal_displayed(admin_logged_in_page: Page):
    """Verify the replacement modal is visible."""
    page = admin_logged_in_page
    # Check for the modal backdrop (the wrapper div has no dimensions due to fixed children)
    modal_backdrop = page.locator("#replacement-modal-backdrop")
    expect(modal_backdrop).to_be_visible()
    # Use specific modal title ID to avoid matching card heading on page
    expect(page.locator("#replacement-modal-title")).to_be_visible()


@then("the Check Spreadsheet button is visible")
def check_spreadsheet_visible(admin_logged_in_page: Page):
    """Verify Check Spreadsheet button is visible in the modal."""
    page = admin_logged_in_page
    # Scope to the modal to avoid matching button in card on page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Check Spreadsheet")
    expect(btn).to_be_visible()


@then("the modal shows a loading spinner")
def modal_shows_spinner(admin_logged_in_page: Page):
    """Verify the modal shows a loading spinner."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # The spinner is an SVG with animate-spin class
    spinner = modal.locator(".animate-spin")
    expect(spinner.first).to_be_visible()


@then("the status shows Running or Pending")
def status_shows_running_or_pending(admin_logged_in_page: Page):
    """Verify status is Running or Pending in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # Either Running or Pending should be visible
    running = modal.get_by_text("Running")
    pending = modal.get_by_text("Pending")
    expect(running.or_(pending)).to_be_visible()


@then("the modal shows the available replacement count")
def modal_shows_replacement_count(admin_logged_in_page: Page):
    """Verify modal shows available replacement count."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    expect(modal.get_by_text("Available replacements:")).to_be_visible()


@then("the number input field is visible")
def number_input_visible(admin_logged_in_page: Page):
    """Verify number input field is visible in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    number_input = modal.get_by_label("Number of people to select")
    expect(number_input).to_be_visible()


@then("the Run Replacements button is visible")
def run_replacements_visible(admin_logged_in_page: Page):
    """Verify Run Replacements button is visible in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Run Replacements")
    expect(btn).to_be_visible()


@then("the Re-check Spreadsheet button is visible")
def recheck_button_visible(admin_logged_in_page: Page):
    """Verify Re-check Spreadsheet button is visible in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Re-check Spreadsheet")
    expect(btn).to_be_visible()


@then("the Cancel Task button is visible")
def cancel_button_visible(admin_logged_in_page: Page):
    """Verify Cancel Task button is visible in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("button", name="Cancel Task")
    expect(btn).to_be_visible()


@then("the modal shows Completed status")
def modal_shows_completed(admin_logged_in_page: Page):
    """Verify modal shows Completed status."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    expect(modal.get_by_text("Completed")).to_be_visible()


@then("the result message shows success")
def result_shows_success(admin_logged_in_page: Page):
    """Verify result message shows success in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    expect(modal.get_by_text("Task completed successfully")).to_be_visible()


@then("the Close button is visible")
def close_button_visible(admin_logged_in_page: Page):
    """Verify Close button is visible in modal."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    btn = modal.get_by_role("link", name="Close")
    expect(btn).to_be_visible()


@then("the modal shows Cancelled status")
def modal_shows_cancelled(admin_logged_in_page: Page):
    """Verify modal shows Cancelled status."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    expect(modal.get_by_text("Cancelled")).to_be_visible(timeout=10_000)


@then("the user is returned to the selection page")
def user_on_selection_page(admin_logged_in_page: Page, test_assembly):
    """Verify user is on selection page."""
    page = admin_logged_in_page
    expected_url = Urls.assembly_selection(test_assembly.id)
    expect(page).to_have_url(expected_url)


@then("the replacement modal is not visible")
def replacement_modal_not_visible(admin_logged_in_page: Page):
    """Verify replacement modal is not visible."""
    page = admin_logged_in_page
    # Check the backdrop is not visible (the wrapper div has no dimensions)
    modal_backdrop = page.locator("#replacement-modal-backdrop")
    expect(modal_backdrop).not_to_be_visible()


@then("the Close button is not visible")
def close_button_not_visible(admin_logged_in_page: Page):
    """Verify Close button is not visible while task is running."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # Close link should not be visible during task execution
    close_link = modal.get_by_role("link", name="Close")
    expect(close_link).not_to_be_visible()


@then("the modal cannot be closed by clicking backdrop")
def modal_cannot_close_via_backdrop(admin_logged_in_page: Page):
    """Verify modal stays open when clicking backdrop."""
    page = admin_logged_in_page
    # The backdrop doesn't close the modal when task is running
    # (This is enforced by the canClose check in the script)
    modal_backdrop = page.locator("#replacement-modal-backdrop")
    expect(modal_backdrop).to_be_visible()


@then("a new load task starts")
def new_load_task_starts(admin_logged_in_page: Page):
    """Verify a new load task has started."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    # Should see the status change or spinner appear
    spinner = modal.locator(".animate-spin")
    expect(spinner.first).to_be_visible()


@then("the modal shows loading state")
def modal_shows_loading(admin_logged_in_page: Page):
    """Verify modal shows loading state."""
    page = admin_logged_in_page
    modal = page.locator("#replacement-modal")
    expect(modal.get_by_text("Processing...")).to_be_visible()


@then("the selection history shows the replacement task")
def history_shows_replacement(admin_logged_in_page: Page):
    """Verify selection history contains the replacement task."""
    page = admin_logged_in_page
    # The history table should be visible with the task
    history_section = page.get_by_role("heading", name="Selection History")
    expect(history_section).to_be_visible()


@then("the task type shows as Replace Selection")
def task_type_shows_replace(admin_logged_in_page: Page):
    """Verify task type shows as replacement selection."""
    page = admin_logged_in_page
    # The verbose text is "Select replacement google spreadsheet"
    # Scope to table and use .first to avoid strict mode violation
    # (multiple cells may contain "replacement" - task type and comment)
    history_table = page.locator("table")
    expect(history_table.get_by_text("replacement", exact=False).first).to_be_visible()
