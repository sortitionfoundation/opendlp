# Replacement selection from the database — implementation plan

**Status:** Implemented — all six chunks landed on `447-db-replacements`
(2026-09-24). Decisions are marked **D1**…**D9** inline and collected in §9.
Move this document to `docs/agent/history/` once the branch is merged.
**Date:** 2026-09-24
**Branch:** `447-db-replacements` (off `main`)
**Story:** 447 — enable replacements when the respondents live in the database

## 0. What this is, and where we start from

On the Selection tab (`gsheets.view_assembly_selection`) an assembly whose data
is in the database (`data_source == "csv"`) gets an Initial Selection card that
works, and a Replacement Selection card that says "Coming Soon" with a disabled
button (`templates/backoffice/assembly_selection.html` ~line 146). This plan
makes that card live.

The user's flow, as agreed in the story:

1. Some selected respondents have withdrawn (status `WITHDRAWN`, set from the
   respondent page by a confirmation caller).
2. On the Selection tab the organiser opens the Replacement Selection dialog.
3. The dialog shows **auto-calculated replacement targets** — for each target
   value, how many seats are still to fill — plus the number of replacements to
   select, highlighting values where the pool cannot supply the minimum.
4. The organiser can **edit the replacement min/max** (never the overall
   targets), then clicks the run button.
5. The run is a Celery task that reuses the database selection machinery and
   the existing progress modal; newly selected people get status `SELECTED`.
6. The run record keeps both the calculated and the actually used targets.

### 0.1 What already exists that we reuse

| Piece | Where | How it helps |
|---|---|---|
| Initial DB selection task | `entrypoints/celery/tasks.py::run_select_from_db` → `_internal_load_db` / `_internal_run_select` / `_internal_write_db_results` | The replacement run is the same pipeline with different features and an `already_selected` set |
| DB data adapter | `adapters/sortition_data_adapter.py::OpenDLPDataAdapter` | Feeds targets and eligible `POOL` respondents to the library. `read_already_selected_data` is a stub that we fill in |
| Task starter and record | `service_layer/sortition.py::start_db_select_task` | Template for `start_db_replace_task`; `SelectionRunRecord.targets_used` already snapshots targets |
| Progress modal | `templates/backoffice/components/db_selection_progress_modal.html` + `db_selection_backoffice.db_selection_progress_modal` | Generic for any DB run: status, log, cancel, downloads. Reused unchanged for the replacement run |
| Per-target-value counts | `uow.respondents.get_selected_attribute_value_counts` (SELECTED+CONFIRMED) and `get_attribute_value_available_counts` (eligible POOL), both used by `service_layer/dashboard_stats.py` | Exactly the "held" and "in pool" numbers the calculation needs |
| Category ↔ attribute matching | `dashboard_stats._matching_attribute` (normalised, loose) | Same matching for the replacement counts |
| Library checks | `sortition_algorithms.features.minimum_selection` / `maximum_selection` / `report_min_max_error_details_structured` / `check_desired`; `people.check_people_per_feature_value` | Validate the edited targets before we start a task |
| Gsheet replacement modal | `templates/backoffice/components/replacement_modal.html`, `gsheets._get_replacement_modal_context`, URL params `replacement_modal=open` / `current_replacement` | Conventions for the dialog; the DB version is simpler (no load task) |
| Modal with a plain form | `templates/backoffice/components/edit_number_to_select_modal.html` | Pattern for a modal that is just a POST form opened by a query param |
| Target snapshot format | `domain/targets.py::target_categories_to_snapshot`, consumed by `service_layer/selection_report.py` | We extend the per-value dicts; the report keeps working |

### 0.2 Why the DB flow is simpler than the Google Sheets flow

The gsheet flow needs a *load* task ("Check Spreadsheet") because reading a
spreadsheet is slow, and it needs the organiser to maintain a "replacement
targets" tab by hand. In the database the counts are a handful of `GROUP BY`
queries, and we can compute the replacement targets ourselves. So the DB
dialog has **one state** (review and run), and after "run" we hand over to the
existing DB progress modal. No polling in the replacement dialog, no
`LoadRunResult`, no `features_pending` dance.

---

## 1. The arithmetic

For each target value `v` in category `c`, with overall targets `[min, max]`:

```
held      = number of respondents with value v whose status is SELECTED or CONFIRMED
calc_min  = max(0, min - held)
calc_max  = max(0, max - held)
available = number of respondents with value v in POOL, not marked ineligible / cannot attend
shortfall = max(0, calc_min - available)
```

And at the top level:

