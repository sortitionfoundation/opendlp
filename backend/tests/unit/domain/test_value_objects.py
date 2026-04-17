"""ABOUTME: Unit tests for value object enums in opendlp.domain.value_objects
ABOUTME: Regression guards for RespondentStatus / RespondentAction membership"""

from opendlp.domain.value_objects import RespondentAction, RespondentStatus


class TestRespondentStatus:
    def test_has_deleted_value(self):
        assert RespondentStatus.DELETED.value == "DELETED"

    def test_excluded_removed(self):
        assert not hasattr(RespondentStatus, "EXCLUDED")


class TestRespondentAction:
    def test_has_none_value(self):
        assert RespondentAction.NONE.value == "NONE"

    def test_has_edit_value(self):
        assert RespondentAction.EDIT.value == "EDIT"

    def test_has_delete_value(self):
        assert RespondentAction.DELETE.value == "DELETE"
