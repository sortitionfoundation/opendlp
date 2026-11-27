"""ABOUTME: CeleryTaskRunner, the TaskRunner that publishes tasks to Celery and reads their results
ABOUTME: Only bootstrap imports it, so the service layer never imports the Celery tasks"""

import pickle
import uuid
from typing import Any

from celery import Task
from sortition_algorithms.settings import Settings

from opendlp.entrypoints.celery import tasks
from opendlp.entrypoints.celery.app import app
from opendlp.service_layer.task_runner import Dispatch, GSheetSource, TaskRunner, TaskStatus

_FAILED_STATES = frozenset({"FAILURE", "REVOKED", "REJECTED"})


def _prepare(task: Task, kwargs: dict[str, Any], **options: Any) -> Dispatch:
    """Check ``kwargs`` pickle, and return a Dispatch that publishes ``task`` with them.

    The pickled bytes are not reused: Celery serialises again on publish. The
    dump is there to raise a serialisation bug now, in the caller's transaction.
    """
    pickle.dumps(kwargs)
    publish_options = {key: value for key, value in options.items() if value is not None}

    def dispatch() -> None:
        task.apply_async(kwargs=kwargs, **publish_options)

    return dispatch


def _describe_failure(info: Any) -> str:
    """The message of the exception a failed task stored, in whichever shape the backend kept it."""
    try:
        if info and isinstance(info, Exception):
            return str(info)
        if info and isinstance(info, dict):
            return str(info.get("exc_message", "No exception message"))
        return "No exception info available"
    except Exception:
        return "Could not extract exception info"


class CeleryTaskRunner(TaskRunner):
    """Publishes each task to the broker with our task id as its Celery id."""

    def load_gsheet(self, *, task_id: uuid.UUID, data_source: GSheetSource, settings: Settings) -> Dispatch:
        kwargs = {"task_id": task_id, "data_source": data_source, "settings": settings}
        return _prepare(tasks.load_gsheet, kwargs, task_id=str(task_id))

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
        return _prepare(
            tasks.run_select,
            kwargs,
            task_id=str(task_id),
            time_limit=time_limit,
            soft_time_limit=soft_time_limit,
        )

    def manage_old_tabs(self, *, task_id: uuid.UUID, data_source: GSheetSource, dry_run: bool) -> Dispatch:
        kwargs = {"task_id": task_id, "data_source": data_source, "dry_run": dry_run}
        return _prepare(tasks.manage_old_tabs, kwargs, task_id=str(task_id))

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
        return _prepare(tasks.run_select_from_db, kwargs, task_id=str(task_id))

    def auto_export_respondents(self, *, assembly_id: uuid.UUID, countdown: int) -> Dispatch:
        return _prepare(tasks.auto_export_respondents, {"assembly_id": assembly_id}, countdown=countdown)

    def status(self, celery_task_id: str) -> TaskStatus:
        # Reads the stored result rather than calling AsyncResult.get(), which
        # Celery forbids inside a worker task, so this is safe from a task too.
        result = app.AsyncResult(celery_task_id)
        state = result.state
        if state == "SUCCESS":
            return TaskStatus(state=state, value=result.result)
        if state in _FAILED_STATES:
            return TaskStatus(state=state, error=_describe_failure(result.info))
        return TaskStatus(state=state)

    def revoke(self, celery_task_id: str) -> None:
        app.control.revoke(celery_task_id, terminate=True)