```
held_total  = count of respondents with status SELECTED or CONFIRMED  (all values)
calc_number = max(0, assembly.number_to_select - held_total)
```

`WITHDRAWN` people are not held: they freed their seat, which is the whole
point. `DELETED` and `TEST_SUBMISSION` are never counted (same as
`COUNTED_RESPONDENT_STATUSES`).

**Flex values.** `TargetValue` carries `min_flex` (default 0) and `max_flex`
(default `MAX_FLEX_UNSET`, meaning "let the library pick"). Proposal:

```
calc_min_flex = min(calc_min, max(0, min_flex - held))
calc_max_flex = MAX_FLEX_UNSET                if max_flex is unset
              = max(calc_max, max_flex - held) otherwise
```

so the invariants `min_flex <= min` and `max_flex >= max` still hold. The
adapter only emits flex columns when every value has explicit flex set, and
that rule carries over unchanged.

> **D1 — flex.** Keep flex and subtract `held` from its bounds as above. We
> do not set flex anywhere today, but we may in future, and an organiser who
> sets it on the overall targets presumably wants the same latitude on the
> seats still to fill. Dropping it on replacement runs was considered and
> rejected.

**Edge cases the arithmetic must survive:**

- `held > max` (someone was hand-moved to SELECTED past the cap, or targets were
  edited after the initial run): `calc_max` clamps to 0 and the row is shown
  with a note. Nothing to select in that value.
- A category whose name matches no respondent column: `held = 0` for every
  value, so the replacement targets equal the overall targets. Show a warning
  on the category (the dashboard already does this: "unmatched").
- `calc_number == 0` (nobody withdrew): the dialog says so and the run button
  is disabled.
- Cross-category inconsistency after subtraction: e.g. Gender still needs
  `[4, 6]` but Age still needs `[0, 3]`. `minimum_selection > maximum_selection`
  — the library would refuse. We detect it up front (§4.2) and the organiser
  fixes it in the editable cells.

---

## 2. Where the code goes

### 2.1 Domain: `domain/targets.py`

Pure functions, testable without a database:

```python
@dataclass(frozen=True)
class ReplacementMinMax:
    min: int
    max: int
    min_flex: int
    max_flex: int

def replacement_min_max(value: TargetValue, held: int) -> ReplacementMinMax:
    """The seats still to fill for one target value, given how many are held."""
```

(§1 arithmetic lives here and nowhere else.)

### 2.2 Service: new module `service_layer/replacement_targets.py`

`sortition.py` is already 1,000+ lines; the replacement calculation is a
different concern from task orchestration, so it gets its own module.

```python
@dataclass
class ReplacementValueRow:
    value: str
    value_id: uuid.UUID         # form field names key off this
    overall_min: int
    overall_max: int
    held: int                   # SELECTED + CONFIRMED
    calculated: ReplacementMinMax
    available: int              # eligible POOL
    shortfall: int              # max(0, calculated.min - available)

@dataclass
class ReplacementCategory:
    name: str
    category_id: uuid.UUID
    attribute_matched: bool     # False → counts are all zero, show a warning
    rows: list[ReplacementValueRow]

@dataclass
class ReplacementPlan:
    number_to_select: int       # assembly.number_to_select
    held_total: int
    calculated_number: int      # number_to_select - held_total, floored at 0
    min_select: int             # minimum_selection() over the calculated targets
    max_select: int             # maximum_selection() over the calculated targets
    categories: list[ReplacementCategory]
    problems: list[str]         # cross-category or "nothing to select" messages

@require_assembly_permission(can_manage_assembly)
def build_replacement_plan(uow, user_id, assembly_id) -> ReplacementPlan
```

`build_replacement_plan` loads the categories, matches each to a respondent
column with the same loose matching the dashboard uses, runs the two count
queries per matched category (`get_selected_attribute_value_counts`,
`get_attribute_value_available_counts`), applies `replacement_min_max`, and
computes the headline numbers. Two count queries per category is what the
dashboard already does on every load, so no new repository methods are needed.

> **D2 — matching.** The targets page matches category names to respondent
> columns case-insensitively (`target_respondent_helpers`); the dashboard
> matches loosely via `normalise_field_name` (so "Age Range" finds
> `age_range`); the library, which decides who counts at selection time, is
> case-insensitive on names. Decision: use the dashboard's loose matching, and
> move `_matching_attribute` to a shared place rather than copy it. The three
> ways of matching are a known inconsistency; a later round of work will
> reconcile them, and is out of scope here.

Also in this module, the form → targets step:

