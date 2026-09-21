"""ABOUTME: Unit tests for target_service logic that needs no database
ABOUTME: Pure helpers - derived percentages, per-field problems, duplicate names - and permission refusals"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import target_csv_import, target_service
from opendlp.service_layer.exceptions import FieldDefinitionConflictError, InsufficientPermissions
from opendlp.service_layer.target_service import (
    LinkAction,
    TargetCategoryEdit,
    TargetLinkedError,
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


class TestTargetLinkedGuards:
    """Renaming or deleting a category that fields feed needs an explicit force-unlink."""

    @pytest.fixture
    def admin(self, uow):
        user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(user)
        return user

    @pytest.fixture
    def assembly(self, uow):
        assembly = Assembly(title="Guarded Assembly", number_to_select=40)
        uow.assemblies.add(assembly)
        return assembly

    def _linked_category(self, uow, assembly, name="Gender"):
        category = TargetCategory(
            assembly_id=assembly.id,
            name=name,
            values=[TargetValue(value="Male", min=1, max=5), TargetValue(value="Female", min=1, max=5)],
        )
        uow.target_categories.add(category)
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key=name,
            label=name,
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )
        uow.respondent_field_definitions.add(field)
        return category, field

    def test_rename_is_blocked_naming_the_linked_fields(self, uow, admin, assembly):
        category, _field = self._linked_category(uow, assembly)

        with pytest.raises(TargetLinkedError) as excinfo:
            target_service.update_target_category(uow, admin.id, assembly.id, category.id, name="Sex")

        (block,) = excinfo.value.blocks
        assert block.action == LinkAction.RENAME
        assert block.category_name == "Gender"
        assert block.field_labels == ["Gender"]
        assert category.name == "Gender"

    def test_rename_with_force_unlink_proceeds_and_unlinks(self, uow, admin, assembly):
        category, field = self._linked_category(uow, assembly)

        target_service.update_target_category(uow, admin.id, assembly.id, category.id, name="Sex", force_unlink=True)

        assert category.name == "Sex"
        assert field.target_category_id is None

    def test_editing_without_renaming_needs_no_force(self, uow, admin, assembly):
        category, field = self._linked_category(uow, assembly)

        target_service.update_target_category(
            uow, admin.id, assembly.id, category.id, name="Gender", comment="census 2021"
        )

        assert category.comment == "census 2021"
        assert field.target_category_id == category.id

    def test_delete_is_blocked_then_forced(self, uow, admin, assembly):
        category, field = self._linked_category(uow, assembly)

        with pytest.raises(TargetLinkedError) as excinfo:
            target_service.delete_target_category(uow, admin.id, assembly.id, category.id)
        assert excinfo.value.blocks[0].action == LinkAction.DELETE

        target_service.delete_target_category(uow, admin.id, assembly.id, category.id, force_unlink=True)

        assert uow.target_categories.get(category.id) is None
        assert field.target_category_id is None

    def _derived_category(self, uow, assembly, name="Region"):
        """A target fed by a computed field, which is in turn computed from a question."""
        category = TargetCategory(
            assembly_id=assembly.id,
            name=name,
            values=[TargetValue(value="North", min=1, max=5), TargetValue(value="South", min=1, max=5)],
        )
        uow.target_categories.add(category)
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key="postcode",
                label="Postcode",
                group=RespondentFieldGroup.ADDRESS,
                sort_order=10,
                field_type=FieldType.TEXT,
            )
        )
        derived = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key=name,
            label=humanise_field_key(name),
            group=RespondentFieldGroup.DERIVED,
            sort_order=20,
            is_derived=True,
            derived_from=["postcode"],
            derivation_type=DerivationType.LARGE_MAPPING,
            derivation_config={"fallback": "UNKNOWN"},
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="North"), ChoiceOption(value="South")],
            target_category_id=category.id,
        )
        uow.respondent_field_definitions.add(derived)
        respondent = Respondent(
            assembly_id=assembly.id, external_id="r1", attributes={"postcode": "E1 6AN", name: "North"}
        )
        uow.respondents.add(respondent)
        return category, derived, respondent

    def test_renaming_a_target_carries_its_computed_field_along(self, uow, admin, assembly):
        """Selection pairs a target with its data by name, so the key has to follow the rename."""
        category, derived, respondent = self._derived_category(uow, assembly)

        # No confirmation: nothing is unlinked and nothing is lost.
        target_service.update_target_category(uow, admin.id, assembly.id, category.id, name="Area")

        assert category.name == "Area"
        assert derived.field_key == "Area"
        assert derived.label == "Area"
        assert derived.target_category_id == category.id
        assert respondent.attributes == {"postcode": "E1 6AN", "Area": "North"}

    def test_renaming_a_target_onto_an_existing_question_saves_nothing(self, uow, admin, assembly):
        category, derived, _respondent = self._derived_category(uow, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="already exists"):
            target_service.update_target_category(uow, admin.id, assembly.id, category.id, name="postcode")

        assert category.name == "Region"
        assert derived.field_key == "Region"

    def test_deleting_a_target_deletes_the_computed_field_that_fed_it(self, uow, admin, assembly):
        category, derived, respondent = self._derived_category(uow, assembly)

        with pytest.raises(TargetLinkedError) as excinfo:
            target_service.delete_target_category(uow, admin.id, assembly.id, category.id)
        (block,) = excinfo.value.blocks
        # The confirmation separates what is unlinked from what is deleted
        assert block.field_labels == []
        assert block.deleted_labels == ["Region"]

        target_service.delete_target_category(uow, admin.id, assembly.id, category.id, force_unlink=True)

        assert uow.respondent_field_definitions.get(derived.id) is None
        assert respondent.attributes == {"postcode": "E1 6AN"}
        # The question it was computed from stays behind
        assert uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, "postcode") is not None

    def test_deleting_every_target_breaks_the_links_first(self, uow, admin, assembly):
        """One statement deletes them all, so nothing per-category gets a say unless it is asked first."""
        _gender, question = self._linked_category(uow, assembly)
        _region, derived, respondent = self._derived_category(uow, assembly)

        deleted = target_service.delete_targets_for_assembly(uow, admin.id, assembly.id)

        assert deleted == 2
        assert question.target_category_id is None
        assert uow.respondent_field_definitions.get(question.id) is not None
        assert uow.respondent_field_definitions.get(derived.id) is None
        assert respondent.attributes == {"postcode": "E1 6AN"}

    def test_a_csv_reimport_keeps_the_set_up_of_targets_that_come_back(self, uow, admin, assembly):
        _gender, question = self._linked_category(uow, assembly)
        _region, derived, respondent = self._derived_category(uow, assembly)
        csv_content = "feature,value,min,max\nGender,Male,2,6\nGender,Female,2,6\nRegion,North,1,5\nRegion,South,1,5"

        target_csv_import.import_targets_from_csv(uow, admin.id, assembly.id, csv_content, replace_existing=True)

        by_name = {c.name: c for c in uow.target_categories.get_by_assembly_id(assembly.id)}
        assert question.target_category_id == by_name["Gender"].id
        assert derived.target_category_id == by_name["Region"].id
        assert respondent.attributes == {"postcode": "E1 6AN", "Region": "North"}

    def test_a_csv_reimport_drops_the_set_up_of_targets_that_do_not(self, uow, admin, assembly):
        _gender, question = self._linked_category(uow, assembly)
        _region, derived, respondent = self._derived_category(uow, assembly)
        csv_content = "feature,value,min,max\nAge,18-30,1,5\nAge,31+,1,5"

        target_csv_import.import_targets_from_csv(uow, admin.id, assembly.id, csv_content, replace_existing=True)

        assert question.target_category_id is None
        assert uow.respondent_field_definitions.get(derived.id) is None
        assert respondent.attributes == {"postcode": "E1 6AN"}

    def test_a_csv_import_that_adds_to_the_targets_touches_no_links(self, uow, admin, assembly):
        gender, question = self._linked_category(uow, assembly)
        csv_content = "feature,value,min,max\nAge,18-30,1,5\nAge,31+,1,5"

        target_csv_import.import_targets_from_csv(uow, admin.id, assembly.id, csv_content, replace_existing=False)

        assert question.target_category_id == gender.id

    def test_a_bulk_rename_that_only_carries_computed_fields_asks_nothing(self, uow, admin, assembly):
        """Nothing is unlinked and nothing is lost, so there is nothing to confirm."""
        region, _derived, _respondent = self._derived_category(uow, assembly, "Region")
        gender, _field = self._linked_category(uow, assembly, "Gender")

        edits = [
            TargetCategoryEdit(category_id=region.id, name="Area"),
            TargetCategoryEdit(category_id=gender.id, name="Sex"),
        ]
        with pytest.raises(TargetLinkedError) as excinfo:
            target_service.save_all_targets(uow, admin.id, assembly.id, edits)

        assert [block.category_name for block in excinfo.value.blocks] == ["Gender"]

    def test_bulk_save_collects_every_blocked_category_at_once(self, uow, admin, assembly):
        gender, _f1 = self._linked_category(uow, assembly, "Gender")
        region, _f2 = self._linked_category(uow, assembly, "Region")

        edits = [
            TargetCategoryEdit(category_id=gender.id, name="Sex"),
            TargetCategoryEdit(category_id=region.id, name="Region", deleted=True),
        ]
        with pytest.raises(TargetLinkedError) as excinfo:
            target_service.save_all_targets(uow, admin.id, assembly.id, edits)

        actions = {block.category_name: block.action for block in excinfo.value.blocks}
        assert actions == {"Gender": LinkAction.RENAME, "Region": LinkAction.DELETE}
