"""Unit tests for Respondent domain model."""

import uuid

import pytest

from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus


class TestRespondent:
    def test_create_respondent_with_valid_data(self):
        assembly_id = uuid.uuid4()
        resp = Respondent(
            assembly_id=assembly_id,
            external_id="NB001",
            attributes={"Gender": "Female", "Age": "30-44"},
        )

        assert resp.external_id == "NB001"
        assert resp.assembly_id == assembly_id
        assert resp.selection_status == RespondentStatus.POOL
        assert resp.attributes == {"Gender": "Female", "Age": "30-44"}
        assert resp.id is not None

    def test_validate_empty_external_id(self):
        with pytest.raises(ValueError, match="external_id is required"):
            Respondent(assembly_id=uuid.uuid4(), external_id="")

    def test_mark_as_selected(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        run_id = uuid.uuid4()

        resp.mark_as_selected(run_id)

        assert resp.selection_status == RespondentStatus.SELECTED
        assert resp.selection_run_id == run_id

    def test_mark_as_confirmed(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.mark_as_selected(uuid.uuid4())

        resp.mark_as_confirmed()

        assert resp.selection_status == RespondentStatus.CONFIRMED

    def test_mark_as_confirmed_fails_if_not_selected(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")

        with pytest.raises(ValueError, match="Only selected respondents"):
            resp.mark_as_confirmed()

    def test_mark_as_withdrawn_from_selected(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.mark_as_selected(uuid.uuid4())

        resp.mark_as_withdrawn()

        assert resp.selection_status == RespondentStatus.WITHDRAWN

    def test_mark_as_withdrawn_from_confirmed(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.mark_as_selected(uuid.uuid4())
        resp.mark_as_confirmed()

        resp.mark_as_withdrawn()

        assert resp.selection_status == RespondentStatus.WITHDRAWN

    def test_mark_as_withdrawn_fails_if_not_selected_or_confirmed(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")

        with pytest.raises(ValueError, match="Only selected or confirmed respondents"):
            resp.mark_as_withdrawn()

    def test_is_available_for_selection_true(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=True,
            can_attend=True,
        )
        assert resp.is_available_for_selection() is True

    def test_is_available_for_selection_false_not_eligible(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=False,
            can_attend=True,
        )
        assert resp.is_available_for_selection() is False

    def test_is_available_for_selection_false_cannot_attend(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=True,
            can_attend=False,
        )
        assert resp.is_available_for_selection() is False

    def test_is_available_for_selection_with_eligible_none(self):
        """None means 'not yet set' — should be treated as available, not excluded."""
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=None,
            can_attend=True,
        )
        assert resp.is_available_for_selection() is True

    def test_is_available_for_selection_with_can_attend_none(self):
        """None means 'not yet set' — should be treated as available, not excluded."""
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=True,
            can_attend=None,
        )
        assert resp.is_available_for_selection() is True

    def test_is_available_for_selection_with_both_none(self):
        """None means 'not yet set' — should be treated as available, not excluded."""
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=None,
            can_attend=None,
        )
        assert resp.is_available_for_selection() is True

    def test_is_available_for_selection_false_not_pool_status(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            selection_status=RespondentStatus.SELECTED,
            eligible=True,
            can_attend=True,
        )
        assert resp.is_available_for_selection() is False

    def test_get_attribute(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            attributes={"Gender": "Female"},
        )

        assert resp.get_attribute("Gender") == "Female"
        assert resp.get_attribute("Age", "Unknown") == "Unknown"

    def test_reset_to_pool_from_selected(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        run_id = uuid.uuid4()
        resp.mark_as_selected(run_id)

        resp.reset_to_pool()

        assert resp.selection_status == RespondentStatus.POOL
        assert resp.selection_run_id is None

    def test_reset_to_pool_from_confirmed(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.mark_as_selected(uuid.uuid4())
        resp.mark_as_confirmed()

        resp.reset_to_pool()

        assert resp.selection_status == RespondentStatus.POOL
        assert resp.selection_run_id is None

    def test_reset_to_pool_from_withdrawn(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.mark_as_selected(uuid.uuid4())
        resp.mark_as_withdrawn()

        resp.reset_to_pool()

        assert resp.selection_status == RespondentStatus.POOL
        assert resp.selection_run_id is None

    def test_reset_to_pool_from_pool_is_noop(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")

        resp.reset_to_pool()

        assert resp.selection_status == RespondentStatus.POOL
        assert resp.selection_run_id is None

    def test_create_detached_copy(self):
        assembly_id = uuid.uuid4()
        resp = Respondent(
            assembly_id=assembly_id,
            external_id="NB001",
            attributes={"Gender": "Female"},
            email="test@example.com",
            consent=True,
            eligible=True,
        )

        copy = resp.create_detached_copy()

        assert copy.id == resp.id
        assert copy.external_id == "NB001"
        assert copy.attributes == {"Gender": "Female"}
        assert copy.email == "test@example.com"
        assert copy.consent is True
        assert copy.eligible is True
        assert copy is not resp  # Different instance


class TestRespondentDisplayName:
    def _make(self, attributes=None, email="", external_id="R001"):
        return Respondent(
            assembly_id=uuid.uuid4(),
            external_id=external_id,
            attributes=attributes or {},
            email=email,
        )

    def test_joins_multiple_fields_with_space(self):
        resp = self._make(attributes={"first_name": "Sarah", "last_name": "Jones"})
        assert resp.display_name(["first_name", "last_name"]) == "Sarah Jones"

    def test_skips_missing_field(self):
        resp = self._make(attributes={"first_name": "Sarah"})
        assert resp.display_name(["first_name", "last_name"]) == "Sarah"

    def test_skips_none_and_empty_and_whitespace_values(self):
        resp = self._make(
            attributes={"first_name": "Sarah", "middle_name": None, "second_name": "", "last_name": "   "},
        )
        assert resp.display_name(["first_name", "middle_name", "second_name", "last_name"]) == "Sarah"

    def test_strips_values_before_joining(self):
        resp = self._make(attributes={"first_name": "  Sarah  ", "last_name": " Jones "})
        assert resp.display_name(["first_name", "last_name"]) == "Sarah Jones"

    def test_falls_back_to_email_local_part_when_all_fields_empty(self):
        resp = self._make(attributes={"first_name": ""}, email="sarah.jones@example.com")
        assert resp.display_name(["first_name"]) == "sarah.jones"

    def test_falls_back_to_email_local_part_with_empty_field_list(self):
        resp = self._make(email="bob@example.com")
        assert resp.display_name([]) == "bob"

    def test_falls_back_to_external_id_when_email_also_empty(self):
        resp = self._make(external_id="R-ABC-42")
        assert resp.display_name([]) == "R-ABC-42"

    def test_coerces_non_string_attribute_values(self):
        resp = self._make(attributes={"age_label": 42})
        assert resp.display_name(["age_label"]) == "42"
