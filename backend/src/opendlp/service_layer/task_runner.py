"""ABOUTME: The port through which the service layer starts background tasks and asks after them
ABOUTME: One method per task, so mypy checks every argument; the Celery adapter lives in entrypoints"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sortition_algorithms import adapters
from sortition_algorithms.settings import Settings

from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.service_layer.exceptions import CuratedMessage, ServiceLayerError
from opendlp.translations import gettext as _

#: A task that has been checked and is ready to publish. Calling it sends the
#: task to the broker. The task methods below return one rather than publishing,
#: so the caller decides when the task goes: after its commit, so the worker can
#: find the record the task reports into.
Dispatch = Callable[[], None]

GSheetSource = adapters.GSheetDataSource | CSVGSheetDataSource


class TaskDispatchError(CuratedMessage, ServiceLayerError):
    """A task could not be sent to the broker.

    Raised after its run record has been marked FAILED, so the assembly is not
    left blocked and the user can try again. The message is translated and
    says nothing about the broker; the real error is logged and chained.
    """

    def __init__(self) -> None:
        super().__init__(_("The task could not be started. Please try again."))


@dataclass(frozen=True)
class TaskStatus:
    """What the task backend knows about one task.

    ``state`` is the backend's state name (PENDING, STARTED, SUCCESS, FAILURE,
    REVOKED, ...). A task the backend has never heard of is PENDING. ``value``
    is the task's return value once it is SUCCESS, and ``error`` describes the
    exception once it has failed.
    """

    state: str
    value: Any = None
    error: str = ""

    @property
    def successful(self) -> bool:
        return self.state == "SUCCESS"


class TaskRunner(ABC):
    """Starts the background tasks and reports on them.

    Each task method checks its arguments can be sent - it pickles them - and
    returns a :data:`Dispatch` without sending anything. A serialisation bug
    therefore raises inside the caller's transaction, where it can still be
    reported, rather than on the way to the broker.

    Adding a task means a method here, on ``CeleryTaskRunner`` and on each fake
    in ``tests/fakes/tasks.py``.
    """

    @abstractmethod
    def load_gsheet(self, *, task_id: uuid.UUID, data_source: GSheetSource, settings: Settings) -> Dispatch:
        """Read and check the respondents and targets in a Google Sheet."""

    @abstractmethod
    def run_select(
        self,
        *,
        task_id: uuid.UUID,
        data_source: GSheetSource,
        number_people_wanted: int,
        settings: Settings,
        test_selection: bool,
        gen_rem_tab: bool,
        for_replacements: bool = False,
        time_limit: int | None = None,
        soft_time_limit: int | None = None,
    ) -> Dispatch:
        """Run a selection over a Google Sheet and write the result back to it.

        ``time_limit`` and ``soft_time_limit`` are in seconds; None leaves the
        worker's defaults.
        """

    @abstractmethod
    def manage_old_tabs(self, *, task_id: uuid.UUID, data_source: GSheetSource, dry_run: bool) -> Dispatch:
        """List, or with ``dry_run=False`` delete, the old output tabs in a Google Sheet."""

    @abstractmethod
    def run_select_from_db(
        self,
        *,
        task_id: uuid.UUID,
        assembly_id: uuid.UUID,
        number_people_wanted: int,
        settings: Settings,
        test_selection: bool,
        targets_snapshot: list[dict[str, Any]] | None = None,
    ) -> Dispatch:
        """Run a selection over the respondents in the database."""

    @abstractmethod
    def auto_export_respondents(self, *, assembly_id: uuid.UUID, countdown: int) -> Dispatch:
        """Rewrite the assembly's respondent export sheet, ``countdown`` seconds after dispatch."""

    @abstractmethod
    def status(self, celery_task_id: str) -> TaskStatus:
        """What the backend knows about the task with this id. May raise if the backend cannot be reached."""

    @abstractmethod
    def revoke(self, celery_task_id: str) -> None:
        """Stop the task with this id, terminating it if it is already running."""
