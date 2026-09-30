"""ABOUTME: Unit tests for the signup survey service
ABOUTME: Written against the service interface only, over fake repositories"""

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import signup_survey_service, user_service
from opendlp.service_layer.exceptions import InsufficientPermissions


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


class TestExportUsers:
    def test_exports_users_with_survey_columns(self, uow):
        admin = _make_user(uow, "admin@example.com", GlobalRole.ADMIN)
        user = _make_user(uow, "someone@example.com")
        signup_survey_service.save_signup_survey(uow, user.id, {"location": "Budapest", "organisation_size": "2_10"})

        target = CsvExportTarget()
        signup_survey_service.export_users(uow, admin.id, target=target)

        lines = target.getvalue().lstrip("﻿").splitlines()
        headers = lines[0].split(",")
        assert headers[:4] == ["email", "first_name", "last_name", "global_role"]
        assert "location" in headers
        assert "organisation_size" in headers

        rows = [line.split(",") for line in lines[1:]]
        assert len(rows) == 2  # admin + user
        user_row = next(row for row in rows if row[0] == "someone@example.com")
        assert user_row[headers.index("location")] == "Budapest"
        assert user_row[headers.index("organisation_size")] == "2_10"
        admin_row = next(row for row in rows if row[0] == "admin@example.com")
        assert admin_row[headers.index("location")] == ""

    def test_answers_to_removed_questions_get_their_own_columns(self, uow):
        admin = _make_user(uow, "admin@example.com", GlobalRole.ADMIN)
        user = _make_user(uow, "someone@example.com")
        signup_survey_service.save_signup_survey(uow, user.id, {"location": "Budapest", "retired_question": "42"})

        target = CsvExportTarget()
        signup_survey_service.export_users(uow, admin.id, target=target)

        lines = target.getvalue().lstrip("﻿").splitlines()
        headers = lines[0].split(",")
        assert headers[-1] == "retired_question"
        user_row = next(row for row in (line.split(",") for line in lines[1:]) if row[0] == "someone@example.com")
        assert user_row[headers.index("retired_question")] == "42"

    def test_non_admin_is_refused(self, uow):
        requester = _make_user(uow, "user@example.com")

        with pytest.raises(InsufficientPermissions):
            signup_survey_service.export_users(uow, requester.id, target=CsvExportTarget())
