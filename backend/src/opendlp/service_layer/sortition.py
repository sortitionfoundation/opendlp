"""ABOUTME: Sortition service for managing selection tasks and background job coordination
ABOUTME: Provides high-level functions for starting and monitoring Celery-based selection workflows"""

import contextlib
import csv
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from typing import Any

import structlog
from sortition_algorithms import RunReport, adapters
from sortition_algorithms.errors import SortitionBaseError
from sortition_algorithms.features import FeatureCollection
from sortition_algorithms.people import People
from sqlalchemy.orm.attributes import flag_modified

from opendlp import config
from opendlp.adapters.sortition_data_adapter import DB_ID_COLUMN, OpenDLPDataAdapter
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import target_categories_to_snapshot
from opendlp.domain.value_objects import (
    DB_SELECTION_TASK_TYPES,
    ManageOldTabsState,
    ManageOldTabsStatus,
    SelectionRunStatus,
    SelectionTaskType,
)
from opendlp.service_layer.error_translation import translate_sortition_error
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InvalidSelection,
    SelectionRunRecordNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.respondent_export_service import respondent_export_table
from opendlp.service_layer.task_runner import Dispatch, TaskDispatchError, TaskRunner, TaskStatus
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.service_layer.writing_guard import refuse_if_writing_run_unfinished
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)


_CSV_BOM = "﻿"


def _table_to_csv(table: list[list[str]]) -> str:
    """
    Convert tabular data to a CSV.

    We use the BOM because non-ASCII CSVs without a BOM will not be loaded
    properly by Excel.
    """
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for row in table:
        writer.writerow(row)
    return _CSV_BOM + output.getvalue()


def _get_selection_settings(assembly: Assembly) -> SelectionSettings:
    """Get selection settings from assembly, falling back to defaults."""
    if assembly.selection_settings is not None:
        return assembly.selection_settings
    return SelectionSettings.for_assembly(assembly)


