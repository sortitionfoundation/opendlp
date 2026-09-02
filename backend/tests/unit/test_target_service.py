"""ABOUTME: Unit tests for target_service logic that needs no database
ABOUTME: Pure helpers - derived percentages, per-field problems, duplicate names - and permission refusals"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import target_csv_import, target_service
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.target_service import (
    TargetCategoryEdit,
    TargetValueEdit,
    _duplicate_value_errors,
    _value_problem,
)
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def uow():
    with FakeUnitOfWork() as entered:
        yield entered


class TestValueProblem:
    """Which box the form should point at, in words aimed at the person filling it in."""

    @pytest.mark.parametrize(
        ("edit", "expected_field"),
        [
            (TargetValueEdit(value="Male", min=-1), "min"),
            (TargetValueEdit(value="Male", max=-1), "max"),
            (TargetValueEdit(value="Male", min=9, max=2), "max"),
            (TargetValueEdit(value="Male", percentage=101.0), "percentage"),
            (TargetValueEdit(value="Male", percentage=-1.0), "percentage"),
        ],
    )
    def test_names_the_field_at_fault(self, edit, expected_field):
        problem = _value_problem(edit)

        assert problem is not None
        assert problem[0] == expected_field

    def test_a_sound_row_has_no_problem(self):
        assert _value_problem(TargetValueEdit(value="Male", min=3, max=7, percentage=50.0)) is None

    def test_a_deleted_row_is_not_checked(self):
        """Numbers on a row that is going away are nobody's problem."""
        assert _value_problem(TargetValueEdit(value="Male", min=9, max=2, deleted=True)) is None

    def test_a_relinked_row_is_not_checked(self):
        """Its min and max are about to be recalculated from the percentage."""
        assert _value_problem(TargetValueEdit(value="Male", min=9, max=2, relink=True)) is None


class TestDuplicateValueErrors:
    """`to_feature_dict` keys on the value name, so a duplicate drops a target from the run."""

    def test_flags_both_rows_of_a_clashing_pair(self):
        edit = TargetCategoryEdit(
            category_id=uuid.uuid4(),
            name="Gender",
            values=[
                TargetValueEdit(value="Male", form_id="a"),
                TargetValueEdit(value="Male", form_id="b"),
            ],
        )

        errors = _duplicate_value_errors(edit)

        assert {error.value_form_id for error in errors} == {"a", "b"}
        assert all(error.field == "value" for error in errors)

    def test_ignores_surrounding_whitespace(self):
        """The stored value is stripped, so " Male" and "Male" would collide once saved."""
        edit = TargetCategoryEdit(
            category_id=uuid.uuid4(),
            name="Gender",
            values=[TargetValueEdit(value="Male", form_id="a"), TargetValueEdit(value=" Male ", form_id="b")],
        )

        assert len(_duplicate_value_errors(edit)) == 2

    def test_a_deleted_row_does_not_clash(self):
        """Renaming a row to the name of one being removed is fine."""
        edit = TargetCategoryEdit(
            category_id=uuid.uuid4(),
            name="Gender",
            values=[
                TargetValueEdit(value="Male", form_id="a"),
                TargetValueEdit(value="Male", form_id="b", deleted=True),
            ],
        )

        assert _duplicate_value_errors(edit) == []

    def test_blank_rows_do_not_clash_with_each_other(self):
        """A missing name is already reported as its own problem."""
        edit = TargetCategoryEdit(
            category_id=uuid.uuid4(),
            name="Gender",
            values=[TargetValueEdit(value="", form_id="a"), TargetValueEdit(value="", form_id="b")],
        )

        assert _duplicate_value_errors(edit) == []

    def test_distinct_names_are_left_alone(self):
        edit = TargetCategoryEdit(
            category_id=uuid.uuid4(),
            name="Gender",
            values=[TargetValueEdit(value="Male", form_id="a"), TargetValueEdit(value="Female", form_id="b")],
        )

        assert _duplicate_value_errors(edit) == []


class TestPermissionRefusals:
    """Refusing a user with no rights needs no database - only a user and an assembly."""

    @pytest.fixture
    def assembly(self, uow):
        assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
        uow.assemblies.add(assembly)
        return assembly

    @pytest.fixture
    def viewer(self, uow):
        user = User(email="viewer@test.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)
        return user

    def test_creating_a_category_is_refused(self, uow, viewer, assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.create_target_category(uow, viewer.id, assembly.id, name="Gender")

    def test_reading_the_targets_is_refused(self, uow, viewer, assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.get_targets_for_assembly(uow, viewer.id, assembly.id)

    def test_deleting_every_target_is_refused(self, uow, viewer, assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.delete_targets_for_assembly(uow, viewer.id, assembly.id)

    def test_saving_the_whole_form_is_refused(self, uow, viewer, assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.save_all_targets(uow, viewer.id, assembly.id, [])

    def test_importing_a_csv_is_refused(self, uow, viewer, assembly):
        with pytest.raises(InsufficientPermissions):
            target_csv_import.import_targets_from_csv(
                uow, viewer.id, assembly.id, "feature,value,min,max\nGender,Male,1,2"
            )
