"""ABOUTME: Refuses a task that would write to an assembly while another writing task is unfinished
ABOUTME: Shared by the selection starts, the worker claim and the reset, so it is a leaf module"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opendlp.domain.value_objects import WRITING_TASK_TYPES, SelectionTaskType
from opendlp.service_layer.exceptions import CuratedMessage, InvalidSelection
from opendlp.translations import gettext as _

if TYPE_CHECKING:
    import uuid

    from opendlp.domain.assembly import SelectionRunRecord
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


class SelectionAlreadyRunning(CuratedMessage, InvalidSelection):
    """A writing task was refused because another writing task on the assembly is unfinished.

    Its message is translated and names only the blocking task's label, so it
    is safe to show. It carries the blocking record's task id and type so a
    route can send the user to that task's progress modal.
    """

    def __init__(self, blocking: SelectionRunRecord) -> None:
        super().__init__(
            _("Another task is already writing to this assembly: %(task)s", task=blocking.task_type_verbose)
        )
        self.task_id = blocking.task_id
        self.task_type = blocking.task_type
        self.task_label = blocking.task_type_verbose


def unfinished_writing_runs(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, exclude_task_id: uuid.UUID | None = None
) -> list[SelectionRunRecord]:
    """Lock the assembly, then return its unfinished writing runs, oldest first.

    The lock is held until the unit of work commits or rolls back, so the
    caller's insert or update is serialised with the check.
    """
    uow.lock_assembly_for_write(assembly_id)
    running = uow.selection_run_records.get_unfinished_for_assembly(assembly_id, WRITING_TASK_TYPES)
    return [record for record in running if record.task_id != exclude_task_id]


def refuse_if_writing_run_unfinished(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> None:
    """Raise SelectionAlreadyRunning if a writing task on the assembly is pending or running.

    Call it inside the open unit of work, after any validation that does not
    depend on other runs and before inserting the new run record, so the lock
    is held only around the check and the insert.
    """
    running = unfinished_writing_runs(uow, assembly_id)
    if running:
        raise SelectionAlreadyRunning(running[0])


# The query parameter on the selection page that opens each writing task's progress modal.
_MODAL_QUERY_PARAMS: dict[SelectionTaskType, str] = {
    SelectionTaskType.SELECT_GSHEET: "current_selection",
    SelectionTaskType.TEST_SELECT_GSHEET: "current_selection",
    SelectionTaskType.SELECT_REPLACEMENT_GSHEET: "current_replacement",
    SelectionTaskType.DELETE_OLD_TABS: "current_manage_tabs",
    SelectionTaskType.SELECT_FROM_DB: "current_selection",
    SelectionTaskType.TEST_SELECT_FROM_DB: "current_selection",
    SelectionTaskType.SELECT_REPLACEMENT_FROM_DB: "current_selection",
}


def running_task_query_param(task_type: SelectionTaskType) -> str:
    """The selection page query parameter that opens the progress modal for a writing task type."""
    return _MODAL_QUERY_PARAMS[task_type]
