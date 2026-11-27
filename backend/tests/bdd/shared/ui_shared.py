import re
from collections.abc import Callable

from playwright.sync_api import Page, expect
from pytest_bdd import given, then, when
from sqlalchemy.orm import sessionmaker

from opendlp.config import get_data_agreement_version, get_terms_version
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from ..config import ADMIN_EMAIL, ADMIN_PASSWORD, FRESH_PASSWORD, Urls

NEWUSER_EMAIL = "newuser@example.com"
AGREEMENT_LABEL = "I agree to the Terms and Conditions and the Data Agreement"
EMAILS_SENTENCE = "We'll email you about important changes to OpenDLP and to these documents."
BETA_DISCLAIMER = (
    "Registration for OpenDLP is currently only open for beta testing. Please contact us if you intend to use it in "
    "actual democratic lottery processes and/or with actual personal datasets."
)


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
    admin_logged_in_page.goto(Urls.backoffice_dashboard)


@given("there is an assembly created", target_fixture="assembly")
def _(assembly_creator: Callable):
    """there is an assembly created."""
    return assembly_creator("To be or not to be?", number_to_select=22)


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
    page.fill('input[name="first_name"]', "New")
    page.fill('input[name="last_name"]', "User")
    page.fill('input[name="email"]', NEWUSER_EMAIL)
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.get_by_role("checkbox", name=AGREEMENT_LABEL).check()


@when("the user uses a valid invite code")
def _(page: Page, user_invite: str):
    """the user uses a valid invite code."""
    page.fill('input[name="invite_code"]', user_invite)
    page.fill('input[name="first_name"]', "New")
    page.fill('input[name="last_name"]', "User")
    page.fill('input[name="email"]', NEWUSER_EMAIL)
    page.fill('input[name="password"]', FRESH_PASSWORD)
    page.fill('input[name="password_confirm"]', FRESH_PASSWORD)
    page.get_by_role("checkbox", name=AGREEMENT_LABEL).check()


@when("the user finishes registration")
def _(page: Page):
    """the user finishes registration."""
    # The registration form also carries Google/Microsoft submit buttons, so
    # target the email button by name rather than the first submit button.
    page.get_by_role("button", name="Create Account with email").click()


@when("the user signs out")
def _(page: Page):
    """the user signs out, from the account menu."""
    page.get_by_role("button", name="Test Admin").click()
    page.get_by_role("link", name="Sign out").click()


@when("the user agrees to the terms and the data agreement")
def _(page: Page):
    """the user ticks the one box that agrees to both documents."""
    checkbox = page.get_by_role("checkbox", name=AGREEMENT_LABEL)
    if not checkbox.is_checked():
        checkbox.check()


@when("the user does not agree to the terms and the data agreement")
def _(page: Page):
    """the user leaves the box that agrees to both documents unticked."""
    checkbox = page.get_by_role("checkbox", name=AGREEMENT_LABEL)
    if checkbox.is_checked():
        checkbox.uncheck()


@then("the user should see who to contact for an invite code")
def _(page: Page):
    """the invite code field's helper text names who to ask, and links to them."""
    invite_code = page.get_by_role("textbox", name="Invite Code")
    expect(invite_code).to_have_accessible_description("If you don't have one, please contact OpenDLP support.")
    support = page.get_by_role("link", name="OpenDLP support")
    expect(support).to_have_attribute("href", re.compile(r"^mailto:[^@\s]+@[^@\s]+$"))


@then("the user should see what their password must be")
def _(page: Page):
    """the password field is described by the short list of rules under it."""
    password = page.locator('input[name="password"]')
    expect(password).to_have_accessible_description(
        re.compile(
            r"^Your password must:\s*10–256 characters\s*Not be numbers only\s*"
            r"Not be a commonly used password\s*Not be too similar to your personal information$"
        )
    )


@then("the user should see the beta disclaimer")
def _(page: Page):
    """the disclaimer is text under its own heading, links to support, and leaves nothing to tick."""
    expect(page.get_by_role("heading", name="Beta disclaimer", level=2)).to_be_visible()
    expect(page.get_by_text(BETA_DISCLAIMER)).to_be_visible()
    contact = page.get_by_role("link", name="contact us")
    expect(contact).to_have_attribute("href", re.compile(r"^mailto:[^@\s]+@[^@\s]+$"))
    # The agreement's tickbox is the only one
    tickboxes = page.get_by_role("checkbox")
    expect(tickboxes).to_have_count(1)
    expect(tickboxes).to_have_accessible_name(re.compile(rf"^{AGREEMENT_LABEL}"))


@then("the user should be asked to agree to the terms and the data agreement")
def _(page: Page):
    """one tickbox for both documents, a link to each, and the notice about emails read out with it."""
    expect(page.get_by_role("group", name="Terms and data agreement")).to_be_visible()
    tickbox = page.get_by_role("checkbox", name=AGREEMENT_LABEL)
    expect(tickbox).not_to_be_checked()
    expect(tickbox).to_have_accessible_description(EMAILS_SENTENCE)
    for name in ("View terms and conditions", "View data agreement"):
        link = page.get_by_role("link", name=name)
        expect(link).to_have_attribute("href", re.compile(r"^https://"))
        expect(link).to_have_attribute("target", "_blank")


@then("the user should be told to agree to the terms and the data agreement")
def _(page: Page):
    """the form comes back with the reason under the tickbox."""
    tickbox = page.get_by_role("checkbox", name=AGREEMENT_LABEL)
    expect(tickbox).to_have_attribute("aria-invalid", "true")
    expect(tickbox).to_have_accessible_description(
        f"{EMAILS_SENTENCE} You must accept the terms and the data agreement to register"
    )


@then("the user's agreement to the terms and the data agreement should be recorded")
def _(test_database: sessionmaker):
    """the new account carries the time and the version of each document."""
    with SqlAlchemyUnitOfWork(test_database) as uow:
        user = uow.users.get_by_email(NEWUSER_EMAIL)
        assert user is not None
        assert user.terms_agreed_at is not None
        assert user.terms_version == get_terms_version()
        assert user.user_data_agreement_agreed_at is not None
        assert user.user_data_agreement_version == get_data_agreement_version()


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
    # Check user exists in database
    uow = SqlAlchemyUnitOfWork(test_database)
    with uow:
        user = uow.users.get_by_email(NEWUSER_EMAIL)
        assert user is not None

        # With email confirmation, password users aren't auto-logged in
        # They need to confirm their email first
        # For backward compatibility with existing tests, auto-confirm and login
        if not user.is_email_confirmed():
            user.confirm_email()
            uow.commit()

    # If user was redirected to login (password registration), log them in
    if page.url != Urls.backoffice_dashboard:
        page.goto(Urls.login)
        page.fill('input[name="email"]', NEWUSER_EMAIL)
        page.fill('input[name="password"]', FRESH_PASSWORD)
        page.click('button[type="submit"]')

    # Now user should be on dashboard
    # The header link says "Your projects" too, so wait for the heading.
    expect(page.get_by_role("heading", name="Your projects", exact=True)).to_be_visible()


@then("the user should see the default view for an authorised user")
def _(page: Page):
    """the user should see the default view for an authorised user."""
    expect(page).to_have_url(Urls.backoffice_dashboard)


@then("the user should be told they are signed out on the sign in page")
def _(page: Page):
    """the user should be told they are signed out on the sign in page."""
    expect(page).to_have_url(Urls.login)
    expect(page.get_by_text("You have been signed out")).to_be_visible()
