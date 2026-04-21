"""ABOUTME: End-to-end tests for backoffice assembly CRUD and member management
ABOUTME: Tests assembly creation, viewing, editing, and user management through the backoffice interface"""

import re
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user, grant_user_assembly_role
from tests.e2e.helpers import get_csrf_token


class TestBackofficeAssemblyDetails:
    """Test backoffice assembly details page."""

    def test_view_assembly_details_page_loads(self, logged_in_admin, existing_assembly):
        """Test that assembly details page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_view_assembly_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_nonexistent_assembly_redirects(self, logged_in_admin):
        """Test that accessing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 302  # Should redirect to dashboard with error

    def test_view_assembly_shows_key_fields(self, logged_in_admin, existing_assembly):
        """Test that assembly details shows key fields."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200

        # Should display assembly title and question
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question.encode() in response.data

    def test_view_assembly_permission_denied_for_regular_user(self, logged_in_user, existing_assembly):
        """Test regular users without assembly roles cannot view assembly details."""
        response = logged_in_user.get(f"/backoffice/assembly/{existing_assembly.id}")
        # Regular users without assembly roles should get permission error
        assert response.status_code in [302, 403, 500]


class TestBackofficeAssemblyCreate:
    """Test backoffice assembly creation functionality."""

    def test_create_assembly_get_form(self, logged_in_admin):
        """Test create assembly form is displayed."""
        response = logged_in_admin.get("/backoffice/assembly/new")
        assert response.status_code == 200
        assert b"title" in response.data.lower()
        assert b"question" in response.data.lower()

    def test_create_assembly_success(self, logged_in_admin):
        """Test successful assembly creation."""
        future_date = (datetime.now(UTC) + timedelta(days=30)).date()
        response = logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "New Backoffice Assembly",
                "question": "What should we discuss in this assembly?",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "50",
                "csrf_token": get_csrf_token(logged_in_admin, "/backoffice/assembly/new"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert "/backoffice/assembly/" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("created successfully" in msg for msg in flash_messages)

    def test_create_assembly_minimal_data(self, logged_in_admin):
        """Test assembly creation with minimal required data."""
        response = logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "Minimal Assembly",
                "number_to_select": "0",
                "csrf_token": get_csrf_token(logged_in_admin, "/backoffice/assembly/new"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/backoffice/assembly/" in response.location

    def test_create_assembly_validation_errors(self, logged_in_admin):
        """Test form validation errors on assembly creation."""
        response = logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "x",  # Too short
                "csrf_token": get_csrf_token(logged_in_admin, "/backoffice/assembly/new"),
            },
        )

        # Should return form with validation errors
        assert response.status_code == 200
        assert b"error" in response.data or b"Field must be" in response.data

    def test_create_assembly_redirects_when_not_logged_in(self, client):
        """Test create assembly redirects to login when not authenticated."""
        response = client.get("/backoffice/assembly/new")
        assert response.status_code == 302
        assert "login" in response.location

    def test_create_assembly_appears_in_dashboard(self, logged_in_admin):
        """Test that newly created assembly appears in backoffice dashboard."""
        future_date = (datetime.now(UTC) + timedelta(days=30)).date()
        logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "Dashboard Visible Assembly",
                "question": "Will this appear?",
                "number_to_select": "25",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "csrf_token": get_csrf_token(logged_in_admin, "/backoffice/assembly/new"),
            },
        )

        # Check it appears in dashboard
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Dashboard Visible Assembly" in response.data


class TestBackofficeAssemblyEdit:
    """Test backoffice assembly editing functionality."""

    def test_edit_assembly_get_form(self, logged_in_admin, existing_assembly):
        """Test edit assembly form is displayed with existing data."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/edit")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_edit_assembly_success(self, logged_in_admin, existing_assembly):
        """Test successful assembly editing."""
        updated_title = "Updated Backoffice Assembly"
        updated_question = "What is the updated question?"
        future_date = (datetime.now(UTC) + timedelta(days=45)).date()

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/edit",
            data={
                "title": updated_title,
                "question": updated_question,
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "100",
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/edit"),
            },
            follow_redirects=False,
        )

        # Should redirect to view assembly page
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}" in response.location

        # Check flash message
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("updated successfully" in msg for msg in flash_messages)

    def test_edit_assembly_validation_errors(self, logged_in_admin, existing_assembly):
        """Test form validation errors on assembly editing."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/edit",
            data={
                "title": "",  # Empty title should fail validation
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/edit"),
            },
        )

        # Should return form with validation errors
        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_edit_nonexistent_assembly(self, logged_in_admin):
        """Test editing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000/edit")
        # Should redirect to dashboard with error message
        assert response.status_code == 302

    def test_edit_assembly_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test edit assembly redirects to login when not authenticated."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/edit")
        assert response.status_code == 302
        assert "login" in response.location

    def test_complete_create_view_edit_workflow(self, logged_in_admin):
        """Test complete workflow: create -> view -> edit assembly."""
        # Step 1: Create assembly
        future_date = (datetime.now(UTC) + timedelta(days=60)).date()
        create_response = logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "Workflow Test Assembly",
                "question": "What should we test?",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
                "number_to_select": "30",
                "csrf_token": get_csrf_token(logged_in_admin, "/backoffice/assembly/new"),
            },
            follow_redirects=False,
        )

        assert create_response.status_code == 302
        assembly_url = create_response.location

        # Step 2: View the created assembly
        view_response = logged_in_admin.get(assembly_url)
        assert view_response.status_code == 200
        assert b"Workflow Test Assembly" in view_response.data

        # Step 3: Extract assembly_id and edit
        assembly_id = assembly_url.rstrip("/").split("/")[-1]
        updated_date = (datetime.now(UTC) + timedelta(days=90)).date()
        edit_response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/edit",
            data={
                "title": "Updated Workflow Test Assembly",
                "question": "What should we test after update?",
                "first_assembly_date": updated_date.strftime("%Y-%m-%d"),
                "number_to_select": "40",
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{assembly_id}/edit"),
            },
            follow_redirects=False,
        )

        assert edit_response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}" in edit_response.location

        # Step 4: Verify the update
        final_view = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}")
        assert final_view.status_code == 200
        assert b"Updated Workflow Test Assembly" in final_view.data


