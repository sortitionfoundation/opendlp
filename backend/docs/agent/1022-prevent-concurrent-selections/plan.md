# Prevent concurrent writing tasks on one assembly — plan

**Status:** Implemented (2026-10-09). Every step in §7 is committed on the
branch; the checklist there says which commit. Decisions are marked
**D1**…**D12**, and §8 records the answers from review.
**Date:** 2026-10-08, revised 2026-10-09
**Branch:** `1022-prevent-concurrent-selections` (off `main`)
**Story:** 1022 — only one task that writes to an assembly may run at a time

## 0. The rule

Two background tasks that write to the same assembly must never run at the
same time. "Write" means changing respondent rows in the database or writing
to the assembly's spreadsheet. Tasks on different assemblies run freely.
Tasks that only read (check spreadsheet, list old tabs) are never blocked and
never block.

The same rule covers the one synchronous bulk write, "reset to pool": it must
not run while a selection is unfinished (§3.5).

Today the only protection is the templates hiding buttons, plus one check in
`start_db_replace_task`. That check is narrower than it looks (§1.3). A second
browser tab, a double-click that beats the redirect, or a direct POST starts a
second run. For a database assembly that writes a second panel on top of the
first; for a Google Sheets assembly it writes a second set of output tabs,
possibly while the first run is still reading.

## 1. What exists

### 1.1 Does Celery have this built in?

