"""ABOUTME: BDD tests for the grouped respondent view and the schema management UI
ABOUTME: Exercises the full UI stack via Playwright for the happy paths covered by unit + e2e tests"""

import uuid

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.respondent_field_schema import FieldType
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.respondent_field_schema_service import add_field
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import PLAYWRIGHT_TIMEOUT, Urls

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


@given(parsers.parse('the assembly "{title}" has a "{field_key}" number field'))
def assembly_has_number_field(title: str, field_key: str, admin_user, test_database) -> None:
    """Add an INTEGER field so it can serve as an age-bracket derivation source."""
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        add_field(
            uow,
            admin_user.id,
            uuid.UUID(_schema_assembly_ids[title]),
            field_key=field_key,
            field_type=FieldType.INTEGER,
        )


@given(parsers.parse('the assembly "{title}" has an "{name}" target with values "{values}"'))
def assembly_has_target(title: str, name: str, values: str, test_database) -> None:
    """Seed a target category whose values the derived field will take as its options."""
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        uow.target_categories.add(
            TargetCategory(
                assembly_id=uuid.UUID(_schema_assembly_ids[title]),
                name=name,
                values=[TargetValue(value=v.strip(), min=1, max=5) for v in values.split(",")],
            )
        )


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
    # Each row has two hidden-input move forms; the "up" one is the first.
    move_button = row.locator("button", has_text="↑").first
    move_button.click()
    admin_logged_in_page.wait_for_load_state("networkidle")


@when("I open the add-field modal")
def open_add_field_modal(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Add a field").click()
    expect(admin_logged_in_page.get_by_role("dialog")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I save a new choice field labelled "{label}" with options "{first}" and "{second}"'))
def save_choice_field_via_modal(admin_logged_in_page: Page, label: str, first: str, second: str) -> None:
    """Fill the modal: label, choice type (HTMX re-render), two option rows, save."""
    page = admin_logged_in_page
    page.fill('input[name="label"]', label)
    page.check("#field-modal-type-choice")
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
    expect(page.get_by_role("dialog")).not_to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I create an age-bracket derived field feeding "{target}" from "{source_key}"'))
def create_age_bracket_derived_field(admin_logged_in_page: Page, target: str, source_key: str) -> None:
    """Walk the derived panel: type → target → source → age config → save."""
    page = admin_logged_in_page
    page.get_by_role("button", name="Add a field").click()
    expect(page.get_by_role("dialog")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    page.check("#field-modal-type-derived")
    target_select = page.locator("#derived-target")
    expect(target_select).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    target_select.select_option(target)
    # Choosing the target re-renders the panel and pre-fills the brackets from
    # its "16-24"-style values — wait for that swap before touching inputs.
    expect(page.locator('input[name="boundaries"]')).to_have_value("25", timeout=PLAYWRIGHT_TIMEOUT)
    source_select = page.locator("#derived-source")
    source_select.select_option(source_key)
    # The source change re-renders again; the 1-January note only exists in the
    # refreshed panel because year_of_birth is an INTEGER source.
    expect(page.get_by_text("1 January")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    # The as-of date stays blank (the assembly has no first date), so fill it.
    page.fill('input[name="as_of_day"]', "1")
    page.fill('input[name="as_of_month"]', "6")
    page.fill('input[name="as_of_year"]', "2026")
    page.get_by_role("button", name="Save").click()


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("I should see the recompute report")
def see_recompute_report(admin_logged_in_page: Page) -> None:
    expect(admin_logged_in_page.get_by_text("Respondents recomputed")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when("I close the recompute report")
def close_recompute_report(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Done").click()
    admin_logged_in_page.wait_for_load_state("networkidle")


@then(parsers.parse('the "{field_key}" row should summarise its options as "{summary}"'))
def row_summarises_options(admin_logged_in_page: Page, field_key: str, summary: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row).to_contain_text(summary, timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the "{field_key}" row should carry the "{tag}" tag'))
def row_carries_tag(admin_logged_in_page: Page, field_key: str, tag: str) -> None:
    row = admin_logged_in_page.locator(f"tr:has(code:text-is('{field_key}'))")
    expect(row.locator(".govuk-tag", has_text=tag)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the "{heading}" group heading'))
def see_group_heading(admin_logged_in_page: Page, heading: str) -> None:
    expect(admin_logged_in_page.locator("h2", has_text=heading)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('I should see the "{label}" collapsible block'))
def see_collapsible_block(admin_logged_in_page: Page, label: str) -> None:
    expect(admin_logged_in_page.locator("details", has_text=label)).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the schema editor should list the "{field_key}" field'))
def schema_lists_field(admin_logged_in_page: Page, field_key: str) -> None:
    expect(admin_logged_in_page.locator(f"code:text-is('{field_key}')")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


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
