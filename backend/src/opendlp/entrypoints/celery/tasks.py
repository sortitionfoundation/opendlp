import logging
import uuid
from datetime import UTC, datetime

from celery import Task
from sortition_algorithms import (
    RunReport,
    adapters,
    features,
    people,
    run_stratification,
    settings,
)
from sortition_algorithms.utils import ReportLevel, override_logging_handlers

from opendlp.bootstrap import bootstrap
from opendlp.entrypoints.celery.app import CeleryContextHandler, app


def _set_up_celery_logging(context: Task) -> None:  # type: ignore[no-any-unimported]
    # get log messages written back as we go
    handler = CeleryContextHandler(context)
    handler.setLevel(logging.DEBUG)
    override_logging_handlers([handler], [handler])


def _update_selection_record(
    task_id: uuid.UUID,
    status: str,
    log_message: str = "",
    error_message: str = "",
    completed_at: datetime | None = None,
) -> None:
    """Update an existing SelectionRunRecord with progress information."""
    with bootstrap() as uow:
        # Get existing record (should always exist since created at submit time)
        record = uow.selection_run_records.get_by_task_id(task_id)

        if record is None:
            raise ValueError(f"SelectionRunRecord with task_id {task_id} not found")

        # Update existing record
        record.status = status
        if log_message:
            record.log_messages.append(log_message)
        if error_message:
            record.error_message = error_message
        if completed_at:
            record.completed_at = completed_at

        uow.commit()


@app.task(bind=True)
def load_gsheet(  # type: ignore[no-any-unimported]
    self: Task,
    task_id: uuid.UUID,
    adapter: adapters.GSheetAdapter,
    feature_tab_name: str,
    respondents_tab_name: str,
    settings: settings.Settings,
) -> tuple[bool, features.FeatureCollection | None, people.People | None, RunReport]:
    _set_up_celery_logging(self)
    report = RunReport()

    # Update SelectionRunRecord to running status
    _update_selection_record(
        task_id=task_id,
        status="running",
        log_message="Starting Google Sheets load task",
    )

    try:
        _update_selection_record(
            task_id=task_id,
            status="running",
            log_message=f"Loading features from tab: {feature_tab_name}",
        )

        features, f_report = adapter.load_features(feature_tab_name)
        print(f_report.as_text())
        report.add_report(f_report)
        self.update_state(
            state="PROGRESS",
            meta={"features_status": f_report},
        )
        assert features is not None

        _update_selection_record(
            task_id=task_id,
            status="running",
            log_message=f"Features loaded successfully. Found {len(features)} features. Loading people from tab: {respondents_tab_name}",
        )

        people, p_report = adapter.load_people(respondents_tab_name, settings, features)
        print(p_report.as_text())
        report.add_report(p_report)
        self.update_state(
            state="PROGRESS",
            meta={"people_status": f_report},
        )
        assert people is not None

        _update_selection_record(
            task_id=task_id,
            status="completed",
            log_message=f"Google Sheets load completed successfully. Loaded {people.count} people.",
            completed_at=datetime.now(UTC),
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


@app.task(bind=True)
def run_select(  # type: ignore[no-any-unimported]
    self: Task,
    task_id: uuid.UUID,
    features: features.FeatureCollection,
    people: people.People,
    number_people_wanted: int,
    settings: settings.Settings,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    success = False
    selected_panels: list[frozenset[str]] = []
    _set_up_celery_logging(self)
    report = RunReport()

    # Update SelectionRunRecord to running status
    _update_selection_record(
        task_id=task_id,
        status="running",
        log_message=f"Starting selection algorithm for {number_people_wanted} people",
    )

    try:
        _update_selection_record(
            task_id=task_id,
            status="running",
            log_message=f"Running stratified selection with {people.count} people and {len(features)} features",
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
                status="completed",
                log_message=f"Selection completed successfully. Selected {len(selected_panels)} panel(s).",
                completed_at=datetime.now(UTC),
            )
        else:
            _update_selection_record(
                task_id=task_id,
                status="failed",
                log_message="Selection algorithm failed to find suitable panels",
                error_message="Selection algorithm could not find panels meeting the specified criteria",
                completed_at=datetime.now(UTC),
            )

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

    # TODO: actually write back to the spreadsheet
    # Should this be part of this task - or a third user triggered task?
    return success, selected_panels, report
