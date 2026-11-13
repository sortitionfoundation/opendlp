"""ABOUTME: BDD tests for the project details page: values edited in place, the data source, the registration link, the team
ABOUTME: Covers what only a browser shows - htmx swaps, focus, Escape, leaving a row, and the dialogs"""

from pathlib import Path

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import assign_assembly_role

from .config import NORMAL_PASSWORD, Urls

scenarios("../../features/project-details.feature")

EXAMPLES = Path(__file__).parent.parent.parent / "static" / "examples"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"

ROWS = {
    "project title": "#project-title-row",
    "framing question": "#project-question-row",
    "panel size": "#project-number_to_select-row",
    "first event date": "#project-first_assembly_date-row",
}
FIELDS = {
    "project title": "#project-title",
    "framing question": "#project-question",
    "panel size": "#project-number-to-select",
    "first event date": "#project-first-event-date",
}


def _row(page: Page, name: str) -> Locator:
    return page.locator(ROWS[name])


def _field(page: Page, name: str) -> Locator:
    return page.locator(FIELDS[name])


def _at_rest(page: Page, name: str) -> Locator:
    """The value as text, which is what the row shows when it is not being edited."""
    return _row(page, name).locator("form > p")


def _open(page: Page, name: str) -> Locator:
    page.get_by_role("button", name=f"Edit {name}", exact=True).click()
    field = _field(page, name)
    expect(field).to_be_focused()
    return field


def _saving(page: Page):
    return page.expect_response(lambda response: response.url.endswith("/edit-field"))


@given("I am logged in as an admin user")
def logged_in_as_admin(admin_logged_in_page: Page) -> None:
    pass


@given(
    parsers.parse('there is a project called "{title}" asking "{question}"'),
    target_fixture="project",
)
def a_project(title: str, question: str, admin_user, test_database):
    with SqlAlchemyUnitOfWork(test_database) as uow:
        assembly = create_assembly(
            uow=uow, title=title, question=question, created_by_user_id=admin_user.id, number_to_select=30
        )
        uow.commit()
        return assembly.create_detached_copy()


@given("I am on the details page of the project")
def on_the_details_page(page: Page, project) -> None:
    page.goto(f"{Urls.base}/backoffice/project/{project.id}")
    expect(page.get_by_role("heading", name="Basic details")).to_be_visible()


@given("a read-only member of the project is signed in")
def read_only_member_signed_in(page: Page, project, normal_user, test_database) -> None:
    with SqlAlchemyUnitOfWork(test_database) as uow:
        assign_assembly_role(uow, normal_user.id, project.id, AssemblyRole.READ_ONLY)
        uow.commit()
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', normal_user.email)
    page.fill('input[name="password"]', NORMAL_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.any_dashboard)


@when(parsers.parse('I edit the {name} to "{value}" and press Enter'))
def edit_and_press_enter(page: Page, name: str, value: str) -> None:
    field = _open(page, name)
    field.fill(value)
    with _saving(page):
        field.press("Enter")


@when(parsers.parse('I start editing the {name} and type "{text}"'))
def start_editing_and_type(page: Page, name: str, text: str) -> None:
    _open(page, name).fill(text)


@when(parsers.parse('I press Enter and type "{text}"'))
def press_enter_and_type(page: Page, text: str) -> None:
    page.keyboard.press("Enter")
    page.keyboard.type(text)


@when("I press Escape")
def press_escape(page: Page) -> None:
    page.keyboard.press("Escape")


@when("I press Ctrl+Enter")
def press_ctrl_enter(page: Page) -> None:
    with _saving(page):
        page.keyboard.press("Control+Enter")


@when("I click elsewhere on the page")
def click_elsewhere(page: Page) -> None:
    with _saving(page):
        page.get_by_role("heading", name="Basic details").click()


@then(parsers.parse('the {name} has the lines "{first}" and "{second}"'))
def reads_two_lines(page: Page, name: str, first: str, second: str) -> None:
    text = _at_rest(page, name)
    expect(text).to_be_visible()
    expect(text).to_contain_text(first)
    expect(text).to_contain_text(second)
    assert "\n" in text.inner_text().strip()


@then(parsers.parse('the {name} reads "{value}"'))
def reads(page: Page, name: str, value: str) -> None:
    text = _at_rest(page, name)
    expect(text).to_be_visible()
    expect(text).to_have_text(value)


@then(parsers.parse('the page heading is "{title}"'))
def page_heading_is(page: Page, title: str) -> None:
    expect(page.locator("h1")).to_have_text(title)


@then(parsers.parse('focus is on the "{name}" button'))
def focus_is_on_button(page: Page, name: str) -> None:
    expect(page.get_by_role("button", name=name, exact=True)).to_be_focused()


@then(parsers.parse('I am told "{message}"'))
def told(page: Page, message: str) -> None:
    expect(page.locator("#floating-alerts")).to_contain_text(message)


@then(parsers.parse('the project is stored with the title "{title}"'))
def stored_with_title(project, test_database, title: str) -> None:
    with SqlAlchemyUnitOfWork(test_database) as uow:
        assert uow.assemblies.get(project.id).title == title


@then(parsers.parse("the {name} field is open and marked as refused"))
def field_is_refused(page: Page, name: str) -> None:
    field = _field(page, name)
    expect(field).to_be_visible()
    expect(field).to_be_focused()
    expect(field).to_have_attribute("aria-invalid", "true")


@then(parsers.parse("the {name} field is still open"))
def field_is_still_open(page: Page, name: str) -> None:
    expect(_field(page, name)).to_be_visible()


