# ABOUTME: Component tests for backoffice assembly routes over a FakeUnitOfWork
# ABOUTME: Drives the real backoffice Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.permissions import can_view_assembly
from opendlp.service_layer.user_service import create_user, grant_user_assembly_role
from tests.component.conftest import expected_timestamp
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def multiple_users(fake_store: FakeStore) -> list[User]:
    """Create multiple users in the shared store for search testing."""
    users = []
    with FakeUnitOfWork(store=fake_store) as uow:
        for email, first, last in [
            ("alice@example.com", "Alice", "Anderson"),
            ("bob@example.com", "Bob", "Builder"),
            ("charlie@example.com", "Charlie", "Chaplin"),
        ]:
            user, _ = create_user(
                uow=uow,
                email=email,
                global_role=GlobalRole.USER,
                password="SecurePass123!",  # pragma: allowlist secret
                first_name=first,
                last_name=last,
                accept_data_agreement=True,
            )
            users.append(user.create_detached_copy())
    return users


@pytest.fixture
def assembly_with_targets(fake_store: FakeStore, admin_user: User) -> Assembly:
    """Create an assembly with target categories in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with Targets",
            created_by_user_id=admin_user.id,
            question="What is the question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with FakeUnitOfWork(store=fake_store) as uow:
        category = TargetCategory(assembly_id=assembly_id, name="Gender", sort_order=0)
        category.values = [
            TargetValue(value="Male", min=10, max=20),
            TargetValue(value="Female", min=10, max=20),
        ]
        uow.target_categories.add(category)
        uow.commit()

    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly_id).create_detached_copy()


class TestBackofficeAssemblyDetails:
    """Test backoffice assembly details page."""

    def test_view_assembly_details_page_loads(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that assembly details page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_view_assembly_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_nonexistent_assembly_redirects(self, logged_in_admin: FlaskClient) -> None:
        """Test that accessing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 302

    def test_view_assembly_shows_key_fields(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that assembly details shows key fields."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question.encode() in response.data

    def test_view_assembly_permission_denied_for_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users without assembly roles cannot view assembly details."""
        response = logged_in_user.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code in [302, 403, 500]

    def test_registration_qr_code_endpoint_404_without_short_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """A QR code encodes the short URL, so it 404s when no such registration page exists."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/registration/no-slug/qr-code.png")
        assert response.status_code == 404


class TestDetailsShowsWhoCreatedIt:
    """The Created row names the creator, when there is one to name."""

    def test_created_row_names_the_creator(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user: User
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")

        assert response.status_code == 200
        assert f"By {admin_user.display_name} at".encode() in response.data

    def test_created_row_shows_the_creation_time(
        self, app, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Not just the date - the row promises a timestamp."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")

        assert expected_timestamp(app, existing_assembly.created_at).encode() in response.data

    def test_created_row_falls_back_to_the_timestamp_alone(
        self, app, logged_in_admin: FlaskClient, assembly_without_a_creator: Assembly
    ) -> None:
        """Assemblies predating the created_by column, and those whose creator was deleted."""
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_without_a_creator.id}")

        assert response.status_code == 200
        assert b"By  at" not in response.data
        assert expected_timestamp(app, assembly_without_a_creator.created_at).encode() in response.data


