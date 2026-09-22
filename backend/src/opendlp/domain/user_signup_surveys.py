"""ABOUTME: Signup survey domain model holding the optional questions answered at registration
ABOUTME: One question spec drives the form, admin display and export; answers live in a JSON dict"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from opendlp.translations import lazy_gettext as _l


class SurveyFieldType(Enum):
    TEXT = "text"
    SELECT = "select"
    RADIO = "radio"
    TEXTAREA = "textarea"


@dataclass(frozen=True)
class SignupSurveyQuestion:
    """One question on the signup form.

    ``key`` names the answer in the stored JSON dict. ``choices`` maps stored
    answer tokens to translatable labels for SELECT/RADIO questions; free-text
    questions leave it empty and display the raw answer.
    """

    key: str
    label: str
    field_type: SurveyFieldType = SurveyFieldType.TEXT
    choices: dict[str, str] = field(default_factory=dict)
    hint: str = ""

    def display_value(self, answers: dict[str, str]) -> str:
        """The human-readable answer for this question, or '' if unanswered."""
        raw = answers.get(self.key, "")
        if not raw or not self.choices:
            return raw
        return str(self.choices.get(raw, raw))


# The canonical list of signup survey questions, in display order. The form,
# the admin user view and the export are all generated from this list, so
# adding, rewording or removing a question is a change here and nowhere else.
# Answers already stored under a removed key keep showing up (see
# leftover_answer_keys), so old data survives question changes.
SIGNUP_SURVEY_QUESTIONS: list[SignupSurveyQuestion] = [
    SignupSurveyQuestion(
        key="location",
        label=_l("Where are you in the world?"),
    ),
    SignupSurveyQuestion(
        key="organisation_name",
        label=_l("Name of organisation"),
    ),
    SignupSurveyQuestion(
        key="organisation_size",
        label=_l("Size of organisation"),
        field_type=SurveyFieldType.SELECT,
        choices={
            "just_me": _l("Just me"),
            "2_10": _l("2 to 10 people"),
            "11_50": _l("11 to 50 people"),
            "51_250": _l("51 to 250 people"),
            "over_250": _l("More than 250 people"),
        },
    ),
    SignupSurveyQuestion(
        key="deliberative_experience",
        label=_l("Experience of running deliberative processes"),
        field_type=SurveyFieldType.SELECT,
        choices={
            "none": _l("None yet"),
            "participated": _l("I have taken part in one, but not organised one"),
            "organised_few": _l("I have organised one or two"),
            "organised_many": _l("I have organised many"),
        },
    ),
    SignupSurveyQuestion(
        key="process_plan",
        label=_l("Are you wanting to run a deliberative process soon?"),
        field_type=SurveyFieldType.RADIO,
        choices={
            "within_3_months": _l("Yes, within the next 3 months"),
            "within_year": _l("Yes, within the next year"),
            "no_plans": _l("No concrete plans yet"),
            "exploring": _l("Just exploring"),
        },
    ),
    SignupSurveyQuestion(
        key="comment",
        label=_l("Anything else you want to tell us?"),
        field_type=SurveyFieldType.TEXTAREA,
    ),
]


def get_question(key: str) -> SignupSurveyQuestion | None:
    """The question with this key, or None if the spec no longer has it."""
    for question in SIGNUP_SURVEY_QUESTIONS:
        if question.key == key:
            return question
    return None


def leftover_answer_keys(answers: dict[str, str]) -> list[str]:
    """Answer keys present in stored data but absent from the current spec.

    A question removed from SIGNUP_SURVEY_QUESTIONS leaves its old answers
    behind; they are still shown and exported under their raw key.
    """
    spec_keys = {question.key for question in SIGNUP_SURVEY_QUESTIONS}
    return sorted(key for key in answers if key not in spec_keys)


class UserSignupSurvey:
    """Answers a user gave to the optional questions on the signup form."""

    def __init__(
        self,
        user_id: uuid.UUID,
        answers: dict[str, str] | None = None,
        survey_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = survey_id or uuid.uuid4()
        self.user_id = user_id
        # Drop empty answers so an untouched field is absent, not stored as "".
        self.answers = {key: value for key, value in (answers or {}).items() if value}
        self.created_at = created_at or datetime.now(UTC)

    def has_any_answers(self) -> bool:
        """Whether the user answered anything at all."""
        return bool(self.answers)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserSignupSurvey):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "UserSignupSurvey":
        """Create a detached copy of this survey for use outside SQLAlchemy sessions"""
        return UserSignupSurvey(
            user_id=self.user_id,
            answers=dict(self.answers),
            survey_id=self.id,
            created_at=self.created_at,
        )
