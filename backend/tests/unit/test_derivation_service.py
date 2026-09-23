"""ABOUTME: Unit tests for the derivation service.
ABOUTME: Covers derived-field CRUD, dispatch, apply/recompute, mapping upload and source protection."""

import uuid
from datetime import date

import pytest

from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondent_derivation import AgeBracket, AgeBracketRule, LargeMappingRule, SmallMappingRule
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
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, SelectionRunStatus, SelectionTaskType
from opendlp.service_layer import derivation_service
from opendlp.service_layer.derivation_service import (
    UNMATCHED_SAMPLE_SIZE,
    apply_derivations,
    create_derived_field,
    derivations_depending_on,
    derived_value_for,
    load_mapping_lookups,
    recompute_derived_field,
    update_derivation,
    upload_large_mapping,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from opendlp.service_layer.respondent_field_schema_service import (
    add_choice_option,
    delete_field,
    remove_choice_option,
    update_choice_option,
    update_field,
)
from tests.fakes import FakeUnitOfWork

AS_OF = date(2026, 5, 13)
AGE_RULE = AgeBracketRule(
    as_of_date=AS_OF,
    brackets=(AgeBracket(16, "16-21"), AgeBracket(22, "22-29"), AgeBracket(30, "30-54"), AgeBracket(55, "55+")),
)


def _seed(uow: FakeUnitOfWork) -> tuple[User, Assembly]:
    user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Test Assembly", number_to_select=40)
    uow.assemblies.add(assembly)
    return user, assembly


def _add_source(
    uow: FakeUnitOfWork,
    assembly: Assembly,
    field_key: str = "date_of_birth",
    field_type: FieldType = FieldType.DATE,
    options: list[ChoiceOption] | None = None,
) -> RespondentFieldDefinition:
    source = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=field_key,
        label=field_key.replace("_", " ").capitalize(),
        group=RespondentFieldGroup.ABOUT_YOU,
        sort_order=10,
        field_type=field_type,
        options=options,
    )
    uow.respondent_field_definitions.add(source)
    return source


def _add_respondent(uow: FakeUnitOfWork, assembly: Assembly, external_id: str, attributes: dict) -> Respondent:
    respondent = Respondent(assembly_id=assembly.id, external_id=external_id, attributes=attributes)
    uow.respondents.add(respondent)
    return respondent


