"""ABOUTME: BDD tests for backoffice UI (Pines UI + Tailwind CSS)
ABOUTME: Tests the separate design system used for admin interfaces"""

import re

import pytest
from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import grant_user_assembly_role

from .config import ADMIN_PASSWORD, NORMAL_PASSWORD, Urls

# Load all scenarios from the feature file
scenarios("../../features/backoffice.feature")


# Store assembly data between steps
class TestAssemblyCache:
    """Cache of assembly title to (string of) UUID"""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def clear(self) -> None:
        self._cache.clear()

    def get(self, title: str) -> str | None:
        return self._cache.get(title)

    def add_existing(self, title: str, assembly: str | Assembly) -> None:
        assembly_id = str(assembly.id) if isinstance(assembly, Assembly) else assembly
        self._cache[title] = assembly_id

    def find_title(self, title: str, session_factory) -> str:
        """
        Find the title in the assemblies that have already been created and add to the cache.

        Return the ID if the title is now in the cache, or empty string if not.
        """
        if title in self._cache:
            return self._cache[title]
        uow = SqlAlchemyUnitOfWork(session_factory)
        with uow:
            assemblies = list(uow.assemblies.all())
            for assembly in assemblies:
                if assembly.title == title:
                    self._cache[title] = str(assembly.id)
                    return self._cache[title]
        return ""


_test_assemblies = TestAssemblyCache()
# _test_assemblies: dict[str, str] = {}


# Override context fixture for backoffice tests - no Celery needed for static pages
# Uses the shared session-scoped browser from conftest.py to avoid sync_playwright conflicts
@pytest.fixture(scope="module")
def backoffice_context(browser, test_server):
    """Browser context without Celery dependency."""
    context = browser.new_context()
    context.set_default_navigation_timeout(5000)
    context.set_default_timeout(5000)
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(backoffice_context):
    """Override page fixture to use backoffice_context (no Celery)."""
    page = backoffice_context.new_page()
    yield page
    page.close()


# Showcase Page Tests


@given("I am on the backoffice showcase page")
def visit_backoffice_showcase(page: Page):
    """Navigate to the backoffice showcase page."""
    page.goto(Urls.backoffice_showcase)


@given('I select the "Foundations" tab')
def _(page: Page):
    """I select the "Foundations" tab."""
    page.locator("button", has_text="Foundations").click()


@then('I should see "Design System"')
def see_design_system_text(page: Page):
    """Verify the Design System heading is visible."""
    heading = page.locator("h1")
    expect(heading).to_contain_text("Design System")


@then('I should see "Alpine.js Interactivity"')
def see_alpine_interactivity_text(page: Page):
    """Verify the Alpine.js section heading is visible."""
    expect(page.locator("body")).to_contain_text("Alpine.js Interactivity")


@then('I should see "Primitive Tokens"')
def see_primitive_tokens_text(page: Page):
    """Verify the Primitive Tokens section heading is visible."""
    expect(page.locator("body")).to_contain_text("Primitive Tokens")


# Design Token Tests


@when(parsers.parse('I click the "{tab_name}" showcase tab'))
def click_showcase_tab(page: Page, tab_name: str):
    """Click a tab in the showcase page tab navigation."""
    tab_button = page.locator("button", has_text=tab_name)
    tab_button.click()
    page.wait_for_timeout(100)  # Allow Alpine.js to update


@then("I should see the brand-400 primary action token box")
def see_brand_400_token_box(page: Page):
    """Verify the brand-400 primary action token box is visible."""
    token_box = page.locator("#token-brand-400")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("brand-400")


@then("the brand-400 token box should have the brand crimson background")
def brand_400_token_has_crimson_background(page: Page):
    """Verify design token --color-brand-400 (#90003F) is applied."""
    token_box = page.locator("#token-brand-400")
    # Brand-400 #90003F = rgb(144, 0, 63)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(144, 0, 63)", f"Expected brand crimson, got {background_color}"


@then("I should see the brand-300 secondary token box")
def see_brand_300_token_box(page: Page):
    """Verify the brand-300 secondary token box is visible."""
    token_box = page.locator("#token-brand-300")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("brand-300")


