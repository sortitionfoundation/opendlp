# Code review: 447-db-replacements

Review of the branch against `main`, from reading the code. No tests were run.
Line numbers prefixed `~` are approximate.

Each item has an ID and a decision. Work that belongs on another branch is
written up in [guard-initial-selection-plan.md](guard-initial-selection-plan.md).

## Part 1: What guards an initial or test selection

The rule: an initial or test selection over database respondents may only run
when nobody is selected or confirmed. **Only the templates enforce it.**

| Layer | Checks the rule? | Detail |
|---|---|---|
| Backoffice template (`assembly_selection.html:107-147`) | Yes | Run buttons render only with no active run and `csv_selected_count == 0` |
| Legacy template (`db_selection/select.html:83-93`) | Weakly | Buttons rendered with `disabled`, client-side only |
| Backoffice route (`db_selection_backoffice.py:97-110`) | No | Checks `settings_confirmed` only |
| Legacy route (`db_selection_legacy.py:175-184`) | No | Checks `settings_confirmed` only |
| `start_db_select_task` (`sortition.py:486-543`) | No | Permission, assembly exists, `number_to_select >= 1`, settings valid |
| Celery task and result write | No | `Respondent.mark_as_selected` has no precondition |

A direct POST to either run route starts a selection regardless. Those two
routes are the only entry points; the CLI and monitor use the Google Sheets flow.

**What a bypass does:** the pool load filters on pool status, so nobody is
selected twice. But the run selects a full `number_to_select` against the full
targets and writes a second panel on top of the first.

`start_db_select_task` is identical on `main` and this branch, so the hole
predates this work.

### G1. Add a service-layer guard on respondent status

Refuse in `start_db_select_task` by raising `InvalidSelection`. Both routes
already catch and flash it, so no route changes are needed.

Which count?

- `count_non_pool_respondents` (`respondent_service.py:410`): anything not in
  the pool and not deleted. This is what the templates gate on today, and it
  matches "reset to pool", which resets withdrawn people too. **Recommended.**
  Catch: one withdrawn person and nobody selected is refused until reset.
- `count_held_respondents` (`respondent_service.py:419`): selected plus
  confirmed. Matches the rule as stated. The template should then switch to the
  same count.

Check for a circular import between `sortition.py` and `respondent_service.py`;
if there is one, call `uow.respondents.count_non_pool` directly.

**Decision:** use `count_held_respondents`. A test submission (from testing the
registration page) must not block a selection, and someone can legitimately
withdraw before one. The templates switch to the same count so that the page
and the guard agree. Separate branch - see the plan.

### G2. Add an "already running" guard

`start_db_replace_task` refuses if `get_active_initial_selection_run_id` returns
a run. `start_db_select_task` does not, so two runs can be queued concurrently.

**Decision:** the rule is wider than this item: no two runs that write to the
same assembly may run at the same time. The blocking rule needs reviewing, and
probably widening, as the first step of the separate branch - see the plan.

### G3. Revert to `already_selected=None` for initial and test runs

`_internal_load_db` (`celery/tasks.py`) now loads selected and confirmed
respondents for all three database task types. On `main` it passed `None`.
Effect today: with address checking on, pool members sharing an address with a
held person are dropped, and every run logs "N people already hold a place."

Agreed: initial and test runs should pass `None`. Gate on
`targets_snapshot is not None`. `docs/architecture.md` and
`docs/background_tasks.md` already describe it that way.

**Decision:** agreed. Fix on this branch.

### G4. A test selection writes statuses

`run_select_from_db` calls `_internal_write_db_results` unconditionally;
`test_selection` reaches only the solver step. So a test run marks its panel as
selected like a real one. No test covers this. Is it intended?

**Decision:** intended. In user testing, people were confused when a test
selection did not mark anyone as selected. No behaviour change; at most a
comment saying so, which goes with the guard work in the plan. "Test selection"
probably wants renaming at some point, as users are not sure what it means.

### G5. `csv_selected_count` is misnamed

It counts everything not in the pool (selected, confirmed, withdrawn, test
submission). `csv_held_count`, added on this branch, is selected plus confirmed.
`assembly_selection.html:86-93` gates on the first and displays the second, so
an assembly with only withdrawn people reads "0 respondents are currently
selected" while hiding the run buttons.

**Decision:** rename to `non_pool_count`, which is what the legacy readiness
object already calls the same number. Fix on this branch.

### G6. Where does the guard go?

G1, G2 and possibly G4 fix something that exists on `main`. Suggest a separate
branch off `main` for those, keeping only G3 and G5 here.

