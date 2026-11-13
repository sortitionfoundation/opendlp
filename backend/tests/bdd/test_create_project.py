"""ABOUTME: BDD tests for the three-step Create new project dialog on the list of projects
ABOUTME: Covers what only a browser shows - the htmx steps, the Alpine panels, uploads, focus and the leave guard"""

from pathlib import Path

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/create-project.feature")

EXAMPLES = Path(__file__).parent.parent.parent / "static" / "examples"


def _dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Create new project")


def _titles(test_database) -> list[str]:
    with SqlAlchemyUnitOfWork(test_database) as uow:
        return [assembly.title for assembly in uow.assemblies.all()]


@given("I am logged in as an admin user")
def logged_in_as_admin(admin_logged_in_page: Page) -> None:
    pass


@given("there are no projects")
def no_projects(test_database) -> None:
    with SqlAlchemyUnitOfWork(test_database) as uow:
        for assembly in list(uow.assemblies.all()):
            uow.session.delete(assembly)
        uow.commit()


@given("I am on the list of my projects")
def on_the_list_of_projects(page: Page) -> None:
    page.goto(Urls.backoffice_dashboard)
    expect(page.get_by_role("heading", name="Your projects", level=1)).to_be_visible()


@when("I open the create project dialog")
def open_the_dialog(page: Page) -> None:
    page.get_by_role("button", name="Create your first project").click()
    expect(_dialog(page)).to_be_visible()


@then(parsers.parse('the create project dialog is at the step "{step}"'))
def dialog_is_at_step(page: Page, step: str) -> None:
    expect(_dialog(page).locator('[aria-current="step"]')).to_contain_text(step)


@then("focus is on the project title")
def focus_is_on_the_title(page: Page) -> None:
    expect(_dialog(page).get_by_label("Project title")).to_be_focused()


@then("the page behind the dialog is still the list of my projects")
def page_behind_is_the_list(page: Page) -> None:
    assert page.url == Urls.backoffice_dashboard
    expect(page.get_by_role("heading", name="Your projects", level=1)).to_be_attached()


@when(parsers.parse('I give the project the title "{title}"'))
def give_the_title(page: Page, title: str) -> None:
    _dialog(page).get_by_label("Project title").fill(title)


@when("I move on to the next step")
def next_step(page: Page) -> None:
    with page.expect_response(lambda response: response.url.endswith("/project/new/step")):
        _dialog(page).get_by_role("button", name="Next", exact=True).click()


@when("I go back a step")
def back_a_step(page: Page) -> None:
    with page.expect_response(lambda response: response.url.endswith("/project/new/step")):
        _dialog(page).get_by_role("button", name="Back", exact=True).click()


@then("I can go back a step")
def can_go_back(page: Page) -> None:
    expect(_dialog(page).get_by_role("button", name="Back", exact=True)).to_be_visible()


@then("I cannot go back a step")
def cannot_go_back(page: Page) -> None:
    expect(_dialog(page).get_by_role("button", name="Back", exact=True)).to_have_count(0)


@then(parsers.parse('the dialog offers "{offered}" instead of "{gone}"'))
def dialog_offers_instead(page: Page, offered: str, gone: str) -> None:
    footer = _dialog(page).locator(".dialog-footer")
    expect(footer.get_by_role("button", name=offered, exact=True)).to_be_visible()
    expect(footer.get_by_role("button", name=gone, exact=True)).to_have_count(0)


@then("the project title is marked as required")
def title_is_marked_required(page: Page) -> None:
    title = _dialog(page).get_by_label("Project title")
    expect(title).to_have_attribute("aria-invalid", "true")
    expect(title).to_be_focused()


@then(parsers.parse('the project title reads "{title}"'))
def title_reads(page: Page, title: str) -> None:
    expect(_dialog(page).get_by_label("Project title")).to_have_value(title)


@when(parsers.parse('I choose the data location "{label}"'))
def choose_location(page: Page, label: str) -> None:
    _dialog(page).get_by_label("Where will you manage your data?").select_option(label=label)


@then(parsers.parse('the data location is "{label}"'))
def location_is(page: Page, label: str) -> None:
    expect(_dialog(page).get_by_label("Where will you manage your data?").locator("option:checked")).to_have_text(label)


@when(parsers.parse('I choose the target data source "{label}"'))
def choose_targets_source(page: Page, label: str) -> None:
    _dialog(page).locator("#project-targets-source").select_option(label=label)


@when(parsers.parse('I choose the respondents data source "{label}"'))
def choose_respondents_source(page: Page, label: str) -> None:
    _dialog(page).locator("#project-respondents-source").select_option(label=label)


@then(parsers.parse('the target data source is "{label}"'))
def targets_source_is(page: Page, label: str) -> None:
    expect(_dialog(page).locator("#project-targets-source option:checked")).to_have_text(label)