def _commit_and_dispatch(uow: AbstractUnitOfWork, record: SelectionRunRecord, dispatch: Dispatch) -> None:
    """Commit the new run record, then send its task.

    The commit comes first so the worker can find the record the task reports
    into. If sending fails, the record is marked FAILED - so the assembly is not
    held for a task that will never run - and TaskDispatchError is raised for
    the route to show.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    uow.selection_run_records.add(record)
    uow.commit()
    try:
        dispatch()
    except Exception as exc:
        _mark_task_as_failed(
            uow,
            record,
            error_msg=_("The task could not be started. Please try again."),
            technical_msg=f"Dispatch failed: {exc!r}",
            celery_state="DISPATCH_FAILED",
        )
        raise TaskDispatchError() from exc


@require_assembly_permission(can_manage_assembly)
def start_gsheet_load_task(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, *, task_runner: TaskRunner
) -> uuid.UUID:
    """
    Start a Google Sheets load task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to load data for
        task_runner: Sends the task to a worker

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    sel_settings = _get_selection_settings(assembly)
    try:
        data_source = gsheet.to_data_source(for_replacements=False, id_column=sel_settings.id_column)
        settings_obj = sel_settings.to_settings()
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    task_id = uuid.uuid4()
    dispatch = task_runner.load_gsheet(task_id=task_id, data_source=data_source, settings=settings_obj)
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=SelectionTaskType.LOAD_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=["Task submitted for Google Sheets loading"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_select_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    test_selection: bool = False,
    *,
    task_runner: TaskRunner,
    time_limit: int | None = None,
    soft_time_limit: int | None = None,
) -> uuid.UUID:
    """Start a Google Sheets selection task for an assembly.

    ``time_limit`` and ``soft_time_limit`` (seconds) bound how long the worker
    lets the task run; the monitor sets them so a stuck run cannot outlive it.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if assembly.number_to_select < 1:
        raise InvalidSelection(_("The project needs a panel size above zero before a selection can run"))

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    sel_settings = _get_selection_settings(assembly)
    refuse_if_writing_run_unfinished(uow, assembly_id)

    try:
        data_source = gsheet.to_data_source(for_replacements=False, id_column=sel_settings.id_column)
        settings_obj = sel_settings.to_settings()
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    task_id = uuid.uuid4()
    task_type = SelectionTaskType.TEST_SELECT_GSHEET if test_selection else SelectionTaskType.SELECT_GSHEET
    log_msg = (
        "Task submitted for Google Sheets TEST selection"
        if test_selection
        else "Task submitted for Google Sheets selection"
    )
    dispatch = task_runner.run_select(
        task_id=task_id,
        data_source=data_source,
        number_people_wanted=assembly.number_to_select,
        settings=settings_obj,
        test_selection=test_selection,
        gen_rem_tab=gsheet.generate_remaining_tab,
        time_limit=time_limit,
        soft_time_limit=soft_time_limit,
    )
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=task_type,
        status=SelectionRunStatus.PENDING,
        log_messages=[log_msg],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_replace_load_task(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, *, task_runner: TaskRunner
) -> uuid.UUID:
    """
    Start a Google Sheets load task for an assembly's replacement data.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to load replacement data for
        task_runner: Sends the task to a worker

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    sel_settings = _get_selection_settings(assembly)
    try:
        data_source = gsheet.to_data_source(for_replacements=True, id_column=sel_settings.id_column)
        settings_obj = sel_settings.to_settings()
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    task_id = uuid.uuid4()
    dispatch = task_runner.load_gsheet(task_id=task_id, data_source=data_source, settings=settings_obj)
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=["Task submitted for Google Sheets replacement data loading"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_replace_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    number_to_select: int,
    *,
    task_runner: TaskRunner,
) -> uuid.UUID:
    """
    Start a Google Sheets replacement selection task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to run replacement selection for
        number_to_select: Number of people to select in the replacement selection
        task_runner: Sends the task to a worker

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    sel_settings = _get_selection_settings(assembly)
    refuse_if_writing_run_unfinished(uow, assembly_id)

    try:
        data_source = gsheet.to_data_source(for_replacements=True, id_column=sel_settings.id_column)
        settings_obj = sel_settings.to_settings()
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    task_id = uuid.uuid4()
    dispatch = task_runner.run_select(
        task_id=task_id,
        data_source=data_source,
        number_people_wanted=number_to_select,
        settings=settings_obj,
        test_selection=False,
        gen_rem_tab=gsheet.generate_remaining_tab,
        for_replacements=True,
    )
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
        status=SelectionRunStatus.PENDING,
        log_messages=[f"Task submitted for Google Sheets replacement selection of {number_to_select} people"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_gsheet_manage_tabs_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    dry_run: bool = True,
    *,
    task_runner: TaskRunner,
) -> uuid.UUID:
    """
    Start a Google Sheets tab management task for an assembly.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the task (checked for permissions)
        assembly_id: ID of assembly to manage tabs for
        dry_run: If True, list tabs without deleting. If False, delete them.
        task_runner: Sends the task to a worker

    Returns:
        task_id: UUID of the created task for tracking

    Raises:
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet configuration not found
        InsufficientPermissions: If user cannot manage the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Get assembly and validate gsheet configuration exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if not gsheet:
        raise GoogleSheetConfigNotFoundError(f"No Google Sheets configuration found for assembly {assembly_id}")

    if not dry_run:
        refuse_if_writing_run_unfinished(uow, assembly_id)

    try:
        data_source = gsheet.to_data_source(for_replacements=False)
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    task_id = uuid.uuid4()
    dispatch = task_runner.manage_old_tabs(task_id=task_id, data_source=data_source, dry_run=dry_run)
    action = "listing" if dry_run else "deleting"
    task_type = SelectionTaskType.LIST_OLD_TABS if dry_run else SelectionTaskType.DELETE_OLD_TABS
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=task_type,
        status=SelectionRunStatus.PENDING,
        log_messages=[f"Task submitted for {action} old output tabs"],
        settings_used=gsheet.dict_for_json(),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@dataclass
class CheckDataResult:
    """Result of validating targets and respondents against selection settings."""

    success: bool
    errors: list[str]
    features_report_html: str
    people_report_html: str
    num_features: int
    num_people: int


