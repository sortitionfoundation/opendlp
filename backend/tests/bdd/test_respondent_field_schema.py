"""ABOUTME: BDD tests for the grouped respondent view and the schema management UI
ABOUTME: Exercises the full UI stack via Playwright for the happy paths covered by unit + e2e tests"""

import uuid

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import PLAYWRIGHT_TIMEOUT, Urls
from .helpers import assert_step_dialog_dimmed

scenarios("../../features/respondent-field-schema.feature")


# ---------------------------------------------------------------------------
# Lightweight cache so later steps can look up assembly IDs by title.
# ---------------------------------------------------------------------------


_schema_assembly_ids: dict[str, str] = {}


def _url_for_schema_page(assembly_id: str) -> str:
    return f"{Urls.base}/backoffice/assembly/{assembly_id}/respondent-schema"


def _url_for_respondent_page(assembly_id: str, respondent_id: str) -> str:
    return f"{Urls.base}/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given(parsers.parse('there is an assembly with respondents imported from CSV called "{title}"'))
def assembly_with_csv_respondents(title: str, assembly_creator, admin_user, test_database) -> None:
    """Create an assembly and seed it by running a real CSV import.

    Running the import (rather than ``bulk_add``) triggers schema population,
    which is what every scenario in this feature relies on.
    """
    assembly = assembly_creator(title, number_to_select=20)
    _schema_assembly_ids[title] = str(assembly.id)

    csv_content = (
        "external_id,first_name,last_name,gender,postcode,custom_notes\n"
        "R001,Alice,Jones,Female,SW1A 1AA,note one\n"
        "R002,Bob,Smith,Male,E1 6AN,note two\n"
    )
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        import_respondents_from_csv(
            uow,
            admin_user.id,
            assembly.id,
            csv_content,
            replace_existing=True,
        )


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    """The ``admin_logged_in_page`` fixture handles the sign-in."""
    # Nothing to do — the fixture performs the login.
    return


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when(parsers.parse('I open the first respondent for "{title}"'))
def open_first_respondent(admin_logged_in_page: Page, title: str, test_database) -> None:
    assembly_id = _schema_assembly_ids[title]
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        respondents = uow.respondents.get_by_assembly_id(uuid.UUID(assembly_id))
        assert respondents, f"No respondents seeded for assembly {title!r}"
        # Pick a deterministic one so the test result doesn't depend on ordering.
        respondent = min(respondents, key=lambda r: r.external_id)
        respondent_id = str(respondent.id)
    admin_logged_in_page.goto(_url_for_respondent_page(assembly_id, respondent_id))
    admin_logged_in_page.wait_for_load_state("networkidle")


@when(parsers.parse('I open the respondent field schema editor for "{title}"'))
def open_schema_editor(admin_logged_in_page: Page, title: str) -> None:
    assembly_id = _schema_assembly_ids[title]
    admin_logged_in_page.goto(_url_for_schema_page(assembly_id))
    admin_logged_in_page.wait_for_load_state("networkidle")