@then("the brand-300 token box should have the brand red background")
def brand_300_token_has_red_background(page: Page):
    """Verify design token --color-brand-300 (#C70039) is applied."""
    token_box = page.locator("#token-brand-300")
    # Brand-300 #C70039 = rgb(199, 0, 57)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(199, 0, 57)", f"Expected brand red, got {background_color}"


# Alpine.js Tests


@then("the Alpine message should be hidden")
def alpine_message_hidden(page: Page):
    """Verify the Alpine.js toggle message is hidden."""
    message = page.locator("#alpine-message")
    # Wait for Alpine.js to initialize and hide the element
    expect(message).to_be_hidden(timeout=10000)


@then("the Alpine message should be visible")
def alpine_message_visible(page: Page):
    """Verify the Alpine.js toggle message is visible."""
    message = page.locator("#alpine-message")
    expect(message).to_be_visible()


@when("I click the Alpine toggle button")
def click_alpine_toggle(page: Page):
    """Click the Alpine.js toggle button."""
    button = page.locator("#alpine-toggle")
    button.click()


@then('I should see "Alpine.js is working!"')
def see_alpine_working_text(page: Page):
    """Verify the Alpine.js confirmation message is visible."""
    expect(page.locator("body")).to_contain_text("Alpine.js is working!")


# Button Component Tests (Iteration 5)


@then("I should see the primary button")
def see_primary_button(page: Page):
    """Verify the primary button is visible."""
    button = page.locator("#btn-primary")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Submit")


@then("I should see the secondary button")
def see_secondary_button(page: Page):
    """Verify the secondary button is visible."""
    button = page.locator("#btn-secondary")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Secondary")


@then("I should see the outline button")
def see_outline_button(page: Page):
    """Verify the outline button is visible."""
    button = page.locator("#btn-outline")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Cancel")


@then("I should see the disabled button")
def see_disabled_button(page: Page):
    """Verify the disabled button is visible."""
    button = page.locator("#btn-disabled")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Disabled")


@then("the primary button should have the brand crimson background")
def primary_button_has_crimson_background(page: Page):
    """Verify primary button uses --color-primary-action (brand-400 #90003F)."""
    button = page.locator("#btn-primary")
    # Brand-400 #90003F = rgb(144, 0, 63)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(144, 0, 63)", f"Expected brand crimson, got {background_color}"


@then("the secondary button should have the brand red background")
def secondary_button_has_red_background(page: Page):
    """Verify secondary button uses --color-buttons-secondary (brand-300 #C70039)."""
    button = page.locator("#btn-secondary")
    # Brand-300 #C70039 = rgb(199, 0, 57)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(199, 0, 57)", f"Expected brand red, got {background_color}"


@then("the disabled button should be disabled")
def disabled_button_is_disabled(page: Page):
    """Verify the disabled button has the disabled attribute."""
    button = page.locator("#btn-disabled")
    expect(button).to_be_disabled()


# Card Component Tests (Iteration 6)


@then("I should see the basic card")
def see_basic_card(page: Page):
    """Verify the basic card is visible."""
    card = page.locator("#card-basic")
    expect(card).to_be_visible()


@then("I should see the card with header")
def see_card_with_header(page: Page):
    """Verify the card with header is visible."""
    card = page.locator("#card-header")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Card with Header")


@then("I should see the card with actions")
def see_card_with_actions(page: Page):
    """Verify the card with actions is visible."""
    card = page.locator("#card-actions")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Card with Actions")


@then("the card with actions should contain buttons")
def card_with_actions_has_buttons(page: Page):
    """Verify the card with actions contains Save and Cancel buttons."""
    card = page.locator("#card-actions")
    expect(card.locator("button", has_text="Save")).to_be_visible()
    expect(card.locator("button", has_text="Cancel")).to_be_visible()


# Navigation Component Tests


@then("I should see the navigation component")
def see_navigation_component(page: Page):
    """Verify the navigation component section is visible."""
    # The navigation is inside a showcase section with a wrapper div
    navigation = page.locator("section:has-text('Navigation Component')")
    expect(navigation).to_be_visible()


@then("the navigation should contain the logo")
def navigation_has_logo(page: Page):
    """Verify the navigation contains the Sortition logo SVG."""
    # The logo is an SVG inside the navigation demo section
    nav_section = page.locator("section:has-text('Navigation Component')")
    logo = nav_section.locator("svg").first
    expect(logo).to_be_visible()