class TestBackofficeAssemblyMembers:
    """Test backoffice assembly members page."""

    def test_members_page_loads(self, logged_in_admin, existing_assembly):
        """Test that the members page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 200
        assert b"Members" in response.data or b"Team" in response.data

    def test_members_page_redirects_when_not_logged_in(self, client, existing_assembly):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 302
        assert "login" in response.location

    def test_members_search_returns_json(self, logged_in_admin, existing_assembly):
        """Test that members search endpoint returns JSON."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)


@pytest.fixture
def multiple_users(postgres_session_factory):
    """Create multiple users for search testing."""
    users = []
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user, _ = create_user(
            uow,
            email="alice@example.com",
            global_role=GlobalRole.USER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Alice",
            last_name="Anderson",
            accept_data_agreement=True,
        )
        users.append(user)
        user, _ = create_user(
            uow,
            email="bob@example.com",
            global_role=GlobalRole.USER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Bob",
            last_name="Builder",
            accept_data_agreement=True,
        )
        users.append(user)
        user, _ = create_user(
            uow,
            email="charlie@example.com",
            global_role=GlobalRole.USER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Charlie",
            last_name="Chaplin",
            accept_data_agreement=True,
        )
        users.append(user)
    return users


def login_as_admin(client: FlaskClient, admin_user: User) -> None:
    """Helper function to login as admin."""
    client.post(
        "/auth/login",
        data={
            "email": admin_user.email,
            "password": "adminpass123",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/auth/login"),
        },
    )


