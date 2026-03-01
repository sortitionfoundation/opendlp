"""ABOUTME: Mock Celery tasks for testing without a real Celery worker
ABOUTME: Provides synchronous task execution that immediately completes tasks"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sortition_algorithms import RunReport
from sortition_algorithms.features import FeatureValueMinMax
from sortition_algorithms.people import People

from opendlp.bootstrap import bootstrap
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType

# Global storage for mock task results, keyed by celery_task_id
# This allows MockAsyncResult.get() to return proper result tuples
_mock_results: dict[str, Any] = {}


def _create_mock_features() -> dict[str, dict[str, FeatureValueMinMax]]:
    """Create a mock FeatureCollection for testing.

    Returns a nested dict structure that minimum_selection() and maximum_selection()
    can process. The values are set so min>0 to avoid Jinja2 falsy issues with 0.
    minimum_selection() returns sum of all min values = 4+4+4+5 = 17
    maximum_selection() returns sum of all max values = 110+120+120+130 = 480
    """
    return {
        "gender": {
            "male": FeatureValueMinMax(min=2, max=50),
            "female": FeatureValueMinMax(min=2, max=50),
            "other": FeatureValueMinMax(min=0, max=10),
        },
        "age": {
            "18-30": FeatureValueMinMax(min=2, max=40),
            "31-50": FeatureValueMinMax(min=1, max=40),
            "51+": FeatureValueMinMax(min=1, max=40),
        },
        "region": {
            "north": FeatureValueMinMax(min=1, max=30),
            "south": FeatureValueMinMax(min=1, max=30),
            "east": FeatureValueMinMax(min=1, max=30),
            "west": FeatureValueMinMax(min=1, max=30),
        },
        "education": {
            "high_school": FeatureValueMinMax(min=2, max=40),
            "bachelors": FeatureValueMinMax(min=2, max=40),
            "masters": FeatureValueMinMax(min=1, max=20),
            "doctorate": FeatureValueMinMax(min=0, max=10),
            "other": FeatureValueMinMax(min=0, max=20),
        },
    }


def _create_mock_people() -> People:
    """Create a mock People object for testing."""
    return People(columns_to_keep=["id", "name", "email"])


class MockAsyncResult:
    """Mock Celery AsyncResult that returns SUCCESS state and mock data.

    The mock stores result tuples in _mock_results dict keyed by celery_task_id.
    This allows get() to return proper result tuples that match what real
    Celery tasks would return.
    """

    def __init__(self, celery_task_id: str | None = None) -> None:
        self.id = celery_task_id or str(uuid.uuid4())
        self._state = "SUCCESS"

    @property
    def state(self) -> str:
        return self._state

    def successful(self) -> bool:
        """Return True if mock results exist for this task."""
        return self.id in _mock_results

    def get(self) -> Any:
        """Return the mock result tuple stored during task execution."""
        return _mock_results.get(self.id)

    @property
    def info(self) -> dict[str, Any]:
        return {}


def _complete_task_immediately(task_id: uuid.UUID, celery_task_id: str, num_selected: int = 22) -> None:
    """Mark a selection task as completed in the database and store mock result.

    Args:
        task_id: The SelectionRunRecord task_id (UUID)
        celery_task_id: The Celery task ID (string) - this is used as the key for mock results
        num_selected: Number of mock selected people
    """
    from sqlalchemy.orm.attributes import flag_modified

    with bootstrap() as uow:
        record = uow.selection_run_records.get_by_task_id(task_id)
        if record:
            record.status = SelectionRunStatus.COMPLETED
            record.completed_at = datetime.now(UTC)
            # Add mock log messages that match what real tasks would produce
            record.log_messages.extend([
                "Starting Google Sheets load task",
                "Loading spreadsheet with title: Test Spreadsheet",
                "Loading targets from tab: targets",
                "Found 4 categories for targets with a total of 20 values.",
                "Minimum selection for targets is 1, maximum is 100.",
                "Loading people from tab: All respondents",
                "Loaded 100 people.",
                "Google Sheets load completed successfully.",
                f"Selection completed: {num_selected} people.",
            ])
            flag_modified(record, "log_messages")
            run_report = RunReport()
            record.run_report = run_report

            # Store appropriate mock result tuple based on task type
            # Use the celery_task_id passed in (not from record, as it's not set yet)
            if record.task_type in (
                SelectionTaskType.LOAD_GSHEET,
                SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
            ):
                # Load tasks return: (success, features, people, _, run_report)
                _mock_results[celery_task_id] = (
                    True,  # success
                    _create_mock_features(),
                    _create_mock_people(),
                    None,  # unused parameter
                    run_report,
                )
            elif record.task_type in (
                SelectionTaskType.SELECT_GSHEET,
                SelectionTaskType.TEST_SELECT_GSHEET,
                SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
                SelectionTaskType.SELECT_FROM_DB,
                SelectionTaskType.TEST_SELECT_FROM_DB,
            ):
                # Selection tasks return: (success, selected_ids, run_report)
                selected_ids = [frozenset([str(i)]) for i in range(1, num_selected + 1)]
                record.selected_ids = [[str(i)] for i in range(1, num_selected + 1)]
                _mock_results[celery_task_id] = (
                    True,  # success
                    selected_ids,
                    run_report,
                )
            elif record.task_type in (
                SelectionTaskType.DELETE_OLD_TABS,
                SelectionTaskType.LIST_OLD_TABS,
            ):
                # Tab management tasks return: (success, tab_names, run_report)
                _mock_results[celery_task_id] = (
                    True,  # success
                    [],  # tab_names
                    run_report,
                )

            uow.commit()


class MockTask:
    """Mock Celery task that executes synchronously."""

    def __init__(self, name: str) -> None:
        self.name = name

    def delay(self, *args: Any, **kwargs: Any) -> MockAsyncResult:
        """Execute task synchronously and return mock result.

        Creates a MockAsyncResult with a specific ID, then passes that ID
        to _complete_task_immediately() so mock results are stored with
        the same key that will be used for later lookups.
        """
        # Create the result first so we have a consistent celery_task_id
        result = MockAsyncResult()
        celery_task_id = result.id

        task_id = kwargs.get("task_id")
        if task_id:
            # Mark task as completed, storing results keyed by celery_task_id
            _complete_task_immediately(task_id, celery_task_id)

        return result

    def apply_async(self, *args: Any, **kwargs: Any) -> MockAsyncResult:
        """Execute task synchronously and return mock result."""
        return self.delay(*args, **kwargs)


class MockCeleryApp:
    """Mock Celery app that provides AsyncResult and control interfaces."""

    def AsyncResult(self, celery_task_id: str) -> MockAsyncResult:
        """Return a mock result that can retrieve stored mock data."""
        return MockAsyncResult(celery_task_id=celery_task_id)

    @property
    def control(self) -> "MockControl":
        return MockControl()


class MockControl:
    """Mock Celery control interface."""

    def revoke(self, task_id: str, terminate: bool = False) -> None:
        """Mock revoke - does nothing."""
        pass


class MockAppModule:
    """Mock module to replace opendlp.entrypoints.celery.app in testing."""

    app = MockCeleryApp()


# Mock task instances
load_gsheet = MockTask("load_gsheet")
run_select = MockTask("run_select")
manage_old_tabs = MockTask("manage_old_tabs")
run_select_from_db = MockTask("run_select_from_db")

# Mock app module for sortition.py's `app.app.AsyncResult()` calls
app = MockAppModule()