@then("the navigation should contain nav links")
def navigation_has_nav_links(page: Page):
    """Verify the navigation contains nav links (Dashboard, Assemblies, etc.)."""
    nav_section = page.locator("section:has-text('Navigation Component')")
    # Check for at least one nav link from the showcase example
    expect(nav_section.locator("a", has_text="Dashboard")).to_be_visible()
    expect(nav_section.locator("a", has_text="Assemblies")).to_be_visible()


@then("the navigation should contain the CTA button")
def navigation_has_cta_button(page: Page):
    """Verify the navigation contains the CTA button (Sign out)."""
    nav_section = page.locator("section:has-text('Navigation Component')")
    cta = nav_section.locator("a", has_text="Sign out")
    expect(cta).to_be_visible()


# Button Link Variant Tests


@then("I should see the link button")
def see_link_button(page: Page):
    """Verify the link button is visible."""
    button = page.locator("#btn-link")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Link Button")


@then("the link button should be an anchor tag")
def link_button_is_anchor(page: Page):
    """Verify the link button renders as an <a> tag, not <button>."""
    link_button = page.locator("#btn-link")
    tag_name = link_button.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "a", f"Expected <a> tag for link button, got <{tag_name}>"


# Typography Tests


@then("I should see the typography section")
def see_typography_section(page: Page):
    """Verify the Typography section heading is visible."""
    expect(page.locator("body")).to_contain_text("Typography")


@then('I should see "Semantic Tokens"')
def see_semantic_tokens_text(page: Page):
    """Verify the Semantic Tokens sub-heading is visible."""
    expect(page.locator("body")).to_contain_text("Semantic Tokens")


@then('I should see "Use Cases"')
def see_use_cases_text(page: Page):
    """Verify the Use Cases sub-heading is visible."""
    expect(page.locator("body")).to_contain_text("Use Cases")


@then(parsers.parse("the {token} sample should use the Oswald font"))
def sample_uses_oswald_font(page: Page, token: str):
    """Verify a typography sample uses the Oswald font family."""
    # Wait for web fonts to load before checking
    page.evaluate("() => document.fonts.ready")
    element = page.locator(f"#typo-{token}")
    font_family = element.evaluate("el => getComputedStyle(el).fontFamily")
    assert "Oswald" in font_family, f"Expected Oswald font for {token}, got {font_family}"


@then(parsers.parse("the {token} sample should use the Lato font"))
def sample_uses_lato_font(page: Page, token: str):
    """Verify a typography sample uses the Lato font family."""
    # Wait for web fonts to load before checking
    page.evaluate("() => document.fonts.ready")
    element = page.locator(f"#typo-{token}")
    font_family = element.evaluate("el => getComputedStyle(el).fontFamily")
    assert "Lato" in font_family, f"Expected Lato font for {token}, got {font_family}"


@then(parsers.parse("the {token} sample should have font size {size}"))
def sample_has_font_size(page: Page, token: str, size: str):
    """Verify a typography sample has the expected computed font size."""
    element = page.locator(f"#typo-{token}")
    font_size = element.evaluate("el => getComputedStyle(el).fontSize")
    assert font_size == size, f"Expected font size {size} for {token}, got {font_size}"


@then("the overline sample should be uppercase")
def overline_is_uppercase(page: Page):
    """Verify the overline sample has text-transform: uppercase."""
    element = page.locator("#typo-overline")
    text_transform = element.evaluate("el => getComputedStyle(el).textTransform")
    assert text_transform == "uppercase", f"Expected uppercase, got {text_transform}"


# Dashboard Tests (Protected Route)


def _login_admin(page: Page, admin_user) -> None:
    """Helper to log in as admin user."""
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', admin_user.email)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)


@given("I am not logged in")
def not_logged_in(page: Page):
    """Ensure user is not logged in by clearing cookies."""
    page.context.clear_cookies()


@given("I am logged in as an admin user")
def logged_in_as_admin(page: Page, admin_user):
    """Log in as admin user."""
    _login_admin(page, admin_user)


@given(parsers.parse('there is an assembly called "{title}"'))
def create_test_assembly(title: str, admin_user, test_database):
    """Create a test assembly for the admin user."""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    assembly = create_assembly(
        uow=uow,
        title=title,
        created_by_user_id=admin_user.id,
    )
    _test_assemblies.add_existing(title, assembly)


