"""ABOUTME: BDD tests for My account: the names edited in place and the Change password dialog
ABOUTME: Covers what only a browser shows - focus across the htmx swap, Escape, and the dialog's focus"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from .config import DISPOSABLE_EMAIL, DISPOSABLE_PASSWORD, Urls

scenarios("../../features/my-account.feature")

# The disposable user is removed after each scenario, so a scenario may change its names.
NAME_ROWS = {"first": "#profile-first_name-row", "last": "#profile-last_name-row"}


@given("I am signed in with a password of my own")
def signed_in_with_a_password(page: Page, disposable_user) -> None:
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', DISPOSABLE_EMAIL)
    page.fill('input[name="password"]', DISPOSABLE_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.any_dashboard)


@given("I am on My account")
def on_my_account(page: Page) -> None:
    page.goto(f"{Urls.base}/profile")
    expect(page.get_by_role("heading", name="My account", level=1)).to_be_visible()


@when(parsers.parse('I edit my first name to "{name}" and press Enter'))
def edit_first_name_and_press_enter(page: Page, name: str) -> None:
    page.get_by_role("button", name="Edit first name").click()
    field = page.get_by_label("First name", exact=True)
    expect(field).to_be_focused()
    field.fill(name)
    with page.expect_response(lambda response: response.url.endswith("/profile/edit")):
        field.press("Enter")


@when(parsers.parse('I start editing my {which} name and type "{text}"'))
def start_editing_and_type(page: Page, which: str, text: str) -> None:
    page.get_by_role("button", name=f"Edit {which} name").click()
    field = page.get_by_label(f"{which.capitalize()} name", exact=True)
    expect(field).to_be_focused()
    field.fill(text)


@when("I press Escape")
def press_escape(page: Page) -> None:
    page.keyboard.press("Escape")


@when("I click the page heading")
def click_the_page_heading(page: Page) -> None:
    page.get_by_role("heading", name="My account", level=1).click()


@then(parsers.parse('my {which} name reads "{name}"'))
def name_reads(page: Page, which: str, name: str) -> None:
    expect(page.locator(NAME_ROWS[which]).get_by_text(name, exact=True)).to_be_visible()


@then(parsers.parse('the "{name}" button has focus'))
def button_has_focus(page: Page, name: str) -> None:
    expect(page.get_by_role("button", name=name, exact=True)).to_be_focused()


@when(parsers.parse('I press "{name}"'))
def press_button(page: Page, name: str) -> None:
    page.get_by_role("button", name=name, exact=True).click()


@then(parsers.parse('the "{name}" dialog is open'))
def dialog_is_open(page: Page, name: str) -> None:
    expect(page.get_by_role("dialog", name=name)).to_be_visible()


@then(parsers.parse('the "{label}" field has focus'))
def field_has_focus(page: Page, label: str) -> None:
    expect(page.get_by_label(label)).to_be_focused()


@then("no dialog is open")
def no_dialog_is_open(page: Page) -> None:
    expect(page.get_by_role("dialog")).to_have_count(0)


@when("I try to change my password with a wrong current password")
def change_password_with_a_wrong_current_password(page: Page) -> None:
    dialog = page.get_by_role("dialog", name="Change password")
    # The dialog puts focus in its first field a frame after it shows. Typing before
    # that - quicker than anyone types - would have focus move away mid-field.
    expect(dialog.locator("#current_password")).to_be_focused()
    dialog.locator("#current_password").fill("not-" + DISPOSABLE_PASSWORD)
    dialog.locator("#new_password").fill("Another-Passphrase-42")  # pragma: allowlist secret
    dialog.locator("#new_password_confirm").fill("Another-Passphrase-42")  # pragma: allowlist secret
    with page.expect_response(lambda response: response.url.endswith("/profile/change-password")):
        dialog.get_by_role("button", name="Change password").click()


@then(parsers.parse('the dialog says "{reason}"'))
def dialog_says(page: Page, reason: str) -> None:
    expect(page.get_by_role("dialog", name="Change password").get_by_text(reason)).to_be_visible()
