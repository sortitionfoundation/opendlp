"""ABOUTME: Unit tests for the target source service.
ABOUTME: Covers configure (four methods x create/reuse), status classification, adopt, resync and unlink."""

import uuid
from datetime import date

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_derivation import AgeBracketRule, LargeMappingRule, SmallMappingRule
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import (
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    InsufficientPermissions,
    NotFoundError,
)
from opendlp.service_layer.target_source_service import (
    AgeBracketSpec,
    ExactCopySpec,
    LargeMappingSpec,
    SmallMappingSpec,
    SourceFieldSpec,
    TargetSourceState,
    adopt_field,
    configure_target_source,
    resync_from_target,
    target_source_status,
    unlink,
)
from tests.fakes import FakeUnitOfWork

AGE_RULE = AgeBracketRule(as_of_date=date(2026, 5, 13), min_age=16, max_age=100, boundaries=(30, 55))


@pytest.fixture
def uow():
    with FakeUnitOfWork() as entered:
        yield entered


def _seed(uow: FakeUnitOfWork) -> tuple[User, Assembly]:
    user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Test Assembly", number_to_select=40)
    uow.assemblies.add(assembly)
    return user, assembly


def _add_category(uow: FakeUnitOfWork, assembly: Assembly, name: str, values: list[str]) -> TargetCategory:
    category = TargetCategory(
        assembly_id=assembly.id,
        name=name,
        values=[TargetValue(value=value, min=1, max=5) for value in values],
    )
    uow.target_categories.add(category)
    return category


def _add_field(uow: FakeUnitOfWork, assembly: Assembly, field_key: str, **kwargs) -> RespondentFieldDefinition:
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=field_key,
        label=kwargs.pop("label", field_key.replace("_", " ").capitalize()),
        group=kwargs.pop("group", RespondentFieldGroup.ABOUT_YOU),
        sort_order=kwargs.pop("sort_order", 10),
        **kwargs,
    )
    uow.respondent_field_definitions.add(field)
    return field


def _linked_field(uow: FakeUnitOfWork, assembly: Assembly, category: TargetCategory) -> RespondentFieldDefinition:
    return next(
        f for f in uow.respondent_field_definitions.list_by_assembly(assembly.id) if f.target_category_id == category.id
    )


