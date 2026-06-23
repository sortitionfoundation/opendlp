"""ABOUTME: End-to-end PostgreSQL smokes + DB-semantics for backoffice assembly routes
ABOUTME: Behavioural coverage (validation, permissions, render, branches) lives in tests/component/"""

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
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
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

    def test_registration_url_copy_widget_uses_csp_safe_data_attributes(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """The copy-URL button must drive the clipboard through utilities.js
        data attributes, not an inline navigator.clipboard expression — the
        latter fails silently under the CSP-safe Alpine build (`@alpinejs/csp`)."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200
        assert b"Registration Page Details" in response.data
        assert b"data-copy-text=" in response.data
        assert b'data-copy-feedback="inline"' in response.data
        # No inline JS expression — incompatible with the CSP-safe build.
        assert b"navigator.clipboard.writeText(" not in response.data

    def test_registration_qr_code_endpoint_returns_png(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """GET .../registration/qr-code.png returns a PNG attachment for the short URL."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/registration/qr-code.png")
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        assert response.data.startswith(b"\x89PNG\r\n\x1a\n")
        assert "attachment" in response.headers.get("Content-Disposition", "")


class TestBackofficeAssemblyCreate:
    """Test backoffice assembly creation functionality."""

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


class TestBackofficeAssemblyEdit:
    """Test backoffice assembly editing functionality."""

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


@pytest.mark.db_semantics
class TestBackofficeSearchUsers:
    """Test searching users for adding to assemblies via backoffice (search_users_not_in_assembly)."""

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
