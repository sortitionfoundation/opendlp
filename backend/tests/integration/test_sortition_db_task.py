"""ABOUTME: Integration tests for database-based Celery selection tasks
ABOUTME: Tests _internal_load_db, _internal_write_db_results, and generate_selection_csvs with a real database"""

import uuid
from unittest.mock import patch

import pytest
from sortition_algorithms.settings import Settings

from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import (
    _internal_load_db,
    _internal_run_select,
    _internal_write_db_results,
    run_select_from_db,
)
from opendlp.service_layer.sortition import generate_selection_csvs
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def test_settings():
    return Settings(id_column="external_id", check_same_address=False, columns_to_keep=[])


@pytest.fixture
def assembly_with_data(postgres_session_factory):
    """Create assembly with Gender category and respondents.

    Returns assembly_id. Data:
    - Gender: Male(min=1, max=1) and Female(min=1, max=1)
    - 4 eligible respondents: NB001/NB002 (Male), NB003/NB004 (Female)
    - 1 ineligible respondent: NB005 (Male, eligible=False)
    """
    assembly_id = uuid.uuid4()

    with bootstrap(session_factory=postgres_session_factory) as uow:
        assembly = Assembly(assembly_id=assembly_id, title="DB Selection Test", number_to_select=2)
        uow.assemblies.add(assembly)

        cat = TargetCategory(assembly_id=assembly_id, name="Gender")
        cat.add_value(TargetValue(value="Male", min=1, max=1))
        cat.add_value(TargetValue(value="Female", min=1, max=1))
        uow.target_categories.add(cat)

        for ext_id, gender in [("NB001", "Male"), ("NB002", "Male"), ("NB003", "Female"), ("NB004", "Female")]:
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly_id,
                    external_id=ext_id,
                    attributes={"Gender": gender},
                    eligible=True,
                    can_attend=True,
                )
            )

        # Ineligible respondent — should be excluded from selection
        uow.respondents.add(
            Respondent(
                assembly_id=assembly_id,
                external_id="NB005",
                attributes={"Gender": "Male"},
                eligible=False,
                can_attend=True,
            )
        )

        uow.commit()

    return assembly_id


def _make_run_record(assembly_id: uuid.UUID, postgres_session_factory) -> uuid.UUID:
    """Create a SelectionRunRecord in the DB and return its task_id."""
    task_id = uuid.uuid4()
    with bootstrap(session_factory=postgres_session_factory) as uow:
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            status=SelectionRunStatus.PENDING,
            log_messages=["Task submitted for database selection"],
        )
        uow.selection_run_records.add(record)
        uow.commit()
    return task_id


class TestInternalLoadDb:
    def test_loads_features_and_people(self, postgres_session_factory, assembly_with_data, test_settings):
        """Test that _internal_load_db loads features and 4 eligible people (ineligible excluded)."""
        assembly_id = assembly_with_data
        task_id = _make_run_record(assembly_id, postgres_session_factory)

        success, features, loaded_people, report = _internal_load_db(
            task_id=task_id,
            assembly_id=assembly_id,
            settings=test_settings,
            final_task=True,
            session_factory=postgres_session_factory,
        )

        assert success is True
        assert features is not None
        assert loaded_people is not None
        assert "Gender" in features
        assert loaded_people.count == 4

        # Verify ineligible respondent was excluded
        assert "NB005" not in set(loaded_people)

        # Verify run record was updated to COMPLETED (final_task=True)
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.COMPLETED


