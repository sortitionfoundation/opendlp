"""ABOUTME: End-to-end PostgreSQL tests for legacy assembly member-management routes
ABOUTME: Add/remove smokes, the email-adapter boundary, and db_semantics search tests; behavioural coverage lives in tests/component/"""

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.permissions import can_view_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user, grant_user_assembly_role
from tests.e2e.helpers import get_csrf_token


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


class TestAddUserToAssembly:
    """Test adding users to assemblies."""

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
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
                "csrf_token": get_csrf_token(client, f"/assemblies/{existing_assembly.id}/members"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert f"/assemblies/{existing_assembly.id}/members" in response.location

        # Reload user from database to get updated assembly_roles
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_view_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_to_assembly_sends_notification_email(
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
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.ASSEMBLY_MANAGER.name,
                "csrf_token": get_csrf_token(client, f"/assemblies/{existing_assembly.id}/members"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should show success message
        assert b"added to assembly" in response.data

        # Verify email was logged (console adapter logs emails)
        assert f"Assembly role assigned email sent to {regular_user.email}" in caplog.text
        # Verify assembly ID is in the logs
        assert str(existing_assembly.id) in caplog.text


class TestRemoveUserFromAssembly:
    """Test removing users from assemblies."""

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
            f"/assemblies/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={
                "csrf_token": get_csrf_token(client, f"/assemblies/{existing_assembly.id}/members"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert f"/assemblies/{existing_assembly.id}/members" in response.location

        # Reload user from database to verify removal
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert not can_view_assembly(refreshed_user, refreshed_assembly)


class TestSearchUsers:
    """Test searching users for adding to assemblies.

    These tests exercise search_users_not_in_assembly fragment matching and
    ordering, which depend on real database semantics.
    """

    @pytest.mark.db_semantics
    def test_search_users_returns_matching_users(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test that search returns users matching the search term."""
        login_as_admin(client, admin_user)

        response = client.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=Alice")

        assert response.status_code == 200
        assert b"Alice" in response.data or b"alice@example.com" in response.data

    @pytest.mark.db_semantics
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
        response = client.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=Alice")

        assert response.status_code == 200
        # Alice should not be in results (or results should be empty)
        data = response.data.decode()
        assert "Alice" not in data
        assert "no users match"

    @pytest.mark.db_semantics
    def test_search_users_case_insensitive(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test that search is case-insensitive."""
        login_as_admin(client, admin_user)

        response = client.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=alice")

        assert response.status_code == 200
        assert b"Alice" in response.data and b"alice@example.com" in response.data

    @pytest.mark.db_semantics
    def test_search_users_by_email(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test searching users by email address."""
        login_as_admin(client, admin_user)

        response = client.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=bob@example")

        assert response.status_code == 200
        assert b"bob@example.com" in response.data and b"Bob" in response.data

    @pytest.mark.db_semantics
    def test_search_users_by_last_name(
        self, client: FlaskClient, admin_user: User, existing_assembly: Assembly, multiple_users: list[User]
    ):
        """Test searching users by last name."""
        login_as_admin(client, admin_user)

        response = client.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=Chaplin")

        assert response.status_code == 200
        assert b"Chaplin" in response.data and b"Charlie" in response.data