```python
@dataclass
class ReplacementTargetsEdit:
    """What the organiser submitted: number to select plus min/max per value id."""
    number_to_select: int
    min_max: dict[uuid.UUID, tuple[int, int]]

@dataclass
class ReplacementValidation:
    ok: bool
    errors: list[str]                          # top-level, e.g. cross-category
    value_errors: dict[uuid.UUID, list[str]]   # per input cell
    targets_snapshot: list[dict]               # what the task will run with

def validate_replacement_targets(uow, assembly_id, plan: ReplacementPlan,
                                 edit: ReplacementTargetsEdit) -> ReplacementValidation
```

Validation (§4.2) builds a `FeatureCollection` from the edited numbers (via the
adapter with a targets override, §2.3) and runs the library's structured checks.

### 2.3 Adapter: `adapters/sortition_data_adapter.py`

Two changes to `OpenDLPDataAdapter`:

1. **Targets override.** New keyword `targets_snapshot: list[dict] | None`.
   When given, `read_feature_data` yields rows from the snapshot instead of
   `uow.target_categories`. The snapshot is the same shape
   `target_categories_to_snapshot` produces, so the task runs on exactly what
   the run record stores. The flex-column rule (emit only if all set) is
   applied to the snapshot the same way.
2. **Already selected.** Fill in the `read_already_selected_data` stub: yield
   the `SELECTED` + `CONFIRMED` respondents with the same headers as
   `read_people_data`. The library only keeps id and address columns from this
   feed, and uses it in `run_stratification` to drop pool members sharing an
   address with someone already on the panel. Today that check silently does
   nothing for DB runs; for replacements it matters (household rule), and it is
   harmless for initial selection (the set is empty). Set
   `already_selected_data_container` to something sensible for error messages.

> **D3 — same-address for replacements.** Enabling `already_selected` means a
> replacement run will not pick someone from the household of a person who is
> still `SELECTED`/`CONFIRMED`. It *will* allow the household of someone who
> `WITHDRAWN`: if two people share an address and one is selected and then
> withdraws, the other is eligible as a replacement. So the feed is
> `SELECTED_RESPONDENT_STATUSES` only, never `WITHDRAWN`. The integration test
> in §6 covers both directions of this rule.

### 2.4 Task: `entrypoints/celery/tasks.py`

No new task. `run_select_from_db` and `_internal_load_db` gain
`targets_snapshot: list[dict] | None = None`. When set:

- `_internal_load_db` builds the adapter with the override and additionally
  calls `select_data.load_already_selected(settings)`, logging how many people
  are already on the panel.
- `run_select_from_db` passes `already_selected` to `_internal_run_select`
  (today it hard-codes `None`).

`_internal_write_db_results` is unchanged: it marks the selected external ids
as `SELECTED` with this run's `task_id` as `selection_run_id` (so "which round
picked them" is answerable from the data), and stores `remaining_ids`.

### 2.5 Task type and starter: `domain/value_objects.py`, `service_layer/sortition.py`

- `SelectionTaskType.SELECT_REPLACEMENT_FROM_DB = "select_replacement_from_db"`
  with label `_l("Select replacements from database")` in
  `selection_task_type_labels`. No test variant (test replacement runs are out
  of scope per the story).
- `start_db_replace_task(uow, user_id, assembly_id, number_to_select,
  targets_snapshot, calculation)` mirrors `start_db_select_task`: builds
  settings, creates the run record, dispatches `run_select_from_db.delay(...,
  targets_snapshot=...)`. Refuses (`InvalidSelection`) if `number_to_select < 1`
  or an initial/replacement DB task is still running for the assembly
  (`get_active_initial_selection_run_id` today only looks at initial types —
  widen it or add a sibling that covers DB replacement runs too).
- `view_run_details` in `gsheets.py` already redirects every run in the
  history table to `?current_selection=<run_id>`, and the selection page picks
  the DB progress modal whenever the source is csv, so a finished replacement
  run opens in the right modal with no change there.

### 2.6 What the run record stores (acceptance criterion 4)

`SelectionRunRecord` already has `settings_used` (JSON), `targets_used` (JSON
snapshot). Proposal, **no migration**:

- `targets_used` = the replacement snapshot the algorithm consumed
  (`min`/`max`/`min_flex`/`max_flex` are the **used** replacement values). Each
  value dict additionally carries `overall_min`, `overall_max`, `held`,
  `calculated_min`, `calculated_max`, `calculated_min_flex`,
  `calculated_max_flex`. `selection_report.py` reads `min`/`max`/
  `percentage_target` and ignores extra keys, so its report for a replacement
  run correctly describes the replacement targets.
