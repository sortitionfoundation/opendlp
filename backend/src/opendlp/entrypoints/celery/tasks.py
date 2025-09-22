import logging

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

from opendlp.entrypoints.celery.app import CeleryContextHandler, app


def _set_up_celery_logging(context: Task) -> None:  # type: ignore[no-any-unimported]
    # get log messages written back as we go
    handler = CeleryContextHandler(context)
    handler.setLevel(logging.DEBUG)
    override_logging_handlers([handler], [handler])


@app.task(bind=True)
def load_gsheet(  # type: ignore[no-any-unimported]
    self: Task,
    adapter: adapters.GSheetAdapter,
    feature_tab_name: str,
    respondents_tab_name: str,
    settings: settings.Settings,
) -> tuple[bool, features.FeatureCollection | None, people.People | None, RunReport]:
    _set_up_celery_logging(self)
    report = RunReport()
    try:
        features, f_report = adapter.load_features(feature_tab_name)
        print(f_report.as_text())
        report.add_report(f_report)
        self.update_state(
            state="PROGRESS",
            meta={"features_status": f_report},
        )
        assert features is not None

        people, p_report = adapter.load_people(respondents_tab_name, settings, features)
        print(p_report.as_text())
        report.add_report(p_report)
        self.update_state(
            state="PROGRESS",
            meta={"people_status": f_report},
        )
        assert people is not None

        return True, features, people, report
    except Exception as err:
        import traceback

        report.add_line(f"Failed to load gsheet: {err}")
        report.add_line(traceback.format_exc())
        return False, None, None, report


@app.task(bind=True)
def run_select(  # type: ignore[no-any-unimported]
    self: Task,
    features: features.FeatureCollection,
    people: people.People,
    number_people_wanted: int,
    settings: settings.Settings,
) -> tuple[bool, list[frozenset[str]], RunReport]:
    success = False
    selected_panels: list[frozenset[str]] = []
    _set_up_celery_logging(self)

    try:
        success, selected_panels, report = run_stratification(
            features=features,
            people=people,
            number_people_wanted=number_people_wanted,
            settings=settings,
        )
    except Exception as err:
        report = RunReport()
        report.add_line(str(err), ReportLevel.IMPORTANT)
    # TODO: actually write back to the spreadsheet
    # Should this be part of this task - or a third user triggered task?
    return success, selected_panels, report
