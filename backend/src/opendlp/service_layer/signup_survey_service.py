"""ABOUTME: MOCK signup survey service - in-memory stand-in and specification for the real one
ABOUTME: Blueprints call these; the real implementation swaps the module store for a repository"""

# This module is the seam between the signup-survey frontend and its (not yet
# implemented) persistence. The function signatures, permission checks and
# behaviours here are the contract; only the storage is fake - answers live in
# a module-level dict, so they survive within one process and vanish on
# restart. The real implementation replaces _STORE with a
# uow.user_signup_surveys repository over a user_signup_surveys table and
# changes nothing else. See docs/agent/919-registration-form/backend_plan.md
# and the 919-reference-implementation branch for the worked-out real version.

import uuid

import structlog

from opendlp.domain.user_signup_surveys import UserSignupSurvey

from .exceptions import InsufficientPermissions, UserNotFoundError
from .permissions import has_global_admin
from .unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)

# user_id -> UserSignupSurvey. MOCK ONLY: single-process, not persisted.
_STORE: dict[uuid.UUID, UserSignupSurvey] = {}


def reset_mock_survey_store() -> None:
    """Empty the in-memory store. Mock-only helper for tests."""
    _STORE.clear()


def _require_admin(uow: AbstractUnitOfWork, admin_user_id: uuid.UUID, action: str) -> None:
    """The permission check is real even though the storage is not."""
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")
    if not has_global_admin(admin_user):
        raise InsufficientPermissions(f"Only admins can {action}")


def save_signup_survey(uow: AbstractUnitOfWork, user_id: uuid.UUID, answers: dict[str, str]) -> None:
    """
    Store the optional signup survey answers for a newly registered user.

    Empty answers are dropped; if nothing was answered no record is stored at
    all, so a stored survey always means the user told us something.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    survey = UserSignupSurvey(user_id=user_id, answers=answers)
    if not survey.has_any_answers():
        return
    _STORE[user_id] = survey
    logger.info("Signup survey saved (mock)", user_id=str(user_id), answered=sorted(survey.answers))


def get_signup_survey(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> UserSignupSurvey | None:
    """
    Get a user's signup survey answers (admin only), or None if they have none.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _require_admin(uow, admin_user_id, "view user details")
    survey = _STORE.get(user_id)
    return survey.create_detached_copy() if survey else None
