"""ABOUTME: E2E tests for public registration page routes
ABOUTME: Tests the full submission flow from rendering form to creating respondent"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.value_objects import RespondentStatus
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import (
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token, route_url

# A minimal valid form HTML that includes the required placeholders
MINIMAL_FORM_HTML = """
<form method="post" action="{{ form_action }}">
    {{ csrf_form_element }}
    {{ form_errors() }}
    <div class="govuk-form-group {% if has_error('name') %}govuk-form-group--error{% endif %}">
        <label class="govuk-label" for="name">Name</label>
        {{ field_errors('name') }}
        <input class="govuk-input" id="name" name="name" type="text" value="{{ value('name') }}">
    </div>
    <div class="govuk-form-group {% if has_error('email') %}govuk-form-group--error{% endif %}">
        <label class="govuk-label" for="email">Email</label>
        {{ field_errors('email') }}
        <input class="govuk-input" id="email" name="email" type="email" value="{{ value('email') }}">
    </div>
    <button type="submit" class="govuk-button">Submit</button>
</form>
"""


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the registration_page feature flag for all tests in this module."""
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


@pytest.fixture
def published_registration_page(postgres_session_factory, admin_user) -> RegistrationPage:
    """Create a published registration page for testing."""
    # Create an assembly first
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Test Registration Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    # Create a registration page with auto-generated slugs
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id)

    # Update the form HTML with a valid form
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)

    # Publish the page
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = publish_registration_page(uow, admin_user.id, assembly_id)
        return page


@pytest.fixture
def test_mode_registration_page(postgres_session_factory, admin_user) -> RegistrationPage:
    """Create a TEST mode registration page for testing."""
    # Create an assembly first
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Test Mode Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    # Create a registration page with auto-generated slugs
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id)

    # Update the form HTML with a valid form
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)

    # Page is in TEST status by default, just return it
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        return uow.registration_pages.get(page.id).create_detached_copy()


# Sentinel emitted when csp_nonce is absent from the render context. It proves
# the probe location actually rendered (rather than the assertion passing because
# the page errored or the markup moved).
NONCE_ABSENT_SENTINEL = "csp-nonce-was-absent"

# Form HTML that tries to smuggle the request CSP nonce into author-controlled
# output. It is valid for publishing (carries both required placeholders) but a
# malicious author has added a <script> whose nonce attribute references
# csp_nonce - if that nonce were available to the sandbox the inline JS would
# satisfy the CSP and execute. The `default` filter keeps the page rendering
# (the sandbox uses StrictUndefined, so a bare {{ csp_nonce }} would raise): it
# yields the sentinel today and the real nonce only if a regression adds
# csp_nonce to the render context.
NONCE_PROBE_FORM_HTML = """
<form method="post" action="{{ form_action }}">
    {{ csrf_form_element }}
    <script nonce="{{ csp_nonce | default('__SENTINEL__') }}">window.__pwned = true;</script>
    <button type="submit" class="govuk-button">Submit</button>
</form>
""".replace("__SENTINEL__", NONCE_ABSENT_SENTINEL)


def _csp_nonce_from_response(response) -> str:
    """Extract the per-request CSP nonce from the response's CSP header."""
    csp = response.headers.get("Content-Security-Policy", "")
    match = re.search(r"'nonce-([^']+)'", csp)
    assert match, f"No CSP nonce found in header: {csp!r}"
    return match.group(1)


