"""ABOUTME: Sortition service for managing selection tasks and background job coordination
ABOUTME: Provides high-level functions for starting and monitoring Celery-based selection workflows"""

import uuid
from dataclasses import dataclass, field

from celery.result import AsyncResult
from sortition_algorithms import RunReport
from sortition_algorithms.features import FeatureCollection
from sortition_algorithms.people import People

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import ManageOldTabsState, ManageOldTabsStatus, SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery import app, tasks
from opendlp.service_layer.exceptions import AssemblyNotFoundError, GoogleSheetConfigNotFoundError, InvalidSelection
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _


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
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type=SelectionTaskType.LOAD_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=["Task submitted for Google Sheets loading"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    # TODO: should this be behind another adapter? That comes from bootstrap?
    # would be handy for unit tests
    result = tasks.load_gsheet.delay(
        task_id=task_id,
        data_source=gsheet.to_data_source(for_replacements=False),
        settings=gsheet.to_settings(),
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_select_task(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, test_selection: bool = False
) -> uuid.UUID:
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if assembly.number_to_select is None or assembly.number_to_select < -1:
        raise InvalidSelection(_("The assembly needs to have a number to select before we can do selection"))

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()
    task_type = SelectionTaskType.TEST_SELECT_GSHEET if test_selection else SelectionTaskType.SELECT_GSHEET
    log_msg = (
        "Task submitted for Google Sheets TEST selection"
        if test_selection
        else "Task submitted for Google Sheets selection"
    )

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type=task_type,
        status=SelectionRunStatus.PENDING,
        log_messages=[log_msg],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    # TODO: should this be behind another adapter? That comes from bootstrap?
    # would be handy for unit tests
    result = tasks.run_select.delay(
        task_id=task_id,
        data_source=gsheet.to_data_source(for_replacements=False),
        number_people_wanted=assembly.number_to_select,
        settings=gsheet.to_settings(),
        test_selection=test_selection,
        gen_rem_tab=gsheet.generate_remaining_tab,
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_replace_load_task(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> uuid.UUID:
    """
    Start a Google Sheets load task for an assembly's replacement data.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to load replacement data for

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=["Task submitted for Google Sheets replacement data loading"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    result = tasks.load_gsheet.delay(
        task_id=task_id,
        data_source=gsheet.to_data_source(for_replacements=True),
        settings=gsheet.to_settings(),
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_replace_task(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, number_to_select: int
) -> uuid.UUID:
    """
    Start a Google Sheets replacement selection task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to run replacement selection for
        number_to_select: Number of people to select in the replacement selection

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=[f"Task submitted for Google Sheets replacement selection of {number_to_select} people"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    result = tasks.run_select.delay(
        task_id=task_id,
        data_source=gsheet.to_data_source(for_replacements=True),
        number_people_wanted=number_to_select,
        settings=gsheet.to_settings(),
        test_selection=False,
        gen_rem_tab=gsheet.generate_remaining_tab,
        for_replacements=True,
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_manage_tabs_task(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, dry_run: bool = True
) -> uuid.UUID:
    """
    Start a Google Sheets tab management task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to manage tabs for
        dry_run: If True, list tabs without deleting. If False, delete them.

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    # Create unique task ID
    task_id = uuid.uuid4()

    # Create SelectionRunRecord for tracking
    action = "listing" if dry_run else "deleting"
    task_type = SelectionTaskType.LIST_OLD_TABS if dry_run else SelectionTaskType.DELETE_OLD_TABS
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        task_type=task_type,
        status=SelectionRunStatus.PENDING,
        log_messages=[f"Task submitted for {action} old output tabs"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    uow.selection_run_records.add(record)
    uow.commit()

    # Submit Celery task
    result = tasks.manage_old_tabs.delay(
        task_id=task_id,
        data_source=gsheet.to_data_source(for_replacements=False),
        dry_run=dry_run,
    )
    record.celery_task_id = str(result.id)
    uow.selection_run_records.add(record)
    uow.commit()

    return task_id


@dataclass
class RunResult:
    run_record: SelectionRunRecord | None
    run_report: RunReport
    log_messages: list[str]
    success: bool | None


@dataclass
class LoadRunResult(RunResult):
    features: FeatureCollection | None = None
    people: People | None = None


@dataclass
class SelectionRunResult(RunResult):
    selected_ids: list[frozenset[str]]


@dataclass
class TabManagementResult(RunResult):
    tab_names: list[str] = field(default_factory=list)


def get_selection_run_status(uow: AbstractUnitOfWork, task_id: uuid.UUID) -> RunResult:
    """
    Get the status of a selection run task.

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task to check - this is the SelectionRunRecord task_id

    Returns:
        SelectionRunRecord with current status, or None if not found
    """
    celery_result: AsyncResult | None = None
    run_record = uow.selection_run_records.get_by_task_id(task_id)
    result = RunResult(
        run_record=run_record,
        run_report=RunReport(),
        log_messages=[],
        success=None,
    )
    if run_record:
        celery_result = app.app.AsyncResult(run_record.celery_task_id)

        # TODO: extract features and people from the result
        # might mean we need to have separate methods for load_gsheet and run_selection
        if celery_result:
            if celery_result.id and celery_result.successful():
                final_result = celery_result.get()
                assert final_result
                assert run_record is not None
                if run_record.task_type in (
                    SelectionTaskType.LOAD_GSHEET,
                    SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
                ):
                    success, features, people, run_report = final_result
                    load_result = LoadRunResult(
                        run_record=run_record,
                        run_report=run_report,
                        log_messages=[],
                        success=success,
                        features=features,
                        people=people,
                    )
                    result = load_result
                elif run_record.task_type in (
                    SelectionTaskType.SELECT_GSHEET,
                    SelectionTaskType.TEST_SELECT_GSHEET,
                    SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                ):
                    success, selected_ids, run_report = final_result
                    select_result = SelectionRunResult(
                        run_record=run_record,
                        run_report=run_report,
                        log_messages=[],
                        success=success,
                        selected_ids=selected_ids,
                    )
                    result = select_result
                elif run_record.task_type in (
                    SelectionTaskType.DELETE_OLD_TABS,
                    SelectionTaskType.LIST_OLD_TABS,
                ):
                    success, tab_names, run_report = final_result
                    tab_result = TabManagementResult(
                        run_record=run_record,
                        run_report=run_report,
                        log_messages=[],
                        success=success,
                        tab_names=tab_names,
                    )
                    result = tab_result
                else:  # pragma: no cover
                    raise Exception(
                        f"Unexpected task_type {run_record.task_type} found in "
                        f"run record {run_record.task_id} for select task"
                    )
            elif celery_result.id and celery_result.state == "PROGRESS":
                result.log_messages = celery_result.info.get("all_messages", [])
    return result


def get_manage_old_tabs_status(result: RunResult) -> ManageOldTabsStatus:
    """
    Get the ManageOldTabsStatus value, based on the run result.

    This is used in the template to work out what to show to the user.
    """
    assert result.run_record is not None
    if result.run_record.is_failed:
        return ManageOldTabsStatus(ManageOldTabsState.ERROR)
    elif result.run_record.task_type == SelectionTaskType.LIST_OLD_TABS:
        if result.run_record.has_finished:
            return ManageOldTabsStatus(ManageOldTabsState.LIST_COMPLETED)
        else:
            return ManageOldTabsStatus(ManageOldTabsState.LIST_RUNNING)
    else:
        assert result.run_record.task_type == SelectionTaskType.DELETE_OLD_TABS
        if result.run_record.has_finished:
            return ManageOldTabsStatus(ManageOldTabsState.DELETE_COMPLETED)
        else:
            return ManageOldTabsStatus(ManageOldTabsState.DELETE_RUNNING)


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