class TestCreateDerivedField:
    def test_creates_age_bracket_field_with_generated_options(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)

        field, report = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        assert field.is_derived is True
        assert field.derived_from == ["date_of_birth"]
        assert field.derivation_type == DerivationType.AGE_BRACKET
        assert field.derivation_config == AGE_RULE.to_config()
        assert field.group == RespondentFieldGroup.DERIVED
        assert field.field_type == FieldType.CHOICE_RADIO
        assert [o.value for o in field.options] == ["16-21", "22-29", "30-54", "55+", "UNKNOWN"]
        assert field.on_registration_page == FieldOnRegistrationPage.NO
        assert report.total == 0

    def test_recomputes_the_existing_pool(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)
        _add_respondent(uow, assembly, "R1", {"date_of_birth": "1990-06-15"})
        _add_respondent(uow, assembly, "R2", {"date_of_birth": "not a date"})

        _, report = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        r1 = uow.respondents.get_by_external_id(assembly.id, "R1")
        r2 = uow.respondents.get_by_external_id(assembly.id, "R2")
        assert r1.attributes["age_bracket"] == "30-54"
        assert r2.attributes["age_bracket"] == "UNKNOWN"
        assert report.total == 2
        assert report.changed == 2
        assert report.fell_back == 1
        assert "not a date" in report.unmatched_sample
        assert report.fallback == "UNKNOWN"

    def test_requires_manage_permission(self, uow):
        _, assembly = _seed(uow)
        outsider = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)
        _add_source(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            create_derived_field(
                uow,
                outsider.id,
                assembly.id,
                field_key="age_bracket",
                label="Age bracket",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    def test_unknown_user_is_rejected(self, uow):
        _user, assembly = _seed(uow)
        _add_source(uow, assembly)

        with pytest.raises(UserNotFoundError):
            create_derived_field(
                uow,
                uuid.uuid4(),
                assembly.id,
                field_key="age_bracket",
                label="Age bracket",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    def test_unknown_assembly_is_rejected(self, uow):
        user, _assembly = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            create_derived_field(
                uow,
                user.id,
                uuid.uuid4(),
                field_key="age_bracket",
                label="Age bracket",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_rejects_a_blank_field_key(self, uow, blank):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="cannot be empty"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key=blank,
                label="Age bracket",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    def test_rejects_missing_source_field(self, uow):
        user, assembly = _seed(uow)
        with pytest.raises(FieldDefinitionConflictError, match="does not exist"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key="age_bracket",
                label="Age bracket",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    def test_rejects_derived_source_field(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)
        create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        with pytest.raises(FieldDefinitionConflictError, match="itself derived"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key="age_bracket_2",
                label="Age bracket 2",
                source_field_key="age_bracket",
                rule=SmallMappingRule(mapping={"16-21": "young"}),
            )

    def test_rejects_incompatible_source_type(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly, field_key="postcode", field_type=FieldType.TEXT)

        with pytest.raises(FieldDefinitionConflictError, match="cannot derive from a Text field"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key="age_bracket",
                label="Age bracket",
                source_field_key="postcode",
                rule=AGE_RULE,
            )

    def test_accepts_integer_year_of_birth_source(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly, field_key="year_of_birth", field_type=FieldType.INTEGER)
        _add_respondent(uow, assembly, "R1", {"year_of_birth": "1990"})

        _, report = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="year_of_birth",
            rule=AGE_RULE,
        )

        r1 = uow.respondents.get_by_external_id(assembly.id, "R1")
        assert r1.attributes["age_bracket"] == "30-54"
        assert report.fell_back == 0

    def test_rejects_duplicate_field_key(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="already exists"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key="date_of_birth",
                label="Clash",
                source_field_key="date_of_birth",
                rule=AGE_RULE,
            )

    def test_large_mapping_requires_output_values(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly, field_key="postcode", field_type=FieldType.TEXT)

        with pytest.raises(FieldDefinitionConflictError, match="output values"):
            create_derived_field(
                uow,
                user.id,
                assembly.id,
                field_key="region",
                label="Region",
                source_field_key="postcode",
                rule=LargeMappingRule(),
            )

    def test_small_mapping_from_choice_source(self, uow):
        user, assembly = _seed(uow)
        _add_source(
            uow,
            assembly,
            field_key="ethnicity",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="White British"), ChoiceOption(value="White Irish")],
        )
        _add_respondent(uow, assembly, "R1", {"ethnicity": "White Irish"})

        field, report = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="ethnicity_group",
            label="Ethnicity group",
            source_field_key="ethnicity",
            rule=SmallMappingRule(mapping={"White British": "White", "White Irish": "White"}),
        )

        assert [o.value for o in field.options] == ["White", "UNKNOWN"]
        r1 = uow.respondents.get_by_external_id(assembly.id, "R1")
        assert r1.attributes["ethnicity_group"] == "White"
        assert report.changed == 1


class TestDerivedValueFor:
    def _derived(self, assembly_id, source_key, rule, derivation_type):
        return RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="derived",
            label="Derived",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=[source_key],
            derivation_type=derivation_type,
            derivation_config=rule.to_config(),
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="x"), ChoiceOption(value="UNKNOWN")],
        )

    def test_age_from_date_source(self):
        assembly_id = uuid.uuid4()
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="date_of_birth",
            label="DOB",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.DATE,
        )
        field = self._derived(assembly_id, "date_of_birth", AGE_RULE, DerivationType.AGE_BRACKET)
        assert derived_value_for(field, AGE_RULE, source, "1990-06-15") == "30-54"
        # Lenient UK-format parse for imported values.
        assert derived_value_for(field, AGE_RULE, source, "15/06/1990") == "30-54"
        assert derived_value_for(field, AGE_RULE, source, "garbage") == "UNKNOWN"

    def test_age_from_integer_source(self):
        assembly_id = uuid.uuid4()
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="year_of_birth",
            label="YOB",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.INTEGER,
        )
        field = self._derived(assembly_id, "year_of_birth", AGE_RULE, DerivationType.AGE_BRACKET)
        assert derived_value_for(field, AGE_RULE, source, "1990") == "30-54"
        assert derived_value_for(field, AGE_RULE, source, "ninety") == "UNKNOWN"

    def test_small_mapping_source(self):
        assembly_id = uuid.uuid4()
        rule = SmallMappingRule(mapping={"White Irish": "White"})
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="ethnicity",
            label="Ethnicity",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="White Irish")],
        )
        field = self._derived(assembly_id, "ethnicity", rule, DerivationType.SMALL_MAPPING)
        assert derived_value_for(field, rule, source, "  White Irish  ") == "White"
        assert derived_value_for(field, rule, source, "Asian") == "UNKNOWN"
        assert derived_value_for(field, rule, source, None) == "UNKNOWN"

    def test_large_mapping_requires_a_lookup(self):
        assembly_id = uuid.uuid4()
        rule = LargeMappingRule()
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="postcode",
            label="Postcode",
            group=RespondentFieldGroup.ADDRESS,
            sort_order=10,
        )
        field = self._derived(assembly_id, "postcode", rule, DerivationType.LARGE_MAPPING)
        with pytest.raises(ValueError, match="lookup"):
            derived_value_for(field, rule, source, "SW1A 1AA")
        assert derived_value_for(field, rule, source, "SW1A 1AA", lookup={"SW1A1AA": "London"}.get) == "London"


