import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import Task
from celery.signals import setup_logging
from sortition_algorithms import (
    RunReport,
    adapters,
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


def _update_selection_record(
    task_id: uuid.UUID,
    status: SelectionRunStatus,
    log_message: str = "",
    log_messages: list[str] | None = None,
    error_message: str = "",
    completed_at: datetime | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Update an existing SelectionRunRecord with progress information."""
    assert not (log_message and log_messages), "only use log_message or log_messages, not both"
    with bootstrap(session_factory=session_factory) as uow:
        # Get existing record (should always exist since created at submit time)
        record = uow.selection_run_records.get_by_task_id(task_id)

        if record is None:
            raise ValueError(f"SelectionRunRecord with task_id {task_id} not found")

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
) -> tuple[bool, FeatureCollection | None, people.People | None, RunReport]:
    data_source = select_data.data_source
    assert isinstance(data_source, adapters.GSheetDataSource | CSVGSheetDataSource)
    report = RunReport()
    # Update SelectionRunRecord to running status
    _update_selection_record(
        task_id=task_id,
        status=SelectionRunStatus.RUNNING,
        log_message="Starting Google Sheets load task",
        session_factory=session_factory,
    )

    try:
        _append_run_log(
            task_id,
            [
                f"Loading spreadsheet with title: {data_source.spreadsheet.title}",
                f"Loading targets from tab: {data_source.feature_tab_name}",
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
                f"Found {num_features} categories for targets with a total of {num_values} values.",
                f"Minimum selection for targets is {min_select}, maximum is {max_select}.",
                f"Loading people from tab: {data_source.people_tab_name}",
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

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED if final_task else SelectionRunStatus.RUNNING,
            log_messages=[f"Loaded {people.count} people.", "Google Sheets load completed successfully."],
            completed_at=datetime.now(UTC) if final_task else None,
            session_factory=session_factory,
        )

        return True, features, people, report
    except Exception as err:
        import traceback

        error_msg = f"Failed to load gsheet: {err}"
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
            session_factory=session_factory,
        )

        return False, None, None, report


def _internal_run_select(
    task_id: uuid.UUID,
    features: FeatureCollection,
    people: people.People,
    settings: settings.Settings,
    number_people_wanted: int,
    test_selection: bool = False,
    final_task: bool = True,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    report = RunReport()
    # Update SelectionRunRecord to running status
    log_suffix = ": TEST only, do not use for real selection" if test_selection else ""
    _append_run_log(
        task_id,
        [f"Starting selection algorithm for {number_people_wanted} people{log_suffix}"],
        session_factory=session_factory,
    )

    try:
        _append_run_log(
            task_id,
            [f"Running stratified selection with {people.count} people and {len(features)} features{log_suffix}"],
            session_factory=session_factory,
        )

        success, selected_panels, report = run_stratification(
            features=features,
            people=people,
            number_people_wanted=number_people_wanted,
            settings=settings,
            test_selection=test_selection,
        )

        if success:
            _update_selection_record(
                task_id=task_id,
                status=SelectionRunStatus.COMPLETED if final_task else SelectionRunStatus.RUNNING,
                log_message=f"Selection completed successfully. Selected {len(selected_panels)} panel(s).{log_suffix}",
                completed_at=datetime.now(UTC) if final_task else None,
                session_factory=session_factory,
            )
        else:
            _update_selection_record(
                task_id=task_id,
                status=SelectionRunStatus.FAILED,
                log_message="Selection algorithm failed to find suitable panels",
                error_message="Selection algorithm could not find panels meeting the specified criteria",
                completed_at=datetime.now(UTC),
                session_factory=session_factory,
            )
        return success, selected_panels, report

    except Exception as err:
        import traceback

        error_msg = f"Selection task failed: {err}"
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
            session_factory=session_factory,
        )
        return False, [], report


def _internal_write_selected(
    task_id: uuid.UUID,
    select_data: adapters.SelectionData,
    features: FeatureCollection,
    people: people.People,
    settings: settings.Settings,
    selected_panels: list[frozenset[str]],
    session_factory: sessionmaker | None = None,
) -> RunReport:
    report = RunReport()
    _append_run_log(task_id, ["About to write selected and remaining tabs"], session_factory=session_factory)
    try:
        # Format results
        selected_table, remaining_table, _ = selected_remaining_tables(people, selected_panels[0], features, settings)

        # Export to Google Sheets
        dupes, report = select_data.output_selected_remaining(selected_table, remaining_table, settings)
        if dupes:
            # TODO: do something more with dupes? Maybe save to run record extra_info JSON???
            _append_run_log(
                task_id,
                [
                    f"In the remaining tab there are {len(dupes)} people who share the same address as "
                    f"someone else in the tab. They are highlighted in orange.",
                ],
                session_factory=session_factory,
            )

        _update_selection_record(
            task_id=task_id,
            status=SelectionRunStatus.COMPLETED,
            log_message=f"Successfully written {len(selected_table) - 1} selected and {len(remaining_table) - 1} remaining to spreadsheet.",
            completed_at=datetime.now(UTC),
            session_factory=session_factory,
        )

        return report
    except Exception as err:
        import traceback

        error_msg = f"Writing results failed: {err}"
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
            session_factory=session_factory,
        )
        return report


@app.task(bind=True)
def load_gsheet(
    self: Task,
    task_id: uuid.UUID,
    data_source: adapters.GSheetDataSource | CSVGSheetDataSource,
    settings: settings.Settings,
    session_factory: sessionmaker | None = None,
) -> tuple[bool, FeatureCollection | None, people.People | None, RunReport]:
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


@app.task(bind=True)
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
    success, features, people, load_report = _internal_load_gsheet(
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
        settings=settings,
        selected_panels=selected_panels,
        session_factory=session_factory,
    )
    report.add_report(write_report)

    return success, selected_panels, report
