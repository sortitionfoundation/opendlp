"""ABOUTME: The events and after-commit callbacks of one UnitOfWork's work in progress
ABOUTME: Dispatches recorded events to handlers and holds callbacks until the commit succeeds"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from opendlp.domain.events import Event
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

    #: Called with the event and the UnitOfWork it was recorded on, inside that
    #: UnitOfWork's open context. Typed loosely on the event because each
    #: handler takes its own Event subclass.
    EventHandler = Callable[[Any, AbstractUnitOfWork], None]
    EventHandlers = Mapping[type[Event], Sequence[EventHandler]]

logger = structlog.get_logger(__name__)

#: How many handlers deep one recorded event may reach, a handler recording an
#: event of its own counting as one level. Far more than any real chain needs;
#: it exists to turn a cycle of handlers into an error instead of a hang.
MAX_EVENT_CHAIN_DEPTH = 10


class EventChainError(Exception):
    """Raised when event handlers record each other's events too many levels deep."""


class UnitOfWorkEvents:
    """What a UnitOfWork knows about the events of the work in progress.

    Each UnitOfWork owns one of these and delegates ``record`` and
    ``after_commit`` to it. The UnitOfWork also tells it where the transaction
    has got to: ``start`` on entering the context, ``run_callbacks`` after a
    successful commit, ``discard_callbacks`` on a rollback or a failed commit.
    See docs/architecture.md.
    """

    def __init__(self, handlers: EventHandlers | None = None) -> None:
        """
        Args:
            handlers: the handlers to call for each recorded event. Left as
                None, the application's registry in
                ``service_layer/handlers.py`` is used.
        """
        self.events: list[Event] = []
        self._handlers: EventHandlers | None = handlers
        self._callbacks: list[Callable[[], object]] = []
        self._chain_depth = 0

    def start(self) -> None:
        """Forget the events and callbacks of any earlier use."""
        self.events = []
        self._callbacks = []
        self._chain_depth = 0

    def record(self, event: Event, uow: AbstractUnitOfWork) -> None:
        """Keep the event and call its handlers now, each as ``handler(event, uow)``.

        ``events`` keeps everything recorded since ``start``, whether or not
        the work went on to commit. An exception from a handler propagates.
        """
        self.events.append(event)
        if self._chain_depth >= MAX_EVENT_CHAIN_DEPTH:
            raise EventChainError(
                f"{type(event).__name__} was recorded {MAX_EVENT_CHAIN_DEPTH} handlers deep. "
                "Event handlers are probably recording each other's events in a cycle."
            )
        self._chain_depth += 1
        try:
            for handler in self._handlers_for(event):
                handler(event, uow)
        finally:
            self._chain_depth -= 1

    def _handlers_for(self, event: Event) -> Sequence[EventHandler]:
        if self._handlers is None:
            # Imported here because the handlers reach modules that import the
            # UnitOfWork, which imports this module:
            # handlers -> services -> celery tasks -> bootstrap -> unit_of_work.
            from opendlp.service_layer import handlers  # noqa: PLC0415

            self._handlers = handlers.EVENT_HANDLERS
        return self._handlers.get(type(event), ())

    def after_commit(self, callback: Callable[[], object]) -> None:
        """Hold callback until ``run_callbacks`` or ``discard_callbacks``."""
        self._callbacks.append(callback)

    def run_callbacks(self) -> bool:
        """Run and forget the pending callbacks. Returns whether there were any.

        A callback that raises is logged and the rest still run.
        """
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                # The change is already committed, so a side effect that fails
                # must not turn a successful request into an error.
                logger.exception("After-commit callback failed", callback=repr(callback), error=str(exc))
        return bool(callbacks)

    def discard_callbacks(self) -> None:
        """Forget the pending callbacks without running them."""
        self._callbacks = []
