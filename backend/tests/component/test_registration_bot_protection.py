# ABOUTME: Component tests for bot protection in the public registration routes
# ABOUTME: Tests honeypot, rate limiting, and noindex header behaviours
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.registration_page_service import (
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork

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
def _enable_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()
    yield
    reload_flags()


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin_user(fake_store):
    with FakeUnitOfWork(store=fake_store) as uow:
        admin, _ = create_user(
            uow=uow,
            email="admin@example.com",
            password="adminpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="Admin",
            global_role=GlobalRole.ADMIN,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user = uow.users.get(admin.id)
        user.confirm_email()
        uow.commit()
        return user.create_detached_copy()


@pytest.fixture
def app(fake_store, monkeypatch: pytest.MonkeyPatch):
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def client(app):
    return app.test_client()


def _make_assembly(fake_store, admin_user: User, title: str) -> uuid.UUID:
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title=title,
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        return assembly.id


def _seed_published_page(fake_store, admin_user: User, title: str = "Test Assembly") -> RegistrationPage:
    assembly_id = _make_assembly(fake_store, admin_user, title)
    with FakeUnitOfWork(store=fake_store) as uow:
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)
    with FakeUnitOfWork(store=fake_store) as uow:
        return publish_registration_page(uow, admin_user.id, assembly_id)


class TestHoneypot:
    def test_honeypot_triggered_redirects_to_thank_you(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """A filled honeypot silently redirects to the thank-you page."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "Bot", "email": "bot@example.com", "_opendlp_ttoken_": "something"},
        )

        assert response.status_code == 302
        assert f"/register/{page.url_slug}/thank-you" in response.location

    def test_honeypot_triggered_does_not_save_respondent(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        """A filled honeypot must not persist any respondent data."""
        page = _seed_published_page(fake_store, admin_user)

        client.post(
            f"/register/{page.url_slug}",
            data={"name": "Bot", "email": "bot@example.com", "_opendlp_ttoken_": "filled"},
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.count_by_assembly_id(page.assembly_id) == 0

    def test_empty_honeypot_allows_submission(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """A submission without a honeypot value proceeds normally."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "Real Person", "email": "real@example.com"},
        )

        assert response.status_code == 302
        assert f"/register/{page.url_slug}/thank-you" in response.location


class TestRateLimit:
    def test_ip_rate_limit_rerenders_form_with_error(
        self, client: FlaskClient, fake_store, admin_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When IP rate limit is exceeded the form is re-rendered with an error."""
        page = _seed_published_page(fake_store, admin_user)

        def _raise(*args, **kwargs):
            raise RateLimitExceeded()

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.registration.check_registration_rate_limit",
            _raise,
        )

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "User", "email": "user@example.com"},
        )

        assert response.status_code == 200
        assert b"Too many registrations" in response.data

    def test_email_rate_limit_rerenders_form_with_error(
        self, client: FlaskClient, fake_store, admin_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When email rate limit is exceeded the form is re-rendered with an error."""
        page = _seed_published_page(fake_store, admin_user)

        def _raise(*args, **kwargs):
            raise RateLimitExceeded()

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.registration.check_registration_rate_limit",
            _raise,
        )

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "User", "email": "heavy@example.com"},
        )

        assert response.status_code == 200
        assert b"Too many registrations" in response.data

    def test_rate_limit_does_not_save_respondent(
        self, client: FlaskClient, fake_store, admin_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rate-limited submission must not persist any respondent data."""
        page = _seed_published_page(fake_store, admin_user)

        def _raise(*args, **kwargs):
            raise RateLimitExceeded()

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.registration.check_registration_rate_limit",
            _raise,
        )

        client.post(
            f"/register/{page.url_slug}",
            data={"name": "User", "email": "user@example.com"},
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.count_by_assembly_id(page.assembly_id) == 0

    def test_submission_is_recorded_on_success(
        self, client: FlaskClient, fake_store, admin_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """record_registration_submission is called on a successful POST."""
        page = _seed_published_page(fake_store, admin_user)

        recorded_calls: list[tuple] = []

        def _record(*args, **kwargs):
            recorded_calls.append((args, kwargs))

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.registration.record_registration_submission",
            _record,
        )

        client.post(
            f"/register/{page.url_slug}",
            data={"name": "User", "email": "user@example.com"},
        )

        assert len(recorded_calls) == 1


class TestNoindexHeader:
    def test_get_form_has_noindex_header(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """GET /register/<slug> includes X-Robots-Tag: noindex."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}")

        assert response.headers.get("X-Robots-Tag") == "noindex"

    def test_post_form_has_noindex_header(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """POST /register/<slug> includes X-Robots-Tag: noindex."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "User", "email": "user@example.com"},
        )

        assert response.headers.get("X-Robots-Tag") == "noindex"

    def test_thank_you_has_noindex_header(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """GET /register/<slug>/thank-you includes X-Robots-Tag: noindex."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}/thank-you")

        assert response.headers.get("X-Robots-Tag") == "noindex"

    def test_short_url_redirect_has_noindex_header(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        """GET /r/<short_slug> includes X-Robots-Tag: noindex."""
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/r/{page.short_url_slug}")

        assert response.headers.get("X-Robots-Tag") == "noindex"

    def test_closed_page_has_noindex_header(self, client: FlaskClient) -> None:
        """GET /registration-closed includes X-Robots-Tag: noindex."""
        response = client.get("/registration-closed")

        assert response.headers.get("X-Robots-Tag") == "noindex"
