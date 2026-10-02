"""ABOUTME: Schedules and runs the automatic respondent export to Google Sheets
ABOUTME: Debounces requests through Redis and hands the export to a Celery task"""

from __future__ import annotations

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


def request_auto_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    redis_client: Redis | None = None,
) -> bool:
    """Ask for the assembly's respondents to be exported again, if auto-export is on.

    Called by every service that changes what the export would contain. It is a
    side effect of someone else's request - a member of the public registering,
    an organiser editing - so it never raises: Redis or broker trouble is logged
    and the caller's work goes ahead regardless. Returns whether a task was
    queued, which is False when auto-export is off, when one is already
    pending, or when scheduling failed.

    Candidate for a ``RespondentsChanged`` domain event once the UnitOfWork
    collects events and dispatches them after commit; until then each writer
    calls this directly.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    if config is None or not config.auto_export:
        return False
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