class TestBackofficeAssemblyCreate:
    """Test backoffice assembly creation functionality."""

    def test_create_assembly_get_form(self, logged_in_admin: FlaskClient) -> None:
        """Test create assembly form is displayed."""
        response = logged_in_admin.get("/backoffice/assembly/new")
        assert response.status_code == 200
        assert b"title" in response.data.lower()
        assert b"question" in response.data.lower()

    def test_create_assembly_minimal_data(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Test assembly creation with minimal required data persists to the store."""
        response = logged_in_admin.post(
            "/backoffice/assembly/new",
            data={"title": "Minimal Assembly", "number_to_select": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/backoffice/assembly/" in response.location

        with FakeUnitOfWork(store=fake_store) as uow:
            assert "Minimal Assembly" in [a.title for a in uow.assemblies.all()]

    def test_create_assembly_validation_errors(self, logged_in_admin: FlaskClient) -> None:
        """Test form validation errors on assembly creation."""
        response = logged_in_admin.post("/backoffice/assembly/new", data={"title": "x"})
        assert response.status_code == 200
        assert b"error" in response.data or b"Field must be" in response.data

    def test_create_assembly_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        """Test create assembly redirects to login when not authenticated."""
        response = client.get("/backoffice/assembly/new")
        assert response.status_code == 302
        assert "login" in response.location

    def test_create_assembly_appears_in_dashboard(self, logged_in_admin: FlaskClient) -> None:
        """Test that newly created assembly appears in backoffice dashboard."""
        future_date = (datetime.now(UTC) + timedelta(days=30)).date()
        logged_in_admin.post(
            "/backoffice/assembly/new",
            data={
                "title": "Dashboard Visible Assembly",
                "question": "Will this appear?",
                "number_to_select": "25",
                "first_assembly_date": future_date.strftime("%Y-%m-%d"),
            },
        )

        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Dashboard Visible Assembly" in response.data


class TestDetailsTabRegistrationSection:
    """The details tab lists the assembly's registration pages read-only."""

    def _seed_page(self, fake_store, assembly_id, *, name, url_slug, short_url_slug=""):
        from opendlp.domain.registration_page import RegistrationPage  # noqa: PLC0415

        page = RegistrationPage(assembly_id=assembly_id, name=name, url_slug=url_slug, short_url_slug=short_url_slug)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.add(page)
            uow.commit()
        return page

    def test_lists_every_page_with_its_urls(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, existing_assembly: Assembly
    ) -> None:
        self._seed_page(
            fake_store, existing_assembly.id, name="English", url_slug="details-en", short_url_slug="111111"
        )
        self._seed_page(fake_store, existing_assembly.id, name="Spanish", url_slug="details-es")

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "English" in body
        assert "Spanish" in body
        assert "details-en" in body
        assert "details-es" in body
        assert "111111" in body

    def test_section_is_read_only_with_a_link_to_the_registration_tab(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")

        body = response.get_data(as_text=True)
        # No create form here any more — creation happens on the Registration tab.
        assert "registration/create" not in body
        assert f"/backoffice/assembly/{existing_assembly.id}/registration" in body


class TestBackofficeAssemblyEdit:
    """Test backoffice assembly editing functionality."""

    def test_edit_assembly_get_form(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test edit assembly form is displayed with existing data."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/edit")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_edit_assembly_ignores_posted_registration_slugs(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, existing_assembly: Assembly
    ) -> None:
        """Registration URLs are page-scoped; Edit Assembly must not touch them."""
        from opendlp.domain.registration_page import RegistrationPage  # noqa: PLC0415

        page = RegistrationPage(assembly_id=existing_assembly.id, name="English", url_slug="keep-this-slug")
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.add(page)
            uow.commit()

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/edit",
            data={
                "title": existing_assembly.title,
                "question": existing_assembly.question,
                "number_to_select": "10",
                "url_slug": "sneaky-new-slug",
                "short_url_slug": "999999",
            },
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.url_slug == "keep-this-slug"
        assert stored.short_url_slug == ""

    def test_edit_assembly_validation_errors(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test form validation errors on assembly editing."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/edit",
            data={"title": ""},
        )
        assert response.status_code == 200
        assert b"error" in response.data or b"required" in response.data

    def test_edit_nonexistent_assembly(self, logged_in_admin: FlaskClient) -> None:
        """Test editing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/assembly/00000000-0000-0000-0000-000000000000/edit")
        assert response.status_code == 302

    def test_edit_assembly_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test edit assembly redirects to login when not authenticated."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/edit")
        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeAssemblyMembers:
    """Test backoffice assembly members page."""

    def test_members_page_loads(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that the members page loads successfully."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 200
        assert b"Members" in response.data or b"Team" in response.data

    def test_members_page_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/members")
        assert response.status_code == 302
        assert "login" in response.location

    def test_members_search_returns_json(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that members search endpoint returns JSON."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)


class TestBackofficeAddUserToAssembly:
    """Test adding users to assemblies via backoffice."""

    def test_add_user_to_assembly_shows_success_message(
        self,
        logged_in_admin: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
    ) -> None:
        """Test that adding user shows success message."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={"user_id": str(regular_user.id), "role": AssemblyRole.CONFIRMATION_CALLER.name},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"success" in response.data.lower()

    def test_add_user_with_manager_role(
        self,
        logged_in_admin: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test adding a user with assembly manager role."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={"user_id": str(regular_user.id), "role": AssemblyRole.ASSEMBLY_MANAGER.name},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            refreshed_user = uow.users.get(regular_user.id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert can_view_assembly(refreshed_user, refreshed_assembly)

    def test_add_user_not_accessible_to_regular_user(
        self,
        logged_in_user: FlaskClient,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that regular users cannot add users to assemblies."""
        with FakeUnitOfWork(store=fake_store) as uow:
            other_user, _ = create_user(
                uow=uow,
                email="other@example.com",
                global_role=GlobalRole.USER,
                password="SecurePass123!",  # pragma: allowlist secret
                accept_data_agreement=True,
            )
            other_user_id = other_user.id

        response = logged_in_user.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={"user_id": str(other_user_id), "role": AssemblyRole.CONFIRMATION_CALLER.name},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"permission" in response.data.lower() or b"error" in response.data.lower()

        with FakeUnitOfWork(store=fake_store) as uow:
            refreshed_other_user = uow.users.get(other_user_id)
            refreshed_assembly = uow.assemblies.get(existing_assembly.id)
            assert not can_view_assembly(refreshed_other_user, refreshed_assembly)

    def test_add_user_with_invalid_user_id(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test adding non-existent user to assembly."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/add",
            data={
                "user_id": "00000000-0000-0000-0000-000000000000",
                "role": AssemblyRole.CONFIRMATION_CALLER.name,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"error" in response.data.lower()


class TestBackofficeRemoveUserFromAssembly:
    """Test removing users from assemblies via backoffice."""

    def test_remove_user_shows_success_message(
        self,
        logged_in_admin: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that removing user shows success message."""
        with FakeUnitOfWork(store=fake_store) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"removed from assembly" in response.data or b"success" in response.data.lower()

    def test_remove_user_not_accessible_to_regular_user(
        self,
        logged_in_user: FlaskClient,
        admin_user: User,
        regular_user: User,
        existing_assembly: Assembly,
        fake_store: FakeStore,
    ) -> None:
        """Test that regular users cannot remove users from assemblies."""
        with FakeUnitOfWork(store=fake_store) as uow:
            grant_user_assembly_role(
                uow=uow,
                user_id=regular_user.id,
                assembly_id=existing_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=admin_user,
            )

        response = logged_in_user.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"permission" in response.data.lower() or b"error" in response.data.lower()

    def test_remove_user_with_invalid_user_id(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test removing non-existent user from assembly."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/members/00000000-0000-0000-0000-000000000000/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"not found" in response.data.lower() or b"error" in response.data.lower()


class TestBackofficeSearchUsers:
    """Test searching users for adding to assemblies via backoffice."""

    def test_search_users_empty_query(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test search with empty term returns empty results."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_search_users_not_accessible_to_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that regular users cannot search users."""
        response = logged_in_user.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 403

    def test_search_users_no_matches(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test search with no matching users."""
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/members/search?q=nonexistentuser12345"
        )
        assert response.status_code == 200
        assert response.get_json() == []


class TestBackofficeCsvUpload:
    """Test CSV upload functionality in backoffice."""

    def test_upload_targets_csv_shows_success_message(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that successful targets upload shows success flash message."""
        csv_content = "feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={"csv_file": (BytesIO(csv_content.encode()), "targets.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"success" in response.data.lower() or b"uploaded" in response.data.lower()

    def test_data_tab_targets_upload_form_field_name_matches_handler(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Data-tab targets upload form must use the field name expected by the handler.

        The form posts to targets.upload_targets_csv, which validates with
        UploadTargetsCsvForm whose file field is named 'csv_file'. If the
        rendered form uses a different name (e.g. 'file'), validation silently
        fails and the user lands on the targets tab with a hidden error.
        """
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv")
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
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """A rejected upload re-renders the data page with the form and the reason.

        Redirecting instead would leave the reason in a flash message at the
        top of the page, away from the field it is about.
        """
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={},
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert b"Please select a CSV file" in response.data, (
            "Expected the FileRequired error message in the response body"
        )
        assert f'action="/backoffice/assembly/{existing_assembly.id}/targets/upload"' in html, (
            "Expected the upload form to still be on the page so the user can retry"
        )

    def test_targets_csv_upload_invalid_format_keeps_form_visible(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """When the CSV passes WTForms validation but the import service rejects it.

        The page must re-render inline (not redirect to a fresh page) so the
        error is visible alongside the form, rather than just flashing a
        message at the top of an empty page.
        """
        # Headers that don't match feature/value/min/max → InvalidSelection
        # at read_in_features() inside import_targets_from_csv.
        csv_content = "wrong,headers,here\nfoo,bar,baz"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={"csv_file": (BytesIO(csv_content.encode()), "bad.csv")},
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
        assert f'action="/backoffice/assembly/{existing_assembly.id}/targets/upload"' in html, (
            "Expected the upload form to still be on the page so the user can retry"
        )

    def test_targets_csv_multiline_error_renders_line_breaks(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Multi-line import errors must sit in a pre-line element.

        The parse failure for bad headers is one message with embedded
        newlines ("Did not find required column name ..." per column); without
        white-space: pre-line the browser collapses them to spaces.
        """
        csv_content = "wrong,headers,here\nfoo,bar,baz"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/targets/upload",
            data={"csv_file": (BytesIO(csv_content.encode()), "bad.csv")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        html = response.data.decode()
        error_items = re.findall(r"<li\b[^>]*>[^<]*CSV import failed", html)
        assert error_items, "Expected the import error inside an <li> in the error summary"
        assert all("pre-line" in tag for tag in error_items), (
            "Error <li> must have white-space: pre-line so newlines render as line breaks. Found: " + repr(error_items)
        )


class TestBackofficeCsvDelete:
    """Test CSV delete functionality in backoffice."""

    def test_delete_targets_shows_success_message(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that successful targets deletion shows success flash message."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_targets.id}/data/delete-targets",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"deleted" in response.data.lower() or b"success" in response.data.lower()


class TestBackofficeCsvViewPages:
    """Test targets view pages with CSV data source."""

    def test_view_targets_page_with_csv_source(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that targets page loads successfully for CSV data source."""
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_with_targets.id}/targets")
        assert response.status_code == 200
        assert b"Targets" in response.data

    def test_view_targets_page_redirects_when_not_logged_in(
        self, client: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{assembly_with_targets.id}/targets")
        assert response.status_code == 302
        assert "login" in response.location


def _seed_respondents(fake_store: FakeStore, assembly_id: uuid.UUID, respondents_data: list) -> None:
    """Seed respondents with the given attributes into the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
        uow.commit()


def _data_url(assembly_id: uuid.UUID) -> str:
    return f"/backoffice/assembly/{assembly_id}/data?source=csv"


class TestDataTabCreateTargetsFromRespondents:
    """The dialog on the targets card that builds categories from respondent columns."""

    def test_offers_the_respondent_columns_when_there_is_data(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _seed_respondents(
            fake_store,
            existing_assembly.id,
            [("1", {"Gender": "Male", "Age": "18-25"}), ("2", {"Gender": "Female", "Age": "26-35"})],
        )

        html = logged_in_admin.get(_data_url(existing_assembly.id)).data.decode()

        assert "Create from respondent data" in html
        assert 'value="Gender"' in html
        assert 'value="Age"' in html
        assert f'action="/backoffice/assembly/{existing_assembly.id}/targets/categories/add-from-columns"' in html

    def test_no_offer_without_respondent_data(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Nothing to build the categories from, so the button stays away."""
        html = logged_in_admin.get(_data_url(assembly_with_targets.id)).data.decode()

        assert "Create from respondent data" not in html

    def test_offered_alongside_existing_targets(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        """A column missed the first time round can still be added later."""
        _seed_respondents(fake_store, assembly_with_targets.id, [("1", {"Region": "North"})])

        html = logged_in_admin.get(_data_url(assembly_with_targets.id)).data.decode()

        assert "Delete Targets" in html
        assert "Create from respondent data" in html

    def test_a_column_already_used_as_a_target_is_shown_as_such(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        """assembly_with_targets has a "Gender" category already."""
        _seed_respondents(fake_store, assembly_with_targets.id, [("1", {"Gender": "Male"})])

        html = logged_in_admin.get(_data_url(assembly_with_targets.id)).data.decode()

        checkbox = next(
            tag for tag in re.findall(r"<input\b[^>]*>", html) if 'value="Gender"' in tag and 'name="columns"' in tag
        )
        assert "already defined" in html
        assert "disabled" in checkbox
        assert "checked" in checkbox

    def test_the_id_column_is_not_offered(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """It identifies a respondent rather than describing them."""
        _seed_respondents(fake_store, existing_assembly.id, [("1", {"Reference": "1", "Gender": "Male"})])
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = uow.assemblies.get(existing_assembly.id)
            assembly.csv = AssemblyCSV(assembly_id=existing_assembly.id, csv_id_column="Reference")
            uow.commit()

        html = logged_in_admin.get(_data_url(existing_assembly.id)).data.decode()

        assert 'value="Gender"' in html
        assert 'value="Reference"' not in html

    def test_high_cardinality_columns_sit_behind_a_disclosure(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """Twenty-odd distinct values makes for a poor target category."""
        _seed_respondents(
            fake_store,
            existing_assembly.id,
            [(str(i), {"Gender": "Male", "Postcode": f"PC{i}"}) for i in range(25)],
        )

        html = logged_in_admin.get(_data_url(existing_assembly.id)).data.decode()
        disclosure = html.index("Other columns")

        assert html.index('value="Gender"') < disclosure
        assert disclosure < html.index('value="Postcode"')