@require_assembly_permission(can_manage_assembly)
def check_db_selection_data(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> CheckDataResult:
    """Synchronously validate targets and respondents against selection settings.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    sel_settings = _get_selection_settings(assembly)

    check_errors: list[str] = []
    features = None
    people = None
    features_report_html = ""
    people_report_html = ""

    try:
        settings_obj = sel_settings.to_settings(id_column=DB_ID_COLUMN)
    except SortitionBaseError as e:
        check_errors.append(translate_sortition_error(e))
        return CheckDataResult(
            success=False,
            errors=check_errors,
            features_report_html="",
            people_report_html="",
            num_features=0,
            num_people=0,
        )

    data_source = OpenDLPDataAdapter(uow, assembly_id)
    select_data = adapters.SelectionData(data_source)

    try:
        features, f_report = select_data.load_features(assembly.number_to_select)
        features_report_html = translate_run_report_to_html(f_report)
    except SortitionBaseError as e:
        check_errors.append(translate_sortition_error(e))

    if features is not None:
        try:
            people, p_report = select_data.load_people(settings_obj, features)
            people_report_html = translate_run_report_to_html(p_report)
        except SortitionBaseError as e:
            check_errors.append(translate_sortition_error(e))

    return CheckDataResult(
        success=not check_errors,
        errors=check_errors,
        features_report_html=features_report_html,
        people_report_html=people_report_html,
        num_features=len(features) if features else 0,
        num_people=people.count if people else 0,
    )


@require_assembly_permission(can_manage_assembly)
def start_db_select_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    test_selection: bool = False,
    *,
    task_runner: TaskRunner,
) -> uuid.UUID:
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if assembly.number_to_select < 1:
        raise InvalidSelection(_("The project needs a panel size above zero before a selection can run"))

    sel_settings = _get_selection_settings(assembly)
    try:
        settings_obj = sel_settings.to_settings(id_column=DB_ID_COLUMN)
    except SortitionBaseError as e:
        raise InvalidSelection(str(e)) from e

    refuse_if_writing_run_unfinished(uow, assembly_id)

    task_id = uuid.uuid4()
    task_type = SelectionTaskType.TEST_SELECT_FROM_DB if test_selection else SelectionTaskType.SELECT_FROM_DB
    log_msg = (
        "Task submitted for database TEST selection" if test_selection else "Task submitted for database selection"
    )

    target_categories = uow.target_categories.get_by_assembly_id(assembly_id)
    dispatch = task_runner.run_select_from_db(
        task_id=task_id,
        assembly_id=assembly_id,
        number_people_wanted=assembly.number_to_select,
        settings=settings_obj,
        test_selection=test_selection,
    )
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=task_type,
        status=SelectionRunStatus.PENDING,
        log_messages=[log_msg],
        settings_used={
            "id_column": settings_obj.id_column,
            "selection_algorithm": settings_obj.selection_algorithm,
            "check_same_address": settings_obj.check_same_address,
            "check_same_address_columns": settings_obj.check_same_address_columns,
            "columns_to_keep": settings_obj.columns_to_keep,
        },
        targets_used=target_categories_to_snapshot(target_categories),
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


@require_assembly_permission(can_manage_assembly)
def start_db_replace_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    number_to_select: int,
    targets_snapshot: list[dict[str, Any]],
    replacement_info: dict[str, Any],
    *,
    task_runner: TaskRunner,
) -> uuid.UUID:
    """Start a replacement selection over the database.

    ``targets_snapshot`` is the replacement targets the algorithm will run on,
    in the shape target_categories_to_snapshot() produces, with the calculated
    values alongside the used ones. ``replacement_info`` is the headline
    arithmetic (places held, places to fill, the number used) and is stored
    under settings_used["replacement"].

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if number_to_select < 1:
        raise InvalidSelection(_("The number of replacements to select must be at least one"))

    sel_settings = _get_selection_settings(assembly)
    try:
        settings_obj = sel_settings.to_settings(id_column=DB_ID_COLUMN)
    except SortitionBaseError as e:
        raise InvalidSelection(translate_sortition_error(e)) from e

    refuse_if_writing_run_unfinished(uow, assembly_id)

    task_id = uuid.uuid4()
    dispatch = task_runner.run_select_from_db(
        task_id=task_id,
        assembly_id=assembly_id,
        number_people_wanted=number_to_select,
        settings=settings_obj,
        test_selection=False,
        targets_snapshot=targets_snapshot,
    )
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=task_id,
        celery_task_id=str(task_id),
        task_type=SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
        status=SelectionRunStatus.PENDING,
        log_messages=[f"Task submitted for database replacement selection of {number_to_select} people"],
        settings_used={
            "id_column": settings_obj.id_column,
            "selection_algorithm": settings_obj.selection_algorithm,
            "check_same_address": settings_obj.check_same_address,
            "check_same_address_columns": settings_obj.check_same_address_columns,
            "columns_to_keep": settings_obj.columns_to_keep,
            "replacement": replacement_info,
        },
        targets_used=targets_snapshot,
        user_id=user_id,
    )
    _commit_and_dispatch(uow, record, dispatch)

    return task_id


