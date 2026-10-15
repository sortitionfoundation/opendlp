"""ABOUTME: BDD test for refusing a second writing task on an assembly while one is unfinished
ABOUTME: A Run Selection click from a page that predates the other run lands in that run's progress dialog"""

import uuid

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import target_csv_import
from opendlp.service_layer.assembly_service import update_csv_config, update_selection_settings
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/concurrent-selection.feature")

TARGETS_CSV = "feature,value,min,max\nGender,Male,1,1\nGender,Female,1,1"
RESPONDENTS_CSV = "external_id,Gender\nM1,Male\nM2,Male\nF1,Female\nF2,Female\n"


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: the fixture handles the login."""


@given("a database assembly ready for selection", target_fixture="test_assembly")
def assembly_ready_for_selection(assembly_creator, admin_user, test_database):
    """A database assembly with confirmed settings, targets and a pool, so Run Selection is offered."""
    assembly = assembly_creator("Concurrent Selection Assembly", number_to_select=2)
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        update_selection_settings(uow, admin_user.id, assembly.id, check_same_address=False)
    with uow:
        update_csv_config(uow, admin_user.id, assembly.id, csv_id_column="external_id", settings_confirmed=True)
    with uow:
        target_csv_import.import_targets_from_csv(uow, admin_user.id, assembly.id, TARGETS_CSV)
    with uow:
        import_respondents_from_csv(uow, admin_user.id, assembly.id, RESPONDENTS_CSV, replace_existing=True)
    return assembly


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    admin_logged_in_page.goto(Urls.assembly_selection(test_assembly.id))
    admin_logged_in_page.wait_for_load_state()
    expect(admin_logged_in_page.get_by_role("button", name="Run Selection")).to_be_visible()


@when("a selection starts on that assembly from somewhere else", target_fixture="running_run_id")
def selection_starts_elsewhere(test_database, test_assembly, admin_user):
    """Another browser, or the monitor, has started a selection since this page was loaded."""
    run_id = uuid.uuid4()
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=test_assembly.id,
                task_id=run_id,
                task_type=SelectionTaskType.SELECT_FROM_DB,
                status=SelectionRunStatus.RUNNING,
                user_id=admin_user.id,
                log_messages=["Task submitted for database selection", "Loading respondents"],
            )
        )
        uow.commit()
    return run_id


@when("the user clicks Run Selection")
def user_clicks_run_selection(admin_logged_in_page: Page):
    admin_logged_in_page.get_by_role("button", name="Run Selection").click()
    admin_logged_in_page.wait_for_load_state()


@then("the user is told another task is already running")
def user_told_another_task_is_running(admin_logged_in_page: Page):
    expect(
        admin_logged_in_page.get_by_text("Another task is already running on this assembly", exact=False)
    ).to_be_visible()


@then("the running selection's progress dialog is displayed with a Cancel Task button")
def running_dialog_displayed(admin_logged_in_page: Page, running_run_id):
    assert f"current_selection={running_run_id}" in admin_logged_in_page.url
    modal = admin_logged_in_page.locator("#db-selection-progress-modal-panel")
    expect(modal).to_be_visible()
    expect(modal.get_by_text("Loading respondents")).to_be_visible()
    expect(modal.get_by_role("button", name="Cancel Task")).to_be_visible()


@when("the user cancels the running selection")
def user_cancels_running_selection(admin_logged_in_page: Page):
    modal = admin_logged_in_page.locator("#db-selection-progress-modal-panel")
    modal.get_by_role("button", name="Cancel Task").click()
    admin_logged_in_page.wait_for_load_state()


@then("the progress dialog shows the task as cancelled")
def dialog_shows_cancelled(admin_logged_in_page: Page, test_database, running_run_id):
    modal = admin_logged_in_page.locator("#db-selection-progress-modal-panel")
    expect(modal.get_by_text("Task Cancelled", exact=True)).to_be_visible()
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        record = uow.selection_run_records.get_by_task_id(running_run_id)
        assert record is not None
        assert record.status == SelectionRunStatus.CANCELLED
