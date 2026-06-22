# ABOUTME: Component tests for public registration page routes over a FakeUnitOfWork
# ABOUTME: Drives the real public Flask routes + services against seeded fake-store pages

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.entrypoints.blueprints.registration import (
    registration_url,
    registration_url_prefix,
    short_url,
    short_url_prefix,
)
from opendlp.entrypoints.flask_app import create_app
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
    update_thank_you_html,
)
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork

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
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FF_"):
            monkeypatch.delenv(key, raising=False)
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
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_with_feature_disabled(fake_store):
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store)).test_client()


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


def _seed_published_page(fake_store, admin_user: User, title: str = "Test Registration Assembly") -> RegistrationPage:
    assembly_id = _make_assembly(fake_store, admin_user, title)
    with FakeUnitOfWork(store=fake_store) as uow:
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)
    with FakeUnitOfWork(store=fake_store) as uow:
        return publish_registration_page(uow, admin_user.id, assembly_id)


def _seed_test_mode_page(fake_store, admin_user: User, title: str = "Test Mode Assembly") -> RegistrationPage:
    assembly_id = _make_assembly(fake_store, admin_user, title)
    with FakeUnitOfWork(store=fake_store) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.registration_pages.get(page.id).create_detached_copy()


class TestFeatureFlagBehavior:
    def test_show_form_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/register/test-slug")
        assert response.status_code == 404

    def test_submit_form_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.post("/register/test-slug", data={})
        assert response.status_code == 404

    def test_thank_you_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/register/test-slug/thank-you")
        assert response.status_code == 404

    def test_short_url_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/r/abc123")
        assert response.status_code == 404

    def test_closed_page_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/registration-closed")
        assert response.status_code == 404


class TestBlueprintRegistration:
    def test_registration_blueprint_registered(self, app) -> None:
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "registration" in blueprint_names


class TestShowRegistrationForm:
    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        response = client.get("/register/nonexistent")
        assert response.status_code == 404

    def test_redirects_to_closed_page_when_closed(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            close_registration_page(uow, admin_user.id, page.assembly_id)

        response = client.get(f"/register/{page.url_slug}")
        assert response.status_code == 302
        assert "/registration-closed" in response.location

    def test_renders_form_when_live(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}")
        assert response.status_code == 200
        assert b"govuk-button" in response.data
        assert b"name" in response.data

    def test_renders_test_banner_when_test_mode(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_test_mode_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}")
        assert response.status_code == 200
        assert b"Test Mode" in response.data


class TestSubmitRegistrationForm:
    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        response = client.post("/register/nonexistent", data={})
        assert response.status_code == 404

    def test_redirects_to_closed_when_closed(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            close_registration_page(uow, admin_user.id, page.assembly_id)

        response = client.post(f"/register/{page.url_slug}", data={})
        assert response.status_code == 302
        assert "/registration-closed" in response.location

    def test_redirects_to_thank_you_on_valid_submission(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            initial_count = uow.respondents.count_by_assembly_id(page.assembly_id)

        response = client.post(
            f"/register/{page.url_slug}",
            data={"name": "Test User", "email": "test@example.com"},
        )
        assert response.status_code == 302
        assert f"/register/{page.url_slug}/thank-you" in response.location

        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(page.assembly_id, status=RespondentStatus.POOL)
            assert len(respondents) == initial_count + 1

    def test_re_renders_form_with_errors_on_invalid_submission(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        assembly_id = _make_assembly(fake_store, admin_user, "Required Field Assembly")
        with FakeUnitOfWork(store=fake_store) as uow:
            create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
            uow.respondent_field_definitions.bulk_add([
                RespondentFieldDefinition(
                    assembly_id=assembly_id,
                    field_key="email",
                    label="Email",
                    group=RespondentFieldGroup.NAME_AND_CONTACT,
                    sort_order=0,
                    field_type=FieldType.EMAIL,
                    on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
                )
            ])
            uow.commit()
        with FakeUnitOfWork(store=fake_store) as uow:
            update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)
        with FakeUnitOfWork(store=fake_store) as uow:
            page = publish_registration_page(uow, admin_user.id, assembly_id)

        response = client.post(f"/register/{page.url_slug}", data={"name": "Test User"})
        assert response.status_code == 200
        assert b'value="Test User"' in response.data

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.count_by_assembly_id(page.assembly_id) == 0


class TestThankYouPage:
    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        response = client.get("/register/nonexistent/thank-you")
        assert response.status_code == 404

    def test_renders_default_thank_you_when_no_custom_html(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.assembly_id, "")

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"Thank you for registering" in response.data

    def test_renders_custom_thank_you_when_provided(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.assembly_id, "<h1>Custom Thank You</h1>")

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"Custom Thank You" in response.data


class TestShortUrlRedirect:
    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        response = client.get("/r/nonexistent")
        assert response.status_code == 404

    def test_returns_404_when_page_has_no_url_slug(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        assembly_id = _make_assembly(fake_store, admin_user, "No Slug Assembly")
        page = RegistrationPage(
            assembly_id=assembly_id,
            url_slug="",
            short_url_slug="123456",
            status=RegistrationPageStatus.TEST,
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.add(page)
            uow.commit()

        response = client.get("/r/123456")
        assert response.status_code == 404

    def test_redirects_to_canonical_url_with_302(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/r/{page.short_url_slug}")
        assert response.status_code == 302
        assert f"/register/{page.url_slug}" in response.location


class TestRegistrationClosed:
    def test_renders_closed_page(self, client: FlaskClient) -> None:
        response = client.get("/registration-closed")
        assert response.status_code == 200
        assert b"Registration Closed" in response.data


class TestUrlHelpers:
    def test_registration_url_matches_route(self, app) -> None:
        with app.test_request_context("http://example.org/"):
            assert registration_url("my-slug") == "http://example.org/register/my-slug"
            assert short_url("ma26") == "http://example.org/r/ma26"

    def test_prefixes_are_urls_without_a_slug(self, app) -> None:
        with app.test_request_context("http://example.org/"):
            assert registration_url_prefix() == "http://example.org/register/"
            assert short_url_prefix() == "http://example.org/r/"
