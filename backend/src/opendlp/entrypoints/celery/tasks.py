import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import gspread
from celery import Task
from celery.signals import setup_logging
from sortition_algorithms import (
    RunReport,
    adapters,
    errors,
    people,
    run_stratification,
    selected_remaining_tables,
    settings,
)
from sortition_algorithms.features import FeatureCollection, maximum_selection, minimum_selection
from sortition_algorithms.utils import ReportLevel, override_logging_handlers
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

import opendlp.logging
from opendlp import config
from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.bootstrap import bootstrap
from opendlp.domain.value_objects import SelectionRunStatus
from opendlp.entrypoints.celery.app import app
from opendlp.entrypoints.context_processors import get_service_account_email
from opendlp.service_layer import password_reset_service
from opendlp.service_layer.exceptions import SelectionRunRecordNotFoundError
from opendlp.translations import gettext as _


@setup_logging.connect
def config_loggers(*args: Any, **kwargs: Any) -> None:
    opendlp.logging.logging_setup(config.get_log_level())


class SelectionRunRecordHandler(logging.Handler):
    """
    A logger that sends the log messages through Celery to the AsyncResult
    object.
    """

    def __init__(self, task_id: uuid.UUID, session_factory: sessionmaker | None = None) -> None:
        super().__init__()
        self.task_id = task_id
        self.setFormatter(logging.Formatter(fmt="%(message)s"))
        self.session_factory = session_factory

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        _append_run_log(self.task_id, [msg], session_factory=self.session_factory)


def _set_up_celery_logging(task_id: uuid.UUID, session_factory: sessionmaker | None = None) -> None:
    # get log messages written back as we go
    handler = SelectionRunRecordHandler(task_id, session_factory=session_factory)
    handler.setLevel(logging.DEBUG)
    override_logging_handlers([handler], [handler])


