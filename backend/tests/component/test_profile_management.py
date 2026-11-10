# ABOUTME: Component tests for profile management routes over a FakeUnitOfWork
# ABOUTME: Drives the real profile Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.blueprints import profile as profile_blueprint
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork

_HTMX = {"HX-Request": "true"}


@pytest.fixture
def oauth_user(fake_store: FakeStore) -> User:
    """A confirmed OAuth-only user (no password) in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=f"oauth-{uuid.uuid4()}@example.com",
            first_name="OAuth",
            last_name="User",
            oauth_provider="google",
            oauth_id="google-oauth-id-123",
            global_role=GlobalRole.USER,
        )
        return user.create_detached_copy()


def _login_session(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()


def _assert_page_is_named(page: bytes, name: str) -> None:
    """The <title> and the <h1> carry the page's name, exactly as written."""
    html = page.decode()
    assert re.search(rf"<title>\s*{re.escape(name)}\s*- OpenDLP</title>", html)
    assert re.search(rf"<h1[^>]*>\s*{re.escape(name)}\s*</h1>", html)


def _tag(html: str, name: str, attribute: str) -> str:
    """The first opening <name …> tag carrying `attribute`, e.g. 'aria-label="Edit first name"', or ""."""
    match = re.search(rf"<{name}\b[^>]*{re.escape(attribute)}[^>]*>", html)
    return match.group(0) if match else ""


def _stored_user(fake_store: FakeStore, user: User) -> User:
    with FakeUnitOfWork(store=fake_store) as uow:
        stored = uow.users.get(user.id)
        assert stored is not None
        return stored.create_detached_copy()