class TestBackofficeAddUserToAssembly:
    """Test adding users to assemblies via backoffice."""

    def test_add_user_to_assembly_success(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test successfully adding a user to an assembly."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert f"/backoffice/assembly/{existing_assembly.id}/members" in response.location

        # Reload user from database to get updated assembly_roles
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_view_assembly(refreshed_user, refreshed_assembly)
            assert not can_manage_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_to_assembly_shows_success_message(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
    ):
        """Test that adding user shows success message."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"success" in response.data.lower()

    def test_add_user_with_manager_role(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test adding a user with assembly manager role."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.ASSEMBLY_MANAGER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        # Reload user from database to get updated assembly_roles
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_manage_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_not_accessible_to_regular_user(
        self, client: FlaskClient, regular_user: User, existing_assembly: Assembly, postgres_session_factory
    ):
        """Test that regular users cannot add users to assemblies."""
        # Create another user to try to add
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            other_user, _ = create_user(
                uow,
                email="other@example.com",
                global_role=GlobalRole.USER,
                password="SecurePass123!",  # pragma: allowlist secret
                accept_data_agreement=True,
            )

        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": str(other_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        # Should show error message or be redirected
        assert response.status_code == 200
        assert b"permission" in response.data.lower() or b"error" in response.data.lower()

        # Reload user from database to verify they were NOT added
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_other_user = uow.users.get(other_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert not can_view_assembly(refreshed_other_user, refreshed_assembly)

    def test_add_user_with_invalid_user_id(self, client: FlaskClient, admin_user: User, existing_assembly: Assembly):
        """Test adding non-existent user to assembly."""
        login_as_admin(client, admin_user)

        fake_user_id = "00000000-0000-0000-0000-000000000000"
        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": fake_user_id,
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        # Should show error
        assert response.status_code == 200
        assert b"error" in response.data.lower()

    def test_add_user_sends_notification_email(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        caplog,
    ):
        """Test that adding user to assembly sends notification email."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.ASSEMBLY_MANAGER.name,
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify email was logged (console adapter logs emails)
        assert f"Assembly role assigned email sent to {regular_user.email}" in caplog.text


class TestBackofficeRemoveUserFromAssembly:
    """Test removing users from assemblies via backoffice."""

    def test_remove_user_from_assembly_success(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test successfully removing a user from an assembly."""
        login_as_admin(client, admin_user)

        # First add user to assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert f"/backoffice/assembly/{existing_assembly.id}/members" in response.location

        # Reload user from database to verify removal
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert not can_view_assembly(refreshed_user, refreshed_assembly)

    def test_remove_user_shows_success_message(
        self,
        client: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test that removing user shows success message."""
        login_as_admin(client, admin_user)

        # First add user to assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"removed from assembly" in response.data or b"success" in response.data.lower()

    def test_remove_user_not_accessible_to_regular_user(
        self,
        client: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
        admin_user: User,
        postgres_session_factory,
    ):
        """Test that regular users cannot remove users from assemblies."""
        # First add user to assembly
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        # Should show permission error
        assert response.status_code == 200
        assert b"permission" in response.data.lower() or b"error" in response.data.lower()

    def test_remove_user_with_invalid_user_id(self, client: FlaskClient, admin_user: User, existing_assembly: Assembly):
        """Test removing non-existent user from assembly."""
        login_as_admin(client, admin_user)

        fake_user_id = "00000000-0000-0000-0000-000000000000"
        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{fake_user_id}/remove",
            data={
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        # Should show error
        assert response.status_code == 200
        assert b"not found" in response.data.lower() or b"error" in response.data.lower()


class TestBackofficeSearchUsers:
    """Test searching users for adding to assemblies via backoffice."""

    def test_search_users_returns_matching_users(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test that search returns users matching the search term."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=Alice")

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(
            "alice" in item.get("label", "").lower() or "alice" in item.get("sublabel", "").lower() for item in data
        )

    def test_search_users_excludes_users_already_in_assembly(
        self,
        client: FlaskClient,
        admin_user: User,
        existing_assembly: Assembly,
        multiple_users: list[User],
        postgres_session_factory,
    ):
        """Test that search excludes users already in assembly."""
        login_as_admin(client, admin_user)

        # Add Alice to assembly
        alice = multiple_users[0]
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=alice.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        # Search for Alice - should not appear
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=Alice")

        assert response.status_code == 200
        data = response.get_json()
        # Alice should not be in results
        assert not any(
            "alice" in item.get("label", "").lower() or "alice" in item.get("sublabel", "").lower() for item in data
        )

    def test_search_users_empty_query(self, client: FlaskClient, admin_user: User, existing_assembly: Assembly):
        """Test search with empty term returns empty results."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=")

        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_search_users_case_insensitive(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test that search is case-insensitive."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=alice")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1

    def test_search_users_by_email(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test searching users by email address."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=bob@example")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1
        assert any("bob" in item.get("label", "").lower() or "bob" in item.get("sublabel", "").lower() for item in data)

    def test_search_users_by_last_name(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test searching users by last name."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=Chaplin")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1

    def test_search_users_not_accessible_to_regular_user(
        self, client: FlaskClient, regular_user: User, existing_assembly: Assembly
    ):
        """Test that regular users cannot search users."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=test")

        # Should be forbidden
        assert response.status_code == 403

    def test_search_users_no_matches(self, client: FlaskClient, admin_user: User, existing_assembly: Assembly):
        """Test search with no matching users."""
        login_as_admin(client, admin_user)

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=nonexistentuser12345")

        assert response.status_code == 200
        data = response.get_json()
        assert data == []


class TestBackofficeCsvUpload:
    """Test CSV upload functionality in backoffice."""

    def test_upload_targets_csv_success(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test successfully uploading a targets CSV file."""
        # CSV format must use: feature,value,min,max (matching sortition-algorithms library)
        csv_content = "feature,value,min,max\nGender,Male,10,20\nGender,Female,10,20\nAge,18-30,5,15\nAge,31-50,5,15"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (BytesIO(csv_content.encode()), "targets.csv"),
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/targets" in response.location

        # Verify targets were created
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            categories = uow.target_categories.get_by_assembly_id(existing_assembly.id)
            assert len(categories) == 2  # Gender and Age
            category_names = {c.name for c in categories}
            assert category_names == {"Gender", "Age"}

    def test_upload_targets_csv_shows_success_message(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """Test that successful targets upload shows success flash message."""
        # CSV format must use: feature,value,min,max (matching sortition-algorithms library)
        csv_content = "feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (BytesIO(csv_content.encode()), "targets.csv"),
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"success" in response.data.lower() or b"uploaded" in response.data.lower()

    def test_data_tab_targets_upload_form_field_name_matches_handler(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """Data-tab targets upload form must use the field name expected by the handler.

        The form posts to targets.upload_targets_csv, which validates with
        UploadTargetsCsvForm whose file field is named 'csv_file'. If the
        rendered form uses a different name (e.g. 'file'), validation silently
        fails and the user lands on the targets tab with a hidden error.
        """
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/data?source=csv",
        )
        assert response.status_code == 200
        html = response.data.decode()

        target_action = f"/backoffice/assembly/{existing_assembly.id}/targets/upload"
        form_pattern = re.compile(
            r'<form[^>]*action="' + re.escape(target_action) + r'"[^>]*>(.*?)</form>',
            re.DOTALL,
        )
        match = form_pattern.search(html)
        assert match, f"No form posting to {target_action} found in data tab"
        form_body = match.group(1)
        assert 'name="csv_file"' in form_body, (
            "Targets upload form on data tab must use input name 'csv_file' "
            "to match UploadTargetsCsvForm. Got form body:\n" + form_body[:400]
        )

    def test_targets_csv_upload_error_keeps_form_visible(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """When CSV upload validation fails, the <details> wrapping the form must be open.

        The CSV import form lives in a <details> block that defaults to closed.
        On validation failure the page re-renders inline with errors, but if
        <details> stays closed those errors are hidden — confusing the user.
        """
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={"csrf_token": "x"},
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert b"Please select a CSV file" in response.data, (
            "Expected the FileRequired error message in the response body"
        )

        details_tags = re.findall(r"<details\b[^>]*>", html)

        def has_open_attribute(tag: str) -> bool:
            # Strip quoted attribute values so we don't match 'open' inside
            # things like x-data="{ open: false }".
            stripped = re.sub(r'"[^"]*"|\'[^\']*\'', '""', tag)
            return re.search(r"\bopen\b", stripped) is not None

        assert any(has_open_attribute(tag) for tag in details_tags), (
            "Expected the CSV import <details> to be open after a validation "
            "error so the user can see it. Found: " + repr(details_tags)
        )

    def test_targets_csv_upload_invalid_format_keeps_form_visible(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """When the CSV passes WTForms validation but the import service rejects it.

        The page must re-render inline (not redirect to a fresh page) so the
        <details> stays open with the error visible alongside the form, rather
        than just flashing a message at the top of an empty page.
        """
        # Headers that don't match feature/value/min/max → InvalidSelection
        # at read_in_features() inside import_targets_from_csv.
        csv_content = "wrong,headers,here\nfoo,bar,baz"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (BytesIO(csv_content.encode()), "bad.csv"),
                "csrf_token": "x",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 200, (
            f"Expected inline re-render (200); got {response.status_code} location={response.location!r}"
        )

        html = response.data.decode()
        assert b"CSV import failed" in response.data or b"Failed to parse CSV" in response.data, (
            "Expected the import error message in the response body"
        )

        details_tags = re.findall(r"<details\b[^>]*>", html)

        def has_open_attribute(tag: str) -> bool:
            stripped = re.sub(r'"[^"]*"|\'[^\']*\'', '""', tag)
            return re.search(r"\bopen\b", stripped) is not None

        assert any(has_open_attribute(tag) for tag in details_tags), (
            "Expected the CSV import <details> to be open after an import "
            "error so the user can see it. Found: " + repr(details_tags)
        )


@pytest.fixture
def assembly_with_targets(postgres_session_factory, admin_user):
    """Create an assembly with target categories for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with Targets",
            created_by_user_id=admin_user.id,
            question="What is the question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    # Add target categories
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        category = TargetCategory(
            assembly_id=assembly_id,
            name="Gender",
            sort_order=0,
        )
        category.values = [
            TargetValue(value="Male", min=10, max=20),
            TargetValue(value="Female", min=10, max=20),
        ]
        uow.target_categories.add(category)
        uow.commit()

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = uow.assemblies.get(assembly_id)
        return assembly.create_detached_copy()


class TestBackofficeCsvDelete:
    """Test CSV delete functionality in backoffice."""

    def test_delete_targets_success(
        self,
        logged_in_admin,
        assembly_with_targets: Assembly,
        postgres_session_factory,
    ):
        """Test successfully deleting targets for an assembly."""
        # Verify targets exist before deletion
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            categories = uow.target_categories.get_by_assembly_id(assembly_with_targets.id)
            assert len(categories) > 0

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_targets.id}/data/delete-targets",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly_with_targets.id}/data?source=csv"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "source=csv" in response.location

        # Verify targets were deleted
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            categories = uow.target_categories.get_by_assembly_id(assembly_with_targets.id)
            assert len(categories) == 0

    def test_delete_targets_shows_success_message(
        self,
        logged_in_admin,
        assembly_with_targets: Assembly,
    ):
        """Test that successful targets deletion shows success flash message."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_targets.id}/data/delete-targets",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly_with_targets.id}/data?source=csv"
                ),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"deleted" in response.data.lower() or b"success" in response.data.lower()


class TestBackofficeCsvViewPages:
    """Test targets view pages with CSV data source."""

    def test_view_targets_page_with_csv_source(
        self,
        logged_in_admin,
        assembly_with_targets: Assembly,
    ):
        """Test that targets page loads successfully for CSV data source."""
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_with_targets.id}/targets")

        assert response.status_code == 200
        # Should see the page title containing "Targets"
        assert b"Targets" in response.data

    def test_view_targets_page_redirects_when_not_logged_in(
        self,
        client,
        assembly_with_targets: Assembly,
    ):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{assembly_with_targets.id}/targets")

        assert response.status_code == 302
        assert "login" in response.location
