"""ABOUTME: Integration tests that a project created with its first data lands, or does not, as one unit.
ABOUTME: Against real Postgres: the sheet settings and imports commit with the project, and a refused file leaves nothing."""

import pytest
from sqlalchemy import text

from opendlp.domain.users import User
from opendlp.domain.value_objects import DataSource, GlobalRole, RespondentsSource, TargetsSource
from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.project_creation_service import (
    ProjectDetails,
    create_project_with_gsheet,
    create_project_with_respondents_csv,
    create_project_with_targets_csv,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.data import VALID_GSHEET_URL

DETAILS = ProjectDetails(title="Made with data", number_to_select=30)
TARGETS_CSV = "feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"
RESPONDENTS_CSV = "ref,code,Region\n1,a,North\n2,b,South"


@pytest.fixture
def organiser(postgres_session):
    user = User(
        email="creator@example.com",
        global_role=GlobalRole.ORGANISER,
        password_hash="hash",  # pragma: allowlist secret
    )
    postgres_session.add(user)
    postgres_session.commit()
    return user


def _assembly_count(session_factory) -> int:
    session = session_factory()
    try:
        return int(session.execute(text("SELECT count(*) FROM assemblies")).scalar_one())
    finally:
        session.close()


class TestCreatedWithItsData:
    def test_a_sheet_project_and_its_settings_commit_together(self, postgres_session_factory, organiser):
        """The sheet and selection settings rows reference a project that is not flushed until they are added."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_project_with_gsheet(uow, organiser.id, DETAILS, {"url": VALID_GSHEET_URL, "team": "uk"})

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            stored = fresh.assemblies.get(assembly.id)
            assert stored.data_source == DataSource.GSHEET
            assert stored.gsheet.url == VALID_GSHEET_URL
            assert stored.selection_settings is not None

    def test_targets_commit_with_the_project(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly, _result = create_project_with_targets_csv(uow, organiser.id, DETAILS, TARGETS_CSV)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            stored = fresh.assemblies.get(assembly.id)
            assert stored.targets_source == TargetsSource.CSV
            assert [category.name for category in fresh.target_categories.get_by_assembly_id(assembly.id)] == ["Region"]

    def test_respondents_commit_with_the_project(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly, _respondents, _skipped = create_project_with_respondents_csv(
                uow, organiser.id, DETAILS, RESPONDENTS_CSV, filename="people.csv"
            )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            stored = fresh.assemblies.get(assembly.id)
            assert stored.respondents_source == RespondentsSource.CSV
            assert stored.csv.last_import_filename == "people.csv"
            assert fresh.respondents.count_by_assembly_id(assembly.id) == 2


class TestARefusedFileLeavesNothing:
    def test_a_bad_targets_file_creates_no_project(self, postgres_session_factory, organiser):
        """Cancel before the first write leaves nothing behind - and so does a first write that fails."""
        before = _assembly_count(postgres_session_factory)

        with pytest.raises(InvalidSelection), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            create_project_with_targets_csv(uow, organiser.id, DETAILS, "not,a,targets,file\n1,2,3,4")

        assert _assembly_count(postgres_session_factory) == before

    def test_a_bad_respondents_file_creates_no_project(self, postgres_session_factory, organiser):
        before = _assembly_count(postgres_session_factory)

        with pytest.raises(InvalidSelection), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            create_project_with_respondents_csv(uow, organiser.id, DETAILS, RESPONDENTS_CSV, id_column="missing")

        assert _assembly_count(postgres_session_factory) == before