@when("I try to access the backoffice dashboard")
def try_access_backoffice_dashboard(page: Page):
    """Attempt to access the backoffice dashboard."""
    page.goto(Urls.backoffice_dashboard)


@when("I visit the backoffice dashboard")
def visit_backoffice_dashboard(page: Page):
    """Navigate to the backoffice dashboard."""
    page.goto(Urls.backoffice_dashboard)


@then("I should be redirected to the login page")
def redirected_to_login(page: Page):
    """Verify user was redirected to login page (with optional next parameter)."""
    expect(page).to_have_url(re.compile(r".*/auth/login.*"), timeout=5000)


@then('I should see "Dashboard"')
def see_dashboard_text(page: Page):
    """Verify Dashboard heading is visible."""
    heading = page.locator("h1")
    expect(heading).to_contain_text("Dashboard")


@then('I should see "Welcome back"')
def see_welcome_back_text(page: Page):
    """Verify Welcome back text is visible."""
    expect(page.locator("body")).to_contain_text("Welcome back")


@then(parsers.parse('I should see an assembly card with title "{title}"'))
def see_assembly_card_with_title(page: Page, title: str):
    """Verify an assembly card with the given title is visible."""
    card = page.locator(".assembly-card", has_text=title)
    expect(card).to_be_visible()


# Footer Component Tests


@then("I should see the footer")
def see_footer(page: Page):
    """Verify the footer is visible."""
    footer = page.locator("footer")
    expect(footer).to_be_visible()


@then("the footer should contain GitHub link")
def footer_has_github_link(page: Page):
    """Verify the footer contains a GitHub link."""
    footer = page.locator("footer")
    github_link = footer.locator("a", has_text="GitHub")
    expect(github_link).to_be_visible()
    expect(github_link).to_have_attribute("href", "https://github.com/sortition-foundation/opendlp")
    expect(github_link).to_have_attribute("target", "_blank")


@then("the footer should contain Sortition Foundation link")
def footer_has_sortition_link(page: Page):
    """Verify the footer contains a Sortition Foundation link."""
    footer = page.locator("footer")
    sf_link = footer.locator("a", has_text="Sortition Foundation")
    expect(sf_link).to_be_visible()
    expect(sf_link).to_have_attribute("href", "https://www.sortitionfoundation.org")
    expect(sf_link).to_have_attribute("target", "_blank")


@then("the footer should contain User Data Agreement link")
def footer_has_user_data_agreement_link(page: Page):
    """Verify the footer contains a User Data Agreement link."""
    footer = page.locator("footer")
    uda_link = footer.locator("a", has_text="User Data Agreement")
    expect(uda_link).to_be_visible()
    # The href should contain the user_data_agreement route
    expect(uda_link).to_have_attribute("href", re.compile(r".*/auth/user-data-agreement"))


@then("the footer should display the version")
def footer_has_version(page: Page):
    """Verify the footer displays the OpenDLP version."""
    footer = page.locator("footer")
    # Version text should be visible (format: "Version YYYY-MM-DD hash" or "Version UNKNOWN")
    expect(footer).to_contain_text("Version")


# Assembly Details Page Tests


@given(parsers.parse('there is an assembly called "{title}" with question "{question}"'))
def create_test_assembly_with_question(title: str, question: str, admin_user, test_database):
    """Create a test assembly with a question for the admin user."""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    assembly = create_assembly(
        uow=uow,
        title=title,
        question=question,
        created_by_user_id=admin_user.id,
    )
    _test_assemblies.add_existing(title, assembly)


@when(parsers.parse('I click the "Go to Assembly" button for "{title}"'))
def click_go_to_assembly_button(page: Page, title: str):
    """Click the Go to Assembly button for a specific assembly card."""
    card = page.locator(".assembly-card", has_text=title)
    button = card.locator("a", has_text="Go to Assembly")
    button.click()


@when(parsers.parse('I visit the assembly details page for "{title}"'))
def visit_assembly_details_page(page: Page, title: str, admin_user, test_database):
    """Navigate directly to the assembly details page."""
    # Get the assembly ID from the database if not already stored
    assembly_id = _test_assemblies.find_title(title, test_database)
    if assembly_id:
        page.goto(Urls.backoffice_assembly_url(assembly_id))


