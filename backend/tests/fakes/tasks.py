"""ABOUTME: RecordingTaskRunner, a TaskRunner that records the tasks it is asked to send and runs none
ABOUTME: Tests set what each task's status reports, to drive the finished, failed and running paths"""

import pickle
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sortition_algorithms.settings import Settings

from opendlp.service_layer.task_runner import Dispatch, GSheetSource, TaskRunner, TaskStatus


@dataclass(frozen=True)
class SubmittedTask:
    """One task the code under test sent: its name, its arguments, and the publish options."""

    name: str
    kwargs: dict[str, Any]
    options: dict[str, Any] = field(default_factory=dict)


class RecordingTaskRunner(TaskRunner):
    """Records each dispatched task in ``submitted`` instead of sending it to a worker.

    Like the Celery runner, each task method pickles its arguments when called,
    so an argument that could not reach a worker fails the test. The task only
    lands in ``submitted`` when its Dispatch is called - after the caller's
    commit - so a test that never commits sees nothing sent. The recorded
    kwargs have been through a pickle round-trip, as a worker would see them.

    ``status`` reports PENDING for any id, as Celery does for one it has not
    seen. ``finish``, ``fail`` and ``set_state`` set what it reports instead.
    Set ``fail_dispatch`` to an exception to make the next Dispatch raise it,
    and ``on_dispatch`` to a function to call with each task as it is sent -
    to look at the database at that moment, say.
    """

    def __init__(self) -> None:
        self.submitted: list[SubmittedTask] = []
        self.revoked: list[str] = []
        self.fail_dispatch: Exception | None = None
        self.on_dispatch: Callable[[SubmittedTask], object] | None = None
        self._statuses: dict[str, TaskStatus] = {}

    def _prepare(self, name: str, kwargs: dict[str, Any], **options: Any) -> Dispatch:
        # Pickled now, as CeleryTaskRunner does, and loaded back so the test
        # sees what a worker would receive.
        sent_kwargs = pickle.loads(pickle.dumps(kwargs))  # noqa: S301 - our own arguments, pickled a line above
        sent_options = {key: value for key, value in options.items() if value is not None}

        def dispatch() -> None:
            if self.fail_dispatch is not None:
                error, self.fail_dispatch = self.fail_dispatch, None
                raise error
            task = SubmittedTask(name=name, kwargs=sent_kwargs, options=sent_options)
            self.submitted.append(task)
            if self.on_dispatch is not None:
                self.on_dispatch(task)

        return dispatch

    def load_gsheet(self, *, task_id: uuid.UUID, data_source: GSheetSource, settings: Settings) -> Dispatch:
        kwargs = {"task_id": task_id, "data_source": data_source, "settings": settings}
        return self._prepare("load_gsheet", kwargs, task_id=str(task_id))

    def run_select(
        self,
        *,
        task_id: uuid.UUID,
        data_source: GSheetSource,
        number_people_wanted: int,
        settings: Settings,
        test_selection: bool,
        gen_rem_tab: bool,
        for_replacements: bool = False,
        time_limit: int | None = None,
        soft_time_limit: int | None = None,
    ) -> Dispatch:
        kwargs = {
            "task_id": task_id,
            "data_source": data_source,
            "number_people_wanted": number_people_wanted,
            "settings": settings,
            "test_selection": test_selection,
            "gen_rem_tab": gen_rem_tab,
            "for_replacements": for_replacements,
        }
        return self._prepare(
            "run_select", kwargs, task_id=str(task_id), time_limit=time_limit, soft_time_limit=soft_time_limit
        )

    def manage_old_tabs(self, *, task_id: uuid.UUID, data_source: GSheetSource, dry_run: bool) -> Dispatch:
        kwargs = {"task_id": task_id, "data_source": data_source, "dry_run": dry_run}
        return self._prepare("manage_old_tabs", kwargs, task_id=str(task_id))

    def run_select_from_db(
        self,
        *,
        task_id: uuid.UUID,
        assembly_id: uuid.UUID,
        number_people_wanted: int,
        settings: Settings,
        test_selection: bool,
        targets_snapshot: list[dict[str, Any]] | None = None,
    ) -> Dispatch:
        kwargs = {
            "task_id": task_id,
            "assembly_id": assembly_id,
            "number_people_wanted": number_people_wanted,
            "settings": settings,
            "test_selection": test_selection,
            "targets_snapshot": targets_snapshot,
        }
        return self._prepare("run_select_from_db", kwargs, task_id=str(task_id))

    def auto_export_respondents(self, *, assembly_id: uuid.UUID, countdown: int) -> Dispatch:
        return self._prepare("auto_export_respondents", {"assembly_id": assembly_id}, countdown=countdown)

    def status(self, celery_task_id: str) -> TaskStatus:
        return self._statuses.get(celery_task_id, TaskStatus(state="PENDING"))

    def revoke(self, celery_task_id: str) -> None:
        self.revoked.append(celery_task_id)

    # What status() reports, keyed by the id the task was sent with - for the
    # start_* services, the run record's task_id.

    def finish(self, task_id: uuid.UUID | str, value: Any) -> None:
        """Report the task as SUCCESS, having returned ``value``."""
        self._statuses[str(task_id)] = TaskStatus(state="SUCCESS", value=value)

    def fail(self, task_id: uuid.UUID | str, error: str = "", state: str = "FAILURE") -> None:
        """Report the task as failed (FAILURE, or REVOKED / REJECTED), with ``error`` as its message."""
        self._statuses[str(task_id)] = TaskStatus(state=state, error=error)

    def set_state(self, task_id: uuid.UUID | str, state: str) -> None:
        """Report the task as in ``state``, with no value or error (STARTED, PENDING, ...)."""
        self._statuses[str(task_id)] = TaskStatus(state=state)

    def submitted_named(self, name: str) -> list[SubmittedTask]:
        """The submitted tasks with this name, in the order they were sent."""
        return [task for task in self.submitted if task.name == name]
