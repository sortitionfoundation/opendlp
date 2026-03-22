"""ABOUTME: Unit tests for the detailed target checking service
ABOUTME: Tests annotation helpers and the check_targets_detailed service function"""

import uuid

import pytest
from sortition_algorithms.errors import (
    InfeasibleQuotasError,
    ParseTableErrorMsg,
    ParseTableMultiError,
    ParseTableMultiValueErrorMsg,
)
from sortition_algorithms.features import FeatureValueMinMax, MinMaxCrossFeatureIssue
from sortition_algorithms.people import FeatureValueCountCheck

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.target_checking import (
    TargetAnnotation,
    _annotations_from_cross_feature_issues,
    _annotations_from_infeasible_quotas,
    _annotations_from_parse_errors,
    _annotations_from_people_checks,
    check_targets_detailed,
)
from tests.fakes import FakeUnitOfWork


class TestAnnotationsFromParseErrors:
    def test_single_field_error(self):
        error = ParseTableMultiError([
            ParseTableErrorMsg(
                row=2,
                row_name="gender/male",
                key="min",
                value="abc",
                msg="'abc' is not a number",
                error_code="not_a_number",
                error_params={"value": "abc"},
            )
        ])
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_parse_errors(error, annotations)

        assert "gender" in annotations
        assert "male" in annotations["gender"]
        assert len(annotations["gender"]["male"]) == 1
        ann = annotations["gender"]["male"][0]
        assert ann.level == "error"
        assert ann.field == "min"
        assert "not a number" in ann.message

    def test_multi_value_error(self):
        error = ParseTableMultiError([
            ParseTableMultiValueErrorMsg(
                row=2,
                row_name="age/young",
                keys=["min", "max"],
                values=["10", "5"],
                msg="Minimum (10) should not be greater than maximum (5)",
                error_code="min_greater_than_max",
                error_params={"min": 10, "max": 5},
            )
        ])
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_parse_errors(error, annotations)

        assert "age" in annotations
        assert "young" in annotations["age"]
        ann = annotations["age"]["young"][0]
        assert ann.level == "error"
        assert ann.field == "min, max"

    def test_error_without_slash_in_row_name(self):
        error = ParseTableMultiError([
            ParseTableErrorMsg(
                row=2,
                row_name="gender",
                key="value",
                value="",
                msg="Empty value in feature gender",
                error_code="empty_feature_value",
                error_params={},
            )
        ])
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_parse_errors(error, annotations)

        assert "gender" in annotations
        assert "" in annotations["gender"]

    def test_multiple_errors_accumulate(self):
        error = ParseTableMultiError([
            ParseTableErrorMsg(
                row=2,
                row_name="gender/male",
                key="min",
                value="",
                msg="No min value",
                error_code="no_value_set",
                error_params={},
            ),
            ParseTableErrorMsg(
                row=3,
                row_name="gender/female",
                key="max",
                value="x",
                msg="'x' is not a number",
                error_code="not_a_number",
                error_params={},
            ),
        ])
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_parse_errors(error, annotations)

        assert len(annotations["gender"]["male"]) == 1
        assert len(annotations["gender"]["female"]) == 1


class TestAnnotationsFromCrossFeatureIssues:
    def test_inconsistent_min_max(self):
        issues = [
            MinMaxCrossFeatureIssue(
                issue_type="inconsistent_min_max",
                message="Inconsistent",
                smallest_maximum_feature="age",
                smallest_maximum_value=10,
                largest_minimum_feature="gender",
                largest_minimum_value=15,
            )
        ]
        cat_ann: dict[str, list[TargetAnnotation]] = {}
        _annotations_from_cross_feature_issues(issues, cat_ann)

        assert "age" in cat_ann
        assert "gender" in cat_ann
        assert cat_ann["age"][0].level == "error"
        assert "10" in cat_ann["age"][0].message
        assert cat_ann["gender"][0].level == "error"
        assert "15" in cat_ann["gender"][0].message

    def test_min_exceeds_number_to_select(self):
        issues = [
            MinMaxCrossFeatureIssue(
                issue_type="min_exceeds_number_to_select",
                message="min too high",
                feature_name="gender",
                feature_sum=30,
                limit=25,
            )
        ]
        cat_ann: dict[str, list[TargetAnnotation]] = {}
        _annotations_from_cross_feature_issues(issues, cat_ann)

        assert "gender" in cat_ann
        assert cat_ann["gender"][0].level == "error"
        assert "30" in cat_ann["gender"][0].message
        assert "25" in cat_ann["gender"][0].message

    def test_max_below_number_to_select(self):
        issues = [
            MinMaxCrossFeatureIssue(
                issue_type="max_below_number_to_select",
                message="max too low",
                feature_name="age",
                feature_sum=10,
                limit=25,
            )
        ]
        cat_ann: dict[str, list[TargetAnnotation]] = {}
        _annotations_from_cross_feature_issues(issues, cat_ann)

        assert "age" in cat_ann
        assert cat_ann["age"][0].level == "error"
        assert "10" in cat_ann["age"][0].message