@then("I should see the assembly details page")
def see_assembly_details_page(page: Page):
    """Verify we're on the assembly details page."""
    expect(page).to_have_url(re.compile(r".*/backoffice/assembly/.*"))


@then(parsers.parse('I should see "{title}" as the page heading'))
def see_page_heading(page: Page, title: str):
    """Verify the page heading contains the expected title."""
    heading = page.locator("h1")
    expect(heading).to_contain_text(title)


@then("I should see the breadcrumbs")
def see_breadcrumbs(page: Page):
    """Verify the breadcrumbs navigation is visible."""
    breadcrumbs = page.locator("nav[aria-label='Breadcrumb']")
    expect(breadcrumbs).to_be_visible()


@then(parsers.parse('the breadcrumbs should contain "{text}"'))
def breadcrumbs_contain_text(page: Page, text: str):
    """Verify the breadcrumbs contain specific text."""
    breadcrumbs = page.locator("nav[aria-label='Breadcrumb']")
    expect(breadcrumbs).to_contain_text(text)


@then("I should see the assembly question section")
def see_assembly_question_section(page: Page):
    """Verify the assembly question section is visible."""
    section = page.locator("section", has_text="Assembly Question")
    expect(section).to_be_visible()


@then("I should see the assembly details summary")
def see_assembly_details_summary(page: Page):
    """Verify the assembly details summary (dl/dd section) is visible."""
    details_section = page.locator("section", has_text="Details").locator("dl")
    expect(details_section).to_be_visible()


@then(parsers.parse('I should see "{text}"'))
def see_text_on_page(page: Page, text: str):
    """Verify specific text is visible on the page."""
    expect(page.locator("body")).to_contain_text(text)


@then(parsers.parse('I should see the "{button_text}" button'))
def see_button_with_text(page: Page, button_text: str):
    """Verify a button with specific text is visible."""
    button = page.locator("a, button", has_text=button_text)
    expect(button).to_be_visible()


# Edit Assembly Page Tests


@when(parsers.parse('I click the "{button_text}" button'))
def click_button_with_text(page: Page, button_text: str):
    """Click a button with specific text."""
    button = page.locator("a, button", has_text=button_text)
    button.click()
    # Wait for navigation if the button triggers a form submission or link
    page.wait_for_load_state("networkidle")


@when(parsers.parse('I visit the edit assembly page for "{title}"'))
def visit_edit_assembly_page(page: Page, title: str, admin_user, test_database):
    """Navigate directly to the edit assembly page."""
    # Get the assembly ID from the database if not already stored
    assembly_id = _test_assemblies.find_title(title, test_database)
    if assembly_id:
        page.goto(Urls.backoffice_edit_assembly_url(assembly_id))


@then("I should see the edit assembly page")
def see_edit_assembly_page(page: Page):
    """Verify we're on the edit assembly page."""
    expect(page).to_have_url(re.compile(r".*/backoffice/assembly/.*/edit"))


@then("I should see the title input field")
def see_title_input_field(page: Page):
    """Verify the title input field is visible."""
    title_input = page.locator("input[name='title']")
    expect(title_input).to_be_visible()


@then("I should see the question textarea field")
def see_question_textarea_field(page: Page):
    """Verify the question textarea field is visible."""
    question_textarea = page.locator("textarea[name='question']")
    expect(question_textarea).to_be_visible()


@then("I should see the first assembly date field")
def see_first_assembly_date_field(page: Page):
    """Verify the first assembly date field is visible."""
    date_input = page.locator("input[name='first_assembly_date']")
    expect(date_input).to_be_visible()


@then("I should see the number to select field")
def see_number_to_select_field(page: Page):
    """Verify the number to select field is visible."""
    number_input = page.locator("input[name='number_to_select']")
    expect(number_input).to_be_visible()


@then(parsers.parse('the title input should contain "{expected_value}"'))
def title_input_contains_value(page: Page, expected_value: str):
    """Verify the title input contains the expected value."""
    title_input = page.locator("input[name='title']")
    expect(title_input).to_have_value(expected_value)


@then(parsers.parse('the question textarea should contain "{expected_value}"'))
def question_textarea_contains_value(page: Page, expected_value: str):
    """Verify the question textarea contains the expected value."""
    question_textarea = page.locator("textarea[name='question']")
    expect(question_textarea).to_have_value(expected_value)


