"""ABOUTME: Unit tests for headings and text placed among the registration questions.
ABOUTME: Covers the block's validation and the single ordered list it shares with the questions."""

import uuid

import pytest

from opendlp.domain.registration_content_block import (
    FormItemKind,
    FormItemRef,
    RegistrationContentBlock,
    form_item_ref,
    form_items,
    sections_at_headings,
)
from opendlp.domain.respondent_field_schema import (
    DerivationType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)

ASSEMBLY_ID = uuid.uuid4()


def _field(key: str, sort_order: int, **kwargs) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=ASSEMBLY_ID,
        field_key=key,
        label=key,
        group=kwargs.pop("group", RespondentFieldGroup.OTHER),
        sort_order=sort_order,
        **kwargs,
    )


def _derived(key: str, sort_order: int) -> RespondentFieldDefinition:
    return _field(
        key,
        sort_order,
        group=RespondentFieldGroup.DERIVED,
        is_derived=True,
        derived_from=["source"],
        derivation_type=DerivationType.SMALL_MAPPING,
        derivation_config={"mapping": {}},
    )


class TestRegistrationContentBlock:
    def test_heading_and_body_are_kept(self) -> None:
        block = RegistrationContentBlock(
            assembly_id=ASSEMBLY_ID, sort_order=10, heading="  About you  ", body_html="<p>Hi</p>"
        )

        assert block.heading == "About you"
        assert block.body_html == "<p>Hi</p>"
        assert block.sort_order == 10
        assert block.id is not None

    def test_a_heading_alone_is_enough(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="Consent")

        assert block.body_html == ""

    def test_a_body_alone_is_enough(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, body_html="<p>Read this</p>")

        assert block.heading == ""

    @pytest.mark.parametrize("body_html", ["", "   ", "<p></p>", "<p> </p><p><br></p>"])
    def test_a_block_with_nothing_in_it_is_refused(self, body_html: str) -> None:
        """An empty editor still posts a paragraph, which says nothing."""
        with pytest.raises(ValueError):
            RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="  ", body_html=body_html)

    def test_a_body_of_only_a_horizontal_line_counts_as_content(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, body_html="<hr>")

        assert block.body_html == "<hr>"

    def test_negative_sort_order_is_refused(self) -> None:
        with pytest.raises(ValueError):
            RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=-1, heading="x")

    def test_update_changes_the_content_and_touches_updated_at(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="Old")
        before = block.updated_at

        block.update(heading="New", body_html="<p>More</p>")

        assert block.heading == "New"
        assert block.body_html == "<p>More</p>"
        assert block.updated_at >= before

    def test_update_refuses_to_empty_the_block(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="Old")

        with pytest.raises(ValueError):
            block.update(heading="", body_html="")
        assert block.heading == "Old"

    def test_detached_copy_is_equal_and_independent(self) -> None:
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="Old")

        copy = block.create_detached_copy()
        copy.heading = "Changed"

        assert copy == block
        assert copy is not block
        assert block.heading == "Old"
        assert copy.created_at == block.created_at


class TestFormItems:
    def test_questions_and_blocks_merge_by_sort_order(self) -> None:
        heading = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="About you")
        first = _field("first_name", 20)
        consent_heading = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=30, heading="Consent")
        consent = _field("consent", 40)

        items = form_items([consent, first], [consent_heading, heading])

        assert items == [heading, first, consent_heading, consent]

    def test_derived_fields_are_not_on_the_list(self) -> None:
        """Computed questions are managed on the targets step, never arranged here."""
        question = _field("year_of_birth", 10)

        assert form_items([question, _derived("age", 5)], []) == [question]

    def test_ties_put_the_question_first(self) -> None:
        question = _field("first_name", 10)
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="Hi")

        assert form_items([question], [block]) == [question, block]

    def test_a_ref_names_the_kind_and_id(self) -> None:
        question = _field("first_name", 10)
        block = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=20, heading="Hi")

        assert form_item_ref(question) == FormItemRef(FormItemKind.QUESTION, question.id)
        assert form_item_ref(block) == FormItemRef(FormItemKind.BLOCK, block.id)

    def test_a_ref_round_trips_through_its_form_value(self) -> None:
        ref = FormItemRef(FormItemKind.BLOCK, uuid.uuid4())

        assert FormItemRef.parse(ref.form_value) == ref

    @pytest.mark.parametrize("raw", ["", "block", "heading:9f0c3a52-5d1e-4b7a-8a37-2f6f3c1d0b11", "block:not-a-uuid"])
    def test_a_malformed_form_value_parses_to_none(self, raw: str) -> None:
        assert FormItemRef.parse(raw) is None


class TestSectionsAtHeadings:
    def _labels(self, sections) -> list[tuple[str, list[str]]]:
        return [(str(s.label), [f.field_key for f in s.fields]) for s in sections]

    def test_each_heading_starts_a_section(self):
        about = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=10, heading="About you")
        consent = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=40, heading="Consent")
        fields = [_field("gender", 20), _field("age", 30), _field("consent", 50)]

        sections = sections_at_headings(fields, [about, consent])

        assert self._labels(sections) == [("About you", ["gender", "age"]), ("Consent", ["consent"])]

    def test_questions_before_any_heading_go_under_answers(self):
        heading = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=20, heading="More")

        sections = sections_at_headings([_field("first", 10), _field("second", 30)], [heading])

        assert self._labels(sections) == [("Answers", ["first"]), ("More", ["second"])]

    def test_text_without_a_heading_does_not_start_a_section(self):
        """Text is addressed to the respondent filling the form, not to whoever reads their record."""
        text = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=20, body_html="<p>Now some more</p>")

        sections = sections_at_headings([_field("first", 10), _field("second", 30)], [text])

        assert self._labels(sections) == [("Answers", ["first", "second"])]

    def test_a_heading_with_no_questions_after_it_is_left_out(self):
        empty = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=20, heading="Nothing here")

        sections = sections_at_headings([_field("first", 10)], [empty])

        assert self._labels(sections) == [("Answers", ["first"])]

    def test_computed_questions_come_last_in_their_own_section(self):
        heading = RegistrationContentBlock(assembly_id=ASSEMBLY_ID, sort_order=5, heading="About you")

        sections = sections_at_headings([_derived("region", 1), _field("postcode", 10)], [heading])

        assert self._labels(sections) == [("About you", ["postcode"]), ("Computed questions", ["region"])]

    def test_no_fields_no_sections(self):
        assert sections_at_headings([], []) == []
