"""ABOUTME: Contract tests for UserSignupSurveyRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from opendlp.domain.user_signup_surveys import UserSignupSurvey

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend


def _make_survey(
    backend: ContractBackend, user_id: uuid.UUID, answers: dict[str, str] | None = None
) -> UserSignupSurvey:
    if answers is None:
        answers = {"location": "Budapest", "organisation_size": "2_10"}
    survey = UserSignupSurvey(user_id=user_id, answers=answers)
    backend.repo.add(survey)
    backend.commit()
    return survey


class TestAddAndGet:
    def test_add_and_get_by_id(self, user_signup_survey_backend: ContractBackend):
        user = user_signup_survey_backend.make_user()
        survey = _make_survey(user_signup_survey_backend, user.id)

        retrieved = user_signup_survey_backend.repo.get(survey.id)
        assert retrieved is not None
        assert retrieved.id == survey.id
        assert retrieved.user_id == user.id
        assert retrieved.answers == {"location": "Budapest", "organisation_size": "2_10"}

    def test_get_nonexistent_returns_none(self, user_signup_survey_backend: ContractBackend):
        assert user_signup_survey_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_surveys(self, user_signup_survey_backend: ContractBackend):
        user1 = user_signup_survey_backend.make_user()
        user2 = user_signup_survey_backend.make_user()
        s1 = _make_survey(user_signup_survey_backend, user1.id)
        s2 = _make_survey(user_signup_survey_backend, user2.id)

        all_surveys = list(user_signup_survey_backend.repo.all())
        ids = {s.id for s in all_surveys}
        assert s1.id in ids
        assert s2.id in ids


class TestGetByUserId:
    def test_returns_survey_for_user(self, user_signup_survey_backend: ContractBackend):
        user = user_signup_survey_backend.make_user()
        survey = _make_survey(user_signup_survey_backend, user.id)

        retrieved = user_signup_survey_backend.repo.get_by_user_id(user.id)
        assert retrieved is not None
        assert retrieved.id == survey.id
        assert retrieved.answers == survey.answers

    def test_returns_none_when_user_has_no_survey(self, user_signup_survey_backend: ContractBackend):
        user = user_signup_survey_backend.make_user()
        assert user_signup_survey_backend.repo.get_by_user_id(user.id) is None

    def test_does_not_return_other_users_survey(self, user_signup_survey_backend: ContractBackend):
        user1 = user_signup_survey_backend.make_user()
        user2 = user_signup_survey_backend.make_user()
        _make_survey(user_signup_survey_backend, user1.id)

        assert user_signup_survey_backend.repo.get_by_user_id(user2.id) is None

    def test_answers_keep_keys_outside_the_current_spec(self, user_signup_survey_backend: ContractBackend):
        """Answers stored under a removed question key must survive the round-trip."""
        user = user_signup_survey_backend.make_user()
        _make_survey(user_signup_survey_backend, user.id, answers={"retired_question": "old answer"})

        retrieved = user_signup_survey_backend.repo.get_by_user_id(user.id)
        assert retrieved is not None
        assert retrieved.answers == {"retired_question": "old answer"}
