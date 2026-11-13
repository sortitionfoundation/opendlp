"""ABOUTME: Unit tests for creating a project together with the first thing written into it.
ABOUTME: Covers the choices each path stores, and what the import paths hand back, over fake repositories."""

import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, DataSource, GlobalRole, RespondentsSource, TargetsSource
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection
from opendlp.service_layer.project_creation_service import (
    ProjectDetails,
    create_project,
    create_project_with_gsheet,
    create_project_with_respondents_csv,
    create_project_with_targets_csv,
)
from tests.data import VALID_GSHEET_URL

DETAILS = ProjectDetails(title="A new project", question="What next?", number_to_select=30)
TARGETS_CSV = "feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"
RESPONDENTS_CSV = "ref,code,Region\n1,a,North\n2,b,South"


@pytest.fixture
def organiser(uow):
    user = User(email="organiser@example.com", global_role=GlobalRole.ORGANISER, password_hash="hash")
    uow.users.add(user)
    return user


class TestCreateProject:
    def test_the_details_and_choices_are_stored(self, uow, organiser):
        assembly = create_project(
            uow,
            organiser.id,
            DETAILS,
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.MANUAL,
            respondents_source=RespondentsSource.REGISTRATION,
        )

        assert assembly.title == "A new project"
        assert assembly.question == "What next?"
        assert assembly.number_to_select == 30
        assert assembly.data_source == DataSource.OPENDLP
        assert assembly.targets_source == TargetsSource.MANUAL
        assert assembly.respondents_source == RespondentsSource.REGISTRATION

    def test_the_creator_manages_the_project(self, uow, organiser):
        assembly = create_project(uow, organiser.id, DETAILS)

        assert uow.users.get(organiser.id).get_assembly_role(assembly.id) == AssemblyRole.ASSEMBLY_MANAGER

    def test_someone_who_cannot_create_projects_is_refused(self, uow):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        with pytest.raises(InsufficientPermissions):
            create_project(uow, user.id, DETAILS)


class TestCreateProjectWithGSheet:
    def test_the_project_is_in_google_sheets_with_its_settings(self, uow, organiser):
        assembly = create_project_with_gsheet(
            uow, organiser.id, DETAILS, {"url": VALID_GSHEET_URL, "team": "uk", "select_registrants_tab": "People"}
        )

        assert assembly.data_source == DataSource.GSHEET
        gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
        assert gsheet.url == VALID_GSHEET_URL
        assert gsheet.select_registrants_tab == "People"


class TestCreateProjectWithTargetsCsv:
    def test_the_targets_are_imported_and_the_choice_recorded(self, uow, organiser):
        assembly, result = create_project_with_targets_csv(
            uow, organiser.id, DETAILS, TARGETS_CSV, respondents_source=RespondentsSource.REGISTRATION
        )

        assert [category.name for category in result.categories] == ["Region"]
        assert assembly.data_source == DataSource.OPENDLP
        assert assembly.targets_source == TargetsSource.CSV
        assert assembly.respondents_source == RespondentsSource.REGISTRATION
        assert len(uow.target_categories.get_by_assembly_id(assembly.id)) == 1

    def test_a_refused_file_raises(self, uow, organiser):
        """The caller's unit of work rolls the project back; see the integration test for that half."""
        with pytest.raises(InvalidSelection):
            create_project_with_targets_csv(uow, organiser.id, DETAILS, "not,a,targets,file\n1,2,3,4")


class TestCreateProjectWithRespondentsCsv:
    def test_the_respondents_are_imported_and_the_upload_recorded(self, uow, organiser):
        assembly, respondents, skipped = create_project_with_respondents_csv(
            uow, organiser.id, DETAILS, RESPONDENTS_CSV, filename="people.csv", targets_source=TargetsSource.MANUAL
        )

        assert len(respondents) == 2
        assert skipped == []
        assert assembly.respondents_source == RespondentsSource.CSV
        assert assembly.targets_source == TargetsSource.MANUAL
        stored = uow.assemblies.get(assembly.id)
        assert stored.csv.last_import_filename == "people.csv"
        assert stored.csv.csv_id_column == "ref"

    def test_the_id_column_named_is_used(self, uow, organiser):
        assembly, _respondents, _skipped = create_project_with_respondents_csv(
            uow, organiser.id, DETAILS, RESPONDENTS_CSV, id_column="code"
        )

        assert uow.assemblies.get(assembly.id).csv.csv_id_column == "code"

    def test_a_refused_file_raises(self, uow, organiser):
        with pytest.raises(InvalidSelection):
            create_project_with_respondents_csv(uow, organiser.id, DETAILS, RESPONDENTS_CSV, id_column="missing")
