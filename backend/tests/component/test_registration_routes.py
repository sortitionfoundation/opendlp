# ABOUTME: Component tests for public registration page routes over a FakeUnitOfWork
# ABOUTME: Drives the real public Flask routes + services against seeded fake-store pages

import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.entrypoints.blueprints.registration import (
    is_registration_path,
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
    page_for_assembly,
    publish_registration_page,
    update_registration_page_html,
    update_thank_you_html,
)
from opendlp.service_layer.user_service import create_user
from tests.conftest import install_email_outbox
from tests.fakes import FakeStore, FakeUnitOfWork


def _page_id(uow, assembly_id):  # type: ignore[no-untyped-def]
    """The id of the assembly's single registration page."""
    page = page_for_assembly(uow, assembly_id)
    assert page is not None
    return page.id


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
def app(fake_store, monkeypatch: pytest.MonkeyPatch, email_outbox):
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()
    app = create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))
    install_email_outbox(app, email_outbox)
    return app


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
        create_registration_page_with_slugs(uow, admin_user.id, assembly_id, name="Registration page")
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_user.id, _page_id(uow, assembly_id), MINIMAL_FORM_HTML)
    with FakeUnitOfWork(store=fake_store) as uow:
        return publish_registration_page(uow, admin_user.id, _page_id(uow, assembly_id))


