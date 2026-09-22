"""ABOUTME: Unit tests for the UserSignupSurvey domain model and question spec
ABOUTME: Covers answer cleaning, leftover keys for removed questions, and display values"""

import uuid

from opendlp.domain.user_signup_surveys import (
    SIGNUP_SURVEY_QUESTIONS,
    SignupSurveyQuestion,
    SurveyFieldType,
    UserSignupSurvey,
    get_question,
    leftover_answer_keys,
)


class TestUserSignupSurvey:
    def test_empty_answers_are_dropped(self):
        survey = UserSignupSurvey(
            user_id=uuid.uuid4(),
            answers={"location": "Budapest", "organisation_name": "", "comment": ""},
        )
        assert survey.answers == {"location": "Budapest"}

    def test_has_any_answers(self):
        user_id = uuid.uuid4()
        assert not UserSignupSurvey(user_id=user_id).has_any_answers()
        assert not UserSignupSurvey(user_id=user_id, answers={"location": ""}).has_any_answers()
        assert UserSignupSurvey(user_id=user_id, answers={"location": "here"}).has_any_answers()

    def test_detached_copy_is_equal_but_independent(self):
        survey = UserSignupSurvey(user_id=uuid.uuid4(), answers={"location": "Budapest"})
        copy = survey.create_detached_copy()
        assert copy == survey
        assert copy.answers == survey.answers
        copy.answers["location"] = "elsewhere"
        assert survey.answers["location"] == "Budapest"


class TestQuestionSpec:
    def test_get_question_finds_spec_entries(self):
        for question in SIGNUP_SURVEY_QUESTIONS:
            assert get_question(question.key) is question
        assert get_question("no_such_question") is None

    def test_question_keys_are_unique(self):
        keys = [question.key for question in SIGNUP_SURVEY_QUESTIONS]
        assert len(keys) == len(set(keys))

    def test_leftover_answer_keys_flags_removed_questions(self):
        answers = {"location": "Budapest", "favourite_colour": "green", "old_question": "yes"}
        assert leftover_answer_keys(answers) == ["favourite_colour", "old_question"]
        assert leftover_answer_keys({"location": "Budapest"}) == []


class TestDisplayValue:
    def test_free_text_shown_as_is(self):
        question = SignupSurveyQuestion(key="location", label="Where?")
        assert question.display_value({"location": "Budapest"}) == "Budapest"
        assert question.display_value({}) == ""

    def test_choice_token_mapped_to_label(self):
        question = SignupSurveyQuestion(
            key="size",
            label="Size?",
            field_type=SurveyFieldType.SELECT,
            choices={"small": "A small one", "large": "A large one"},
        )
        assert question.display_value({"size": "small"}) == "A small one"

    def test_unknown_choice_token_falls_back_to_raw_value(self):
        question = SignupSurveyQuestion(
            key="size",
            label="Size?",
            field_type=SurveyFieldType.SELECT,
            choices={"small": "A small one"},
        )
        assert question.display_value({"size": "retired_token"}) == "retired_token"