class TestApplyDerivations:
    def _schema_and_field(self, assembly_id):
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="date_of_birth",
            label="DOB",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.DATE,
        )
        derived = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config=AGE_RULE.to_config(),
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="30-54"), ChoiceOption(value="UNKNOWN")],
        )
        return [source, derived]

    def test_derivation_overwrites_a_supplied_value(self):
        assembly_id = uuid.uuid4()
        schema = self._schema_and_field(assembly_id)
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id="R1",
            attributes={"date_of_birth": "1990-06-15", "age_bracket": "hand-typed"},
        )

        outcome = apply_derivations(respondent, schema, {})

        assert respondent.attributes["age_bracket"] == "30-54"
        assert "age_bracket" in outcome.overwrote_supplied

    def test_supplied_value_kept_when_source_cannot_derive(self):
        assembly_id = uuid.uuid4()
        schema = self._schema_and_field(assembly_id)
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id="R1",
            attributes={"age_bracket": "22-29"},
        )

        outcome = apply_derivations(respondent, schema, {})

        assert respondent.attributes["age_bracket"] == "22-29"
        assert "age_bracket" in outcome.kept_supplied

    def test_fallback_when_no_source_and_no_supplied_value(self):
        assembly_id = uuid.uuid4()
        schema = self._schema_and_field(assembly_id)
        respondent = Respondent(assembly_id=assembly_id, external_id="R1", attributes={})

        apply_derivations(respondent, schema, {})

        assert respondent.attributes["age_bracket"] == "UNKNOWN"

    def test_source_absent_from_the_schema_falls_back(self):
        """A derived_from naming a field this schema does not carry cannot derive.

        It must not raise: the write paths hand in whatever schema they loaded.
        """
        assembly_id = uuid.uuid4()
        _source, derived = self._schema_and_field(assembly_id)
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id="R1",
            attributes={"date_of_birth": "1990-06-15"},
        )

        outcome = apply_derivations(respondent, [derived], {})

        assert respondent.attributes["age_bracket"] == "UNKNOWN"
        assert outcome.derived["age_bracket"] == "UNKNOWN"
        # There is no source value to report as unmatched - the source is missing,
        # not unreadable.
        assert outcome.fallback_sources == {}

    def test_source_absent_from_the_schema_keeps_a_supplied_value(self):
        assembly_id = uuid.uuid4()
        _source, derived = self._schema_and_field(assembly_id)
        respondent = Respondent(assembly_id=assembly_id, external_id="R1", attributes={"age_bracket": "22-29"})

        outcome = apply_derivations(respondent, [derived], {})

        assert respondent.attributes["age_bracket"] == "22-29"
        assert outcome.kept_supplied == ["age_bracket"]

    def test_config_the_rule_rejects_is_skipped_not_raised(self):
        assembly_id = uuid.uuid4()
        source = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="ethnicity",
            label="Ethnicity",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="White British")],
        )
        derived = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="ethnicity_group",
            label="Ethnicity group",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["ethnicity"],
            derivation_type=DerivationType.SMALL_MAPPING,
            derivation_config={"mapping": {}, "fallback": "UNKNOWN"},
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="UNKNOWN")],
        )
        respondent = Respondent(assembly_id=assembly_id, external_id="R1", attributes={"ethnicity": "White British"})

        outcome = apply_derivations(respondent, [source, derived], {})

        assert outcome.derived == {}
        assert "ethnicity_group" not in respondent.attributes

    def test_recompute_mode_overwrites_even_on_fallback(self):
        assembly_id = uuid.uuid4()
        schema = self._schema_and_field(assembly_id)
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id="R1",
            attributes={"age_bracket": "22-29"},
        )

        apply_derivations(respondent, schema, {}, keep_supplied_on_fallback=False)

        assert respondent.attributes["age_bracket"] == "UNKNOWN"