class TestProfileViewing:
    def test_view_profile_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_a_user_is_told_what_their_role_means(self, logged_in_user: FlaskClient) -> None:
        """The page used to render the raw enum value, which explained nothing."""
        response = logged_in_user.get("/profile")
        assert response.status_code == 200
        assert b"A Project Manager can add you to one" in response.data

    def test_an_organiser_is_told_what_their_role_means(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/profile")
        assert response.status_code == 200
        assert b"Organiser" in response.data
        assert b"You can create projects" in response.data

    def test_an_admin_is_told_what_their_role_means(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/profile")
        assert response.status_code == 200
        assert b"You can see and manage every project" in response.data

    def test_the_raw_enum_value_is_not_shown(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/profile")
        assert b">organiser<" not in response.data


class TestProfileEditing:
    def test_edit_profile_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/edit")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_the_edit_page_leads_to_my_account(self, logged_in_user: FlaskClient) -> None:
        """The names are edited in place on My account; a bookmark to the old page still lands there."""
        response = logged_in_user.get("/profile/edit")

        assert response.status_code == 302
        assert response.location == "/profile"


class TestNamesEditedInPlace:
    """My account edits the first and last name where they are shown, as the project details
    design does. The behaviour in the browser - the pencil, Escape, saving by the tick, Enter or
    leaving the row - is src/js/components/inline-edit.js and its tests; these pin the markup that
    component works on and the answers profile.edit gives it.
    """

    @pytest.mark.parametrize(
        ("field", "name", "autocomplete"),
        [("first_name", "first name", "given-name"), ("last_name", "last name", "family-name")],
    )
    def test_each_name_is_a_row_that_saves_itself(
        self, logged_in_user: FlaskClient, field: str, name: str, autocomplete: str
    ) -> None:
        html = logged_in_user.get("/profile").data.decode()

        form = _tag(html, "form", f'hx-target="#profile-{field}-row"')
        assert 'hx-post="/profile/edit"' in form
        assert 'hx-trigger="inline-edit-save"' in form
        assert 'x-data="inlineEdit"' in form
        assert "data-editing" not in form
        assert f'<input type="hidden" name="field" value="{field}">' in html
        assert f'<label for="{field}">' in html
        field_input = _tag(html, "input", f'name="{field}"')
        assert f'autocomplete="{autocomplete}"' in field_input
        assert 'maxlength="100"' in field_input
        assert "autofocus" not in field_input
        assert 'x-ref="edit"' in _tag(html, "button", f'aria-label="Edit {name}"')
        assert 'type="submit"' in _tag(html, "button", f'aria-label="Save {name}"')

    def test_the_names_show_at_rest(self, logged_in_user: FlaskClient) -> None:
        html = logged_in_user.get("/profile").data.decode()

        assert ">Test</p>" in html
        assert ">User</p>" in html
        # The separate edit page and its button are gone
        assert "Edit profile" not in html

    def test_a_save_answers_with_the_row_at_rest_and_a_flash(
        self, logged_in_user: FlaskClient, fake_store: FakeStore, regular_user: User
    ) -> None:
        response = logged_in_user.post(
            "/profile/edit", data={"field": "first_name", "first_name": "Grace"}, headers=_HTMX
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert html.lstrip().startswith('<div id="profile-first_name-row"')
        assert "<html" not in html
        assert "data-editing" not in _tag(html, "form", 'hx-target="#profile-first_name-row"')
        assert ">Grace</p>" in html
        # The flash joins the page's alerts out of band, so the next page does not show it again
        assert re.search(r'id="floating-alerts"\s+hx-swap-oob="beforeend"', html)
        assert "Profile updated successfully" in html
        assert _stored_user(fake_store, regular_user).first_name == "Grace"

    def test_a_save_made_inside_the_row_puts_focus_back_on_the_pencil(self, logged_in_user: FlaskClient) -> None:
        """The tick or Enter: the row is swapped out from under the keyboard, so it comes back focused."""
        response = logged_in_user.post(
            "/profile/edit",
            data={"field": "first_name", "first_name": "Grace", "return_focus": "1"},
            headers=_HTMX,
        )

        assert "autofocus" in _tag(response.data.decode(), "button", 'aria-label="Edit first name"')

    def test_a_save_made_by_leaving_the_row_leaves_focus_alone(self, logged_in_user: FlaskClient) -> None:
        """Focus went somewhere else on purpose; the row coming back must not take it."""
        response = logged_in_user.post(
            "/profile/edit",
            data={"field": "first_name", "first_name": "Grace", "return_focus": ""},
            headers=_HTMX,
        )

        assert b"autofocus" not in response.data

    def test_saving_one_name_leaves_the_other_alone(
        self, logged_in_user: FlaskClient, fake_store: FakeStore, regular_user: User
    ) -> None:
        logged_in_user.post("/profile/edit", data={"field": "first_name", "first_name": "Grace"}, headers=_HTMX)

        stored = _stored_user(fake_store, regular_user)
        assert (stored.first_name, stored.last_name) == ("Grace", "User")

    def test_a_name_can_be_left_blank(
        self, logged_in_user: FlaskClient, fake_store: FakeStore, regular_user: User
    ) -> None:
        response = logged_in_user.post("/profile/edit", data={"field": "last_name", "last_name": ""}, headers=_HTMX)

        assert response.status_code == 200
        assert ">Not set</p>" in response.data.decode()
        assert _stored_user(fake_store, regular_user).last_name == ""

    def test_a_refused_name_comes_back_open_with_the_reason(
        self, logged_in_user: FlaskClient, fake_store: FakeStore, regular_user: User
    ) -> None:
        too_long = "x" * 101

        response = logged_in_user.post(
            "/profile/edit", data={"field": "first_name", "first_name": too_long}, headers=_HTMX
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert "data-editing" in _tag(html, "form", 'hx-target="#profile-first_name-row"')
        field_input = _tag(html, "input", 'name="first_name"')
        assert f'value="{too_long}"' in field_input
        assert 'aria-invalid="true"' in field_input
        assert 'aria-describedby="first_name-error"' in field_input
        assert "autofocus" in field_input
        assert "Field cannot be longer than 100 characters" in html
        # What Escape puts back is the stored name, carried apart from the refused one
        assert 'value="Test"' in _tag(html, "input", 'x-ref="saved"')
        assert "Profile updated successfully" not in html
        assert _stored_user(fake_store, regular_user).first_name == "Test"

    def test_a_save_that_breaks_comes_back_open_with_a_general_reason(
        self, logged_in_user: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(**kwargs: object) -> User:
            raise RuntimeError("connection to server at db:5432 lost")

        monkeypatch.setattr(profile_blueprint, "update_own_profile", broken)

        response = logged_in_user.post(
            "/profile/edit", data={"field": "first_name", "first_name": "Grace"}, headers=_HTMX
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert "An error occurred while updating your profile" in html
        assert "db:5432" not in html
        assert "data-editing" in _tag(html, "form", 'hx-target="#profile-first_name-row"')

    @pytest.mark.parametrize("field", ["email", ""])
    def test_a_post_for_anything_but_a_name_is_refused(self, logged_in_user: FlaskClient, field: str) -> None:
        response = logged_in_user.post(
            "/profile/edit", data={"field": field, "email": "someone@example.com"}, headers=_HTMX
        )

        assert response.status_code == 400

    def test_without_htmx_a_save_goes_back_to_my_account_with_a_flash(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/edit", data={"field": "first_name", "first_name": "Grace"}, follow_redirects=True
        )

        assert response.status_code == 200
        assert response.request.path == "/profile"
        assert b"Profile updated successfully" in response.data
        assert b">Grace</p>" in response.data

    def test_without_htmx_a_refused_name_renders_my_account_with_the_row_open(
        self, logged_in_user: FlaskClient
    ) -> None:
        response = logged_in_user.post("/profile/edit", data={"field": "first_name", "first_name": "x" * 101})

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        html = response.data.decode()
        assert "data-editing" in _tag(html, "form", 'hx-target="#profile-first_name-row"')
        assert "data-editing" not in _tag(html, "form", 'hx-target="#profile-last_name-row"')
        assert "Field cannot be longer than 100 characters" in html
        assert 'aria-invalid="true"' in _tag(html, "input", 'name="first_name"')


# Each page a password user can open, and the name its <title> and <h1> carry
PASSWORD_USER_PAGES = {
    "/profile": "My account",
    "/profile/change-password": "Change password",  # pragma: allowlist secret
    "/profile/2fa": "Two-factor authentication",
    "/profile/2fa/setup": "Set up two-factor authentication",
}


class TestProfilePagesOnTheBackofficeDesign:
    """The profile pages left GOV.UK Frontend for the backoffice layout (sc-869).

    The set-password page is only reachable by an OAuth user without a password, and the
    regenerated backup codes page only by a POST with a valid code (tests/component/test_2fa_flow.py).
    """

    @pytest.mark.parametrize("url", PASSWORD_USER_PAGES)
    def test_page_has_no_govuk_markup(self, logged_in_user: FlaskClient, url: str) -> None:
        """A migrated page never mixes in GOV.UK classes or the GOV.UK stylesheet."""
        response = logged_in_user.get(url)

        assert response.status_code == 200
        assert b"govuk-" not in response.data
        assert b"css/application.css" not in response.data

    @pytest.mark.parametrize("url", PASSWORD_USER_PAGES)
    def test_page_uses_the_backoffice_layout(self, logged_in_user: FlaskClient, url: str) -> None:
        """The backoffice chrome is there: the account menu in the top bar and the flash container."""
        response = logged_in_user.get(url)

        assert b"backoffice/dist/main.css" in response.data
        assert b'id="account-menu-toggle"' in response.data
        assert b'id="floating-alerts"' in response.data

    @pytest.mark.parametrize(("url", "name"), PASSWORD_USER_PAGES.items())
    def test_page_is_named_in_sentence_case(self, logged_in_user: FlaskClient, url: str, name: str) -> None:
        """docs/language.md: sentence case for every string, the page's own name included."""
        response = logged_in_user.get(url)

        _assert_page_is_named(response.data, name)

    def test_view_sections_and_rows_are_in_sentence_case(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile")

        assert b"Profile information" in response.data
        assert b"First name" in response.data
        assert b"Last name" in response.data
        assert b"Authentication methods" in response.data
        assert b"Two-factor authentication" in response.data

    def test_set_password_page_is_on_the_backoffice_design(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/set-password")

        assert response.status_code == 200
        assert b"govuk-" not in response.data
        assert b"backoffice/dist/main.css" in response.data
        assert b'name="new_password"' in response.data
        assert b'name="new_password_confirm"' in response.data
        assert response.data.count(b'autocomplete="new-password"') == 2
        _assert_page_is_named(response.data, "Set password")
        assert b"Confirm password" in response.data

    def test_change_password_form_keeps_its_fields(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/change-password")

        assert b'<form method="POST" novalidate' in response.data
        assert b'name="current_password"' in response.data
        assert b'autocomplete="current-password"' in response.data
        assert b'name="new_password"' in response.data
        assert b'name="new_password_confirm"' in response.data
        assert response.data.count(b'autocomplete="new-password"') == 2
        # The show/hide toggle the design system renders on every password input
        assert response.data.count(b"data-toggle-password=") == 3
        # The password requirements list under the new password field
        assert b"Your password must meet the following requirements:" in response.data
        assert b"<li>" in response.data

    def test_change_password_shows_the_field_error_beside_the_field(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "userpass123",  # pragma: allowlist secret
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 200
        assert b'id="new_password-error"' in response.data
        assert b'aria-describedby="new_password-error"' in response.data

    def test_two_factor_settings_offer_the_set_up_when_disabled(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/2fa")

        assert b"Disabled" in response.data
        assert b"Current status" in response.data
        assert b"Enable two-factor authentication" in response.data
        assert b'href="/profile/2fa/setup"' in response.data
        assert b'aria-label="Back to profile"' in response.data
        # Nothing to regenerate or disable yet
        assert b"/profile/2fa/disable" not in response.data

    def test_my_account_menu_item_opens_in_the_same_tab(self, logged_in_user: FlaskClient) -> None:
        """It used to open a separate tab because the page was on the old design."""
        response = logged_in_user.get("/profile")

        my_account_link = re.search(rb'<a href="/profile"\s[^>]*>', response.data)
        assert my_account_link is not None
        assert b"target=" not in my_account_link.group(0)

    def test_view_links_back_to_the_projects_list(self, app: Flask, logged_in_user: FlaskClient) -> None:
        """The old page linked to main.dashboard, which 404s unless the old dashboard is enabled."""
        with app.test_request_context():
            projects_url = url_for("backoffice.dashboard")
        response = logged_in_user.get("/profile")

        back_link = re.search(rb'<a href="([^"]+)"[^>]*aria-label="Back to Your projects"', response.data)
        assert back_link is not None
        assert back_link.group(1).decode() == projects_url


class TestPasswordChange:
    def test_change_password_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/change-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_oauth_user_redirected_from_change_password(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/change-password", follow_redirects=True)
        assert response.status_code == 200
        assert b"Set password" in response.data
        assert b"You need to set a password first" in response.data

    def test_change_password_get(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/change-password")
        assert response.status_code == 200
        assert b"Change password" in response.data
        assert b"Current password" in response.data
        assert b"New password" in response.data
        assert b"Confirm new password" in response.data

    def test_change_password_with_wrong_current_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "WrongPassword123!",  # pragma: allowlist secret
                "new_password": "NewPassword123!",  # pragma: allowlist secret
                "new_password_confirm": "NewPassword123!",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Current password is incorrect" in response.data

    def test_change_password_with_weak_new_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "userpass123",  # pragma: allowlist secret
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Field must be at least 8 characters long" in response.data


class TestSetPassword:
    def test_set_password_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/set-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_set_password_redirects_user_with_existing_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/set-password", follow_redirects=True)
        assert response.status_code == 200
        assert b"You already have a password" in response.data

    def test_set_password_validates_strength(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.post(
            "/profile/set-password",
            data={
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Field must be at least 8 characters long" in response.data

    def test_set_password_requires_confirmation_match(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.post(
            "/profile/set-password",
            data={
                "new_password": "NewSecurePass123!",  # pragma: allowlist secret
                "new_password_confirm": "DifferentPass456!",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Passwords must match" in response.data

    def test_after_setting_password_user_can_remove_oauth(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        client.post(
            "/profile/set-password",
            data={
                "new_password": "NewSecurePass123!",  # pragma: allowlist secret
                "new_password_confirm": "NewSecurePass123!",  # pragma: allowlist secret
            },
        )

        response = client.post("/profile/remove-oauth", follow_redirects=True)

        assert response.status_code == 200
        assert b"OAuth authentication removed successfully" in response.data
