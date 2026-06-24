"""ABOUTME: E2E smoke tests for bot protection on the public registration page
ABOUTME: Verifies honeypot and normal submission behaviour against real DB and Redis"""

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

# Minimal valid form HTML — no honeypot or timing fields needed in the author
# HTML because {{ csrf_form_element }} injects them automatically.
MINIMAL_FORM_HTML = """
<form method="post" action="{{ form_action }}">
    {{ csrf_form_element }}
    {{ form_errors() }}
    <div class="govuk-form-group">
        <label class="govuk-label" for="name">Name</label>
        <input class="govuk-input" id="name" name="name" type="text" value="{{ value('name') }}">
    </div>
    <div class="govuk-form-group">
        <label class="govuk-label" for="email">Email</label>
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
    """Create a published registration page for bot-protection smoke tests."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Bot Protection Test Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = publish_registration_page(uow, admin_user.id, assembly_id)
        return page


class TestBotProtectionSmoke:
    """Smoke tests that verify bot protection with a real database and real Redis.

    The timing-token check is gated on REGISTRATION_TIMING_CHECK_ENABLED, which
    is False in the test config, so these tests do not need to supply timing
    tokens — they cover the honeypot path and the happy path only.
    """

    def test_normal_submission_succeeds_with_real_redis(
        self,
        client: FlaskClient,
        published_registration_page: RegistrationPage,
        postgres_session_factory,
    ) -> None:
        """A valid submission should redirect to thank-you and persist a POOL respondent."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        form_url = route_url(
            client, "registration.show_registration_form", url_slug=published_registration_page.url_slug
        )
        csrf_token = get_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Normal Bot User",
                "email": "normal@example.com",
            },
        )

        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(
                published_registration_page.assembly_id, status=RespondentStatus.POOL
            )
            assert len(respondents) == initial_count + 1

    def test_honeypot_submission_redirects_to_thank_you_without_saving(
        self,
        client: FlaskClient,
        published_registration_page: RegistrationPage,
        postgres_session_factory,
    ) -> None:
        """A submission with the honeypot field filled should redirect to thank-you
        but must NOT persist a respondent — the bot is silently rejected."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            initial_count = uow.respondents.count_by_assembly_id(published_registration_page.assembly_id)

        form_url = route_url(
            client, "registration.show_registration_form", url_slug=published_registration_page.url_slug
        )
        csrf_token = get_csrf_token(client, form_url)

        response = client.post(
            form_url,
            data={
                "csrf_token": csrf_token,
                "name": "Bot User",
                "email": "bot@example.com",
                # Honeypot field — a real user leaves this blank; bots fill it in
                "_opendlp_ttoken_": "i-am-a-bot",
            },
        )

        # Still redirects to thank-you so bots don't learn they were blocked
        assert response.status_code == 302

        # No respondent should have been saved
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondents.count_by_assembly_id(published_registration_page.assembly_id) == initial_count
