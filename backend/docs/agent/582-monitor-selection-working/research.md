# Plan: end-to-end monitoring of selection (issue #582)

## Problem

A recent prod incident: a Google selection silently broke after deploy because
the service-account needed extra IAM roles. Unit/integration tests didn't catch
this — only a real run against a real Google Sheet would have. We want to
exercise the entire selection chain (Flask → DB → Celery → Redis →
sortition-algorithms → gspread → Google Drive/Sheets API) on a regular cadence
so that any broken link is visible quickly, not the next time a real organiser
tries to run a selection.

## What "the whole chain" actually is

Walking the path Doctor Chewie suggested I trace:

1. **Trigger** — caller (CLI, HTTP, scheduled task) invokes
   `start_gsheet_select_task` in `service_layer/sortition.py:134`.
2. **Record creation** — a `SelectionRunRecord` is created in PENDING and
   committed (`assembly.py:235`).
3. **Data source build** — `AssemblyGSheet.to_data_source()`
   (`assembly.py:190`) constructs a `GSheetDataSource` configured from
   `config.get_google_auth_json_path()`. This is the first thing that touches
   credentials.
4. **Celery dispatch** — `tasks.run_select.delay(...)` sends the pickled
   data-source over Redis to a worker.
5. **Worker picks it up** — `run_select` in `entrypoints/celery/tasks.py:794`,
   wrapping `_internal_load_gsheet` → `_internal_run_select` →
   `_internal_write_selected`.
6. **Sheet load** — `data_source.spreadsheet.title` is the first real Google
   API call; this is where the recent incident manifested. Failure modes
   already handled here: `SpreadsheetNotFound`, `NotNativeGoogleSheetError`,
   `PermissionError`, generic `Exception`.
7. **Stratified selection** — `run_stratification` in sortition-algorithms
   (uses HiGHS via `highspy`).
8. **Write back** — `_internal_write_selected` calls
   `select_data.output_selected_remaining`, which writes new tabs via gspread
   (this is a *different* set of API permissions — `drive.file` vs read-only
   read of metadata vs sheet edit).
9. **Status update** — `_update_selection_record` flips the record to
   COMPLETED with `completed_at`, run report and selected ids JSON-stored.