@pytest.fixture
def nonce_probe_registration_page(postgres_session_factory, admin_user) -> RegistrationPage:
    """A published page whose form HTML references csp_nonce."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Nonce Probe Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, NONCE_PROBE_FORM_HTML)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        return publish_registration_page(uow, admin_user.id, assembly_id)


class TestCspNonceNotLeakedToAuthorHtml:
    """Author HTML must never receive the request CSP nonce.

    Assembly managers can author form HTML containing Jinja, which we render in
    a sandbox. Our CSP forbids inline JavaScript unless it carries the
    per-request nonce. If author HTML could read that nonce (via
    ``{{ csp_nonce }}``), a malicious manager could whitelist their own inline
    script and defeat the CSP. The page's own framework scripts legitimately
    carry the nonce; this locks in that author-controlled markup never does,
    guarding against a future change that adds ``csp_nonce`` to the render
    context.
    """

    def test_author_script_does_not_receive_request_nonce(
        self, client: FlaskClient, nonce_probe_registration_page: RegistrationPage
    ) -> None:
        response = client.get(
            route_url(client, "registration.show_registration_form", url_slug=nonce_probe_registration_page.url_slug)
        )
        assert response.status_code == 200

        # The real nonce is in the CSP header. It legitimately appears in the
        # page's own framework <script> tags (the outer template gets the nonce),
        # so we check the *author-controlled* script specifically: it must not
        # have been handed the live nonce, or its inline JS would satisfy the CSP.
        nonce = _csp_nonce_from_response(response)
        assert f'nonce="{nonce}">window.__pwned'.encode() not in response.data

        # And it did render - with the empty-context sentinel rather than a
        # nonce - so the assertion above is not vacuously true. A regression that
        # added csp_nonce to the render context would swap the sentinel for the
        # live nonce and fail the check above.
        assert f'nonce="{NONCE_ABSENT_SENTINEL}">window.__pwned'.encode() in response.data


class TestRegistrationFormRendering:
    """Test GET /register/<url_slug> route."""

    def test_renders_published_form(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(
            route_url(client, "registration.show_registration_form", url_slug=published_registration_page.url_slug)
        )
        assert response.status_code == 200
        assert b"govuk-button" in response.data
        assert b"name" in response.data

    def test_public_form_footer_links_to_cookies_page(
        self, client: FlaskClient, published_registration_page: RegistrationPage
    ) -> None:
        """The public form is the one page an anonymous visitor lands on, and the one
        that sets a cookie, so GOV.UK requires a footer link to the cookies page."""
        response = client.get(
            route_url(client, "registration.show_registration_form", url_slug=published_registration_page.url_slug)
        )

        assert b"govuk-footer" in response.data
        assert b"https://docs.sortitionlab.org/data-and-legal/cookies/" in response.data
        assert b"https://docs.sortitionlab.org/data-and-legal/data-agreement/" in response.data


class TestRegistrationFormSubmission:
    """Test POST /register/<url_slug> route."""

    def test_submission_creates_respondent_with_pool_status(
        self, client: FlaskClient, published_registration_page: RegistrationPage, postgres_session_factory
    ) -> None:
        # Count existing respondents
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        # Get CSRF token and submit
        form_url = route_url(
            client, "registration.show_registration_form", url_slug=published_registration_page.url_slug
        )
        csrf_token = get_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Pool Test User",
                "email": "pool@example.com",
            },
        )
        # Verify redirect to thank-you page
        assert response.status_code == 302

        # Check that a new respondent was created with POOL status
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(
                published_registration_page.assembly_id, status=RespondentStatus.POOL
            )
            assert len(respondents) == initial_count + 1

    def test_test_mode_submission_creates_test_respondent(
        self, client: FlaskClient, test_mode_registration_page: RegistrationPage, postgres_session_factory
    ) -> None:
        # Count existing TEST_SUBMISSION respondents
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = len(
                uow.respondents.get_by_assembly_id(
                    test_mode_registration_page.assembly_id, status=RespondentStatus.TEST_SUBMISSION
                )
            )

        # Get CSRF token and submit
        form_url = route_url(
            client, "registration.show_registration_form", url_slug=test_mode_registration_page.url_slug
        )
        csrf_token = get_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Test Mode User",
                "email": "testmode@example.com",
            },
        )
        # Verify redirect to thank-you page
        assert response.status_code == 302

        # Check that a new respondent was created with TEST_SUBMISSION status
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(
                test_mode_registration_page.assembly_id, status=RespondentStatus.TEST_SUBMISSION
            )
            assert len(respondents) == initial_count + 1


class TestRegistrationCsrfExpiry:
    """An expired/invalid CSRF token re-renders the form with the user's values preserved.

    These tests enable CSRF (disabled in the test config) on the function-scoped
    app so the manual validate_csrf check in the submit view is exercised.
    """

    @staticmethod
    def _real_csrf_token(client: FlaskClient, form_url: str) -> str:
        """Extract the real CSRF token rendered into the form."""
        response = client.get(form_url)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        assert match, "No CSRF token found in rendered form"
        return match.group(1).decode()

    def test_expired_token_rerenders_form_with_values(
        self, app, client: FlaskClient, published_registration_page: RegistrationPage, postgres_session_factory
    ) -> None:
        app.config["WTF_CSRF_ENABLED"] = True

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        form_url = route_url(
            client, "registration.show_registration_form", url_slug=published_registration_page.url_slug
        )
        response = client.post(
            form_url,
            data={
                "csrf_token": "stale-or-invalid-token",
                "name": "Jo Public",
                "email": "jo@example.com",
            },
        )

        # Form is re-rendered (200), not the generic 400 error page
        assert response.status_code == 200
        # The friendly expiry message is shown
        assert b"open too long" in response.data
        # The submitted values are preserved so the user doesn't lose their work
        assert b'value="Jo Public"' in response.data
        assert b"jo@example.com" in response.data

        # No respondent was created - the route is still protected
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondents.count_by_assembly_id(published_registration_page.assembly_id) == initial_count

    def test_valid_token_still_creates_respondent(
        self, app, client: FlaskClient, published_registration_page: RegistrationPage, postgres_session_factory
    ) -> None:
        app.config["WTF_CSRF_ENABLED"] = True

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        form_url = route_url(
            client, "registration.show_registration_form", url_slug=published_registration_page.url_slug
        )
        csrf_token = self._real_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Valid User",
                "email": "valid@example.com",
            },
        )

        assert response.status_code == 302
        assert (
            route_url(client, "registration.thank_you", url_slug=published_registration_page.url_slug)
            in response.location
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondents.count_by_assembly_id(published_registration_page.assembly_id) == initial_count + 1


class TestThankYouPage:
    """Test GET /register/<url_slug>/thank-you route."""

    def test_renders_thank_you_page(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(
            route_url(client, "registration.thank_you", url_slug=published_registration_page.url_slug)
        )
        assert response.status_code == 200
        # The page uses DEFAULT_THANK_YOU_HTML from the domain
        assert b"Thank you for registering" in response.data


class TestShortUrlRedirect:
    """Test GET /r/<short_url_slug> route."""

    def test_redirects_to_full_url(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(
            route_url(
                client, "registration.short_url_redirect", short_url_slug=published_registration_page.short_url_slug
            )
        )
        assert response.status_code == 302
        assert (
            route_url(client, "registration.show_registration_form", url_slug=published_registration_page.url_slug)
            in response.location
        )


class TestRegistrationClosedPage:
    """Test GET /registration-closed route."""

    def test_renders_closed_page(self, client: FlaskClient) -> None:
        response = client.get(route_url(client, "registration.registration_closed"))
        assert response.status_code == 200
        assert b"Registration Closed" in response.data