@when(parsers.parse('I fill in the title with "{new_title}"'))
def fill_in_title(page: Page, new_title: str):
    """Fill in the title input with a new value."""
    title_input = page.locator("input[name='title']")
    title_input.fill(new_title)


# Create Assembly Page Tests


@when("I visit the create assembly page")
def visit_create_assembly_page(page: Page):
    """Navigate to the create assembly page."""
    page.goto(Urls.backoffice_create_assembly)


@then("I should see the create assembly page")
def see_create_assembly_page(page: Page):
    """Verify we're on the create assembly page."""
    expect(page).to_have_url(re.compile(r".*/backoffice/assembly/new"))


@when(parsers.parse('I fill in the question with "{question}"'))
def fill_in_question(page: Page, question: str):
    """Fill in the question textarea with a value."""
    question_textarea = page.locator("textarea[name='question']")
    question_textarea.fill(question)


@when(parsers.parse('I fill in the number to select with "{number}"'))
def fill_in_number_to_select(page: Page, number: str):
    """Fill in the number to select input with a value."""
    number_input = page.locator("input[name='number_to_select']")
    number_input.fill(number)


@given("there are no assemblies")
def ensure_no_assemblies(test_database):
    """Ensure there are no assemblies in the database."""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        # Delete all assemblies
        assemblies = list(uow.assemblies.all())
        for assembly in assemblies:
            uow.session.delete(assembly)
        uow.commit()
    _test_assemblies.clear()


# Assembly Members Page Tests


def _login_normal(page: Page, normal_user) -> None:
    """Helper to log in as normal user."""
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', normal_user.email)
    page.fill('input[name="password"]', NORMAL_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)


@given("I am logged in as a normal user")
def logged_in_as_normal(page: Page, normal_user):
    """Log in as normal user."""
    _login_normal(page, normal_user)


@given(parsers.parse('there is an assembly called "{title}" created by admin'))
def create_test_assembly_by_admin(title: str, admin_user, test_database):
    """Create a test assembly owned by the admin user."""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    assembly = create_assembly(
        uow=uow,
        title=title,
        created_by_user_id=admin_user.id,
    )
    _test_assemblies.add_existing(title, assembly)


@given(parsers.parse('I am assigned to "{title}" as "{role}"'))
def assign_current_user_to_assembly(title: str, role: str, normal_user, admin_user, test_database):
    """Assign the current (normal) user to an assembly with a specific role."""
    assembly_id = _test_assemblies.get(title)
    if not assembly_id:
        raise ValueError(f"Assembly '{title}' not found in test assemblies")

    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    assembly_role = AssemblyRole(role)
    grant_user_assembly_role(
        uow=uow,
        user_id=normal_user.id,
        assembly_id=assembly_id,
        role=assembly_role,
        current_user=admin_user,
    )


@given(parsers.parse('"{email}" is assigned to "{title}" as "{role}"'))
def assign_user_to_assembly(email: str, title: str, role: str, admin_user, normal_user, test_database):
    """Assign a specific user to an assembly with a specific role."""
    assembly_id = _test_assemblies.get(title)
    if not assembly_id:
        raise ValueError(f"Assembly '{title}' not found in test assemblies")

    # Determine which user to assign based on email
    user_to_assign = normal_user if email == normal_user.email else admin_user

    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    assembly_role = AssemblyRole(role)
    grant_user_assembly_role(
        uow=uow,
        user_id=user_to_assign.id,
        assembly_id=assembly_id,
        role=assembly_role,
        current_user=admin_user,
    )


@when(parsers.parse('I click the "{tab_name}" tab'))
def click_tab(page: Page, tab_name: str):
    """Click a tab in the tab navigation."""
    tab = page.locator("nav[aria-label='Assembly sections'] a", has_text=tab_name)
    tab.click()
    page.wait_for_load_state("networkidle")


@when(parsers.parse('I visit the assembly members page for "{title}"'))
def visit_assembly_members_page(page: Page, title: str, test_database):
    """Navigate directly to the assembly members page."""
    assembly_id = _test_assemblies.find_title(title, test_database)
    if assembly_id:
        page.goto(Urls.backoffice_members_assembly_url(assembly_id))


