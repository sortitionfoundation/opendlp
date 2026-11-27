# ABOUTME: Component tests for admin user management routes over a FakeUnitOfWork
# ABOUTME: Drives the real admin Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.domain.users import MAX_NAME_LENGTH, User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import UserNotFoundError
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeEmailAdapter, FakeStore, FakeUnitOfWork

# What htmx sends with every request it makes, and what the routes answer differently.
HTMX_HEADERS = {"HX-Request": "true"}


def _second_client(app: Flask, user: User | None = None) -> FlaskClient:
    """A client separate from the conftest one, optionally signed in.

    The `client` and `logged_in_*` fixtures hand back the same object, so a test
    that needs both an admin and a victim browsing at once has to make its own.
    """
    other = app.test_client()
    if user is not None:
        with other.session_transaction() as session:
            session["_user_id"] = user.get_id()
            session["_fresh"] = True
    return other


def _seed_user(
    fake_store: FakeStore,
    email: str,
    global_role: GlobalRole,
    first_name: str = "",
    last_name: str = "",
    is_active: bool = True,
) -> User:
    """Create a confirmed user in the shared store and return a detached copy."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=email,
            password="SecurePass123!",  # pragma: allowlist secret
            global_role=global_role,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


class TestAdminUserListPermissions:
    """Permission and auth branches for the admin user list."""

    def test_list_users_not_accessible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/admin/users")
        assert response.status_code == 403

    def test_list_users_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        response = client.get("/admin/users")
        assert response.status_code == 302
        assert "login" in response.location


class TestSiteAdminLayout:
    """Site Admin opens on the users list, and its list pages share a tab bar."""

    def test_site_admin_index_redirects_to_the_users_list(self, logged_in_admin: FlaskClient) -> None:
        """/admin/ has no page of its own; it lands on the Users tab."""
        response = logged_in_admin.get("/admin/")
        assert response.status_code == 302
        assert response.location.endswith("/admin/users")

    def test_site_admin_index_refused_to_a_regular_user(self, logged_in_user: FlaskClient) -> None:
        """The redirect is still behind the admin check."""
        assert logged_in_user.get("/admin/").status_code == 403

    def test_users_list_is_on_the_backoffice_design(self, logged_in_admin: FlaskClient) -> None:
        """The users list renders on the backoffice base, not the GOV.UK one."""
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert "backoffice/dist/main.css" in body
        assert "govuk-" not in body

    def test_users_list_has_the_users_tab_selected(self, logged_in_admin: FlaskClient) -> None:
        """The Users tab is selected and the Invites tab links to the invites list."""
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert re.search(r'id="admin-tabs-tab-users"[^>]*aria-selected="true"', body)
        assert re.search(r'href="/admin/invites"[^>]*\s+role="tab"[^>]*id="admin-tabs-tab-invites"', body)
        assert 'id="admin-tabs-panel-users"' in body

    def test_users_list_back_arrow_goes_to_your_projects(self, logged_in_admin: FlaskClient) -> None:
        """The page header's back arrow leads to Your projects."""
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert re.search(r'<a href="/backoffice/dashboard"[^>]*aria-label="Back to Your projects"', body, re.DOTALL)


