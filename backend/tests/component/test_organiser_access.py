# ABOUTME: Component tests for the organiser role's access boundary over a FakeUnitOfWork
# ABOUTME: An organiser may create assemblies, and may reach only the assemblies they hold a role on

from datetime import UTC, datetime

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.assembly_service import create_assembly
from tests.component.conftest import _login
from tests.fakes import FakeStore, FakeUnitOfWork


def _second_organiser(fake_store: FakeStore) -> User:
    """A second organiser account, so two organisers can be checked against each other."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user = User(
            email="stranger@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
            email_confirmed_at=datetime.now(UTC),
        )
        uow.users.add(user)
        uow.commit()
        return user.create_detached_copy()


class TestCreateAssemblyGate:
    """Both create-assembly routes are gated by the capability, not by a role."""

    def test_organiser_can_reach_the_legacy_create_form(self, logged_in_organiser: FlaskClient) -> None:
        assert logged_in_organiser.get("/assemblies/new").status_code == 200

    def test_organiser_can_reach_the_backoffice_create_form(self, logged_in_organiser: FlaskClient) -> None:
        assert logged_in_organiser.get("/backoffice/assembly/new").status_code == 200

    def test_user_is_refused_the_backoffice_create_form(self, logged_in_user: FlaskClient) -> None:
        """Previously a plain user got the form and a flash on submit; now the route refuses."""
        assert logged_in_user.get("/backoffice/assembly/new").status_code == 403


class TestOrganiserReachesWhatTheyCreate:
    def test_creating_an_assembly_makes_the_organiser_its_manager(
        self, logged_in_organiser: FlaskClient, organiser_user: User, fake_store: FakeStore
    ) -> None:
        response = logged_in_organiser.post(
            "/backoffice/assembly/new",
            data={"title": "My own assembly", "question": "What should we do?", "number_to_select": "0"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        with FakeUnitOfWork(store=fake_store) as uow:
            created = next(a for a in uow.assemblies.all() if a.title == "My own assembly")
            assert uow.users.get(organiser_user.id).get_assembly_role(created.id) == AssemblyRole.ASSEMBLY_MANAGER
            assert created.created_by_user_id == organiser_user.id

    def test_the_new_assembly_appears_on_their_dashboard(self, logged_in_organiser: FlaskClient) -> None:
        logged_in_organiser.post(
            "/backoffice/assembly/new",
            data={"title": "On my dashboard", "question": "Shall we?", "number_to_select": "0"},
            follow_redirects=True,
        )

        response = logged_in_organiser.get("/dashboard")
        assert b"On my dashboard" in response.data


class TestOrganiserCannotReachSomeoneElsesAssembly:
    def test_dashboard_does_not_list_it(self, logged_in_organiser: FlaskClient, existing_assembly: Assembly) -> None:
        """existing_assembly belongs to the admin, so it is not the organiser's to see."""
        response = logged_in_organiser.get("/dashboard")
        assert response.status_code == 200
        assert existing_assembly.title.encode() not in response.data

    def test_the_assembly_url_is_refused(self, logged_in_organiser: FlaskClient, existing_assembly: Assembly) -> None:
        """The route flashes and redirects rather than rendering someone else's assembly."""
        response = logged_in_organiser.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 302
        assert existing_assembly.title.encode() not in response.data

    def test_a_second_organiser_cannot_reach_the_first_organisers_assembly(
        self, client: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        """Two organisers are isolated from each other, not only from admins."""
        with FakeUnitOfWork(store=fake_store) as uow:
            theirs = create_assembly(uow=uow, title="Not yours", created_by_user_id=organiser_user.id)
            uow.commit()

        response = _login(client, _second_organiser(fake_store)).get(f"/backoffice/assembly/{theirs.id}")

        assert response.status_code == 302
        assert b"Not yours" not in response.data
