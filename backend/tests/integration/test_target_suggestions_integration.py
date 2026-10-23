"""ABOUTME: Integration tests for accepting the target check's suggestions, against PostgreSQL
ABOUTME: Real targets and respondents that cannot all be met, so the real check makes the suggestions"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer.target_checking import check_targets_detailed
from opendlp.service_layer.target_service import get_targets_for_assembly
from opendlp.service_layer.target_suggestions import accept_all_suggestions, accept_suggestion
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    return SqlAlchemyUnitOfWork(postgres_session_factory)


def _fresh(uow):
    return SqlAlchemyUnitOfWork(uow.session_factory)


@pytest.fixture
def admin_user(uow):
    user = User(email="admin-suggestions@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


@pytest.fixture
def infeasible_assembly(uow):
    """Ten to select from ten older men and ten younger women.

    The age targets want at least six young people, but at most five women may
    be chosen and every young person is a woman, so no panel meets them all.
    The check suggests lowering the young minimum to 5 and raising the old
    maximum to 5.
    """
    assembly = Assembly(title="Suggestions Assembly", number_to_select=10)
    with uow:
        uow.assemblies.add(assembly)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.target_categories.add(
            TargetCategory(
                assembly_id=assembly.id,
                name="Gender",
                values=[TargetValue(value="Male", min=5, max=6), TargetValue(value="Female", min=4, max=5)],
            )
        )
        uow.target_categories.add(
            TargetCategory(
                assembly_id=assembly.id,
                name="Age",
                values=[
                    TargetValue(value="Young", min=6, max=7, comment="From the census"),
                    TargetValue(value="Old", min=3, max=4),
                ],
            )
        )
        for i in range(10):
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly.id,
                    external_id=f"m{i}",
                    attributes={"Gender": "Male", "Age": "Old"},
                    selection_status=RespondentStatus.POOL,
                )
            )
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly.id,
                    external_id=f"f{i}",
                    attributes={"Gender": "Female", "Age": "Young"},
                    selection_status=RespondentStatus.POOL,
                )
            )
        detached = assembly.create_detached_copy()
        uow.commit()
        return detached


def _age_value(uow, user_id, assembly_id, value_name):
    with _fresh(uow) as read_uow:
        categories = get_targets_for_assembly(read_uow, user_id, assembly_id)
    age = next(c for c in categories if c.name == "Age")
    return age, next(v for v in age.values if v.value == value_name)


class TestTheCheckSuggestsChanges:
    def test_the_real_check_suggests_a_min_and_a_max(self, uow, admin_user, infeasible_assembly):
        with _fresh(uow) as check_uow:
            result = check_targets_detailed(check_uow, admin_user.id, infeasible_assembly.id)

        assert result.success is False
        assert result.has_suggestions is True
        young = result.annotations["Age"]["Young"]
        old = result.annotations["Age"]["Old"]
        assert [(a.field, a.suggested_value) for a in young] == [("min", 5)]
        assert [(a.field, a.suggested_value) for a in old] == [("max", 5)]


class TestAcceptSuggestion:
    def test_applies_the_suggested_number_as_a_manual_override(self, uow, admin_user, infeasible_assembly):
        age, young = _age_value(uow, admin_user.id, infeasible_assembly.id, "Young")

        with _fresh(uow) as accept_uow:
            applied = accept_suggestion(
                accept_uow, admin_user.id, infeasible_assembly.id, age.id, young.value_id, "min", comment="Agreed"
            )
            accept_uow.commit()

        assert applied is True
        _age, young = _age_value(uow, admin_user.id, infeasible_assembly.id, "Young")
        assert (young.min, young.max) == (5, 7)
        assert young.minmax_manual is True
        assert "Agreed" in young.comment

    def test_a_field_with_no_suggestion_changes_nothing(self, uow, admin_user, infeasible_assembly):
        age, young = _age_value(uow, admin_user.id, infeasible_assembly.id, "Young")

        with _fresh(uow) as accept_uow:
            applied = accept_suggestion(
                accept_uow, admin_user.id, infeasible_assembly.id, age.id, young.value_id, "max"
            )
            accept_uow.commit()

        assert applied is False
        _age, young = _age_value(uow, admin_user.id, infeasible_assembly.id, "Young")
        assert (young.min, young.max) == (6, 7)


class TestAcceptAllSuggestions:
    def test_applies_every_suggestion_and_the_targets_become_feasible(self, uow, admin_user, infeasible_assembly):
        with _fresh(uow) as accept_uow:
            applied = accept_all_suggestions(accept_uow, admin_user.id, infeasible_assembly.id)
            accept_uow.commit()

        assert applied is True
        _age, young = _age_value(uow, admin_user.id, infeasible_assembly.id, "Young")
        _age, old = _age_value(uow, admin_user.id, infeasible_assembly.id, "Old")
        assert young.min == 5
        assert old.max == 5
        with _fresh(uow) as check_uow:
            assert check_targets_detailed(check_uow, admin_user.id, infeasible_assembly.id).success is True

    def test_nothing_to_accept_once_the_targets_are_feasible(self, uow, admin_user, infeasible_assembly):
        with _fresh(uow) as accept_uow:
            accept_all_suggestions(accept_uow, admin_user.id, infeasible_assembly.id)
            accept_uow.commit()

        with _fresh(uow) as accept_uow:
            assert accept_all_suggestions(accept_uow, admin_user.id, infeasible_assembly.id) is False