def get_selected_respondents(uow: AbstractUnitOfWork, record: SelectionRunRecord) -> list[Respondent]:
    """The respondents a finished run selected, ordered by external ID.

    Respondents deleted since the run are included; anyone whose row has gone
    entirely is left out. Returns an empty list for a run that has no selected
    panel yet, and for a run that did not select from the database: the people
    a Google Sheets run selected are rows of the spreadsheet, not respondents.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if record.task_type not in DB_SELECTION_TASK_TYPES or not record.selected_ids:
        return []
    return uow.respondents.get_by_external_ids(record.assembly_id, list(record.selected_ids[0]))


def generate_selection_csvs(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    task_id: uuid.UUID,
) -> tuple[str, str]:
    """The people a finished run selected, and those it left, as two CSVs.

    Both carry the columns of the respondents export, and show each respondent
    as they are now rather than as they were when the run finished. Someone
    whose details have been deleted since keeps their row, with the external ID
    and the status alone.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    record = uow.selection_run_records.get_by_task_id(task_id)
    if not record:
        raise SelectionRunRecordNotFoundError(f"SelectionRunRecord {task_id} not found")
    if not record.selected_ids or record.remaining_ids is None:
        raise InvalidSelection(_("Selection has not completed — no results to download"))
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    def csv_of(external_ids: list[str]) -> str:
        respondents = uow.respondents.get_by_external_ids(assembly_id, external_ids)
        table = respondent_export_table(uow, assembly, respondents)
        return _table_to_csv([table.headers, *table.rows])

    return csv_of(list(record.selected_ids[0])), csv_of(list(record.remaining_ids))


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


def _process_final_result(task_status: TaskStatus, run_record: SelectionRunRecord) -> RunResult:
    """Turn a successful task's return value into the RunResult for its task type."""
    final_result = task_status.value
    assert final_result
    if run_record.task_type in (
        SelectionTaskType.LOAD_GSHEET,
        SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
    ):
        success, features, people, _, run_report = final_result
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
        SelectionTaskType.SELECT_FROM_DB,
        SelectionTaskType.TEST_SELECT_FROM_DB,
        SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
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


