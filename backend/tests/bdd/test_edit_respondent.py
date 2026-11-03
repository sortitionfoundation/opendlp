"""ABOUTME: BDD tests for the backoffice edit-respondent page
ABOUTME: Covers pre-selecting stored yes/no answers and showing why a save failed"""

import uuid
from typing import Any

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.respondent_field_schema import FieldType
from opendlp.service_layer.respondent_field_schema_service import get_schema, update_field
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import Urls

scenarios("../../features/edit-respondent.feature")


def _assembly_with_bool_attribute(
    assembly_creator, admin_user, test_database, label: str, stored_value: Any
) -> dict[str, str]:
    """An assembly whose one respondent holds `stored_value` for a BOOL attribute.

    The registration form stores a real JSON bool, which is what the edit form must read.
    """
    field_key = label.lower()
    assembly = assembly_creator(f"Edit respondent {uuid.uuid4().hex[:6]}")
    with SqlAlchemyUnitOfWork(test_database) as uow:
        import_respondents_from_csv(
            uow, admin_user.id, assembly.id, f"external_id,{field_key}\nR001,placeholder\n", replace_existing=True
        )
        schema = get_schema(uow, admin_user.id, assembly.id)
        field = next(f for f in schema if f.field_key == field_key)
        update_field(uow, admin_user.id, assembly.id, field.id, field_type=FieldType.BOOL, label=label)
        respondent = uow.respondents.get_by_assembly_id(assembly.id)[0]
        respondent.attributes = {**respondent.attributes, field_key: stored_value}
        uow.commit()
        return {"assembly_id": str(assembly.id), "respondent_id": str(respondent.id), "field_key": field_key}


@given(
    parsers.parse('there is an assembly with a respondent who answered yes to "{label}"'),
    target_fixture="edit_target",
)
def respondent_answered_yes(label: str, assembly_creator, admin_user, test_database) -> dict[str, str]:
    return _assembly_with_bool_attribute(assembly_creator, admin_user, test_database, label, True)


@given(
    parsers.parse('there is an assembly with a respondent who has not answered "{label}"'),
    target_fixture="edit_target",
)
def respondent_not_answered(label: str, assembly_creator, admin_user, test_database) -> dict[str, str]:
    return _assembly_with_bool_attribute(assembly_creator, admin_user, test_database, label, "")


@given("I am signed in as an admin user")
def admin_signed_in(admin_logged_in_page: Page) -> None:
    """The ``admin_logged_in_page`` fixture handles the sign-in."""


@when("I open the edit page for that respondent")
def open_edit_page(admin_logged_in_page: Page, edit_target: dict[str, str]) -> None:
    admin_logged_in_page.goto(
        f"{Urls.base}/backoffice/project/{edit_target['assembly_id']}/respondents/{edit_target['respondent_id']}/edit"
    )


@then(parsers.parse('"Yes" is selected for "{label}"'))
def yes_is_selected(admin_logged_in_page: Page, edit_target: dict[str, str]) -> None:
    expect(admin_logged_in_page.locator(f"#attr_{edit_target['field_key']}_1")).to_be_checked()


@when(parsers.parse('I enter the change note "{note}"'))
def enter_change_note(admin_logged_in_page: Page, note: str) -> None:
    admin_logged_in_page.locator("textarea#comment").fill(note)


@when("I save the changes")
def save_changes(admin_logged_in_page: Page) -> None:
    admin_logged_in_page.get_by_role("button", name="Save changes").click()


@then(parsers.parse('I see "{text}"'))
def see_text(admin_logged_in_page: Page, text: str) -> None:
    expect(admin_logged_in_page.get_by_text(text)).to_be_visible()


@then(parsers.parse('I see that there is a problem with "{label}"'))
def see_problem(admin_logged_in_page: Page, label: str) -> None:
    summary = admin_logged_in_page.get_by_role("alert").filter(has_text="There is a problem")
    expect(summary).to_be_visible()
    expect(summary.get_by_role("link", name=f"{label}:")).to_be_visible()


@when(parsers.parse('I follow the link to the problem with "{label}"'))
def follow_problem_link(admin_logged_in_page: Page, label: str) -> None:
    summary = admin_logged_in_page.get_by_role("alert").filter(has_text="There is a problem")
    summary.get_by_role("link", name=f"{label}:").click()


@then(parsers.parse('the first option for "{label}" has keyboard focus'))
def first_option_focused(admin_logged_in_page: Page, edit_target: dict[str, str]) -> None:
    expect(admin_logged_in_page.locator(f"#attr_{edit_target['field_key']}_1")).to_be_focused()