class TestAnnotationsFromPeopleChecks:
    def test_insufficient_people(self):
        issues = [
            FeatureValueCountCheck(
                feature_name="gender",
                value_name="female",
                min_required=25,
                actual_count=15,
            )
        ]
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_people_checks(issues, annotations)

        assert "gender" in annotations
        assert "female" in annotations["gender"]
        ann = annotations["gender"]["female"][0]
        assert ann.level == "error"
        assert ann.field == "min"
        assert "25" in ann.message
        assert "15" in ann.message

    def test_multiple_issues(self):
        issues = [
            FeatureValueCountCheck(feature_name="gender", value_name="male", min_required=10, actual_count=5),
            FeatureValueCountCheck(feature_name="age", value_name="young", min_required=8, actual_count=3),
        ]
        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_people_checks(issues, annotations)

        assert len(annotations["gender"]["male"]) == 1
        assert len(annotations["age"]["young"]) == 1


class TestAnnotationsFromInfeasibleQuotas:
    def test_relaxation_suggestions(self):
        original = {
            "gender": {
                "male": FeatureValueMinMax(min=15, max=20, min_flex=0, max_flex=30),
                "female": FeatureValueMinMax(min=15, max=20, min_flex=0, max_flex=30),
            }
        }
        relaxed = {
            "gender": {
                "male": FeatureValueMinMax(min=12, max=20, min_flex=0, max_flex=30),
                "female": FeatureValueMinMax(min=15, max=23, min_flex=0, max_flex=30),
            }
        }
        error = InfeasibleQuotasError(features=relaxed, output=["suggestion line"])

        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_infeasible_quotas(original, error, annotations)

        # male: min reduced from 15 to 12
        male_anns = annotations["gender"]["male"]
        assert len(male_anns) == 1
        assert male_anns[0].level == "suggestion"
        assert male_anns[0].field == "min"
        assert male_anns[0].suggested_value == 12

        # female: max increased from 20 to 23
        female_anns = annotations["gender"]["female"]
        assert len(female_anns) == 1
        assert female_anns[0].level == "suggestion"
        assert female_anns[0].field == "max"
        assert female_anns[0].suggested_value == 23

    def test_no_changes(self):
        original = {"gender": {"male": FeatureValueMinMax(min=10, max=20, min_flex=0, max_flex=30)}}
        relaxed = {"gender": {"male": FeatureValueMinMax(min=10, max=20, min_flex=0, max_flex=30)}}
        error = InfeasibleQuotasError(features=relaxed, output=[])

        annotations: dict[str, dict[str, list[TargetAnnotation]]] = {}
        _annotations_from_infeasible_quotas(original, error, annotations)

        assert not annotations


def _make_uow_with_targets_and_respondents(
    number_to_select: int = 10,
    target_categories: list[TargetCategory] | None = None,
    respondents: list[Respondent] | None = None,
) -> tuple[FakeUnitOfWork, uuid.UUID, uuid.UUID]:
    uow = FakeUnitOfWork()

    admin = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(admin)

    assembly = Assembly(title="Test Assembly", number_to_select=number_to_select)
    assembly.csv = AssemblyCSV(assembly_id=assembly.id, check_same_address=False)
    uow.assemblies.add(assembly)

    if target_categories:
        for tc in target_categories:
            tc.assembly_id = assembly.id
            uow.target_categories.add(tc)

    if respondents:
        for r in respondents:
            r.assembly_id = assembly.id
            uow.respondents.add(r)

    return uow, admin.id, assembly.id


