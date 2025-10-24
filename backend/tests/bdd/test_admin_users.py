import re

import pytest
from playwright.sync_api import Page, expect
from pytest_bdd import given, scenario, scenarios, then, when

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole

from .config import Urls


@pytest.mark.skip
@scenario("../../features/admin-users.feature", "Add user to assembly")
def test_add_user_to_assembly():
    pass


# consider splitting up if these features grow many more tests
scenarios("../../features/admin-users.feature")

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


@when("the user creates an invite")
def _(page: Page):
    """the user creates an invite."""
    page.goto(Urls.admin)
    invite_links = page.get_by_text("Manage Invites")
    invite_links.last.click()
    page.get_by_text("Create New Invite").click()
    page.get_by_label("Admin - Full system access including user management").check()
    page.click('button[type="submit"]')


@then("the user sees the invite to give to the user")
def _(page: Page):
    """the user sees the invite to give to the user."""
    expect(page.locator("main")).to_contain_text(re.compile(r"http://[^/]+/auth/register/[A-Z0-9]{12}"))


@given("there is a non-admin user")
def _(normal_user: User):
    """there is a non-admin user."""
    assert normal_user.global_role == GlobalRole.USER


@given("the non-admin user cannot see the assembly")
def _(normal_logged_in_page: Page, assembly: Assembly):
    """the non-admin user cannot see the assembly."""
    expect(normal_logged_in_page.locator("main")).not_to_contain_text(assembly.title)


@when("the admin adds them to the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly, normal_user: User):
    """the admin adds them to the assembly."""
    admin_logged_in_page.goto(Urls.for_assembly("view_assembly", str(assembly.id)))
    # admin_logged_in_page.get_by_text("Add user to assembly").click()
    # TODO: find the normal_user, add them to the project


@then("the non-admin user can see the assembly")
def _(normal_logged_in_page: Page, assembly: Assembly):
    """the non-admin user can see the assembly."""
    expect(normal_logged_in_page.locator("main")).to_contain_text(assembly.title)
