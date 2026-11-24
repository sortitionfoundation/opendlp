"""ABOUTME: Schedules and runs the automatic respondent export to Google Sheets
ABOUTME: Debounces requests through Redis and hands the export to a Celery task"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import structlog

from opendlp.config import RedisCfg
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.entrypoints.celery import tasks
from opendlp.service_layer.respondent_export_service import resolve_status_filter, write_respondent_export

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from redis import Redis

    from opendlp.adapters.tabular_export import AbstractGSheetExportTarget
    from opendlp.domain.events import RespondentsChanged, RespondentSchemaChanged
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)

EXPORT_KIND = GSheetExportKind.RESPONDENTS

# How long after a change the export runs. Long enough to fold a burst of
# registrations into one export and to let the caller's transaction commit
# before the task reads; short enough that the sheet still feels live.
AUTO_EXPORT_DELAY_SECONDS = 30

_PENDING_KEY_PREFIX = "auto_export_pending:"
# If the queued task never runs (broker lost, worker down) the pending key
# must not block auto-export for good, so it expires a while after the task
# was due.
_PENDING_TTL_SECONDS = AUTO_EXPORT_DELAY_SECONDS * 4

_LOCK_KEY_PREFIX = "auto_export_lock:"
# Held while one export writes, so two exports of the same assembly cannot
# interleave. Generous: it only matters if a worker dies mid-export.
LOCK_TIMEOUT_SECONDS = 300


def _get_redis() -> Redis:
    return RedisCfg.from_env().create_client()


def pending_key(assembly_id: uuid.UUID) -> str:
    return f"{_PENDING_KEY_PREFIX}{assembly_id}"


def lock_key(assembly_id: uuid.UUID) -> str:
    return f"{_LOCK_KEY_PREFIX}{assembly_id}"


def handle_respondents_changed(event: RespondentsChanged | RespondentSchemaChanged, uow: AbstractUnitOfWork) -> None:
    """Have the assembly's respondents exported again once this change commits, if auto-export is on.

    The handler for both events that change what the export would contain: the
    respondents themselves, and the fields that make up its columns. It reads
    the config in the caller's transaction and leaves the scheduling, which is
    outside the database, to run after the commit - so a change that rolls
    back queues nothing, and the task cannot run before the change is there
    to read.
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(event.assembly_id, EXPORT_KIND)
    if config is None or not config.auto_export:
        return
    uow.after_commit(partial(schedule_auto_export, event.assembly_id))


def schedule_auto_export(assembly_id: uuid.UUID, redis_client: Redis | None = None) -> bool:
    """Queue the export task for the assembly unless one is already pending.

    Does not look at the config: the task re-reads it and does nothing if
    auto-export has been stopped. It is a side effect of someone else's
    request - a member of the public registering, an organiser editing - so it
    never raises: Redis or broker trouble is logged and swallowed. Returns
    whether a task was queued, which is False when one is already pending or
    when scheduling failed.
    """
    try:
        r = redis_client or _get_redis()
        if not r.set(pending_key(assembly_id), "1", nx=True, ex=_PENDING_TTL_SECONDS):
            return False
        tasks.auto_export_respondents.apply_async(
            kwargs={"assembly_id": assembly_id}, countdown=AUTO_EXPORT_DELAY_SECONDS
        )
    except Exception as exc:
        # A failed export must never fail the change that asked for it; the next
        # change will ask again, and the pending key expires on its own.
        logger.exception("Could not schedule automatic export", assembly_id=str(assembly_id), error=str(exc))
        return False
    return True


def run_auto_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    target_factory: Callable[[str], AbstractGSheetExportTarget],
) -> bool:
    """Export the assembly's respondents to its saved sheet, as a background task.

    Not permission-gated: there is no acting user when a registration triggers
    it. Authority comes from the organiser who enabled auto-export, who needed
    manage permission to do so. Only the Celery task should call this.

    Re-reads the config, so an export queued before auto-export was stopped does
    nothing. Returns whether a write happened. Lets ``ExportTargetError``
    propagate so the task can retry it.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    if config is None or not config.auto_export:
        return False
    target = target_factory(config.url)
    write_respondent_export(
        uow,
        assembly_id,
        status_filter=resolve_status_filter(config.auto_export_status_filter),
        target=target,
        sheet_title=config.worksheet_name,
    )
    config.update_values(spreadsheet_title=target.result_title, worksheet_url=target.result_url)
    uow.commit()
    return True
