"""ABOUTME: Feeds the example CSV files offered beside the Data tab uploads through the real imports
ABOUTME: Keeps them loadable, free of warnings and selectable, so the files cannot drift from the format"""

import uuid
from collections import Counter
from unittest.mock import patch

import pytest

from opendlp import config
from opendlp.adapters.sortition_data_adapter import DB_ID_COLUMN
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import run_select_from_db
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.sortition import check_db_selection_data
from opendlp.service_layer.target_csv_import import TargetImportResult, import_targets_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

# The number the Targets card tells organisers to set to use the example targets.
NUMBER_TO_SELECT = 10


def _read_example(filename: str) -> str:
    """The file as the upload routes read it."""
    return (config.get_static_path() / "examples" / filename).read_bytes().decode("utf-8-sig")


@pytest.fixture
def user_id(postgres_session_factory) -> uuid.UUID:
    user = User(
        email="example-csv@example.com",
        global_role=GlobalRole.ADMIN,
        password_hash="hash",  # pragma: allowlist secret
    )
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.users.add(user)
        return user.id


@pytest.fixture
def assembly_id(postgres_session_factory) -> uuid.UUID:
    assembly = Assembly(title="Trying the examples", number_to_select=NUMBER_TO_SELECT)
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.assemblies.add(assembly)
        return assembly.id


def _import_targets(postgres_session_factory, user_id: uuid.UUID, assembly_id: uuid.UUID) -> TargetImportResult:
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        return import_targets_from_csv(uow, user_id, assembly_id, _read_example("example-targets.csv"))


def _import_respondents(postgres_session_factory, user_id: uuid.UUID, assembly_id: uuid.UUID):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        return import_respondents_from_csv(uow, user_id, assembly_id, _read_example("example-respondents.csv"))


class TestExampleTargets:
    def test_load_through_the_import_without_warnings(self, postgres_session_factory, user_id, assembly_id):
        result = _import_targets(postgres_session_factory, user_id, assembly_id)

        assert result.warnings == []
        assert [category.name for category in result.categories] == ["Gender", "Age", "Region"]

    def test_percentages_add_up_to_100_for_every_target(self, postgres_session_factory, user_id, assembly_id):
        """Otherwise the targets page greets a first upload with a warning about the example."""
        result = _import_targets(postgres_session_factory, user_id, assembly_id)

        for category in result.categories:
            assert category.percentage_total() == pytest.approx(100), category.name

    def test_carry_only_the_columns_every_targets_file_needs(self):
        header = _read_example("example-targets.csv").splitlines()[0]

        assert header == "feature,value,min,max"


class TestExampleRespondents:
    def test_load_through_the_import_with_no_row_refused(self, postgres_session_factory, user_id, assembly_id):
        respondents, errors, id_column = _import_respondents(postgres_session_factory, user_id, assembly_id)

        assert errors == []
        assert id_column == "ID"
        assert len(respondents) == 20

    def test_use_addresses_that_cannot_reach_anyone(self, postgres_session_factory, user_id, assembly_id):
        respondents, _errors, _id_column = _import_respondents(postgres_session_factory, user_id, assembly_id)

        assert all(respondent.email.endswith("@example.com") for respondent in respondents)

    def test_every_other_column_becomes_an_attribute(self, postgres_session_factory, user_id, assembly_id):
        respondents, _errors, _id_column = _import_respondents(postgres_session_factory, user_id, assembly_id)

        for respondent in respondents:
            assert set(respondent.attributes) == {"First name", "Last name", "Gender", "Age", "Region"}


class TestExamplePair:
    def test_every_target_value_occurs_among_the_respondents(self, postgres_session_factory, user_id, assembly_id):
        categories = _import_targets(postgres_session_factory, user_id, assembly_id).categories
        respondents, _errors, _id_column = _import_respondents(postgres_session_factory, user_id, assembly_id)

        for category in categories:
            offered = {value.value for value in category.values}
            present = {respondent.attributes[category.name] for respondent in respondents}
            assert offered == present, category.name

    @pytest.mark.parametrize(
        "imports",
        [(_import_targets, _import_respondents), (_import_respondents, _import_targets)],
        ids=["targets_first", "respondents_first"],
    )
    def test_pass_the_selection_check_in_either_upload_order(
        self, postgres_session_factory, user_id, assembly_id, imports
    ):
        for do_import in imports:
            do_import(postgres_session_factory, user_id, assembly_id)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            result = check_db_selection_data(uow=uow, user_id=user_id, assembly_id=assembly_id)

        assert result.errors == []
        assert result.success is True
        assert result.num_features == 3
        assert result.num_people == 20

    def test_a_selection_finds_ten_people_within_the_targets(self, postgres_session_factory, user_id, assembly_id):
        """Something to play with: the pair has to run a selection, not only load."""
        categories = _import_targets(postgres_session_factory, user_id, assembly_id).categories
        respondents, _errors, _id_column = _import_respondents(postgres_session_factory, user_id, assembly_id)

        task_id = uuid.uuid4()
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.PENDING,
                    user_id=user_id,
                )
            )
            # As start_db_select_task builds them for a project that has saved none.
            assembly = uow.assemblies.get(assembly_id)
            settings = SelectionSettings.for_assembly(assembly).to_settings(id_column=DB_ID_COLUMN)

        with patch.object(run_select_from_db, "update_state"):
            success, panels, _report = run_select_from_db(
                task_id=task_id,
                assembly_id=assembly_id,
                number_people_wanted=NUMBER_TO_SELECT,
                settings=settings,
                test_selection=False,
                session_factory=postgres_session_factory,
            )

        assert success is True
        assert len(panels) == 1
        assert len(panels[0]) == NUMBER_TO_SELECT

        selected = [respondent for respondent in respondents if respondent.external_id in panels[0]]
        for category in categories:
            counts = Counter(respondent.attributes[category.name] for respondent in selected)
            for value in category.values:
                assert value.min <= counts[value.value] <= value.max, f"{category.name}/{value.value}"
