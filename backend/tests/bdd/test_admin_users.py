import re
from collections.abc import Callable

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, step, then, when

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole

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


@given("there is a non-admin user")
def _(normal_user: User):
    """there is a non-admin user."""
    assert normal_user.global_role == GlobalRole.USER


@given("the non-admin user is a manager for the assembly")
def _(normal_user: User, assembly: Assembly, assembly_user_role_creator: Callable):
    """the non-admin user is a manager for the assembly."""
    assembly_user_role_creator(assembly=assembly, user=normal_user)


@step("the non-admin user cannot see the assembly")
def _(normal_logged_in_page: Page, assembly: Assembly):
    """the non-admin user cannot see the assembly."""
    normal_logged_in_page.goto(Urls.dashboard)
    expect(normal_logged_in_page.locator("main")).not_to_contain_text(assembly.title)


@when("the admin adds them to the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly, normal_user: User):
    """the admin adds them to the assembly."""
    admin_logged_in_page.goto(Urls.for_assembly("view_assembly_members", str(assembly.id)))
    # Open the "Add User to Assembly" details section
    admin_logged_in_page.get_by_text("Add User to Assembly").locator("visible=true").click()
    # Search for the normal user by email using the HTMX search input
    search_input = admin_logged_in_page.locator("#user_search")
    search_input.type(normal_user.email)
    # Wait for search results to appear
    admin_logged_in_page.wait_for_selector(".search-result-item")
    # Click on the matching user result
    admin_logged_in_page.get_by_role("button", name=re.compile(normal_user.email)).first.click()
    # Select the default role (Confirmation Caller)
    admin_logged_in_page.get_by_label("Confirmation Caller - Can call confirmations for selected participants").check()
    # Submit the form
    admin_logged_in_page.get_by_role("button", name="Add User to Assembly").click()
    # Wait for the success message
    expect(admin_logged_in_page.locator(".govuk-notification-banner")).to_contain_text("added to assembly")


@when("the admin removes them from the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly, normal_user: User):
    """the admin removes them from the assembly."""
    admin_logged_in_page.goto(Urls.for_assembly("view_assembly_members", str(assembly.id)))
    # Find the remove button for the normal user in the team members table
    # TODO: consider matching by user if we ever have more than one
    remove_button = admin_logged_in_page.get_by_role("button", name="Remove").first
    # Set up the dialog handler BEFORE clicking to catch the confirmation dialog
    admin_logged_in_page.on("dialog", lambda dialog: dialog.accept())
    # Click the remove button (it will show a confirmation dialog which we'll accept)
    remove_button.click()
    # Wait for the success message
    expect(admin_logged_in_page.locator(".govuk-notification-banner")).to_contain_text("removed from assembly")


@then("the non-admin user can see the assembly")
def _(normal_logged_in_page: Page, assembly: Assembly):
    """the non-admin user can see the assembly."""
    # Refresh the page to see the updated assembly list (user was just added)
    # and as we just switched users, we'll be back at the dashboard page
    normal_logged_in_page.goto(Urls.for_assembly("view_assembly", str(assembly.id)))
    expect(normal_logged_in_page.locator("main")).to_contain_text(assembly.title)
