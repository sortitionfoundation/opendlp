# ABOUTME: Component tests for legacy assembly member-management routes over a FakeUnitOfWork
# ABOUTME: Drives the real /assemblies/<id>/members routes + services against a seeded fake store, no PostgreSQL

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.user_service import create_user, grant_user_assembly_role
from tests.fakes import FakeStore, FakeUnitOfWork


def _seed_user(fake_store: FakeStore, email: str, first_name: str = "Some", last_name: str = "User") -> User:
    """Create and confirm a regular user in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=email,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name=first_name,
            last_name=last_name,
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


def _grant_role(fake_store: FakeStore, user: User, assembly: Assembly, role: AssemblyRole, current_user: User) -> None:
    """Grant an assembly role to a user via the real service."""
    with FakeUnitOfWork(store=fake_store) as uow:
        grant_user_assembly_role(
            uow=uow,
            user_id=user.id,
            assembly_id=assembly.id,
            role=role,
            current_user=current_user,
        )


class TestAddUserToAssembly:
    """Test adding users to assemblies."""

    def test_role_picker_includes_read_only_option(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test the members page renders the read-only role option."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/members")
        assert response.status_code == 200
        assert b"Read Only" in response.data
        assert AssemblyRole.READ_ONLY.name.encode() in response.data

    def test_add_user_to_assembly_with_read_only_role(
        self,
        logged_in_admin: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test adding a user with the read-only role grants view but not manage."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.READ_ONLY.name,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_view_assembly(refreshed_user, refreshed_assembly)
            assert not can_manage_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_to_assembly_shows_success_message(
        self, logged_in_admin: FlaskClient, regular_user: User, existing_assembly: Assembly
    ) -> None:
        """Test that adding a user shows a success message."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"added to assembly" in response.data and b"success" in response.data.lower()

    def test_add_user_to_assembly_with_organiser_role(
        self,
        logged_in_admin: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test adding a user with the manager role grants manage permission."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.ASSEMBLY_MANAGER.name,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_manage_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_to_assembly_not_accessible_to_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """Test that regular users cannot add users to assemblies."""
        other_user = _seed_user(fake_store, "other@example.com")

        response = logged_in_user.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(other_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"permission" in response.data.lower() and b"error" in response.data.lower()

        with FakeUnitOfWork(store=fake_store) as uow:
            refreshed_other_user = uow.users.get(other_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert not can_view_assembly(refreshed_other_user, refreshed_assembly)

    def test_add_user_to_assembly_with_invalid_user_id(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test adding a non-existent user shows an error."""
        fake_user_id = "00000000-0000-0000-0000-000000000000"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": fake_user_id,
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"invalid user" in response.data.lower() and b"error" in response.data.lower()

    def test_add_user_without_csrf_token_redirects(
        self, logged_in_admin: FlaskClient, regular_user: User, existing_assembly: Assembly
    ) -> None:
        """Test that posting without a CSRF token still redirects (CSRF disabled here)."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members",
            data={
                "user_id": str(regular_user.id),
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
            },
        )
        assert response.status_code == 302


class TestRemoveUserFromAssembly:
    """Test removing users from assemblies."""

    def test_remove_user_from_assembly_shows_success_message(
        self,
        logged_in_admin: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that removing a user shows a success message."""
        _grant_role(fake_store, regular_user, existing_assembly, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members/{regular_user.id}/remove",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"removed from assembly" in response.data and b"success" in response.data.lower()

    def test_remove_user_from_assembly_not_accessible_to_regular_user(
        self,
        logged_in_user: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that regular users cannot remove users from assemblies."""
        _grant_role(fake_store, regular_user, existing_assembly, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        response = logged_in_user.post(
            f"/assemblies/{existing_assembly.id}/members/{regular_user.id}/remove",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/assemblies/{existing_assembly.id}/members"
        assert "You don&#39;t have permission to remove users from this assembly" in response.data.decode()

    def test_remove_user_without_csrf_token_redirects(
        self,
        logged_in_admin: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that removing without a CSRF token still redirects (CSRF disabled here)."""
        _grant_role(fake_store, regular_user, existing_assembly, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members/{regular_user.id}/remove",
        )
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/members" in response.location

    def test_remove_user_from_assembly_with_invalid_user_id(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test removing a non-existent user shows an error."""
        fake_user_id = "00000000-0000-0000-0000-000000000000"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/members/{fake_user_id}/remove",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert (
            "Could not remove user from assembly: User 00000000-0000-0000-0000-000000000000 not found"
            in response.data.decode()
        )


class TestSearchUsers:
    """Test searching users for adding to assemblies."""

    def test_search_users_with_empty_search_term(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test search with an empty term returns an empty body."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=")
        assert response.status_code == 200
        assert response.data.decode() == ""

    def test_search_users_with_no_matches(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test search with no matching users shows a no-match message."""
        response = logged_in_admin.get(
            f"/assemblies/{existing_assembly.id}/search-users?user_search=nonexistentuser12345"
        )
        assert response.status_code == 200
        assert "No users match" in response.data.decode()

    def test_search_users_not_accessible_to_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that regular users cannot search users."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}/search-users?user_search=test")
        assert response.status_code == 403
