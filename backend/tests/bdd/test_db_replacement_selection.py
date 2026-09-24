"""ABOUTME: BDD tests for replacement selection over respondents held in the database
ABOUTME: Drives the review dialog and a real replacement run through the browser and Celery worker"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer import target_csv_import
from opendlp.service_layer.assembly_service import update_csv_config, update_selection_settings
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/db-replacement-selection.feature")

# Four to select, two of each gender. M1 and F1 hold places, M2 withdrew, so one
# Male place is to be filled and the pool (M3, F2, F3) can fill it.
TARGETS_CSV = "feature,value,min,max\nGender,Male,2,2\nGender,Female,2,2"
RESPONDENTS_CSV = "external_id,Gender\nM1,Male\nM2,Male\nM3,Male\nF1,Female\nF2,Female\nF3,Female\n"
STATUSES = {
    "M1": RespondentStatus.SELECTED,
    "F1": RespondentStatus.CONFIRMED,
    "M2": RespondentStatus.WITHDRAWN,
}


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: the fixture handles the login."""


@given("a database assembly where one selected person has withdrawn", target_fixture="test_assembly")
def assembly_after_withdrawal(assembly_creator, admin_user, test_database):
    assembly = assembly_creator("DB Replacement Assembly", number_to_select=4)
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        update_selection_settings(uow, admin_user.id, assembly.id, check_same_address=False)
    with uow:
        update_csv_config(uow, admin_user.id, assembly.id, csv_id_column="external_id", settings_confirmed=True)
    with uow:
        target_csv_import.import_targets_from_csv(uow, admin_user.id, assembly.id, TARGETS_CSV)
    with uow:
        import_respondents_from_csv(uow, admin_user.id, assembly.id, RESPONDENTS_CSV, replace_existing=True)
    with uow:
        for respondent in uow.respondents.get_by_assembly_id(assembly.id):
            if respondent.external_id in STATUSES:
                respondent.selection_status = STATUSES[respondent.external_id]
        uow.commit()
    return assembly


@when("the user visits the selection page")
def user_visits_selection_page(admin_logged_in_page: Page, test_assembly):
    admin_logged_in_page.goto(Urls.assembly_selection(test_assembly.id))
    admin_logged_in_page.wait_for_load_state()


@when("the user opens the replacement selection dialog")
def user_opens_dialog(admin_logged_in_page: Page):
    admin_logged_in_page.get_by_role("button", name="Go to Replacement Selection").click()
    admin_logged_in_page.wait_for_load_state()
    expect(admin_logged_in_page.locator("#db-replacement-modal")).to_be_visible()


@when("the user clicks Run Replacement Selection")
def user_clicks_run(admin_logged_in_page: Page):
    admin_logged_in_page.get_by_role("button", name="Run Replacement Selection").click()


@then("the dialog shows how many places are to be filled")
def dialog_shows_places_to_fill(admin_logged_in_page: Page):
    modal = admin_logged_in_page.locator("#db-replacement-modal")
    expect(modal.get_by_text("2 people are selected or confirmed")).to_be_visible()
    expect(modal.get_by_text("2 places are to be filled")).to_be_visible()


@then("the dialog shows the calculated replacement targets")
def dialog_shows_targets(admin_logged_in_page: Page):
    modal = admin_logged_in_page.locator("#db-replacement-modal")
    expect(modal.get_by_label("Minimum still needed for Gender: Male")).to_have_value("1")
    expect(modal.get_by_label("Maximum still needed for Gender: Female")).to_have_value("1")


@then("the Run Replacement Selection button is visible")
def run_button_visible(admin_logged_in_page: Page):
    expect(admin_logged_in_page.get_by_role("button", name="Run Replacement Selection")).to_be_visible()


@then("the task progress dialog is displayed")
def progress_dialog_displayed(admin_logged_in_page: Page):
    modal = admin_logged_in_page.locator("#db-selection-progress-modal-panel")
    expect(modal).to_be_visible()
    expect(modal.get_by_text("Select replacements from database")).to_be_visible()


@then("the replacement selection completes")
def replacement_completes(admin_logged_in_page: Page):
    modal = admin_logged_in_page.locator("#db-selection-progress-modal-panel")
    expect(modal.get_by_text("Task completed successfully")).to_be_visible(timeout=30_000)


@then("the withdrawn place has been filled from the pool")
def place_filled(test_database, test_assembly):
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        status_by_id = {r.external_id: r.selection_status for r in uow.respondents.get_by_assembly_id(test_assembly.id)}
    assert status_by_id["M1"] == RespondentStatus.SELECTED
    assert status_by_id["F1"] == RespondentStatus.CONFIRMED
    assert status_by_id["M2"] == RespondentStatus.WITHDRAWN
    newly_selected = {ext for ext, status in status_by_id.items() if status == RespondentStatus.SELECTED} - {"M1"}
    assert len(newly_selected) == 2
    assert "M3" in newly_selected
    assert newly_selected & {"F2", "F3"}