def get_selection_run_status(uow: AbstractUnitOfWork, task_id: uuid.UUID, *, task_runner: TaskRunner) -> RunResult:
    """
    Get the status of a selection run task.

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task to check - this is the SelectionRunRecord task_id
        task_runner: Asked for a finished task's return value

    Returns:
        SelectionRunRecord with current status, or None if not found

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    run_record = uow.selection_run_records.get_by_task_id(task_id)
    # this is the null result, effectively
    result = RunResult(run_record=run_record)
    if run_record:
        # The DB record is the authoritative source for log messages — every
        # _append_run_log call commits an update — so always read from there
        # first. The task runner is only consulted to detect a successful
        # task whose final return value still lives in the result backend.
        result.log_messages = list(run_record.log_messages)

        # Old records whose task could not be created have no Celery id, and
        # there is nothing to ask the backend about.
        if run_record.celery_task_id:
            task_status = task_runner.status(run_record.celery_task_id)
            if task_status.successful:
                # The backend still has the result — pull the typed final value out so
                # the caller gets features/people/selected_ids etc.
                return _process_final_result(task_status, run_record)

        if run_record.run_report:
            result.run_report = run_record.run_report
            # set success - the default is None, for not finished at all
            if run_record.is_completed:
                result.success = True
            if run_record.is_failed:
                result.success = False
    return result


@require_assembly_permission(can_manage_assembly)
def cancel_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    task_runner: TaskRunner,
) -> None:
    """
    Cancel a running or pending task.

    Args:
        uow: Unit of work for database operations
        user_id: ID of user requesting the cancellation (checked for permissions)
        assembly_id: ID of assembly (for permission checking)
        task_id: UUID of the task to cancel
        task_runner: Stops the task if a worker has it

    Raises:
        NotFoundError: If task not found
        InvalidSelection: If task has already finished
        InsufficientPermissions: If user cannot manage the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    logger.info(f"User {user_id} attempting to cancel task {task_id}")

    # Get the task record
    run_record = uow.selection_run_records.get_by_task_id(task_id)
    if not run_record:
        raise InvalidSelection(_("Task not found"))

    # Check if task has already finished
    if run_record.has_finished:
        raise InvalidSelection(_("Cannot cancel task — it has already finished"))

    # Get user info for the cancellation message
    user = uow.users.get(user_id)
    user_name = user.display_name if user else "Unknown User"

    # Revoke the Celery task
    try:
        task_runner.revoke(run_record.celery_task_id)
        logger.info(f"Successfully revoked Celery task {run_record.celery_task_id}")
    except Exception as e:
        # Log the error but continue - we still want to mark as CANCELLED in DB
        logger.warning(f"Failed to revoke Celery task {run_record.celery_task_id}: {e}")

    # Update the record
    run_record.status = SelectionRunStatus.CANCELLED
    run_record.completed_at = datetime.now(UTC)
    run_record.error_message = _("Task cancelled by %(user_name)s", user_name=user_name)
    run_record.log_messages.append(f"Task cancelled by {user_name} at {datetime.now(UTC).isoformat()}")

    # Only flag_modified if object is attached to SQLAlchemy session (not needed for fake UoW in tests)
    if hasattr(run_record, "_sa_instance_state"):
        flag_modified(run_record, "log_messages")

    uow.selection_run_records.add(run_record)
    uow.commit()

    logger.info(f"Task {task_id} successfully cancelled by user {user_id}")


def get_manage_old_tabs_status(result: RunResult) -> ManageOldTabsStatus:
    """
    Get the ManageOldTabsStatus value, based on the run result.

    This is used in the template to work out what to show to the user.
    """
    assert result.run_record is not None
    if result.run_record.is_failed:
        return ManageOldTabsStatus(ManageOldTabsState.ERROR)
    if result.run_record.task_type == SelectionTaskType.LIST_OLD_TABS:
        if result.run_record.has_finished:
            return ManageOldTabsStatus(ManageOldTabsState.LIST_COMPLETED)
        return ManageOldTabsStatus(ManageOldTabsState.LIST_RUNNING)
    assert result.run_record.task_type == SelectionTaskType.DELETE_OLD_TABS
    if result.run_record.has_finished:
        return ManageOldTabsStatus(ManageOldTabsState.DELETE_COMPLETED)
    return ManageOldTabsStatus(ManageOldTabsState.DELETE_RUNNING)


# Task types corresponding to the Initial Selection card's buttons on the selection page
# (both GSheet and CSV branches). When a task of one of these types is pending/running for
# an assembly, the card footer shows a single "View Running Selection" button instead of
# the check/test/run buttons. A database replacement run writes to the same respondent
# rows, so it counts too: both cards wait for it.
_INITIAL_SELECTION_TASK_TYPES = frozenset({
    SelectionTaskType.LOAD_GSHEET,
    SelectionTaskType.SELECT_GSHEET,
    SelectionTaskType.TEST_SELECT_GSHEET,
    SelectionTaskType.SELECT_FROM_DB,
    SelectionTaskType.TEST_SELECT_FROM_DB,
    SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
})