A monitor that doesn't exercise step 8 misses write-permission regressions
(real example: read works but adding tabs doesn't). So the test must do a
full run including writing the output tabs, not just a load or a `test_selection`.

## Proposed architecture

I'd structure this around **two independent triggers that share one
implementation**:

- A **service function** `run_monitoring_selection(uow) -> MonitorResult`
  that does one full selection run and returns success/failure + timing +
  message. Lives in `service_layer/monitoring.py` (new module).
- A **CLI command** `opendlp monitor run-selection` that calls it and exits
  non-zero on failure — for post-deploy gating.
- A **Celery beat job** `monitor_selection_periodic` that calls it on a
  schedule (every 30 min) and updates a small `MonitorRun` record.
- The **`/health` endpoint** consults the most recent `MonitorRun` and
  becomes unhealthy if the last success is too old or the last run failed.

This keeps "what does an end-to-end run look like?" in one place and gives
both deploy-time and continuous monitoring for free.

## Decision 1 — Assembly object in DB vs URL-only

Three options, in order of weight.

### Option A — Full Assembly fixture in the DB

A real `Assembly` + `AssemblyGSheet` + `SelectionSettings` +
`TargetCategories` row. Identified by env var `MONITOR_ASSEMBLY_ID`.

**Pros**

- **Exercises the most code.** `start_gsheet_select_task` runs unchanged,
  including permission decorators, the gsheet repository, the
  `SelectionRunRecord` write path, error_translation, the Celery serialisation
  path — exactly what users hit.
- **Tests the DB schema.** A bad migration that breaks
  `assembly_gsheets`/`selection_run_records` is caught here even when no human
  has tried to run a selection yet.
- **Reuses existing UI.** Admins can inspect the monitor's run history through
  the normal selection-run pages — useful for debugging when a run fails.
- **Reuses existing cleanup.** `cleanup_orphaned_tasks` already handles dead
  monitor runs.

**Cons**

- **Setup ceremony.** Creating the assembly is a one-off manual step (or a
  migration / management command) per environment. Forgettable.
- **Pollutes prod data.** A monitor assembly shows up in admin lists. Mitigate
  with a `MONITOR` `AssemblyStatus` or an `is_monitor` flag, or by filtering
  `assembly_id == config.MONITOR_ASSEMBLY_ID` in admin UI.
- **GDPR.** The assembly contains "respondents" — these need to be obviously
  fake (e.g. `Test Respondent 0042`) and documented as such. Not a real
  problem because they're synthetic, but worth being explicit about.
- **Permission decorator.** `start_gsheet_select_task` requires a user with
  manage permission. We'd need a dedicated `monitor` system user with a role
  on the monitor assembly.

### Option B — URL + tab names in env, no Assembly row

`MONITOR_GSHEET_URL`, `MONITOR_NUMBER_TO_SELECT` etc., and the monitor builds
a `GSheetDataSource` directly and calls `tasks.run_select.delay(...)` (or even
runs the load+select inline).

**Pros**

- Zero DB setup. New environments get monitoring just by setting env vars.
- No "weird assembly" in the UI to explain.

**Cons**

- **Bypasses the bits that broke recently.** The original incident was about
  service-account permissions — those are exercised either way — but in
  general bypassing `start_gsheet_select_task`, the repositories, and the
  permission decorator means we're not actually exercising the user-facing
  path. Future regressions in `assembly_gsheets` querying, or in the targets
  snapshot, or in `dict_for_json` would be missed.
- Diverges from the real flow over time as the real flow grows features.
- Have to reinvent SelectionRunRecord bookkeeping or skip it (then losing
  audit trail / health-check signal).

### Option C — Hybrid: real Assembly in DB, but the monitor explicitly invokes the same service function a user invokes

Same as A, with a thin wrapper `run_monitoring_selection` that:

1. Resolves the monitor user + assembly from config,
2. Calls `start_gsheet_select_task(uow, monitor_user_id, monitor_assembly_id)`,
3. Polls `get_selection_run_status` until terminal,
4. Returns success/failure.

**Pros**

- All of A's coverage benefits.
- The wrapper is tiny — no logic duplication.
- Polling is the same pattern the UI uses.

**Cons**

- Same setup cost as A.
- Polling-based — if the worker is wedged, the monitor itself looks "stuck"
  rather than "failed" until the timeout hits. Mitigate with a tight monitor
  timeout (~5 min) that's separate from the global `TASK_TIMEOUT_HOURS`.

**Recommendation: Option C.** The whole point of the exercise is to catch
regressions in the user-facing path — bypassing it defeats the purpose. The
setup cost is paid once per environment and can be a CLI command
(`opendlp monitor setup-assembly`).

## Decision 2 — Trigger mechanism

### B1 — Celery beat (already in the codebase)

Add to `app.py` `beat_schedule` next to `cleanup-orphaned-tasks`:
`monitor-selection: every 30 min`. Beat is already running in prod (it must
be, since `cleanup_orphaned_tasks` is configured there).

**Pros**: zero new infra; already-running scheduler; same observability as
other periodic tasks; fits the existing model of "celery does background
work".

**Cons**: if Celery itself is broken, the monitor never runs and the
healthcheck rightly screams — but the screaming might be ambiguous between
"Google broke" and "Celery broke". The healthcheck already independently
checks `celery_worker_running`, so this is actually fine.

### B2 — systemd timer + service unit

Doctor Chewie's original suggestion. A unit on the host that runs
`opendlp monitor run-selection` every 30 min.

**Pros**: independent of Celery — if Celery is down, the timer still runs and
the CLI command will fail clearly because the dispatched task never completes.
Useful as an extra layer.

**Cons**: more infra (service files in deploy ansible/justfile), runs the
*Flask* image in CLI mode every 30 min (memory + DB connection churn), and
inside Docker it has to be wired carefully (probably runs `docker compose
exec opendlp opendlp monitor run-selection`).

### B3 — Both

A single beat job + a systemd timer that calls a CLI command which checks
"has the beat job run successfully recently?" and bails out if not — i.e. the
timer's job is to verify the beat is firing, not to run the selection itself.

**Pros**: covers "Celery beat stopped firing" without duplicating runs.

**Cons**: complexity for a corner case the healthcheck endpoint already
covers if it's monitored.

**Recommendation: B1 (beat) for the periodic check, plus the deploy-time CLI
gate (separate concern, not really an alternative).**

## Decision 3 — Where to record success

### R1 — Reuse `SelectionRunRecord`

A monitor run is a real selection run, so it lands in the existing table. The
healthcheck queries `selection_run_records` filtered to the monitor assembly
id ordered by `created_at desc`.

**Pros**: no new table, no new migration, fits the model. Admins can already
see history via the normal selection page (a small UX win).

**Cons**: `SelectionRunRecord.log_messages` and `run_report` are heavy JSON
fields — every 30 min creates a row. With orphaned-task cleanup at 5 min and
selection at 30 min, that's ~50 rows/day. Probably fine, but consider a
periodic cleanup task that keeps the most recent 100 monitor runs.

### R2 — New `MonitorRun` table

Tiny table: `id`, `kind`, `started_at`, `completed_at`, `success`, `message`.

**Pros**: the healthcheck query is trivially fast; rows are tiny; doesn't
mix with audit-relevant user-driven runs.

**Cons**: more code; small migration; another DELETE in
`_delete_all_test_data` to remember.

**Recommendation: R1 with a periodic prune.** The reuse is genuinely valuable
for debuggability — when prod monitoring fails I want to look at the same
log_messages/run_report I'd see for a human run, not a different table.

## Decision 4 — Tab cleanup

Each gsheet selection writes new "Selected"/"Remaining" tabs. Without
cleanup, a 30-minute monitor accumulates ~50 tabs/day; gsheets has a 200-tab
soft limit and gets slow well before that.

The codebase already has `manage_old_tabs` (`tasks.py:877`) which calls
`data_source.delete_old_output_tabs(dry_run=False)` — this is the right tool.

Two strategies:

### T1 — Run delete-old-tabs as part of the same monitor cycle

After a successful selection, dispatch a `manage_old_tabs` task with
`dry_run=False` for the same gsheet. Adds one more Celery roundtrip but
exercises that code path too (also valuable — it has its own permission
requirements).

### T2 — Independent beat schedule for tab cleanup

`manage-monitor-tabs: every 6 hours`. Decoupled, runs less often, recovers
gracefully if a single run was missed.

### T3 — Use a copy-of-template strategy: each run copies a template gsheet, runs against the copy, deletes the copy

Cleanest from a "no leftover state" perspective.

**Pros**: no tab accumulation; each run starts from a known-good state, so
historical drift in the monitor sheet can't break selection.

**Cons**: exercises *more* of the Drive API surface area (copy + delete file
needs `drive.file` scope or full Drive scope on the service account) — which
is good for coverage but is also one more thing to break and a new IAM
requirement that itself needs to be set up correctly. Also the existing
codebase doesn't have copy/delete-spreadsheet helpers, so we'd need new
adapter methods.

**Recommendation: T1 + T2.** T1 keeps the working sheet tidy; T2 acts as a
safety net if T1 ever silently fails. Skip T3 — it's a lot of new code for a
problem T1 solves cheaply, and the extra Drive scope is a real ops cost.
Revisit if we ever want monitoring to also cover Drive copy/delete.

## Decision 5 — Healthcheck wiring

Extend `health.py:health_check` with a new check function:

```python
def check_monitor_selection() -> tuple[str, datetime | None, str]:
    """Returns (status, last_success_at, message)
    status: "OK" | "STALE" | "FAILED" | "NOT_CONFIGURED" | "UNKNOWN"
    """
```

- `NOT_CONFIGURED`: `MONITOR_ASSEMBLY_ID` env not set → never affects health.
- `OK`: most recent run succeeded AND last success was within
  `MONITOR_HEALTH_MAX_AGE` (default 60 min, configurable).
- `STALE`: most recent run succeeded but it's older than the threshold (beat
  isn't firing, or worker is wedged).
- `FAILED`: most recent terminal run was FAILED/CANCELLED.
- `UNKNOWN`: DB query blew up.

Add to response JSON: `monitor_selection_status`,
`monitor_selection_last_success_at`, `monitor_selection_last_run_status`,
`monitor_selection_last_error` (truncated). `STALE`/`FAILED`/`UNKNOWN` cause
the endpoint to return 500. `NOT_CONFIGURED` does not — same pattern as
`NO_MICROSOFT_OAUTH`.

## Decision 6 — Timeouts

Doctor Chewie's instinct (5 min) is right. The global
`TASK_TIMEOUT_HOURS` defaults to 24 — way too long for a monitor that's
supposed to fail loud. Two timeouts:

- **Celery task soft/hard timeout** on the dispatched `run_select` for the
  monitor: 5 min hard. Set this via `apply_async(time_limit=300,
  soft_time_limit=270)` rather than mutating the global. (Confirms Celery
  itself enforces it even if `cleanup_orphaned_tasks` is broken.)
- **Monitor wrapper polling timeout**: 6 min wall-clock in
  `run_monitoring_selection`, after which the wrapper itself returns
  `success=False, message="monitor exceeded wall-clock timeout"`.

Belt + braces; either alone could fail silently.

## Decision 7 — Dedicated gsheet shape

The monitor sheet should be:

- Small (50-ish synthetic respondents, 3-4 categories) — fast, cheap.
- Owned by the org's Google account (not a personal one).
- Shared with the prod *and* test/staging service accounts (so the same
  sheet can drive both, or use one-per-environment).
- Versioned: keep a copy of the source CSV in `tests/fixtures/` so the sheet
  can be rebuilt from scratch and a new env can be bootstrapped.

COMMENT: we already have google sheets that can be used. I can make a copy and add the CSV exports to a docs directory, along with documenting the number to select and the gsheet and selection settings to be used.

## Other options worth considering

- **Synthetic-only run that doesn't hit Google.** Would catch most of the
  chain but explicitly *not* the bit that broke. Reject — defeats the
  purpose.
- **Exercise via the BDD suite in prod.** Way too heavy, and BDD is for
  code-change validation not infra heartbeats. Reject.
- **Have the `/health` endpoint itself trigger a selection synchronously.**
  Tempting but bad: makes healthcheck slow and load-amplifying (any
  monitoring system polling /health every 30 sec would pile up runs);
  conflates "is the service up" with "did the last selection work". Reject.
- **Use Celery's `flower` or a third-party uptime ping (Healthchecks.io,
  Better Uptime).** Worth doing as the *consumer* of `/health` — out of
  scope for this plan but mention to ops. The plan here makes `/health`
  expressive enough that any HTTP-based uptime checker can act on it.