No. Celery 5.6 has no per-key mutual exclusion. Its own docs ("Ensuring a task
is only executed one at a time", in the task cookbook) tell you to take a
cache lock with a timeout around the body, which is what
`auto_export_respondents` already does with a redis-py lock
(`entrypoints/celery/tasks.py`, `service_layer/respondent_auto_export.py`).
Third-party packages (`celery-singleton`, `celery-once`) implement the same
Redis lock, keyed on task name plus arguments. They do not fit: our key is
"any writing task on this assembly", not "this task with these arguments",
and both are small, thinly maintained libraries we would otherwise not need.
So this is ours to build, and the lock lives in Postgres (§2).

### 1.2 Every task, and what it writes

| Celery task | Run record task type | Writes | Guard? |
|---|---|---|---|
| `load_gsheet` | `LOAD_GSHEET`, `LOAD_REPLACEMENT_GSHEET` | nothing (it calls `require_writable()`, but that is a read-side check) | no |
| `run_select` | `SELECT_GSHEET`, `TEST_SELECT_GSHEET`, `SELECT_REPLACEMENT_GSHEET` | spreadsheet output tabs | **yes** |
| `run_select_from_db` | `SELECT_FROM_DB`, `TEST_SELECT_FROM_DB`, `SELECT_REPLACEMENT_FROM_DB` | respondent rows (`bulk_mark_as_selected`) | **yes** |
| `manage_old_tabs(dry_run=True)` | `LIST_OLD_TABS` | nothing | no |
| `manage_old_tabs(dry_run=False)` | `DELETE_OLD_TABS` | spreadsheet (deletes tabs) | **yes** |
| `auto_export_respondents` | none | the respondent *export* spreadsheet | no — it has its own per-assembly Redis lock, writes a different spreadsheet, and a DB selection commits before asking for an export (**D9**) |
| `monitor_selection_periodic` | — | goes through `start_gsheet_select_task` and `start_gsheet_manage_tabs_task` on the monitor assembly | covered by the service-layer guard |
| `cleanup_orphaned_tasks`, `prune_monitor_run_records`, `cleanup_old_password_reset_tokens` | — | run records / tokens, not assembly data | no |

Not a task but a bulk write to respondent rows: `reset_selection_status`
(`service_layer/respondent_service.py`), which calls
`respondents.reset_all_to_pool` and records a `RESET_TO_POOL` run record that
is COMPLETED the moment it is written. It is guarded (§3.5) but, because its
record is never unfinished, it is not in the set below.

So the set of task types that must exclude each other is:

```python
WRITING_TASK_TYPES = frozenset({
    SelectionTaskType.SELECT_GSHEET,
    SelectionTaskType.TEST_SELECT_GSHEET,
    SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
    SelectionTaskType.DELETE_OLD_TABS,
    SelectionTaskType.SELECT_FROM_DB,
    SelectionTaskType.TEST_SELECT_FROM_DB,
    SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
})
```

**D1** — one set, not one per data source. An assembly is either a Google
Sheets assembly or a database one, so cross pairs (a DB run alongside a
gsheet run) should not arise, and if they somehow do, refusing is the safe
answer. The set lives in `domain/value_objects.py` next to `SelectionTaskType`
and its labels, so a task type added later is seen next to the list it must be
classified into.

**D2** — a write never waits for a read, and a read never waits for a write.
Deleting output tabs while "check spreadsheet" is reading could make that read
fail, but it fails with a normal error the user can retry, and blocking reads
would complicate the UI for a small gain.

### 1.3 The existing check, and its two holes

`get_active_initial_selection_run_id` (`service_layer/sortition.py`) was
written to drive the "View Running Selection" button, and
`start_db_replace_task` borrows it as a guard. Two problems:

1. It looks only at the **latest** run record for the assembly. If a selection
   is running and someone then clicks "list old tabs" (read-only, allowed), the
   latest record is now `LIST_OLD_TABS`, and the running selection is invisible
   to the check. Same if an older run is still going and a newer one finished.
2. Its task-type set is the Initial Selection card's set. It omits
   `SELECT_REPLACEMENT_GSHEET` and `DELETE_OLD_TABS`, both writers.

Neither hole is a UI bug to fix separately: the fix is a repository query that
asks the right question, and the UI function switches to it (§3.2).

### 1.4 Where the race is

Check-then-insert at submit time: two requests both read "no unfinished run",
both insert a PENDING record, both dispatch. Without a lock somewhere the
service-layer check alone narrows the window but does not close it. Closing
it is the point of §2.

## 2. Where the lock lives

### The run record is the lock, Postgres serialises the check

The thing we want to know — "is a writing run unfinished on this assembly?" —
is already in the database, with a lifecycle that every failure path
maintains: the task marks its record COMPLETED/FAILED, the failure callback
marks FAILED, `cancel_task` marks CANCELLED, and `cleanup_orphaned_tasks`
marks FAILED after a crash, after `TASK_TIMEOUT_HOURS`, and (new, §3.6) after
an hour stuck in PENDING. So:

- **Submit time** (`start_*` in `sortition.py`): inside the open unit of work,
  take a Postgres transaction-scoped advisory lock keyed on the assembly id,
  then query unfinished writing runs for the assembly. If any, raise
  `SelectionAlreadyRunning`. Otherwise insert the PENDING record and commit
  (which releases the lock). Two concurrent submits serialise on the lock; the
  second sees the first's PENDING record.
- **Worker start** (the three writing tasks): the same claim, under the same
  lock, before any read of the data. It looks for unfinished writing runs on
  the assembly *other than itself*; if any, it marks its own record FAILED
  with a message saying what blocked it and returns; otherwise it sets its
  record RUNNING and commits. This is belt and braces for anything that
  reaches a task without going through a `start_*` function, and it is where
  the user asked for the guard.
- **Reset to pool** (§3.5): takes the same lock inside its own transaction,
  runs the same check, and does its bulk update before committing. Because
  the lock is transaction-scoped, a selection submitted or claimed *during*
  the reset waits for the reset's commit and then proceeds — the reset needs
  no unfinished record of its own to be excluded.

The lock is `SELECT pg_advisory_xact_lock(hashtext(:assembly_id))`. It is
released automatically at commit or rollback, needs no row, no TTL, no
cleanup, and leaves no state behind. A hash collision between two assemblies
only means two unrelated submits serialise for a few milliseconds.

Costs: one repository method (`get_unfinished_for_assembly`) and one
unit-of-work method to take the lock, plus a no-op in the fakes. Nothing new
in Redis, no migration.

### The alternative, and why not

A per-assembly Redis lock in the worker, like auto-export, was considered and
rejected: a selection may legitimately run for hours, so no TTL is right;
`cancel_task` revokes with `terminate=True` and a SIGKILL/OOM never runs
`finally`, so cancel and the cleanup job would both have to learn to release
a lock they did not take; and it makes two sources of truth (record says
RUNNING, Redis says free). Its one advantage — a lost Celery message never
blocks anything — is covered instead by failing records stuck in PENDING
(§3.6).

## 3. The work, in order

### 3.1 Domain

- `WRITING_TASK_TYPES` in `domain/value_objects.py` (§1.2), with a comment
  saying what "writes" means and that a new task type must be classified.

### 3.2 Repository and unit of work

- `SelectionRunRecordRepository.get_unfinished_for_assembly(assembly_id,
  task_types=None) -> list[SelectionRunRecord]`: PENDING or RUNNING records for
  the assembly, optionally filtered to a set of task types, oldest first. It
  sits next to the existing `get_all_unfinished`, which the cleanup job uses.
  SQL implementation filters on the ORM table columns as the CLAUDE.md pattern
  requires; the fake filters in Python.
- **D3** — the lock is a method on the unit of work,
  `uow.lock_assembly_for_write(assembly_id)`, rather than on a repository: it
  is a transaction-level concern, not a query about one aggregate.
  `SqlAlchemyUnitOfWork` executes the advisory lock SQL; `FakeUnitOfWork`
  records that it was called (so unit tests can assert the guard took the
  lock) and does nothing else.
- `get_active_initial_selection_run_id` switches to
  `get_unfinished_for_assembly(assembly_id, _INITIAL_SELECTION_TASK_TYPES)`
  and returns the oldest. That closes hole 1 of §1.3 for the UI without
  changing which card the button appears on.

### 3.3 Service layer: one guard function, called by every writing start

**D10** — the guard lives in a small new module,
`service_layer/writing_guard.py`, not in `sortition.py`. Both `sortition.py`
and `respondent_service.py` (for the reset, §3.5) need it; `sortition.py` is
large and reaches into Celery, and `respondent_service.py` is imported by
four other services, so a tiny leaf module is the safe way to avoid an import
cycle. It holds the exception, the guard, and the modal-parameter helper of
§3.4.

```python
class SelectionAlreadyRunning(InvalidSelection):
    """Raised when a writing task is refused because another is unfinished on the assembly."""
    def __init__(self, blocking: SelectionRunRecord) -> None: ...   # exposes .task_id and .task_type


def refuse_if_writing_run_unfinished(uow, assembly_id) -> None:
    uow.lock_assembly_for_write(assembly_id)
    running = uow.selection_run_records.get_unfinished_for_assembly(assembly_id, WRITING_TASK_TYPES)
    if running:
        raise SelectionAlreadyRunning(running[0])
```

The message (`str(e)`, flashed by every route that catches
`InvalidSelection`): "Another task is already writing to this assembly:
%(task)s", with the blocking record's `task_type_verbose`.

Called, after the existing validation and before the record is inserted, in:

- `start_gsheet_select_task`
- `start_gsheet_replace_task`
- `start_gsheet_manage_tabs_task` — only when `dry_run` is False
- `start_db_select_task`
- `start_db_replace_task` — replacing its current
  `get_active_initial_selection_run_id` check

Not called in `start_gsheet_load_task` or `start_gsheet_replace_load_task`
(reads). **D4** — the lock is taken *after* the validation that reads the
assembly. The validation (`number_to_select`, settings parse) does not depend
on other runs, and raising before taking the lock keeps the locked section to
the check and the insert.

Being an `InvalidSelection`, every existing `except InvalidSelection` still
catches it: the legacy routes, `dev.py`, and the monitor's
`_start_select_or_failure`, which reports "failed to start". That is right:
if the previous 15-minute monitor run is still going, this one should not
pile on. **D5** — the message names the blocking task's type label, not its
id; the modal redirect (§3.4) carries the id.

### 3.4 UI: a refused start lands inside the running task's modal

Clicking "run selection" while a run is going on takes the user to the
running selection, with a flash explaining why, and the modal's cancel button
is right there.

What the page already has: every progress modal opens from a query parameter
on `gsheets.view_assembly_selection` — `current_selection=<task_id>` for the
selection modals, `current_replacement` for the Google Sheets replacement
dialog, `current_manage_tabs` for the tab-management modal — and each has a
cancel button. The "View Running Selection" button on the Initial Selection
card is this same redirect. So no new modal is needed; the refused start just
has to land on the right one.

- One helper in `writing_guard.py`, `running_task_query_param(task_type) ->
  str`, mapping each writing task type to the query parameter that opens its
  modal. During implementation, confirm the mapping by reading
  `_get_selection_modal_context`, `_get_replacement_modal_context` and
  `_get_manage_tabs_context` in `blueprints/gsheets.py`; the DB progress modal
  is generic, so `SELECT_REPLACEMENT_FROM_DB` likely goes through
  `current_selection`.
- The six writing routes (`start_db_selection`, `start_db_replacement` and
  `reset_db_selection` in `db_selection_backoffice.py`; select, replace and
  delete tabs in `gsheets.py`) catch `SelectionAlreadyRunning` *before*
  `InvalidSelection` (or, for the reset, before its generic `except
  Exception`), flash an informational message ("A %(task)s is already running
  on this assembly. You can wait for it or cancel it here."), and redirect to
  the selection page with that parameter set to the running task's id. The
  user arrives inside the running task's modal, cancel button and all.

**D8** — the legacy blueprints keep the plain flash. They are due for deletion
and already catch `InvalidSelection`.

### 3.5 Reset to pool is refused while a selection is unfinished

`reset_selection_status` calls `refuse_if_writing_run_unfinished` after its
permission check and before `reset_all_to_pool`. Its own `RESET_TO_POOL`
record stays as it is — written COMPLETED, in the same transaction — because
the advisory lock already serialises the reset against any selection that
arrives while it runs (§2). The route change is in §3.4. The `dev.py` service
call and the legacy routes get the plain `InvalidSelection` flash for free.

### 3.6 A record stuck in PENDING for an hour is FAILED

A PENDING record whose Celery message was lost would otherwise block the
assembly until someone cancels it or `TASK_TIMEOUT_HOURS` (24) expires. So
`check_and_update_task_health` gets one more rule, checked right after the
overall timeout: a record still PENDING more than an hour after `created_at`
is marked FAILED with the user message "Task did not start" and a technical
message giving the elapsed time and Celery's reported state. The cleanup job
runs every five minutes, so the record is cleared within 65 minutes.

**D11** — the hour is a constant in `config.py` next to
`get_task_timeout_hours`, `PENDING_TASK_TIMEOUT_MINUTES = 60`, with the same
optional override parameter on `check_and_update_task_health` that
`timeout_hours` has, for tests. No environment variable: nobody has asked to
tune it, and the overall timeout already has one.

**D12** — an hour is honest queue time. The worker claim (§3.7) moves the
record to RUNNING as the very first thing a task does, so "PENDING for an
hour" means the worker never picked it up. The risk is a worker so backed up
that a selection waits over an hour in the queue; with one worker and tasks
measured in minutes that is itself a problem worth surfacing.

### 3.7 Worker: the claim at the top of each writing task

In `entrypoints/celery/tasks.py`:

```python
def _claim_assembly_for_writing(task_id, session_factory) -> bool:
    """Mark this run RUNNING unless another writing run on its assembly is unfinished.

    Returns False, having marked the record FAILED, when something else holds the assembly.
    """
```

It loads its own record by `task_id` (the tasks that take a `data_source`
rather than an `assembly_id` get the assembly from the record), takes the
lock, queries unfinished writing runs excluding itself, and either fails
itself or moves to RUNNING. Commit releases the lock.

Called first thing — before `_internal_load_*` — in `run_select`,
`run_select_from_db`, and `manage_old_tabs` when `dry_run` is False. Each
returns its usual failure tuple when the claim fails, so the progress modal
shows the error the same way as any other failure.

**D6** — a refused task is FAILED, not CANCELLED and not re-queued. Nobody
cancelled it, FAILED is the status every "could not do what was asked" path
uses, and in almost every case the user does not want a second run to happen
later either. The error message says exactly why: "Another task was already
writing to this assembly when this one started: …".

**D7** — the claim also moves the record to RUNNING. `_internal_load_gsheet`
and `_internal_load_db` set RUNNING again a moment later; harmless, and it
means the record leaves PENDING at the earliest possible moment, which is what
the PENDING timeout of §3.6 keys off.

### 3.8 Tell the reader

- `docs/background_tasks.md`: a section "One writing task per assembly" —
  the rule, the task table from §1.2, where the three checks live (submit,
  worker, reset), and why the lock is the run record and not Redis. Add the
  PENDING timeout to the health-check description. Adjust the auto-export
  section's mention of its own lock to point at it.
- `docs/configuration.md`: a line for the PENDING timeout constant under
  `TASK_TIMEOUT_HOURS`, saying it is not configurable.
- A sentence under Key Business Rules in `CLAUDE.md`.
- The `guard-initial-selection-plan.md` in `447-db-replacements/`: its step 2
  is this work; note that there and leave its step 1 (the held-count guard)
  as a separate branch.
- New `_()` strings → run the `translate-catalogues` skill before committing.

## 4. Tests

Unit, over `FakeUnitOfWork`, in `tests/unit/test_sortition_service.py` and
`tests/unit/test_respondent_service.py`:

- Each of the five writing starts refuses with `SelectionAlreadyRunning`
  when an unfinished run of a writing type exists on the assembly —
  parametrise the start function × the blocking task type × PENDING/RUNNING.
- Each runs when the unfinished run is a read type, is on another assembly,
  or has finished (COMPLETED, FAILED, CANCELLED).
- `start_gsheet_manage_tabs_task(dry_run=True)` is never refused.
- A refusal adds no record and dispatches no task.
- Every guarded start, and the reset, asked the fake unit of work for the
  lock (this is the only way unit tests catch a function that forgot the
  guard; see §6).
- `reset_selection_status` refuses while a DB selection is unfinished, changes
  no respondent and writes no record; runs when the selection has finished.
- `get_active_initial_selection_run_id` finds a running selection when a
  newer read-only record exists (hole 1).
- `get_unfinished_for_assembly` on the fake: filtering and ordering.
- `check_and_update_task_health`: a PENDING record older than the pending
  timeout is FAILED with the "did not start" message; a younger one, or a
  RUNNING one of the same age, is untouched. Next to the existing timeout
  tests.
- `running_task_query_param` covers every member of `WRITING_TASK_TYPES`
  (parametrise over the set, so a new type fails the test until mapped).

Integration, against Postgres:

- `tests/integration/test_sql_repository.py` (or wherever run-record
  repository tests live): `get_unfinished_for_assembly` filtering, ordering,
  and the task-type filter.
- `tests/integration/test_sortition_db_task.py`: `run_select_from_db` with a
  RUNNING writing record already on the assembly marks its own record FAILED
  with the message, and changes no respondent; with only a finished or
  read-only record it proceeds as today.
- `tests/integration/test_celery_tasks.py`: the same for `run_select` and for
  `manage_old_tabs(dry_run=False)` using the existing CSV-backed fake data
  source; `manage_old_tabs(dry_run=True)` is not blocked.
- The lock itself: two threads, each with its own session, call
  `refuse_if_writing_run_unfinished` then insert; exactly one succeeds.
  Advisory locks are per connection, so this needs real concurrent sessions,
  not one session used twice. Keep it to one test; it is the only test of the
  race.
- `cleanup_orphaned_tasks` end to end with a PENDING record created over an
  hour ago: it comes back FAILED.

Component, in `tests/component/test_db_selection_backoffice.py` and
`test_backoffice_gsheet_selection.py`:

- POST to each of the six writing routes while a writing run is unfinished
  starts nothing (or, for the reset, resets nothing) and redirects to the
  selection page with the running task's modal parameter set, and the page
  then renders that modal with its cancel button. Covers the bypass the guard
  exists for.

BDD, one scenario in a new `features/concurrent-selection.feature`, driven
from `tests/bdd/test_concurrent_selection.py` on a database assembly (no
Google needed): the admin opens the selection page, *then* another selection
starts (seeded as a RUNNING `SELECT_FROM_DB` record through the unit of work,
the way `assembly_with_many_runs` in `tests/bdd/conftest.py` seeds records),
and the admin clicks "Run selection" from the page they already had open.
They see the flash and the running selection's modal with its cancel button.
That is the real-world shape of the race — the button is only visible because
the page predates the other run — and it exercises the whole path from form
POST to modal. During implementation, check that clicking cancel on a seeded
record whose `celery_task_id` is None does not blow up in `cancel_task`;
if it does, the scenario stops at seeing the modal and the cancel path stays
with the existing cancel tests.

## 5. Out of scope, and why

- **The held-count guard** (an initial selection refusing to run while anyone
  is selected or confirmed). Separate plan, separate branch; see
  `447-db-replacements/guard-initial-selection-plan.md` step 1.
- **Respondent edits during a selection.** A confirmation caller marking
  someone withdrawn while `run_select_from_db` is between reading the pool and
  writing the panel can see that person marked selected. Single-row edits are
  not tasks and locking them out of the page for the length of a run is a
  product decision, not a guard. Worth a `future_work/` note.
- **Auto-export.** Not blocked by, and does not block, a selection (**D9**,
  §1.2). Its Redis lock stays as it is.
- **Deleting the legacy routes** — they call the same `start_*` functions, so
  they are covered for free.

## 6. Risks

- The advisory-lock SQL is Postgres-only. So is `PostgresUUID`; the app has
  no other database. The fake unit of work does not take a real lock, so
  unit tests cannot catch a start function that forgets to call the guard by
  observing a race. They catch it instead by asserting the fake saw the lock
  call (§4), and the parametrised refusal tests catch it a second way.
- The monitor runs every 15 minutes with a 6-minute wall clock. If a monitor
  selection hangs past 15 minutes, every subsequent monitor run fails to
  start until the cleanup job or a cancel clears it. That is the correct
  signal (something is stuck), but it changes what the monitoring alert says
  from "timed out" to "failed to start (InvalidSelection)". Accepted.
- The PENDING timeout (§3.6) will fail a task that genuinely sat queued for
  over an hour on a backed-up worker. Accepted; see **D12**.

## 7. Order of commits

- [x] 1. `WRITING_TASK_TYPES`, repository method and fake, unit-of-work lock
  method, integration tests for the query. (696142a0)
- [x] 2. `writing_guard.py` (exception, guard, modal-parameter helper) and its
  unit tests; the five `start_*` functions and the reset call it;
  `get_active_initial_selection_run_id` on the new query; translation
  catalogues. (70e45632)
- [x] 3. Worker claim and its integration tests. (62afc282)
- [x] 4. PENDING timeout in `check_and_update_task_health`, config constant,
  unit and integration tests. (fee772ef)
- [x] 5. Route handling and redirect of §3.4 (six routes), component tests.
  (02e36079)
- [x] 6. BDD scenario. (7627cd99)
- [x] 7. Docs, CLAUDE.md line, update to the 447 plan.

Two things learned while implementing, neither in the plan:

- The worker claim must run *before* `_set_up_celery_logging` installs the
  run-log handler, because that handler sets the record to RUNNING on every
  log line and would undo a refusal.
- `check_and_update_task_health` went over the complexity limit, so both
  timeouts now live in helpers (`_fail_if_timed_out`,
  `_fail_if_stuck_pending`) that read the same way.

## 8. Review decisions

Answers from the first review, kept so the reasoning is not lost:

- **Q1** Advisory lock, not `FOR UPDATE` on the assembly row. The row lock
  would block concurrent assembly edits for the length of the check and
  couple the guard to the `assemblies` table.
- **Q2** The run record is the lock; Postgres serialises the check. The Redis
  alternative is recorded in §2 with the reasons against it.
- **Q3** Auto-export neither blocks nor is blocked by a selection (**D9**).
- **Q4** "Reset to pool" is refused while a selection is unfinished, through
  the same guard (§3.5).
- **Q5** A record still PENDING after an hour is FAILED (§3.6).
- **Q6** A worker that finds the assembly held fails its run; it does not
  re-queue. The user almost never wants the second run to happen later
  (**D6**).
- **Q7** One BDD scenario (§4).
- **Q8** A stuck monitor selection surfacing as "failed to start" on later
  ticks is fine.
- **Q9** A refused start redirects straight into the running task's modal,
  with a flash (§3.4).
