"""ABOUTME: Detailed target validation service for inline feedback on the targets page.
ABOUTME: Runs structured checks and maps errors to specific categories/values for UI annotation."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog
from sortition_algorithms import adapters
from sortition_algorithms.committee_generation.common import setup_committee_generation
from sortition_algorithms.errors import (
    InfeasibleQuotasError,
    ParseTableMultiError,
    ParseTableMultiValueErrorMsg,
    SortitionBaseError,
)
from sortition_algorithms.features import (
    FeatureCollection,
    iterate_feature_collection,
    report_min_max_against_number_to_select_structured,
    report_min_max_error_details_structured,
)
from sortition_algorithms.people import (
    FeatureValueCountCheck,
    check_people_per_feature_value,
)

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

if TYPE_CHECKING:
    from sortition_algorithms.people import People
    from sortition_algorithms.settings import Settings
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)


@dataclass
class TargetAnnotation:
    level: str  # "error", "warning", "suggestion"
    message: str
    field: str | None = None  # "min", "max", or None for whole-value
    suggested_value: int | None = None


# annotations[category_name][value_name] -> list of annotations
AnnotationsDict = dict[str, dict[str, list[TargetAnnotation]]]
# category_annotations[category_name] -> list of annotations
CategoryAnnotationsDict = dict[str, list[TargetAnnotation]]


@dataclass
class DetailedCheckResult:
    success: bool
    global_errors: list[str]
    annotations: AnnotationsDict = field(default_factory=dict)
    category_annotations: CategoryAnnotationsDict = field(default_factory=dict)
    num_features: int = 0
    num_people: int = 0


def _add_annotation(annotations: AnnotationsDict, category: str, value: str, annotation: TargetAnnotation) -> None:
    if category not in annotations:
        annotations[category] = defaultdict(list)
    annotations[category][value].append(annotation)


def _add_category_annotation(
    category_annotations: CategoryAnnotationsDict, category: str, annotation: TargetAnnotation
) -> None:
    if category not in category_annotations:
        category_annotations[category] = []
    category_annotations[category].append(annotation)


def _annotations_from_parse_errors(
    error: ParseTableMultiError,
    annotations: AnnotationsDict,
) -> None:
    for sub_error in error.all_errors:
        row_name = sub_error.row_name
        if "/" in row_name:
            category, value = row_name.split("/", 1)
        else:
            category = row_name
            value = ""

        if isinstance(sub_error, ParseTableMultiValueErrorMsg):
            field_name = ", ".join(sub_error.keys) if sub_error.keys else None
        else:
            field_name = sub_error.key if sub_error.key else None

        _add_annotation(
            annotations,
            category,
            value,
            TargetAnnotation(level="error", message=sub_error.msg, field=field_name),
        )


def _annotations_from_cross_feature_issues(
    issues: list,
    category_annotations: CategoryAnnotationsDict,
) -> None:
    for issue in issues:
        if issue.issue_type == "inconsistent_min_max":
            _add_category_annotation(
                category_annotations,
                issue.smallest_maximum_feature,
                TargetAnnotation(
                    level="error",
                    message=_(
                        "Sum of max values (%(value)s) is the smallest across all categories — "
                        "conflicts with category '%(other)s'",
                        value=issue.smallest_maximum_value,
                        other=issue.largest_minimum_feature,
                    ),
                ),
            )
            _add_category_annotation(
                category_annotations,
                issue.largest_minimum_feature,
                TargetAnnotation(
                    level="error",
                    message=_(
                        "Sum of min values (%(value)s) is the largest across all categories — "
                        "conflicts with category '%(other)s'",
                        value=issue.largest_minimum_value,
                        other=issue.smallest_maximum_feature,
                    ),
                ),
            )
        elif issue.issue_type == "min_exceeds_number_to_select":
            _add_category_annotation(
                category_annotations,
                issue.feature_name,
                TargetAnnotation(
                    level="error",
                    message=_(
                        "Sum of minimums (%(sum)s) exceeds number to select (%(limit)s)",
                        sum=issue.feature_sum,
                        limit=issue.limit,
                    ),
                ),
            )
        elif issue.issue_type == "max_below_number_to_select":
            _add_category_annotation(
                category_annotations,
                issue.feature_name,
                TargetAnnotation(
                    level="error",
                    message=_(
                        "Sum of maximums (%(sum)s) is less than number to select (%(limit)s)",
                        sum=issue.feature_sum,
                        limit=issue.limit,
                    ),
                ),
            )


def _annotations_from_people_checks(
    issues: list[FeatureValueCountCheck],
    annotations: AnnotationsDict,
) -> None:
    for issue in issues:
        _add_annotation(
            annotations,
            issue.feature_name,
            issue.value_name,
            TargetAnnotation(
                level="error",
                field="min",
                message=_(
                    "Need minimum %(min)s but only %(count)s respondents match",
                    min=issue.min_required,
                    count=issue.actual_count,
                ),
            ),
        )


def _annotations_from_infeasible_quotas(
    original_features: FeatureCollection,
    error: InfeasibleQuotasError,
    annotations: AnnotationsDict,
) -> None:
    relaxed = error.features
    for feature_name, value_name, original_fv in iterate_feature_collection(original_features):
        if feature_name not in relaxed or value_name not in relaxed[feature_name]:
            continue
        relaxed_fv = relaxed[feature_name][value_name]
        if relaxed_fv.min < original_fv.min:
            _add_annotation(
                annotations,
                feature_name,
                value_name,
                TargetAnnotation(
                    level="suggestion",
                    field="min",
                    message=_(
                        "Suggested minimum: %(value)s (currently %(current)s)",
                        value=relaxed_fv.min,
                        current=original_fv.min,
                    ),
                    suggested_value=relaxed_fv.min,
                ),
            )
        if relaxed_fv.max > original_fv.max:
            _add_annotation(
                annotations,
                feature_name,
                value_name,
                TargetAnnotation(
                    level="suggestion",
                    field="max",
                    message=_(
                        "Suggested maximum: %(value)s (currently %(current)s)",
                        value=relaxed_fv.max,
                        current=original_fv.max,
                    ),
                    suggested_value=relaxed_fv.max,
                ),
            )


def _run_feasibility_check(
    features: FeatureCollection,
    people: "People",
    number_to_select: int,
    settings_obj: "Settings",
    result: DetailedCheckResult,
) -> None:
    try:
        setup_committee_generation(
            features=features,
            people=people,
            number_people_wanted=number_to_select,
            check_same_address_columns=settings_obj.check_same_address_columns
            if settings_obj.check_same_address
            else [],
            solver_backend=settings_obj.solver_backend,
        )
    except InfeasibleQuotasError as e:
        result.success = False
        _annotations_from_infeasible_quotas(features, e, result.annotations)
    except SortitionBaseError as e:
        result.success = False
        result.global_errors.append(str(e))


@require_assembly_permission(can_manage_assembly)
def check_targets_detailed(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> DetailedCheckResult:
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    number_to_select = assembly.number_to_select
    csv_config = assembly.csv if assembly.csv is not None else AssemblyCSV(assembly_id=assembly_id)

    result = DetailedCheckResult(success=True, global_errors=[])

    try:
        settings_obj = csv_config.to_settings()
    except SortitionBaseError as e:
        result.success = False
        result.global_errors.append(str(e))
        return result

    data_source = OpenDLPDataAdapter(uow, assembly_id)
    select_data = adapters.SelectionData(data_source)

    # Load features without number_to_select check so we always get the FeatureCollection
    # back (check_min_max won't raise). We run the structured checks ourselves below.
    try:
        features, _f_report = select_data.load_features(number_to_select=0)
    except ParseTableMultiError as e:
        result.success = False
        _annotations_from_parse_errors(e, result.annotations)
        return result
    except SortitionBaseError as e:
        result.success = False
        result.global_errors.append(str(e))
        return result

    result.num_features = len(features)

    # Run structured cross-feature checks
    cross_issues = report_min_max_error_details_structured(features)
    if number_to_select:
        cross_issues += report_min_max_against_number_to_select_structured(features, number_to_select)
    if cross_issues:
        result.success = False
        _annotations_from_cross_feature_issues(cross_issues, result.category_annotations)

    # Load people
    try:
        people, _p_report = select_data.load_people(settings_obj, features)
    except SortitionBaseError as e:
        result.success = False
        result.global_errors.append(str(e))
        return result

    result.num_people = people.count

    # Check enough people per feature value
    people_issues = check_people_per_feature_value(features, people)
    if people_issues:
        result.success = False
        _annotations_from_people_checks(people_issues, result.annotations)

    # Feasibility check (only if number_to_select is set)
    if number_to_select > 0:
        _run_feasibility_check(features, people, number_to_select, settings_obj, result)

    return result
