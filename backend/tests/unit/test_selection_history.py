"""ABOUTME: Unit tests for naming an assembly's selection runs by their place in its history
ABOUTME: Covers era boundaries, replacement round numbering, failed runs and the current era start"""

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.assembly import RunSummary
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.service_layer.selection_history import name_history

_BASE = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _run(
    task_type: SelectionTaskType,
    status: SelectionRunStatus = SelectionRunStatus.COMPLETED,
    hours: int = 0,
) -> RunSummary:
    return RunSummary(
        task_id=uuid.uuid4(),
        task_type=task_type,
        status=status,
        created_at=_BASE + timedelta(hours=hours),
    )


def _names(*runs: RunSummary) -> list[str]:
    """The names of ``runs`` in the order given, however the summaries were passed in."""
    naming = name_history(list(reversed(runs)))
    return [naming.names[run.task_id] for run in runs]


class TestInitialSelections:
    def test_single_initial_selection(self):
        """One completed full selection is just the initial selection."""
        assert _names(_run(SelectionTaskType.SELECT_FROM_DB)) == ["Initial selection"]

    def test_test_selection_has_its_own_name(self):
        assert _names(_run(SelectionTaskType.TEST_SELECT_FROM_DB)) == ["Test selection"]

    def test_older_initial_selection_is_marked_previous(self):
        """A later completed initial selection supersedes the earlier one."""
        first = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        second = _run(SelectionTaskType.SELECT_FROM_DB, hours=1)
        assert _names(first, second) == ["Initial selection (previous)", "Initial selection"]

    def test_test_selection_then_full_selection(self):
        """A completed test selection is an era of its own, superseded by the real run."""
        test = _run(SelectionTaskType.TEST_SELECT_FROM_DB, hours=0)
        real = _run(SelectionTaskType.SELECT_FROM_DB, hours=1)
        assert _names(test, real) == ["Test selection (previous)", "Initial selection"]

    def test_pending_and_running_runs_carry_the_bare_name(self):
        pending = _run(SelectionTaskType.SELECT_FROM_DB, status=SelectionRunStatus.PENDING, hours=0)
        running = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, status=SelectionRunStatus.RUNNING, hours=1)
        assert _names(pending, running) == ["Initial selection", "Replacement selection"]


class TestReplacementRounds:
    def test_replacement_rounds_are_numbered_from_one(self):
        initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        first = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=1)
        second = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=2)
        assert _names(initial, first, second) == [
            "Initial selection",
            "Replacement selection (round 1)",
            "Replacement selection (round 2)",
        ]

    def test_rounds_restart_with_a_new_initial_selection(self):
        """Replacement rounds in a superseded era keep their number and gain the suffix."""
        old_initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        old_round = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=1)
        new_initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=2)
        new_round = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=3)
        assert _names(old_initial, old_round, new_initial, new_round) == [
            "Initial selection (previous)",
            "Replacement selection (round 1, previous)",
            "Initial selection",
            "Replacement selection (round 1)",
        ]

    def test_replacements_before_any_initial_selection_still_count(self):
        """History pruning can leave replacement runs with no initial run on record."""
        first = _run(SelectionTaskType.SELECT_REPLACEMENT_GSHEET, hours=0)
        second = _run(SelectionTaskType.SELECT_REPLACEMENT_GSHEET, hours=1)
        assert _names(first, second) == ["Replacement selection (round 1)", "Replacement selection (round 2)"]


