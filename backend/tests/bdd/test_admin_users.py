import re

from playwright.sync_api import Page, expect
from pytest_bdd import scenarios, then, when

from .config import Urls

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