@then(parsers.parse('I can read "{first}" and "{second}"'))
def can_read(page: Page, first: str, second: str) -> None:
    card = page.locator("main")
    expect(card).to_contain_text(first)
    expect(card).to_contain_text(second)


@then("there are no edit buttons on the page")
def no_edit_buttons(page: Page) -> None:
    expect(page.locator('main [x-data="inlineEdit"]')).to_have_count(0)
    expect(page.get_by_role("button", name="Edit project title", exact=True)).to_have_count(0)


# Data source


def _settings_dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Data source settings")


def _card(page: Page) -> Locator:
    return page.locator("#data-source")


@when("I open the data source settings")
def open_data_source_settings(page: Page) -> None:
    page.get_by_role("button", name="Data source settings", exact=True).click()
    expect(_settings_dialog(page)).to_be_visible()


@then("the data source settings dialog is open")
def settings_dialog_is_open(page: Page) -> None:
    expect(_settings_dialog(page)).to_be_visible()


@then("the data source settings dialog is closed")
def settings_dialog_is_closed(page: Page) -> None:
    expect(_settings_dialog(page)).to_have_count(0)


@then(parsers.parse('the dialog\'s data location is "{label}"'))
def dialog_location_is(page: Page, label: str) -> None:
    expect(_settings_dialog(page).locator("#project-location option:checked")).to_have_text(label)


@then("the dialog's data location cannot be changed")
def dialog_location_is_locked(page: Page) -> None:
    expect(_settings_dialog(page).locator("#project-location")).to_be_disabled()


@then("the dialog's data location can be changed")
def dialog_location_is_unlocked(page: Page) -> None:
    expect(_settings_dialog(page).locator("#project-location")).to_be_enabled()


@then("the dialog has no stepper")
def dialog_has_no_stepper(page: Page) -> None:
    expect(_settings_dialog(page).locator(".stepper")).to_have_count(0)


@when("I close the data source settings")
def close_data_source_settings(page: Page) -> None:
    _settings_dialog(page).locator(".dialog-footer").get_by_role("button", name="Close", exact=True).click()
    page.wait_for_load_state("networkidle")


@when("I choose to import targets from a CSV")
def choose_import_targets(page: Page) -> None:
    _settings_dialog(page).locator("#project-targets-source").select_option("csv")
    expect(_settings_dialog(page).locator("#project-targets-file")).to_be_visible()


@when("I choose to collect respondents through registration")
def choose_registration(page: Page) -> None:
    _settings_dialog(page).locator("#project-respondents-source").select_option("registration")


@when("I upload the example targets in the settings dialog")
def upload_targets_in_settings(page: Page) -> None:
    dialog = _settings_dialog(page)
    dialog.locator("#project-targets-file").set_input_files(EXAMPLES / "example-targets.csv")
    with page.expect_response(lambda response: response.url.endswith("/upload-targets")):
        dialog.get_by_role("button", name="Upload targets", exact=True).click()


@then(parsers.parse('the settings dialog says "{text}"'))
def settings_dialog_says(page: Page, text: str) -> None:
    expect(_settings_dialog(page)).to_contain_text(text)


@then(parsers.parse('the settings dialog does not say "{text}"'))
def settings_dialog_does_not_say(page: Page, text: str) -> None:
    expect(_settings_dialog(page)).not_to_contain_text(text)


@when("I save the data source settings")
def save_data_source_settings(page: Page) -> None:
    with page.expect_response(lambda response: response.url.endswith("/data-source/save")):
        _settings_dialog(page).get_by_role("button", name="Save", exact=True).click()
    page.wait_for_load_state("networkidle")


@when(parsers.parse('I change the dialog\'s data location to "{label}"'))
def change_dialog_location(page: Page, label: str) -> None:
    with page.expect_response(lambda response: response.url.endswith("/data-source/refresh")):
        _settings_dialog(page).locator("#project-location").select_option(label=label)


@then("the settings dialog shows the Google Sheets fields")
def settings_dialog_shows_sheet_fields(page: Page) -> None:
    expect(_settings_dialog(page).get_by_label("Spreadsheet URL")).to_be_visible()
    expect(_settings_dialog(page).locator("#project-targets-source")).to_have_count(0)


@when("I fill in a spreadsheet URL and the UK team")
def fill_in_sheet(page: Page) -> None:
    dialog = _settings_dialog(page)
    dialog.get_by_label("Spreadsheet URL").fill(SHEET_URL)
    dialog.get_by_text("UK Team", exact=True).click()


@when("I delete the targets and confirm")
def delete_targets_and_confirm(page: Page) -> None:
    page.once("dialog", lambda dialog: dialog.accept())
    _settings_dialog(page).get_by_role("button", name="Delete targets", exact=True).click()
    page.wait_for_url("**/backoffice/project/*?data_source=1*")


@then(parsers.parse('the data source card says "{text}"'))
def card_says(page: Page, text: str) -> None:
    expect(_card(page)).to_contain_text(text)


@then("the data source card links to the spreadsheet")
def card_links_to_sheet(page: Page) -> None:
    expect(_card(page).get_by_role("link", name=SHEET_URL)).to_be_visible()


@then("the spreadsheet's access is checked on the page")
def access_is_checked(page: Page) -> None:
    """The panel is there and has finished asking: with no Google credentials in tests it says it cannot check."""
    panel = _card(page).locator("#gsheet-access-status")
    expect(panel).to_be_visible()
    expect(panel).not_to_be_empty()