@when(parsers.parse('I type "{text}" into the user search dropdown'))
def type_into_search_dropdown(page: Page, text: str):
    """Type text into the user search dropdown."""
    search_input = page.locator("#user_id_search")
    search_input.fill(text)
    # Wait for debounce and potential API response
    page.wait_for_timeout(500)


@then("I should see the assembly members page")
def see_assembly_members_page(page: Page):
    """Verify we're on the assembly members page."""
    expect(page).to_have_url(re.compile(r".*/backoffice/assembly/.*/members"))


@then(parsers.parse('I should see "{text}" as a section heading'))
def see_section_heading(page: Page, text: str):
    """Verify a section heading with specific text is visible."""
    heading = page.locator("h2", has_text=text)
    expect(heading).to_be_visible()


@then("I should see the user search dropdown")
def see_user_search_dropdown(page: Page):
    """Verify the user search dropdown is visible."""
    search_input = page.locator("#user_id_search")
    expect(search_input).to_be_visible()


@then("I should see the role selection radio buttons")
def see_role_selection_radio_buttons(page: Page):
    """Verify the role selection radio buttons are visible."""
    fieldset = page.locator("fieldset", has_text="Role")
    expect(fieldset).to_be_visible()
    # Check that radio buttons exist
    radios = fieldset.locator("input[type='radio']")
    expect(radios.first).to_be_visible()


@then("I should see the team members table")
def see_team_members_table(page: Page):
    """Verify the team members table is visible."""
    table = page.locator("table")
    expect(table).to_be_visible()


@then(parsers.parse('the team members table should show "{email}"'))
def team_members_table_shows_email(page: Page, email: str):
    """Verify the team members table shows a specific email."""
    table = page.locator("table")
    expect(table).to_contain_text(email)


@then(parsers.parse('the team members table should show role "{role}"'))
def team_members_table_shows_role(page: Page, role: str):
    """Verify the team members table shows a specific role."""
    table = page.locator("table")
    expect(table).to_contain_text(role)


@then("I should see remove buttons in the team members table")
def see_remove_buttons_in_table(page: Page):
    """Verify remove buttons are visible in the team members table."""
    table = page.locator("table")
    remove_button = table.locator("button", has_text="Remove")
    expect(remove_button.first).to_be_visible()


@then("I should not see the user search dropdown")
def not_see_user_search_dropdown(page: Page):
    """Verify the user search dropdown is not visible."""
    search_input = page.locator("#user_id_search")
    expect(search_input).to_be_hidden()


@then("I should not see remove buttons in the team members table")
def not_see_remove_buttons_in_table(page: Page):
    """Verify remove buttons are not visible in the team members table."""
    table = page.locator("table")
    remove_button = table.locator("button", has_text="Remove")
    expect(remove_button).to_have_count(0)


@then(parsers.parse('I should not see "{text}"'))
def not_see_text_on_page(page: Page, text: str):
    """Verify specific text is not visible on the page."""
    expect(page.locator("body")).not_to_contain_text(text)


@then(parsers.parse('I should see "{text}" after searching'))
def see_text_after_searching(page: Page, text: str):
    """Verify specific text is visible after searching."""
    # Wait for search results to load
    page.wait_for_timeout(500)
    expect(page.locator("body")).to_contain_text(text)


@when(parsers.parse('I try to access the assembly details page for "{title}"'))
def try_access_assembly_details_page(page: Page, title: str, test_database):
    """Try to navigate directly to the assembly details page (may be unauthorized)."""
    assembly_id = _test_assemblies.find_title(title, test_database)
    if assembly_id:
        page.goto(Urls.backoffice_assembly_url(assembly_id))
        page.wait_for_load_state("networkidle")


@when(parsers.parse('I try to access the assembly members page for "{title}"'))
def try_access_assembly_members_page(page: Page, title: str, test_database):
    """Try to navigate directly to the assembly members page (may be unauthorized)."""
    assembly_id = _test_assemblies.find_title(title, test_database)
    if assembly_id:
        page.goto(Urls.backoffice_members_assembly_url(assembly_id))
        page.wait_for_load_state("networkidle")


@then("I should be redirected to the dashboard")
def redirected_to_dashboard(page: Page):
    """Verify user was redirected to the backoffice dashboard."""
    expect(page).to_have_url(re.compile(r".*/backoffice/dashboard"))
