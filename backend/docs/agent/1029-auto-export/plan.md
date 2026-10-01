# 1029 — Auto-export respondents to Google Sheets

Status: **implemented on branch `1029-auto-export`** (2026-09-30). Every step in
[Order of work](#11-order-of-work) is done and committed. Doctor Chewie's
answers from the review rounds are folded into the design below and recorded in
[Decisions](#decisions). Departures from the plan are listed in
[As built](#as-built).

## Goal

An organiser ticks "Automatically export" when exporting respondents to Google
Sheets. From then on the sheet is rewritten, in a Celery task, whenever a
respondent of that assembly is created or changed, or the respondent schema
changes. Failures of the background export are retried a few times, then logged
only (for now). The initial export is done in the request, as today, and must
succeed for auto-export to be switched on.

## What exists today

| Piece | Where | Notes |
| --- | --- | --- |
| Saved export target | `domain/assembly_export_gsheet.py`, table `assembly_export_gsheets` | One row per assembly per `GSheetExportKind`. Holds `url`, `worksheet_name`, `spreadsheet_title`, `worksheet_url`. |
| Export service | `service_layer/respondent_export_service.py` | `export_respondents_to_gsheet()` writes, then saves the config via `save_export_gsheet_config()`. Both public functions are permission-gated on a `user_id`. |
| Config save | `service_layer/export_gsheet_config.py` | Shared with the dashboard export. Commits. |
| Target | `adapters/gsheet_export.py` `GSheetExportTarget` | `clear()` then `update()` of the whole tab. 20s gspread timeout, chosen for web requests. Raises `ExportTargetError`. |
| Route + flow | `blueprints/respondents.py` `run_export` / `_run_gsheet_export`, `entrypoints/gsheet_export_flow.py` | Target built by `app.extensions["gsheet_export_target_factory"]` so tests can fake it. |
| Modal | `templates/backoffice/respondents/export_modal.html`, `components/gsheet_export_fields.html` | The fields macro is shared with the dashboard export modal. |
| Page link | `templates/backoffice/assembly_respondents.html` | "Exported to Google Sheets <link>" next to the heading. |
| Celery | `entrypoints/celery/tasks.py`, `app.py` | Tasks open their own uow via `bootstrap(session_factory=...)`. The service layer already dispatches tasks (`service_layer/sortition.py` calls `tasks.x.delay`). Tests patch `.delay`. |
| Redis from services | e.g. `service_layer/csv_upload_stash.py` | `RedisCfg.from_env().create_client()`, with an injectable `redis_client` for tests. |

Three facts that shape the design:

1. **The status filter is not saved.** A manual export picks a filter ("All",
   "Selected or confirmed", ...) per export. Auto-export saves the one chosen
   when it was enabled and reuses it (D1).
2. **The transaction commits when the entrypoint's `with uow:` exits**, not
   inside the service. A task dispatched from a service with no delay can run
   before the commit and export stale data.
3. **Every export is a full rewrite of the tab**, several Google API calls. A
   burst of registrations (a mailing lands, 200 people sign up in ten minutes)
   must not become 200 rewrites — Google's quota is 60 write requests per minute
   per service account, and that account is shared by every assembly on the
   install, including selection runs. So exports are debounced to at most one
   per 30 seconds per assembly (D3).

## Proposed design

### 1. Data model

Add to `AssemblyExportGSheet` and `assembly_export_gsheets`:

- `auto_export: bool = False` (column `Boolean, nullable=False, server_default false`)
- `auto_export_status_filter: str = ""` — the UI filter token (`""`/`all`,
  `selected_or_confirmed`, `POOL`, ...) as accepted by `resolve_status_filter()`.
  Stored as the token rather than a list of statuses so that
  `selected_or_confirmed` survives as one thing, and the modal can pre-select it.

Alembic migration via `uv run alembic revision --autogenerate`. No new table, so
no change to the test-data delete functions.

The columns sit on the shared table, so the dashboard kind gets them too and
ignores them. `save_export_gsheet_config()` gains keyword arguments for the two
fields, defaulting to "leave unchanged", so the dashboard export's call is
untouched.

### 2. Turning it on (the initial export)

- `gsheet_export_fields` macro is shared with the dashboard modal, so the
  checkbox goes in `export_modal.html` itself, inside the
  `destination === 'gsheet'` block: **"Automatically export when respondents
  change"**. Hint text: the tab is rewritten on every change, with the status
  filter chosen above, and anything typed into that tab is lost — notes belong
  in another tab. Pre-ticked from the saved config, and the status dropdown
  pre-selects the saved filter when auto-export is on.
- `run_export` reads `auto_export` from the form and passes it, with the raw
  status token, to `export_respondents_to_gsheet(..., auto_export=bool,
  status_filter_token=str)`.
- The service writes first and saves the config second, exactly as now. So a
  failed initial export saves nothing and auto-export stays as it was — this is
  the "initial export must succeed" rule, and it falls out of the existing
  ordering.
- Success flash differs when enabled: "Respondents exported to Google Sheets.
  The tab will now update automatically."
- Respondents page: the existing link line reads "Automatically exported to
  Google Sheets <link>" when `auto_export` is on.
- A CSV download from the same modal does not touch the saved config, so it
  leaves auto-export alone (D2).

### 3. Turning it off

A **"Stop automatic export"** button (design-system `button()` macro,
secondary variant, in a small POST form with the CSRF token) beside the link on
the respondents page, shown only while auto-export is on. It posts to
`POST /assembly/<id>/respondents/export/auto/stop`, which calls a manage-gated
`disable_auto_export(uow, user_id, assembly_id)` in
`respondent_export_service.py`. That clears `auto_export` and nothing else: the
URL, tab and last-export link stay, so the next manual export pre-fills as
before. No Google call is made, so it works when the sheet is the thing that is
broken (D2). Flash: "Automatic export stopped."

Any export already queued when the button is pressed re-reads the config at run
time and does nothing (section 5).

### 4. Requesting an export (the trigger)

New module `service_layer/respondent_auto_export.py`:

```python
AUTO_EXPORT_DELAY_SECONDS = 30

def request_auto_export(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> None:
```

- Looks up the config; returns if there is none or `auto_export` is off.
- Debounces through Redis: `SET auto_export_pending:<assembly_id> 1 NX EX <ttl>`.
  If the key was already set, an export is already scheduled — return.
- Otherwise calls
  `tasks.auto_export_respondents.apply_async(kwargs={"assembly_id": ...}, countdown=AUTO_EXPORT_DELAY_SECONDS)`.
- **Never raises.** Redis or broker trouble is logged (`structlog`, `assembly_id`
  only) and swallowed, with the explanatory comment the code-quality rules
  require. A failed side effect must not fail a registration.

The countdown does two jobs: it collects a burst of changes into one export, and
it lets the caller's transaction commit before the task reads. If the caller
rolls back, the task exports unchanged data — wasteful, harmless.

The task deletes the pending key **before** it reads the database, so a change
that lands mid-export schedules a follow-up rather than being lost.

Under continuous load this gives at most one export every ~30 seconds per
assembly (each export deletes the pending key on start; the next change re-arms
a 30s countdown). That is the accepted rate (D3); there is deliberately no
second per-assembly rate limit on top of the debounce.

### 5. The task

`entrypoints/celery/tasks.py`:

```python
@app.task(
    bind=True,
    autoretry_for=(ExportTargetError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def auto_export_respondents(self, assembly_id, session_factory=None, target_factory=None) -> bool:
```

- No `SelectionRunRecord`, no `_on_task_failure` — those belong to selection runs.
- Takes a per-assembly Redis lock (`redis.lock("auto_export_lock:<id>",
  timeout=<a few minutes>)`, non-blocking) so two exports of one assembly cannot
  interleave their writes. If the lock is held, re-request (pending key +
  countdown) and return `False`.
- Deletes the pending key, then opens
  `with bootstrap(session_factory=...) as uow:` and calls a new service
  function `run_auto_export(uow, assembly_id, target_factory)` which:
  - re-reads the config and returns `False` if auto-export has been switched
    off since the task was queued;
  - resolves the saved status filter token with `resolve_status_filter()`;
  - builds the target from the saved URL and calls the existing `_write_export()`
    with the saved worksheet name;
  - updates `spreadsheet_title` / `worksheet_url` / `updated_at` on success and
    commits.
- `run_auto_export` is **not** permission-gated: there is no acting user when a
  member of the public registers. Authority comes from the organiser who
  enabled it, who had manage permission at that moment. The function is named
  and documented so that it is not reachable from a route.
- **Retries (D4):** `ExportTargetError` propagates out of the task so Celery's
  `autoretry_for` handles it: up to 3 retries with exponential backoff (1s, 2s,
  4s before jitter, capped at 600s) — enough to ride out a Google 429 or a
  blip, cheap when the failure is permanent. Each attempt logs a warning with
  `assembly_id`, `attempt=self.request.retries` and `error=str(e)`; the final
  failure logs at error level. No PII — the error text comes from gspread and
  names the sheet, not people. Anything that is not an `ExportTargetError` is
  a bug, not a Google problem: it is logged with `logger.exception` and not
  retried. Switching auto-export off after repeated permanent failures is
  **out of scope** for this round; noted in `docs/background_tasks.md` as a
  follow-up.
- The Celery-side target uses a longer gspread timeout than the web's 20s (a
  constructor argument on `GSheetExportTarget`, default unchanged).

### 6. Write first, then trim (D6)

`GSheetExportTarget.write_sheet()` changes from clear-then-update to:

1. `worksheet.update([headers, *rows])` over the old data;
2. `worksheet.batch_clear([...])` for the two ranges beyond the new data — the
   rows below it (`A{n+1}:{last_col}{row_count}`) and the columns to its right
   (`{col+1}1:{col_count}{n}`) — using the worksheet's `row_count`/`col_count`,
   and skipping a range when there is nothing beyond.

The tab is never empty, and a failure between the two calls leaves old rows
below new data rather than nothing at all. This applies to the manual
respondent export and the dashboard export as well, which is wanted. The
existing limitation that data larger than the grid (1000×26 for a fresh tab)
fails is unchanged and out of scope — it is the same before and after.

Existing adapter unit tests are updated to assert the new call sequence.

### 7. Where `request_auto_export` is called

Called from the service layer, next to the write, so a new entrypoint cannot
forget it. Inventory of everything that changes what the sheet would contain:

| Change | Function | Trigger? |
| --- | --- | --- |
| Registration form submission | `registration_submission_service._create_and_save_respondent` | yes (covers test submissions too) |
| Create respondent | `respondent_service.create_respondent` | yes |
| Edit respondent | `respondent_service.update_respondent` | yes |
| Status change (select, confirm, withdraw...) | `respondent_service.transition_respondent_status` | yes |
| Delete one respondent | `respondent_service.delete_respondent` | yes |
| CSV import | `respondent_service.import_respondents_from_rows` | yes |
| Reset selection status | `respondent_service.reset_selection_status` | yes |
| Delete all respondents | `assembly_service.delete_respondents_for_assembly` | yes |
| Selection run writes results | `tasks._internal_write_db_results` (`bulk_mark_as_selected`) | yes |
| Replacement selection (447, unmerged) | same path | yes, once 447 lands — check then (D7) |
| Derived field recompute | `derivation_service.recompute_derived_field` | yes |
| Field renamed / deleted | `respondent_field_schema_service.rename_derived_field`, `delete_field`, `delete_derived_field` | yes — headers change |
| Field added / edited / reordered | `respondent_field_schema_service.add_field`, `update_field`, `reorder_group`, `apply_reconciliation`, `update_schema_from_headers`, `populate_schema_from_headers` | yes (D5) — column order and headers |
| Choice options changed | `add_choice_option`, `update_choice_option`, `remove_choice_option` | yes — `update_choice_option` and `remove_choice_option` rewrite respondent values; `add_choice_option` does not, but one rule for the three is easier to keep than two |
| Comment added | `respondent_service.add_respondent_comment` | no — comments are not exported |

I will re-grep for writers at implementation time; this list is from one pass.

**Domain events (D8).** This is a cross-cutting after-commit side effect
sprinkled by hand into a dozen services, which is exactly what the domain
events + message bus pattern in *Architecture Patterns with Python* exists for,
and Chewie plans to add that machinery before long. Until then:

- `request_auto_export` and each call site carry a one-line comment naming it
  as a candidate for a `RespondentsChanged` event;
- `docs/architecture.md` gets a short subsection under *The UnitOfWork
  convention* listing this as the first known after-commit side effect, so the
  event work has a worked example to start from;
- the function is kept to a single entry point with a single argument, so the
  future event handler can replace the call sites mechanically.

### 8. Personal data

The sheet is a copy of personal data outside our database, which already exists
with manual export. Auto-export improves the erasure story for it: deleting a
respondent rewrites the sheet without them. The pending and lock Redis keys
hold an assembly UUID only. No new cookies, scripts or logs of PII.
`docs/personal-data.md` gets a short paragraph.

### 9. Tests

| Level | What |
| --- | --- |
| Unit | Domain: new fields, `update_values`. `request_auto_export` with fake uow + fake redis + patched `apply_async`: off → nothing; on → one dispatch with a 30s countdown; second call while pending → none; Redis error → swallowed and logged. `run_auto_export` with fake target: writes with saved filter and tab; disabled-since-queued → no write; `ExportTargetError` propagates. `GSheetExportTarget`: update-then-trim call sequence, including "nothing to trim". `disable_auto_export`: clears the flag only, permission-gated. |
| Contract | Repo round-trips the new columns. |
| Integration | The task against Postgres with a fake target factory: respondent added → table written; lock held → re-requested, no write; failing target → retried the configured number of times, then logged (Celery eager mode or direct `.retry` assertion, whichever the existing suite supports). One test per trigger site asserting `request_auto_export` fires. Migration up/down. |
| E2E | Modal POST with the checkbox: config saved with `auto_export=True` and the chosen filter token; failing target → not enabled; unticked → disabled; CSV download → config unchanged. Stop button → flag cleared, no target built. Registration POST on an auto-export assembly dispatches the task (patched). |
| BDD | Organiser enables auto-export, sees the "Automatically exported" line and the stop button; presses stop and both revert. |

Log assertions capture the expected warnings so test output stays pristine.

### 10. Docs and translations

- `docs/background_tasks.md`: new task section, including the retry policy and
  the "switch off after repeated failure" follow-up.
- `docs/architecture.md`: the domain-events note (section 7).
- `docs/personal-data.md`: paragraph as above.
- `docs/language.md` check for the new strings; `just translate-regen` and
  `just translate-check`.

### 11. Order of work

Branch `1029-auto-export` from `main` (D7).

1. [x] Domain fields, ORM column, migration, contract test.
2. [x] `GSheetExportTarget` write-then-trim; adapter unit tests.
3. [x] `save_export_gsheet_config` + `export_respondents_to_gsheet` accept the flag and filter token; `disable_auto_export`; unit tests.
4. [x] Modal checkbox, route, stop route and button, page link text; component + e2e tests.
5. [x] `run_auto_export` service + Celery task with retries and lock; unit + integration tests.
6. [x] `request_auto_export` with debounce; unit tests (same commit as 5).
7. [x] Wire the trigger sites, with a test per site.
8. [x] BDD, docs, translations, `just check`, `just test`.

Each step is a commit that leaves the suite green. Steps 1–4 give a checkbox
that records intent but does nothing, so they should not be deployed alone.

## As built

Where the code differs from the design above:

- **Ungated write helper.** `respondent_export_service.write_respondent_export()`
  is the permission-free core that both `export_respondents` (manage-gated) and
  `run_auto_export` call, instead of `run_auto_export` reaching for the private
  `_write_export`.
- **Unticking the box switches auto-export off.** `export_respondents_to_gsheet`
  saves the flag as given on every Google Sheets export, so the checkbox is the
  truth each time. A CSV download does not touch it.
- **Trigger inventory.** Derived-field create/update/recompute all pass through
  `derivation_service._recompute`, so one call there covers them. In
  `target_source_service`, the derivation path triggers via `_recompute` and
  `unlink` via `delete_derived_field`; only the exact-copy path needed its own
  call. Choice-option changes (add/update/remove) all trigger.
- **BDD.** The BDD server is a separate process, so the Google write cannot be
  faked there. The scenario seeds an auto-exporting assembly directly and drives
  the status line and the stop button; the enable path is covered by component
  and e2e tests over the fake target.
- **Retry logging.** The task catches `ExportTargetError`, logs (warning per
  attempt, error on the last), and re-raises for Celery's `autoretry_for`; the
  last attempt returns `False` rather than raising, so the task result is clean.
- **Trim ranges.** `_stale_ranges()` clears the rows below the data at full
  width and the columns to its right at data height, using
  `gspread.utils.rowcol_to_a1`; nothing is cleared when the data reaches the
  grid's edge.

## Future work: run the one-off export in Celery too

Added 2026-10-01, after the 907 work on Google Sheet access errors.

### Why

The one-off export (respondents modal, and the dashboard export that shares
`gsheet_export_flow.py`) still writes to Google inside the web request. Two
things make that a worse fit than it was when this plan was written:

- **The export adapter now authenticates through the library's
  `make_gsheet_client()`** (907), which uses gspread's `BackOffHTTPClient`.
  On a 429 or a 5xx that client sleeps and retries with doubling waits of up
  to 128 seconds. The 20 second per-request timeout bounds each attempt, not
  the sleeps between them, so a Google outage or a quota squeeze can hold a
  gunicorn worker for minutes. That back-off is exactly right in a Celery
  task, where `auto_export_respondents` already layers its own retries on
  top, and exactly wrong in a request.
- **The service account's write quota is shared** across every assembly and
  every selection run on the install (see fact 3 above). A one-off export is
  the one Google write that bypasses the per-assembly Redis lock and the
  debounce, so it can interleave with an auto-export of the same sheet.

### Shape

- The modal's "Export to Google Sheets" submits as today, but the route
  dispatches a task instead of writing. The natural candidate is the existing
  `auto_export_respondents` task with the saved config as its input, which
  gets the lock, the debounce key and the retries for free. The one-off case
  differs only in that the config may not exist yet and the status filter
  comes from the form rather than the saved row, so the task (or a thin
  sibling) takes those as arguments.
- The flash becomes "Export started" and the page shows the export's state.
  The selection runs already have the pattern: a run record polled by an
  HTMX partial (`components/selection_progress_modal.html` and the
  `SelectionRunRecord` behind it). A small `ExportRunRecord` (assembly,
  kind, status, error message, result URL, timestamps) or a Redis status key
  with the same fields would do; a database row is easier to show in the
  "Exported to Google Sheets" line and to keep for the last-failure case
  noted under D4.
- **Enabling auto-export** currently relies on the initial export succeeding
  synchronously. In the async version either the flag is set only by the task
  on its first success, or it is set immediately and the status line carries
  the failure. The first keeps today's guarantee and is the recommendation.
- The error classification from 907 carries over unchanged:
  `ExportTargetError` keeps the library's `SelectionError` as `__cause__`, so
  the record's error message can be the translated not-shared, not-found,
  read-only or not-native text rather than a generic hint.

### Out of scope here

The dashboard export route shares the flow helper, so it moves at the same
time or the helper grows a flag; either way the modal copy and the "Exported
to" line need the same status treatment. None of this is needed for the
auto-export feature to ship.

## Decisions

Recorded from the first review round, 2026-09-30.

| # | Question | Decision |
| --- | --- | --- |
| D1 | Which respondents does the auto-export write? | Save the status filter chosen at the initial export and reuse it. |
| D2 | How is auto-export turned off? | A separate "Stop automatic export" button and route; no Google call. A CSV download from the modal leaves auto-export alone. |
| D3 | Debounce delay and rate | A single 30-second constant, one Redis pending key. The earlier thought of a separate once-a-minute cap per assembly was dropped to keep it simple (second round). |
| D4 | Retries | Retry with backoff, max 3 — API errors and limits do occur. Switching off after permanent failure is a later round. |
| D5 | Do schema changes trigger an export? | Yes, including add and reorder. |
| D6 | Empty-tab window | Write first, then trim; applies to all exports through the target. |
| D7 | Branch | New branch `1029-auto-export` off `main`. Add the 447 replacement trigger when 447 lands. |
| D8 | Trigger placement | Service-layer calls for now; leave comments in code and docs because domain events are planned. |
| D9 | Dependencies | None new: Celery, Redis, gspread already present. |
