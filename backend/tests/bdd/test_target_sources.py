"""ABOUTME: BDD tests for the target data sources checklist (registration step 1)
ABOUTME: Exercises exact-copy, age-ranges and lookup-table set-up, and the force-unlink confirmation, via Playwright"""

import re
import uuid
from datetime import UTC, datetime

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.respondent_field_schema import FieldType
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.respondent_field_schema_service import add_field
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import PLAYWRIGHT_TIMEOUT, Urls

scenarios("../../features/target-data-sources.feature")


_assembly_ids: dict[str, str] = {}


def _sources_url(assembly_id: str) -> str:
    return f"{Urls.base}/backoffice/assembly/{assembly_id}/target-sources"


def _row_for(page: Page, target_name: str):
    return page.locator(f"#target-sources-list li:has(h3:text-is('{target_name}'))")


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given(parsers.parse('there is an assembly with respondents imported from CSV called "{title}"'))
def assembly_with_csv_respondents(title: str, assembly_creator, admin_user, test_database) -> None:
    """A real CSV import so the schema exists, mirroring the field-schema feature's seeding."""
    assembly = assembly_creator(title, number_to_select=20)
    _assembly_ids[title] = str(assembly.id)

    csv_content = (
        "external_id,first_name,last_name,gender,postcode\n"
        "R001,Alice,Jones,Female,SW1A 1AA\n"
        "R002,Bob,Smith,Male,E1 6AN\n"
    )
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        import_respondents_from_csv(uow, admin_user.id, assembly.id, csv_content, replace_existing=True)


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    return


@given(parsers.parse('the assembly "{title}" has a "{field_key}" number field'))
def assembly_has_number_field(title: str, field_key: str, admin_user, test_database) -> None:
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        add_field(
            uow,
            admin_user.id,
            uuid.UUID(_assembly_ids[title]),
            field_key=field_key,
            field_type=FieldType.INTEGER,
        )


@given(parsers.parse('the assembly "{title}" has a "{name}" target with values "{values}"'))
@given(parsers.parse('the assembly "{title}" has an "{name}" target with values "{values}"'))
def assembly_has_target(title: str, name: str, values: str, test_database) -> None:
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=uuid.UUID(_assembly_ids[title]),
                name=name,
                values=[TargetValue(value=v.strip(), min=1, max=5) for v in values.split(",")],
            )
        )


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


def _setup_dialog(page: Page) -> Locator:
    """The set-up modal - scoped to its container, as the step itself is a dialog too."""
    return page.locator("#ts-modal-container").get_by_role("dialog")


@when(parsers.parse('I open the target data sources for "{title}"'))
def open_target_sources(admin_logged_in_page: Page, title: str) -> None:
    admin_logged_in_page.goto(_sources_url(_assembly_ids[title]))
    admin_logged_in_page.wait_for_load_state("networkidle")


