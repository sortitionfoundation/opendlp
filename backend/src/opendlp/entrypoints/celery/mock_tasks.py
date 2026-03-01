"""ABOUTME: Mock Celery tasks for testing without a real Celery worker
ABOUTME: Provides synchronous task execution that immediately completes tasks"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sortition_algorithms import RunReport

from opendlp.bootstrap import bootstrap
from opendlp.domain.value_objects import SelectionRunStatus


class MockAsyncResult:
    """Mock Celery AsyncResult that returns PENDING state.

    The mock task completes synchronously and writes results directly to the
    database (SelectionRunRecord). Returning PENDING from Celery forces
    get_selection_run_status() to use the database state, which contains
    the log messages and run report set by _complete_task_immediately().
    """

    def __init__(self) -> None:
        self.id = str(uuid.uuid4())
        self._state = "PENDING"

    @property
    def state(self) -> str:
        return self._state

    def successful(self) -> bool:
        # Return False so get_selection_run_status() uses database state
        # The mock writes completion data directly to the database
        return False

    def get(self) -> None:
        return None

    @property
    def info(self) -> dict[str, Any]:
        return {}


def _complete_task_immediately(task_id: uuid.UUID, num_selected: int = 22) -> None:
    """Mark a selection task as completed in the database."""
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
                f"Successfully selected {num_selected} people.",
            ])
            flag_modified(record, "log_messages")
            record.run_report = RunReport()
            # Add some mock selected IDs for selection tasks
            record.selected_ids = [[str(i)] for i in range(1, num_selected + 1)]
            uow.commit()


class MockTask:
    """Mock Celery task that executes synchronously."""

    def __init__(self, name: str) -> None:
        self.name = name

    def delay(self, *args: Any, **kwargs: Any) -> MockAsyncResult:
        """Execute task synchronously and return mock result."""
        task_id = kwargs.get("task_id")
        if task_id:
            # Mark task as completed
            _complete_task_immediately(task_id)
        return MockAsyncResult()

    def apply_async(self, *args: Any, **kwargs: Any) -> MockAsyncResult:
        """Execute task synchronously and return mock result."""
        return self.delay(*args, **kwargs)


class MockCeleryApp:
    """Mock Celery app that provides AsyncResult and control interfaces."""

    def AsyncResult(self, celery_task_id: str) -> MockAsyncResult:
        """Return a mock result that uses database state."""
        return MockAsyncResult()

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
