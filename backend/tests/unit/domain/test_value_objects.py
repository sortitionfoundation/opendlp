"""ABOUTME: Unit tests for value object enums in opendlp.domain.value_objects
ABOUTME: Regression guards for RespondentStatus / RespondentAction membership"""

from opendlp.domain.value_objects import RespondentStatus


class TestRespondentStatus:
    def test_has_deleted_value(self):
        assert RespondentStatus.DELETED.value == "DELETED"

    def test_excluded_removed(self):
        assert not hasattr(RespondentStatus, "EXCLUDED")