@when(parsers.parse('I move the "{field_key}" field up'))
def move_field_up(admin_logged_in_page: Page, field_key: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # Moving lives in the row's "more actions" menu.
    row.get_by_role("button", name="More actions for").click()
    row.get_by_role("menuitem", name="Move up").click()
    admin_logged_in_page.wait_for_load_state("networkidle")


def _field_dialog(page: Page) -> Locator:
    """The field modal - scoped to its container, as the step itself is a dialog too."""
    return page.locator("#field-modal-container").get_by_role("dialog")


@when("I open the add-field modal")
def open_add_field_modal(admin_logged_in_page: Page) -> None:
    # Every section has its own add button; use the catch-all section's.
    admin_logged_in_page.get_by_role("button", name="Add a question to Other").click()
    expect(_field_dialog(admin_logged_in_page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I choose "{item}" from the "{field_key}" row menu and confirm'))
def choose_row_menu_item_and_confirm(admin_logged_in_page: Page, item: str, field_key: str) -> None:
    page = admin_logged_in_page
    row = page.locator(f"tr:has(code:text-is('{field_key}'))")
    row.get_by_role("button", name="More actions for").click()
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_navigation():
        row.get_by_role("menuitem", name=item).click()
    page.wait_for_load_state("networkidle")


@when(parsers.parse('I click the Edit button on the "{field_key}" row'))
def click_field_row_edit(admin_logged_in_page: Page, field_key: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    row.get_by_role("button", name="Edit").click()


@when(parsers.parse('I save a new choice field labelled "{label}" with options "{first}" and "{second}"'))
def save_choice_field_via_modal(admin_logged_in_page: Page, label: str, first: str, second: str) -> None:
    """Fill the modal: label, radio choice type (HTMX re-render), two option rows, save."""
    page = admin_logged_in_page
    page.fill('input[name="label"]', label)
    page.select_option('select[name="question_type"]', "choice_radio")
    # The type change re-renders the form fragment; the options editor appears.
    first_option = page.locator('input[name="option_value"]').first
    expect(first_option).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # The re-render preserved the label; fill the first option, add a second row.
    first_option.fill(first)
    page.get_by_role("button", name="Add another option").click()
    second_option = page.locator('input[name="option_value"]').nth(1)
    expect(second_option).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    expect(page.locator('input[name="option_value"]').first).to_have_value(first, timeout=PLAYWRIGHT_TIMEOUT)
    second_option.fill(second)
    page.get_by_role("button", name="Save").click()
    # A successful save closes the modal via the out-of-band editor swap.
    expect(_field_dialog(page)).not_to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I choose the "{question_type}" question type'))
def choose_question_type(admin_logged_in_page: Page, question_type: str) -> None:
    """Pick a type from the dropdown; the change re-renders the form fragment."""
    dialog = _field_dialog(admin_logged_in_page)
    dialog.locator('select[name="question_type"]').select_option(question_type)
    expect(dialog.locator('select[name="question_type"]')).to_have_value(question_type, timeout=PLAYWRIGHT_TIMEOUT)


@when("I turn the required switch off")
def turn_required_switch_off(admin_logged_in_page: Page) -> None:
    """Found by name, not accessible name: the label - and so the name - changes with the switch."""
    switch = _field_dialog(admin_logged_in_page).locator('input[name="required"]')
    switch.uncheck(force=True)
    expect(switch).not_to_be_checked(timeout=PLAYWRIGHT_TIMEOUT)


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then(parsers.parse('the edit modal for "{label}" should be open'))
def edit_modal_open(admin_logged_in_page: Page, label: str) -> None:
    dialog = _field_dialog(admin_logged_in_page)
    expect(dialog).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    expect(dialog.locator('input[name="label"]')).to_have_value(label, timeout=PLAYWRIGHT_TIMEOUT)


@then("the question list behind the edit modal should be dimmed")
def question_list_is_dimmed(admin_logged_in_page: Page) -> None:
    assert_step_dialog_dimmed(admin_logged_in_page, "#field-modal-container")


@then(parsers.parse('the "{field_key}" row should summarise its options as "{summary}"'))
def row_summarises_options(admin_logged_in_page: Page, field_key: str, summary: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row).to_contain_text(summary, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the "{heading}" group heading'))
def see_group_heading(admin_logged_in_page: Page, heading: str) -> None:
    expect(admin_logged_in_page.locator("h2", has_text=heading)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the "{label}" collapsible block'))
def see_collapsible_block(admin_logged_in_page: Page, label: str) -> None:
    expect(admin_logged_in_page.locator("details", has_text=label)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the schema editor should list the "{field_key}" field'))
def schema_lists_field(admin_logged_in_page: Page, field_key: str) -> None:
    expect(admin_logged_in_page.locator(f"code:text-is('{field_key}')")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the schema editor should not list the "{field_key}" field'))
def schema_does_not_list_field(admin_logged_in_page: Page, field_key: str) -> None:
    expect(admin_logged_in_page.locator(f"code:text-is('{field_key}')")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{earlier_key}" field should appear before the "{later_key}" field'))
def field_order(admin_logged_in_page: Page, earlier_key: str, later_key: str) -> None:
    # Find the row index of each field within the same group's table. The template
    # lays out each group's fields as consecutive <tr>s, so the first occurrence
    # of each <code> in the page is the row we care about.
    earlier = admin_logged_in_page.locator(f"code:text-is('{earlier_key}')").first
    later = admin_logged_in_page.locator(f"code:text-is('{later_key}')").first
    expect(earlier).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    expect(later).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)

    earlier_box = earlier.bounding_box()
    later_box = later.bounding_box()
    assert earlier_box is not None, f"{earlier_key!r} has no bounding box"
    assert later_box is not None, f"{later_key!r} has no bounding box"
    assert earlier_box["y"] < later_box["y"], (
        f"Expected {earlier_key!r} to appear before {later_key!r} on the page, "
        f"but earlier.y={earlier_box['y']} is not less than later.y={later_box['y']}"
    )


@then(parsers.parse('the required switch should read "{text}"'))
def required_switch_reads(admin_logged_in_page: Page, text: str) -> None:
    """Only the label for the switch's current state is visible, so inner text is the one that shows."""
    switch_label = _field_dialog(admin_logged_in_page).locator("label.switch-container")
    expect(switch_label).to_have_text(text, use_inner_text=True, timeout=PLAYWRIGHT_TIMEOUT)
