"""ABOUTME: Names an assembly's selection runs by their place in its history
ABOUTME: Groups runs into eras started by a completed initial selection or a reset, and numbers replacement rounds"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType, selection_task_type_labels
from opendlp.translations import gettext as _

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from opendlp.domain.assembly import RunSummary

_INITIAL_TYPES = frozenset({SelectionTaskType.SELECT_GSHEET, SelectionTaskType.SELECT_FROM_DB})
_TEST_TYPES = frozenset({SelectionTaskType.TEST_SELECT_GSHEET, SelectionTaskType.TEST_SELECT_FROM_DB})
_REPLACEMENT_TYPES = frozenset({
    SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
    SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
})


@dataclass(frozen=True)
class HistoryNaming:
    """What the selection page needs to label an assembly's runs.

    ``names`` holds a name for every run, keyed by task id. ``current_era_start``
    is when the current era began, or None when nothing has started one yet;
    the page hides runs from before it unless asked for the whole history.
    """

    names: dict[uuid.UUID, str]
    current_era_start: datetime | None


def _starts_era(summary: RunSummary) -> bool:
    if summary.task_type == SelectionTaskType.RESET_TO_POOL:
        return True
    return summary.task_type in _INITIAL_TYPES | _TEST_TYPES and summary.status == SelectionRunStatus.COMPLETED


def _base_name(task_type: SelectionTaskType) -> str:
    if task_type in _INITIAL_TYPES:
        return _("Initial selection")
    if task_type in _TEST_TYPES:
        return _("Test selection")
    return _("Replacement selection")


def _name_run(summary: RunSummary, previous: bool, round_number: int | None) -> str:
    if summary.task_type not in _INITIAL_TYPES | _TEST_TYPES | _REPLACEMENT_TYPES:
        return str(selection_task_type_labels[summary.task_type])
    name = _base_name(summary.task_type)
    if summary.status == SelectionRunStatus.FAILED:
        return _("%(name)s (failed)", name=name)
    if summary.status == SelectionRunStatus.CANCELLED:
        return _("%(name)s (cancelled)", name=name)
    if summary.status != SelectionRunStatus.COMPLETED:
        return name
    if round_number is not None:
        if previous:
            return _("%(name)s (round %(round)s, previous)", name=name, round=round_number)
        return _("%(name)s (round %(round)s)", name=name, round=round_number)
    if previous:
        return _("%(name)s (previous)", name=name)
    return name


def name_history(summaries: list[RunSummary]) -> HistoryNaming:
    """Name every run of an assembly by its place in the history.

    A completed initial or test selection starts a new era, as does a reset.
    Within an era the completed replacement runs are numbered from one. Runs
    in an era that a later one has superseded are marked "previous". Failed
    and cancelled runs neither start eras nor take round numbers; they are
    named by their status instead. Pending and running runs carry the bare
    name until they finish. Runs that are not selections keep their task type
    label.
    """
    placed: list[tuple[RunSummary, int, int | None]] = []
    era = 0
    round_in_era = 0
    current_era_start: datetime | None = None
    for summary in sorted(summaries, key=lambda s: s.created_at):
        if _starts_era(summary):
            era += 1
            round_in_era = 0
            current_era_start = summary.created_at
        round_number: int | None = None
        if summary.task_type in _REPLACEMENT_TYPES and summary.status == SelectionRunStatus.COMPLETED:
            round_in_era += 1
            round_number = round_in_era
        placed.append((summary, era, round_number))

    names = {
        summary.task_id: _name_run(summary, previous=run_era < era, round_number=round_number)
        for summary, run_era, round_number in placed
    }
    return HistoryNaming(names=names, current_era_start=current_era_start)
