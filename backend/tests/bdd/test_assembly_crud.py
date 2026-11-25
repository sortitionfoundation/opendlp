"""ABOUTME: BDD tests for creating, viewing, editing and listing projects in the backoffice
ABOUTME: Drives the create dialog, the project details page and the list of projects"""

import re
from collections.abc import Callable, Iterable

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.assembly import Assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.bdd.helpers import wait_for_page_with_text

from .config import Urls

# consider splitting up if these features grow many more tests
scenarios(
    "../../features/create-assembly.feature",
    "../../features/update-assembly.feature",
    "../../features/view-assembly.feature",
    "../../features/view-assembly-list.feature",
)

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


def _create_dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Create new project")


@given(parsers.parse("there are {num_assemblies:d} assemblies in the system"), target_fixture="assembly_list")
def _(num_assemblies: int, assembly_creator: Callable):
    """there are num assemblies in the system."""
    return [assembly_creator(f"To be or not to be? stage {idx}") for idx in range(num_assemblies)]


@given("the user starts editing the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly):
    """the user starts editing the assembly."""
    admin_logged_in_page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    admin_logged_in_page.get_by_role("button", name="Edit framing question", exact=True).click()


@given("the user is creating an assembly")
def _(admin_logged_in_page: Page):
    """the user is creating an assembly."""
    admin_logged_in_page.goto(Urls.backoffice_dashboard)
    admin_logged_in_page.get_by_role("button", name="Create project", exact=True).click()
    expect(_create_dialog(admin_logged_in_page)).to_be_visible()


@when("the user sees the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly):
    """the user sees the assembly."""
    admin_logged_in_page.goto(Urls.backoffice_assembly_url(str(assembly.id)))


@when("the user sees the list of assemblies")
def _(admin_logged_in_page: Page):
    """the user sees the list of assemblies."""
    admin_logged_in_page.goto(Urls.backoffice_dashboard)


@when(
    parsers.parse('the user makes the title "{assembly_title}"'),
    target_fixture="assembly_title_for_lookup",
)
def _(page: Page, assembly_title: str):
    """the user makes the title "Liliput Climate Assembly"."""
    _create_dialog(page).get_by_label("Project title").fill(assembly_title)
    return assembly_title


@when(parsers.parse('the user makes the question "{assembly_question}"'))
def _(page: Page, assembly_question: str):
    """the user makes the question "What should Liliput do about the Climate Emergency?"."""
    page.locator("#project-question").fill(assembly_question)


@when("the user finishes editing the assembly")
def _(page: Page):
    """the user finishes editing the assembly."""
    with page.expect_response(lambda response: response.url.endswith("/edit-field")):
        page.get_by_role("button", name="Save framing question", exact=True).click()


@when("the user finishes creating the assembly")
def _(page: Page):
    """the user finishes creating the assembly, leaving where its data lives for later."""
    dialog = _create_dialog(page)
    for _step in ("Data location", "Targets and people"):
        with page.expect_response(lambda response: response.url.endswith("/project/new/step")):
            dialog.get_by_role("button", name="Next", exact=True).click()
    with page.expect_response(lambda response: response.url.endswith("/save")):
        dialog.get_by_role("button", name="Save", exact=True).click()


@then('the user sees the message "No assemblies"')
def _(page: Page):
    """the user sees the message "No assemblies"."""
    expect(page.locator("main")).to_contain_text("No projects yet")


@then("the user sees the title of both assemblies")
def _(page: Page, assembly_list: Iterable[Assembly]):
    """the user sees the title of both assemblies."""
    for assembly in assembly_list:
        expect(page.locator("main")).to_contain_text(assembly.title)


@then('the user should see the "question" of the Assembly')
def _(page: Page, assembly: Assembly):
    """the user should see the "question" of the Assembly."""
    expect(page.locator("main")).to_contain_text(assembly.question)


@then('the user should see the "title" of the Assembly')
def _(page: Page, assembly: Assembly):
    """the user should see the "title" of the Assembly."""
    expect(page.locator("main")).to_contain_text(assembly.title)


@then(parsers.parse('the user should see the assembly question "{assembly_question}"'))
def _(page: Page, assembly_question: str):
    """the user should see the assembly question "{assembly_question}"."""
    expect(page.locator("main")).to_contain_text(assembly_question)


@then(parsers.parse('the user should see the assembly title "{assembly_title}"'))
def _(page: Page, assembly_title: str):
    """the user should see the assembly title "{assembly_title}"."""
    expect(page).to_have_title(re.compile(rf"^\s*{re.escape(assembly_title)} - Project details\s+- OpenDLP$"))
    expect(page.get_by_role("heading", name=assembly_title, level=1)).to_be_visible()


@then("the user should see that they created it")
def _(page: Page):
    """the user should see that they created it."""
    expect(page.locator("main")).to_contain_text("By Test Admin at")


@then("the user should see the edited assembly")
def _(page: Page, assembly: Assembly):
    """the user should see the edited assembly."""
    expect(page).to_have_url(Urls.backoffice_assembly_url(str(assembly.id)))
    expect(page.locator("#project-question")).to_be_hidden()


@then("the user should see the created assembly")
def _(page: Page, test_database, assembly_title_for_lookup: str):
    """the user should see the created assembly."""
    # Before looking in the database we need to wait for the pages to finish loading
    wait_for_page_with_text(page, "Last Updated")
    # we don't have the whole assembly object, so we have to find it in the database
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        matching_assemblies = list(uow.assemblies.search_by_title(assembly_title_for_lookup))
        assert len(matching_assemblies) == 1
        assembly_id = matching_assemblies[0].id
    expect(page).to_have_url(Urls.backoffice_assembly_url(str(assembly_id)))