class TestRecomputeDerivedField:
    def _create(self, uow, user, assembly):
        _add_source(uow, assembly)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )
        return field

    def test_is_idempotent_for_age_brackets(self, uow):
        user, assembly = _seed(uow)
        _add_respondent(uow, assembly, "R1", {"date_of_birth": "1990-06-15"})
        field = self._create(uow, user, assembly)

        report = recompute_derived_field(uow, user.id, assembly.id, field.id)

        assert report.total == 1
        assert report.changed == 0

    def test_skips_deleted_respondents(self, uow):
        user, assembly = _seed(uow)
        r1 = _add_respondent(uow, assembly, "R1", {"date_of_birth": "1990-06-15"})
        r1.delete_personal_data(author_id=user.id, comment="erasure request")
        field = self._create(uow, user, assembly)

        report = recompute_derived_field(uow, user.id, assembly.id, field.id)

        assert report.total == 0
        assert "age_bracket" not in r1.attributes

    def test_counts_completed_selection_runs(self, uow):
        user, assembly = _seed(uow)
        field = self._create(uow, user, assembly)
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.COMPLETED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
            )
        )
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly.id,
                task_id=uuid.uuid4(),
                status=SelectionRunStatus.FAILED,
                task_type=SelectionTaskType.SELECT_FROM_DB,
            )
        )

        report = recompute_derived_field(uow, user.id, assembly.id, field.id)

        assert report.completed_selection_runs == 1

    def test_unknown_field_id_is_not_found(self, uow):
        user, assembly = _seed(uow)

        with pytest.raises(FieldDefinitionNotFoundError):
            recompute_derived_field(uow, user.id, assembly.id, uuid.uuid4())

    def test_a_field_belonging_to_another_assembly_is_not_found(self, uow):
        user, assembly = _seed(uow)
        field = self._create(uow, user, assembly)
        other = Assembly(title="Other Assembly", number_to_select=20)
        uow.assemblies.add(other)

        with pytest.raises(FieldDefinitionNotFoundError):
            recompute_derived_field(uow, user.id, other.id, field.id)

    def test_unmatched_sample_is_deduplicated_and_capped(self, uow):
        user, assembly = _seed(uow)
        # More distinct unreadable values than the sample holds, each seen twice.
        for i in range(UNMATCHED_SAMPLE_SIZE + 5):
            _add_respondent(uow, assembly, f"A{i}", {"date_of_birth": f"rubbish-{i}"})
            _add_respondent(uow, assembly, f"B{i}", {"date_of_birth": f"rubbish-{i}"})
        field = self._create(uow, user, assembly)

        report = recompute_derived_field(uow, user.id, assembly.id, field.id)

        assert report.fell_back == 2 * (UNMATCHED_SAMPLE_SIZE + 5)
        assert len(report.unmatched_sample) == UNMATCHED_SAMPLE_SIZE
        assert len(set(report.unmatched_sample)) == UNMATCHED_SAMPLE_SIZE

    def test_rejects_non_derived_field(self, uow):
        user, assembly = _seed(uow)
        source = _add_source(uow, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="not a derived field"):
            recompute_derived_field(uow, user.id, assembly.id, source.id)


