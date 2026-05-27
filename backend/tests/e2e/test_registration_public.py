"""ABOUTME: E2E tests for public registration page routes
ABOUTME: Tests the full submission flow from rendering form to creating respondent"""

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.value_objects import RespondentStatus
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

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
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id)

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


class TestRegistrationFormRendering:
    """Test GET /register/<url_slug> route."""

    def test_renders_published_form(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(f"/register/{published_registration_page.url_slug}")
        assert response.status_code == 200
        assert b"govuk-button" in response.data
        assert b"name" in response.data

    def test_renders_test_mode_form_with_banner(
        self, client: FlaskClient, test_mode_registration_page: RegistrationPage
    ) -> None:
        response = client.get(f"/register/{test_mode_registration_page.url_slug}")
        assert response.status_code == 200
        assert b"Test Mode" in response.data

    def test_returns_404_for_nonexistent_slug(self, client: FlaskClient) -> None:
        response = client.get("/register/nonexistent-slug-12345")
        assert response.status_code == 404

    def test_closed_page_redirects(
        self, client: FlaskClient, published_registration_page: RegistrationPage, postgres_session_factory, admin_user
    ) -> None:
        # Close the registration page
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            close_registration_page(uow, admin_user.id, published_registration_page.assembly_id)

        response = client.get(f"/register/{published_registration_page.url_slug}")
        assert response.status_code == 302
        assert "/registration-closed" in response.location


class TestRegistrationFormSubmission:
    """Test POST /register/<url_slug> route."""

    def test_valid_submission_redirects_to_thank_you(
        self, client: FlaskClient, published_registration_page: RegistrationPage
    ) -> None:
        # Get CSRF token from the form page
        form_url = f"/register/{published_registration_page.url_slug}"
        csrf_token = get_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Test User",
                "email": "test@example.com",
            },
        )
        assert response.status_code == 302
        assert f"/register/{published_registration_page.url_slug}/thank-you" in response.location

    def test_submission_creates_respondent_with_pool_status(
        self, client: FlaskClient, published_registration_page: RegistrationPage, postgres_session_factory
    ) -> None:
        # Count existing respondents
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        # Get CSRF token and submit
        form_url = f"/register/{published_registration_page.url_slug}"
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
        form_url = f"/register/{test_mode_registration_page.url_slug}"
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


class TestThankYouPage:
    """Test GET /register/<url_slug>/thank-you route."""

    def test_renders_thank_you_page(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(f"/register/{published_registration_page.url_slug}/thank-you")
        assert response.status_code == 200
        # The page uses DEFAULT_THANK_YOU_HTML from the domain
        assert b"Thank you for registering" in response.data

    def test_returns_404_for_nonexistent_slug(self, client: FlaskClient) -> None:
        response = client.get("/register/nonexistent-slug-12345/thank-you")
        assert response.status_code == 404


class TestShortUrlRedirect:
    """Test GET /r/<short_url_slug> route."""

    def test_redirects_to_full_url(self, client: FlaskClient, published_registration_page: RegistrationPage) -> None:
        response = client.get(f"/r/{published_registration_page.short_url_slug}")
        assert response.status_code == 302
        assert f"/register/{published_registration_page.url_slug}" in response.location

    def test_returns_404_for_nonexistent_short_slug(self, client: FlaskClient) -> None:
        response = client.get("/r/999999")
        assert response.status_code == 404


class TestRegistrationClosedPage:
    """Test GET /registration-closed route."""

    def test_renders_closed_page(self, client: FlaskClient) -> None:
        response = client.get("/registration-closed")
        assert response.status_code == 200
        assert b"Registration Closed" in response.data