- **Push instead of pull.** Have the monitor task emit to a webhook
  (Slack, email, PagerDuty) directly on failure. Simpler than polling
  `/health` from outside. Could be a follow-up — for now `/health`
  is enough and fits existing infra.
- **Microsoft OAuth expiry pattern.** There's already
  `check_microsoft_oauth_expiry` in `health.py:61` that returns
  status enums and a `fail_on_warning` query parameter. Mirror that
  shape for consistency — the same external uptime checker can hit
  `/health?fail_on_warning=true` and get the strict version.

COMMENT: Agree with the conclusions above.

## Open questions for Doctor Chewie

1. **Production sheet ownership.** Whose Google account owns the monitor
   sheet, and is one sheet shared across test/staging/prod, or one per env?
   I lean one-per-env: blast radius if test breaks the sheet is zero.
2. **Frequency.** 30 min is fine for me, but is the API quota cost
   acceptable? Each run is roughly 6-10 Sheets API calls + 2-3 Drive API
   calls. 48 runs/day × few API calls = trivial vs the 60 req/min/user quota.
3. **Should test/staging environments alert?** I'd say no — only prod's
   `/health` should page. Test envs have monitoring as a passive signal
   that future deploys won't break prod, but a flapping test env shouldn't
   wake anyone.
4. **Tab-cleanup retention.** Keep the most recent N=20 selection tabs (so
   we can debug a recent failure by looking at the sheet) or zero (cleaner)?

