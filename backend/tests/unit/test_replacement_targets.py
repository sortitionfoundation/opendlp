"""ABOUTME: Unit tests for the replacement targets service over a FakeUnitOfWork
ABOUTME: Covers the review plan's arithmetic, the form parsing and the pre-run validation"""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions
from opendlp.service_layer.replacement_targets import (
    ReplacementPlan,
    build_replacement_plan,
    validate_replacement_form,
)


def _seed(uow, *, number_to_select: int = 6):
    """Gender Male [3,3] / Female [3,3]; Age 18-30 [2,4] / 31+ [2,4].

    The category is "Age" over an "age" column: the library matches names
    case-insensitively and no more loosely, so the seed stays runnable.

    Selected: M1 (18-30), F1 (31+). Confirmed: M2 (31+). Withdrawn: F2 (18-30).
    Pool: M3 (18-30), M4 (31+, cannot attend), F3 (18-30), F4 (31+), F5 (31+).
    """
    admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(admin)
    assembly = Assembly(title="Test Assembly", number_to_select=number_to_select)
    assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
    uow.assemblies.add(assembly)

    gender = TargetCategory(assembly_id=assembly.id, name="Gender", sort_order=0)
    gender.add_value(TargetValue(value="Male", min=3, max=3))
    gender.add_value(TargetValue(value="Female", min=3, max=3))
    age = TargetCategory(assembly_id=assembly.id, name="Age", sort_order=1)
    age.add_value(TargetValue(value="18-30", min=2, max=4))
    age.add_value(TargetValue(value="31+", min=2, max=4))
    uow.target_categories.add(gender)
    uow.target_categories.add(age)

    rows = [
        ("M1", "Male", "18-30", RespondentStatus.SELECTED, True),
        ("F1", "Female", "31+", RespondentStatus.SELECTED, True),
        ("M2", "Male", "31+", RespondentStatus.CONFIRMED, True),
        ("F2", "Female", "18-30", RespondentStatus.WITHDRAWN, True),
        ("M3", "Male", "18-30", RespondentStatus.POOL, True),
        ("M4", "Male", "31+", RespondentStatus.POOL, False),
        ("F3", "Female", "18-30", RespondentStatus.POOL, True),
        ("F4", "Female", "31+", RespondentStatus.POOL, True),
        ("F5", "Female", "31+", RespondentStatus.POOL, True),
    ]
    for ext_id, g, a, status, can_attend in rows:
        uow.respondents.add(
            Respondent(
                assembly_id=assembly.id,
                external_id=ext_id,
                attributes={"gender": g, "age": a},
                selection_status=status,
                can_attend=can_attend,
            )
        )
    return admin, assembly, gender, age


def _rows(plan: ReplacementPlan) -> dict[tuple[str, str], object]:
    return {(c.name, r.value): r for c in plan.categories for r in c.rows}


def _form_from_plan(plan: ReplacementPlan, number: int | None = None) -> dict[str, str]:
    form = {"number_to_select": str(plan.default_number if number is None else number)}
    for category in plan.categories:
        for row in category.rows:
            form[row.min_field] = str(row.calculated.min)
            form[row.max_field] = str(row.calculated.max)
    return form