@when(parsers.parse('I set up the "{target_name}" target as an exact copy'))
def set_up_exact_copy(admin_logged_in_page: Page, target_name: str) -> None:
    """Open the set-up modal by clicking the row itself, choose Exact copy, and save."""
    page = admin_logged_in_page
    # The centre of the card is clear of its buttons, so this exercises the whole-row link.
    _row_for(page, target_name).click()
    expect(_setup_dialog(page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # Choosing a method round-trips through the server and swaps the modal back in.
    with page.expect_response(lambda r: "setup-modal" in r.url):
        page.select_option('select[name="method"]', "exact")
    expect(_setup_dialog(page).get_by_text("will be created")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    page.get_by_role("button", name="Save").click()
    # A successful exact-copy save closes the modal via the out-of-band checklist swap.
    expect(_setup_dialog(page)).not_to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I set up the "{target_name}" target with age ranges from "{source_key}"'))
def set_up_age_ranges(admin_logged_in_page: Page, target_name: str, source_key: str) -> None:
    """Walk the modal: Age ranges method → reuse the number field → as-of date → save."""
    page = admin_logged_in_page
    _row_for(page, target_name).get_by_role("button", name="Set up", exact=True).click()
    expect(_setup_dialog(page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # Each change round-trips through the server and swaps the modal back in;
    # waiting on the response stops the next action racing the swap.
    with page.expect_response(lambda r: "setup-modal" in r.url):
        page.select_option('select[name="method"]', "age_bracket")
    # A reusable number field exists, so reuse should be offered and chosen;
    # flip to it if not (another server round-trip).
    reuse_radio = page.locator('input[name="source_mode"][value="reuse"]')
    expect(reuse_radio).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    if not reuse_radio.is_checked():
        with page.expect_response(lambda r: "setup-modal" in r.url):
            reuse_radio.check()
    reuse_select = page.locator('select[name="reuse_field_id"]')
    expect(reuse_select).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # Options are labelled "<label> (<field_key>)"; match on the key, select by value.
    option_value = reuse_select.locator("option", has_text=source_key).first.get_attribute("value")
    assert option_value, f"No source option offering {source_key!r}"
    with page.expect_response(lambda r: "setup-modal" in r.url):
        reuse_select.select_option(option_value)
    # Choosing the target's row pre-filled the brackets from its "16-24"-style values.
    expect(page.locator('input[name="boundaries"]')).to_have_value("25", timeout=PLAYWRIGHT_TIMEOUT)
    page.fill('input[name="as_of_day"]', "1")
    page.fill('input[name="as_of_month"]', "6")
    # The as-of year must be within a year of today, so never hard-code it.
    page.fill('input[name="as_of_year"]', str(datetime.now(UTC).year))
    page.get_by_role("button", name="Save").click()


@when(parsers.parse('I set up the "{target_name}" target to map from "{source_key}"'))
def set_up_lookup_table(admin_logged_in_page: Page, target_name: str, source_key: str) -> None:
    """Walk the modal: Map postcode to value → reuse the imported question → save."""
    page = admin_logged_in_page
    _row_for(page, target_name).get_by_role("button", name="Set up", exact=True).click()
    expect(_setup_dialog(page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    with page.expect_response(lambda r: "setup-modal" in r.url):
        page.select_option('select[name="method"]', "large_mapping")
    reuse_radio = page.locator('input[name="source_mode"][value="reuse"]')
    expect(reuse_radio).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    if not reuse_radio.is_checked():
        with page.expect_response(lambda r: "setup-modal" in r.url):
            reuse_radio.check()
    reuse_select = page.locator('select[name="reuse_field_id"]')
    expect(reuse_select).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    option_value = reuse_select.locator("option", has_text=f"({source_key})").first.get_attribute("value")
    assert option_value, f"No source option offering {source_key!r}"
    with page.expect_response(lambda r: "setup-modal" in r.url):
        reuse_select.select_option(option_value)
    with page.expect_response(lambda r: "configure" in r.url):
        page.get_by_role("button", name="Save").click()


@when(parsers.parse('I upload a lookup table mapping "{source_value}" to "{target_value}"'))
def upload_lookup_table(admin_logged_in_page: Page, source_value: str, target_value: str) -> None:
    page = admin_logged_in_page
    csv_bytes = f"postcode,Region\n{source_value},{target_value}\n".encode()
    page.locator('input[name="mapping_file"]').set_input_files({
        "name": "mapping.csv",
        "mimeType": "text/csv",
        "buffer": csv_bytes,
    })
    with page.expect_response(lambda r: r.url.endswith("/upload")):
        _setup_dialog(page).get_by_role("button", name="Upload", exact=True).click()


@when(parsers.parse('I tick "{label}"'))
def tick_checkbox(admin_logged_in_page: Page, label: str) -> None:
    # The native checkbox is visually hidden behind a styled box, so click its label as a person would.
    _setup_dialog(admin_logged_in_page).locator("label.checkbox-container", has_text=label).click()


@when(parsers.parse('I press the "{name}" button'))
def press_button(admin_logged_in_page: Page, name: str) -> None:
    page = admin_logged_in_page
    with page.expect_response(lambda r: r.request.method == "POST"):
        _setup_dialog(page).get_by_role("button", name=name, exact=True).click()


@when(parsers.parse('I open the more actions menu for the "{target_name}" target'))
def open_more_actions(admin_logged_in_page: Page, target_name: str) -> None:
    page = admin_logged_in_page
    _row_for(page, target_name).get_by_role("button", name=f"More actions for {target_name}").click()
    expect(_row_for(page, target_name).get_by_role("menu")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I focus the more actions button for the "{target_name}" target and press "{key}"'))
def focus_more_actions_and_press(admin_logged_in_page: Page, target_name: str, key: str) -> None:
    toggle = _row_for(admin_logged_in_page, target_name).get_by_role("button", name=f"More actions for {target_name}")
    toggle.focus()
    admin_logged_in_page.keyboard.press(key)


def _row_opener(page: Page, target_name: str):
    """The row's set-up or edit button - whichever its state shows - which is where focus returns."""
    return _row_for(page, target_name).locator("[data-focus-id]")


@when(parsers.parse('I focus the set-up button for the "{target_name}" target and press "{key}"'))
def focus_set_up_and_press(admin_logged_in_page: Page, target_name: str, key: str) -> None:
    _row_opener(admin_logged_in_page, target_name).focus()
    admin_logged_in_page.keyboard.press(key)
    expect(_setup_dialog(admin_logged_in_page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I choose the "{method}" method from the keyboard'))
def choose_method_from_keyboard(admin_logged_in_page: Page, method: str) -> None:
    """Changing the method re-renders the whole dialog, replacing the select that has focus."""
    page = admin_logged_in_page
    with page.expect_response(lambda r: "setup-modal" in r.url):
        page.locator('select[name="method"]:focus').select_option(method)
    expect(_setup_dialog(page).get_by_text("will be created")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when("I press Escape")
def press_escape(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.keyboard.press("Escape")


@when(parsers.parse('I choose "{item}" from the menu and confirm'))
def choose_menu_item_and_confirm(admin_logged_in_page: Page, item: str) -> None:
    page = admin_logged_in_page
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response(lambda r: r.request.method == "POST"):
        page.get_by_role("menuitem", name=item).click()


@when(parsers.parse('I rename the "{old_name}" target to "{new_name}" on the targets page'))
def rename_target(admin_logged_in_page: Page, old_name: str, new_name: str, request) -> None:
    page = admin_logged_in_page
    # The checklist page knows which assembly we're on; derive the targets URL from it.
    assembly_id = page.url.split("/assembly/")[1].split("/")[0]
    page.goto(f"{Urls.base}/backoffice/assembly/{assembly_id}/targets")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Edit targets").click()
    name_input = page.locator(f'#bulk-categories input[value="{old_name}"]')
    expect(name_input).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    name_input.fill(new_name)
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_load_state("networkidle")


@when("I confirm the unlinking")
def confirm_unlinking(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Break the links and save").click()
    admin_logged_in_page.wait_for_load_state("networkidle")


@when(parsers.parse('I open the respondent field schema editor for "{title}"'))
def open_schema_editor(admin_logged_in_page: Page, title: str) -> None:
    admin_logged_in_page.goto(f"{Urls.base}/backoffice/assembly/{_assembly_ids[title]}/respondent-schema")
    admin_logged_in_page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then(parsers.parse('the "{target_name}" target row should say "{text}"'))
def target_row_says(admin_logged_in_page: Page, target_name: str, text: str) -> None:
    expect(_row_for(admin_logged_in_page, target_name)).to_contain_text(text, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the set-up dialog should be on "{caption}"'))
@then(parsers.parse('the set-up dialog should say "{caption}"'))
def setup_dialog_says(admin_logged_in_page: Page, caption: str) -> None:
    expect(_setup_dialog(admin_logged_in_page)).to_contain_text(caption, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{name}" button should be hidden'))
def button_hidden(admin_logged_in_page: Page, name: str) -> None:
    button = _setup_dialog(admin_logged_in_page).locator("button", has_text=name)
    expect(button).to_have_count(1)
    expect(button).to_be_hidden(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see a warning toast saying "{text}"'))
def see_warning_toast(admin_logged_in_page: Page, text: str) -> None:
    """The recompute outcome arrives out-of-band in the floating alerts, and the set-up modal closes."""
    toast = admin_logged_in_page.locator("#floating-alerts [role='alert']", has_text=text)
    expect(toast).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    expect(toast).to_have_attribute("style", re.compile(r"--color-warning-100"), timeout=PLAYWRIGHT_TIMEOUT)
    expect(_setup_dialog(admin_logged_in_page)).not_to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the more actions menu for the "{target_name}" target should be closed'))
def more_actions_closed(admin_logged_in_page: Page, target_name: str) -> None:
    expect(_row_for(admin_logged_in_page, target_name).get_by_role("menu")).to_be_hidden(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('keyboard focus should be on the "{item}" menu item'))
def focus_on_menu_item(admin_logged_in_page: Page, item: str) -> None:
    expect(admin_logged_in_page.get_by_role("menuitem", name=item)).to_be_focused(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('keyboard focus should be on the more actions button for the "{target_name}" target'))
def focus_on_more_actions(admin_logged_in_page: Page, target_name: str) -> None:
    toggle = _row_for(admin_logged_in_page, target_name).get_by_role("button", name=f"More actions for {target_name}")
    expect(toggle).to_be_focused(timeout=PLAYWRIGHT_TIMEOUT)


@then("keyboard focus should be on the method chooser in the set-up dialog")
def focus_on_method_chooser(admin_logged_in_page: Page) -> None:
    expect(_setup_dialog(admin_logged_in_page).locator('select[name="method"]')).to_be_focused(
        timeout=PLAYWRIGHT_TIMEOUT
    )


@then("the checklist behind the set-up dialog should be out of reach")
def checklist_is_inert(admin_logged_in_page: Page) -> None:
    """Inert, so neither Tab nor a screen reader's browse mode reaches what the dialog covers."""
    step = admin_logged_in_page.locator('[role="dialog"][aria-labelledby="target-sources-title"]')
    expect(step).to_have_attribute("inert", "", timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('keyboard focus should be on the set-up button for the "{target_name}" target'))
def focus_on_set_up_button(admin_logged_in_page: Page, target_name: str) -> None:
    expect(_row_opener(admin_logged_in_page, target_name)).to_be_focused(timeout=PLAYWRIGHT_TIMEOUT)


@then("the target data sources should still be open")
def target_sources_still_open(admin_logged_in_page: Page) -> None:
    """Escape in the menu must not also close the step dialog around it."""
    page = admin_logged_in_page
    expect(page.get_by_role("dialog", name="Target data sources")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    assert page.url.endswith("/target-sources")


@then("I should be asked to confirm unlinking")
def asked_to_confirm_unlinking(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.get_by_text("registration questions linked")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the schema editor should list the "{field_key}" field'))
def schema_lists_field(admin_logged_in_page: Page, field_key: str) -> None:
    expect(admin_logged_in_page.locator(f"code:text-is('{field_key}')")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{field_key}" row should carry the "{tag}" tag'))
def row_carries_tag(admin_logged_in_page: Page, field_key: str, tag: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row.locator(".question-tags li", has_text=tag)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
