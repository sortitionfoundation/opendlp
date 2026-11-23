"""ABOUTME: Unit tests for domain events
ABOUTME: Events are immutable values that compare by what they say happened"""

import dataclasses
import uuid

import pytest

from opendlp.domain import events


class TestEvents:
    @pytest.mark.parametrize("event_class", [events.RespondentsChanged, events.RespondentSchemaChanged])
    def test_is_an_event(self, event_class):
        assert isinstance(event_class(assembly_id=uuid.uuid4()), events.Event)

    def test_events_with_the_same_values_are_equal(self):
        assembly_id = uuid.uuid4()

        assert events.RespondentsChanged(assembly_id) == events.RespondentsChanged(assembly_id)

    def test_different_events_about_the_same_assembly_are_not_equal(self):
        assembly_id = uuid.uuid4()

        assert events.RespondentsChanged(assembly_id) != events.RespondentSchemaChanged(assembly_id)

    def test_an_event_cannot_be_changed(self):
        event = events.RespondentsChanged(uuid.uuid4())

        with pytest.raises(dataclasses.FrozenInstanceError):
            event.assembly_id = uuid.uuid4()
