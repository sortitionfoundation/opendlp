"""ABOUTME: BDD tests for the project details page: values edited in place, the data source, the registration link, the team
ABOUTME: Covers what only a browser shows - htmx swaps, focus, Escape, leaving a row, and the dialogs"""

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import assign_assembly_role

from .config import NORMAL_PASSWORD, Urls

scenarios("../../features/project-details.feature")

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