**Decision:** G1 and G2 go on a new branch, planned in
[guard-initial-selection-plan.md](guard-initial-selection-plan.md). G3 and G5
are fixed on this branch.

## Part 2: Fix before merge

### B1. Feasibility solve runs inside a GET, inside the transaction

`gsheets.py:290-294`, `db_selection_backoffice.py:~153-159`. Every
`?replacement_modal=open` load pulls the whole pool into memory and runs
`setup_committee_generation` within `with uow:`. A large pool holds a database
connection and a gunicorn worker for the length of a solve. Not measured.

Fix: split the load (needs the uow) from the check (`_check_feasibility` is
already uow-free) and run the check after the block closes. Consider checking
only on the recheck button.

**Decision:** run the check after the uow block closes. Keep checking on every
open of the dialog, not just on the recheck button.

### B2. Read-only users are bounced off a page they can view

`gsheets.py:292`. The selection page needs view permission, but
`build_replacement_plan` requires `can_manage_assembly`. A read-only user
following a `?replacement_modal=open` link is sent to the dashboard with a
permission error. It fails closed, so nothing leaks. No test covers it.

Fix: build the plan only when the user can manage the assembly; otherwise
render with the modal closed.

**Decision:** fix.

### B3. Legacy run redirect does not know the new task type

`gsheets_legacy.py:1414`. A `SELECT_REPLACEMENT_FROM_DB` run falls through to
"Unknown task type". `DB_SELECTION_TASK_TYPES` (`value_objects.py:151`) exists
for this and is referenced nowhere; its comment says the download routes use it.

Fix: use the constant there and at `sortition.py:736`, or delete it.

**Decision:** minimal fix only - the legacy routes will be deleted soon.

### B4. Focus is lost when a suggestion is accepted

`replacement-suggestions.js:41-90`, `db_replacement_modal.html:105-111`.
`refresh()` hides the button just pressed; "Accept all" hides its own container.
Focus drops to `<body>` behind an `aria-modal` dialog. The "Every suggestion has
been applied" note has no live region, so a screen reader announces nothing.

Fix: move focus to the filled input or the note, and put the note in a
`role="status"` container. Add a Vitest case.

**Decision:** fix.

## Part 3: Lower stakes

### Backend

- **L1.** GET render keeps only `.feasibility` (`gsheets.py:294`), so an empty
  pool or conflicting targets opens the dialog with no explanation until submit.
- **L2.** `db_selection_backoffice.py:150-170` validates in one `with uow:` and
  starts the task in a second. Impact is small: the task re-reads the pool.
- **L3.** A solver exception other than `SortitionBaseError` on the GET path
  sends the organiser to the dashboard. Could degrade to
  `FeasibilityResult(checked=False)`.
- **L4.** `sortition.py:~577` raises `InvalidSelection(str(e))`, which is
  flashed untranslated. Existing pattern; `translate_sortition_error(e)` is what
  `replacement_targets.py` uses.
- **L5.** `docs/architecture.md` lists 8 routes for `db_selection_backoffice`
  (now 10) and has no row for `replacement_targets`.
- **L6.** `db_selection_backoffice.py` imports `render_selection_page` from the
  sibling blueprint `gsheets.py`; `replacement_targets.py` parses raw form
  fields. Layering smells, not defects.

**Decision:** fix L1 to L5. L6 stays as it is.

### Translation and wording

- **L7.** Six strings use a bare `%(count)s` and read "1 places are to be
  filled" / "1 people are selected". Use `ngettext`.
  `db_replacement_modal.html:21, 30`, `assembly_selection.html:93`,
  `tasks.py:630`, `replacement_targets.py:~502, ~541`.
- **L8.** `db_replacement_modal.html:30` splices one msgid into another
  ("...so %(to_fill)s."). Translators cannot reorder across them.
- **L9.** "no matching respondent column, so nothing counts as held"
  (`db_replacement_modal.html:~128`): "column" and "held" are code words.
  Touches an open item in `language.md`.
- **L10.** `%(category)s` placeholder names where the glossary says target.
- **L11.** A bare lowercase `change` msgid (`db_replacement_modal.html:37`),
  which is also the button's whole accessible name.
- **L12.** "Warning:" prefix inside a warning alert
  (`db_replacement_modal.html:54`).
- **L13.** One reword, justified: "respondents have been selected" became "are
  currently selected" because the number changed meaning. The Hungarian is
  lost. About 55 new msgids need translating.

**Decision:** fix L7 to L12. The Hungarian catalogue is brought up to date
later, not on this branch.

### Template

- **L14.** `<ul>` inside the alert macro's `<p>`
  (`db_replacement_modal.html:40-44`): the parser closes the `<p>`, so the
  error list loses its colour.
