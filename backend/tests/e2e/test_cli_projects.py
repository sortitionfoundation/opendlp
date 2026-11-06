"""ABOUTME: End-to-end tests for the `opendlp projects` CLI commands against a real database
ABOUTME: Drives the Click commands through CliRunner, as an admin at a shell would"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp.adapters.database import start_mappers
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.entrypoints.cli import cli
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
