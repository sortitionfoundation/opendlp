"""ABOUTME: Unit tests for the signup survey service (currently the in-memory mock)
ABOUTME: Written against the service interface only, so they must keep passing once the real implementation lands"""

import pytest

from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import signup_survey_service, user_service
from opendlp.service_layer.exceptions import InsufficientPermissions


@pytest.fixture(autouse=True)
def _fresh_survey_store():
    """The mock's store is process-global; give every test an empty one."""
    signup_survey_service.reset_mock_survey_store()
    yield
    signup_survey_service.reset_mock_survey_store()


def _make_user(uow, email: str, role: GlobalRole = GlobalRole.USER):
    user, _ = user_service.create_user(
        uow=uow,
        email=email,
        password="StrongPass123",  # pragma: allowlist secret
        global_role=role,
    )
    return user


class TestSaveSignupSurvey:
    def test_saves_answers_for_user(self, uow):
        admin = _make_user(uow, "admin@example.com", GlobalRole.ADMIN)
        user = _make_user(uow, "someone@example.com")

        signup_survey_service.save_signup_survey(uow, user.id, {"location": "Budapest", "comment": "hello"})

        survey = signup_survey_service.get_signup_survey(uow, user.id, admin.id)
        assert survey is not None
        assert survey.answers == {"location": "Budapest", "comment": "hello"}

    def test_all_empty_answers_store_nothing(self, uow):
        admin = _make_user(uow, "admin@example.com", GlobalRole.ADMIN)
        user = _make_user(uow, "someone@example.com")

        signup_survey_service.save_signup_survey(uow, user.id, {"location": "", "comment": ""})

        assert signup_survey_service.get_signup_survey(uow, user.id, admin.id) is None


class TestGetSignupSurvey:
    def test_returns_none_when_user_has_no_survey(self, uow):
        admin = _make_user(uow, "admin@example.com", GlobalRole.ADMIN)
        user = _make_user(uow, "someone@example.com")

        assert signup_survey_service.get_signup_survey(uow, user.id, admin.id) is None

    def test_non_admin_is_refused(self, uow):
        requester = _make_user(uow, "user@example.com")
        other = _make_user(uow, "other@example.com")

        with pytest.raises(InsufficientPermissions):
            signup_survey_service.get_signup_survey(uow, other.id, requester.id)