def _seed_test_mode_page(fake_store, admin_user: User, title: str = "Test Mode Assembly") -> RegistrationPage:
    assembly_id = _make_assembly(fake_store, admin_user, title)
    with FakeUnitOfWork(store=fake_store) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id, name="Registration page")
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_user.id, _page_id(uow, assembly_id), MINIMAL_FORM_HTML)
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
            close_registration_page(uow, admin_user.id, page.id)

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
            close_registration_page(uow, admin_user.id, page.id)

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
            create_registration_page_with_slugs(uow, admin_user.id, assembly_id, name="Registration page")
            uow.respondent_field_definitions.bulk_add([
                RespondentFieldDefinition(
                    assembly_id=assembly_id,
                    field_key="email",
                    label="Email",
                    sort_order=0,
                    field_type=FieldType.EMAIL,
                    on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
                )
            ])
            uow.commit()
        with FakeUnitOfWork(store=fake_store) as uow:
            update_registration_page_html(uow, admin_user.id, _page_id(uow, assembly_id), MINIMAL_FORM_HTML)
        with FakeUnitOfWork(store=fake_store) as uow:
            page = publish_registration_page(uow, admin_user.id, _page_id(uow, assembly_id))

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
            update_thank_you_html(uow, admin_user.id, page.id, "")

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"Thank you for registering" in response.data

    def test_renders_custom_thank_you_when_provided(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>")

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"Custom Thank You" in response.data

    def test_standard_page_links_back_to_the_form_without_a_referer(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"start a new registration" in response.data
        assert f'href="http://localhost/register/{page.url_slug}"'.encode() in response.data

    def test_standard_page_ignores_the_referer(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(
            f"/register/{page.url_slug}/thank-you", headers={"Referer": "https://elsewhere.example/page"}
        )
        assert b"elsewhere.example" not in response.data

    def test_standard_page_is_translated(self, app, client: FlaskClient, fake_store, admin_user: User) -> None:
        app.config["LANGUAGES"] = ["en", "hu"]
        page = _seed_published_page(fake_store, admin_user)

        response = client.get(f"/register/{page.url_slug}/thank-you?lang=hu")
        assert "Köszönjük a regisztrációt" in response.get_data(as_text=True)

    def test_standard_page_is_shown_while_chosen_even_with_html_saved(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>", use_default=True)

        response = client.get(f"/register/{page.url_slug}/thank-you")
        assert b"Custom Thank You" not in response.data
        assert b"Thank you for registering" in response.data

    def test_show_own_shows_the_own_html_behind_the_standard_page_to_someone_who_can_view_the_assembly(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>", use_default=True)

        response = logged_in_admin.get(f"/register/{page.url_slug}/thank-you?show=own")
        assert b"Custom Thank You" in response.data

    def test_show_own_is_ignored_for_a_visitor_who_is_not_signed_in(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>", use_default=True)

        response = client.get(f"/register/{page.url_slug}/thank-you?show=own")
        assert b"Custom Thank You" not in response.data
        assert b"Thank you for registering" in response.data

    def test_show_own_is_ignored_for_someone_who_cannot_view_the_assembly(
        self, logged_in_user: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>", use_default=True)

        response = logged_in_user.get(f"/register/{page.url_slug}/thank-you?show=own")
        assert b"Custom Thank You" not in response.data

    def test_show_standard_shows_the_standard_page_while_own_html_is_chosen(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>")

        response = logged_in_admin.get(f"/register/{page.url_slug}/thank-you?show=standard")
        assert b"Custom Thank You" not in response.data
        assert b"Thank you for registering" in response.data

    def test_any_other_show_value_shows_the_chosen_page(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, page.id, "<h1>Custom Thank You</h1>")

        response = client.get(f"/register/{page.url_slug}/thank-you?show=nonsense")
        assert b"Custom Thank You" in response.data

    def test_own_page_fills_its_variables(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(
                uow, admin_user.id, page.id, '<p>{{ assembly_title }}</p><a href="{{ restart_url }}">again</a>'
            )

        body = client.get(f"/register/{page.url_slug}/thank-you").get_data(as_text=True)
        assert "Test Registration Assembly" in body
        assert f'href="http://localhost/register/{page.url_slug}"' in body

    def test_a_broken_own_page_falls_back_to_the_standard_page(
        self, client: FlaskClient, fake_store, admin_user: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The registration is already saved: the respondent must never see an error here."""
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
            stored.thank_you_html = "<p>{{ name }}</p>"
            stored.thank_you_use_default = False

        with caplog.at_level("ERROR"):
            response = client.get(f"/register/{page.url_slug}/thank-you")
        assert response.status_code == 200
        assert b"Thank you for registering" in response.data
        assert "Thank-you page failed to render" in caplog.text

    def test_an_error_that_is_not_the_template_s_is_not_swallowed(
        self, client: FlaskClient, fake_store, admin_user: User
    ) -> None:
        """Only a broken template falls back; anything else is a bug for the error handler."""
        page = _seed_published_page(fake_store, admin_user)

        with (
            patch("opendlp.entrypoints.blueprints.registration.render_thank_you_html", side_effect=RuntimeError("x")),
            pytest.raises(RuntimeError),
        ):
            client.get(f"/register/{page.url_slug}/thank-you")


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


class TestRegistrationPageNotFound:
    """A missing page at a registration address gets the registration pages' own
    page, in their GOV.UK look, not the error page the rest of the app shows."""

    def _assert_registration_not_found(self, response) -> None:  # type: ignore[no-untyped-def]
        assert response.status_code == 404
        body = response.get_data(as_text=True)
        assert '<h1 class="govuk-heading-l">Registration page not found</h1>' in body
        assert "contact the event organisers" in body
        # base_public.html, the registration pages' own base
        assert "register-page" in body
        assert "backoffice/dist/main.css" not in body
        assert '<meta name="robots" content="noindex, nofollow">' in body
        footer = body.split('<footer class="govuk-footer"', 1)[1]
        assert "Cookies" in footer
        assert "User Data Agreement" not in footer

    def test_an_unknown_page(self, client: FlaskClient) -> None:
        self._assert_registration_not_found(client.get("/register/nonexistent"))

    def test_an_unknown_short_url(self, client: FlaskClient) -> None:
        self._assert_registration_not_found(client.get("/r/nonexistent"))

    def test_an_unknown_thank_you_page(self, client: FlaskClient) -> None:
        self._assert_registration_not_found(client.get("/register/nonexistent/thank-you"))

    @pytest.mark.parametrize("path", ["/register/nonexistent/", "/register/a/b/c", "/r/nonexistent/more"])
    def test_an_address_no_route_matches(self, client: FlaskClient, path: str) -> None:
        """No registration route sees these, as none matches: the app's 404 handler decides by the path."""
        self._assert_registration_not_found(client.get(path))

    def test_with_registration_pages_switched_off(self, client_with_feature_disabled: FlaskClient) -> None:
        self._assert_registration_not_found(client_with_feature_disabled.get("/register/test-slug"))

    @pytest.mark.parametrize("path", ["/no-such-page", "/register", "/registration", "/r", "/rabbit/hole"])
    def test_other_addresses_get_the_usual_page(self, client: FlaskClient, path: str) -> None:
        response = client.get(path)

        assert response.status_code == 404
        body = response.get_data(as_text=True)
        assert "Page not found" in body
        assert "Registration page not found" not in body
        assert "govuk-" not in body

    def test_a_closed_page_still_redirects(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        with FakeUnitOfWork(store=fake_store) as uow:
            close_registration_page(uow, admin_user.id, page.id)

        response = client.get(f"/r/{page.short_url_slug}", follow_redirects=True)

        assert response.status_code == 200
        assert b"Registration Closed" in response.data


class TestRegistrationFooter:
    """The public registration pages' footer keeps the cookies link but drops the
    User Data Agreement, which is for platform users, not respondents."""

    def _assert_footer(self, response) -> None:  # type: ignore[no-untyped-def]
        assert response.status_code == 200
        footer = response.data.split(b'<footer class="govuk-footer"', 1)[1]
        assert b"Cookies" in footer
        assert b"User Data Agreement" not in footer

    def test_form_footer(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        self._assert_footer(client.get(f"/register/{page.url_slug}"))

    def test_thank_you_footer(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        page = _seed_published_page(fake_store, admin_user)
        self._assert_footer(client.get(f"/register/{page.url_slug}/thank-you"))

    def test_closed_footer(self, client: FlaskClient) -> None:
        self._assert_footer(client.get("/registration-closed"))


class TestUrlHelpers:
    def test_registration_url_matches_route(self, app) -> None:
        with app.test_request_context("http://example.org/"):
            assert registration_url("my-slug") == "http://example.org/register/my-slug"
            assert short_url("ma26") == "http://example.org/r/ma26"

    def test_prefixes_are_urls_without_a_slug(self, app) -> None:
        with app.test_request_context("http://example.org/"):
            assert registration_url_prefix() == "http://example.org/register/"
            assert short_url_prefix() == "http://example.org/r/"

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/register/my-slug", True),
            ("/register/my-slug/thank-you", True),
            ("/r/ma26", True),
            ("/register", False),
            ("/registration-closed", False),
            ("/register-assets/images/x.png", False),
            ("/r", False),
            ("/auth/register", False),
        ],
    )
    def test_registration_paths_are_those_under_register_and_r(self, path: str, expected: bool) -> None:
        assert is_registration_path(path) is expected
