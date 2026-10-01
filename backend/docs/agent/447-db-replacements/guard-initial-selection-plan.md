# Plan: guard initial and test selections in the service layer

For a new branch off `main`. It came out of the review of `447-db-replacements`
([review.md](review.md), items G1, G2, G4 and T8), but the hole it closes is on
`main` already: `start_db_select_task` is identical on both.

## The problem

Two rules about selections over database respondents are enforced only by
templates hiding or disabling buttons:

1. An initial or test selection may only run when nobody is selected or
   confirmed. Once someone is, the organiser has to "reset to pool" first.
2. No two runs that write to the same assembly may run at the same time.

A direct POST to either run route starts a selection regardless, and so would
any route added later. What a bypass does today: the pool load filters on pool
status, so nobody is selected twice, but the run selects a full
`number_to_select` against the full targets and writes a second panel on top of
the first.

Entry points that reach `start_db_select_task`, neither of which checks:

- `POST /assembly/<id>/selection/db/run` - `db_selection_backoffice.start_db_selection`
- `POST /assemblies/<id>/db_select/run` - `db_selection_legacy.start_db_selection`

The CLI and the monitor use the Google Sheets flow only.

## Decisions already made

- **The status guard counts selected plus confirmed** - `count_held_respondents`,
  not `count_non_pool_respondents`. A test submission (from testing the
  registration page) must not block a selection, and someone can legitimately
  withdraw before one.
- **A test selection writes statuses, and that is intended.** In user testing,
  people were confused when a test selection did not mark anyone as selected.
  So the guard applies to test selections exactly as it does to real ones.
- **Guards raise `InvalidSelection`.** Both routes already catch and flash it,
  so the routes need no new handling.

## Step 1: the status guard (G1)

In `start_db_select_task` (`service_layer/sortition.py`), after the
`number_to_select` check:

- Refuse when `count_held_respondents(uow, assembly_id) > 0`, with a message
  that says what to do: reset the selection first.
- `count_held_respondents` is in `respondent_service.py`. It arrives with
  `447-db-replacements`, so this branch has to start after that one merges, or
  carry the function itself. Check for a circular import between `sortition.py`
  and `respondent_service.py`; if there is one, move the count rather than
  importing at runtime.

Then make the pages agree with the guard:

- `templates/backoffice/assembly_selection.html` hides the run buttons on the
  non-pool count (`non_pool_count`). Switch that condition to the held count.
- `db_selection_legacy.py` readiness uses `non_pool_count == 0`. The legacy
  routes are due for deletion, so leave the template alone unless they are
  still there - the service guard covers them either way.
- Decide what the page says when the only non-pool people are withdrawn or test
  submissions: the run buttons now show, so the "reset" warning should not.

Open question for Hamish: "reset to pool" also resets withdrawn people to the
pool. With the guard on held people only, an organiser can now run a selection
with withdrawn people left withdrawn. That looks right - they withdrew - but it
is a change from what the page allows today.

## Step 2: the running guard (G2)

Start by digging, not coding. The rule is wider than "initial selection already
running", and the existing check is narrower than it looks:

- `get_active_initial_selection_run_id` looks only at the **latest** run for
  the assembly. If the latest record is some other task type, or a finished
  one, an older run that is still going is missed. Find out whether that can
  happen in practice.
- Its task-type set (`_INITIAL_SELECTION_TASK_TYPES`) was written to drive a
  button on the selection page, not to guard writes. List every task type and
  what it writes to - respondent rows, the spreadsheet, nothing - and decide
  which pairs must exclude each other.
- The Google Sheets starts (`start_gsheet_select_task`,
  `start_gsheet_replace_task`, the tab management tasks) have no running check
  either. Decide whether they are in scope: two runs writing tabs to one
  spreadsheet is the same defect.
- Check-then-insert is a race: two requests can both pass the check before
  either commits its record. Decide whether that needs closing (a row lock on
  the assembly, or a partial unique index on unfinished runs) or whether the
  window is acceptable.

Then write the rule down, give it one function with a name that says it guards
writes, and call it from every start function it covers.
`start_db_replace_task` already has a check to fold in.

## Step 3: say that a test selection writes statuses (G4)

No behaviour change. Add a comment at the write step in `run_select_from_db`
(`entrypoints/celery/tasks.py`) saying that a test selection marks its panel as
selected on purpose, and why. Mention it in `docs/background_tasks.md`.

## Tests (T8)

Unit, over `FakeUnitOfWork`, in `tests/unit/test_sortition_service.py`:

- `start_db_select_task` refuses when a respondent is selected.
- It refuses when a respondent is confirmed.
- It runs when the only non-pool respondents are withdrawn, test submissions or
  deleted.
- Each of those for `test_selection=True` as well - parametrise.
- It refuses while another run that writes to the assembly is unfinished, and
  runs once that one has finished. One case per pair the rule in step 2 covers.
- A refusal adds no `SelectionRunRecord` and dispatches no task.

Component, in `tests/component/test_db_selection_backoffice.py`:

- A direct POST to the run route with a selected respondent flashes the error
  and starts nothing. This is the bypass the guard exists for.
- The selection page shows the run buttons when only withdrawn people are
  outside the pool, and hides them when someone is selected.

Integration, in `tests/integration/test_sortition_db_task.py`:

- `run_select_from_db` with `test_selection=True` marks its panel as selected.
  Nothing covers this today.

BDD: one scenario that an organiser who has run a selection is offered a reset,
not another run. Check first whether `features/` already has it.

## Out of scope

- Renaming "test selection". Users are not sure what it means, but that is a
  wording and translation job of its own.
- Deleting the legacy routes.
