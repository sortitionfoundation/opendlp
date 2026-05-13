"""ABOUTME: BDD tests for the grouped respondent view and the schema management UI
ABOUTME: Exercises the full UI stack via Playwright for the happy paths covered by unit + e2e tests"""

import uuid

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

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
    return None


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


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


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
