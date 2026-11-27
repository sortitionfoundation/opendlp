"""ABOUTME: The registry of event handlers - which functions run when each domain event is recorded
ABOUTME: The one place to look to find out what recording an event causes"""

from functools import partial
from typing import TYPE_CHECKING

from opendlp.domain import events
from opendlp.service_layer import respondent_auto_export

if TYPE_CHECKING:
    from opendlp.service_layer.task_runner import TaskRunner
    from opendlp.service_layer.unit_of_work_events import EventHandlers


def build_event_handlers(task_runner: TaskRunner) -> EventHandlers:
    """The application's handlers for each event type, with the adapters they need already supplied.

    Each handler is called as handler(event, uow) when uow.record(event) is
    called, inside the caller's open `with uow:` block. A handler never opens or
    commits a context. For anything outside the database it registers a callback
    with uow.after_commit(). Dispatch is by the event's exact type.

    bootstrap.default_event_handlers() builds the table the application uses.
    """
    export = partial(respondent_auto_export.handle_respondents_changed, task_runner=task_runner)
    return {
        events.RespondentsChanged: [export],
        events.RespondentSchemaChanged: [export],
    }