class TestConfigureExactCopy:
    def test_creates_a_linked_choice_field_mirroring_the_target(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female", "Other"])

        fields, report = configure_target_source(uow, user.id, assembly.id, category.id, ExactCopySpec())

        assert report is None
        (field,) = fields
        assert field.field_key == "Gender"
        assert field.field_type == FieldType.CHOICE_RADIO
        assert [o.value for o in field.options] == ["Male", "Female", "Other"]
        assert field.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED
        assert field.target_category_id == category.id
        assert field.is_derived is False

    def test_many_values_get_a_dropdown(self, uow):
        user, assembly = _seed(uow)
        values = [f"Region {i}" for i in range(9)]
        category = _add_category(uow, assembly, "Region", values)

        fields, _report = configure_target_source(uow, user.id, assembly.id, category.id, ExactCopySpec())

        assert fields[0].field_type == FieldType.CHOICE_DROPDOWN

    def test_create_refuses_an_occupied_field_key(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        _add_field(uow, assembly, "Gender")

        with pytest.raises(FieldDefinitionConflictError, match="already exists"):
            configure_target_source(uow, user.id, assembly.id, category.id, ExactCopySpec())

    def test_reuse_links_a_compatible_existing_field(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        existing = _add_field(
            uow,
            assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        fields, report = configure_target_source(
            uow, user.id, assembly.id, category.id, ExactCopySpec(source=SourceFieldSpec(reuse_field_id=existing.id))
        )

        assert report is None
        assert fields[0].id == existing.id
        assert existing.target_category_id == category.id

    def test_reuse_refuses_a_field_missing_target_values(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female", "Other"])
        existing = _add_field(
            uow,
            assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        with pytest.raises(FieldDefinitionConflictError, match="Other"):
            configure_target_source(
                uow,
                user.id,
                assembly.id,
                category.id,
                ExactCopySpec(source=SourceFieldSpec(reuse_field_id=existing.id)),
            )

    def test_reuse_refuses_a_non_choice_field(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        existing = _add_field(uow, assembly, "gender", field_type=FieldType.TEXT)

        with pytest.raises(FieldDefinitionConflictError, match="not a choice field"):
            configure_target_source(
                uow,
                user.id,
                assembly.id,
                category.id,
                ExactCopySpec(source=SourceFieldSpec(reuse_field_id=existing.id)),
            )

    def test_relinking_clears_the_previous_field(self, uow):
        """A category feeds from one field at a time; pointing it elsewhere unlinks the old one."""
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        old = _add_field(
            uow,
            assembly,
            "old_gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )
        replacement = _add_field(
            uow,
            assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        configure_target_source(
            uow, user.id, assembly.id, category.id, ExactCopySpec(source=SourceFieldSpec(reuse_field_id=replacement.id))
        )

        assert old.target_category_id is None
        assert replacement.target_category_id == category.id

    def test_refuses_a_category_with_no_values(self, uow):
        user, assembly = _seed(uow)
        category = TargetCategory(assembly_id=assembly.id, name="Gender")
        uow.target_categories.add(category)

        with pytest.raises(FieldDefinitionConflictError, match="no values"):
            configure_target_source(uow, user.id, assembly.id, category.id, ExactCopySpec())


class TestConfigureAgeBracket:
    def test_creates_source_and_linked_derived_field(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(
            uow, assembly, "Age bracket", ["under-16", "16-29", "30-54", "55-99", "100+", "UNKNOWN"]
        )

        fields, report = configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            AgeBracketSpec(rule=AGE_RULE, source=SourceFieldSpec(field_key="date_of_birth", field_type=FieldType.DATE)),
        )

        assert report is not None
        source, derived = fields
        assert source.field_key == "date_of_birth"
        assert source.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED
        assert source.target_category_id is None
        assert derived.field_key == "Age bracket"
        assert derived.is_derived is True
        assert derived.group == RespondentFieldGroup.DERIVED
        assert derived.on_registration_page == FieldOnRegistrationPage.NO
        assert derived.target_category_id == category.id
        assert "16-29" in [o.value for o in derived.options]

    def test_reuses_an_existing_date_source(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age bracket", ["16-29", "30-99"])
        existing = _add_field(uow, assembly, "date_of_birth", field_type=FieldType.DATE)

        fields, _report = configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            AgeBracketSpec(rule=AGE_RULE, source=SourceFieldSpec(reuse_field_id=existing.id)),
        )

        assert fields[0].id == existing.id

    def test_refuses_an_incompatible_source_type(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age bracket", ["16-29", "30-99"])
        existing = _add_field(uow, assembly, "notes", field_type=FieldType.LONGTEXT)

        with pytest.raises(FieldDefinitionConflictError, match="cannot feed"):
            configure_target_source(
                uow,
                user.id,
                assembly.id,
                category.id,
                AgeBracketSpec(rule=AGE_RULE, source=SourceFieldSpec(reuse_field_id=existing.id)),
            )

    def test_reconfiguring_updates_the_existing_derived_field(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age bracket", ["16-29", "30-99"])
        spec = AgeBracketSpec(
            rule=AGE_RULE, source=SourceFieldSpec(field_key="date_of_birth", field_type=FieldType.DATE)
        )
        configure_target_source(uow, user.id, assembly.id, category.id, spec)

        new_rule = AgeBracketRule(as_of_date=date(2027, 1, 1), min_age=18, max_age=90, boundaries=(40,))
        source = uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, "date_of_birth")
        fields, report = configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            AgeBracketSpec(rule=new_rule, source=SourceFieldSpec(reuse_field_id=source.id)),
        )

        assert report is not None
        derived = fields[-1]
        assert derived.derivation_config["min_age"] == 18
        assert len([f for f in uow.respondent_field_definitions.list_by_assembly(assembly.id) if f.is_derived]) == 1

    def test_a_plain_field_occupying_the_target_name_is_refused(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age bracket", ["16-29", "30-99"])
        _add_field(uow, assembly, "Age bracket", field_type=FieldType.TEXT)

        with pytest.raises(FieldDefinitionConflictError, match="not derived"):
            configure_target_source(
                uow,
                user.id,
                assembly.id,
                category.id,
                AgeBracketSpec(
                    rule=AGE_RULE, source=SourceFieldSpec(field_key="date_of_birth", field_type=FieldType.DATE)
                ),
            )


class TestConfigureSmallMapping:
    def test_creates_choice_source_and_derived_field_and_recomputes(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age group", ["Younger", "Older"])
        respondent = Respondent(assembly_id=assembly.id, external_id="r1", attributes={"age_band": "16-29"})
        uow.respondents.add(respondent)

        rule = SmallMappingRule(mapping={"16-29": "Younger", "30-99": "Older"})
        fields, report = configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            SmallMappingSpec(
                rule=rule,
                source=SourceFieldSpec(
                    field_key="age_band",
                    field_type=FieldType.CHOICE_RADIO,
                    options=(ChoiceOption(value="16-29"), ChoiceOption(value="30-99")),
                ),
            ),
        )

        source, derived = fields
        assert source.field_key == "age_band"
        assert [o.value for o in derived.options] == ["Younger", "Older", "UNKNOWN"]
        assert derived.target_category_id == category.id
        assert report.total == 1
        assert respondent.attributes["Age group"] == "Younger"


class TestConfigureLargeMapping:
    def test_creates_text_source_and_derived_field_with_target_outputs(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Region", ["North", "South"])

        fields, report = configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            LargeMappingSpec(rule=LargeMappingRule(), source=SourceFieldSpec(field_key="Postcode")),
        )

        source, derived = fields
        assert source.field_key == "Postcode"
        assert source.field_type == FieldType.TEXT
        assert [o.value for o in derived.options] == ["North", "South", "UNKNOWN"]
        assert derived.derivation_type == DerivationType.LARGE_MAPPING
        assert report is not None

    def test_one_source_can_feed_two_targets(self, uow):
        """The postcode case: one collected field, two derived fields, two links."""
        user, assembly = _seed(uow)
        region = _add_category(uow, assembly, "Region", ["North", "South"])
        urbanicity = _add_category(uow, assembly, "Urbanicity", ["Urban", "Rural"])

        configure_target_source(
            uow,
            user.id,
            assembly.id,
            region.id,
            LargeMappingSpec(rule=LargeMappingRule(), source=SourceFieldSpec(field_key="Postcode")),
        )
        postcode = uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, "Postcode")
        configure_target_source(
            uow,
            user.id,
            assembly.id,
            urbanicity.id,
            LargeMappingSpec(rule=LargeMappingRule(), source=SourceFieldSpec(reuse_field_id=postcode.id)),
        )

        assert _linked_field(uow, assembly, region).field_key == "Region"
        assert _linked_field(uow, assembly, urbanicity).field_key == "Urbanicity"
        fields = uow.respondent_field_definitions.list_by_assembly(assembly.id)
        assert len([f for f in fields if f.field_key == "Postcode"]) == 1


class TestTargetSourceStatus:
    def test_classifies_all_five_states(self, uow):
        user, assembly = _seed(uow)
        linked_cat = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        _add_field(
            uow,
            assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=linked_cat.id,
        )
        derived_cat = _add_category(uow, assembly, "Region", ["North", "South"])
        _add_field(uow, assembly, "postcode", group=RespondentFieldGroup.ADDRESS)
        derived = _add_field(
            uow,
            assembly,
            "Region",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["postcode"],
            derivation_type=DerivationType.LARGE_MAPPING,
            derivation_config={"fallback": "UNKNOWN"},
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="North"), ChoiceOption(value="South"), ChoiceOption(value="UNKNOWN")],
            target_category_id=derived_cat.id,
        )
        uow.respondent_field_mapping_entries.bulk_add([
            RespondentFieldMappingEntry(field_id=derived.id, lookup_key="AB1", output_value="North")
        ])
        _add_category(uow, assembly, "Education", ["School", "Degree"])
        _add_field(
            uow,
            assembly,
            "education",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="School"), ChoiceOption(value="Degree")],
        )
        _add_category(uow, assembly, "Ethnicity", ["A", "B"])
        respondent = Respondent(assembly_id=assembly.id, external_id="r1", attributes={"ethnicity": "A"})
        uow.respondents.add(respondent)
        _add_category(uow, assembly, "Income", ["Low", "High"])

        statuses = {status.category.name: status for status in target_source_status(uow, user.id, assembly.id)}

        assert statuses["Gender"].state == TargetSourceState.LINKED_EXACT
        assert statuses["Gender"].stale is False
        assert statuses["Region"].state == TargetSourceState.LINKED_DERIVED
        assert statuses["Region"].source_field.field_key == "postcode"
        assert statuses["Region"].mapping_row_count == 1
        assert statuses["Region"].stale is False
        assert statuses["Education"].state == TargetSourceState.MATCHED_NOT_LINKED
        assert statuses["Education"].field.field_key == "education"
        assert statuses["Ethnicity"].state == TargetSourceState.IMPORT_COVERED
        assert statuses["Income"].state == TargetSourceState.NONE

    def test_an_exact_field_goes_stale_when_the_target_values_change(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        _add_field(
            uow,
            assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )

        category.add_value(TargetValue(value="Other", min=0, max=5))

        (status,) = target_source_status(uow, user.id, assembly.id)
        assert status.stale is True

    def test_a_derived_field_ignores_its_fallback_when_checking_staleness(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Region", ["North", "South"])
        _add_field(uow, assembly, "postcode", group=RespondentFieldGroup.ADDRESS)
        _add_field(
            uow,
            assembly,
            "Region",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["postcode"],
            derivation_type=DerivationType.LARGE_MAPPING,
            derivation_config={"fallback": "UNKNOWN"},
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="North"), ChoiceOption(value="South"), ChoiceOption(value="UNKNOWN")],
            target_category_id=category.id,
        )

        statuses = target_source_status(uow, user.id, assembly.id)
        assert statuses[0].stale is False

        category.add_value(TargetValue(value="East", min=0, max=5))
        statuses = target_source_status(uow, user.id, assembly.id)
        assert statuses[0].stale is True


class TestAdoptField:
    def test_links_a_name_matched_field_case_insensitively(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        field = _add_field(
            uow,
            assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        adopted = adopt_field(uow, user.id, assembly.id, category.id, field.id)

        assert adopted.target_category_id == category.id
        assert field.target_category_id == category.id

    def test_refuses_a_field_with_a_different_name(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        field = _add_field(
            uow,
            assembly,
            "sex",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        with pytest.raises(FieldDefinitionConflictError, match="name"):
            adopt_field(uow, user.id, assembly.id, category.id, field.id)

    def test_refuses_a_choice_field_missing_target_values(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female", "Other"])
        field = _add_field(
            uow,
            assembly,
            "gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
        )

        with pytest.raises(FieldDefinitionConflictError, match="Other"):
            adopt_field(uow, user.id, assembly.id, category.id, field.id)


class TestResyncFromTarget:
    def test_exact_copy_options_follow_the_target_preserving_help_text(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        field = _add_field(
            uow,
            assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female", help_text="Includes trans women")],
            target_category_id=category.id,
        )
        category.add_value(TargetValue(value="Other", min=0, max=5))

        resynced, report = resync_from_target(uow, user.id, assembly.id, category.id)

        assert report is None
        assert [o.value for o in resynced.options] == ["Male", "Female", "Other"]
        assert resynced.options[1].help_text == "Includes trans women"
        assert [o.value for o in field.options] == ["Male", "Female", "Other"]

    def test_mapping_outputs_follow_the_target_and_recompute(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age group", ["Younger", "Older"])
        _add_field(
            uow,
            assembly,
            "age_band",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="16-29"), ChoiceOption(value="30-99")],
        )
        rule = SmallMappingRule(mapping={"16-29": "Younger", "30-99": "Older"})
        derived = _add_field(
            uow,
            assembly,
            "Age group",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["age_band"],
            derivation_type=DerivationType.SMALL_MAPPING,
            derivation_config=rule.to_config(),
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Younger"), ChoiceOption(value="Older"), ChoiceOption(value="UNKNOWN")],
            target_category_id=category.id,
        )
        category.add_value(TargetValue(value="Middle", min=0, max=5))

        resynced, report = resync_from_target(uow, user.id, assembly.id, category.id)

        assert report is not None
        assert [o.value for o in resynced.options] == ["Younger", "Older", "Middle", "UNKNOWN"]
        assert derived.target_category_id == category.id

    def test_age_brackets_are_refused(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Age bracket", ["16-29", "30-99"])
        _add_field(uow, assembly, "date_of_birth", field_type=FieldType.DATE)
        _add_field(
            uow,
            assembly,
            "Age bracket",
            group=RespondentFieldGroup.DERIVED,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config=AGE_RULE.to_config(),
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="16-29"), ChoiceOption(value="UNKNOWN")],
            target_category_id=category.id,
        )

        with pytest.raises(FieldDefinitionConflictError, match="Age brackets"):
            resync_from_target(uow, user.id, assembly.id, category.id)

    def test_a_category_with_no_linked_field_is_refused(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])

        with pytest.raises(FieldDefinitionNotFoundError):
            resync_from_target(uow, user.id, assembly.id, category.id)


class TestUnlink:
    def test_clears_the_link_and_keeps_the_field(self, uow):
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])
        field = _add_field(
            uow,
            assembly,
            "Gender",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Male"), ChoiceOption(value="Female")],
            target_category_id=category.id,
        )

        unlinked, deleted = unlink(uow, user.id, assembly.id, category.id)

        assert [f.field_key for f in unlinked] == ["Gender"]
        assert deleted == []
        assert field.target_category_id is None
        assert uow.respondent_field_definitions.get(field.id) is not None

    def test_a_derived_field_is_deleted_with_its_values_and_lookup_table(self, uow):
        """Nothing lists a derived field, so one left behind could never be reached again."""
        user, assembly = _seed(uow)
        category = _add_category(uow, assembly, "Region", ["North", "South"])
        respondent = Respondent(assembly_id=assembly.id, external_id="r1", attributes={"Postcode": "E1 6AN"})
        uow.respondents.add(respondent)
        configure_target_source(
            uow,
            user.id,
            assembly.id,
            category.id,
            LargeMappingSpec(
                rule=LargeMappingRule(fallback="UNKNOWN"),
                source=SourceFieldSpec(field_key="Postcode", field_type=FieldType.TEXT),
            ),
        )
        derived = _linked_field(uow, assembly, category)
        uow.respondent_field_mapping_entries.bulk_add([
            RespondentFieldMappingEntry(field_id=derived.id, lookup_key="E1 6AN", output_value="North")
        ])

        unlinked, deleted = unlink(uow, user.id, assembly.id, category.id)

        assert [f.field_key for f in deleted] == ["Region"]
        assert unlinked == []
        assert uow.respondent_field_definitions.get(derived.id) is None
        assert uow.respondent_field_mapping_entries.count_for_field(derived.id) == 0
        # The values it wrote go too - otherwise they keep exporting as a column nothing explains
        assert "Region" not in respondent.attributes
        # The question it was computed from is untouched
        assert uow.respondent_field_definitions.get_by_assembly_and_key(assembly.id, "Postcode") is not None
        assert respondent.attributes["Postcode"] == "E1 6AN"

    def test_unknown_category_raises(self, uow):
        user, assembly = _seed(uow)

        with pytest.raises(NotFoundError):
            unlink(uow, user.id, assembly.id, uuid.uuid4())


class TestPermissions:
    def test_configure_requires_manage_permission(self, uow):
        _admin, assembly = _seed(uow)
        outsider = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)
        category = _add_category(uow, assembly, "Gender", ["Male", "Female"])

        with pytest.raises(InsufficientPermissions):
            configure_target_source(uow, outsider.id, assembly.id, category.id, ExactCopySpec())

    def test_status_requires_view_permission(self, uow):
        _admin, assembly = _seed(uow)
        outsider = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            target_source_status(uow, outsider.id, assembly.id)
