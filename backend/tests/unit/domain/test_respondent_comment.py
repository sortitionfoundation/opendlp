"""ABOUTME: Unit tests for the RespondentComment dataclass
ABOUTME: Covers field presence, defaults, serialisation round-trip, and immutability"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from opendlp.domain.respondents import RespondentComment
from opendlp.domain.value_objects import RespondentAction


class TestRespondentComment:
    def _sample(self, **overrides):
        defaults = {
            "text": "looked them up, all good",
            "author_id": uuid.uuid4(),
            "created_at": datetime(2026, 4, 17, 12, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return RespondentComment(**defaults)

    def test_default_action_is_none(self):
        comment = self._sample()
        assert comment.action is RespondentAction.NONE

    def test_constructs_with_action(self):
        comment = self._sample(action=RespondentAction.DELETE)
        assert comment.action is RespondentAction.DELETE

    def test_to_dict_includes_all_fields(self):
        author = uuid.uuid4()
        created = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        comment = RespondentComment(
            text="hi",
            author_id=author,
            created_at=created,
            action=RespondentAction.EDIT,
        )
        assert comment.to_dict() == {
            "text": "hi",
            "author_id": str(author),
            "created_at": created.isoformat(),
            "action": "EDIT",
        }

    def test_from_dict_round_trips(self):
        original = self._sample(action=RespondentAction.DELETE)
        restored = RespondentComment.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_defaults_missing_action_to_none(self):
        author = uuid.uuid4()
        created = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        restored = RespondentComment.from_dict({
            "text": "legacy row",
            "author_id": str(author),
            "created_at": created.isoformat(),
        })
        assert restored.action is RespondentAction.NONE
        assert restored.text == "legacy row"
        assert restored.author_id == author
        assert restored.created_at == created

    def test_is_frozen(self):
        comment = self._sample()
        with pytest.raises(FrozenInstanceError):
            comment.text = "mutated"  # type: ignore[misc]