class TestUpdateDerivation:
    def test_replaces_config_and_regenerates_options(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)
        _add_respondent(uow, assembly, "R1", {"date_of_birth": "1990-06-15"})
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        new_rule = AgeBracketRule(as_of_date=AS_OF, brackets=(AgeBracket(18, "18-39"), AgeBracket(40, "40+")))
        updated, report = update_derivation(uow, user.id, assembly.id, field.id, rule=new_rule)

        assert updated.derivation_config == new_rule.to_config()
        assert [o.value for o in updated.options] == ["18-39", "40+", "UNKNOWN"]
        r1 = uow.respondents.get_by_external_id(assembly.id, "R1")
        assert r1.attributes["age_bracket"] == "18-39"
        assert report.changed == 1

    def test_a_source_that_no_longer_fits_the_rule_is_refused(self, uow):
        """The source is re-validated on every rule edit, not just at creation.

        ``update_field`` refuses to retype a source field, so the state is built
        here by writing the source directly - what a hand-edited row would leave.
        """
        user, assembly = _seed(uow)
        source = _add_source(uow, assembly)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )
        source.field_type = FieldType.TEXT

        with pytest.raises(FieldDefinitionConflictError, match="cannot derive from a Text field"):
            update_derivation(uow, user.id, assembly.id, field.id, rule=AGE_RULE)

    def test_large_mapping_fallback_change_keeps_outputs_and_swaps_fallback(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly, field_key="postcode", field_type=FieldType.TEXT)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="region",
            label="Region",
            source_field_key="postcode",
            rule=LargeMappingRule(),
            output_values=["London", "North"],
        )

        updated, _ = update_derivation(uow, user.id, assembly.id, field.id, rule=LargeMappingRule(fallback="Unknown"))

        assert [o.value for o in updated.options] == ["London", "North", "Unknown"]
        assert updated.derivation_config == {"fallback": "Unknown"}


class TestDerivationsDependingOn:
    def test_finds_dependents_by_source_key(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)
        _add_source(uow, assembly, field_key="postcode", field_type=FieldType.TEXT)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        dependents = derivations_depending_on(uow, assembly.id, "date_of_birth")
        assert [f.id for f in dependents] == [field.id]
        assert derivations_depending_on(uow, assembly.id, "postcode") == []