COMMENT: 1. one-per-env makes sense. Though this is just something to document, can't really be enforced by code.
COMMENT: 2. could make it once per hour, and health max age is then 2 hours. Deploying new code is the most likely point that causes a failure, so the deploy check is the most important. Doesn't need to be super frequent in the background.
COMMENT: 3. what we have is that the staging/demo env is monitored, but in that environment it only sends an email to developers, so no one is disturbed outside work, but we do know the health monitoring works. And production has more aggressive notification.
COMMENT: 4. no need to keep any old selection tabs

## Implementation sketch

Roughly the order of small, reviewable PRs:

1. **Service layer + CLI.** `service_layer/monitoring.py` with
   `run_monitoring_selection`. CLI `opendlp monitor run-selection`. Config
   reads `MONITOR_ASSEMBLY_ID`, `MONITOR_USER_ID`,
   `MONITOR_TIMEOUT_SECONDS` (default 300),
   `MONITOR_HEALTH_MAX_AGE_MINUTES` (default 60). Unit tests with a fake
   uow; an integration test that hits a local CSV-mode gsheet stand-in.
2. **Healthcheck integration.** Extend `/health` with the
   `check_monitor_selection` function, mirroring the MS-OAuth pattern.
3. **Celery beat schedule.** Add `monitor-selection` to
   `beat_schedule` in `app.py` (every 30 min) and
   `monitor-selection-tab-cleanup` (every 6 hr). Wire the beat job to call
   the same service function as the CLI.
4. **Setup tooling.** `opendlp monitor setup-assembly` CLI that takes a
   gsheet URL + creates the monitor user, assembly, gsheet config, settings,
   and target categories from a fixture file. Idempotent. Document in
   `docs/agent/582-monitor-selection-working/setup.md`.
5. **Pruning.** Periodic task that keeps the most recent N
   `SelectionRunRecord`s for the monitor assembly to bound table growth.
6. **Docs.** Brief note in `docs/configuration.md` for the new env vars; a
   one-pager in `docs/monitor.md` explaining the moving parts and how to
   debug a failing monitor (mirror of Doctor Chewie's recent service-account
   incident as the worked example).

Total surface area: small. New tables: zero. New external infra: zero
(beyond setting up the gsheet). Risk: the monitor itself becomes the source
of truth for "is selection broken" — so its own correctness matters and
deserves more than passing tests.
