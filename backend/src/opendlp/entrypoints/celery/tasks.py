import logging
import uuid
from datetime import UTC, datetime

from celery import Task
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
from sqlalchemy.orm.attributes import flag_modified

from opendlp.bootstrap import bootstrap
from opendlp.entrypoints.celery.app import app


class SelectionRunRecordHandler(logging.Handler):
    """
    A logger that sends the log messages through Celery to the AsyncResult
    object.
    """

    def __init__(self, task_id: uuid.UUID) -> None:  # type: ignore[no-any-unimported]
        super().__init__()
        self.task_id = task_id
        self.setFormatter(logging.Formatter(fmt="'%(message)s'"))

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        _append_run_log(self.task_id, [msg])


def _set_up_celery_logging(task_id: uuid.UUID) -> None:  # type: ignore[no-any-unimported]
    # get log messages written back as we go
    handler = SelectionRunRecordHandler(task_id)
    handler.setLevel(logging.DEBUG)
    override_logging_handlers([handler], [handler])


def _update_selection_record(
    task_id: uuid.UUID,
    status: str,
    log_message: str = "",
    log_messages: list[str] | None = None,
    error_message: str = "",
    completed_at: datetime | None = None,
) -> None:
    """Update an existing SelectionRunRecord with progress information."""
    assert not (log_message and log_messages), "only use log_message or log_messages, not both"
    with bootstrap() as uow:
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


def _append_run_log(task_id: uuid.UUID, log_messages: list[str]) -> None:
    """Add to the log while running"""
    _update_selection_record(task_id, status="running", log_messages=log_messages)


def _internal_load_gsheet(
    task_obj: Task,
    task_id: uuid.UUID,
    adapter: adapters.GSheetAdapter,
    feature_tab_name: str,
    respondents_tab_name: str,
    settings: settings.Settings,
    final_task: bool = True,
) -> tuple[bool, FeatureCollection | None, people.People | None, RunReport]:
    report = RunReport()
    # Update SelectionRunRecord to running status
    _update_selection_record(
        task_id=task_id,
        status="running",
        log_message="Starting Google Sheets load task",
    )

    try:
        _append_run_log(task_id, [f"Loading targets from tab: {feature_tab_name}"])

        features, f_report = adapter.load_features(feature_tab_name)
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
                f"Loading people from tab: {respondents_tab_name}",
            ],
        )

        people, p_report = adapter.load_people(respondents_tab_name, settings, features)
        report.add_report(p_report)
        task_obj.update_state(
            state="PROGRESS",
            meta={"people_status": p_report.as_text()},
        )
        assert people is not None

        _update_selection_record(
            task_id=task_id,
            status="completed" if final_task else "running",
            log_messages=[f"Loaded {people.count} people.", "Google Sheets load completed successfully."],
            completed_at=datetime.now(UTC) if final_task else None,
        )

        return True, features, people, report
    except Exception as err:
        import traceback

        error_msg = f"Failed to load gsheet: {err}"
        traceback_msg = traceback.format_exc()

        report.add_line(error_msg)
        report.add_line(traceback_msg)

        _update_selection_record(
            task_id=task_id,
            status="failed",
            log_message=error_msg,
            error_message=f"{error_msg}\n{traceback_msg}",
            completed_at=datetime.now(UTC),
        )

        return False, None, None, report


def _internal_run_select(
    task_id: uuid.UUID,
    features: FeatureCollection,
    people: people.People,
    settings: settings.Settings,
    number_people_wanted: int,
    final_task: bool = True,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    report = RunReport()
    # Update SelectionRunRecord to running status
    _append_run_log(task_id, [f"Starting selection algorithm for {number_people_wanted} people"])

    try:
        _append_run_log(
            task_id, [f"Running stratified selection with {people.count} people and {len(features)} features"]
        )

        success, selected_panels, report = run_stratification(
            features=features,
            people=people,
            number_people_wanted=number_people_wanted,
            settings=settings,
        )

        if success:
            _update_selection_record(
                task_id=task_id,
                status="completed" if final_task else "running",
                log_message=f"Selection completed successfully. Selected {len(selected_panels)} panel(s).",
                completed_at=datetime.now(UTC) if final_task else None,
            )
        else:
            _update_selection_record(
                task_id=task_id,
                status="failed",
                log_message="Selection algorithm failed to find suitable panels",
                error_message="Selection algorithm could not find panels meeting the specified criteria",
                completed_at=datetime.now(UTC),
            )
        return success, selected_panels, report

    except Exception as err:
        import traceback

        error_msg = f"Selection task failed: {err}"
        traceback_msg = traceback.format_exc()

        report.add_line(error_msg, ReportLevel.IMPORTANT)
        report.add_line(traceback_msg, ReportLevel.NORMAL)

        _update_selection_record(
            task_id=task_id,
            status="failed",
            log_message=error_msg,
            error_message=f"{error_msg}\n{traceback_msg}",
            completed_at=datetime.now(UTC),
        )
        return False, [], report


def _internal_write_selected(
    task_id: uuid.UUID,
    adapter: adapters.GSheetAdapter,
    features: FeatureCollection,
    people: people.People,
    settings: settings.Settings,
    selected_panels: list[frozenset[str]],
) -> RunReport:
    report = RunReport()
    _append_run_log(task_id, ["About to write selected and remaining tabs"])
    # Format results
    selected_table, remaining_table, _ = selected_remaining_tables(people, selected_panels[0], features, settings)

    # Export to Google Sheets
    adapter.output_selected_remaining(selected_table, remaining_table, settings)
    # TODO: do something with dupes

    _update_selection_record(
        task_id=task_id,
        status="completed",
        log_message=f"Successfully written {len(selected_table) - 1} selected and {len(remaining_table) - 1} remaining to spreadsheet.",
        completed_at=datetime.now(UTC),
    )

    return report


@app.task(bind=True)
def load_gsheet(  # type: ignore[no-any-unimported]
    self: Task,
    task_id: uuid.UUID,
    adapter: adapters.GSheetAdapter,
    feature_tab_name: str,
    respondents_tab_name: str,
    settings: settings.Settings,
) -> tuple[bool, FeatureCollection | None, people.People | None, RunReport]:
    _set_up_celery_logging(task_id)
    return _internal_load_gsheet(self, task_id, adapter, feature_tab_name, respondents_tab_name, settings)


@app.task(bind=True)
def run_select(  # type: ignore[no-any-unimported]
    self: Task,
    task_id: uuid.UUID,
    adapter: adapters.GSheetAdapter,
    feature_tab_name: str,
    respondents_tab_name: str,
    number_people_wanted: int,
    settings: settings.Settings,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    _set_up_celery_logging(task_id)
    report = RunReport()
    success, features, people, load_report = _internal_load_gsheet(
        self, task_id, adapter, feature_tab_name, respondents_tab_name, settings
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
    )
    report.add_report(select_report)
    if not success:
        return False, [], report

    # write back to the spreadsheet
    write_report = _internal_write_selected(
        task_id=task_id,
        adapter=adapter,
        features=features,
        people=people,
        settings=settings,
        selected_panels=selected_panels,
    )
    report.add_report(write_report)

    return success, selected_panels, report
