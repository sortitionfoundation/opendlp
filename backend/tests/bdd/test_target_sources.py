"""ABOUTME: BDD tests for the target data sources checklist (registration step 1)
ABOUTME: Exercises exact-copy and age-ranges set-up, and the force-unlink confirmation, via Playwright"""

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
    """Open the row's set-up modal; Exact copy is the default method, so just save."""
    page = admin_logged_in_page
    _row_for(page, target_name).get_by_role("button", name="Set up", exact=True).click()
    expect(_setup_dialog(page)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    expect(page.locator('input[name="method"][value="exact"]')).to_be_checked(timeout=PLAYWRIGHT_TIMEOUT)
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
        page.check('input[name="method"][value="age_bracket"]')
    # The previous render had no reusable field, so "create" carried over; flip
    # to reusing the seeded number field (another server round-trip).
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
    admin_logged_in_page.get_by_role("button", name="Unlink the fields and save").click()
    admin_logged_in_page.wait_for_load_state("networkidle")


@when("I close the recompute report")
def close_recompute_report(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Done").click()
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


@then("I should see the recompute report")
def see_recompute_report(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.get_by_text("Respondents recomputed")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then("I should be asked to confirm unlinking")
def asked_to_confirm_unlinking(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.get_by_text("registration fields linked")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the schema editor should list the "{field_key}" field'))
def schema_lists_field(admin_logged_in_page: Page, field_key: str) -> None:
    expect(admin_logged_in_page.locator(f"code:text-is('{field_key}')")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{field_key}" row should carry the "{tag}" tag'))
def row_carries_tag(admin_logged_in_page: Page, field_key: str, tag: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row.locator(".govuk-tag", has_text=tag)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
