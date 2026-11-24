"""ABOUTME: The registry of event handlers - which functions run when each domain event is recorded
ABOUTME: The one place to look to find out what recording an event causes"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opendlp.domain import events
from opendlp.service_layer import respondent_auto_export

if TYPE_CHECKING:
    from opendlp.domain.events import Event
    from opendlp.service_layer.unit_of_work_events import EventHandler

# Each handler is called as handler(event, uow) when uow.record(event) is
# called, inside the caller's open `with uow:` block. A handler never opens or
# commits a context. For anything outside the database it registers a callback
# with uow.after_commit(). Dispatch is by the event's exact type.
EVENT_HANDLERS: dict[type[Event], list[EventHandler]] = {
    events.RespondentsChanged: [respondent_auto_export.handle_respondents_changed],
    events.RespondentSchemaChanged: [respondent_auto_export.handle_respondents_changed],
}