def get_active_initial_selection_run_id(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> uuid.UUID | None:
    """Return the task id of an unfinished initial-selection task for this assembly, or None.

    Used by the selection page to swap the check/test/run buttons for a single
    "View Running Selection" button while a task is pending or running.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    unfinished = uow.selection_run_records.get_unfinished_for_assembly(assembly_id, _INITIAL_SELECTION_TASK_TYPES)
    if not unfinished:
        return None
    return unfinished[0].task_id


def get_latest_run_for_assembly(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> SelectionRunRecord | None:
    """
    Get the most recent selection run for an assembly.

    Args:
        uow: Unit of work for database operations
        assembly_id: UUID of the assembly

    Returns:
        Most recent SelectionRunRecord for the assembly, or None if no runs exist

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    return uow.selection_run_records.get_latest_for_assembly(assembly_id)


# The runs the targets page can offer to re-run, once the targets that made them
# fail have been adjusted.
_RERUNNABLE_FROM_TARGETS_TASK_TYPES = frozenset({
    SelectionTaskType.SELECT_FROM_DB,
    SelectionTaskType.TEST_SELECT_FROM_DB,
})


def get_selection_to_rerun(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, task_id: uuid.UUID
) -> SelectionRunRecord | None:
    """The failed selection `task_id` names, if the targets page may re-run it, or None.

    It must be on this assembly, have failed, and be an initial or test
    selection over the database. A re-run starts the same kind of selection,
    so a test run is re-run as a test run - which is why the run is looked up
    rather than its kind taken from the request.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    record = uow.selection_run_records.get_by_task_id(task_id)
    if record is None or record.assembly_id != assembly_id:
        return None
    if not record.is_failed or record.task_type not in _RERUNNABLE_FROM_TARGETS_TASK_TYPES:
        return None
    return record.create_detached_copy()


def _mark_task_as_failed(
    uow: AbstractUnitOfWork,
    run_record: SelectionRunRecord,
    error_msg: str,
    technical_msg: str,
    celery_state: str,
) -> None:
    """
    Update a SelectionRunRecord to FAILED status with error details.

    Args:
        uow: Unit of work for database operations
        run_record: The record to update
        error_msg: User-friendly error message
        technical_msg: Technical details for logs
        celery_state: The Celery state that triggered this failure

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Log technical details
    logger.warning(
        "Marking task as failed:",
        run_id=run_record.task_id,
        celery_id=run_record.celery_task_id,
        celery_state=celery_state,
        details=technical_msg,
    )

    # Update record with user-friendly message
    run_record.status = SelectionRunStatus.FAILED
    run_record.error_message = error_msg + " " + _("Please contact the administrators if this problem persists.")
    run_record.log_messages.append(f"ERROR: {error_msg}")
    run_record.completed_at = datetime.now(UTC)

    # flag_modified only works for SQLAlchemy-managed instances
    # In unit tests with plain Python objects, this will fail, so we catch it
    with contextlib.suppress(AttributeError):
        flag_modified(run_record, "log_messages")

    uow.selection_run_records.add(run_record)
    uow.commit()


def _get_task_status(run_record: SelectionRunRecord, task_id: uuid.UUID, task_runner: TaskRunner) -> TaskStatus | None:
    # Check if celery_task_id is valid before querying Celery
    if not run_record.celery_task_id:
        # Task was created without a Celery task ID (shouldn't happen in production)
        # This can happen in tests or if task creation failed
        logger.warning(
            "Task has no Celery task ID, cannot check health",
            run_id=task_id,
            db_status=run_record.status.value,
        )
        return None  # Can't check Celery without a task ID

    # Query Celery for task state
    try:
        return task_runner.status(run_record.celery_task_id)
    except Exception as exc:
        # Handle invalid celery_task_id or other Celery errors
        logger.error(
            "Error querying Celery for task state",
            run_id=task_id,
            celery_id=run_record.celery_task_id,
            error=str(exc),
        )
        return None  # Can't determine health if Celery query fails


def _fail_if_timed_out(uow: AbstractUnitOfWork, run_record: SelectionRunRecord, timeout_hours: int | None) -> bool:
    """Mark a record FAILED if it is older than the overall task timeout. Returns True if it did."""
    timeout_hrs = timeout_hours if timeout_hours is not None else config.get_task_timeout_hours()
    if not (timeout_hrs and run_record.created_at):
        return False
    elapsed = datetime.now(UTC) - run_record.created_at
    if elapsed.total_seconds() <= timeout_hrs * 3600:
        return False
    _mark_task_as_failed(
        uow,
        run_record,
        error_msg=_("Task exceeded timeout"),
        technical_msg=f"Task timed out after {timeout_hrs} hours",
        celery_state="TIMEOUT",
    )
    return True


def _fail_if_stuck_pending(
    uow: AbstractUnitOfWork, run_record: SelectionRunRecord, pending_timeout_minutes: int | None, celery_state: str
) -> bool:
    """Mark a record FAILED if it has sat in PENDING past the pending timeout. Returns True if it did.

    A record still PENDING this long was never picked up by a worker, and it
    must not keep blocking the other writing tasks on its assembly.
    """
    pending_mins = (
        pending_timeout_minutes if pending_timeout_minutes is not None else config.PENDING_TASK_TIMEOUT_MINUTES
    )
    if not (run_record.is_pending and pending_mins and run_record.created_at):
        return False
    elapsed = datetime.now(UTC) - run_record.created_at
    if elapsed.total_seconds() <= pending_mins * 60:
        return False
    _mark_task_as_failed(
        uow,
        run_record,
        error_msg=_("Task did not start"),
        technical_msg=f"Still PENDING after {pending_mins} minutes. Celery state: {celery_state}",
        celery_state=celery_state,
    )
    return True


def check_and_update_task_health(
    uow: AbstractUnitOfWork,
    task_id: uuid.UUID,
    timeout_hours: int | None = None,
    pending_timeout_minutes: int | None = None,
    *,
    task_runner: TaskRunner,
) -> None:
    """
    Check if a task is still alive and update its status if it has died.

    Only checks tasks in PENDING or RUNNING state.
    Handles multiple failure scenarios:
    - Task is PENDING but Celery says it FAILED/REVOKED/REJECTED
    - Task is still PENDING after the pending timeout (never picked up)
    - Task is RUNNING but Celery has no record (>24hrs old, died)
    - Task is RUNNING but Celery says FAILURE/REVOKED/REJECTED
    - Task exceeded timeout (if configured)

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task (SelectionRunRecord.task_id)
        timeout_hours: Optional timeout in hours (overrides env config)
        pending_timeout_minutes: Optional pending timeout in minutes (overrides the config constant)
        task_runner: Asked what the task backend knows about the task

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    run_record = uow.selection_run_records.get_by_task_id(task_id)

    if not run_record or run_record.has_finished:
        return  # Nothing to check

    # Check timeout first
    if _fail_if_timed_out(uow, run_record, timeout_hours):
        return

    task_status = _get_task_status(run_record, task_id, task_runner)
    celery_state = task_status.state if task_status else ""
    if _fail_if_stuck_pending(uow, run_record, pending_timeout_minutes, celery_state):
        return
    if not task_status:
        return

    # Log current state for debugging
    logger.debug(
        "Task health check",
        run_id=task_id,
        celery_id=run_record.celery_task_id,
        celery_state=celery_state,
        db_status=run_record.status.value,
    )

    # Decision matrix based on DB status and Celery state
    if run_record.is_pending:
        if celery_state in ("FAILURE", "REVOKED", "REJECTED"):
            # Task failed before it even started running
            exc_info = task_status.error
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg=_("Task failed to start"),
                technical_msg=f"Celery state: {celery_state}, Exception: {exc_info}",
                celery_state=celery_state,
            )

    elif run_record.is_running:
        if celery_state in ("FAILURE", "REVOKED", "REJECTED"):
            # Task crashed or was killed
            exc_info = task_status.error
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg=_("Task stopped unexpectedly"),
                technical_msg=f"Celery state: {celery_state}, Exception: {exc_info}",
                celery_state=celery_state,
            )

        elif celery_state == "PENDING" and run_record.celery_task_id:
            # Celery has forgotten the task (likely >24hrs) but DB says RUNNING
            # This means the worker died without updating status
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg=_("Task stopped unexpectedly"),
                technical_msg=(
                    "Task shows RUNNING in database but Celery has no record. Worker likely crashed or was killed."
                ),
                celery_state="UNKNOWN",
            )

        # SUCCESS and STARTED states are fine, let normal polling handle them
