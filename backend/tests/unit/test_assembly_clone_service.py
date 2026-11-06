"""ABOUTME: Unit tests for the pure parts of cloning a project
ABOUTME: Option validation, the respondent status reset, and choosing the clone's title over fake repositories"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentStatus
from opendlp.service_layer.assembly_clone_service import (
    CloneOptions,
    choose_clone_title,
    clone_status,
    validate_clone_options,
)
from opendlp.service_layer.exceptions import AssemblyTitleTaken, InvalidCloneOptions


class TestValidateCloneOptions:
    def test_defaults_are_valid(self):
        validate_clone_options(CloneOptions())

    @pytest.mark.parametrize(
        "options",
        [
            CloneOptions(questions=False),
            CloneOptions(questions=False, registration=False, respondents=True, confirm_no_personal_data=True),
            CloneOptions(respondents=True),
            CloneOptions(preserve_respondent_status=True),
        ],
        ids=[
            "registration-without-questions",
            "respondents-without-questions",
            "respondents-unconfirmed",
            "preserve-without-respondents",
        ],
    )
    def test_forbidden_combinations(self, options):
        with pytest.raises(InvalidCloneOptions):
            validate_clone_options(options)

    def test_respondents_with_confirmation_are_valid(self):
        validate_clone_options(CloneOptions(respondents=True, confirm_no_personal_data=True))

    def test_targets_without_questions_is_valid(self):
        validate_clone_options(CloneOptions(questions=False, registration=False))


class TestCloneStatus:
    @pytest.mark.parametrize(
        ("original", "reset"),
        [
            (RespondentStatus.POOL, RespondentStatus.POOL),
            (RespondentStatus.SELECTED, RespondentStatus.POOL),
            (RespondentStatus.CONFIRMED, RespondentStatus.POOL),
            (RespondentStatus.WITHDRAWN, RespondentStatus.POOL),
            (RespondentStatus.TEST_SUBMISSION, RespondentStatus.TEST_SUBMISSION),
        ],
    )
    def test_reset(self, original, reset):
        assert clone_status(original, preserve=False) == reset

    @pytest.mark.parametrize("status", [s for s in RespondentStatus if s != RespondentStatus.DELETED])
    def test_preserve(self, status):
        assert clone_status(status, preserve=True) == status


class TestChooseCloneTitle:
    @pytest.fixture
    def organiser(self, uow):
        user = User(email="organiser@example.com", global_role=GlobalRole.ORGANISER, password_hash="hash")
        uow.users.add(user)
        return user

    @staticmethod
    def _own(uow, user, title):
        assembly = Assembly(title=title)
        uow.assemblies.add(assembly)
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        )

    def test_default_is_copy(self, uow, organiser):
        self._own(uow, organiser, "Climate")

        assert choose_clone_title(uow, organiser.id, "Climate", "") == "Climate (copy)"

    def test_takes_the_first_free_copy_number(self, uow, organiser):
        for title in ("Climate", "Climate (copy)", "climate (COPY 2)"):
            self._own(uow, organiser, title)

        assert choose_clone_title(uow, organiser.id, "Climate", "") == "Climate (copy 3)"

    def test_fails_when_every_copy_title_is_taken(self, uow, organiser):
        for title in ["Climate (copy)"] + [f"Climate (copy {n})" for n in range(2, 10)]:
            self._own(uow, organiser, title)

        with pytest.raises(AssemblyTitleTaken):
            choose_clone_title(uow, organiser.id, "Climate", "")

    def test_requested_title_is_stripped(self, uow, organiser):
        assert choose_clone_title(uow, organiser.id, "Climate", "  Demo  ") == "Demo"

    def test_requested_title_that_is_taken_fails(self, uow, organiser):
        self._own(uow, organiser, "Demo")

        with pytest.raises(AssemblyTitleTaken):
            choose_clone_title(uow, organiser.id, "Climate", "demo ")