@then(parsers.parse('the respondents data source is "{label}"'))
def respondents_source_is(page: Page, label: str) -> None:
    expect(_dialog(page).locator("#project-respondents-source option:checked")).to_have_text(label)


@then("I cannot see the target data source")
def no_targets_source(page: Page) -> None:
    expect(_dialog(page).locator("#project-targets-source")).to_have_count(0)


@then("I can see where to upload targets")
def can_see_targets_upload(page: Page) -> None:
    expect(_dialog(page).locator("#project-targets-file")).to_be_visible()


@then("I cannot see where to upload targets")
def cannot_see_targets_upload(page: Page) -> None:
    expect(_dialog(page).locator("#project-targets-file")).to_be_hidden()


@then("I can see where to upload respondents")
def can_see_respondents_upload(page: Page) -> None:
    expect(_dialog(page).locator("#project-respondents-file")).to_be_visible()


@then("I cannot see where to upload respondents")
def cannot_see_respondents_upload(page: Page) -> None:
    expect(_dialog(page).locator("#project-respondents-file")).to_be_hidden()


def _upload(page: Page, file_input: str, button: str, filename: str) -> None:
    _dialog(page).locator(file_input).set_input_files(EXAMPLES / filename)
    with page.expect_response(lambda response: "/upload-" in response.url):
        _dialog(page).get_by_role("button", name=button, exact=True).click()


@when("I upload the example targets")
def upload_example_targets(page: Page) -> None:
    _upload(page, "#project-targets-file", "Upload targets", "example-targets.csv")


@when("I upload the example respondents as targets")
def upload_respondents_as_targets(page: Page) -> None:
    _upload(page, "#project-targets-file", "Upload targets", "example-respondents.csv")


@when("I upload the example respondents")
def upload_example_respondents(page: Page) -> None:
    _upload(page, "#project-respondents-file", "Upload respondents", "example-respondents.csv")


@then(parsers.parse('the dialog says "{text}"'))
def dialog_says(page: Page, text: str) -> None:
    expect(_dialog(page)).to_contain_text(text)


@then("I can see the Google Sheets settings")
def can_see_sheet_settings(page: Page) -> None:
    expect(_dialog(page).get_by_label("Spreadsheet URL")).to_be_visible()
    expect(_dialog(page).get_by_text("Team Configuration")).to_be_visible()


@when(parsers.parse('I give the spreadsheet URL "{url}"'))
def give_spreadsheet_url(page: Page, url: str) -> None:
    _dialog(page).get_by_label("Spreadsheet URL").fill(url)


@when(parsers.parse('I choose the team "{team}"'))
def choose_team(page: Page, team: str) -> None:
    _dialog(page).get_by_text(team, exact=True).click()


@then("I cannot see the custom column settings")
def no_custom_columns(page: Page) -> None:
    expect(_dialog(page).get_by_label("ID Column")).to_be_hidden()


@then("the spreadsheet URL is marked as refused")
def spreadsheet_url_refused(page: Page) -> None:
    expect(_dialog(page).get_by_label("Spreadsheet URL")).to_have_attribute("aria-invalid", "true")


@when("I save the create project dialog")
def save_the_dialog(page: Page) -> None:
    with page.expect_response(lambda response: response.url.endswith("/save")):
        _dialog(page).get_by_role("button", name="Save", exact=True).click()
    page.wait_for_load_state("networkidle")


@when("I cancel the create project dialog")
def cancel_the_dialog(page: Page) -> None:
    _dialog(page).locator(".dialog-footer").get_by_role("button", name="Cancel", exact=True).click()


@when("I press Escape")
def press_escape(page: Page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_load_state("networkidle")


@then("I am asked whether to discard my changes")
def asked_to_discard(page: Page) -> None:
    expect(page.get_by_role("alertdialog", name="Discard changes?")).to_be_visible()


@when("I discard my changes")
def discard_changes(page: Page) -> None:
    page.get_by_role("button", name="Discard changes", exact=True).click()
    page.wait_for_load_state("networkidle")


@then("I am on the list of my projects")
def am_on_the_list(page: Page) -> None:
    page.wait_for_url(Urls.backoffice_dashboard)


@then("the create project dialog is closed")
def dialog_is_closed(page: Page) -> None:
    expect(_dialog(page)).to_have_count(0)


@then(parsers.parse('I am on the details page of "{title}"'))
def on_details_page(page: Page, title: str) -> None:
    expect(page.get_by_role("heading", name=title, level=1)).to_be_visible()
    assert "/backoffice/project/" in page.url


@then("I am told the project was created")
def told_it_was_created(page: Page) -> None:
    expect(page.locator("body")).to_contain_text("created successfully")


@then(parsers.parse('there is a project called "{title}"'))
def there_is_a_project(test_database, title: str) -> None:
    assert title in _titles(test_database)


@then(parsers.parse('there is no project called "{title}"'))
def there_is_no_project(test_database, title: str) -> None:
    assert title not in _titles(test_database)
