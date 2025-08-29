from playwright.sync_api import Page, expect
from pytest_bdd import given, then, when

from ..config import ADMIN_EMAIL, ADMIN_PASSWORD, FRESH_PASSWORD, Urls


@given("the user is on the login page")
def navigate_to_login_page(page: Page):
    page.goto(Urls.login)


@given("the user is on the register page")
def navigate_to_register_page(page: Page):
    page.goto(Urls.register)


@given("the user is on the dashboard page")
def navigate_to_dashboard_page(logged_in_page: Page):
    logged_in_page.goto(Urls.dashboard)


@when("the user logs in with valid credentials")
def login_with_valid_credentials(page: Page):
    page.fill('input[name="email"]', ADMIN_EMAIL)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')


@when("the user registers using an invalid invite code")
def fill_in_registration_form_invalid(page: Page):
    page.fill('input[name="invite_code"]', "invalidcode123")
    page.fill('input[name="email"]', ADMIN_EMAIL)
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.click('button[type="submit"]')


@when("the user registers using a valid invite code")
def fill_in_registration_form(page: Page, user_invite: str):
    page.fill('input[name="invite_code"]', user_invite)
    page.fill('input[name="email"]', "newuser@example.com")
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.click('button[type="submit"]')


@when("the user clicks the logout link")
def click_log_out_link(page: Page):
    page.get_by_text("Sign out").click()


@then("the user should be on the register page")
def verify_register(page: Page):
    # page.wait_for_url(Urls.register)
    expect(page).to_have_url(Urls.register)


@then("the user should be redirected to the dashboard")
def verify_dashboard(page: Page):
    # page.wait_for_url(Urls.dashboard)
    expect(page).to_have_url(Urls.dashboard)


@then("the user should be redirected to the front page")
def verify_front_page(page: Page):
    # page.wait_for_url(Urls.front_page)
    expect(page).to_have_url(Urls.front_page)
