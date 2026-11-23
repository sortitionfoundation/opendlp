# ABOUTME: Component tests for archiving and unarchiving a project, over a FakeUnitOfWork
# ABOUTME: Covers the Archive button, the routes, the banner on every project tab and the Archived projects page

import re

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from opendlp.service_layer.user_service import assign_assembly_role
from tests.fakes import FakeStore, FakeUnitOfWork


def _details(assembly: Assembly) -> str:
    return f"/backoffice/project/{assembly.id}"


def _status_row(html: str) -> str:
    """The Status row's value: the tag, and the Archive button and its dialog when offered."""
    start = html.index(">Status</dt>")
    return html[start : html.index("</dd>", start)]


def _button_tags(html: str, label: str) -> list[str]:
    """The opening tag of every button whose text is the label."""
    return re.findall(rf"<button[^>]*>\s*<span>{re.escape(label)}</span>", html)


def _stored(fake_store: FakeStore, assembly: Assembly) -> Assembly:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly.id).create_detached_copy()


def _set_status(fake_store: FakeStore, assembly: Assembly, status: AssemblyStatus) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.assemblies.get(assembly.id).status = status
        uow.commit()


def _seed_page(fake_store: FakeStore, assembly: Assembly, name: str, status: RegistrationPageStatus) -> None:
    page = RegistrationPage(assembly_id=assembly.id, name=name, url_slug=name.lower(), status=status)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_pages.add(page)
        uow.commit()


def _with_role(fake_store: FakeStore, client: FlaskClient, user, assembly: Assembly, role: AssemblyRole):
    with FakeUnitOfWork(store=fake_store) as uow:
        assign_assembly_role(uow, user.id, assembly.id, role)
    return client


@pytest.fixture
def manager(fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly):
    """The regular user, signed in, managing the project alongside its creator."""
    return _with_role(fake_store, logged_in_user, regular_user, existing_assembly, AssemblyRole.ASSEMBLY_MANAGER)


@pytest.fixture
def reader(fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly):
    """The regular user, signed in, with a read-only role on the project."""
    return _with_role(fake_store, logged_in_user, regular_user, existing_assembly, AssemblyRole.READ_ONLY)


