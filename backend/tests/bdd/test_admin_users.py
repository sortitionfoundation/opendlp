import pathlib
import re
from collections.abc import Callable

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, step, then, when

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole

from .config import DISPOSABLE_PASSWORD, Urls

# consider splitting up if these features grow many more tests
scenarios("../../features/admin-users.feature")

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


@when("the user creates an invite")
def _(page: Page):
    """the user creates an invite."""
    page.goto(Urls.admin)
    page.get_by_role("tab", name="Invites").click()
    page.get_by_role("button", name="Create invite").click()
    page.get_by_label("Admin — Full system access including user management").check()
    page.get_by_role("button", name="Create invite").click()


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
    normal_logged_in_page.goto(Urls.backoffice_dashboard)
    expect(normal_logged_in_page.get_by_role("heading", name="Your projects", level=1)).to_be_visible()
    expect(normal_logged_in_page.locator("main")).not_to_contain_text(assembly.title)


@when("the admin adds them to the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly, normal_user: User):
    """the admin adds them to the assembly, from the Team card of its details page."""
    page = admin_logged_in_page
    page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    team = page.locator("#team")
    team.get_by_role("button", name="Add a team member", exact=True).click()
    dialog = page.get_by_role("dialog", name="Add a team member")
    dialog.locator("#user_id_search").fill("normal")
    dialog.get_by_role("option", name=normal_user.email).click()
    dialog.locator("#team-member-role").select_option(value="CONFIRMATION_CALLER")
    with page.expect_response(lambda response: response.url.endswith("/team/add")):
        dialog.get_by_role("button", name="Add", exact=True).click()
    expect(team.get_by_role("row").filter(has_text=normal_user.email)).to_be_visible()


@when("the admin removes them from the assembly")
def _(admin_logged_in_page: Page, assembly: Assembly, normal_user: User):
    """the admin removes them from the assembly, from the Team card of its details page."""
    page = admin_logged_in_page
    page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    team = page.locator("#team")
    page.once("dialog", lambda dialog: dialog.accept())
    team.get_by_role("row").filter(has_text=normal_user.email).get_by_role("button", name="Remove").click()
    expect(team).not_to_contain_text(normal_user.email)


@then("the non-admin user can see the assembly")
def _(normal_logged_in_page: Page, assembly: Assembly):
    """the non-admin user can see the assembly."""
    normal_logged_in_page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    expect(normal_logged_in_page.get_by_role("heading", name=assembly.title, level=1)).to_be_visible()


def _disable_account(page: Page, user: User) -> None:
    """Confirm Disable account in its dialog on the user's page."""
    page.goto(f"{Urls.admin_users}/{user.id}")
    page.get_by_role("button", name="Disable account").click()
    page.get_by_role("alertdialog").get_by_role("button", name="Disable account").click()
    expect(page.locator("#floating-alerts")).to_contain_text("Account disabled")


def _sign_in_attempt(page: Page, email: str, password: str) -> None:
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')


@given("there is a disposable user")
def _(disposable_user: User):
    """there is a disposable user."""
    assert disposable_user.is_active


@when("the admin disables their account")
@given("the admin has disabled their account")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the admin disables their account."""
    _disable_account(admin_logged_in_page, disposable_user)


@then("the disposable user cannot sign in")
def _(page: Page, disposable_user: User):
    """the disposable user cannot sign in."""
    _sign_in_attempt(page, disposable_user.email, DISPOSABLE_PASSWORD)
    expect(page.locator("#floating-alerts")).to_contain_text("Invalid email or password")


@when("the admin enables their account")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the admin enables their account."""
    admin_logged_in_page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    admin_logged_in_page.get_by_role("button", name="Enable account").click()
    admin_logged_in_page.get_by_role("alertdialog").get_by_role("button", name="Enable account").click()
    expect(admin_logged_in_page.locator("#floating-alerts")).to_contain_text("Account enabled")


@when("the admin starts to disable their account and cancels")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the admin starts to disable their account and cancels."""
    page = admin_logged_in_page
    page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    opener = page.get_by_role("button", name="Disable account")
    opener.click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("Disable this account?")
    expect(dialog.get_by_role("button", name="Cancel")).to_be_focused()
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    expect(opener).to_be_focused()


@then("the disposable user's account is still active")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the disposable user's account is still active."""
    admin_logged_in_page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    expect(admin_logged_in_page.get_by_role("button", name="Disable account")).to_be_visible()


@then("the disposable user still cannot sign in with their old password")
def _(page: Page, disposable_user: User):
    """the disposable user still cannot sign in with their old password."""
    _sign_in_attempt(page, disposable_user.email, DISPOSABLE_PASSWORD)
    expect(page.locator("#floating-alerts")).to_contain_text("Invalid email or password")


@when(parsers.parse('the admin edits their first name to "{name}" and presses Enter'))
def _(admin_logged_in_page: Page, disposable_user: User, name: str):
    """the admin edits their first name and presses Enter."""
    page = admin_logged_in_page
    page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    page.get_by_role("button", name="Edit first name").click()
    field = page.get_by_label("First name", exact=True)
    expect(field).to_be_focused()
    field.fill(name)
    with page.expect_response(lambda response: response.url.endswith(f"/admin/users/{disposable_user.id}/name")):
        field.press("Enter")


@then(parsers.parse('the admin sees the first name "{name}" without leaving the page'))
def _(admin_logged_in_page: Page, disposable_user: User, name: str):
    """the admin sees the saved first name in the row, with focus back on the pencil."""
    page = admin_logged_in_page
    expect(page.locator("#admin-user-first_name-row")).to_contain_text(name)
    expect(page.get_by_role("button", name="Edit first name")).to_be_focused()
    expect(page.locator("#floating-alerts")).to_contain_text("updated successfully")
    assert page.url.endswith(f"/admin/users/{disposable_user.id}")


@then(parsers.parse('the user\'s first name is "{name}" after a reload'))
def _(admin_logged_in_page: Page, name: str):
    """the saved name survives a reload."""
    admin_logged_in_page.reload()
    expect(admin_logged_in_page.locator("#admin-user-first_name-row")).to_contain_text(name)


@when("the admin changes their role to Organiser")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the admin changes the role in the dialog."""
    page = admin_logged_in_page
    page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    page.get_by_role("button", name="Change role").click()
    dialog = page.get_by_role("dialog", name="Change role")
    expect(dialog).to_be_visible()
    dialog.get_by_label("Organiser — Can create projects, and manage the ones they belong to").check()
    dialog.get_by_role("button", name="Save role").click()
    expect(page.locator("#floating-alerts")).to_contain_text("updated successfully")


@then("the user's role is Organiser")
def _(admin_logged_in_page: Page, disposable_user: User):
    """the role row shows Organiser."""
    admin_logged_in_page.goto(f"{Urls.admin_users}/{disposable_user.id}")
    row = admin_logged_in_page.locator("dl > div", has_text="Global role")
    expect(row.locator("strong").first).to_have_text("Organiser")


@given("the admin has searched the users for the disposable user among organisers")
def _(admin_logged_in_page: Page, disposable_user: User):
    """search for the user by email, with the role filter on Organiser."""
    page = admin_logged_in_page
    page.goto(Urls.admin_users)
    clear = page.get_by_role("button", name="Clear search")
    expect(clear).to_be_hidden()
    page.get_by_label("Search by name or email").fill(disposable_user.email)
    expect(clear).to_be_visible()
    page.get_by_label("Role").select_option("organiser")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_label("Search by name or email")).to_have_value(disposable_user.email)


@when("the admin clears the search")
def _(admin_logged_in_page: Page):
    """press the clear icon inside the search box."""
    page = admin_logged_in_page
    with page.expect_navigation():
        page.get_by_role("button", name="Clear search").click()


@then("the search is empty and the role filter is kept")
def _(admin_logged_in_page: Page):
    """the list reloads without the search term but still filtered by role."""
    page = admin_logged_in_page
    expect(page.get_by_label("Search by name or email")).to_have_value("")
    expect(page.get_by_role("button", name="Clear search")).to_be_hidden()
    expect(page.get_by_label("Role")).to_have_value("organiser")
    assert "role=organiser" in page.url


@when("the admin opens the users export dialog")
def _(admin_logged_in_page: Page):
    """open the Export dialog from the users list."""
    page = admin_logged_in_page
    page.goto(Urls.admin_users)
    page.get_by_role("button", name="Export").click()
    dialog = page.get_by_role("dialog", name="Export users")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("CSV")).to_be_checked()


@then("a CSV of the users downloads when the admin runs the export", target_fixture="users_csv")
def _(admin_logged_in_page: Page) -> str:
    """run the export and read the downloaded file."""
    page = admin_logged_in_page
    dialog = page.get_by_role("dialog", name="Export users")
    with page.expect_download() as download_info:
        dialog.get_by_role("button", name="Export").click()
    download = download_info.value
    assert download.suggested_filename == "opendlp-users.csv"
    expect(dialog).to_be_hidden()
    return pathlib.Path(download.path()).read_text(encoding="utf-8")


@then("the CSV includes the disposable user")
def _(users_csv: str, disposable_user: User):
    """the disposable user has a row."""
    assert disposable_user.email in users_csv


@when("the admin cancels the users export")
def _(admin_logged_in_page: Page):
    """press Cancel in the dialog."""
    dialog = admin_logged_in_page.get_by_role("dialog", name="Export users")
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()


@then("keyboard focus is back on the users Export button")
def _(admin_logged_in_page: Page):
    """focus returns to the button that opened the dialog."""
    expect(admin_logged_in_page.locator('[data-focus-id="users-export"]')).to_be_focused()