- `settings_used["replacement"] = {"number_to_select_overall": N,
  "held_total": H, "calculated_number": N-H, "number_to_select_used": n,
  "edited": true/false}`.

> **D4 — storage.** Use the existing JSON columns as described: extend the
> `targets_used` snapshot per value, and add a `replacement` block to
> `settings_used`. A dedicated `targets_calculated` column (one Alembic
> migration) was considered and rejected: the calculated and used values are
> the same rows and belong side by side, and the read pattern is unknown until
> a later story displays them. **No migration in this story.**

### 2.7 Blueprint: `entrypoints/blueprints/db_selection_backoffice.py`

One new route, `@login_required` + `@require_assembly_management`; the rest is reuse:

| Route | Method | Does |
|---|---|---|
| *(none — see D5)* | GET | The dialog opens via `?replacement_modal=open` on `gsheets.view_assembly_selection`, which calls `build_replacement_plan` for a csv assembly |
| `/assembly/<id>/selection/db/replacement/run` | POST | Parses the form → `ReplacementTargetsEdit`; `validate_replacement_targets`; on failure re-render the page with the dialog open, errors and the posted numbers kept (mirrors `save_db_settings`); on success `start_db_replace_task` and redirect to `gsheets.view_assembly_selection?current_selection=<task_id>` |
| (none) | — | Progress, cancel and downloads reuse the existing `db/modal-progress`, `db/<run>/cancel`, `db/<run>/download/*` routes |

> **D5 — how the dialog opens.** Two ways that both exist on this page:
> (a) query param on the selection page, `?replacement_modal=open`, like the
> gsheet card, with `view_assembly_selection` calling `build_replacement_plan`
> when the param is present and the source is csv; or (b) a dedicated GET route
> that renders the same page. (a) keeps one page route and the URL convention
> the gsheet flow and BDD steps already use; (b) keeps `view_assembly_selection`
> (already long) from growing. I recommend **(a)** with the plan-building
> pulled into a small helper next to `_get_replacement_modal_context`, and
> the POST living in `db_selection_backoffice.py`. The HTMX partial-modal
> pattern from the targets/registration pages would also work, but the
> selection page's other modals are all query-param driven and mixing styles
> on one page is worse than either.
>
> **D5: (a).** The dialog opens on `?replacement_modal=open`; for a csv
> assembly `view_assembly_selection` builds the plan via a helper
> `_get_db_replacement_context` beside the gsheet one, and renders
> `db_replacement_modal.html` instead of `replacement_modal.html`. The
> dedicated GET route in the table above is therefore **not** built.

`view_assembly_selection` also gains `replacement_enabled` for the card:
`data_source == "csv" and csv_selected_count > 0 and not
active_initial_selection_run_id`.

### 2.8 Form parsing

Not a WTForms form: the number of inputs depends on the targets. Field names
are `min-<value_id>` and `max-<value_id>` (the `TargetValue.value_id` UUIDs
the plan rows carry) plus `number_to_select`. Parsing lives in the service
module (`parse_replacement_form(form: Mapping[str, str], plan) ->
ReplacementTargetsEdit | errors`) so it is unit-testable; the route only
shuffles request data in and errors out. Missing or non-integer cells are
errors, not defaults.

---

## 3. The dialog