class TestArchiveButton:
    @pytest.mark.parametrize("who", ["logged_in_admin", "manager"])
    def test_an_admin_and_a_manager_get_the_button_and_its_confirmation(
        self, request, who: str, existing_assembly: Assembly
    ) -> None:
        client: FlaskClient = request.getfixturevalue(who)

        row = _status_row(client.get(_details(existing_assembly)).data.decode())

        [opener, confirm] = _button_tags(row, "Archive project")
        assert 'aria-haspopup="dialog"' in opener
        assert "disabled" not in opener
        assert 'type="submit"' in confirm
        assert "btn--danger" in confirm
        assert 'x-data="confirmDialog"' in row
        assert f'action="{_details(existing_assembly)}/archive"' in row
        assert 'name="csrf_token"' in row
        assert "Archive this project?" in row
        assert "It will no longer appear in project lists." in row
        assert "Nothing is deleted, and you can unarchive it at any time." in row
        assert _button_tags(row, "Keep it active")

    @pytest.mark.parametrize("role", [AssemblyRole.READ_ONLY, AssemblyRole.CONFIRMATION_CALLER])
    def test_other_team_members_get_the_status_alone(
        self, fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly, role
    ) -> None:
        client = _with_role(fake_store, logged_in_user, regular_user, existing_assembly, role)

        row = _status_row(client.get(_details(existing_assembly)).data.decode())

        assert "Active" in row
        assert "Archive project" not in row
        assert "/archive" not in row

    def test_a_published_page_disables_it_and_says_why(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _seed_page(fake_store, existing_assembly, "English", RegistrationPageStatus.PUBLISHED)

        row = _status_row(logged_in_admin.get(_details(existing_assembly)).data.decode())

        [button] = _button_tags(row, "Archive project")
        assert 'disabled aria-disabled="true"' in button
        assert 'aria-describedby="archive-blocked-reason"' in button
        assert 'id="archive-blocked-reason"' in row
        assert "A registration page is published. Close it before archiving the project." in row
        assert f'href="{_details(existing_assembly)}/registration"' in row
        assert "Go to Registration" in row
        assert "/archive" not in row
        assert "confirmDialog" not in row

    @pytest.mark.parametrize("status", [RegistrationPageStatus.TEST, RegistrationPageStatus.CLOSED])
    def test_test_and_closed_pages_leave_it_enabled(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, status
    ) -> None:
        _seed_page(fake_store, existing_assembly, "English", status)

        row = _status_row(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "archive-blocked-reason" not in row
        assert f'action="{_details(existing_assembly)}/archive"' in row

    def test_an_archived_project_reads_archived_in_grey_with_no_button(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _set_status(fake_store, existing_assembly, AssemblyStatus.ARCHIVED)

        row = _status_row(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "Archived" in row
        assert "var(--color-subtle-background-panels)" in row
        assert "var(--color-success-background)" not in row
        assert "Archive project" not in row


class TestArchiveRoute:
    def test_a_manager_archives_the_project(
        self, fake_store: FakeStore, manager: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = manager.post(f"{_details(existing_assembly)}/archive", follow_redirects=True)

        assert response.request.path == _details(existing_assembly)
        assert "Project archived" in response.data.decode()
        assert _stored(fake_store, existing_assembly).status == AssemblyStatus.ARCHIVED

    def test_it_redirects_to_the_project(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.post(f"{_details(existing_assembly)}/archive")

        assert response.status_code == 302
        assert response.location == _details(existing_assembly)

    def test_a_reader_is_refused(self, fake_store: FakeStore, reader: FlaskClient, existing_assembly: Assembly) -> None:
        response = reader.post(f"{_details(existing_assembly)}/archive", follow_redirects=True)

        assert response.request.path == _details(existing_assembly)
        assert "You don&#39;t have permission to archive this project" in response.data.decode()
        assert _stored(fake_store, existing_assembly).status == AssemblyStatus.ACTIVE

    def test_a_published_page_is_refused_by_name(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _seed_page(fake_store, existing_assembly, "Welsh", RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.post(f"{_details(existing_assembly)}/archive", follow_redirects=True)

        assert response.request.path == _details(existing_assembly)
        assert (
            "The registration page &#39;Welsh&#39; is published. Close it before archiving this project."
            in response.data.decode()
        )
        assert _stored(fake_store, existing_assembly).status == AssemblyStatus.ACTIVE

    def test_an_unknown_project_goes_back_to_your_projects(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(
            "/backoffice/project/00000000-0000-0000-0000-000000000000/archive", follow_redirects=True
        )

        assert response.request.path == "/backoffice/dashboard"
        assert "Project not found" in response.data.decode()

    def test_it_needs_a_sign_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        response = client.post(f"{_details(existing_assembly)}/archive")

        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestUnarchiveRoute:
    def test_a_manager_unarchives_the_project(
        self, fake_store: FakeStore, manager: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _set_status(fake_store, existing_assembly, AssemblyStatus.ARCHIVED)

        response = manager.post(f"{_details(existing_assembly)}/unarchive", follow_redirects=True)

        assert response.request.path == _details(existing_assembly)
        assert "Project unarchived" in response.data.decode()
        assert _stored(fake_store, existing_assembly).status == AssemblyStatus.ACTIVE

    def test_a_reader_is_refused(self, fake_store: FakeStore, reader: FlaskClient, existing_assembly: Assembly) -> None:
        _set_status(fake_store, existing_assembly, AssemblyStatus.ARCHIVED)

        response = reader.post(f"{_details(existing_assembly)}/unarchive", follow_redirects=True)

        assert response.request.path == _details(existing_assembly)
        assert "You don&#39;t have permission to unarchive this project" in response.data.decode()
        assert _stored(fake_store, existing_assembly).status == AssemblyStatus.ARCHIVED

    def test_an_unknown_project_goes_back_to_your_projects(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(
            "/backoffice/project/00000000-0000-0000-0000-000000000000/unarchive", follow_redirects=True
        )

        assert response.request.path == "/backoffice/dashboard"
        assert "Project not found" in response.data.decode()


# Every page that renders the project tabs. "{editor}" is the registration
# editor, which opens on the page the archived_project fixture gives the project.
PROJECT_TABS = [
    "",
    "/dashboard",
    "/targets",
    "/registration",
    "/registration/{editor}",
    "/respondent-schema",
    "/target-sources",
    "/respondents",
    "/selection",
]


@pytest.fixture
def archived_project(fake_store: FakeStore, admin_user, existing_assembly: Assembly) -> tuple[Assembly, str]:
    """The existing project, archived, and the url_slug of a registration page it has."""
    with FakeUnitOfWork(store=fake_store) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id, name="English")
    _set_status(fake_store, existing_assembly, AssemblyStatus.ARCHIVED)
    return existing_assembly, page.url_slug


def _tab_url(project: tuple[Assembly, str], tab: str) -> str:
    assembly, url_slug = project
    return _details(assembly) + tab.format(editor=url_slug)


class TestArchivedBanner:
    @pytest.mark.parametrize("tab", PROJECT_TABS)
    def test_a_manager_sees_it_with_the_unarchive_button_on_every_tab(
        self, manager: FlaskClient, archived_project: tuple[Assembly, str], tab: str
    ) -> None:
        response = manager.get(_tab_url(archived_project, tab))

        assert response.status_code == 200
        html = response.data.decode()
        assert html.count('id="archived-banner"') == 1
        assert "This project is archived. It doesn't appear in project lists." in html
        assert f'action="{_details(archived_project[0])}/unarchive"' in html
        assert _button_tags(html, "Unarchive project")

    @pytest.mark.parametrize("tab", PROJECT_TABS)
    def test_a_reader_sees_it_without_the_button(
        self, reader: FlaskClient, archived_project: tuple[Assembly, str], tab: str
    ) -> None:
        response = reader.get(_tab_url(archived_project, tab))

        assert response.status_code == 200
        html = response.data.decode()
        assert html.count('id="archived-banner"') == 1
        assert "/unarchive" not in html
        assert "Unarchive project" not in html

    def test_it_is_information_not_a_warning(
        self, manager: FlaskClient, archived_project: tuple[Assembly, str]
    ) -> None:
        html = manager.get(_details(archived_project[0])).data.decode()

        banner_start = html.rindex("<div", 0, html.index('id="archived-banner"'))
        banner_tag = html[banner_start : html.index(">", banner_start)]
        assert "var(--color-info-100)" in banner_tag
        assert "var(--color-warning-100)" not in banner_tag

    @pytest.mark.parametrize("tab", ["", "/targets", "/registration", "/respondents", "/selection"])
    def test_an_active_project_has_none(self, manager: FlaskClient, existing_assembly: Assembly, tab: str) -> None:
        html = manager.get(f"{_details(existing_assembly)}{tab}").data.decode()

        assert "archived-banner" not in html
        assert "This project is archived." not in html


ARCHIVED_PAGE = "/backoffice/projects/archived"


def _project(fake_store: FakeStore, title: str, status: AssemblyStatus = AssemblyStatus.ARCHIVED) -> Assembly:
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = Assembly(title=title, question=f"What is {title} for?", status=status)
        uow.assemblies.add(assembly)
        uow.commit()
        return assembly.create_detached_copy()


class TestArchivedProjectsPage:
    def test_an_admin_sees_every_archived_project_and_no_active_one(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient
    ) -> None:
        jury = _project(fake_store, "Climate Jury")
        panel = _project(fake_store, "Health Panel")
        active = _project(fake_store, "Transport Assembly", status=AssemblyStatus.ACTIVE)

        response = logged_in_admin.get(ARCHIVED_PAGE)

        assert response.status_code == 200
        html = response.data.decode()
        assert "Archived projects" in html
        assert f'href="{_details(jury)}"' in html
        assert f'href="{_details(panel)}"' in html
        assert f'id="assembly-{active.id}"' not in html
        assert html.count(">Archived</strong>") == 2

    def test_anyone_else_sees_only_their_own(
        self, fake_store: FakeStore, logged_in_user: FlaskClient, regular_user
    ) -> None:
        theirs = _project(fake_store, "Climate Jury")
        someone_elses = _project(fake_store, "Health Panel")
        _with_role(fake_store, logged_in_user, regular_user, theirs, AssemblyRole.READ_ONLY)

        html = logged_in_user.get(ARCHIVED_PAGE).data.decode()

        assert f'id="assembly-{theirs.id}"' in html
        assert f'id="assembly-{someone_elses.id}"' not in html

    def test_the_search_narrows_by_title_and_keeps_what_was_typed(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient
    ) -> None:
        jury = _project(fake_store, "Climate Jury")
        panel = _project(fake_store, "Health Panel")

        html = logged_in_admin.get(f"{ARCHIVED_PAGE}?q=+jury+").data.decode()

        assert f'id="assembly-{jury.id}"' in html
        assert f'id="assembly-{panel.id}"' not in html
        assert 'role="search"' in html
        assert 'method="get"' in html
        assert 'type="search"' in html
        assert 'name="q"' in html
        assert 'value="jury"' in html

    def test_a_search_that_finds_nothing_says_so_and_offers_them_all(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient
    ) -> None:
        _project(fake_store, "Climate Jury")

        html = logged_in_admin.get(f"{ARCHIVED_PAGE}?q=zebra").data.decode()

        assert "No archived projects match 'zebra'" in html
        assert f'href="{ARCHIVED_PAGE}"' in html
        assert "Show all archived projects" in html

    def test_what_was_searched_for_is_shown_as_text(self, logged_in_admin: FlaskClient) -> None:
        html = logged_in_admin.get(f"{ARCHIVED_PAGE}?q=<b>bold</b>").data.decode()

        assert "<b>bold</b>" not in html
        assert "No archived projects match '&lt;b&gt;bold&lt;/b&gt;'" in html

    def test_with_nothing_archived_it_says_so(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        html = logged_in_admin.get(ARCHIVED_PAGE).data.decode()

        assert 'id="no-archived-projects-card"' in html
        assert "No archived projects" in html
        assert f'id="assembly-{existing_assembly.id}"' not in html

    def test_it_leads_back_to_your_projects(self, logged_in_admin: FlaskClient) -> None:
        html = logged_in_admin.get(ARCHIVED_PAGE).data.decode()

        assert 'href="/backoffice/dashboard"' in html
        assert 'aria-label="Back to Your projects"' in html

    def test_it_needs_a_sign_in(self, client: FlaskClient) -> None:
        response = client.get(ARCHIVED_PAGE)

        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_an_unexpected_error_still_renders_the_page(
        self, monkeypatch: pytest.MonkeyPatch, logged_in_admin: FlaskClient
    ) -> None:
        def broken(*_args, **_kwargs):
            raise RuntimeError("the database went away")

        monkeypatch.setattr("opendlp.entrypoints.blueprints.backoffice.get_user_archived_assemblies", broken)

        response = logged_in_admin.get(ARCHIVED_PAGE)

        assert response.status_code == 500
        assert "No archived projects" in response.data.decode()


class TestYourProjects:
    def test_it_links_to_the_archived_projects(self, logged_in_user: FlaskClient) -> None:
        html = logged_in_user.get("/backoffice/dashboard").data.decode()

        assert f'href="{ARCHIVED_PAGE}"' in html
        assert "Archived projects" in html

    def test_an_archived_project_leaves_it(self, fake_store: FakeStore, logged_in_admin: FlaskClient) -> None:
        archived = _project(fake_store, "Climate Jury")
        active = _project(fake_store, "Health Panel", status=AssemblyStatus.ACTIVE)

        html = logged_in_admin.get("/backoffice/dashboard").data.decode()

        assert f'id="assembly-{active.id}"' in html
        assert f'id="assembly-{archived.id}"' not in html
        assert ">Active</strong>" not in html
