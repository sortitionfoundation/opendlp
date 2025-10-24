from collections.abc import Callable

from playwright.sync_api import Page, expect
from pytest_bdd import given, then, when
from sqlalchemy.orm import sessionmaker

from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.bdd.helpers import wait_for_page_with_text

from ..config import ADMIN_EMAIL, ADMIN_PASSWORD, FRESH_PASSWORD, Urls

NEWUSER_EMAIL = "newuser@example.com"


@given("the user is signing in")
def _(page: Page):
    """the user is signing in."""
    page.goto(Urls.login)


@given("the user is starting to register")
def _(logged_out_page: Page):
    """the user is starting to register."""
    logged_out_page.goto(Urls.register)


@given("the user is signed in")
def _(admin_logged_in_page: Page):
    """the user is signed in."""
    admin_logged_in_page.goto(Urls.dashboard)


@given("there is an assembly created", target_fixture="assembly")
def _(assembly_creator: Callable):
    """there is an assembly created."""
    assembly = assembly_creator("To be or not to be?")
    return assembly


@when("the user uses valid credentials")
def _(page: Page):
    """the user uses valid credentials."""
    page.fill('input[name="email"]', ADMIN_EMAIL)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')


@when("the user uses an invalid invite code")
def _(page: Page):
    """the user uses an invalid invite code."""
    page.fill('input[name="invite_code"]', "invalidcode123")
    page.fill('input[name="email"]', NEWUSER_EMAIL)
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.get_by_role("checkbox", name="Accept Data Agreement").check()
    # Note: Don't check data agreement here - let the explicit steps handle it


@when("the user uses a valid invite code")
def _(page: Page, user_invite: str):
    """the user uses a valid invite code."""
    page.fill('input[name="invite_code"]', user_invite)
    page.fill('input[name="email"]', NEWUSER_EMAIL)
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.get_by_role("checkbox", name="Accept Data Agreement").check()
    # Note: Don't check data agreement here - let the explicit steps handle it


@when("the user finishes registration")
def _(page: Page):
    """the user finishes registration."""
    page.click('button[type="submit"]')


@when("the user signs out")
def _(page: Page):
    """the user signs out."""
    page.get_by_text("Sign out").click()


@when("the user accepts the data agreement")
def _(page: Page):
    """the user accepts the data agreement."""
    checkbox = page.get_by_role("checkbox", name="Accept Data Agreement")
    if not checkbox.is_checked():
        checkbox.check()


@when("the user does not accept the data agreement")
def _(page: Page):
    """the user does not accept the data agreement."""
    checkbox = page.get_by_role("checkbox", name="Accept Data Agreement")
    if checkbox.is_checked():
        checkbox.uncheck()


@then("the user should be directed to try registering again")
def _(page: Page):
    """the user should be directed to try registering again."""
    expect(page).to_have_url(Urls.register)


@then("the user should not be registered")
def _(test_database: sessionmaker):
    """the user should be registered."""
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        user = uow.users.get_by_email(NEWUSER_EMAIL)
        assert user is None


@then("the user should be registered")
def _(page: Page, test_database: sessionmaker):
    """the user should be registered."""
    wait_for_page_with_text(page, "Your Assemblies")  # text from the dashboard page
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        user = uow.users.get_by_email(NEWUSER_EMAIL)
        assert user is not None


@then("the user should see the default view for an authorised user")
def _(page: Page):
    """the user should see the default view for an authorised user."""
    expect(page).to_have_url(Urls.dashboard)


@then("the user should see the default view for an anonymous user")
def _(page: Page):
    """the user should see the default view for an anonymous user."""
    expect(page).to_have_url(Urls.front_page)