Template: `templates/backoffice/components/db_replacement_modal.html`, opened
by the `modal()` Alpine component exactly as `edit_number_to_select_modal.html`
is (closing navigates to the plain selection URL). One state.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Replacement Selection                                            [X] │
├──────────────────────────────────────────────────────────────────────┤
│ 12 people are selected or confirmed. The assembly needs 20, so       │
│ 8 places are to be filled.                                           │
│                                                                      │
│ Number of replacements to select   [ 8 ]   (between 6 and 9)         │
│                                                                      │
│ ⚠ Age · 51+ needs at least 2 more, but only 1 eligible person with   │
│   that value remains in the pool.                                    │
│                                                                      │
│ ┃ Warning: 8 places are to be filled, but the replacement targets    │
│ ┃ only allow between 6 and 7. Edit the targets below so that 8 is    │
│ ┃ within the range, or the assembly will be short.     (D8, if hit)  │
│                                                                      │
│ Replacement targets                                                  │
│ Values still to fill are calculated from the targets and who already │
│ holds a place. Edit the minimum and maximum if you need to.          │
│                                                                      │
│ ▾ Gender                                                             │
│   Value    Target   Holding   Still needed          In pool          │
│   Female   10–12    6         min [ 4 ]  max [ 6 ]   31              │
│   Male     8–10     6         min [ 2 ]  max [ 4 ]   27              │
│ ▾ Age                                     (1 value short — expanded) │
│   18–30    6–8      4         min [ 2 ]  max [ 4 ]   14              │
│   31–50    8–10     6         min [ 2 ]  max [ 4 ]   18              │
│   51+      4–6      2         min [ 2 ]  max [ 4 ]    1   ⚠ short    │
│ ▸ Region                                            (all fine)       │
│                                                                      │
│ ⚠ The edited targets cannot all be met at once: Gender needs at      │
│   least 6 but Age allows at most 5.            (shown after a POST)  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                   [ Cancel ]  [ Run Replacement Selection ] │
└──────────────────────────────────────────────────────────────────────┘
```

Design notes:

- **Not overwhelming.** Each category is a `<details>` block. Categories with
  any shortfall (or `held > max`) render open; the rest closed with a one-line
  summary ("all values can be met"). Every cell is still there for the
  organiser who wants it. This answers the "maybe in scope" question without
  hiding anything.
- **Highlighting.** A row with `shortfall > 0` gets the error colour and a
  "short by N" note; a row where `available == calculated.min` or
  `available - calculated.min <= 1` gets the warning colour ("no spare"). Uses
  the existing `--color-error-*` / `--color-warning-*` tokens, no new CSS.
- **Accessibility.** Inputs get `<label>`s (visually hidden, "Minimum for
  Gender: Female"); the shortfall note is text, not colour alone; `<details>`
  is keyboard-native. Read `docs/agent/component_accessibility.md` before
  building.
- **No JS beyond the modal open/close.** The numbers are server-rendered; edits
  are plain inputs; validation is on POST. **D6:** no live recomputation of
  `min_select`/`max_select` as the user types. It would be doable with a
  small Alpine component but duplicates the library's rule in JS; the POST
  round-trip with errors beside the cells is the feedback loop.

- **Copy** follows `docs/language.md`: the people are "replacements", the
  process is "replacement selection", the run button is "Run Replacement
  Selection" (the glossary names that button explicitly). The card button
  that opens the dialog: "Go to Replacement Selection", matching the gsheet
  card.

> **D7 — button wording.** Follow `docs/language.md`. The story's "Start
> replacements" and the request's "Run Replacements" are not used: the
> glossary names the button "Run Replacement Selection" and warns against
> "replacements" for the process. Card button: "Go to Replacement Selection"
> (same as the gsheet card). Dialog run button: "Run Replacement Selection".
> `docs/language.md` is not touched.

> **D8 — default number.** The gsheet dialog defaults the number to the
> minimum. Here the default is `calculated_number` (seats to fill), with the
> `[min_select, max_select]` range shown beside the input. **If
> `calculated_number` falls outside that range, the dialog shows a prominent
> warning** (an `alert(variant="warning")` block above the targets, not just
> hint text): it names the number of places to fill, the range the
> replacement targets allow, and says the targets need editing so the two
> agree. The input is then pre-filled with the nearest end of the range so the
> form still submits, but the organiser has been told plainly that the
> assembly will end up short (or over) unless they change the targets. The
> mockup in §3 gains this block; the component tests in §6 cover it.

---

## 4. Validation and failure modes

### 4.1 When can the dialog open?

- `data_source == "csv"`, `csv_settings_confirmed`, and at least one respondent
  is not in the pool. Otherwise the card explains why (mirrors the initial
  selection card's states).
- An initial or replacement DB run in progress → card shows "View Running
  Selection" instead (same as today for initial).

### 4.2 On POST, before dispatching

1. Structural: every cell is an integer ≥ 0, `max ≥ min`. Per-cell errors.
2. Number: integer ≥ 1.
3. Build a `FeatureCollection` from the edited numbers via the adapter
   override and run:
   - `report_min_max_error_details_structured` — cross-category impossibility
     → top-level error naming the categories.
   - `check_desired(features, number)` → "number must be between X and Y".
   - `check_people_per_feature_value(features, pool_people)` → the library's
     own "not enough people" check. This needs the pool `People` object, which
     `check_db_selection_data` already loads synchronously in a request, so
     the cost is known and acceptable.
4. All three blocking. A value the pool cannot fill would fail the task
   seconds later with a less helpful message, so refusing here is kinder.

> **D9 — block on pool shortfall.** All three checks in 4.2 block the POST.
> The library would refuse anyway (`check_enough_people_for_every_feature_value`
> uses `min`, not `min_flex`), so letting the task start only moves the same
> failure somewhere less helpful. The organiser lowers the min in the cell
> and re-submits.

### 4.3 Behaviour if targets change between GET and POST

The POST recomputes the plan and validates the submitted numbers against it.
If a value id in the form no longer exists (someone edited targets in another
tab) → top-level error "targets changed, review again" and re-render.

---

## 5. Files touched

| File | Change |
|---|---|
| `src/opendlp/domain/targets.py` | `ReplacementMinMax`, `replacement_min_max()` |
| `src/opendlp/domain/value_objects.py` | `SELECT_REPLACEMENT_FROM_DB` + label |
| `src/opendlp/service_layer/replacement_targets.py` | **new** — plan, parse, validate |
| `src/opendlp/service_layer/dashboard_stats.py` | move `_matching_attribute` to a shared spot (D2) |
| `src/opendlp/service_layer/sortition.py` | `start_db_replace_task`, widen the "active DB run" lookup |
| `src/opendlp/adapters/sortition_data_adapter.py` | `targets_snapshot` override, real `read_already_selected_data` |
| `src/opendlp/entrypoints/celery/tasks.py` | `targets_snapshot` through `run_select_from_db` / `_internal_load_db`; pass `already_selected` |
| `src/opendlp/entrypoints/blueprints/db_selection_backoffice.py` | `start_db_replacement` POST |
| `src/opendlp/entrypoints/blueprints/gsheets.py` | open the DB dialog on `replacement_modal=open` for csv; `replacement_enabled` |
| `templates/backoffice/assembly_selection.html` | live Replacement card for csv; include the new modal |
| `templates/backoffice/components/db_replacement_modal.html` | **new** |
| `tests/fakes.py` | nothing expected — the fake respondent repo already has both count queries |
| `docs/background_tasks.md` / `docs/architecture.md` | describe the replacement run and the new service |
| translations | `just translate-regen` after the strings land |

No Alembic migration (D4).

---

## 6. Tests

Following `docs/testing.md` and the component-first pattern
(`tests/component/test_db_selection_backoffice.py` is the model).

**Unit**

- `tests/unit/domain/test_targets.py`: `replacement_min_max` — normal, `held >
  max`, `held > min` only, flex clamping, unset `max_flex` stays unset.
- `tests/unit/test_replacement_targets.py` (FakeUnitOfWork, real services to
  seed): plan numbers for a small assembly with SELECTED / CONFIRMED /
  WITHDRAWN / ineligible / unmatched-category respondents; form parsing
  (missing cell, non-integer, unknown value id); validation for each of the
  three library checks.
- `tests/unit/test_sortition_data_adapter.py`: targets override yields the
  snapshot rows; already-selected feed yields SELECTED+CONFIRMED only, with
  the people headers.
- `tests/unit/test_sortition_service.py`: `start_db_replace_task` record
  fields (`task_type`, `targets_used` extras, `settings_used["replacement"]`),
  refuses while a run is active, refuses `number < 1`.

**Component** (`tests/component/test_db_selection_backoffice.py` or a sibling
`test_db_replacement_backoffice.py`)

- Card disabled with no selected respondents; enabled after a selection.
- Dialog renders calculated numbers, opens the short category, closes the
  fine one, shows the shortfall note.
- POST with bad cell → 200 re-render, error beside the cell, values kept.
- POST with cross-category impossibility → top-level error.
- POST valid → Celery `delay` patched, redirect to `?current_selection=<id>`,
  run record has the right type and snapshot.
- Auth: anonymous → login redirect; read-only role → 403/redirect.

**Integration** (postgres)

- `tests/integration/test_sortition_db_task.py`: `run_select_from_db` with a
  `targets_snapshot` end to end: withdrawn seats get filled, previously
  SELECTED people untouched, new people carry the new `selection_run_id`,
  a household of a still-selected person is not picked when
  `check_same_address` is on.
- `tests/integration/test_sortition_data_adapter.py`: already-selected feed
  over real SQL.

**E2E** (1–2 PG smokes with real CSRF, `tests/e2e/test_db_selection_backoffice.py`)

- POST run with `delay` patched; GET the page with the dialog open.

**BDD** — there is no BDD coverage of the DB selection flow today
(`features/replacement-selection.feature` is gsheet-only). Add
`features/db-replacement-selection.feature` with two scenarios: open the
dialog and see the calculated targets; run and reach the progress modal. Needs
a Celery worker in the BDD environment, which `just test-bdd` already
provides for the gsheet scenarios.

**JS** — none needed (D6).

---

## 7. Sequencing

Each chunk is a green `just check && just test-nobdd` and a commit.

1. **Domain + adapter.** `replacement_min_max`; adapter override and
   already-selected feed; unit + integration tests. — **Done**
2. **Task + starter.** `targets_snapshot` through the task; `already_selected`
   wired; new task type; `start_db_replace_task`; unit + integration. — **Done**
3. **Plan service.** `build_replacement_plan`, parse, validate; unit tests. — **Done**
4. **Dialog + routes.** Template, card, GET/POST wiring;
   component + e2e tests; translations regenerated. — **Done**
5. **BDD.** Feature file and steps; run `just test-bdd-headless` after
   `just test-nobdd`, never concurrently. — **Done**
6. **Docs.** `background_tasks.md` and `architecture.md` describe the
   replacement run; `testing.md` needed nothing (the new BDD feature follows
   its existing instructions). — **Done**; move this plan to
   `docs/agent/history/` when merged.

Estimated size: chunks 1–3 are mostly service code with clear tests; chunk 4
is where the review effort goes (accessibility, copy, translations).

---

## 8. Out of scope, restated so nobody drifts

- Showing replacement targets on the Targets tab.
- Editing the overall targets from this dialog.
- A test-mode replacement run.
- ~~"Accept all suggestions" from the algorithm.~~ Now in scope: see §10.
- Any history/detail view of past replacement rounds beyond what the run
  history table and selection report already show (the data is recorded, §2.6).

---

## 9. Decisions

Answered by Doctor Chewie on 2026-09-24. Each is also recorded inline at the
point it applies.

| # | Decision |
|---|---|
| D1 | Keep flex; subtract `held` from its bounds, clamped. Flex is unused today but may be later |
| D2 | Use the dashboard's loose category ↔ column matching, shared not copied. Reconciling the three matching rules is later work |
| D3 | Same-address exclusion covers households of SELECTED/CONFIRMED only. A withdrawn person's housemate is eligible |
| D4 | Record calculated targets inside the existing `targets_used` / `settings_used` JSON. No migration |
| D5 | Dialog opens via `?replacement_modal=open` on the selection page; only the POST is a new route |
| D6 | No live recomputation in JS; validation feedback comes from the POST re-render |
| D7 | Wording follows `docs/language.md`: "Go to Replacement Selection" on the card, "Run Replacement Selection" in the dialog |
| D8 | Default number is `calculated_number`; if it falls outside the allowed range, show a prominent warning and pre-fill the nearest bound |
| D9 | Pool shortfall, cross-category conflict and out-of-range number all block the POST |

---

## 10. Feasibility check and suggestions in the dialog

Added 2026-09-25. The pool can have enough people for every value on its own
and the targets still be impossible to meet together. The selection algorithm
detects this and proposes a minimal relaxation, which the Targets page already
shows via `check_targets_detailed()` and `_run_feasibility_check()` in
`service_layer/target_checking.py`. This round brings the same check into the
replacement dialog, with the suggestions placed next to the cells they concern
and buttons to accept them.

### 10.1 Decisions

| # | Decision |
|---|---|
| D10 | The check sees the pool the run will see: people sharing an address with someone SELECTED/CONFIRMED are dropped first, via the library's `exclude_matching_selected_addresses` and the adapter's already-selected feed |
| D11 | Two buttons in the footer: "Recheck feasibility" and "Run Replacement Selection". Running does **not** block on infeasibility; some people need to see the run fail to believe it. Revisit after user testing |
| D12 | The check runs synchronously in the request, as the Targets page does. No HTMX deferral |
| D13 | On opening the dialog, the check uses the calculated targets and the default number. On recheck it uses the numbers in the form, including the edited number to select |
| D14 | Flex is only settable by CSV upload today, so `InfeasibleQuotasCantRelaxError` is caught and shown as a plain message with no suggestions. Revisit once flex has a UI |
| D15 | Accepting a suggestion writes it into the input client-side; the suggestion hides once the input matches it. Nothing is re-checked until the organiser presses recheck or run |
| D16 | A list of every suggestion, with "Accept all", sits in the alert at the top of the dialog, above the category tables |

### 10.2 Service: `service_layer/replacement_targets.py`

- New dataclass `ReplacementSuggestion(value_id, field, current, suggested)`
  where `field` is `"min"` or `"max"`. Its `input_id` property returns the
  matching cell id (`min-<value_id>` / `max-<value_id>`) so the template and the
  accept buttons share one name for the input.
- New dataclass `FeasibilityResult(checked: bool, feasible: bool, message: str,
  suggestions: list[ReplacementSuggestion])`. `checked` is false when a
  structural error stopped the check before the solver ran. `message` carries
  the translated library error when no relaxation exists (D14), or the
  library's other failure text.
- `ReplacementValidation` gains `feasibility: FeasibilityResult | None`.
- `validate_replacement_form(...)` gains a keyword `check_feasibility: bool`.
  After the existing structured checks pass, it loads the already-selected
  people through the adapter, drops their housemates from the pool with
  `exclude_matching_selected_addresses`, and calls
  `setup_committee_generation` with the submitted number (D13). It maps
  `InfeasibleQuotasError.features` to suggestions by comparing against the
  loaded features, the same comparison `_annotations_from_infeasible_quotas`
  makes, but keyed by value id through `_row_by_name`. It reuses
  `setup_committee_generation` directly rather than `_run_feasibility_check`
  because that helper writes into the Targets page's annotation shape.
- New `check_replacement_plan(uow, user_id, assembly_id, plan)` builds the
  form the dialog would submit unedited (calculated min/max, default number)
  and runs `validate_replacement_form` with the check on. This is what the GET
  path calls (D13) so open and recheck share one code path.
- A per-value pool shortfall does not stop the solver: the relaxation is how
  to get past it, so the cell error and the suggestion show together, as on
  the Targets page. Only errors the library itself refuses (bad cells, a
  cross-category conflict) stop it. A pool smaller than the number to select
  gets a plain message instead of the library's flex text, since no committee
  exists whatever the targets.

### 10.3 Blueprint

- `gsheets.render_selection_page` runs `check_replacement_plan` when it opens
  the dialog with no submitted form, and passes the result as
  `replacement_validation` so the template has one place to look.
- `db_selection_backoffice.start_db_replacement` reads a `action` form field.
  `recheck` re-renders the page with the form kept and
  `check_feasibility=True`; anything else keeps today's behaviour (validate
  without the solver, then start the task). Two submit buttons on one form,
  each with `name="action"`, is the plain HTML way to do this; no JS.
- The recheck response is a normal 200 render, the same as a rejected run.

### 10.4 Template: `components/db_replacement_modal.html`

- Top alert (D16): when `feasibility.suggestions` is non-empty, an error alert
  reads "The targets cannot all be met from the pool. The algorithm suggests
  these changes:" followed by one line per suggestion ("<category>: <value>,
  minimum 3 → 2") each with its own "Accept" button, and an "Accept all"
  button under the list. When the check ran and passed, a short success line
  ("These targets can be met from the pool.") so the organiser knows it
  happened. When `message` is set, an error alert with that text.
- Beside the cell: the row's notes column shows the suggestion with an
  "Accept" button, using the same colour treatment the Targets page gives
  suggestions. The category `<details>` opens when it holds a suggestion.
- Footer: "Recheck feasibility" (secondary, `name="action" value="recheck"`)
  and "Run Replacement Selection" (primary, `value="run"`).
- Alpine: a registered `replacementSuggestions` component on the form. Each
  accept button carries `data-input` and `data-value`; the click handler reads
  `$el.dataset`, sets the input's value and dispatches `input` so Alpine state
  follows. "Accept all" iterates every `[data-input]` button. Each suggestion
  element is `x-show`n while the input's value differs from the suggested one
  (D15), tracked in a flat object keyed by input id to stay CSP-safe. Follows
  the patterns in `templates/backoffice/patterns.html`.

### 10.5 Tests

- Unit (`tests/unit/test_replacement_targets.py`): feasible pool → checked,
  feasible, no suggestions; infeasible pool → suggestions keyed to the right
  value ids and fields with the relaxed numbers; housemate of a selected person
  is excluded before the check (a pool that is feasible only if the housemate
  counts must come back infeasible); no relaxation within flex → message and
  no suggestions; structural error → `checked` false.
- Component (`tests/component/test_db_replacement_backoffice.py`): opening the
  dialog shows the suggestion list and per-cell suggestions on an infeasible
  fixture; recheck keeps edited numbers and re-runs; run with `action=run` on
  infeasible targets still starts the task (D11).
- JS (`vitest`): the accept and accept-all handlers set the inputs and the
  hidden state, per `docs/agent/frontend_js_testing.md`.
- BDD (`features/db-replacement-selection.feature`): one scenario opening the
  dialog on an infeasible pool, accepting all, rechecking, and seeing the
  success line.

### 10.6 Sequencing

1. Service: suggestion dataclasses, feasibility in the validator, plan check.
   Unit tests. **Done.**
2. Blueprint and template, without the accept buttons. Component tests. **Done.**
3. Accept / accept all in Alpine, with JS tests. BDD scenario. **Done.**
4. Docs and translations. **Done.**
