"""ABOUTME: End-to-end tests for the `opendlp projects` CLI commands against a real database
ABOUTME: Drives the Click commands through CliRunner, as an admin at a shell would"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp.adapters.database import start_mappers
from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml, RegistrationPageStatus
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentStatus
from opendlp.entrypoints.cli import cli
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture(autouse=True)
def setup_mappers():
    start_mappers()


class TestProjectsList:
    @pytest.fixture
    def projects(self, postgres_session_factory):
        now = datetime.now(UTC)
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            member = User(email="member@example.com", global_role=GlobalRole.USER, password_hash="hash")
            uow.users.add(member)
            empty = Assembly(title="Empty project", created_at=now - timedelta(days=3))
            database = Assembly(title="Database project", created_at=now - timedelta(days=2))
            archived = Assembly(title="Archived project", created_at=now - timedelta(days=1))
            archived.archive()
            for assembly in (empty, database, archived):
                uow.assemblies.add(assembly)
            uow.flush()
            uow.respondents.add(Respondent(assembly_id=database.id, external_id="r1"))
            uow.user_assembly_roles.add(
                UserAssemblyRole(user_id=member.id, assembly_id=empty.id, role=AssemblyRole.READ_ONLY)
            )
            uow.commit()
            return {"empty": empty.id, "database": database.id, "archived": archived.id}

    def test_one_tab_separated_line_per_active_project_newest_first(self, projects, cli_with_session_factory):
        result = cli_with_session_factory(cli, ["projects", "list"])

        assert result.exit_code == 0, result.output
        assert result.output.splitlines() == [
            f"{projects['database']}\tactive\tcsv\tDatabase project",
            f"{projects['empty']}\tactive\t-\tEmpty project",
        ]

    def test_include_archived(self, projects, cli_with_session_factory):
        result = cli_with_session_factory(cli, ["projects", "list", "--include-archived"])

        assert result.exit_code == 0, result.output
        assert f"{projects['archived']}\tarchived\t-\tArchived project" in result.output.splitlines()

    def test_member_filter(self, projects, cli_with_session_factory):
        result = cli_with_session_factory(cli, ["projects", "list", "--member", "member@example.com"])

        assert result.exit_code == 0, result.output
        assert result.output.splitlines() == [f"{projects['empty']}\tactive\t-\tEmpty project"]

    def test_unknown_member_refused(self, projects, cli_with_session_factory):
        result = cli_with_session_factory(cli, ["projects", "list", "--member", "nobody@example.com"])

        assert result.exit_code != 0
        assert "nobody@example.com" in result.output


FORM_HTML = """
<form method="post" action="{{ form_action }}">
    {{ csrf_form_element }}
    <input class="govuk-input" id="name" name="name" type="text" value="{{ value('name') }}">
    <button type="submit" class="govuk-button">Submit</button>