class TestAdminUserList:
    """What the users list shows."""

    def test_shows_counts_and_users(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """The stat tiles and a row per user appear."""
        _seed_user(fake_store, "listed@example.com", GlobalRole.USER, first_name="Listed", last_name="Person")
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert "Total users" in body
        assert "2FA enabled" in body
        assert "listed@example.com" in body
        assert "Listed Person" in body

    def test_a_row_links_to_the_users_page(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Clicking a row opens the user's page."""
        user = _seed_user(fake_store, "row@example.com", GlobalRole.USER)
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert f'data-row-url="/admin/users/{user.id}"' in body

    def test_filters_keep_their_values(self, logged_in_admin: FlaskClient) -> None:
        """The search box and selects show what was filtered on, with a count of matches."""
        body = logged_in_admin.get("/admin/users?search=nobody&role=organiser&active=false").get_data(as_text=True)
        assert 'value="nobody"' in body
        assert re.search(r'<option value="organiser"\s+selected', body)
        assert re.search(r'<option value="false"\s+selected', body)
        assert "Users found: 0" in body
        assert "No users found matching your criteria." in body

    def test_search_can_be_cleared_and_filters_cleared_all_at_once(self, logged_in_admin: FlaskClient) -> None:
        """The search box has a clear button that resubmits, and Clear all is a tertiary button."""
        body = logged_in_admin.get("/admin/users?search=smith").get_data(as_text=True)
        assert re.search(r'x-data="clearableInput"[^>]*data-clear-submits="true"', body, re.DOTALL)
        assert 'aria-label="Clear search"' in body
        assert re.search(
            r'<a href="/admin/users"\s+role="button"\s+class="btn btn--tertiary"[^>]*><span>Clear all</span>', body
        )

    def test_export_button_opens_the_export_dialog(self, logged_in_admin: FlaskClient) -> None:
        """Export loads its dialog into the page's dialog host, under a one-word label."""
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert re.search(
            r'<button[^>]*hx-get="/admin/users/export/modal"[^>]*hx-target="#export-modal-container"[^>]*>'
            r"\s*<span>Export</span>",
            body,
        )
        assert re.search(r'<div id="export-modal-container" data-fragment-dialog-host>', body)

    def test_points_to_invites_for_adding_a_user(self, logged_in_admin: FlaskClient) -> None:
        """Users are added by invite, and the page says so with a link."""
        body = logged_in_admin.get("/admin/users").get_data(as_text=True)
        assert re.search(r'To add a user, <a href="/admin/invites/create"[^>]*>create an invite</a> for them\.', body)


class TestAdminUserView:
    """Admin view user details page."""

    def test_view_user_not_accessible_to_regular_user(self, logged_in_user: FlaskClient, regular_user: User) -> None:
        response = logged_in_user.get(f"/admin/users/{regular_user.id}")
        assert response.status_code == 403

    def test_view_user_shows_user_details(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "view@example.com", GlobalRole.USER, "View", "Target")

        response = logged_in_admin.get(f"/admin/users/{user.id}")
        assert response.status_code == 200
        assert user.email.encode() in response.data
        assert user.first_name.encode() in response.data
        assert user.last_name.encode() in response.data

    def test_view_user_is_on_the_backoffice_design(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """The user page has a back arrow to the users list and no GOV.UK markup."""
        user = _seed_user(fake_store, "design@example.com", GlobalRole.USER)

        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        assert "govuk-" not in body
        assert re.search(r'<a href="/admin/users"[^>]*aria-label="Back to Users"', body, re.DOTALL)
        assert f'action="/admin/users/{user.id}/name"' in body
        assert f'href="/admin/users/{user.id}/2fa/audit-log"' in body

    def test_an_oauth_user_shows_their_provider_and_no_2fa_link(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Two-factor does not apply to an OAuth user, so there is no audit log link."""
        with FakeUnitOfWork(store=fake_store) as uow:
            oauth_user = User(
                email="viewoauth@example.com",
                global_role=GlobalRole.USER,
                oauth_provider="google",
                oauth_id="google456",
            )
            uow.users.add(oauth_user)
            uow.commit()
            user_id = oauth_user.id

        body = logged_in_admin.get(f"/admin/users/{user_id}").get_data(as_text=True)

        assert "Google" in body
        assert "Not applicable (OAuth user)" in body
        assert "/2fa/audit-log" not in body
        assert "will still sign in with Google" in body

    def test_disable_2fa_is_offered_only_when_2fa_is_on(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """The Disable 2FA dialog appears for a user with two-factor on, and not otherwise."""
        user = _seed_user(fake_store, "no2fa@example.com", GlobalRole.USER)
        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)
        assert "disable-2fa-dialog" not in body

        with FakeUnitOfWork(store=fake_store) as uow:
            uow.users.get(user.id).enable_totp("encrypted-secret")
            uow.commit()
        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        assert 'id="disable-2fa-dialog-open"' in body
        assert "Disable two-factor authentication?" in body
        assert f'<form method="post" action="/admin/users/{user.id}/2fa/disable">' in body

    def test_enabling_is_confirmed_in_a_dialog(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """A disabled user's page offers Enable account through a dialog that explains the email."""
        user = _seed_user(fake_store, "disabled@example.com", GlobalRole.USER, is_active=False)

        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        assert 'id="enable-account-dialog-open"' in body
        assert "Enable this account?" in body
        assert "request a password reset" in body
        assert f'<form method="post" action="/admin/users/{user.id}/enable">' in body


class TestAdminUser2faAuditLog:
    """The two-factor audit log page for one user."""

    def _log(self, fake_store: FakeStore, user: User, action: str, **kwargs: object) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.two_factor_audit_logs.add(TwoFactorAuditLog(user_id=user.id, action=action, **kwargs))
            uow.commit()

    def test_each_known_action_has_a_translated_tag(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Recorded actions show as labels, never as their stored tokens."""
        user = _seed_user(fake_store, "audited@example.com", GlobalRole.USER)
        self._log(fake_store, user, "enabled", performed_by=user.id)
        self._log(fake_store, user, "backup_codes_regenerated", performed_by=user.id)

        body = logged_in_admin.get(f"/admin/users/{user.id}/2fa/audit-log").get_data(as_text=True)

        assert ">Enabled</strong>" in body
        assert ">Backup codes regenerated</strong>" in body
        assert "backup_codes_regenerated" not in body
        assert "Self" in body
        assert "govuk-" not in body

    def test_an_unknown_action_is_not_shown_raw(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """An action the page does not know shows a generic tag instead of the database token."""
        user = _seed_user(fake_store, "oddlog@example.com", GlobalRole.USER)
        self._log(fake_store, user, "some_future_event")

        body = logged_in_admin.get(f"/admin/users/{user.id}/2fa/audit-log").get_data(as_text=True)

        assert ">Unknown action</strong>" in body
        assert "some_future_event" not in body
        assert "System" in body

    def test_another_performer_is_named_by_email(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        """An admin who acted on the account is shown by their email, with the details collapsed."""
        user = _seed_user(fake_store, "acted@example.com", GlobalRole.USER)
        self._log(fake_store, user, "admin_disabled", performed_by=admin_user.id, metadata={"reason": "lost phone"})

        body = logged_in_admin.get(f"/admin/users/{user.id}/2fa/audit-log").get_data(as_text=True)

        assert ">Admin disabled</strong>" in body
        assert admin_user.email in body
        assert "<details" in body
        assert "lost phone" in body

    def test_no_entries_says_so(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """A user with no two-factor history gets a message, not an empty table."""
        user = _seed_user(fake_store, "quiet@example.com", GlobalRole.USER)

        body = logged_in_admin.get(f"/admin/users/{user.id}/2fa/audit-log").get_data(as_text=True)

        assert "No 2FA audit log entries found for this user." in body
        assert "audit-log-table" not in body


class TestAdminUserEdit:
    """There is no edit page: a user is edited on their own page."""

    def test_the_old_edit_address_goes_to_the_users_page(
        self, logged_in_admin: FlaskClient, regular_user: User
    ) -> None:
        """There is no edit page any more; old links land on the user's page."""
        response = logged_in_admin.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 302
        assert response.location.endswith(f"/admin/users/{regular_user.id}")

    def test_edit_address_not_accessible_to_regular_user(self, logged_in_user: FlaskClient, regular_user: User) -> None:
        response = logged_in_user.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 403


class TestAdminUserNameEdit:
    """A user's names are edited in place on their page, one at a time."""

    def test_the_page_has_a_pencil_for_each_name(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Both names are rows edited in place, posting to the name route."""
        user = _seed_user(fake_store, "pencil@example.com", GlobalRole.USER, "Pen", "Cil")

        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        assert 'id="admin-user-first_name-row"' in body
        assert 'id="admin-user-last_name-row"' in body
        assert 'aria-label="Edit first name"' in body
        assert 'aria-label="Edit last name"' in body

    @pytest.mark.parametrize("field", ["first_name", "last_name"])
    def test_a_name_field_is_limited_and_not_filled_with_the_admins_own(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, field: str
    ) -> None:
        """The field takes as many characters as the form allows, and the browser is not
        asked to fill it in: it would offer the admin's own name, not the user's."""
        user = _seed_user(fake_store, "limits@example.com", GlobalRole.USER, "Lim", "Its")

        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        field_input = re.search(rf'<input[^>]*name="{field}"[^>]*>', body)
        assert field_input is not None
        assert f'maxlength="{MAX_NAME_LENGTH}"' in field_input.group(0)
        assert 'autocomplete="off"' in field_input.group(0)

    def test_saving_a_name_over_htmx_answers_with_the_row(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """The row comes back at rest with the new name, and the flash out of band."""
        user = _seed_user(fake_store, "rename@example.com", GlobalRole.USER, "Old", "Name")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name",
            data={"field": "first_name", "first_name": "New", "return_focus": "1"},
            headers=HTMX_HEADERS,
        )

        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="admin-user-first_name-row"' in body
        assert re.search(r">\s*New\s*<", body) is not None
        assert 'id="floating-alerts"' in body and "updated successfully" in body
        assert "<html" not in body
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.users.get(user.id)
            assert stored.first_name == "New"
            assert stored.last_name == "Name"

    def test_saving_a_name_without_htmx_goes_back_to_the_page(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Without htmx the save redirects to the user's page."""
        user = _seed_user(fake_store, "plain@example.com", GlobalRole.USER, "Plain", "Form")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name", data={"field": "last_name", "last_name": "Post"}
        )

        assert response.status_code == 302
        assert response.location.endswith(f"/admin/users/{user.id}")
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).last_name == "Post"

    def test_a_refused_name_over_htmx_stays_open_with_the_reason(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Too long a name is refused with 422, the row open with what was typed."""
        user = _seed_user(fake_store, "long@example.com", GlobalRole.USER, "Short", "Name")
        too_long = "x" * (MAX_NAME_LENGTH + 1)

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name",
            data={"field": "first_name", "first_name": too_long},
            headers=HTMX_HEADERS,
        )

        body = response.get_data(as_text=True)
        assert response.status_code == 422
        assert f'value="{too_long}"' in body
        assert 'aria-invalid="true"' in body
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).first_name == "Short"

    def test_a_refused_name_without_htmx_renders_the_page_with_the_row_open(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Without htmx a refusal shows the whole page, that row open with the reason."""
        user = _seed_user(fake_store, "longplain@example.com", GlobalRole.USER, "Short", "Name")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name", data={"field": "last_name", "last_name": "y" * (MAX_NAME_LENGTH + 1)}
        )

        body = response.get_data(as_text=True)
        assert response.status_code == 422
        assert "<html" in body
        assert 'id="last_name-error"' in body
        assert 'id="first_name-error"' not in body
        assert "100 characters" in body
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).last_name == "Name"

    def test_a_blank_name_clears_it(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """An emptied field saves an empty name, rather than leaving the name as it was."""
        user = _seed_user(fake_store, "blank@example.com", GlobalRole.USER, "Gone", "Stays")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name", data={"field": "first_name", "first_name": ""}, headers=HTMX_HEADERS
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.users.get(user.id)
            assert stored.first_name == ""
            assert stored.last_name == "Stays"

    def test_an_unknown_user_over_htmx_redirects_to_the_users_list(self, logged_in_admin: FlaskClient) -> None:
        """htmx is told to load the users list, rather than swap a redirect into the row."""
        response = logged_in_admin.post(
            f"/admin/users/{uuid.uuid4()}/name", data={"field": "first_name", "first_name": "X"}, headers=HTMX_HEADERS
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/admin/users"
        assert logged_in_admin.get("/admin/users").get_data(as_text=True).count("User not found") == 1

    def test_an_unknown_user_without_htmx_redirects_to_the_users_list(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(
            f"/admin/users/{uuid.uuid4()}/name", data={"field": "first_name", "first_name": "X"}
        )

        assert response.status_code == 302
        assert response.location.endswith("/admin/users")
        assert "HX-Redirect" not in response.headers

    def test_a_user_gone_by_the_save_redirects_to_the_users_list(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A user who goes between the page loading the user and the save is reported as not found."""
        user = _seed_user(fake_store, "vanish@example.com", GlobalRole.USER, "Van", "Ish")

        def _gone(**kwargs: object) -> User:
            raise UserNotFoundError(f"User {user.id} not found")

        monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.update_user", _gone)
        response = logged_in_admin.post(
            f"/admin/users/{user.id}/name", data={"field": "first_name", "first_name": "X"}, headers=HTMX_HEADERS
        )

        assert response.headers["HX-Redirect"] == "/admin/users"

    def test_an_unexpected_error_leaves_the_row_open_and_is_logged(
        self,
        logged_in_admin: FlaskClient,
        fake_store: FakeStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failed save answers 422 with a generic reason, never the exception's text."""
        user = _seed_user(fake_store, "boom@example.com", GlobalRole.USER, "Keep", "Me")

        def _boom(**kwargs: object) -> User:
            raise RuntimeError("database exploded")

        monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.update_user", _boom)
        with caplog.at_level("ERROR"):
            response = logged_in_admin.post(
                f"/admin/users/{user.id}/name", data={"field": "first_name", "first_name": "X"}, headers=HTMX_HEADERS
            )

        body = response.get_data(as_text=True)
        assert response.status_code == 422
        assert "An error occurred while updating the user" in body
        assert "database exploded" not in body
        assert "Error updating user name" in caplog.text
        assert "Traceback" in caplog.text

    def test_an_unknown_field_is_refused(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Only the two names can be posted; the email cannot be changed this way."""
        user = _seed_user(fake_store, "field@example.com", GlobalRole.USER)

        response = logged_in_admin.post(f"/admin/users/{user.id}/name", data={"field": "email", "email": "x@y.z"})

        assert response.status_code == 400

    def test_a_regular_user_cannot_save_a_name(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "victim@example.com", GlobalRole.USER, "Keep", "Me")

        response = logged_in_user.post(f"/admin/users/{user.id}/name", data={"field": "first_name", "first_name": "X"})

        assert response.status_code == 403
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).first_name == "Keep"


class TestAdminUserRoleEdit:
    """A user's global role is changed in a dialog on their page."""

    def test_the_role_dialog_preselects_the_current_role(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """The Change role dialog opens on the role the user has now."""
        organiser = _seed_user(fake_store, "organiser@example.com", GlobalRole.ORGANISER, "Global", "Organiser")

        body = logged_in_admin.get(f"/admin/users/{organiser.id}").get_data(as_text=True)

        assert 'id="change-role-open"' in body
        assert f'action="/admin/users/{organiser.id}/role"' in body
        assert re.search(r'value="ORGANISER"[^>]*?checked', body) is not None
        assert re.search(r'value="USER"[^>]*?checked', body) is None

    def test_changing_the_role_saves_it_and_goes_back(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """The dialog's form changes the role and leaves the account active."""
        user = _seed_user(fake_store, "role@example.com", GlobalRole.USER, "Role", "Change")

        response = logged_in_admin.post(f"/admin/users/{user.id}/role", data={"global_role": GlobalRole.ORGANISER.name})

        assert response.status_code == 302
        assert response.location.endswith(f"/admin/users/{user.id}")
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.users.get(user.id)
            assert stored.global_role == GlobalRole.ORGANISER
            assert stored.is_active is True

    def test_an_invalid_role_is_refused(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """A role that is not one of the choices changes nothing."""
        user = _seed_user(fake_store, "badrole@example.com", GlobalRole.USER)

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/role", data={"global_role": "EMPEROR"}, follow_redirects=True
        )

        assert b"Choose a role for this user" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).global_role == GlobalRole.USER

    def test_admin_cannot_change_own_role(
        self, logged_in_admin: FlaskClient, admin_user: User, fake_store: FakeStore
    ) -> None:
        """Posting a new role for yourself is refused, and the page offers no dialog for it."""
        response = logged_in_admin.post(
            f"/admin/users/{admin_user.id}/role", data={"global_role": GlobalRole.USER.name}, follow_redirects=True
        )
        assert b"You cannot change your own role" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(admin_user.id).global_role == GlobalRole.ADMIN

        body = logged_in_admin.get(f"/admin/users/{admin_user.id}").get_data(as_text=True)
        assert "change-role-open" not in body

    def test_changing_an_unknown_users_role_says_so(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"/admin/users/{uuid.uuid4()}/role", data={"global_role": GlobalRole.USER.name})

        assert response.status_code == 302
        assert response.location.endswith("/admin/users")
        assert "User not found" in logged_in_admin.get("/admin/users").get_data(as_text=True)

    def test_an_unexpected_error_changing_the_role_is_logged(
        self,
        logged_in_admin: FlaskClient,
        fake_store: FakeStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failed change goes back to the user's page with a generic message, never the exception's text."""
        user = _seed_user(fake_store, "roleboom@example.com", GlobalRole.USER)

        def _boom(**kwargs: object) -> User:
            raise RuntimeError("database exploded")

        monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.update_user", _boom)
        with caplog.at_level("ERROR"):
            response = logged_in_admin.post(
                f"/admin/users/{user.id}/role", data={"global_role": GlobalRole.ADMIN.name}, follow_redirects=True
            )

        body = response.get_data(as_text=True)
        assert "An error occurred while updating the user" in body
        assert "database exploded" not in body
        assert "Error changing user role" in caplog.text
        assert "Traceback" in caplog.text
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).global_role == GlobalRole.USER

    def test_a_regular_user_cannot_change_a_role(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "promote@example.com", GlobalRole.USER)

        response = logged_in_user.post(f"/admin/users/{user.id}/role", data={"global_role": GlobalRole.ADMIN.name})

        assert response.status_code == 403
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).global_role == GlobalRole.USER


class TestAdminDisableAccount:
    """Disabling has to leave no way back in until the account is enabled again."""

    def test_a_disabled_user_is_signed_out_on_their_next_request(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore
    ) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        victim_client = _second_client(app, victim)
        assert victim_client.get("/backoffice/dashboard").status_code == 200

        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        response = victim_client.get("/backoffice/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.location

    def test_the_cancelled_session_stays_cancelled_after_re_enabling(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        """The whole point: an attacker's browser must not come back to life."""
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        victim_client = _second_client(app, victim)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        logged_in_admin.post(f"/admin/users/{victim.id}/enable")

        response = victim_client.get("/backoffice/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.location

    def test_disabling_makes_the_password_unusable(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)

        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(victim.id).has_usable_password() is False

    def test_a_disabled_user_cannot_sign_in_with_their_old_password(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore
    ) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        response = _second_client(app).post(
            "/auth/login",
            data={"email": "victim@example.com", "password": "SecurePass123!"},  # pragma: allowlist secret
            follow_redirects=True,
        )

        assert b"Invalid email or password" in response.data

    def test_the_old_password_still_fails_once_the_account_is_enabled_again(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        """With the account active again, only the destroyed password stands between them."""
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")
        logged_in_admin.post(f"/admin/users/{victim.id}/enable")

        client = _second_client(app)
        response = client.post(
            "/auth/login",
            data={"email": "victim@example.com", "password": "SecurePass123!"},  # pragma: allowlist secret
            follow_redirects=True,
        )

        assert b"Invalid email or password" in response.data
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_an_admin_cannot_disable_their_own_account(
        self, logged_in_admin: FlaskClient, admin_user: User, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(f"/admin/users/{admin_user.id}/disable", follow_redirects=True)

        assert b"cannot disable your own account" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(admin_user.id).is_active is True

    def test_a_regular_user_cannot_disable_anyone(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)

        response = logged_in_user.post(f"/admin/users/{victim.id}/disable")

        assert response.status_code == 403
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(victim.id).is_active is True

    def test_disabling_an_unknown_user_says_so(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"/admin/users/{uuid.uuid4()}/disable", follow_redirects=True)

        assert b"User not found" in response.data

    def test_the_user_page_offers_disable_for_an_active_user(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        user = _seed_user(fake_store, "active@example.com", GlobalRole.USER)

        response = logged_in_admin.get(f"/admin/users/{user.id}")

        assert f"/admin/users/{user.id}/disable".encode() in response.data
        assert f"/admin/users/{user.id}/enable".encode() not in response.data

    def test_the_user_page_offers_enable_for_a_disabled_user(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        user = _seed_user(fake_store, "inactive@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_admin.get(f"/admin/users/{user.id}")

        assert f"/admin/users/{user.id}/enable".encode() in response.data
        assert f"/admin/users/{user.id}/disable".encode() not in response.data

    def test_disabling_is_confirmed_in_a_dialog(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """The Disable account button opens a dialog whose form does the POST."""
        user = _seed_user(fake_store, "active@example.com", GlobalRole.USER)

        body = logged_in_admin.get(f"/admin/users/{user.id}").get_data(as_text=True)

        assert re.search(r'id="disable-account-dialog-open"[^>]*aria-haspopup="dialog"', body, re.DOTALL)
        assert 'role="alertdialog"' in body
        assert "Disable this account?" in body
        assert "permanently removes their password" in body
        assert re.search(rf'<form method="post" action="/admin/users/{user.id}/disable">', body)

    def test_an_admin_is_not_offered_a_button_on_their_own_page(
        self, logged_in_admin: FlaskClient, admin_user: User
    ) -> None:
        response = logged_in_admin.get(f"/admin/users/{admin_user.id}")

        assert f"/admin/users/{admin_user.id}/disable".encode() not in response.data


class TestAdminEnableAccount:
    """Re-enabling has to tell the user how to get back in."""

    def test_enabling_sets_the_account_active(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).is_active is True

    def test_enabling_emails_the_user_a_route_to_a_new_password(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        assert len(email_outbox.sent) == 1
        sent = email_outbox.sent[0]
        assert sent["to"] == ["back@example.com"]
        assert "Re-enabled" in sent["subject"]
        # No token in the email - it points at the page that mints one
        assert "/auth/forgot-password" in sent["text_body"]
        assert "/auth/forgot-password" in sent["html_body"]

    def test_a_user_whose_2fa_was_cleared_is_told_to_set_it_up_again(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "twofactor@example.com", GlobalRole.USER)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.users.get(user.id).enable_totp("encrypted-secret")
            uow.commit()
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        sent = email_outbox.sent[0]
        assert "Two-factor authentication was also switched off" in sent["text_body"]
        assert "Two-factor authentication was also switched off" in sent["html_body"]

    def test_a_user_who_never_had_2fa_is_not_told_about_it(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        assert "Two-factor authentication" not in email_outbox.sent[0]["text_body"]

    def test_an_oauth_user_is_not_told_to_reset_a_password(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            oauth_user = User(
                email="oauth@example.com",
                global_role=GlobalRole.USER,
                oauth_provider="google",
                oauth_id="google123",
                is_active=False,
            )
            uow.users.add(oauth_user)
            uow.commit()
            user_id = oauth_user.id

        logged_in_admin.post(f"/admin/users/{user_id}/enable")

        assert "/auth/forgot-password" not in email_outbox.sent[0]["text_body"]
        assert "/auth/login" in email_outbox.sent[0]["text_body"]

    def test_the_admin_is_told_when_the_email_could_not_be_sent(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, email_outbox: FakeEmailAdapter
    ) -> None:
        email_outbox.succeed = False
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_admin.post(f"/admin/users/{user.id}/enable", follow_redirects=True)

        assert b"the email to the user could not be sent" in response.data

    def test_a_regular_user_cannot_enable_anyone(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_user.post(f"/admin/users/{user.id}/enable")

        assert response.status_code == 403

    def test_enabling_an_unknown_user_says_so(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"/admin/users/{uuid.uuid4()}/enable", follow_redirects=True)

        assert b"User not found" in response.data


class TestAdminNavigation:
    """Admin navigation menu visibility by role."""

    def test_admin_menu_visible_to_admin(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Site Admin" in response.data

    def test_account_menu_opens_site_admin_in_the_same_tab(self, logged_in_admin: FlaskClient) -> None:
        """Site Admin is on the backoffice design, so the account menu no longer sends it to another tab."""
        body = logged_in_admin.get("/backoffice/dashboard").get_data(as_text=True)

        link = re.search(r'<a[^>]*href="/admin/"[^>]*>', body)
        assert link is not None
        assert "target=" not in link.group(0)

    def test_admin_menu_not_visible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/backoffice/dashboard")
        assert response.status_code == 200

        data = response.data.decode()
        assert "admin/users" not in data.lower() or "Admin" not in data
