# ABOUTME: Component tests for profile management routes over a FakeUnitOfWork
# ABOUTME: Drives the real profile Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid
from typing import Any

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.blueprints import profile as profile_blueprint
from opendlp.service_layer.security import verify_password
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

    @pytest.mark.parametrize("name", ["first name", "last name"])
    def test_an_x_beside_the_tick_cancels_without_saving(self, logged_in_user: FlaskClient, name: str) -> None:
        """A mouse user's Escape: the stored name back, nothing sent."""
        html = logged_in_user.get("/profile").data.decode()

        cancel = _tag(html, "button", f'aria-label="Cancel editing {name}"')
        assert 'type="button"' in cancel
        assert '@click="cancel()"' in cancel
        assert 'x-show="editing"' in cancel
        assert "x-cloak" in cancel
        # Pressing it must not take focus from the field: in Safari the field would blur
        # to the page, which counts as leaving the row, and leaving the row saves.
        assert "@mousedown.prevent" in cancel
        assert "@mousedown.prevent" in _tag(html, "button", f'aria-label="Save {name}"')
        # Red, as the tick is green
        assert re.search(
            rf'aria-label="Cancel editing {name}"[^>]*>\s*<span class="btn-icon">\s*'
            r'<svg[^>]*style="color: var\(--color-error-text\);"',
            html,
        )

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