class TestUploadLargeMapping:
    def _region_field(self, uow, user, assembly):
        _add_source(uow, assembly, field_key="postcode", field_type=FieldType.TEXT)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="region",
            label="Region",
            source_field_key="postcode",
            rule=LargeMappingRule(),
            output_values=["London", "North"],
        )
        return field

    def test_uploads_with_matching_headers(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nSW1A 1AA,London\nm1 1ae,North\n",
        )

        assert report.row_count == 2
        assert report.used_positional_headers is False
        entries = uow.respondent_field_mapping_entries.list_for_field(field.id)
        assert {(e.lookup_key, e.output_value) for e in entries} == {("SW1A1AA", "London"), ("M11AE", "North")}

    def test_falls_back_to_positional_headers(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="pc,area\nSW1A 1AA,London\n",
        )

        assert report.row_count == 1
        assert report.used_positional_headers is True

    def test_reports_duplicate_keys(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nSW1A 1AA,London\nsw1a1aa,North\n",
        )

        assert report.row_count == 1
        assert "SW1A1AA" in report.duplicate_keys

    def test_rejects_unknown_outputs_by_default(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="Scotland"):
            upload_large_mapping(
                uow,
                user.id,
                assembly.id,
                field.id,
                csv_content="postcode,region\nEH1 1YZ,Scotland\n",
            )

    def test_allow_new_outputs_extends_the_options(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nEH1 1YZ,Scotland\n",
            allow_new_outputs=True,
        )

        assert report.unknown_outputs == {"Scotland": 1}
        stored = uow.respondent_field_definitions.get(field.id)
        assert "Scotland" in [o.value for o in stored.options]

    def test_replaces_the_previous_table(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        uow.respondent_field_mapping_entries.add(
            RespondentFieldMappingEntry(field_id=field.id, lookup_key="OLD1", output_value="London")
        )

        upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nSW1A 1AA,London\n",
        )

        entries = uow.respondent_field_mapping_entries.list_for_field(field.id)
        assert [e.lookup_key for e in entries] == ["SW1A1AA"]

    def test_rejects_a_field_that_is_not_a_large_mapping(self, uow):
        user, assembly = _seed(uow)
        _add_source(uow, assembly)
        field, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )

        with pytest.raises(FieldDefinitionConflictError, match="does not use a large mapping"):
            upload_large_mapping(uow, user.id, assembly.id, field.id, csv_content="postcode,region\nSW1A 1AA,London\n")

    @pytest.mark.parametrize("content", ["", "\n\n", "  \n , \n"])
    def test_rejects_an_empty_file(self, uow, content):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="empty"):
            upload_large_mapping(uow, user.id, assembly.id, field.id, csv_content=content)

    def test_rejects_a_single_column_file(self, uow):
        """One header matches, but positional fallback needs two columns to fall back to."""
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        with pytest.raises(FieldDefinitionConflictError, match="two columns"):
            upload_large_mapping(uow, user.id, assembly.id, field.id, csv_content="postcode\nSW1A 1AA\n")

    def test_skips_rows_too_short_to_carry_both_columns(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nSW1A 1AA,London\nM1 1AE\n",
        )

        assert report.row_count == 1
        entries = uow.respondent_field_mapping_entries.list_for_field(field.id)
        assert [e.lookup_key for e in entries] == ["SW1A1AA"]

    def test_skips_rows_with_a_blank_key_or_value(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\n  ,London\nM1 1AE,   \nSW1A 1AA,London\n",
        )

        assert report.row_count == 1
        entries = uow.respondent_field_mapping_entries.list_for_field(field.id)
        assert [e.lookup_key for e in entries] == ["SW1A1AA"]

    def test_duplicate_keys_are_capped_at_the_sample_size(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        repeated = "".join(f"K{i},London\nK{i},North\n" for i in range(UNMATCHED_SAMPLE_SIZE + 5))

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content=f"postcode,region\n{repeated}",
        )

        assert report.row_count == UNMATCHED_SAMPLE_SIZE + 5
        assert len(report.duplicate_keys) == UNMATCHED_SAMPLE_SIZE
        assert report.duplicate_keys == sorted(report.duplicate_keys)

    def test_enforces_the_row_cap(self, uow, monkeypatch):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        monkeypatch.setattr(derivation_service, "MAX_MAPPING_ROWS", 2)

        with pytest.raises(FieldDefinitionConflictError, match="too many rows"):
            upload_large_mapping(
                uow,
                user.id,
                assembly.id,
                field.id,
                csv_content="postcode,region\nA1 1AA,London\nB2 2BB,London\nC3 3CC,North\n",
            )

    def test_accepts_a_file_exactly_at_the_row_cap(self, uow, monkeypatch):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        monkeypatch.setattr(derivation_service, "MAX_MAPPING_ROWS", 2)

        report = upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nA1 1AA,London\nB2 2BB,North\n",
        )

        assert report.row_count == 2

    def test_stops_parsing_once_the_row_cap_is_exceeded(self, uow, monkeypatch):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        monkeypatch.setattr(derivation_service, "MAX_MAPPING_ROWS", 2)
        # A field beyond csv's own limit: reaching it would raise csv.Error, so
        # only a FieldDefinitionConflictError proves parsing stopped at the cap.
        oversized_row = "X" * 200_000 + ",London\n"

        with pytest.raises(FieldDefinitionConflictError, match="too many rows"):
            upload_large_mapping(
                uow,
                user.id,
                assembly.id,
                field.id,
                csv_content="postcode,region\nA1 1AA,London\nB2 2BB,London\nC3 3CC,North\n" + oversized_row,
            )

    def test_lookups_serve_derivation(self, uow):
        user, assembly = _seed(uow)
        field = self._region_field(uow, user, assembly)
        upload_large_mapping(
            uow,
            user.id,
            assembly.id,
            field.id,
            csv_content="postcode,region\nSW1A 1AA,London\n",
        )

        stored = uow.respondent_field_definitions.get(field.id)
        lookups = load_mapping_lookups(uow, [stored])
        assert lookups[field.id]("SW1A1AA") == "London"
        assert lookups[field.id]("ZZ99ZZ") is None