</form>
"""


class TestProjectsClone:
    @pytest.fixture
    def source(self, postgres_session_factory, admin_user):
        """A database project with a published page showing an image, and respondents."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow, title="Climate Assembly", created_by_user_id=admin_user.id)
            image = RegistrationImage(
                assembly_id=assembly.id, byte_size=4, width=1, height=1, sha256="c" * 64, data=b"\x89PNG"
            )
            uow.registration_images.add(image)
            page = RegistrationPage(
                assembly_id=assembly.id,
                name="English",
                url_slug="climate-assembly",
                short_url_slug="333333",
                status=RegistrationPageStatus.PUBLISHED,
            )
            uow.registration_pages.add(page)
            uow.flush()
            uow.registration_page_html_sources.add(
                RegistrationPageHtml(
                    registration_page_id=page.id,
                    intro_html=f'<img src="/register-assets/images/{image.id}.png" alt="Logo">',
                    form_html=FORM_HTML,
                )
            )
            for external_id, status in [("a", RespondentStatus.SELECTED), ("b", RespondentStatus.DELETED)]:
                uow.respondents.add(
                    Respondent(assembly_id=assembly.id, external_id=external_id, selection_status=status)
                )
            uow.commit()
            return assembly.id

    def _clone_ids(self, postgres_session_factory, source_id):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            return [a.id for a in uow.assemblies.all() if a.id != source_id]

    def test_default_clone_prints_the_copy(
        self, source, admin_user, postgres_session_factory, cli_with_session_factory
    ):
        result = cli_with_session_factory(cli, ["projects", "clone", str(source), "--user-email", admin_user.email])

        assert result.exit_code == 0, result.output
        [clone_id] = self._clone_ids(postgres_session_factory, source)
        assert "Cloned as 'Climate Assembly (copy)'" in result.output
        assert f"/backoffice/project/{clone_id}" in result.output
        assert "English: /register/climate-assembly-copy" in result.output
        assert "registration pages: 1" in result.output
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondents.count_by_assembly_id(clone_id) == 0

    def test_explicit_title(self, source, admin_user, postgres_session_factory, cli_with_session_factory):
        result = cli_with_session_factory(
            cli, ["projects", "clone", str(source), "--user-email", admin_user.email, "--title", "Training day"]
        )

        assert result.exit_code == 0, result.output
        assert "Cloned as 'Training day'" in result.output

    def test_taken_title_suggests_title_option(self, source, admin_user, cli_with_session_factory):
        result = cli_with_session_factory(
            cli, ["projects", "clone", str(source), "--user-email", admin_user.email, "--title", "Climate Assembly"]
        )

        assert result.exit_code != 0
        assert "--title" in result.output

    @pytest.mark.parametrize(
        ("email", "message"),
        [("nobody@example.com", "not found"), ("user@example.com", "ADMIN role")],
    )
    def test_user_email_must_name_an_admin(
        self, source, regular_user, postgres_session_factory, cli_with_session_factory, email, message
    ):
        result = cli_with_session_factory(cli, ["projects", "clone", str(source), "--user-email", email])

        assert result.exit_code != 0
        assert message in result.output
        assert self._clone_ids(postgres_session_factory, source) == []

    def test_inactive_admin_refused(self, source, admin_user, postgres_session_factory, cli_with_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.users.get(admin_user.id).is_active = False
            uow.commit()

        result = cli_with_session_factory(cli, ["projects", "clone", str(source), "--user-email", admin_user.email])

        assert result.exit_code != 0
        assert "active user with the ADMIN role" in result.output

    def test_respondents_need_the_training_flag(
        self, source, admin_user, postgres_session_factory, cli_with_session_factory
    ):
        result = cli_with_session_factory(
            cli, ["projects", "clone", str(source), "--user-email", admin_user.email, "--respondents"]
        )

        assert result.exit_code != 0
        assert "--for-training-or-demo" in result.output
        assert self._clone_ids(postgres_session_factory, source) == []

    def test_invalid_option_combination_refused(self, source, admin_user, cli_with_session_factory):
        result = cli_with_session_factory(
            cli, ["projects", "clone", str(source), "--user-email", admin_user.email, "--no-questions"]
        )

        assert result.exit_code != 0
        assert "registration form needs its questions" in result.output

    def test_respondents_prompt_names_the_count_and_proceeds_on_yes(
        self, source, admin_user, postgres_session_factory, cli_with_session_factory
    ):
        args = ["projects", "clone", str(source), "--user-email", admin_user.email]
        result = cli_with_session_factory(cli, [*args, "--respondents", "--for-training-or-demo"], input="y\n")

        assert result.exit_code == 0, result.output
        assert "This will copy 1 respondents" in result.output
        [clone_id] = self._clone_ids(postgres_session_factory, source)
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            [respondent] = uow.respondents.get_by_assembly_id(clone_id)
            assert respondent.selection_status == RespondentStatus.POOL

    def test_respondents_prompt_cancels_on_no(
        self, source, admin_user, postgres_session_factory, cli_with_session_factory
    ):
        args = ["projects", "clone", str(source), "--user-email", admin_user.email]
        result = cli_with_session_factory(cli, [*args, "--respondents", "--for-training-or-demo"], input="n\n")

        assert "Operation cancelled" in result.output
        assert self._clone_ids(postgres_session_factory, source) == []

    def test_yes_skips_the_prompt_and_preserve_keeps_status(
        self, source, admin_user, postgres_session_factory, cli_with_session_factory
    ):
        args = ["projects", "clone", str(source), "--user-email", admin_user.email]
        flags = ["--respondents", "--for-training-or-demo", "--preserve-respondent-status", "--yes"]
        result = cli_with_session_factory(cli, [*args, *flags])

        assert result.exit_code == 0, result.output
        assert "This will copy" not in result.output
        [clone_id] = self._clone_ids(postgres_session_factory, source)
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            [respondent] = uow.respondents.get_by_assembly_id(clone_id)
            assert respondent.selection_status == RespondentStatus.SELECTED

    def test_cloned_page_renders_with_its_own_image(
        self, source, admin_user, client, monkeypatch, postgres_session_factory, cli_with_session_factory
    ):
        """The copy's page loads at its new slug, and its image comes from the copy, not the original."""
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
        reload_flags()
        result = cli_with_session_factory(cli, ["projects", "clone", str(source), "--user-email", admin_user.email])
        assert result.exit_code == 0, result.output

        [clone_id] = self._clone_ids(postgres_session_factory, source)
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            [page] = uow.registration_pages.list_by_assembly_id(clone_id)
            [image] = uow.registration_images.list_by_assembly_id(clone_id)
            slug, image_id = page.url_slug, image.id

        response = client.get(f"/register/{slug}")

        assert response.status_code == 200
        assert f"/register-assets/images/{image_id}.png".encode() in response.data
        assert client.get(f"/register-assets/images/{image_id}.png").status_code == 200