class TestInternalWriteDbResults:
    def test_updates_respondent_statuses_and_stores_remaining_ids(
        self, postgres_session_factory, assembly_with_data, test_settings
    ):
        """Test that write results marks 2 respondents SELECTED and stores 2 remaining_ids."""
        assembly_id = assembly_with_data
        task_id = _make_run_record(assembly_id, postgres_session_factory)

        # Load data
        success, features, loaded_people, _ = _internal_load_db(
            task_id=task_id,
            assembly_id=assembly_id,
            settings=test_settings,
            final_task=False,
            session_factory=postgres_session_factory,
        )
        assert success and features is not None and loaded_people is not None

        # Run selection
        success, selected_panels, _ = _internal_run_select(
            task_id=task_id,
            features=features,
            people=loaded_people,
            settings=test_settings,
            number_people_wanted=2,
            test_selection=False,
            final_task=False,
            session_factory=postgres_session_factory,
        )
        assert success

        # Write results
        _internal_write_db_results(
            task_id=task_id,
            assembly_id=assembly_id,
            full_people=loaded_people,
            selected_panels=selected_panels,
            session_factory=postgres_session_factory,
        )

        # Verify respondent statuses
        with bootstrap(session_factory=postgres_session_factory) as uow:
            all_respondents = uow.respondents.get_by_assembly_id(assembly_id)
            selected = [r for r in all_respondents if r.selection_status == RespondentStatus.SELECTED]
            pool = [r for r in all_respondents if r.selection_status == RespondentStatus.POOL]
            assert len(selected) == 2
            assert len(pool) == 3  # 2 remaining eligible + 1 ineligible

        # Verify run record has remaining_ids
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.COMPLETED
            assert record.remaining_ids is not None
            assert len(record.remaining_ids) == 2


class TestGenerateSelectionCsvs:
    def test_generates_csvs_with_correct_structure(self, postgres_session_factory, assembly_with_data, test_settings):
        """Test that generate_selection_csvs produces valid CSVs after a selection run."""
        assembly_id = assembly_with_data
        task_id = _make_run_record(assembly_id, postgres_session_factory)

        # Run full pipeline
        success, features, loaded_people, _ = _internal_load_db(
            task_id=task_id,
            assembly_id=assembly_id,
            settings=test_settings,
            final_task=False,
            session_factory=postgres_session_factory,
        )
        assert success and features is not None and loaded_people is not None

        success, selected_panels, _ = _internal_run_select(
            task_id=task_id,
            features=features,
            people=loaded_people,
            settings=test_settings,
            number_people_wanted=2,
            test_selection=False,
            final_task=False,
            session_factory=postgres_session_factory,
        )
        assert success

        _internal_write_db_results(
            task_id=task_id,
            assembly_id=assembly_id,
            full_people=loaded_people,
            selected_panels=selected_panels,
            session_factory=postgres_session_factory,
        )

        # Now generate CSVs
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            selected_csv, remaining_csv = generate_selection_csvs(uow, assembly_id, task_id)

        # Check selected CSV structure
        selected_lines = [line for line in selected_csv.strip().split("\n") if line]
        assert len(selected_lines) == 3  # header + 2 selected people
        assert "external_id" in selected_lines[0]
        assert "Gender" in selected_lines[0]

        # Check remaining CSV structure
        remaining_lines = [line for line in remaining_csv.strip().split("\n") if line]
        assert len(remaining_lines) == 3  # header + 2 remaining people
        assert "external_id" in remaining_lines[0]
        assert "Gender" in remaining_lines[0]

        # Verify all 4 eligible respondents appear across both CSVs
        all_ids = set()
        for line in selected_lines[1:] + remaining_lines[1:]:
            all_ids.add(line.split(",")[0])
        assert all_ids == {"NB001", "NB002", "NB003", "NB004"}


class TestRunSelectFromDb:
    def test_run_select_from_db_end_to_end(self, postgres_session_factory, assembly_with_data, test_settings):
        """Test that run_select_from_db orchestrates load, select, and write correctly."""
        assembly_id = assembly_with_data
        task_id = _make_run_record(assembly_id, postgres_session_factory)

        with patch.object(run_select_from_db, "update_state"):
            success, selected_panels, report = run_select_from_db(
                task_id=task_id,
                assembly_id=assembly_id,
                number_people_wanted=2,
                settings=test_settings,
                test_selection=False,
                session_factory=postgres_session_factory,
            )

        assert success is True
        assert len(selected_panels) == 1
        assert len(selected_panels[0]) == 2

        # Verify respondent statuses updated
        with bootstrap(session_factory=postgres_session_factory) as uow:
            all_resp = uow.respondents.get_by_assembly_id(assembly_id)
            selected = [r for r in all_resp if r.selection_status == RespondentStatus.SELECTED]
            assert len(selected) == 2

        # Verify remaining_ids stored on run record
        with bootstrap(session_factory=postgres_session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(task_id)
            assert record is not None
            assert record.status == SelectionRunStatus.COMPLETED
            assert record.remaining_ids is not None
            assert len(record.remaining_ids) == 2
