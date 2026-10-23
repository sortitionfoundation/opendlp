"""ABOUTME: Accepting the min/max changes the target check suggests when the targets are infeasible
ABOUTME: Re-derives the suggestions from a fresh check and writes them as manual overrides with a comment"""

import uuid

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.target_checking import DetailedCheckResult, TargetAnnotation, check_targets_detailed
from opendlp.service_layer.target_service import get_targets_for_assembly, update_target_value
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _


def _suggestion_change_phrase(field: str, current: int, suggested: int) -> str:
    """The "minimum X → Y" fragment shared by the single and combined comments."""
    if field == "min":
        return _("minimum %(current)s → %(suggested)s", current=current, suggested=suggested)
    return _("maximum %(current)s → %(suggested)s", current=current, suggested=suggested)


def _applicable_annotations(check: DetailedCheckResult, category_name: str, value_name: str) -> list[TargetAnnotation]:
    """The applicable min/max suggestions the check holds for one value."""
    return [
        annotation
        for annotation in check.annotations.get(category_name, {}).get(value_name, [])
        if annotation.is_applicable
    ]


def _apply_value_suggestions(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category: TargetCategory,
    value: TargetValue,
    annotations: list[TargetAnnotation],
    comment: str,
) -> None:
    """Apply every min/max suggestion for one value in a single update.

    Passing only the fields that change leaves the other bound alone; accepting
    a suggestion is a manual override, so this breaks the percentage link and
    records why in the comment.
    """
    min_count = next((a.suggested_value for a in annotations if a.field == "min"), None)
    max_count = next((a.suggested_value for a in annotations if a.field == "max"), None)
    assert value.value_id is not None
    update_target_value(
        uow,
        user_id,
        assembly_id,
        category.id,
        value.value_id,
        value.value,
        min_count=min_count,
        max_count=max_count,
        comment=comment,
    )


def accept_suggestion(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    field: str,
    comment: str = "",
) -> bool:
    """Apply the one suggestion for `field` ("min" or "max") on one value.

    The suggestion is re-derived from a fresh check rather than taken from the
    caller, so a stale page cannot apply a number the check no longer
    recommends. Returns False, changing nothing, when there is no such
    suggestion any more. An empty `comment` is replaced by one saying where the
    change came from.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    check = check_targets_detailed(uow, user_id, assembly_id)
    categories = get_targets_for_assembly(uow, user_id, assembly_id)
    category = next((c for c in categories if c.id == category_id), None)
    value = next((v for v in (category.values or []) if v.value_id == value_id), None) if category else None
    if category is None or value is None:
        return False

    annotations = [a for a in _applicable_annotations(check, category.name, value.value) if a.field == field]
    if not annotations:
        return False

    suggested = annotations[0].suggested_value
    assert suggested is not None
    current = value.min if field == "min" else value.max
    comment = comment.strip() or _(
        "Accepted algorithm suggestion — %(change)s",
        change=_suggestion_change_phrase(field, current, suggested),
    )
    _apply_value_suggestions(uow, user_id, assembly_id, category, value, annotations, comment)
    return True


def accept_all_suggestions(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
    """Apply every outstanding suggestion from a fresh check, each with a comment saying so.

    Returns False when the check has nothing to accept.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    check = check_targets_detailed(uow, user_id, assembly_id)
    categories = get_targets_for_assembly(uow, user_id, assembly_id)
    applied = False
    for category in categories:
        for value in category.values or []:
            annotations = _applicable_annotations(check, category.name, value.value)
            if not annotations:
                continue
            changes = ", ".join(
                _suggestion_change_phrase(
                    a.field or "", value.min if a.field == "min" else value.max, a.suggested_value or 0
                )
                for a in sorted(annotations, key=lambda a: a.field or "")
            )
            comment = _("Accepted algorithm suggestion — %(changes)s", changes=changes)
            _apply_value_suggestions(uow, user_id, assembly_id, category, value, annotations, comment)
            applied = True
    return applied
