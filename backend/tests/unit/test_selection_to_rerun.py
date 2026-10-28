"""ABOUTME: Unit tests for finding the failed selection the targets page may re-run
ABOUTME: Covers which runs qualify - assembly, status and kind - and that a test run stays a test"""

import uuid

import pytest

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.sortition import get_selection_to_rerun

ASSEMBLY_ID = uuid.uuid4()


def _add_run(
    uow, task_type=SelectionTaskType.SELECT_FROM_DB, status=SelectionRunStatus.FAILED, assembly_id=ASSEMBLY_ID
):
    record = SelectionRunRecord(assembly_id=assembly_id, task_id=uuid.uuid4(), status=status, task_type=task_type)
    uow.selection_run_records.add(record)
    return record.task_id


class TestGetSelectionToRerun:
    @pytest.mark.parametrize("task_type", [SelectionTaskType.SELECT_FROM_DB, SelectionTaskType.TEST_SELECT_FROM_DB])
    def test_a_failed_initial_or_test_selection_on_the_assembly(self, uow, task_type):
        task_id = _add_run(uow, task_type=task_type)

        run = get_selection_to_rerun(uow, ASSEMBLY_ID, task_id)

        assert run is not None
        assert run.task_type == task_type

    def test_an_unknown_run(self, uow):
        assert get_selection_to_rerun(uow, ASSEMBLY_ID, uuid.uuid4()) is None

    def test_a_run_on_another_assembly(self, uow):
        task_id = _add_run(uow, assembly_id=uuid.uuid4())
        assert get_selection_to_rerun(uow, ASSEMBLY_ID, task_id) is None

    @pytest.mark.parametrize(
        "status", [SelectionRunStatus.COMPLETED, SelectionRunStatus.RUNNING, SelectionRunStatus.CANCELLED]
    )
    def test_a_run_that_has_not_failed(self, uow, status):
        task_id = _add_run(uow, status=status)
        assert get_selection_to_rerun(uow, ASSEMBLY_ID, task_id) is None

    @pytest.mark.parametrize(
        "task_type",
        [
            SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
            SelectionTaskType.SELECT_GSHEET,
            SelectionTaskType.RESET_TO_POOL,
        ],
    )
    def test_a_run_of_another_kind(self, uow, task_type):
        task_id = _add_run(uow, task_type=task_type)
        assert get_selection_to_rerun(uow, ASSEMBLY_ID, task_id) is None