class TestFailedAndCancelledRuns:
    def test_failed_runs_are_named_by_status_and_take_no_round(self):
        """A failed replacement neither consumes a round number nor leaves a gap."""
        initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        failed = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, status=SelectionRunStatus.FAILED, hours=1)
        completed = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=2)
        assert _names(initial, failed, completed) == [
            "Initial selection",
            "Replacement selection (failed)",
            "Replacement selection (round 1)",
        ]

    def test_cancelled_initial_selection_does_not_start_an_era(self):
        """The completed run stays current when a later attempt was cancelled."""
        initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        cancelled = _run(SelectionTaskType.SELECT_FROM_DB, status=SelectionRunStatus.CANCELLED, hours=1)
        naming = name_history([initial, cancelled])
        assert naming.names[initial.task_id] == "Initial selection"
        assert naming.names[cancelled.task_id] == "Initial selection (cancelled)"
        assert naming.current_era_start == initial.created_at

    def test_failed_runs_in_an_older_era_are_not_marked_previous(self):
        """The status is the more useful word, so it is the only suffix a failed run gets."""
        failed = _run(SelectionTaskType.SELECT_FROM_DB, status=SelectionRunStatus.FAILED, hours=0)
        initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=1)
        later = _run(SelectionTaskType.SELECT_FROM_DB, hours=2)
        assert _names(failed, initial, later) == [
            "Initial selection (failed)",
            "Initial selection (previous)",
            "Initial selection",
        ]


class TestGoogleSheetsRuns:
    def test_google_sheets_selections_follow_the_same_rules(self):
        test = _run(SelectionTaskType.TEST_SELECT_GSHEET, hours=0)
        initial = _run(SelectionTaskType.SELECT_GSHEET, hours=1)
        replacement = _run(SelectionTaskType.SELECT_REPLACEMENT_GSHEET, hours=2)
        assert _names(test, initial, replacement) == [
            "Test selection (previous)",
            "Initial selection",
            "Replacement selection (round 1)",
        ]

    def test_other_task_types_keep_their_labels(self):
        """Loads and tab housekeeping are not selections, so they are neither renamed nor numbered."""
        load = _run(SelectionTaskType.LOAD_GSHEET, hours=0)
        initial = _run(SelectionTaskType.SELECT_GSHEET, hours=1)
        load_replacement = _run(SelectionTaskType.LOAD_REPLACEMENT_GSHEET, hours=2)
        tabs = _run(SelectionTaskType.LIST_OLD_TABS, hours=3)
        assert _names(load, initial, load_replacement, tabs) == [
            "Load from Google Sheets",
            "Initial selection",
            "Load replacement data from Google Sheets",
            "List old tabs",
        ]


class TestResets:
    def test_reset_between_eras(self):
        """A reset keeps its label and ends the era before it."""
        old_initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        old_round = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=1)
        reset = _run(SelectionTaskType.RESET_TO_POOL, hours=2)
        new_initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=3)
        new_round = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=4)
        assert _names(old_initial, old_round, reset, new_initial, new_round) == [
            "Initial selection (previous)",
            "Replacement selection (round 1, previous)",
            "Reset all to pool",
            "Initial selection",
            "Replacement selection (round 1)",
        ]

    def test_reset_after_the_last_selection_starts_the_current_era(self):
        """After a reset with no new selection yet, the current era is just the reset."""
        initial = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        reset = _run(SelectionTaskType.RESET_TO_POOL, hours=1)
        naming = name_history([initial, reset])
        assert naming.names[initial.task_id] == "Initial selection (previous)"
        assert naming.names[reset.task_id] == "Reset all to pool"
        assert naming.current_era_start == reset.created_at


class TestCurrentEraStart:
    def test_no_runs(self):
        naming = name_history([])
        assert naming.names == {}
        assert naming.current_era_start is None

    def test_no_completed_selection_means_no_era(self):
        """Loads and failed attempts alone leave the whole history current."""
        load = _run(SelectionTaskType.LOAD_GSHEET, hours=0)
        failed = _run(SelectionTaskType.SELECT_GSHEET, status=SelectionRunStatus.FAILED, hours=1)
        naming = name_history([load, failed])
        assert naming.current_era_start is None

    def test_current_era_starts_at_the_latest_completed_selection(self):
        first = _run(SelectionTaskType.SELECT_FROM_DB, hours=0)
        second = _run(SelectionTaskType.SELECT_FROM_DB, hours=1)
        replacement = _run(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB, hours=2)
        naming = name_history([replacement, first, second])
        assert naming.current_era_start == second.created_at
