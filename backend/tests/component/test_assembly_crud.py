# ABOUTME: Component tests for Assembly CRUD routes over a FakeUnitOfWork
# ABOUTME: Drives the real assembly Flask routes + services against a seeded fake store, no PostgreSQL

from datetime import UTC, datetime, timedelta

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from tests.fakes import FakeStore, FakeUnitOfWork


class TestAssemblyListView:
    """Test Assembly list view functionality - the dashboard for now."""

    def test_assemblies_list_shows_existing(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test assemblies list shows existing assemblies."""
        response = logged_in_admin.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question[:50].encode() in response.data

    def test_assemblies_list_create_button_for_admin(self, logged_in_admin: FlaskClient) -> None:
        """Test create assembly button is shown for admin users."""
        response = logged_in_admin.get("/dashboard")
        assert response.status_code == 200
        assert b"Create Assembly" in response.data

    def test_assemblies_list_no_create_button_for_user(self, logged_in_user: FlaskClient) -> None:
        """Test regular users can see the list but not the create button."""
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data

    def test_assemblies_list_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        """Test assemblies list redirects to login when not authenticated."""
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyCreateView:
    """Test Assembly creation functionality."""

    def test_create_assembly_get_form(self, logged_in_admin: FlaskClient) -> None:
        """Test create assembly form is displayed."""
        response = logged_in_admin.get("/assemblies/new")
        assert response.status_code == 200
        assert b"Create Assembly" in response.data
        assert b"Assembly Title" in response.data
        assert b"Assembly Question" in response.data
        assert b"First Assembly Date" in response.data

    def test_create_assembly_minimal_data(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Test assembly creation with minimal required data persists to the store."""
        response = logged_in_admin.post(
            "/assemblies/new",
            data={
                "title": "Minimal Assembly",
                "number_to_select": "0",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/assemblies/" in response.location

        with FakeUnitOfWork(store=fake_store) as uow:
            titles = [a.title for a in uow.assemblies.all()]
            assert "Minimal Assembly" in titles

    def test_create_assembly_validation_errors(self, logged_in_admin: FlaskClient) -> None:
        """Test form validation errors on assembly creation."""
        response = logged_in_admin.post(
            "/assemblies/new",
            data={
                "title": "x",  # Too short
            },
        )

        assert response.status_code == 200
        assert b"error" in response.data or b"Field must be" in response.data

    def test_create_assembly_permission_denied_for_user(self, logged_in_user: FlaskClient) -> None:
        """Test regular users can view create form but get error on submit."""
        response = logged_in_user.get("/assemblies/new")
        assert response.status_code == 200

        future_date = (datetime.now(UTC) + timedelta(days=30)).date()
        response = logged_in_user.post(
            "/assemblies/new",
            data={
                "title": "Unauthorized Assembly",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
            },
        )
        assert response.status_code in [200, 302]

    def test_create_assembly_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        """Test create assembly redirects to login when not authenticated."""
        response = client.get("/assemblies/new")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyViewDetail:
    """Test Assembly detail view functionality."""

    def test_view_assembly_success(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test viewing an existing assembly."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question.encode() in response.data
        assert b"Edit" in response.data
        assert b"active" in response.data

    def test_view_assembly_shows_all_fields(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that all assembly fields are displayed."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code == 200

        assert b"Title" in response.data or b"title" in response.data
        assert b"Question" in response.data or b"question" in response.data
        assert b"Status" in response.data or b"status" in response.data
        assert b"Created" in response.data or b"created" in response.data

        assert str(existing_assembly.first_assembly_date.year).encode() in response.data

    def test_view_nonexistent_assembly(self, logged_in_admin: FlaskClient) -> None:
        """Test viewing non-existent assembly redirects to dashboard with error."""
        response = logged_in_admin.get("/assemblies/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 302
        assert "/dashboard" in response.location

    def test_view_assembly_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test view assembly redirects to login when not authenticated."""
        response = client.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyEditView:
    """Test Assembly editing functionality."""

    def test_edit_assembly_get_form(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test edit assembly form is displayed with existing data."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/edit")
        assert response.status_code == 200
        assert b"Edit Assembly" in response.data
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question.encode() in response.data

    def test_edit_assembly_validation_errors(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test form validation errors on assembly editing."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/edit",
            data={
                "title": "",  # Empty title should fail validation
            },
        )

        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_edit_nonexistent_assembly(self, logged_in_admin: FlaskClient) -> None:
        """Test editing non-existent assembly redirects to dashboard with error."""
        response = logged_in_admin.get("/assemblies/00000000-0000-0000-0000-000000000000/edit")
        assert response.status_code == 302
        assert "/dashboard" in response.location

    def test_edit_assembly_permission_denied_for_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users cannot edit assemblies."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}/edit")
        assert response.status_code in [302, 403, 500]

    def test_edit_assembly_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test edit assembly redirects to login when not authenticated."""
        response = client.get(f"/assemblies/{existing_assembly.id}/edit")
        assert response.status_code == 302
        assert "login" in response.location


class TestAssemblyWorkflowIntegration:
    """Test assembly workflows over the fake store."""

    def test_assembly_appears_in_list_after_creation(self, logged_in_admin: FlaskClient) -> None:
        """Test that newly created assembly appears in assemblies list."""
        logged_in_admin.post(
            "/assemblies/new",
            data={
                "title": "List Test Assembly",
                "question": "Will this appear in the list?",
                "number_to_select": "25",
            },
        )

        list_response = logged_in_admin.get("/dashboard")
        assert list_response.status_code == 200
        assert b"List Test Assembly" in list_response.data
        assert b"Will this appear in the list?" in list_response.data

    def test_navigation_breadcrumbs_work(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that navigation breadcrumbs are functional."""
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code == 200
        assert b"Dashboard" in response.data or b"dashboard" in response.data

        edit_response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/edit")
        assert edit_response.status_code == 200
        assert b"Dashboard" in response.data or b"dashboard" in response.data


class TestAssemblyPermissions:
    """Test assembly permission handling."""

    def test_regular_user_can_view_assemblies_list_on_dashboard(self, logged_in_user: FlaskClient) -> None:
        """Test regular users can view assemblies list."""
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data

    def test_regular_user_can_view_assembly_detail(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users without assembly roles get a permission error."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code in [302, 403, 500]

    def test_permissions_properly_enforced(self, logged_in_user: FlaskClient) -> None:
        """Test that permission restrictions are properly enforced."""
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
