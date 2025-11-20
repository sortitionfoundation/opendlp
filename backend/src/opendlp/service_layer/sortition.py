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

    if assembly.number_to_select < 1:
        raise InvalidSelection(_("The assembly needs to have a non-zero number to select before we can do selection"))

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
    run_report: RunReport = field(default_factory=RunReport)
    log_messages: list[str] = field(default_factory=list)
    success: bool | None = None


@dataclass
class LoadRunResult(RunResult):
    features: FeatureCollection | None = None
    people: People | None = None


@dataclass
class SelectionRunResult(RunResult):
    selected_ids: list[frozenset[str]] = field(default_factory=list)


@dataclass
class TabManagementResult(RunResult):
    tab_names: list[str] = field(default_factory=list)


def _process_celery_final_result(celery_result: AsyncResult, run_record: SelectionRunRecord) -> RunResult:
    final_result = celery_result.get()
    assert final_result
    if run_record.task_type in (
        SelectionTaskType.LOAD_GSHEET,
        SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
    ):
        success, features, people, run_report = final_result
        return LoadRunResult(
            run_record=run_record,
            run_report=run_report,
            log_messages=run_record.log_messages,
            success=success,
            features=features,
            people=people,
        )
    if run_record.task_type in (
        SelectionTaskType.SELECT_GSHEET,
        SelectionTaskType.TEST_SELECT_GSHEET,
        SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
    ):
        success, selected_ids, run_report = final_result
        return SelectionRunResult(
            run_record=run_record,
            run_report=run_report,
            log_messages=run_record.log_messages,
            success=success,
            selected_ids=selected_ids,
        )
    if run_record.task_type in (
        SelectionTaskType.DELETE_OLD_TABS,
        SelectionTaskType.LIST_OLD_TABS,
    ):
        success, tab_names, run_report = final_result
        return TabManagementResult(
            run_record=run_record,
            run_report=run_report,
            log_messages=run_record.log_messages,
            success=success,
            tab_names=tab_names,
        )
    raise Exception(
        f"Unexpected task_type {run_record.task_type} found in run record {run_record.task_id} for select task"
    )


def get_selection_run_status(uow: AbstractUnitOfWork, task_id: uuid.UUID) -> RunResult:
    """
    Get the status of a selection run task.

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task to check - this is the SelectionRunRecord task_id

    Returns:
        SelectionRunRecord with current status, or None if not found
    """
    run_record = uow.selection_run_records.get_by_task_id(task_id)
    # this is the null result, effectively
    result = RunResult(run_record=run_record)
    if run_record:
        celery_result = app.app.AsyncResult(run_record.celery_task_id)

        # We will always get a result object back here, even if celery has no
        # record of the task id. (By default, celery will forget the results adapter
        # 24 hours, so this is quite possible if looking at an old run.) So we:
        # - first check if it is successful - which means it was successful, and the result
        #   is still tracked by celery. Then we can get the results of the function that
        #   was run.
        # - if not and it is started, then we can check for any log messages that may have
        #   been written.
        # - if not, then either it is pending, or long finished and celery forgot it. In that
        #   case we check if the RunReport was saved on the run record. If it was, that means
        #   the task was long finished and celery forgot it.

        if celery_result.id and celery_result.successful():
            # The task was successful, celery still has the result.
            return _process_celery_final_result(celery_result, run_record)
        elif celery_result.id and celery_result.state == "STARTED":
            # The task has started but not finished.
            result.log_messages = celery_result.info.get("all_messages", [])
        elif run_record.run_report:
            # The task finished long ago and celery has forgotten it. But we still have the run report
            result.run_report = run_record.run_report
            result.log_messages = run_record.log_messages
            # set success - the default is None, for not finished at all
            if run_record.is_completed:
                result.success = True
            if run_record.is_failed:
                result.success = False
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
