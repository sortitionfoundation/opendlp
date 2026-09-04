# ABOUTME: Component tests for the organiser role's access boundary over a FakeUnitOfWork
# ABOUTME: An organiser may create assemblies, and may reach only the assemblies they hold a role on

import uuid
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
        response = logged_in_organiser.get(
            f"/backoffice/assembly/{existing_assembly.id}",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"You don&#39;t have permission to view this assembly" in response.data
        assert existing_assembly.title.encode() not in response.data

    def test_a_second_organiser_cannot_reach_the_first_organisers_assembly(
        self, client: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        """Two organisers are isolated from each other, not only from admins."""
        with FakeUnitOfWork(store=fake_store) as uow:
            theirs = create_assembly(uow=uow, title="Not yours", created_by_user_id=organiser_user.id)
            uow.commit()

        response = _login(client, _second_organiser(fake_store)).get(
            f"/backoffice/assembly/{theirs.id}",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"You don&#39;t have permission to view this assembly" in response.data
        assert b"Not yours" not in response.data


class TestDashboardGating:
    """The create button and the Site Admin link follow capabilities, not roles."""

    def test_backoffice_dashboard_offers_create_to_an_admin(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Create New Assembly" in response.data

    def test_backoffice_dashboard_offers_create_to_an_organiser(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Create New Assembly" in response.data

    def test_backoffice_dashboard_hides_create_from_a_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert b"Create New Assembly" not in response.data
        assert b"Create Your First Assembly" not in response.data

    def test_a_user_with_nothing_is_told_what_to_do(self, logged_in_user: FlaskClient) -> None:
        """The empty state must not tell someone to create an assembly they cannot create."""
        response = logged_in_user.get("/backoffice/dashboard")
        assert b"ask an assembly manager to add you" in response.data

    def test_legacy_dashboard_offers_create_to_an_organiser(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/dashboard")
        assert response.status_code == 200
        assert b"Create Assembly" in response.data

    def test_legacy_dashboard_hides_create_from_a_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
        assert b"Create Assembly" not in response.data

    def test_site_admin_link_shown_to_an_admin(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/dashboard")
        assert b"Site Admin" in response.data

    def test_site_admin_link_hidden_from_an_organiser(self, logged_in_organiser: FlaskClient) -> None:
        """It used to be shown to organisers, and led straight to a 403."""
        response = logged_in_organiser.get("/dashboard")
        assert b"Site Admin" not in response.data

    def test_site_admin_link_hidden_from_a_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert b"Site Admin" not in response.data


class TestAssemblyManagerManagesMembers:
    """An organiser who creates an assembly must be able to add a colleague to it."""

    def _assembly_owned_by_the_organiser(self, fake_store: FakeStore, organiser_user: User) -> Assembly:
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(uow=uow, title="Theirs to run", created_by_user_id=organiser_user.id)
            uow.commit()
        return assembly

    def _colleague(self, fake_store: FakeStore) -> User:
        with FakeUnitOfWork(store=fake_store) as uow:
            user = User(
                email="colleague@example.com",
                first_name="Casey",
                last_name="Colleague",
                global_role=GlobalRole.USER,
                password_hash="hash",  # pragma: allowlist secret
                email_confirmed_at=datetime.now(UTC),
            )
            uow.users.add(user)
            uow.commit()
            return user.create_detached_copy()

    def test_the_members_page_offers_the_add_form(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)

        response = logged_in_organiser.get(f"/backoffice/assembly/{assembly.id}/members")

        assert response.status_code == 200
        assert b"Add User to Assembly" in response.data

    def test_an_exact_email_finds_the_colleague(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)
        colleague = self._colleague(fake_store)

        response = logged_in_organiser.get(f"/backoffice/assembly/{assembly.id}/members/search?q={colleague.email}")

        assert response.status_code == 200
        assert [row["id"] for row in response.get_json()] == [str(colleague.id)]

    def test_a_fragment_finds_nothing_for_a_non_admin(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        """The member-search endpoint must not be usable to enumerate accounts."""
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)
        self._colleague(fake_store)

        response = logged_in_organiser.get(f"/backoffice/assembly/{assembly.id}/members/search?q=colle")

        assert response.status_code == 200
        assert response.get_json() == []

    def test_an_admin_keeps_partial_search(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, existing_assembly: Assembly
    ) -> None:
        colleague = self._colleague(fake_store)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=colle")

        assert response.status_code == 200
        assert str(colleague.id) in [row["id"] for row in response.get_json()]

    def test_a_non_member_is_refused_the_search(
        self, logged_in_organiser: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_organiser.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=anyone")

        assert response.status_code == 403
        assert response.get_json() == []

    def test_an_unknown_assembly_looks_the_same_as_someone_elses(
        self, logged_in_organiser: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Otherwise the endpoint answers whether an assembly id exists."""
        unknown = logged_in_organiser.get(f"/backoffice/assembly/{uuid.uuid4()}/members/search?q=anyone")
        someone_elses = logged_in_organiser.get(f"/backoffice/assembly/{existing_assembly.id}/members/search?q=anyone")

        assert unknown.status_code == someone_elses.status_code == 403

    def test_an_admin_still_gets_an_honest_not_found(self, logged_in_admin: FlaskClient) -> None:
        """An admin may see every assembly, so nothing is hidden from them."""
        response = logged_in_admin.get(f"/backoffice/assembly/{uuid.uuid4()}/members/search?q=anyone")

        assert response.status_code == 404

    def test_the_organiser_can_add_the_colleague(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)
        colleague = self._colleague(fake_store)

        response = logged_in_organiser.post(
            f"/backoffice/assembly/{assembly.id}/members/add",
            data={"user_id": str(colleague.id), "role": AssemblyRole.CONFIRMATION_CALLER.name},
            follow_redirects=True,
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(colleague.id).get_assembly_role(assembly.id) == AssemblyRole.CONFIRMATION_CALLER


class TestTheAssemblyKeepsAManager:
    """An organiser must not be able to lock themselves out of their own assembly."""

    def _assembly_owned_by_the_organiser(self, fake_store: FakeStore, organiser_user: User) -> Assembly:
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(uow=uow, title="Only mine", created_by_user_id=organiser_user.id)
            uow.commit()
        return assembly

    def test_the_sole_manager_is_not_offered_the_remove_button(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)

        response = logged_in_organiser.get(f"/backoffice/assembly/{assembly.id}/members")

        assert response.status_code == 200
        assert b"Last manager" in response.data
        assert f"members/{organiser_user.id}/remove".encode() not in response.data

    def test_posting_the_removal_anyway_is_refused(
        self, logged_in_organiser: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        """Hiding the button is a courtesy; the service is what enforces it."""
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)

        response = logged_in_organiser.post(
            f"/backoffice/assembly/{assembly.id}/members/{organiser_user.id}/remove",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"must keep at least one assembly manager" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(organiser_user.id).get_assembly_role(assembly.id) == AssemblyRole.ASSEMBLY_MANAGER

    def test_an_admin_is_still_offered_the_button(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, organiser_user: User
    ) -> None:
        """An admin can put a manager back, so they are not stopped."""
        assembly = self._assembly_owned_by_the_organiser(fake_store, organiser_user)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly.id}/members")

        assert response.status_code == 200
        assert f"members/{organiser_user.id}/remove".encode() in response.data