class TestBuildReplacementPlan:
    def test_headline_numbers(self, uow):
        """Three people hold a place, so three of the six are still to fill."""
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        assert plan.number_to_select == 6
        assert plan.held_total == 3
        assert plan.calculated_number == 3
        assert not plan.nothing_to_fill

    def test_per_value_arithmetic_ignores_withdrawn(self, uow):
        """F2's withdrawal frees a Female / 18-30 place; M2's confirmation still holds one."""
        admin, assembly, _, _ = _seed(uow)
        rows = _rows(build_replacement_plan(uow, admin.id, assembly.id))

        male = rows[("Gender", "Male")]
        assert (male.held, male.calculated.min, male.calculated.max) == (2, 1, 1)
        female = rows[("Gender", "Female")]
        assert (female.held, female.calculated.min, female.calculated.max) == (1, 2, 2)
        young = rows[("Age", "18-30")]
        assert (young.held, young.calculated.min, young.calculated.max) == (1, 1, 3)
        older = rows[("Age", "31+")]
        assert (older.held, older.calculated.min, older.calculated.max) == (2, 0, 2)

    def test_available_counts_eligible_pool_only(self, uow):
        """M4 cannot attend, so only M3 is available among Male."""
        admin, assembly, _, _ = _seed(uow)
        rows = _rows(build_replacement_plan(uow, admin.id, assembly.id))
        assert rows[("Gender", "Male")].available == 1
        assert rows[("Gender", "Female")].available == 3
        assert rows[("Age", "31+")].available == 2

    def test_range_and_default_number(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        assert (plan.min_select, plan.max_select) == (3, 3)
        assert plan.number_in_range
        assert plan.default_number == 3
        assert not plan.targets_conflict

    def test_shortfall_and_tight_rows(self, uow):
        """Male needs 1 and has exactly 1 spare person: tight, not short."""
        admin, assembly, _, _ = _seed(uow)
        rows = _rows(build_replacement_plan(uow, admin.id, assembly.id))
        male = rows[("Gender", "Male")]
        assert male.shortfall == 0
        assert male.is_tight
        older = rows[("Age", "31+")]
        assert older.calculated.min == 0
        assert not older.is_tight

    def test_short_row_and_category_problem(self, uow):
        """With M3 gone, Male needs 1 and nobody eligible remains."""
        admin, assembly, _, _ = _seed(uow)
        m3 = next(r for r in uow.respondents.get_by_assembly_id(assembly.id) if r.external_id == "M3")
        m3.eligible = False
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        rows = _rows(plan)
        assert rows[("Gender", "Male")].shortfall == 1
        assert rows[("Gender", "Male")].is_short
        gender = next(c for c in plan.categories if c.name == "Gender")
        age = next(c for c in plan.categories if c.name == "Age")
        assert gender.has_problem
        assert not age.has_problem

    def test_category_matches_its_column_loosely(self, uow):
        """An 'Age Range' category finds an age_range column, as the dashboard does."""
        admin, assembly, _, _ = _seed(uow)
        band = TargetCategory(assembly_id=assembly.id, name="Age Range", sort_order=2)
        band.add_value(TargetValue(value="young", min=1, max=6))
        uow.target_categories.add(band)
        for r in uow.respondents.get_by_assembly_id(assembly.id):
            r.attributes = {**r.attributes, "age_range": "young"}
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        cat = next(c for c in plan.categories if c.name == "Age Range")
        assert cat.attribute_matched
        assert cat.rows[0].held == 3

    def test_unmatched_category_has_zero_counts_and_is_flagged(self, uow):
        admin, assembly, _, _ = _seed(uow)
        region = TargetCategory(assembly_id=assembly.id, name="Region", sort_order=2)
        region.add_value(TargetValue(value="North", min=1, max=6))
        uow.target_categories.add(region)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        cat = next(c for c in plan.categories if c.name == "Region")
        assert not cat.attribute_matched
        assert cat.has_problem
        assert cat.rows[0].held == 0
        assert cat.rows[0].calculated.min == 1

    def test_over_held_value(self, uow):
        """A value holding more than its maximum has nothing to fill and says so."""
        admin, assembly, gender, _ = _seed(uow)
        gender.values[0].max = 1
        gender.values[0].min = 1
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        male = _rows(plan)[("Gender", "Male")]
        assert male.over_held
        assert (male.calculated.min, male.calculated.max) == (0, 0)

    def test_nothing_to_fill_when_panel_is_full(self, uow):
        admin, assembly, _, _ = _seed(uow, number_to_select=3)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        assert plan.nothing_to_fill
        assert plan.calculated_number == 0

    def test_number_outside_range_is_flagged(self, uow):
        """Eight to select but the gender targets only allow three more."""
        admin, assembly, _, _ = _seed(uow, number_to_select=8)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        assert plan.calculated_number == 5
        assert not plan.number_in_range
        assert plan.default_number == plan.max_select

    def test_replacement_info(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        assert plan.replacement_info(3, edited=False) == {
            "number_to_select_overall": 6,
            "held_total": 3,
            "calculated_number": 3,
            "number_to_select_used": 3,
            "edited": False,
        }

    def test_requires_assembly_management(self, uow):
        _, assembly, _, _ = _seed(uow)
        viewer = User(email="viewer@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(viewer)
        with pytest.raises(InsufficientPermissions):
            build_replacement_plan(uow, viewer.id, assembly.id)

    def test_assembly_not_found(self, uow):
        admin, _, _, _ = _seed(uow)
        with pytest.raises(AssemblyNotFoundError):
            build_replacement_plan(uow, admin.id, uuid.uuid4())


class TestValidateReplacementForm:
    def test_calculated_numbers_pass_and_build_the_snapshot(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)

        result = validate_replacement_form(uow, assembly.id, plan, _form_from_plan(plan))

        assert result.ok, (result.errors, result.value_errors)
        assert result.number_to_select == 3
        assert not result.edited
        gender = next(c for c in result.targets_snapshot if c["name"] == "Gender")
        male = next(v for v in gender["values"] if v["value"] == "Male")
        assert male["min"] == 1
        assert male["max"] == 1
        assert male["overall_min"] == 3
        assert male["overall_max"] == 3
        assert male["held"] == 2
        assert male["calculated_min"] == 1
        assert male["calculated_max"] == 1
        assert male["max_flex"] == MAX_FLEX_UNSET

    def test_edited_numbers_are_recorded_as_edited(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        older = _rows(plan)[("Age", "31+")]
        form[older.max_field] = "3"

        result = validate_replacement_form(uow, assembly.id, plan, form)

        assert result.ok, (result.errors, result.value_errors)
        assert result.edited
        age = next(c for c in result.targets_snapshot if c["name"] == "Age")
        assert next(v for v in age["values"] if v["value"] == "31+")["max"] == 3

    def test_missing_number_is_an_error(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        form["number_to_select"] = "0"
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert not result.ok
        assert len(result.errors) == 1

    def test_non_integer_cell_is_a_cell_error(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        male = _rows(plan)[("Gender", "Male")]
        form[male.min_field] = "two"
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert not result.ok
        assert list(result.value_errors) == [male.value_id]

    def test_max_below_min_is_a_cell_error(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        male = _rows(plan)[("Gender", "Male")]
        form[male.min_field] = "2"
        form[male.max_field] = "1"
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert list(result.value_errors) == [male.value_id]

    def test_missing_cell_means_the_targets_changed(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        del form[_rows(plan)[("Gender", "Male")].max_field]
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert not result.ok
        assert "changed" in result.errors[0]

    def test_cross_category_conflict_blocks(self, uow):
        """Gender still needs 3 but Age Range is edited to allow at most 2."""
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        rows = _rows(plan)
        form[rows[("Age", "18-30")].max_field] = "1"
        form[rows[("Age", "31+")].max_field] = "1"
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert not result.ok
        assert any("Gender" in e and "Age" in e for e in result.errors)

    def test_number_outside_range_blocks(self, uow):
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        result = validate_replacement_form(uow, assembly.id, plan, _form_from_plan(plan, number=5))
        assert not result.ok
        assert any("5" in e for e in result.errors)

    def test_pool_shortfall_is_a_cell_error(self, uow):
        """Male edited to need 2, but only M3 is eligible."""
        admin, assembly, _, _ = _seed(uow)
        plan = build_replacement_plan(uow, admin.id, assembly.id)
        form = _form_from_plan(plan)
        rows = _rows(plan)
        form[rows[("Gender", "Male")].min_field] = "2"
        form[rows[("Gender", "Male")].max_field] = "2"
        form[rows[("Gender", "Female")].min_field] = "1"
        form[rows[("Gender", "Female")].max_field] = "1"
        result = validate_replacement_form(uow, assembly.id, plan, form)
        assert not result.ok
        assert list(result.value_errors) == [rows[("Gender", "Male")].value_id]
        assert "only 1" in result.value_errors[rows[("Gender", "Male")].value_id][0]
