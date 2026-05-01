"""Unit tests for Respondent domain model."""

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.respondents import Respondent, RespondentComment, validate_no_field_name_collisions
from opendlp.domain.value_objects import (
    ALLOWED_SELECTION_STATUS_TRANSITIONS,
    RespondentAction,
    RespondentStatus,
)


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

    def test_rejects_attributes_with_colliding_normalised_keys(self):
        with pytest.raises(ValueError, match="normalise"):
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="R001",
                attributes={"first_name": "Sarah", "FirstName": "Sarah"},
            )

    def test_rejects_attribute_colliding_with_reserved_field(self):
        with pytest.raises(ValueError, match="reserved"):
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="R001",
                attributes={"Email": "sarah@example.com"},
            )

    def test_rejects_attribute_key_normalising_to_empty(self):
        with pytest.raises(ValueError, match="empty"):
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="R001",
                attributes={"---": "value"},
            )

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


class TestRespondentComments:
    def test_defaults_to_empty_list(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        assert resp.comments == []

    def test_constructor_accepts_comments(self):
        author = uuid.uuid4()
        comment = RespondentComment(
            text="note",
            author_id=author,
            created_at=datetime(2026, 4, 17, tzinfo=UTC),
        )
        resp = Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            comments=[comment],
        )
        assert resp.comments == [comment]

    def test_reserved_name_comments_rejects_attribute_collision(self):
        with pytest.raises(ValueError, match="reserved"):
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="NB001",
                attributes={"Comments": "hi"},
            )

    def test_add_comment_appends_with_default_action_none(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        author = uuid.uuid4()

        resp.add_comment("first note", author)

        assert len(resp.comments) == 1
        assert resp.comments[0].text == "first note"
        assert resp.comments[0].author_id == author
        assert resp.comments[0].action is RespondentAction.NONE

    def test_add_comment_with_explicit_action(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.add_comment("edit note", uuid.uuid4(), action=RespondentAction.EDIT)
        assert resp.comments[0].action is RespondentAction.EDIT

    def test_add_comment_updates_updated_at(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        resp.add_comment("note", uuid.uuid4())
        assert resp.updated_at > datetime(2000, 1, 1, tzinfo=UTC)

    def test_add_comment_rejects_empty_text(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        with pytest.raises(ValueError, match="Comment text is required"):
            resp.add_comment("", uuid.uuid4())

    def test_add_comment_rejects_whitespace_only_text(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        with pytest.raises(ValueError, match="Comment text is required"):
            resp.add_comment("   ", uuid.uuid4())

    def test_add_comment_strips_text(self):
        resp = Respondent(assembly_id=uuid.uuid4(), external_id="NB001")
        resp.add_comment("  note  ", uuid.uuid4())
        assert resp.comments[0].text == "note"


class TestRespondentDeletePersonalData:
    def _live_respondent(self):
        return Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            attributes={"Gender": "Female", "Age": "30-44"},
            email="sarah@example.com",
            consent=True,
            stay_on_db=True,
            eligible=True,
            can_attend=True,
            source_reference="import 2026",
            selection_status=RespondentStatus.SELECTED,
            selection_run_id=uuid.uuid4(),
        )

    def test_sets_status_deleted(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.selection_status == RespondentStatus.DELETED

    def test_blanks_email_and_source_reference(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.email == ""
        assert resp.source_reference == ""

    def test_clears_booleans_to_none(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.consent is None
        assert resp.stay_on_db is None
        assert resp.eligible is None
        assert resp.can_attend is None

    def test_clears_selection_run_id(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.selection_run_id is None

    def test_blanks_attribute_values_but_keeps_keys(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.attributes == {"Gender": "", "Age": ""}

    def test_appends_delete_action_comment(self):
        author = uuid.uuid4()
        resp = self._live_respondent()
        resp.delete_personal_data(author, "gdpr request")

        assert len(resp.comments) == 1
        comment = resp.comments[0]
        assert comment.text == "gdpr request"
        assert comment.author_id == author
        assert comment.action is RespondentAction.DELETE

    def test_preserves_identity_fields(self):
        resp = self._live_respondent()
        original_id = resp.id
        original_external_id = resp.external_id
        original_assembly_id = resp.assembly_id
        original_source_type = resp.source_type
        original_created_at = resp.created_at

        resp.delete_personal_data(uuid.uuid4(), "gdpr request")

        assert resp.id == original_id
        assert resp.external_id == original_external_id
        assert resp.assembly_id == original_assembly_id
        assert resp.source_type == original_source_type
        assert resp.created_at == original_created_at

    def test_preserves_prior_comments(self):
        resp = self._live_respondent()
        earlier_author = uuid.uuid4()
        resp.add_comment("pre-existing note", earlier_author)

        resp.delete_personal_data(uuid.uuid4(), "gdpr request")

        assert len(resp.comments) == 2
        assert resp.comments[0].text == "pre-existing note"
        assert resp.comments[0].author_id == earlier_author
        assert resp.comments[1].text == "gdpr request"
        assert resp.comments[1].action is RespondentAction.DELETE

    def test_rejects_empty_comment(self):
        resp = self._live_respondent()
        with pytest.raises(ValueError, match="comment is required"):
            resp.delete_personal_data(uuid.uuid4(), "")

    def test_rejects_whitespace_only_comment(self):
        resp = self._live_respondent()
        with pytest.raises(ValueError, match="comment is required"):
            resp.delete_personal_data(uuid.uuid4(), "   ")

    def test_detached_copy_round_trips_comments(self):
        resp = self._live_respondent()
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")

        copy = resp.create_detached_copy()

        assert copy.comments == resp.comments
        assert copy.comments is not resp.comments  # separate list
        assert copy.selection_status == RespondentStatus.DELETED
        assert copy.attributes == {"Gender": "", "Age": ""}


class TestRespondentApplyEdit:
    def _live(self) -> Respondent:
        return Respondent(
            assembly_id=uuid.uuid4(),
            external_id="NB001",
            attributes={"gender": "Female", "age": "30"},
            email="a@b.com",
            consent=True,
            stay_on_db=True,
            eligible=True,
            can_attend=True,
        )

    def test_requires_non_blank_comment(self):
        resp = self._live()
        with pytest.raises(ValueError, match="comment"):
            resp.apply_edit(author_id=uuid.uuid4(), comment="   ", email="new@b.com")

    def test_refuses_on_deleted_status(self):
        resp = self._live()
        resp.delete_personal_data(uuid.uuid4(), "gdpr")
        with pytest.raises(ValueError, match=r"DELETED|deleted"):
            resp.apply_edit(author_id=uuid.uuid4(), comment="try", email="x@y.com")

    def test_updates_email_and_flags(self):
        resp = self._live()
        author = uuid.uuid4()
        resp.apply_edit(
            author_id=author,
            comment="fix email",
            email="new@b.com",
            eligible=False,
        )
        assert resp.email == "new@b.com"
        assert resp.eligible is False

    def test_sentinel_leaves_unpassed_flags_alone(self):
        resp = self._live()
        resp.apply_edit(author_id=uuid.uuid4(), comment="no-op flag test", email="other@b.com")
        assert resp.eligible is True  # unpassed => untouched
        assert resp.consent is True

    def test_explicit_none_sets_flag_to_none(self):
        resp = self._live()
        resp.apply_edit(author_id=uuid.uuid4(), comment="clear eligible", eligible=None)
        assert resp.eligible is None

    def test_merges_attributes(self):
        resp = self._live()
        resp.apply_edit(author_id=uuid.uuid4(), comment="fix age", attributes={"age": "31"})
        assert resp.attributes["age"] == "31"
        assert resp.attributes["gender"] == "Female"  # preserved

    def test_rejects_when_nothing_changes(self):
        resp = self._live()
        with pytest.raises(ValueError, match="changes"):
            resp.apply_edit(author_id=uuid.uuid4(), comment="no-op")

    def test_appends_edit_comment(self):
        resp = self._live()
        author = uuid.uuid4()
        resp.apply_edit(author_id=author, comment="fix email", email="new@b.com")
        assert len(resp.comments) == 1
        c = resp.comments[0]
        assert c.text == "fix email"
        assert c.author_id == author
        assert c.action is RespondentAction.EDIT


class TestApplyStatusTransition:
    def _at(self, status: RespondentStatus, selection_run_id=None) -> Respondent:
        return Respondent(
            assembly_id=uuid.uuid4(),
            external_id="R-ST",
            selection_status=status,
            selection_run_id=selection_run_id,
        )

    def test_allowed_transitions_matches_agreed_matrix(self):
        expected = {
            RespondentStatus.POOL: [RespondentStatus.SELECTED],
            RespondentStatus.SELECTED: [RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
            RespondentStatus.CONFIRMED: [RespondentStatus.WITHDRAWN],
            RespondentStatus.WITHDRAWN: [],
            RespondentStatus.PARTICIPATED: [],
            RespondentStatus.DELETED: [],
        }
        assert expected == ALLOWED_SELECTION_STATUS_TRANSITIONS

    def test_pool_to_selected_allowed_and_clears_run(self):
        resp = self._at(RespondentStatus.POOL)
        resp.apply_status_transition(
            new_status=RespondentStatus.SELECTED,
            author_id=uuid.uuid4(),
            comment="manual add",
        )
        assert resp.selection_status == RespondentStatus.SELECTED
        assert resp.selection_run_id is None

    def test_selected_to_confirmed_preserves_run_id(self):
        run_id = uuid.uuid4()
        resp = self._at(RespondentStatus.SELECTED, selection_run_id=run_id)
        resp.apply_status_transition(
            new_status=RespondentStatus.CONFIRMED,
            author_id=uuid.uuid4(),
            comment="confirmed on call",
        )
        assert resp.selection_status == RespondentStatus.CONFIRMED
        assert resp.selection_run_id == run_id

    def test_confirmed_to_withdrawn(self):
        run_id = uuid.uuid4()
        resp = self._at(RespondentStatus.CONFIRMED, selection_run_id=run_id)
        resp.apply_status_transition(
            new_status=RespondentStatus.WITHDRAWN,
            author_id=uuid.uuid4(),
            comment="withdrew after confirmation",
        )
        assert resp.selection_status == RespondentStatus.WITHDRAWN
        assert resp.selection_run_id == run_id

    def test_pool_to_confirmed_refused(self):
        resp = self._at(RespondentStatus.POOL)
        with pytest.raises(ValueError, match="not allowed"):
            resp.apply_status_transition(
                new_status=RespondentStatus.CONFIRMED,
                author_id=uuid.uuid4(),
                comment="try",
            )

    def test_no_transitions_out_of_withdrawn(self):
        resp = self._at(RespondentStatus.WITHDRAWN)
        with pytest.raises(ValueError, match="not allowed"):
            resp.apply_status_transition(
                new_status=RespondentStatus.CONFIRMED,
                author_id=uuid.uuid4(),
                comment="try",
            )

    def test_blank_comment_refused(self):
        resp = self._at(RespondentStatus.SELECTED)
        with pytest.raises(ValueError, match="comment"):
            resp.apply_status_transition(
                new_status=RespondentStatus.CONFIRMED,
                author_id=uuid.uuid4(),
                comment="   ",
            )

    def test_comment_prefixed_with_status_line(self):
        resp = self._at(RespondentStatus.SELECTED)
        resp.apply_status_transition(
            new_status=RespondentStatus.CONFIRMED,
            author_id=uuid.uuid4(),
            comment="confirmed on the phone",
        )
        assert len(resp.comments) == 1
        c = resp.comments[0]
        assert c.action == RespondentAction.EDIT
        assert "SELECTED" in c.text and "CONFIRMED" in c.text
        assert "confirmed on the phone" in c.text


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

    def test_returns_name_deleted_when_status_is_deleted(self):
        resp = self._make(attributes={"first_name": "Sarah", "last_name": "Jones"}, email="sarah@example.com")
        resp.delete_personal_data(uuid.uuid4(), "gdpr request")
        assert resp.display_name(["first_name", "last_name"]) == "Name deleted"


class TestValidateFieldNameCollisions:
    def test_empty_iterable_is_ok(self):
        validate_no_field_name_collisions([])

    def test_non_colliding_names_are_ok(self):
        validate_no_field_name_collisions(["age", "gender", "region"])

    def test_case_only_collision_raises(self):
        with pytest.raises(ValueError, match=r"first_name.*FirstName|FirstName.*first_name"):
            validate_no_field_name_collisions(["first_name", "FirstName"])

    def test_separator_only_collision_raises(self):
        with pytest.raises(ValueError, match=r"age-group.*age_group|age_group.*age-group"):
            validate_no_field_name_collisions(["age-group", "age_group"])

    def test_three_keys_two_collide_raises(self):
        with pytest.raises(ValueError, match=r"first_name.*FirstName|FirstName.*first_name"):
            validate_no_field_name_collisions(["age", "first_name", "FirstName"])

    def test_empty_normalisation_raises(self):
        with pytest.raises(ValueError, match="---"):
            validate_no_field_name_collisions(["---"])

    def test_whitespace_only_normalisation_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_no_field_name_collisions(["   "])

    def test_reserved_field_collision_raises(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_no_field_name_collisions(["Email"])

    def test_reserved_field_collision_with_separator(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_no_field_name_collisions(["external id"])

    def test_exact_duplicate_raises(self):
        with pytest.raises(ValueError, match="age"):
            validate_no_field_name_collisions(["age", "age"])

    def test_error_message_includes_normalised_form(self):
        with pytest.raises(ValueError, match="firstname"):
            validate_no_field_name_collisions(["first_name", "FirstName"])