- **L15.** The "change" button hides itself on click, so `aria-expanded="true"`
  is never exposed.
- **L16.** `required` inputs inside collapsed `<details>` may block submit
  silently. Not browser-tested. `novalidate` plus server-side errors avoids it.
- **L17.** Hand-rolled table, number input and footer where macros exist. Table
  headers lack `scope`. Input and footer copy
  `edit_number_to_select_modal.html`.
- **L18.** The `else` hint at `assembly_selection.html:157-165` is correct only
  by coincidence; make it an explicit `elif not csv_settings_confirmed`.

**Decision:** fix L17 and L18. L14 to L16 stay open while Hamish looks into
them further.

## Part 4: Test gaps

- **T1.** The e2e dispatch smoke patches `start_db_replace_task`
  (`tests/e2e/test_db_selection_backoffice.py:462-490`), an internal service
  function. Nothing reaches Postgres, so the JSON round trip of `targets_used`
  is unexercised. Patch `.delay` and read the record back.
- **T2.** `test_requires_assembly_management`
  (`test_db_replacement_backoffice.py:344-350`) accepts `302 or 403` and asserts
  the modal is absent, which a redirect satisfies trivially.
- **T3.** Four `except` branches of `start_db_replacement` have no route test,
  including "selection already running".
- **T4.** No report or CSV test for a replacement-shaped snapshot
  (`overall_min`, `held`, `calculated_*`). The `SELECT_REPLACEMENT_FROM_DB`
  branch of `_process_celery_final_result` is untested.
- **T5.** Untested branches in `replacement_targets.py`:
  `min_exceeds_number_to_select`, the three `SortitionBaseError` paths, explicit
  flex clamping, `targets_conflict` true, negative or non-numeric cells.
- **T6.** Two assertions that cannot fail in
  `test_db_replacement_backoffice.py`: `'value="5"'` also matches the Female
  maximum cell (`:486`); `"Gender" in html` is always true (`:322`).
- **T7.** `test_missing_number_is_an_error` submits `"0"`
  (`test_replacement_targets.py:300-307`).
- **T8.** No test asserts a selection is refused when people are selected, and
  none runs `run_select_from_db` with `test_selection=True`. Both belong with
  G1 and G4.
- **T9.** Template branches unasserted: the `targets_conflict` alert, the "more
  places held than the target allows" note, the "no matching respondent column"
  label.

**Decision:** fix T1, T2, T4, T6, T7 and T9. T8 moves to the plan. For T3 and
T5, error handling that follows a common pattern does not need a test of its
own, so only the handling that is new or unusual gets one: the "selection
already running" refusal (T3), and `min_exceeds_number_to_select`, explicit
flex clamping, `targets_conflict` and negative or non-numeric cells (T5).

No existing test was weakened. The BDD loading scenario now seeds a RUNNING
record rather than clicking, a sound race fix; other scenarios still cover the
click.

## Part 5: Issues to raise, not fix here

- **I1.** `tests/unit/test_celery_tasks_progress.py` uses Postgres from under
  `tests/unit/`.
- **I2.** Unwrapped "Task submitted for..." run-log lines in `sortition.py`.
  The branch adds a fifth to four existing.
- **I3.** `modal.html:35-36` notes that dialogs do not all move focus in on
  open.

## Clean

- **JSON:** no JSON route added or reshaped, no `str(e)` in a response body, no
  hand-typed API literal in the JS test.
- **Exceptions and logging:** no new exception classes; catches are narrow; the
  one `except Exception` is the outermost handler and logs via structlog. No
  personal data logged.
- **Transactions:** `render_template` is outside every block, no
  `commit_and_reset()`, no swallowed database errors.
- **Permissions:** the new route is capability-gated and every query is scoped
  by the URL's assembly id.
- **Personal data:** snapshots hold target names and counts only. No cookies,
  analytics or third-party scripts.
- **Config and build:** no changes to `config.py`, `package.json`,
  `esbuild.config.mjs`, `justfile` or `static/`. The new component is reached
  from an existing entry point under the name the template uses.
- **Frontend rules:** no inline `<svg>`, no nested `caller()`, all CSS tokens
  defined, Alpine attributes CSP-compliant, no user-facing strings in JS, no
  CDN scripts, no `x-html`.
- **Enum labels:** the new task type has its `_l()` label and is covered by the
  parametrised test.
- **Schema:** no migration needed; `task_type` is a string column.
- **`gsheets.py` refactor:** body extracted verbatim into
  `render_selection_page`, behaviour preserved.
