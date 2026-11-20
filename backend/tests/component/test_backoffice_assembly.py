# ABOUTME: Component tests for backoffice assembly routes over a FakeUnitOfWork
# ABOUTME: Drives the real backoffice Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from flask.testing import FlaskClient

from opendlp import config
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.assembly_service import create_assembly
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
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_view_assembly_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/project/{existing_assembly.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_nonexistent_assembly_redirects(self, logged_in_admin: FlaskClient) -> None:
        """Test that accessing non-existent assembly redirects with error."""
        response = logged_in_admin.get("/backoffice/project/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 302

    def test_the_panel_size_says_what_it_means(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}")

        html = response.data.decode()
        assert "Panel size" in html
        assert "Number to Select" not in html
        assert 'title="The number of people to select"' in html

    def test_view_assembly_shows_key_fields(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that assembly details shows key fields."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data
        assert existing_assembly.question.encode() in response.data

    def test_status_is_translated(self, app, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """The status badge must go through gettext. Rendering the raw
        AssemblyStatus value put an untranslatable lowercase "active" on the
        page in every language.

        LANGUAGES is set here because tests/conftest.py scrubs
        SUPPORTED_LANGUAGES, so the suite runs on config.py's default of
        en,es,fr,de and get_locale() would refuse "hu". The autouse
        _restore_shared_app_state fixture puts the config back.

        If this fails with English on the page, suspect a missing .mo before
        suspecting the catalogue: the compiled files are gitignored, so a fresh
        checkout has none and every lookup falls back to its msgid. `just
        translate-compile` - which every test recipe now depends on.
        """
        app.config["LANGUAGES"] = ["en", "hu"]
        response = logged_in_admin.get(
            f"/backoffice/project/{existing_assembly.id}",
            headers=[("Accept-Language", "hu")],
        )
        assert response.status_code == 200
        assert "Aktív" in response.get_data(as_text=True)

    def test_view_assembly_permission_denied_for_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users without assembly roles cannot view assembly details."""
        response = logged_in_user.get(f"/backoffice/project/{existing_assembly.id}")
        assert response.status_code in [302, 403, 500]

    def test_registration_qr_code_endpoint_404_without_short_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """A QR code encodes the short URL, so it 404s when no such registration page exists."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/registration/no-slug/qr-code.png")
        assert response.status_code == 404


class TestDetailsShowsWhoCreatedIt:
    """The Created row names the creator, when there is one to name."""

    def test_created_row_names_the_creator(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user: User
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}")

        assert response.status_code == 200
        assert f"By {admin_user.display_name} at".encode() in response.data

    def test_created_row_shows_the_creation_time(
        self, app, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Not just the date - the row promises a timestamp."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}")

        assert expected_timestamp(app, existing_assembly.created_at).encode() in response.data

    def test_created_row_falls_back_to_the_timestamp_alone(
        self, app, logged_in_admin: FlaskClient, assembly_without_a_creator: Assembly
    ) -> None:
        """Assemblies predating the created_by column, and those whose creator was deleted."""
        response = logged_in_admin.get(f"/backoffice/project/{assembly_without_a_creator.id}")

        assert response.status_code == 200
        assert b"By  at" not in response.data
        assert expected_timestamp(app, assembly_without_a_creator.created_at).encode() in response.data


class TestBackofficeAssemblyMembers:
    """Where the Team Members tab was, and the search the Team card's dialog uses."""

    def test_the_members_address_goes_to_the_team_card(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The Team Members tab is a card on the details page now; old links still land somewhere useful."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/members")
        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/project/{existing_assembly.id}#team")

    def test_members_page_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/project/{existing_assembly.id}/members")
        assert response.status_code == 302
        assert "login" in response.location

    def test_members_search_returns_json(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that members search endpoint returns JSON."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)


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
            f"/backoffice/project/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"removed from project" in response.data or b"success" in response.data.lower()

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
            f"/backoffice/project/{existing_assembly.id}/members/{regular_user.id}/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"permission" in response.data.lower() or b"error" in response.data.lower()

    def test_remove_user_with_invalid_user_id(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test removing non-existent user from assembly."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/members/00000000-0000-0000-0000-000000000000/remove",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"not found" in response.data.lower() or b"error" in response.data.lower()


class TestBackofficeSearchUsers:
    """Test searching users for adding to assemblies via backoffice."""

    def test_search_users_empty_query(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test search with empty term returns empty results."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/members/search?q=")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_search_users_not_accessible_to_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that regular users cannot search users."""
        response = logged_in_user.get(f"/backoffice/project/{existing_assembly.id}/members/search?q=test")
        assert response.status_code == 403

    def test_search_users_no_matches(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test search with no matching users."""
        response = logged_in_admin.get(
            f"/backoffice/project/{existing_assembly.id}/members/search?q=nonexistentuser12345"
        )
        assert response.status_code == 200
        assert response.get_json() == []


class TestBackofficeCsvDelete:
    """Test CSV delete functionality in backoffice."""

    def test_delete_targets_shows_success_message(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that successful targets deletion shows success flash message."""
        response = logged_in_admin.post(
            f"/backoffice/project/{assembly_with_targets.id}/data/delete-targets",
            data={},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"deleted" in response.data.lower() or b"success" in response.data.lower()

    def _link_a_question(self, fake_store: FakeStore, assembly: Assembly) -> RespondentFieldDefinition:
        with FakeUnitOfWork(store=fake_store) as uow:
            category = uow.target_categories.get_by_assembly_id(assembly.id)[0]
            question = RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key="gender",
                label="Your gender",
                sort_order=10,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
                target_category_id=category.id,
            )
            uow.respondent_field_definitions.add(question)
            uow.commit()
            return question

    def test_delete_targets_with_a_linked_question_asks_first(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        self._link_a_question(fake_store, assembly_with_targets)

        response = logged_in_admin.post(f"/backoffice/project/{assembly_with_targets.id}/data/delete-targets")

        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'Deleting the target "Gender" unlinks: Your gender' in body
        assert f'action="/backoffice/project/{assembly_with_targets.id}/data/delete-targets"' in body
        assert 'name="force_unlink" value="1"' in body
        assert "Break the links and delete all targets" in body
        with FakeUnitOfWork(store=fake_store) as uow:
            assert len(uow.target_categories.get_by_assembly_id(assembly_with_targets.id)) == 1

    def test_confirming_deletes_the_targets_and_unlinks_the_question(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        question = self._link_a_question(fake_store, assembly_with_targets)

        response = logged_in_admin.post(
            f"/backoffice/project/{assembly_with_targets.id}/data/delete-targets", data={"force_unlink": "1"}
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.target_categories.get_by_assembly_id(assembly_with_targets.id) == []
            assert uow.respondent_field_definitions.get(question.id).target_category_id is None


class TestBackofficeCsvViewPages:
    """Test targets view pages with CSV data source."""

    def test_view_targets_page_with_csv_source(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that targets page loads successfully for CSV data source."""
        response = logged_in_admin.get(f"/backoffice/project/{assembly_with_targets.id}/targets")
        assert response.status_code == 200
        assert b"Targets" in response.data

    def test_view_targets_page_redirects_when_not_logged_in(
        self, client: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/project/{assembly_with_targets.id}/targets")
        assert response.status_code == 302
        assert "login" in response.location


def _seed_respondents(fake_store: FakeStore, assembly_id: uuid.UUID, respondents_data: list) -> None:
    """Seed respondents with the given attributes into the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
        uow.commit()


def _targets_url(assembly_id: uuid.UUID) -> str:
    return f"/backoffice/project/{assembly_id}/targets"


HTMX = {"HX-Request": "true"}


def _dialog_panel(html: str, panel_id: str) -> str:
    """One panel of the data source dialog: from its section to the next one, or the end of the form."""
    start = html.index(f'id="{panel_id}"')
    end = html.find("</section>", start)
    return html[start:end]


class TestExampleCsvFiles:
    """In each CSV panel of the data source dialog, an example to download, read and upload."""

    @pytest.mark.parametrize(
        ("panel", "about", "filename"),
        [
            pytest.param("project-targets-panel", "Targets", "example-targets.csv", id="targets"),
            pytest.param("project-respondents-panel", "Respondents", "example-respondents.csv", id="respondents"),
        ],
    )
    def test_each_panel_links_its_own_example(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, panel: str, about: str, filename: str
    ) -> None:
        html = logged_in_admin.get(
            f"/backoffice/project/{existing_assembly.id}/data-source", headers=HTMX
        ).data.decode()

        section = _dialog_panel(html, panel)

        assert section.count("Download an example CSV") == 1
        assert f"/static/examples/{filename}" in section
        assert f'<span class="sr-only"> ({about})</span>' in section

    def test_the_targets_note_sits_with_its_link(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(
            f"/backoffice/project/{existing_assembly.id}/data-source", headers=HTMX
        ).data.decode()

        assert "set the panel size to 30" in _dialog_panel(html, "project-targets-panel")
        assert "set the panel size to 30" not in _dialog_panel(html, "project-respondents-panel")

    def test_the_example_goes_once_its_file_is_uploaded(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """With targets in place there is no upload field for an example to go with."""
        html = logged_in_admin.get(
            f"/backoffice/project/{assembly_with_targets.id}/data-source", headers=HTMX
        ).data.decode()

        assert "example-targets.csv" not in html
        assert "example-respondents.csv" in html

    @pytest.mark.parametrize(
        ("action", "filename", "field", "message"),
        [
            pytest.param("upload-targets", "example-targets.csv", "csv_file", "4 targets uploaded", id="targets"),
            pytest.param(
                "upload-respondents", "example-respondents.csv", "file", "100 respondents uploaded", id="respondents"
            ),
        ],
    )
    def test_what_a_link_serves_uploads_cleanly(
        self,
        logged_in_admin: FlaskClient,
        existing_assembly: Assembly,
        action: str,
        filename: str,
        field: str,
        message: str,
    ) -> None:
        """Download, then upload: the whole of what the links are for."""
        html = logged_in_admin.get(
            f"/backoffice/project/{existing_assembly.id}/data-source", headers=HTMX
        ).data.decode()
        href = re.search(rf'href="(/static/examples/{re.escape(filename)}[^"]*)"', html).group(1)

        downloaded = logged_in_admin.get(href)

        assert downloaded.status_code == 200
        assert downloaded.data == (config.get_static_path() / "examples" / filename).read_bytes()

        uploaded = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/{action}",
            data={field: (BytesIO(downloaded.data), filename)},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert uploaded.status_code == 200
        html = uploaded.data.decode()
        assert message in html
        assert "Some rows were not imported" not in html


class TestTargetsTabCreateTargetsFromRespondents:
    """The dialog on the Targets tab that builds categories from respondent columns."""

    def test_offers_the_respondent_columns_when_there_is_data(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        _seed_respondents(
            fake_store,
            existing_assembly.id,
            [("1", {"Gender": "Male", "Age": "18-25"}), ("2", {"Gender": "Female", "Age": "26-35"})],
        )

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert "Create from respondent data" in html
        assert 'value="Gender"' in html
        assert 'value="Age"' in html
        assert f'action="/backoffice/project/{existing_assembly.id}/targets/categories/add-from-columns"' in html

    def test_no_offer_without_respondent_data(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly
    ) -> None:
        """Nothing to build the categories from, so the button stays away."""
        html = logged_in_admin.get(_targets_url(assembly_with_targets.id)).data.decode()

        assert "Create from respondent data" not in html

    def test_offered_alongside_existing_targets(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        """A column missed the first time round can still be added later."""
        _seed_respondents(fake_store, assembly_with_targets.id, [("1", {"Region": "North"})])

        html = logged_in_admin.get(_targets_url(assembly_with_targets.id)).data.decode()

        assert "Create from respondent data" in html

    def test_a_column_already_used_as_a_target_is_shown_as_such(
        self, logged_in_admin: FlaskClient, assembly_with_targets: Assembly, fake_store: FakeStore
    ) -> None:
        """assembly_with_targets has a "Gender" category already."""
        _seed_respondents(fake_store, assembly_with_targets.id, [("1", {"Gender": "Male"})])

        html = logged_in_admin.get(_targets_url(assembly_with_targets.id)).data.decode()

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

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

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

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        disclosure = html.index("Other columns")

        assert html.index('value="Gender"') < disclosure
        assert disclosure < html.index('value="Postcode"')