# Each page a password user can open, and the name its <title> and <h1> carry. Change
# password is a dialog over My account.
PASSWORD_USER_PAGES = {
    "/profile": "My account",
    "/profile/change-password": "My account",  # pragma: allowlist secret
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
        """Set password is a dialog over My account, as Change password is."""
        _login_session(client, oauth_user)

        response = client.get("/profile/set-password")

        assert response.status_code == 200
        assert b"govuk-" not in response.data
        assert b"backoffice/dist/main.css" in response.data
        assert b'name="new_password"' in response.data
        assert b'name="new_password_confirm"' in response.data
        assert response.data.count(b'autocomplete="new-password"') == 2
        _assert_page_is_named(response.data, "My account")
        assert re.search(rb'<h2 class="dialog-title" id="set-password-dialog-title">Set password</h2>', response.data)
        assert b"Confirm password" in response.data

    def test_change_password_form_keeps_its_fields(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/change-password", headers=_HTMX)

        assert 'action="/profile/change-password"' in _tag(response.data.decode(), "form", "novalidate")
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

    def test_an_account_without_a_password_gets_the_set_password_dialog(
        self, client: FlaskClient, oauth_user: User
    ) -> None:
        """It has no current password to type, so the address opens the dialog that sets one."""
        _login_session(client, oauth_user)

        response = client.get("/profile/change-password")

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        assert re.search(rb'<h2 class="dialog-title" id="set-password-dialog-title">Set password</h2>', response.data)
        assert b'name="current_password"' not in response.data

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


class TestChangePasswordDialog:
    """Change password opens in a dialog over My account: a fragment dialog loaded over htmx
    into the page's dialog host (docs/agent/component_accessibility.md), whose focus handling,
    inert page and Escape are init/fragment-dialog-focus.js and the modal() component's.
    """

    def _post(
        self, client: FlaskClient, new_password: str, current: str = "userpass123", **kwargs: Any
    ) -> TestResponse:
        return client.post(
            "/profile/change-password",
            data={
                "current_password": current,
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
            **kwargs,
        )

    def test_my_account_opens_the_dialog_from_a_button(self, logged_in_user: FlaskClient) -> None:
        html = logged_in_user.get("/profile").data.decode()

        opener = _tag(html, "button", 'hx-get="/profile/change-password"')
        assert 'aria-haspopup="dialog"' in opener
        assert 'hx-target="#profile-dialog-host"' in opener
        # Focus comes back to it, found by this, when the dialog closes
        assert 'data-focus-id="change-password"' in opener
        assert re.search(r'<div id="profile-dialog-host" data-fragment-dialog-host>\s*</div>', html)

    def test_my_account_offers_no_change_without_a_password(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        html = client.get("/profile").data.decode()

        assert not _tag(html, "button", 'hx-get="/profile/change-password"')

    def test_over_htmx_the_address_answers_with_the_dialog(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/change-password", headers=_HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        assert "<html" not in html
        dialog = _tag(html, "div", 'role="dialog"')
        assert 'aria-modal="true"' in dialog
        assert 'aria-labelledby="change-password-dialog-title"' in dialog
        assert re.search(r'<h2 class="dialog-title" id="change-password-dialog-title">Change password</h2>', html)
        # Closing hides it in place, and the host hands focus back to the button
        assert 'x-data="modal({ initialOpen: true })"' in html
        form = _tag(html, "form", 'hx-post="/profile/change-password"')
        assert 'hx-target="#profile-dialog-host"' in form
        assert 'hx-swap="innerHTML"' in form
        assert "data-dialog-initial-focus" not in html
        assert _tag(html, "button", '@click="close()"')

    def test_without_htmx_the_address_is_my_account_with_the_dialog_open(self, logged_in_user: FlaskClient) -> None:
        """Where /.well-known/change-password sends a password manager."""
        response = logged_in_user.get("/profile/change-password")

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        html = response.data.decode()
        host = html[html.index('id="profile-dialog-host"') :]
        assert 'role="dialog"' in host
        # Closing goes to My account, so the address stops opening the dialog
        assert "x-data=\"modal({ initialOpen: true, closeUrl: '/profile' })\"" in host

    def test_a_refused_change_comes_back_as_the_dialog_with_the_reason(self, logged_in_user: FlaskClient) -> None:
        response = self._post(logged_in_user, "weak", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert 'role="dialog"' in html
        new_password = _tag(html, "input", 'name="new_password"')
        assert 'aria-describedby="new_password-error"' in new_password
        assert "data-dialog-initial-focus" in new_password
        assert "Field must be at least 8 characters long" in html
        # A password is never sent back to the page
        assert 'value="weak"' not in html

    def test_a_wrong_current_password_is_said_beside_its_field(self, logged_in_user: FlaskClient) -> None:
        response = self._post(logged_in_user, "NewPassword456!", current="WrongPassword123!", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        current = _tag(html, "input", 'name="current_password"')
        assert 'aria-invalid="true"' in current
        assert "data-dialog-initial-focus" in current
        assert re.search(r'<p id="current_password-error"[^>]*>Current password is incorrect</p>', html)
        # Not flashed: the page's alerts sit beneath an open dialog, and would surface on the next page
        assert b"Current password is incorrect" not in logged_in_user.get("/profile").data

    def test_a_password_the_strength_rules_refuse_is_said_beside_the_new_password(
        self, logged_in_user: FlaskClient
    ) -> None:
        response = self._post(logged_in_user, "1234567890", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert "New password is too weak:" in html
        assert 'aria-invalid="true"' in _tag(html, "input", 'name="new_password"')

    def test_a_change_that_breaks_is_said_in_the_dialog(
        self, logged_in_user: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(**kwargs: object) -> None:
            raise RuntimeError("connection to server at db:5432 lost")

        monkeypatch.setattr(profile_blueprint, "change_own_password", broken)

        response = self._post(logged_in_user, "NewPassword456!", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert 'role="dialog"' in html
        assert "An error occurred while changing your password" in html
        assert "db:5432" not in html

    def test_a_change_closes_the_dialog_and_says_so(
        self, logged_in_user: FlaskClient, fake_store: FakeStore, regular_user: User
    ) -> None:
        response = self._post(logged_in_user, "NewPassword456!", headers=_HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        # Nothing left for the host, which closes the dialog; the flash joins the page's alerts
        assert 'role="dialog"' not in html
        assert re.search(r'id="floating-alerts"\s+hx-swap-oob="beforeend"', html)
        assert "Password changed successfully" in html
        stored = _stored_user(fake_store, regular_user)
        assert stored.password_hash is not None
        assert verify_password("NewPassword456!", stored.password_hash)  # pragma: allowlist secret

    def test_without_htmx_a_change_goes_back_to_my_account(self, logged_in_user: FlaskClient) -> None:
        response = self._post(logged_in_user, "NewPassword456!", follow_redirects=True)

        assert response.status_code == 200
        assert response.request.path == "/profile"
        assert b"Password changed successfully" in response.data
        assert b'role="dialog"' not in response.data

    def test_without_htmx_a_refused_change_renders_my_account_with_the_dialog_open(
        self, logged_in_user: FlaskClient
    ) -> None:
        response = self._post(logged_in_user, "weak")

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        html = response.data.decode()
        assert 'role="dialog"' in html
        assert "Field must be at least 8 characters long" in html

    def test_over_htmx_an_account_without_a_password_gets_the_set_password_dialog(
        self, client: FlaskClient, oauth_user: User
    ) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/change-password", headers=_HTMX)

        assert response.status_code == 200
        assert "HX-Redirect" not in response.headers
        assert b'id="set-password-dialog-title">Set password</h2>' in response.data


class TestSetPassword:
    def test_set_password_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/set-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_an_account_with_a_password_gets_the_change_password_dialog(self, logged_in_user: FlaskClient) -> None:
        """It has a password to change, so the address opens the dialog that changes it."""
        response = logged_in_user.get("/profile/set-password")

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        assert b'id="change-password-dialog-title">Change password</h2>' in response.data
        assert b'name="current_password"' in response.data

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


class TestSetPasswordDialog:
    """Set password, for an account that signs in only with Google or Microsoft, opens in the
    dialog Change password uses: the same fragment dialog host, focus handling and answers,
    except that a password set reloads My account, whose password row it changes.
    """

    def _post(self, client: FlaskClient, password: str, confirm: str = "", **kwargs: Any) -> TestResponse:
        return client.post(
            "/profile/set-password",
            data={"new_password": password, "new_password_confirm": confirm or password},
            **kwargs,
        )

    def test_my_account_opens_the_dialog_from_the_password_row(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        html = client.get("/profile").data.decode()

        opener = _tag(html, "button", 'hx-get="/profile/set-password"')
        assert 'aria-haspopup="dialog"' in opener
        assert 'hx-target="#profile-dialog-host"' in opener
        # Focus comes back to it, found by this, when the dialog closes
        assert 'data-focus-id="set-password"' in opener
        assert re.search(r'<div id="profile-dialog-host" data-fragment-dialog-host>\s*</div>', html)

    def test_over_htmx_the_address_answers_with_the_dialog(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/set-password", headers=_HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        assert "<html" not in html
        dialog = _tag(html, "div", 'role="dialog"')
        assert 'aria-modal="true"' in dialog
        assert 'aria-labelledby="set-password-dialog-title"' in dialog
        assert "You will be able to sign in using either your password or Google OAuth." in html
        assert 'name="current_password"' not in html
        assert html.count('autocomplete="new-password"') == 2
        # The Show toggles beside both fields
        assert html.count("data-toggle-password=") == 2
        form = _tag(html, "form", 'hx-post="/profile/set-password"')
        assert 'hx-target="#profile-dialog-host"' in form
        assert 'x-data="modal({ initialOpen: true })"' in html

    def test_without_htmx_the_address_is_my_account_with_the_dialog_open(
        self, client: FlaskClient, oauth_user: User
    ) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/set-password")

        assert response.status_code == 200
        _assert_page_is_named(response.data, "My account")
        html = response.data.decode()
        host = html[html.index('id="profile-dialog-host"') :]
        assert 'aria-labelledby="set-password-dialog-title"' in host
        assert "x-data=\"modal({ initialOpen: true, closeUrl: '/profile' })\"" in host

    def test_a_refused_password_comes_back_as_the_dialog_with_the_reason(
        self, client: FlaskClient, oauth_user: User
    ) -> None:
        _login_session(client, oauth_user)

        response = self._post(client, "NewSecurePass123!", confirm="DifferentPass456!", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert 'aria-labelledby="set-password-dialog-title"' in html
        confirm = _tag(html, "input", 'name="new_password_confirm"')
        assert 'aria-describedby="new_password_confirm-error"' in confirm
        assert "data-dialog-initial-focus" in confirm
        assert "Passwords must match" in html
        # Not flashed: the page's alerts sit beneath an open dialog
        assert b"Passwords must match" not in client.get("/profile").data

    def test_a_password_the_strength_rules_refuse_is_said_beside_it(
        self, client: FlaskClient, oauth_user: User
    ) -> None:
        _login_session(client, oauth_user)

        response = self._post(client, "1234567890", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert "Password is too weak:" in html
        assert 'aria-invalid="true"' in _tag(html, "input", 'name="new_password"')

    def test_a_password_that_breaks_is_said_in_the_dialog(
        self, client: FlaskClient, oauth_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(password: str) -> str:
            raise RuntimeError("connection to server at db:5432 lost")

        monkeypatch.setattr(profile_blueprint, "hash_password", broken)
        _login_session(client, oauth_user)

        response = self._post(client, "Another-Passphrase-42", headers=_HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert "An error occurred while setting your password" in html
        assert "db:5432" not in html

    def test_a_password_set_reloads_my_account_with_focus_on_change_password(
        self, client: FlaskClient, oauth_user: User, fake_store: FakeStore
    ) -> None:
        """The page behind changes - the password row, the Change password button - so it loads afresh."""
        _login_session(client, oauth_user)

        response = self._post(client, "Another-Passphrase-42", headers=_HTMX)

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/profile#focus=change-password"
        stored = _stored_user(fake_store, oauth_user)
        assert stored.has_usable_password()
        html = client.get("/profile").data.decode()
        assert "Password set successfully" in html
        assert 'data-focus-id="change-password"' in _tag(html, "button", 'hx-get="/profile/change-password"')

    def test_without_htmx_a_password_set_goes_back_to_my_account(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = self._post(client, "Another-Passphrase-42", follow_redirects=True)

        assert response.status_code == 200
        assert response.request.path == "/profile"
        assert b"Password set successfully" in response.data
        assert b'role="dialog"' not in response.data
