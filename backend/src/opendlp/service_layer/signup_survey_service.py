"""ABOUTME: Signup survey service - stores and reads the optional answers given at registration
ABOUTME: Answers persist on the user_signup_surveys table, one optional row per user"""

import uuid

import structlog

from opendlp.adapters.tabular_export import AbstractTabularExportTarget, TabularData
from opendlp.domain.user_signup_surveys import SIGNUP_SURVEY_QUESTIONS, UserSignupSurvey, leftover_answer_keys

from .exceptions import InsufficientPermissions, UserNotFoundError
from .permissions import has_global_admin
from .unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)


def _require_admin(uow: AbstractUnitOfWork, admin_user_id: uuid.UUID, action: str) -> None:
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")
    if not has_global_admin(admin_user):
        raise InsufficientPermissions(f"Only admins can {action}")


def save_signup_survey(uow: AbstractUnitOfWork, user_id: uuid.UUID, answers: dict[str, str]) -> None:
    """
    Store the optional signup survey answers for a newly registered user.

    Empty answers are dropped; if nothing was answered no record is stored at
    all, so a survey row always means the user told us something.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    survey = UserSignupSurvey(user_id=user_id, answers=answers)
    if not survey.has_any_answers():
        return
    uow.user_signup_surveys.add(survey)
    # The answered keys are safe to log; the answers themselves are personal data.
    logger.info("Signup survey saved", user_id=str(user_id), answered=sorted(survey.answers))


def get_signup_survey(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> UserSignupSurvey | None:
    """
    Get a user's signup survey answers (admin only), or None if they have none.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _require_admin(uow, admin_user_id, "view user details")
    survey = uow.user_signup_surveys.get_by_user_id(user_id)
    return survey.create_detached_copy() if survey else None


def export_users(uow: AbstractUnitOfWork, admin_user_id: uuid.UUID, *, target: AbstractTabularExportTarget) -> None:
    """
    Export every user with their signup survey answers to the given target (admin only).

    Survey columns come from SIGNUP_SURVEY_QUESTIONS, keyed by question key so
    the export is stable across UI languages. Answers stored under keys no
    longer in the spec get their own columns after the current ones, so old
    data is never silently dropped.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _require_admin(uow, admin_user_id, "export users")

    surveys = {survey.user_id: survey for survey in uow.user_signup_surveys.all()}
    leftover: set[str] = set()
    for survey in surveys.values():
        leftover.update(leftover_answer_keys(survey.answers))
    leftover_keys = sorted(leftover)

    question_keys = [question.key for question in SIGNUP_SURVEY_QUESTIONS]
    headers = [
        "email",
        "first_name",
        "last_name",
        "global_role",
        "active",
        "created_at",
        "email_confirmed_at",
        *question_keys,
        *leftover_keys,
    ]
    rows: list[list[str]] = []
    for user in sorted(uow.users.all(), key=lambda user: user.created_at):
        user_survey = surveys.get(user.id)
        answers = user_survey.answers if user_survey else {}
        rows.append([
            user.email,
            user.first_name,
            user.last_name,
            user.global_role.value,
            "yes" if user.is_active else "no",
            user.created_at.isoformat(),
            user.email_confirmed_at.isoformat() if user.email_confirmed_at else "",
            *(answers.get(key, "") for key in question_keys),
            *(answers.get(key, "") for key in leftover_keys),
        ])
    target.write_sheet("users", TabularData(headers=headers, rows=rows))