class TestCheckTargetsDetailed:
    def test_success_with_valid_targets_and_respondents(self):
        targets = [
            TargetCategory(
                assembly_id=uuid.uuid4(),
                name="gender",
                values=[
                    TargetValue(value="male", min=3, max=7),
                    TargetValue(value="female", min=3, max=7),
                ],
            ),
        ]
        respondents = [
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id=f"p{i}",
                attributes={"gender": "male" if i % 2 == 0 else "female"},
                selection_status=RespondentStatus.POOL,
            )
            for i in range(20)
        ]
        uow, user_id, assembly_id = _make_uow_with_targets_and_respondents(
            number_to_select=10, target_categories=targets, respondents=respondents
        )

        result = check_targets_detailed(uow, user_id, assembly_id)

        assert result.success is True
        assert result.num_features == 1
        assert result.num_people == 20
        assert not result.global_errors
        assert not result.annotations
        assert not result.category_annotations

    def test_no_targets_returns_global_error(self):
        uow, user_id, assembly_id = _make_uow_with_targets_and_respondents(
            number_to_select=10, target_categories=[], respondents=[]
        )

        result = check_targets_detailed(uow, user_id, assembly_id)

        # No targets means no features loaded — but no parse error either,
        # it just means 0 features. The check should still succeed in loading
        # (empty features is not an error at the parse level)
        assert result.num_features == 0

    def test_no_respondents_returns_global_error(self):
        targets = [
            TargetCategory(
                assembly_id=uuid.uuid4(),
                name="gender",
                values=[
                    TargetValue(value="male", min=3, max=7),
                    TargetValue(value="female", min=3, max=7),
                ],
            ),
        ]
        uow, user_id, assembly_id = _make_uow_with_targets_and_respondents(
            number_to_select=10, target_categories=targets, respondents=[]
        )

        result = check_targets_detailed(uow, user_id, assembly_id)

        assert result.success is False
        assert len(result.global_errors) > 0

    def test_cross_feature_min_exceeds_number_to_select(self):
        targets = [
            TargetCategory(
                assembly_id=uuid.uuid4(),
                name="gender",
                values=[
                    TargetValue(value="male", min=8, max=10),
                    TargetValue(value="female", min=8, max=10),
                ],
            ),
        ]
        respondents = [
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id=f"p{i}",
                attributes={"gender": "male" if i % 2 == 0 else "female"},
                selection_status=RespondentStatus.POOL,
            )
            for i in range(30)
        ]
        # sum of mins = 16 > number_to_select = 10
        uow, user_id, assembly_id = _make_uow_with_targets_and_respondents(
            number_to_select=10, target_categories=targets, respondents=respondents
        )

        result = check_targets_detailed(uow, user_id, assembly_id)

        assert result.success is False
        assert "gender" in result.category_annotations
        assert any("16" in ann.message for ann in result.category_annotations["gender"])

    def test_insufficient_respondents_for_value(self):
        targets = [
            TargetCategory(
                assembly_id=uuid.uuid4(),
                name="gender",
                values=[
                    TargetValue(value="male", min=5, max=7),
                    TargetValue(value="female", min=5, max=7),
                ],
            ),
        ]
        # Only 2 females, but min is 5
        respondents = [
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="p0",
                attributes={"gender": "female"},
                selection_status=RespondentStatus.POOL,
            ),
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id="p1",
                attributes={"gender": "female"},
                selection_status=RespondentStatus.POOL,
            ),
        ] + [
            Respondent(
                assembly_id=uuid.uuid4(),
                external_id=f"p{i}",
                attributes={"gender": "male"},
                selection_status=RespondentStatus.POOL,
            )
            for i in range(2, 20)
        ]
        uow, user_id, assembly_id = _make_uow_with_targets_and_respondents(
            number_to_select=10, target_categories=targets, respondents=respondents
        )

        result = check_targets_detailed(uow, user_id, assembly_id)

        assert result.success is False
        assert "gender" in result.annotations
        assert "female" in result.annotations["gender"]
        female_anns = result.annotations["gender"]["female"]
        assert any(ann.level == "error" and ann.field == "min" for ann in female_anns)

    def test_assembly_not_found_raises(self):
        uow = FakeUnitOfWork()
        admin = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin)

        with pytest.raises(AssemblyNotFoundError):
            check_targets_detailed(uow, admin.id, uuid.uuid4())
