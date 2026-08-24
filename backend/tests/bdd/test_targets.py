"""ABOUTME: BDD tests for target percentages, hand-set notes, bulk edit and reordering
ABOUTME: Exercises the full UI stack via Playwright for the paths covered by unit + e2e tests"""

import uuid

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer.target_service import (
    add_target_value,
    create_target_category,
    get_targets_for_assembly,
    update_target_value,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import PLAYWRIGHT_TIMEOUT, Urls

scenarios("../../features/targets.feature")


_target_assembly_ids: dict[str, str] = {}

# The assembly the scenario currently under way is about. The dict above outlives
# a single scenario, so steps that do not name their assembly use this instead.
_current_assembly_id: list[str] = []


def _targets_url(assembly_id: str) -> str:
    return f"{Urls.base}/backoffice/assembly/{assembly_id}/targets"


def _row_for(page: Page, value: str):
    """The table row whose first cell is this target value."""
    return page.locator("tr").filter(has=page.get_by_role("cell", name=value, exact=False)).first


@given(parsers.parse('there is an assembly with targets called "{title}"'))
def assembly_with_targets(title: str, assembly_creator, admin_user, test_database) -> None:
    """One category of two values at 50% each, against 20 seats."""
    assembly = assembly_creator(title, number_to_select=20)
    _target_assembly_ids[title] = str(assembly.id)
    _current_assembly_id[:] = [str(assembly.id)]

    with SqlAlchemyUnitOfWork(test_database) as uow:
        category = create_target_category(uow, admin_user.id, assembly.id, name="Gender")
        add_target_value(uow, admin_user.id, assembly.id, category.id, value="Male", percentage=50.0)
        add_target_value(uow, admin_user.id, assembly.id, category.id, value="Female", percentage=50.0)


@given(parsers.parse('there is an assembly with two target categories called "{title}"'))
def assembly_with_two_categories(title: str, assembly_creator, admin_user, test_database) -> None:
    assembly = assembly_creator(title, number_to_select=20)
    _target_assembly_ids[title] = str(assembly.id)
    _current_assembly_id[:] = [str(assembly.id)]

    with SqlAlchemyUnitOfWork(test_database) as uow:
        create_target_category(uow, admin_user.id, assembly.id, name="Gender")
        create_target_category(uow, admin_user.id, assembly.id, name="Age")


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    """The ``admin_logged_in_page`` fixture handles the sign-in."""
    return


@given(parsers.parse('the "{value}" target was set by hand with the note "{note}"'))
def target_set_by_hand(value: str, note: str, admin_user, test_database) -> None:
    assembly_id = uuid.UUID(_current_assembly_id[0])
    with SqlAlchemyUnitOfWork(test_database) as uow:
        category = get_targets_for_assembly(uow, admin_user.id, assembly_id)[0]
        target_value = category.get_value(value)
        update_target_value(
            uow,
            admin_user.id,
            assembly_id,
            category.id,
            target_value.value_id,
            value=value,
            min_count=12,
            max_count=13,
            comment=note,
        )


@when(parsers.parse('I open the targets page for "{title}"'))
def open_targets_page(admin_logged_in_page: Page, title: str) -> None:
    admin_logged_in_page.goto(_targets_url(_target_assembly_ids[title]))


@when("I choose to edit all targets")
def choose_edit_all(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Edit all").click()


@when("I save all targets")
def save_all(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Save all").click()


@when(parsers.parse('I link the "{value}" target back to its percentage'))
def relink_target(admin_logged_in_page: Page, value: str) -> None:
    _row_for(admin_logged_in_page, value).get_by_role("button", name="Use percentage").click()


@when(parsers.parse('I move the "{name}" category down'))
def move_category_down(admin_logged_in_page: Page, name: str) -> None:
    heading = admin_logged_in_page.get_by_role("heading", name=name, exact=True)
    block = admin_logged_in_page.locator("div").filter(has=heading).last
    block.get_by_role("button", name="Move down").first.click()


@then(parsers.parse('I should see the percentage total "{total}"'))
def see_percentage_total(admin_logged_in_page: Page, total: str) -> None:
    expect(admin_logged_in_page.get_by_text(total).first).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{value}" target should show min "{minimum}" and max "{maximum}"'))
def target_shows_min_max(admin_logged_in_page: Page, value: str, minimum: str, maximum: str) -> None:
    row = _row_for(admin_logged_in_page, value)
    expect(row).to_contain_text(minimum, timeout=PLAYWRIGHT_TIMEOUT)
    expect(row).to_contain_text(maximum, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see "{text}"'))
def should_see(admin_logged_in_page: Page, text: str) -> None:
    expect(admin_logged_in_page.get_by_text(text).first).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should not see "{text}"'))
def should_not_see(admin_logged_in_page: Page, text: str) -> None:
    expect(admin_logged_in_page.get_by_text(text)).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then("I should see the bulk edit form")
def see_bulk_edit_form(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.locator("#save-all-form")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{first}" category should appear before the "{second}" category'))
def category_order(admin_logged_in_page: Page, first: str, second: str) -> None:
    headings = admin_logged_in_page.get_by_role("heading").all_text_contents()
    names = [h.strip() for h in headings]
    assert names.index(first) < names.index(second), f"expected {first} before {second} in {names}"
