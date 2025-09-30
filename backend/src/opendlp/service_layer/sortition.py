"""ABOUTME: Sortition service for managing selection tasks and background job coordination
ABOUTME: Provides high-level functions for starting and monitoring Celery-based selection workflows"""

import uuid

from celery.result import AsyncResult
from sortition_algorithms import RunReport

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.entrypoints.celery import app, tasks
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


@require_assembly_permission(can_manage_assembly)
def start_gsheet_load_task(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> uuid.UUID:
    """
    Start a Google Sheets load task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to load data for

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        ValueError: If assembly or gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise ValueError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise ValueError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type="load_gsheet",
        status="pending",
        log_messages=["Task submitted for Google Sheets loading"],
        settings_used=gsheet.dict_for_json(),
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    # TODO: should this be behind another adapter? That comes from bootstrap?
    # would be handy for unit tests
    result = tasks.load_gsheet.delay(
        task_id=task_id,
        adapter=gsheet.to_adapter(),
        feature_tab_name=gsheet.select_targets_tab,
        respondents_tab_name=gsheet.select_registrants_tab,
        settings=gsheet.to_settings(),
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_select_task(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> uuid.UUID:
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise ValueError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise ValueError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type="select_gsheet",
        status="pending",
        log_messages=["Task submitted for Google Sheets selection"],
        settings_used=gsheet.dict_for_json(),
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    # TODO: should this be behind another adapter? That comes from bootstrap?
    # would be handy for unit tests
    result = tasks.run_select.delay(
        task_id=task_id,
        adapter=gsheet.to_adapter(),
        feature_tab_name=gsheet.select_targets_tab,
        respondents_tab_name=gsheet.select_registrants_tab,
        number_people_wanted=assembly.number_to_select,
        settings=gsheet.to_settings(),
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


def get_selection_run_status(
    uow: AbstractUnitOfWork, task_id: uuid.UUID
) -> tuple[SelectionRunRecord | None, list[str], RunReport]:
    """
    Get the status of a selection run task.

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task to check - this is the SelectionRunRecord task_id

    Returns:
        SelectionRunRecord with current status, or None if not found
    """
    celery_result: AsyncResult | None = None
    run_record: SelectionRunRecord | None = uow.selection_run_records.get_by_task_id(task_id)
    run_report: RunReport = RunReport()
    log_messages: list[str] = []
    if run_record:
        celery_result = app.app.AsyncResult(run_record.celery_task_id)

        # TODO: extract features and people from the result
        # might mean we need to have separate methods for load_gsheet and run_selection
        if celery_result and celery_result.id:
            if celery_result.successful():
                final_result = celery_result.get()
                assert final_result
                if run_record.task_type == "load_gsheet":
                    _, _, _, run_report = final_result
                elif run_record.task_type == "select_gsheet":
                    _, _, run_report = final_result
                else:
                    raise Exception(
                        f"Unknown task_type {run_record.task_type} found in run record {run_record.task_id}"
                    )
            elif celery_result.state == "PROGRESS":
                log_messages = celery_result.info.get("all_messages", [])
    return run_record, log_messages, run_report


def get_latest_run_for_assembly(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> SelectionRunRecord | None:
    """
    Get the most recent selection run for an assembly.

    Args:
        uow: Unit of work for database operations
        assembly_id: UUID of the assembly

    Returns:
        Most recent SelectionRunRecord for the assembly, or None if no runs exist
    """
    return uow.selection_run_records.get_latest_for_assembly(assembly_id)
