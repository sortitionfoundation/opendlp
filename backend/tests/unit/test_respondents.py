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

    def test_is_available_for_selection_false_eligible_none(self):
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            eligible=None,
            can_attend=True,
        )
        assert resp.is_available_for_selection() is False

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