def _on_task_failure(self: Task | None, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
    """
    Callback executed when a Celery task fails.

    Note: This only fires if the worker process is alive when the exception occurs.
    Hard crashes (SIGKILL, OOM) won't trigger this callback.

    Args:
        self: Task instance (can be None in tests)
        exc: The exception that caused the failure
        task_id: Celery task ID (not our task_id UUID)
        args: Task positional arguments
        kwargs: Task keyword arguments
        einfo: Exception info object
    """
    # Extract our task_id from kwargs (the SelectionRunRecord task_id)
    our_task_id = kwargs.get("task_id")
    if not our_task_id:
        logging.error(f"Task {task_id} failed but no task_id in kwargs")
        return

    session_factory = kwargs.get("session_factory")

    # Format error details
    error_msg = f"Task failed with exception: {type(exc).__name__}"
    technical_msg = f"{type(exc).__name__}: {exc}"
    if einfo:
        technical_msg += f"\n{einfo}"

    logging.error(
        f"Celery task failure callback: our_task_id={our_task_id}, celery_task_id={task_id}, exception={technical_msg}"
    )

    # Update the database record
    try:
        with bootstrap(session_factory=session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(our_task_id)
            if record and not record.has_finished:
                record.status = SelectionRunStatus.FAILED
                record.error_message = f"{error_msg}. " + _(
                    "Please contact the administrators if this problem persists."
                )
                record.log_messages.append(f"ERROR: {error_msg}")
                record.completed_at = datetime.now(UTC)
                flag_modified(record, "log_messages")
                uow.commit()
    except Exception as update_exc:
        logging.error(f"Failed to update task record in failure callback: {update_exc}")


def _update_selection_record(
    task_id: uuid.UUID,
    status: SelectionRunStatus,
    log_message: str = "",
    log_messages: list[str] | None = None,
    error_message: str = "",
    completed_at: datetime | None = None,
    run_report: RunReport | None = None,
    selected_ids: list[list[str]] | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Update an existing SelectionRunRecord with progress information."""
    assert not (log_message and log_messages), "only use log_message or log_messages, not both"
    with bootstrap(session_factory=session_factory) as uow:
        # Get existing record (should always exist since created at submit time)
        record = uow.selection_run_records.get_by_task_id(task_id)

        if record is None:
            raise SelectionRunRecordNotFoundError(f"SelectionRunRecord with task_id {task_id} not found")

        # Update existing record
        record.status = status
        if log_message:
            record.log_messages.append(log_message)
            flag_modified(record, "log_messages")
        if log_messages:
            record.log_messages.extend(log_messages)
            flag_modified(record, "log_messages")
        if error_message:
            record.error_message = error_message
        if completed_at:
            record.completed_at = completed_at
        if run_report is not None:
            record.add_report(run_report)
            flag_modified(record, "run_report")
        if selected_ids is not None:
            record.selected_ids = selected_ids
            flag_modified(record, "selected_ids")

        uow.commit()


def _append_run_log(task_id: uuid.UUID, log_messages: list[str], session_factory: sessionmaker | None = None) -> None:
    """Add to the log while running"""
    _update_selection_record(
        task_id, status=SelectionRunStatus.RUNNING, log_messages=log_messages, session_factory=session_factory
    )


def _internal_load_gsheet(
    task_obj: Task,
    task_id: uuid.UUID,
    select_data: adapters.SelectionData,
    settings: settings.Settings,
    final_task: bool = True,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, FeatureCollection | None, people.People | None, people.People | None, RunReport]:
    data_source = select_data.data_source
    assert isinstance(data_source, adapters.GSheetDataSource | CSVGSheetDataSource)
    report = RunReport()
    # Update SelectionRunRecord to running status
    _update_selection_record(
        task_id=task_id,
        status=SelectionRunStatus.RUNNING,
        log_message=_("Starting Google Sheets load task"),
        session_factory=session_factory,
    )
    # check if we can even get the title
    try:
        # TODO: use data_source.get_title() once we have sortition_algorithms>0.10.21
        spreadsheet_title = data_source.spreadsheet.title
    except gspread.exceptions.SpreadsheetNotFound:
        msg = f"Spreadsheet not found, check URL: {data_source._g_sheet_name}"
        _update_selection_record(
            task_id,
            status=SelectionRunStatus.FAILED,
            log_message=msg,
            error_message=msg,
            completed_at=datetime.now(UTC),
            session_factory=session_factory,
        )
        return False, None, None, None, report

    try:
        _append_run_log(
            task_id,
            [
                _("Loading spreadsheet with title: %(title)s", title=spreadsheet_title),
                _("Loading targets from tab: %(tab_name)s", tab_name=data_source.feature_tab_name),
            ],
            session_factory=session_factory,
        )

        features, f_report = select_data.load_features()
        # print(f_report.as_text())
        report.add_report(f_report)
        task_obj.update_state(
            state="PROGRESS",
            meta={"features_status": f_report.as_text()},
        )
        assert features is not None

        num_features = len(features)
        num_values = sum(len(v) for v in features.values())
        min_select, max_select = minimum_selection(features), maximum_selection(features)
        _append_run_log(
            task_id,
            [
                _(
                    "Found %(num_features)s categories for targets with a total of %(num_values)s values.",
                    num_features=num_features,
                    num_values=num_values,
                ),
                _(
                    "Minimum selection for targets is %(min_select)s, maximum is %(max_select)s.",
                    min_select=min_select,
                    max_select=max_select,
                ),
                _("Loading people from tab: %(tab_name)s", tab_name=data_source.people_tab_name),
            ],
            session_factory=session_factory,
        )

        people, p_report = select_data.load_people(settings, features)
        report.add_report(p_report)
        task_obj.update_state(
            state="PROGRESS",
            meta={"people_status": p_report.as_text()},
        )
        assert people is not None
        _append_run_log(
            task_id,
            [
                _("Loaded %(count)s people.", count=people.count),
            ],
            session_factory=session_factory,
        )

        if data_source.already_selected_tab_name:
            _append_run_log(
                task_id,
                [
                    _(
                        "Loading already selected from tab: %(tab_name)s",
                        tab_name=data_source.already_selected_tab_name,
                    ),
                ],
                session_factory=session_factory,
            )
        # always do this, as it gives a safe default
        already_selected, a_s_report = select_data.load_already_selected(settings, features)
        if data_source.already_selected_tab_name:
            report.add_report(a_s_report)
            task_obj.update_state(
                state="progress",
                meta={"already_selected_status": a_s_report.as_text()},
            )
            _append_run_log(
                task_id,
                [
                    _("Loaded %(count)s already selected people.", count=already_selected.count),
                ],
                session_factory=session_factory,
            )

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED if final_task else SelectionRunStatus.RUNNING,
            log_messages=[
                _("Google Sheets load completed successfully."),
            ],
            completed_at=datetime.now(UTC) if final_task else None,
            run_report=report,
            session_factory=session_factory,
        )

        return True, features, people, already_selected, report
    except errors.SortitionBaseError as error:
        report.add_line(str(error))
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=str(error),
            error_message=error.to_html(),
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )
        return False, None, None, None, report

    except PermissionError:
        # the PermissionError raised by gspread has no text, so appears to be blank, leading to
        # no hint to the user as to what happened, so we deal with it differently here.
        service_account_email = get_service_account_email()
        error_msg = _(
            "Failed to load gsheet due to permissions issues. Check the spreadsheet is shared with %(email)s",
            email=service_account_email,
        )
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )
        return False, None, None, None, report
    except Exception as err:
        import traceback

        error_msg = _("Failed to load gsheet: %(error)s", error=str(err))
        traceback_msg = traceback.format_exc()

        # TODO: add to logs - just say "error occurred, contact admins" to the user
        report.add_line(error_msg)
        report.add_lines(traceback_msg.split("\n"))

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )

        return False, None, None, None, report


def _internal_run_select(
    task_id: uuid.UUID,
    features: FeatureCollection,
    people: people.People,
    settings: settings.Settings,
    number_people_wanted: int,
    test_selection: bool = False,
    already_selected: people.People | None = None,
    final_task: bool = True,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    report = RunReport()
    # Update SelectionRunRecord to running status
    log_suffix = _(": TEST only, do not use for real selection") if test_selection else ""
    _append_run_log(
        task_id,
        [
            _(
                "Starting selection algorithm for %(number)s people%(suffix)s",
                number=number_people_wanted,
                suffix=log_suffix,
            )
        ],
        session_factory=session_factory,
    )

    try:
        _append_run_log(
            task_id,
            [
                _(
                    "Running stratified selection with %(people_count)s people and %(features_count)s features%(suffix)s",
                    people_count=people.count,
                    features_count=len(features),
                    suffix=log_suffix,
                )
            ],
            session_factory=session_factory,
        )

        success, selected_panels, report = run_stratification(
            features=features,
            people=people,
            number_people_wanted=number_people_wanted,
            settings=settings,
            test_selection=test_selection,
            already_selected=already_selected,
        )

        if success:
            # Convert frozensets to lists for JSON serialization
            selected_ids = [list(panel) for panel in selected_panels]
            _update_selection_record(
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED if final_task else SelectionRunStatus.RUNNING,
                log_message=_(
                    "Selection completed successfully. Selected %(count)s panel(s).%(suffix)s",
                    count=len(selected_panels),
                    suffix=log_suffix,
                ),
                completed_at=datetime.now(UTC) if final_task else None,
                run_report=report,
                selected_ids=selected_ids,
                session_factory=session_factory,
            )
        else:
            error = report.last_error()
            if error:
                error_message = error.to_html() if isinstance(error, errors.SortitionBaseError) else str(error)
            else:
                error_message = _("Selection algorithm could not find panels meeting the specified criteria")
            _update_selection_record(
                task_id=task_id,
                status=SelectionRunStatus.FAILED,
                log_message=_("Selection algorithm failed to find suitable panels"),
                error_message=error_message,
                completed_at=datetime.now(UTC),
                run_report=report,
                session_factory=session_factory,
            )
        return success, selected_panels, report

    except Exception as err:
        import traceback

        error_msg = _("Selection task failed: %(error)s", error=str(err))
        traceback_msg = traceback.format_exc()

        # TODO: add to logs - just say "error occurred, contact admins" to the user
        report.add_line(error_msg, ReportLevel.IMPORTANT)
        report.add_lines(traceback_msg.split("\n"))

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )
        return False, [], report


def _internal_write_selected(
    task_id: uuid.UUID,
    select_data: adapters.SelectionData,
    features: FeatureCollection,
    people: people.People,
    already_selected: people.People | None,
    settings: settings.Settings,
    selected_panels: list[frozenset[str]],
    session_factory: sessionmaker | None = None,
) -> RunReport:
    report = RunReport()
    _append_run_log(task_id, [_("About to write selected and remaining tabs")], session_factory=session_factory)
    try:
        # Format results
        selected_table, remaining_table, _o = selected_remaining_tables(
            full_people=people,
            people_selected=selected_panels[0],
            features=features,
            settings=settings,
            already_selected=already_selected,
            exclude_matching_addresses=False,
        )

        # Export to Google Sheets
        dupes, report = select_data.output_selected_remaining(
            people_selected_rows=selected_table,
            people_remaining_rows=remaining_table,
            settings=settings,
            already_selected=already_selected,
        )
        if dupes:
            # TODO: do something more with dupes? Maybe save to run record extra_info JSON???
            _append_run_log(
                task_id,
                [
                    _(
                        "In the remaining tab there are %(count)s people who share an address with "
                        "someone else selected or remaining. They are highlighted in orange.",
                        count=len(dupes),
                    ),
                ],
                session_factory=session_factory,
            )

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED,
            log_message=_(
                "Successfully written %(selected_count)s selected and %(remaining_count)s remaining to spreadsheet.",
                selected_count=len(selected_table) - 1,
                remaining_count=len(remaining_table) - 1,
            ),
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )

        return report
    except Exception as err:
        import traceback

        error_msg = _("Writing results failed: %(error)s", error=str(err))
        traceback_msg = traceback.format_exc()

        # TODO: add to logs - just say "error occurred, contact admins" to the user
        report.add_line(error_msg, ReportLevel.IMPORTANT)
        report.add_lines(traceback_msg.split("\n"))

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            run_report=report,
            session_factory=session_factory,
        )
        return report


@app.task(bind=True, on_failure=_on_task_failure)
def load_gsheet(
    self: Task,
    task_id: uuid.UUID,
    data_source: adapters.GSheetDataSource | CSVGSheetDataSource,
    settings: settings.Settings,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, FeatureCollection | None, people.People | None, people.People | None, RunReport]:
    _set_up_celery_logging(task_id, session_factory=session_factory)
    select_data = adapters.SelectionData(data_source)
    return _internal_load_gsheet(
        task_obj=self,
        task_id=task_id,
        select_data=select_data,
        settings=settings,
        final_task=True,
        session_factory=session_factory,
    )


@app.task(bind=True, on_failure=_on_task_failure)
def run_select(
    self: Task,
    task_id: uuid.UUID,
    data_source: adapters.GSheetDataSource | CSVGSheetDataSource,
    number_people_wanted: int,
    settings: settings.Settings,
    test_selection: bool = False,
    gen_rem_tab: bool = True,
    for_replacements: bool = False,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    _set_up_celery_logging(task_id, session_factory=session_factory)
    report = RunReport()
    select_data = adapters.SelectionData(data_source, gen_rem_tab=gen_rem_tab)
    success, features, people, already_selected, load_report = _internal_load_gsheet(
        task_obj=self,
        task_id=task_id,
        select_data=select_data,
        settings=settings,
        final_task=False,
        session_factory=session_factory,
    )
    report.add_report(load_report)
    if not success:
        return False, [], report
    assert features is not None
    assert people is not None

    success, selected_panels, select_report = _internal_run_select(
        task_id=task_id,
        features=features,
        people=people,
        settings=settings,
        number_people_wanted=number_people_wanted,
        test_selection=test_selection,
        already_selected=already_selected,
        final_task=False,
        session_factory=session_factory,
    )
    report.add_report(select_report)
    if not success:
        return False, [], report

    # write back to the spreadsheet
    write_report = _internal_write_selected(
        task_id=task_id,
        select_data=select_data,
        features=features,
        people=people,
        already_selected=already_selected,
        settings=settings,
        selected_panels=selected_panels,
        session_factory=session_factory,
    )
    report.add_report(write_report)

    return success, selected_panels, report


@app.task
def cleanup_old_password_reset_tokens(days_old: int = 30) -> int:
    """
    Cleanup old password reset tokens from the database.

    This task should be run periodically (e.g., daily) to remove old
    expired and used tokens and prevent database bloat.

    Args:
        days_old: Delete tokens older than this many days (default 30)

    Returns:
        Number of tokens deleted
    """
    uow = bootstrap()
    count = password_reset_service.cleanup_expired_tokens(uow, days_old=days_old)
    logging.info(f"Cleaned up {count} old password reset tokens (older than {days_old} days)")
    return count


@app.task(bind=True, on_failure=_on_task_failure)
def manage_old_tabs(
    self: Task,
    task_id: uuid.UUID,
    data_source: adapters.GSheetDataSource | CSVGSheetDataSource,
    dry_run: bool = True,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, list[str], RunReport]:
    """
    Manage (list or delete) old output tabs in the spreadsheet.

    Args:
        self: Celery task instance (auto-injected when bind=True)
        task_id: UUID of the task for tracking
        data_source: Data source with access to spreadsheet
        dry_run: If True, list tabs without deleting. If False, delete them.
        session_factory: Optional session factory for database operations

    Returns:
        Tuple of (success: bool, tab_names: list[str], report: RunReport)
    """
    _set_up_celery_logging(task_id, session_factory=session_factory)
    report = RunReport()

    # Update SelectionRunRecord to running status
    action = _("listing") if dry_run else _("deleting")
    _update_selection_record(
        task_id=task_id,
        status=SelectionRunStatus.RUNNING,
        log_message=_("Starting task to %(action)s old output tabs", action=action),
        session_factory=session_factory,
    )

    try:
        # Call delete_old_output_tabs method
        tab_names = data_source.delete_old_output_tabs(dry_run=dry_run)

        # Log what was found/deleted
        if len(tab_names) == 0:
            log_message = _("No old output tabs found")
        elif dry_run:
            log_message = _("Found %(count)s old output tab(s) that can be deleted", count=len(tab_names))
        else:
            log_message = _("Successfully deleted %(count)s old output tab(s)", count=len(tab_names))

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED,
            log_message=log_message,
            completed_at=datetime.now(UTC),
            session_factory=session_factory,
        )

        return True, tab_names, report

    except PermissionError:
        # the PermissionError raised by gspread has no text, so appears to be blank, leading to
        # no hint to the user as to what happened, so we deal with it differently here.
        service_account_email = get_service_account_email()
        error_msg = _(
            "Failed to load gsheet due to permissions issues. Check the spreadsheet is shared with %(email)s",
            email=service_account_email,
        )
        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            session_factory=session_factory,
        )

        return False, [], report

    except Exception as err:
        import traceback

        error_msg = _("Failed to %(action)s old tabs: %(error)s", action=action, error=str(err))
        traceback_msg = traceback.format_exc()

        report.add_line(error_msg)
        report.add_lines(traceback_msg.split("\n"))

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.FAILED,
            log_message=error_msg,
            error_message=error_msg,
            completed_at=datetime.now(UTC),
            session_factory=session_factory,
        )

        return False, [], report


@app.task
def cleanup_orphaned_tasks(session_factory: sessionmaker | None = None) -> dict[str, int]:
    """
    Periodic task to find and mark orphaned selection tasks as FAILED.

    Scans all PENDING and RUNNING tasks and checks their health status
    against Celery. Marks tasks as FAILED if they have died, timed out,
    or were forgotten by Celery.

    This is a safety net that runs periodically (e.g., every 5 minutes)
    to catch tasks that died hard (SIGKILL, OOM) and didn't trigger
    the failure callback.

    Returns:
        Dict with counts: {'checked': int, 'marked_failed': int, 'errors': int}
    """
    # Import here to avoid circular import (sortition.py imports from tasks.py)
    from opendlp.service_layer.sortition import check_and_update_task_health

    checked = 0
    marked_failed = 0
    errors = 0

    logging.info("Starting cleanup_orphaned_tasks periodic job")

    try:
        with bootstrap(session_factory=session_factory) as uow:
            # Get all unfinished tasks (PENDING or RUNNING)
            unfinished_tasks = uow.selection_run_records.get_all_unfinished()
            logging.info(f"Found {len(unfinished_tasks)} unfinished task(s) to check")

            for record in unfinished_tasks:
                try:
                    # Record status before health check
                    status_before = record.status

                    # Check and update task health (will mark as FAILED if needed)
                    check_and_update_task_health(uow, record.task_id)
                    checked += 1

                    # Reload record to see if it was updated
                    uow.commit()  # Commit any changes made by check_and_update_task_health
                    updated_record = uow.selection_run_records.get_by_task_id(record.task_id)

                    # If status changed to FAILED, increment counter
                    if updated_record and status_before != updated_record.status and updated_record.is_failed:
                        marked_failed += 1
                        logging.info(
                            f"Marked orphaned task as FAILED: task_id={record.task_id}, "
                            f"celery_task_id={record.celery_task_id}"
                        )

                except Exception as exc:
                    errors += 1
                    logging.error(
                        f"Error checking task health for task_id={record.task_id}: {exc}",
                        exc_info=True,
                    )

    except Exception as exc:
        errors += 1
        logging.error(f"Error in cleanup_orphaned_tasks: {exc}", exc_info=True)

    result = {"checked": checked, "marked_failed": marked_failed, "errors": errors}
    logging.info(f"Cleanup completed: {result}")
    return result