class TestSourceFieldProtection:
    def _age_setup(self, uow):
        user, assembly = _seed(uow)
        source = _add_source(uow, assembly)
        derived, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )
        return user, assembly, source, derived

    def test_delete_field_on_a_source_is_blocked(self, uow):
        user, assembly, source, _ = self._age_setup(uow)
        with pytest.raises(FieldDefinitionConflictError, match="age_bracket"):
            delete_field(uow, user.id, assembly.id, source.id)

    def test_delete_field_on_the_derived_field_itself_is_allowed(self, uow):
        user, assembly, _, derived = self._age_setup(uow)
        delete_field(uow, user.id, assembly.id, derived.id)
        assert uow.respondent_field_definitions.get(derived.id) is None

    def test_changing_a_source_fields_type_is_blocked(self, uow):
        user, assembly, source, _ = self._age_setup(uow)
        with pytest.raises(FieldDefinitionConflictError, match="age_bracket"):
            update_field(uow, user.id, assembly.id, source.id, field_type=FieldType.TEXT)

    def test_relabeling_a_source_field_is_still_allowed(self, uow):
        user, assembly, source, _ = self._age_setup(uow)
        updated = update_field(uow, user.id, assembly.id, source.id, label="Birth date")
        assert updated.label == "Birth date"

    def test_relabeling_a_source_field_while_passing_its_unchanged_type_is_allowed(self, uow):
        # The edit modal always posts the field's type, even when only the label changed.
        user, assembly, source, _ = self._age_setup(uow)
        updated = update_field(uow, user.id, assembly.id, source.id, label="Birth date", field_type=FieldType.DATE)
        assert updated.label == "Birth date"
        assert updated.field_type == FieldType.DATE

    def test_changing_a_derived_fields_own_type_is_blocked(self, uow):
        user, assembly, _, derived = self._age_setup(uow)
        with pytest.raises(FieldDefinitionConflictError, match="derived"):
            update_field(uow, user.id, assembly.id, derived.id, field_type=FieldType.TEXT)

    def test_moving_a_derived_field_out_of_the_derived_section_is_blocked(self, uow):
        """The registration questions editor hides the Derived section, so a field moved out would appear there."""
        user, assembly, _, derived = self._age_setup(uow)
        with pytest.raises(FieldDefinitionConflictError, match="Derived section"):
            update_field(uow, user.id, assembly.id, derived.id, group=RespondentFieldGroup.ABOUT_YOU)
        assert uow.respondent_field_definitions.get(derived.id).group == RespondentFieldGroup.DERIVED

    def test_a_derived_field_can_be_relabelled_in_place(self, uow):
        user, assembly, _, derived = self._age_setup(uow)
        updated = update_field(
            uow, user.id, assembly.id, derived.id, label="Age range", group=RespondentFieldGroup.DERIVED
        )
        assert updated.label == "Age range"

    def _small_mapping_setup(self, uow):
        user, assembly = _seed(uow)
        source = _add_source(
            uow,
            assembly,
            field_key="ethnicity",
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="White British"), ChoiceOption(value="White Irish")],
        )
        derived, _ = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="ethnicity_group",
            label="Ethnicity group",
            source_field_key="ethnicity",
            rule=SmallMappingRule(mapping={"White British": "White", "White Irish": "White"}),
        )
        return user, assembly, source, derived

    def test_renaming_a_source_option_renames_the_mapping_key_in_step(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        update_choice_option(uow, user.id, assembly.id, source.id, "White British", "White (British)")

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White (British)": "White", "White Irish": "White"}

    def test_removing_a_source_option_drops_the_mapping_entry(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        remove_choice_option(uow, user.id, assembly.id, source.id, "White Irish")

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White British": "White"}

    def test_replacing_source_options_wholesale_drops_stale_mapping_keys(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        update_field(
            uow,
            user.id,
            assembly.id,
            source.id,
            options=[ChoiceOption(value="White British"), ChoiceOption(value="Asian")],
        )

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White British": "White"}

    def test_a_wholesale_replace_that_says_what_was_renamed_carries_the_mapping_key(self, uow):
        """The question dialog submits the whole list; without the hint a rename reads as remove + add."""
        user, assembly, source, derived = self._small_mapping_setup(uow)

        update_field(
            uow,
            user.id,
            assembly.id,
            source.id,
            options=[ChoiceOption(value="White (British)"), ChoiceOption(value="White Irish")],
            option_renames={"White British": "White (British)"},
        )

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White (British)": "White", "White Irish": "White"}

    def test_renaming_every_mapped_option_at_once_is_not_mistaken_for_emptying_the_mapping(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        update_field(
            uow,
            user.id,
            assembly.id,
            source.id,
            options=[ChoiceOption(value="British"), ChoiceOption(value="Irish")],
            option_renames={"White British": "British", "White Irish": "Irish"},
        )

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"British": "White", "Irish": "White"}

    @pytest.mark.parametrize(
        "renames",
        [
            {"Never an option": "Asian"},  # the old value is not one of the field's options
            {"White Irish": "Not submitted"},  # the new value is not in the new list
            {"White British": "Asian"},  # the old value is still in the list, so nothing was renamed
        ],
    )
    def test_a_rename_hint_that_describes_no_real_rename_is_ignored(self, uow, renames):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        update_field(
            uow,
            user.id,
            assembly.id,
            source.id,
            options=[ChoiceOption(value="White British"), ChoiceOption(value="Asian")],
            option_renames=renames,
        )

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White British": "White"}

    def test_replacing_source_options_that_empties_a_mapping_is_refused(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)

        with pytest.raises(FieldDefinitionConflictError, match="ethnicity_group"):
            update_field(uow, user.id, assembly.id, source.id, options=[ChoiceOption(value="Asian")])

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White British": "White", "White Irish": "White"}
        assert [o.value for o in uow.respondent_field_definitions.get(source.id).options] == [
            "White British",
            "White Irish",
        ]

    def test_removing_the_last_mapped_source_option_is_refused(self, uow):
        user, assembly, source, derived = self._small_mapping_setup(uow)
        remove_choice_option(uow, user.id, assembly.id, source.id, "White Irish")
        add_choice_option(uow, user.id, assembly.id, source.id, "Asian")

        with pytest.raises(FieldDefinitionConflictError, match="ethnicity_group"):
            remove_choice_option(uow, user.id, assembly.id, source.id, "White British")

        stored = uow.respondent_field_definitions.get(derived.id)
        assert stored.derivation_config["mapping"] == {"White British": "White"}
        assert [o.value for o in uow.respondent_field_definitions.get(source.id).options] == ["White British", "Asian"]


class TestCompatibleSourceFields:
    def _fields(self, uow):
        _user, assembly = _seed(uow)
        dob = _add_source(uow, assembly, "date_of_birth", FieldType.DATE)
        yob = _add_source(uow, assembly, "year_of_birth", FieldType.INTEGER)
        postcode = _add_source(uow, assembly, "postcode", FieldType.TEXT)
        gender = _add_source(uow, assembly, "gender", FieldType.CHOICE_RADIO, options=[ChoiceOption(value="Female")])
        return [dob, yob, postcode, gender]

    def test_age_bracket_accepts_date_and_integer_sources(self, uow):
        """Age brackets derive from a date of birth or a year of birth."""
        fields = self._fields(uow)
        keys = [f.field_key for f in derivation_service.compatible_source_fields(fields, DerivationType.AGE_BRACKET)]
        assert keys == ["date_of_birth", "year_of_birth"]

    def test_small_mapping_accepts_choice_sources(self, uow):
        fields = self._fields(uow)
        keys = [f.field_key for f in derivation_service.compatible_source_fields(fields, DerivationType.SMALL_MAPPING)]
        assert keys == ["gender"]

    def test_large_mapping_accepts_text_sources(self, uow):
        fields = self._fields(uow)
        keys = [f.field_key for f in derivation_service.compatible_source_fields(fields, DerivationType.LARGE_MAPPING)]
        assert keys == ["postcode"]

    def test_derived_fields_are_never_offered_as_sources(self, uow):
        """Derivations cannot chain, so a derived field is excluded even with a compatible type."""
        user, assembly = _seed(uow)
        _add_source(uow, assembly, "date_of_birth", FieldType.DATE)
        derived, _report = create_derived_field(
            uow,
            user.id,
            assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            source_field_key="date_of_birth",
            rule=AGE_RULE,
        )
        fields = uow.respondent_field_definitions.list_by_assembly(assembly.id)
        compatible = derivation_service.compatible_source_fields(fields, DerivationType.SMALL_MAPPING)
        assert derived.id not in [f.id for f in compatible]

    def test_fixed_fields_use_their_effective_type(self, uow):
        """The email fixed field is TEXT in storage but EMAIL effectively, so no rule accepts it."""
        _user, assembly = _seed(uow)
        email = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="email",
            label="Email",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=0,
            is_fixed=True,
            field_type=FieldType.TEXT,
        )
        uow.respondent_field_definitions.add(email)
        assert derivation_service.compatible_source_fields([email], DerivationType.LARGE_MAPPING) == []
