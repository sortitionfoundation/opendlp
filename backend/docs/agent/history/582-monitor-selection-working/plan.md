# Implementation plan: end-to-end monitoring of selection (issue #582)

Background and option analysis are in `research.md` in this folder. This
plan reflects the agreed decisions (recapped at the bottom in case
research.md diverges).

Implementation is **red/green TDD**: every behaviour change starts with a
failing test, then the minimum code to make it pass, then refactor. The
"Steps" section below lists each red/green cycle in order.

Test layering follows `docs/testing.md`:

- Repository method tests → `tests/contract/` (run against both fake and
  SQL backends).
- Service-function tests that don't need real SQLAlchemy → `tests/unit/`
  with `FakeUnitOfWork`.
- Database-specific behaviour (cascade, JSON round-trips, SQL-only
  helpers) → `tests/integration/`.
- HTTP-level tests of `/health` and friends → `tests/e2e/`.
- Prefer **dependency injection of fakes** over `mock.patch`. Where DI
  is impractical (eg. the Celery boundary), patching is fine — flagged
  case-by-case in the steps below.
- Use the `temp_env_vars` and `clear_env_vars` fixtures from
  `tests/conftest.py` for env-var manipulation, not raw monkeypatch.

## Assumptions verified against the code

These are the existing pieces this plan builds on. I checked each before
writing the plan, so it's grounded in what's actually there rather than
what I half-remember.

- `bootstrap()` in `src/opendlp/bootstrap.py:31` returns an
  `AbstractUnitOfWork`. It is **used as a context manager** in existing
  code, e.g. `with bootstrap() as uow:` in `tasks.py:104` and
  `with bootstrap(session_factory=session_factory) as uow:` in
  `tasks.py:996`.
- `SelectionRunRecordRepository` (`src/opendlp/service_layer/repositories.py:214`)
  has `get_by_task_id`, `get_by_assembly_id`, `get_latest_for_assembly`,
  `get_running_tasks`, `get_all_unfinished`, `get_by_assembly_id_paginated`.
  **It does NOT have `delete_old_for_assembly`**, and `get_latest_for_assembly`
  has no `task_type` filter — both need to be added (see "Repository
  additions" below).
- `start_gsheet_select_task` in `service_layer/sortition.py:134` takes
  `(uow, user_id, assembly_id, test_selection)`, creates a
  `SelectionRunRecord`, and dispatches via `tasks.run_select.delay(...)`.
  Permission decorator `@require_assembly_permission(can_manage_assembly)`
  means the monitor user needs an `organiser` role on the monitor assembly.
- `start_gsheet_manage_tabs_task` in `service_layer/sortition.py:333` is
  the service entry point for tab cleanup; it dispatches
  `tasks.manage_old_tabs` and creates its own `SelectionRunRecord` with
  `task_type=SelectionTaskType.DELETE_OLD_TABS`. We will use this rather
  than bypassing into `tasks.manage_old_tabs.delay(...)`.
- `tasks.manage_old_tabs` (`tasks.py:877`) calls
  `data_source.delete_old_output_tabs(dry_run=False)`. The real
  `GSheetDataSource.delete_old_output_tabs` (in sortition-algorithms)
  deletes every old auto-generated output tab — we don't need a "keep N"
  knob to satisfy "keep zero".
- `check_and_update_task_health` in `service_layer/sortition.py:904`
  already enforces `TASK_TIMEOUT_HOURS` and reconciles DB status with
  Celery state. We can reuse this for "did the worker die?".
- `get_selection_run_status` in `service_layer/sortition.py:670` is the
  polling helper the UI uses; suitable for the wrapper to poll.
- `health.py:check_microsoft_oauth_expiry` (lines 61-104) is the pattern
  to mirror.
- `gsheets.view_assembly_selection_with_run` route
  (`entrypoints/blueprints/gsheets.py:306`) is the canonical "view this
  run" URL: `url_for("gsheets.view_assembly_selection_with_run",
  assembly_id=…, run_id=…, _external=True)`.
- `tests/fakes.py:632` has `FakeUnitOfWork` and
  `FakeSelectionRunRecordRepository` (line 310).
- `tests/conftest.py` exposes `cli_with_session_factory`, `temp_env_vars`,
  `clear_env_vars`. Health endpoint tests live in
  `tests/e2e/test_health_check.py`.
- `tasks.run_select.delay(...)` is shorthand for
  `apply_async(args, kwargs)`. We can substitute
  `apply_async(kwargs={...}, time_limit=300)` to get a per-call hard
  timeout without touching global Celery config.
- `beat_schedule` in `entrypoints/celery/app.py:33` already configures
  `cleanup_orphaned_tasks` at 300s. New beat entries go here.
- Click subgroup pattern: `entrypoints/cli/__init__.py` imports each
  subgroup and registers it via `cli.add_command(...)`.
- `backend/env.example` exists at the repo level — needs new entries.

## Files to be added or changed

### New files

| Path | Purpose |
| --- | --- |
| `src/opendlp/service_layer/monitoring.py` | `run_monitoring_selection`, `MonitorResult`, `get_latest_monitor_run`, URL helper. |
| `src/opendlp/entrypoints/cli/monitor.py` | Click subgroup; `run-selection` command. |
| `tests/unit/test_monitoring_service.py` | Service-function tests using `FakeUnitOfWork` + injected fakes. |
| `tests/contract/test_selection_run_record_repo.py` (or extend if it exists) | Contract tests for `delete_old_for_assembly` and the `task_type`-filtered `get_latest_for_assembly`. |
| `tests/e2e/test_health_check_monitoring.py` | `/health` and `/health/monitor_selection` integration when monitoring is configured. |
| `tests/integration/test_cli_monitor.py` | CLI tests via `cli_with_session_factory`. |
| `docs/monitoring.md` | New long-term doc covering: (a) the `/health` and `/health/bdd` endpoints (currently only documented incidentally across other files), (b) the new `/health/monitor_selection` endpoint, (c) the end-to-end monitor selection feature — provisioning the gsheet, env vars, deploy-script wiring, troubleshooting. **Skeleton with TODO blanks for Doctor Chewie to fill in concrete values.** |
| `docs/fixtures/monitoring/respondents.csv` | Source-of-truth CSV for the monitor sheet's people tab. (Doctor Chewie supplies.) Lives outside `docs/agent/` because it ships permanently. |
| `docs/fixtures/monitoring/categories.csv` | Same for the targets tab. (Doctor Chewie supplies.) |

### Modified files

| Path | What changes |
| --- | --- |
| `src/opendlp/config.py` | Three new helpers: `get_monitor_assembly_id`, `get_monitor_user_id`, `get_monitor_health_max_age_minutes`. |
| `src/opendlp/service_layer/repositories.py` | Add `delete_old_for_assembly` and a `task_type` filter on `get_latest_for_assembly`. |
| `src/opendlp/service_layer/sortition.py` | Add optional `celery_apply_kwargs: dict | None = None` to `start_gsheet_select_task`; forward to `apply_async` if set, otherwise keep `delay()`. |
| `src/opendlp/entrypoints/blueprints/health.py` | Add `check_monitor_selection`; wire into `/health` (informational) and add a focused `/health/monitor_selection` endpoint that returns 500 on `NOT_CONFIGURED` (see "Health endpoint structure"). |
| `src/opendlp/entrypoints/celery/app.py` | Add `monitor-selection` (3600s) and `prune-monitor-runs` (86400s) entries to `beat_schedule`. |
| `src/opendlp/entrypoints/celery/tasks.py` | Add `monitor_selection_periodic` and `prune_monitor_run_records` tasks. |
| `src/opendlp/entrypoints/cli/__init__.py` | Register the new `monitor` subgroup. |
| `tests/fakes.py` | Add `delete_old_for_assembly` and the `task_type` kwarg on `get_latest_for_assembly` to `FakeSelectionRunRecordRepository`. |
| `docs/configuration.md` | Document the three new env vars **and** how to provision the monitor assembly (CSV file locations, expected number-to-select, settings). Skeleton with blanks for Doctor Chewie. |
| `backend/env.example` | Add the three new env vars with placeholder values. |

No Alembic migration. No new domain classes. No new tables. No
`_delete_all_test_data()` updates.

## Configuration

Three env vars, helpers in `config.py` shaped like
`get_task_timeout_hours` (`config.py:167`):

| Env var | Default | Behaviour |
| --- | --- | --- |
| `MONITOR_ASSEMBLY_ID` | unset | UUID of the monitor assembly. Unset → monitoring disabled across CLI/beat/health. |
| `MONITOR_USER_ID` | unset | UUID of the system user that "runs" the monitor. Required when `MONITOR_ASSEMBLY_ID` is set. |
| `MONITOR_HEALTH_MAX_AGE_MINUTES` | `120` | Age beyond which the latest successful monitor run is `STALE`. |

Two values stay as module-level constants in `monitoring.py` because they
are tied to the implementation rather than ops-tunable:

```python
MONITOR_CELERY_TIME_LIMIT_SECONDS = 300
MONITOR_WRAPPER_TIMEOUT_SECONDS = 360
```

`env.example` gains:

```bash
# Monitoring (issue #582). Both IDs must be set together; leaving them
# unset disables monitoring entirely. See docs/monitoring.md
MONITOR_ASSEMBLY_ID=
MONITOR_USER_ID=
# Optional override (default 120 minutes)
# MONITOR_HEALTH_MAX_AGE_MINUTES=120
```

## The service function

```python
# src/opendlp/service_layer/monitoring.py

@dataclass
class MonitorResult:
    success: bool
    task_id: uuid.UUID | None
    duration_seconds: float
    message: str           # short user-facing summary
    error: str = ""        # technical detail when success is False
    not_configured: bool = False
    run_url: str = ""      # absolute URL to the run page; empty when no Flask context


def run_monitoring_selection(
    uow: AbstractUnitOfWork,
    *,
    # Injected dependencies — defaults are the real implementations.
    # Tests override these instead of monkeypatching.
    start_select_fn: Callable = start_gsheet_select_task,
    start_cleanup_fn: Callable = start_gsheet_manage_tabs_task,
    health_check_fn: Callable = check_and_update_task_health,
    poll_status_fn: Callable = get_selection_run_status,
    now_fn: Callable[[], datetime] = aware_utcnow,
    sleep_fn: Callable[[float], None] = time.sleep,
    wrapper_timeout_seconds: int = MONITOR_WRAPPER_TIMEOUT_SECONDS,
    celery_time_limit_seconds: int = MONITOR_CELERY_TIME_LIMIT_SECONDS,
) -> MonitorResult:
    ...
```

The kwargs-only injection points let unit tests pass fakes/spies for the
boundary calls. Production callers (CLI, beat task) call with no kwargs
and get the real defaults.

Behaviour, in the order the tests will drive it:

1. Read `assembly_id` and `user_id` from config. If either is unset →
   `MonitorResult(success=False, not_configured=True, message="monitoring not configured")`.
2. Call
   `start_select_fn(uow, user_id, assembly_id, celery_apply_kwargs={"time_limit": celery_time_limit_seconds, "soft_time_limit": celery_time_limit_seconds - 30})`.
   Catch `AssemblyNotFoundError`, `GoogleSheetConfigNotFoundError`,
   `InvalidSelection`, `InsufficientPermissions` → failure result naming
   the underlying error class.
3. Poll loop: every 2 seconds (configurable for tests via the injected
   `sleep_fn`), call `poll_status_fn(uow, task_id)`. Stop when the
   record's `has_finished` is true OR `now_fn() - start` exceeds
   `wrapper_timeout_seconds`.
4. After roughly half the wall-clock budget, call
   `health_check_fn(uow, task_id)` once — catches dead workers without
   us reimplementing Celery introspection.
5. On wrapper timeout: call `health_check_fn` (which marks timed-out
   records FAILED), return failure with
   `message="monitor exceeded wall-clock timeout"`.
6. On success: best-effort dispatch
   `start_cleanup_fn(uow, user_id, assembly_id, dry_run=False)`. Don't
   poll — its own `SelectionRunRecord` will surface failures via the
   next health check.
7. Build `run_url` if a Flask app context is available (via
   `_safe_run_url(assembly_id, task_id)` — returns `""` outside a
   request context, so callers without one degrade gracefully).
8. Return `MonitorResult` reflecting `record.is_completed`.

### Latest-run helper

```python
def get_latest_monitor_run(
    uow: AbstractUnitOfWork,
    task_type: SelectionTaskType = SelectionTaskType.SELECT_GSHEET,
) -> SelectionRunRecord | None:
    """Most recent SelectionRunRecord of a given type for the monitor assembly.

    Defaults to SELECT_GSHEET — that's the heartbeat. Callers that want to
    inspect the latest cleanup pass DELETE_OLD_TABS.
    """
```

This is filtered by `task_type` because after a successful selection the
monitor also dispatches a cleanup task, and `get_latest_for_assembly()`
would otherwise return that cleanup record. The healthcheck wants the
latest selection specifically, with the cleanup tracked alongside it.

## Repository additions

`SelectionRunRecordRepository`:

```python
@abc.abstractmethod
def delete_old_for_assembly(self, assembly_id: uuid.UUID, keep: int) -> int:
    """Delete all but the most recent `keep` records for this assembly. Returns count deleted."""

# Extension to the existing method:
@abc.abstractmethod
def get_latest_for_assembly(
    self,
    assembly_id: uuid.UUID,
    task_type: SelectionTaskType | None = None,
) -> SelectionRunRecord | None:
    """Most recent record for an assembly, optionally filtered by task_type."""
```

The `task_type` kwarg defaults to `None` to preserve every existing
caller's behaviour (`service_layer/sortition.py:803, 820`).

SQLAlchemy implementation: ORM table column refs per the project's mypy
convention (CLAUDE.md "Database Patterns"). For
`delete_old_for_assembly`, use a subquery to find the cutoff `created_at`
then delete records older than that for the assembly.

`FakeSelectionRunRecordRepository` mirrors both: filter to assembly,
optional task_type filter, sort desc by `created_at`, slice/return the
matching subset.

These methods are tested in `tests/contract/` (parameterized over fake
and SQL backends) per `docs/testing.md`. SQL-specific behaviour
(behaviour around uncommitted records, JSON round-trip) stays in
integration tests if needed.

## Health endpoint structure

Doctor Chewie raised this in two comments: the `fail_on_warning=true`
semantics get tangled when we add a `NOT_CONFIGURED` value, and the
endpoint is becoming a junk drawer. Splitting helps.

**Recommendation:** add focused subsystem endpoints alongside the
existing `/health`, rather than reshaping `/health` itself.

| Endpoint | Purpose | Status code rules |
| --- | --- | --- |
| `/health` | Aggregate overall view, **unchanged from today**. Add monitor info as informational JSON fields, but do NOT let `NOT_CONFIGURED` cause 500. Existing `fail_on_warning=true` semantics preserved exactly. | As today, plus monitor failures (FAILED/STALE/UNKNOWN) cause 500. |
| `/health/monitor_selection` | Monitor-only view. **`NOT_CONFIGURED` returns 500 here**, on the assumption that anything pointing a watcher at this URL has elected to monitor it. | 200 only on `OK` or `PENDING`. 500 otherwise (incl. `NOT_CONFIGURED`). |
| `/health/oauth_microsoft` | (Optional, can defer.) Same pattern for the existing Microsoft expiry check. | Same shape. |

Splitting solves three things:

1. **Cleaner `fail_on_warning` semantics.** The aggregate keeps
   conservative defaults; opt-in strictness lives at the focused URL.
2. **Explicit "I expect this to be configured".** Pointing at
   `/health/monitor_selection` is the operator's declaration that
   monitoring should be live. Returning 500 on `NOT_CONFIGURED` correctly
   surfaces a forgotten env var on a redeployed environment.
3. **No coupling between the existing pollers and new behaviour.**
   Existing `/health` consumers keep working unchanged.

The new `/health/oauth_microsoft` endpoint is sketched here for
consistency but I'd suggest deferring to a separate PR — outside the
scope of #582.

### `check_monitor_selection`

```python
# health.py — new function, mirrors check_microsoft_oauth_expiry shape

def check_monitor_selection() -> tuple[str, datetime | None, str, str]:
    """
    Returns (status, last_run_at, short_message, run_url).

    status:
      "NOT_CONFIGURED"  - no MONITOR_ASSEMBLY_ID set
      "OK"              - last SELECT_GSHEET COMPLETED within max-age window
                          AND latest DELETE_OLD_TABS (if any) succeeded
      "STALE"           - last SELECT_GSHEET COMPLETED but older than threshold,
                          OR last is RUNNING/PENDING and older than threshold,
                          OR no SELECT_GSHEET runs exist yet
      "FAILED"          - last terminal SELECT_GSHEET was FAILED/CANCELLED,
                          OR last DELETE_OLD_TABS was FAILED/CANCELLED
      "PENDING"         - last is RUNNING/PENDING and within threshold
      "UNKNOWN"         - bootstrap/DB query failed
    """
```

`run_url` is built with `url_for("gsheets.view_assembly_selection_with_run",
assembly_id=…, run_id=…, _external=True)` — Flask context is always
available inside a request handler, so this is safe.

Why include cleanup status: a regression that breaks `delete_old_output_tabs`
(eg. tab-naming convention drift in sortition-algorithms) won't show up
in selection success. Both checks are cheap; including both is the
right call. We don't separately surface "stale cleanup" because cleanup
runs piggyback on selection — if selection is fresh, cleanup is too.

### JSON shape

`/health` (and `/health/monitor_selection`) gain:

```jsonc
{
  "monitor_selection_status": "OK",                    // see status enum
  "monitor_selection_last_run_at": "2026-05-07T15:00:00+00:00",
  "monitor_selection_message": "Selection completed successfully…",
  "monitor_selection_last_run_url": "https://opendlp.example.org/assembly/<uuid>/selection/<run_uuid>",
  "monitor_cleanup_status": "OK"                       // optional informational field
}
```

Healthy iff `monitor_selection_status in ("OK", "PENDING", "NOT_CONFIGURED")`
and `monitor_cleanup_status` is not `FAILED`.

For `/health/monitor_selection`, `NOT_CONFIGURED` is unhealthy.

## Celery beat additions

`entrypoints/celery/app.py`, extending `beat_schedule`:

```python
beat_schedule={
    "cleanup-orphaned-tasks": {
        "task": "opendlp.entrypoints.celery.tasks.cleanup_orphaned_tasks",
        "schedule": 300.0,
    },
    "monitor-selection": {
        "task": "opendlp.entrypoints.celery.tasks.monitor_selection_periodic",
        "schedule": 3600.0,  # hourly
    },
    "prune-monitor-runs": {
        "task": "opendlp.entrypoints.celery.tasks.prune_monitor_run_records",
        "schedule": 86400.0,  # daily
    },
},
```

`entrypoints/celery/tasks.py`:

```python
@app.task
def monitor_selection_periodic(session_factory: sessionmaker | None = None) -> dict[str, Any]:
    """Hourly heartbeat — one full monitor selection."""
    with bootstrap(session_factory=session_factory) as uow:
        result = run_monitoring_selection(uow)
    logging.info("monitor selection completed: success=%s, message=%s",
                 result.success, result.message)
    return {"success": result.success,
            "duration_seconds": result.duration_seconds,
            "message": result.message,
            "task_id": str(result.task_id) if result.task_id else None}


@app.task
def prune_monitor_run_records(
    session_factory: sessionmaker | None = None,
    keep: int = 100,
) -> int:
    """Prune monitor SelectionRunRecords beyond the most recent `keep`."""
```

`prune_monitor_run_records` is a no-op when `MONITOR_ASSEMBLY_ID` is
unset. Default `keep=100` ≈ 4 days at hourly cadence.

## Optional kwarg on `start_gsheet_select_task`

Current call (`service_layer/sortition.py:182`):

```python
result = tasks.run_select.delay(
    task_id=task_id,
    data_source=data_source,
    number_people_wanted=assembly.number_to_select,
    settings=settings_obj,
    test_selection=test_selection,
    gen_rem_tab=gsheet.generate_remaining_tab,
)
```

After:

```python
def start_gsheet_select_task(
    uow, user_id, assembly_id,
    test_selection=False,
    celery_apply_kwargs: dict[str, Any] | None = None,
):
    ...
    apply_kwargs = celery_apply_kwargs or {}
    kwargs = {
        "task_id": task_id,
        "data_source": data_source,
        "number_people_wanted": assembly.number_to_select,
        "settings": settings_obj,
        "test_selection": test_selection,
        "gen_rem_tab": gsheet.generate_remaining_tab,
    }
    result = tasks.run_select.apply_async(kwargs=kwargs, **apply_kwargs)
```

Default behaviour for every existing caller is unchanged because
`apply_async(kwargs=...)` with no extra kwargs is equivalent to
`delay(**kwargs)`. The monitor passes
`{"time_limit": 300, "soft_time_limit": 270}`.

## Tab cleanup wiring

In `run_monitoring_selection` after success, we call
`start_cleanup_fn(uow, user_id, assembly_id, dry_run=False)` (which by
default is `start_gsheet_manage_tabs_task`).

Three reasons for going through the service function:

1. The cleanup gets its own `SelectionRunRecord` with task_type
   `DELETE_OLD_TABS`.
2. The permission decorator runs (catches a missing role on the monitor
   user before the Celery roundtrip).
3. A failing cleanup is independently visible via
   `monitor_cleanup_status` in `/health`.

Doctor Chewie wants zero retained tabs, which is what
`delete_old_output_tabs(dry_run=False)` gives us already.

## CLI command

```python
# src/opendlp/entrypoints/cli/monitor.py

@click.group()
def monitor() -> None:
    """End-to-end monitoring of the selection pipeline."""


@monitor.command("run-selection")
@click.option("--strict/--no-strict", default=True,
              help="When --no-strict, exit 0 even on failure (still prints).")
@click.pass_context
def run_selection(ctx: click.Context, strict: bool) -> None:
    """Run one full monitor selection. Intended at the end of deploy."""
    uow = bootstrap()
    with uow:
        result = run_monitoring_selection(uow)

    if result.not_configured:
        click.echo(click.style(
            "⚠  Monitoring not configured (MONITOR_ASSEMBLY_ID/MONITOR_USER_ID unset)",
            "yellow"))
        return

    if result.success:
        click.echo(click.style(
            f"✓ Monitor selection succeeded in {result.duration_seconds:.1f}s",
            "green"))
        if result.run_url:
            click.echo(f"  View: {result.run_url}")
        return

    click.echo(click.style(f"✗ Monitor selection failed: {result.message}", "red"))
    if result.error:
        click.echo(f"  {result.error}")
    if result.run_url:
        click.echo(f"  View: {result.run_url}")
    if strict:
        raise Exit(1)
```

`run_url` is populated by the service function only if a Flask app
context is available. For the CLI we'd need to either push an app
context at startup (cheap — `current_app.app_context().push()` in the
CLI bootstrap) **or** build the URL in the CLI itself once the result is
back. Going with the first since `url_for(_external=True)` needs
`SERVER_NAME` to give a sensible host outside a request — see
`docs/deploy.md`. If `SERVER_NAME` isn't set, `run_url` stays empty and
the CLI just doesn't print the View line. Acceptable degradation.

Registered in `entrypoints/cli/__init__.py` next to the existing
subgroups.

## TDD steps (in order)

Each step starts **red** and ends **green**. Run `just test` and
`just check` at the end of every step.

### Step 1 — Config helpers

**Red:** Extend or add `tests/unit/test_config.py` (the existing config
tests file). Use `temp_env_vars` / `clear_env_vars`:

- `MONITOR_ASSEMBLY_ID` cleared → `None`
- `MONITOR_ASSEMBLY_ID="not-a-uuid"` → `None` and a warning is logged
- valid UUID → that UUID
- symmetric for `MONITOR_USER_ID`
- `MONITOR_HEALTH_MAX_AGE_MINUTES` cleared → 120
- non-integer → 120 plus warning
- valid integer → that integer

Capture warnings with `caplog` to assert pristine output policy: only
the expected warning text appears.

**Green:** Implement the three helpers in `config.py`.

### Step 2 — Repository additions (contract tests)

**Red:** `tests/contract/test_selection_run_record_repo.py` (extend if
present, create otherwise). Following the `tests/contract` pattern in
`docs/testing.md`:

- `delete_old_for_assembly`: insert N+5 records with staggered
  `created_at`, call with `keep=N`, assert exactly N remain and they're
  the newest. A second test asserts records for *other* assemblies are
  untouched.
- `get_latest_for_assembly(task_type=…)`: insert mixed task types,
  assert the filter returns the newest matching record.
- `get_latest_for_assembly()` with no `task_type` still returns the
  newest record overall (regression guard for existing callers).

**Green:**

- Extend the abstract methods on `SelectionRunRecordRepository`.
- SQL implementation using ORM table column refs.
- Update `FakeSelectionRunRecordRepository` to match.

### Step 3 — `MonitorResult` + not-configured path

**Red:** `tests/unit/test_monitoring_service.py`, using `clear_env_vars`
to drop `MONITOR_ASSEMBLY_ID`, calling
`run_monitoring_selection(FakeUnitOfWork())` and asserting
`MonitorResult(success=False, not_configured=True, ...)`. Spy fakes for
`start_select_fn` etc. assert nothing was called.

**Green:** Create `monitoring.py` with `MonitorResult` and the
not-configured branch only.

### Step 4 — Happy path with injected fakes

**Red:** Same test file. Use `temp_env_vars` to set fake UUIDs.
Pre-populate `FakeUnitOfWork` with the monitor assembly + user + an
`AssemblyGSheet`. Inject:

- `start_select_fn`: a callable that creates a `SelectionRunRecord` in
  the fake repo and returns its `task_id`. Records the
  `celery_apply_kwargs` it was called with.
- `start_cleanup_fn`: spy that records its call args.
- `poll_status_fn`: a stateful callable that returns RUNNING the first
  call and COMPLETED on subsequent calls.
- `now_fn` / `sleep_fn`: a fake clock that advances when `sleep_fn` is
  called. No real sleeping in tests.

Assert:

- `start_select_fn` was called with
  `celery_apply_kwargs={"time_limit": 300, "soft_time_limit": 270}`.
- `MonitorResult.success` is True; `task_id` matches the seeded record.
- `start_cleanup_fn` was called once with `dry_run=False`.

This is the canonical example for **DI over patching**. The Celery
boundary is never crossed, and no `mock.patch` is needed.

**Green:** Implement the polling + happy-path branches.

### Step 5 — Wrapper timeout

**Red:** Same test file. Inject a `poll_status_fn` that returns
RUNNING forever, and a fake clock that jumps forward each `sleep_fn`
call. Set a tiny `wrapper_timeout_seconds` for the test.

Assert: `success is False`, `"timeout" in message.lower()`,
`health_check_fn` was called.

**Green:** Add the wall-clock guard + the half-budget health-check call.

### Step 6 — Service-function exceptions

**Red:** Inject a `start_select_fn` that raises each of:
`AssemblyNotFoundError`, `GoogleSheetConfigNotFoundError`,
`InvalidSelection`, `InsufficientPermissions`. Assert each yields
`MonitorResult(success=False, ...)` with a message naming the underlying
error class for diagnosis.

**Green:** Try/except around the call.

### Step 7 — `apply_kwargs` plumbing in `start_gsheet_select_task`

**Red:** Extend `tests/unit/test_sortition_service.py`. This test does
need to verify the Celery dispatch shape, and the existing tests in this
module already use `mock.patch` on `tasks.run_select` — DI here would
require restructuring `start_gsheet_select_task` more invasively than
the agreed scope. **Patch is the right call here, in line with the
exception in this plan's TDD preamble.**

Patch `tasks.run_select.apply_async`; call
`start_gsheet_select_task(..., celery_apply_kwargs={"time_limit": 5})`;
assert the kwargs and `time_limit=5` were forwarded.

**Green:** Add the parameter; switch from `.delay` to
`.apply_async(kwargs=..., **apply_kwargs)`. Confirm every existing
test in the module still passes unchanged.

### Step 8 — `get_latest_monitor_run`

**Red:** Unit test using `FakeUnitOfWork`. With monitor configured and
zero records → `None`. With one SELECT_GSHEET record → that record.
With a newer DELETE_OLD_TABS record → `get_latest_monitor_run()` (default
task_type) still returns the SELECT_GSHEET record.
`get_latest_monitor_run(task_type=DELETE_OLD_TABS)` returns the cleanup.

**Green:** Thin wrapper around the repo method.

### Step 9 — `check_monitor_selection`

**Red:** `tests/e2e/test_health_check_monitoring.py`. Each scenario sets
env vars via `temp_env_vars`, seeds `SelectionRunRecord`s for the
monitor assembly via direct repo writes (using
`postgres_session_factory`), then hits `/health` and (separately)
`/health/monitor_selection`. Patch out `check_database` and
`check_celery_worker` to keep assertions focused.

Cover each combination listed in the status table:

- `NOT_CONFIGURED`: env vars cleared. `/health` returns 200 with status
  `NOT_CONFIGURED`. `/health/monitor_selection` returns **500**.
- `OK`: COMPLETED SELECT_GSHEET 30 min old; cleanup also COMPLETED.
  Both endpoints 200, both `monitor_selection_status` and
  `monitor_cleanup_status` are `OK`.
- `STALE` (old success): COMPLETED SELECT_GSHEET 3 hours old → 500 on
  both, status `STALE`.
- `STALE` (no records): no records exist → status `STALE`.
- `FAILED` (selection): latest SELECT_GSHEET is FAILED → 500, status
  `FAILED`, message truncated.
- `FAILED` (cancelled): CANCELLED → `FAILED`.
- `FAILED` (cleanup): latest SELECT_GSHEET ok but latest
  DELETE_OLD_TABS is FAILED → 500, `monitor_cleanup_status="FAILED"`.
- `PENDING` within window → 200, status `PENDING`.
- `STALE` for old pending: RUNNING but `created_at` 3h ago → 500,
  `STALE`.
- `last_run_url` field is populated and looks like
  `…/assembly/<uuid>/selection/<run_uuid>` when there's a record.

**Green:** Implement `check_monitor_selection` returning the
4-tuple. Add the new fields to the JSON. Add the
`/health/monitor_selection` route. Wire the JSON updates into existing
`/health`.

### Step 10 — CLI `monitor run-selection`

**Red:** `tests/integration/test_cli_monitor.py` using
`cli_with_session_factory`. Patch `run_monitoring_selection` (the
service function — module-level, hard to inject through Click without
contrived plumbing — patch is the right call). Assert:

- success → exit 0, "✓" in output, "View:" line printed when `run_url`
  set.
- failure with `--strict` (default) → exit 1, "✗" in output.
- failure with `--no-strict` → exit 0 with "✗" still in output.
- not_configured → exit 0, "⚠" in output.

**Green:** Implement the `monitor` subgroup, register it.

### Step 11 — Beat tasks

**Red:** `tests/integration/test_celery_tasks.py` (extend). Test that
`monitor_selection_periodic` invokes `run_monitoring_selection` (patch
that function — the task body is a thin wrapper, DI here would be
over-engineering) and returns the documented dict shape. Test
`prune_monitor_run_records` directly against a real DB with seeded
records, asserting only the most-recent `keep` survive.

**Green:** Implement both tasks. Update `beat_schedule`.

### Step 12 — Documentation + `env.example`

No tests, but the operator-facing deliverables. The
`docs/agent/582-monitor-selection-working/` folder is a *working*
directory and gets moved to `docs/agent/history/` after this work is
merged — so any artefact that needs to live long-term goes into the
top-level `docs/` tree, not under `docs/agent/`.

- **New file `docs/monitoring.md`** — the long-term home. Sections:
  - *Health endpoints* — document the existing `/health` and
    `/health/bdd` routes (response shape, status-code rules,
    `fail_on_warning` semantics). This is documentation of behaviour
    that already exists; right now it's only mentioned incidentally in
    `architecture.md`, `docker.md`, `google_service_account.md`,
    `microsoft_oauth_setup.md`. Pulling it together here is a small
    bonus deliverable while we're in the area.
  - *`/health/monitor_selection`* — the new focused endpoint, status
    enum, JSON shape including `monitor_selection_last_run_url` and
    `monitor_cleanup_status`.
  - *Monitor selection feature* — what it does, how often it runs
    (hourly via Celery beat + on demand via CLI).
  - *Per-environment provisioning* — copy gsheet, share with service
    account, record URL.
  - *CSV fixtures* — point to `docs/fixtures/monitoring/`.
  - *Selection parameters* — `number_to_select=TODO`, `id_column=TODO`,
    any non-default settings (skeleton, blanks for Doctor Chewie).
  - *Bootstrap commands* — create monitor user, assembly,
    AssemblyGSheet, SelectionSettings, UserAssemblyRole (via
    `flask shell` initially; automation deferred).
  - *Env vars to set* — the three new variables.
  - *Wiring into deploy script* — `opendlp monitor run-selection`.
  - *Troubleshooting* — recipes mapping `/health/monitor_selection`
    failure modes to root causes, with the recent
    service-account-roles incident as the worked example.
- **New directory `docs/fixtures/monitoring/`** — drop
  `respondents.csv` and `categories.csv` here once Doctor Chewie
  supplies them. Cross-link from `docs/monitoring.md`.
- **Update `docs/configuration.md`** — add a "Monitoring" subsection
  under env vars covering all three new variables, with a pointer to
  `docs/monitoring.md`.
- **Update `backend/env.example`** — add the three new variables with
  placeholder comments. Reference `docs/monitoring.md` (not the
  working dir).
- **Cross-link from `docs/architecture.md`** — the existing
  `health` blueprint row briefly mentions `/health`; mention the new
  `/health/monitor_selection` endpoint there too.
- **Update CLAUDE.md's "Further Documentation" list** — add an entry
  for `docs/monitoring.md`.

After merge, archive the working directory:
`git mv docs/agent/582-monitor-selection-working docs/agent/history/582-monitor-selection-working`.
Anything Doctor Chewie wants to keep referencing later already lives
in `docs/monitoring.md` and `docs/fixtures/monitoring/`.

### Step 13 — Manual end-to-end verification (post-merge, on staging)

Not a TDD step but worth listing:

1. Set the env vars on staging.
2. Run `opendlp monitor run-selection`, confirm it succeeds and writes
   tabs to the gsheet.
3. Hit `/health` and `/health/monitor_selection`, confirm both are 200.
4. Revoke the service-account permission on the gsheet.
5. Run again; confirm CLI exits 1 with a permissions message, and
   `/health/monitor_selection` returns 500 with `FAILED`.
6. Restore permissions; wait for the next beat tick; confirm both
   endpoints recover.

## Open items needing Doctor Chewie's input before implementation

Just one item remains; the rest have been resolved in comment passes
above.

1. **Source CSVs and concrete settings.** When you hand over the CSV
   exports + the `number_to_select` / non-default `SelectionSettings`,
   I'll fill in the skeleton in `docs/monitoring.md`,
   `docs/configuration.md`, and `docs/fixtures/monitoring/`.

## Detailed TODO list

Phases group the TDD steps above into review-sized chunks. Each phase
ends with `just test && just check` clean and is mergeable on its own.
Within a phase, **every implementation task is preceded by the test
that drives it** — write the test, watch it fail (red), write the
minimum code to pass it (green), then refactor before moving to the
next checkbox. Don't tick the green box until the red box is ticked.

**Conventions used in this list**

- 🔴 = red test task (write the failing test)
- 🟢 = green implementation task (make it pass)
- 📄 = non-code task (docs, config, fixture)
- A box that says "all tests still pass" is a regression check, not
  new code — run the suite and verify nothing existing has broken.

---

### Phase 0 — Pre-flight

Make sure the working environment is sane before writing any code.

- [x] 📄 Run `just test` and `just check` on `main` and confirm both
      are clean. Any pre-existing failure must be sorted before this
      work starts so we don't conflate failures.
- [x] 📄 Pull the latest `main` into the `582-selection-monitoring`
      branch (or rebase) so we're starting from current code.
- [ ] 📄 Confirm a Doctor Chewie-supplied source gsheet is available
      for staging end-to-end verification later (URL noted in
      `docs/monitoring.md` skeleton during Phase 5).

---

### Phase 1 — Foundations: config + repository methods

Adds the lowest-level bits that everything else depends on. No
behaviour change visible to users yet. **Mergeable independently.**

#### Config helpers (Step 1 from above)

- [x] 🔴 In `tests/unit/test_config.py` add `TestMonitorConfig` with:
  - `MONITOR_ASSEMBLY_ID` cleared via `clear_env_vars` → returns `None`.
  - `MONITOR_ASSEMBLY_ID="not-a-uuid"` via `temp_env_vars` → returns
    `None` and emits a single warning (assert via `caplog`).
  - Valid UUID string → returns the parsed UUID.
  - Symmetric block of three tests for `MONITOR_USER_ID`.
  - `MONITOR_HEALTH_MAX_AGE_MINUTES`: cleared → `120`; non-integer →
    `120` plus warning; valid integer string → that integer.
  - Watch all eight tests fail with `AttributeError` /
    `ImportError`.
- [x] 🟢 Implement `get_monitor_assembly_id`,
      `get_monitor_user_id`, `get_monitor_health_max_age_minutes` in
      `src/opendlp/config.py`.
- [x] 🟢 All eight tests now pass.
- [x] 🟢 `just test && just check` clean.

#### Repository: `delete_old_for_assembly` and `task_type` filter (Step 2)

- [x] 🔴 Create or extend
      `tests/contract/test_selection_run_record_repo.py`
      following the contract pattern in `docs/testing.md`:
  - `TestDeleteOldForAssembly`: insert N+5 records with staggered
    `created_at` for assembly A; call `delete_old_for_assembly(A, keep=N)`;
    assert exactly N remain; assert they are the newest by `created_at`.
  - Second test in the same class: insert records for assembly A and
    assembly B; call against A; assert B's records are untouched.
  - Third test: `keep` larger than total → no-op, returns 0.
  - `TestGetLatestForAssemblyByTaskType`: insert mixed task types
    (`SELECT_GSHEET`, `DELETE_OLD_TABS`, `LOAD_GSHEET`); assert the
    `task_type=SELECT_GSHEET` filter returns the newest matching one.
  - Fourth test: `get_latest_for_assembly()` with no `task_type` still
    returns the newest record overall (regression guard).
  - Watch all parameterized cases (fake + SQL) fail.
- [x] 🟢 Add abstract method `delete_old_for_assembly` to
      `SelectionRunRecordRepository` in
      `src/opendlp/service_layer/repositories.py`.
- [x] 🟢 Add the `task_type: SelectionTaskType | None = None` kwarg to
      the abstract `get_latest_for_assembly`.
- [x] 🟢 Implement both on the SQLAlchemy class using ORM table column
      refs.
- [x] 🟢 Implement both on `FakeSelectionRunRecordRepository` in
      `tests/fakes.py`.
- [x] 🟢 All contract tests pass against fake **and** SQL.
- [x] 🟢 Run all existing repo tests — no regression.
- [x] 🟢 `just test && just check` clean.
- [x] 📄 **Phase 1 commit/PR.**

---

### Phase 2 — Service function: `run_monitoring_selection`

Builds the orchestration wrapper and the small `start_gsheet_select_task`
extension it needs. All tests live in `tests/unit/` against
`FakeUnitOfWork` with injected fakes — no real Celery, no real DB.

#### `apply_kwargs` plumbing in `start_gsheet_select_task` (Step 7 — done first because the service function depends on it)

- [x] 🔴 In `tests/unit/test_sortition_service.py`, add a test:
      patch `tasks.run_select.apply_async` (this is the documented
      "patch is fine here" exception); call
      `start_gsheet_select_task(uow, user_id, assembly_id,
      celery_apply_kwargs={"time_limit": 5, "soft_time_limit": 4})`;
      assert `apply_async` was called once with
      `kwargs={...all six...}` and the `time_limit=5,
      soft_time_limit=4` extra kwargs.
- [x] 🔴 Add a second test asserting the **default** call (no
      `celery_apply_kwargs`) still works — patch `apply_async`,
      assert `kwargs={...}` only, no extra kwargs.
- [x] 🟢 Add `celery_apply_kwargs: dict[str, Any] | None = None` to
      `start_gsheet_select_task`.
- [x] 🟢 Switch from `tasks.run_select.delay(...)` to
      `tasks.run_select.apply_async(kwargs=..., **(celery_apply_kwargs or {}))`.
- [x] 🟢 New tests pass; **all existing sortition-service tests still
      pass unchanged**.
- [x] 🟢 `just test && just check` clean.

#### `MonitorResult` + not-configured branch (Step 3)

- [x] 🔴 Create `tests/unit/test_monitoring_service.py`. First test:
      use `clear_env_vars("MONITOR_ASSEMBLY_ID", "MONITOR_USER_ID")`;
      call `run_monitoring_selection(FakeUnitOfWork())`; assert the
      result has `success=False`, `not_configured=True`,
      `task_id is None`. Inject spy fakes for `start_select_fn` etc.
      and assert none were called.
- [x] 🟢 Create `src/opendlp/service_layer/monitoring.py` with the
      `MonitorResult` dataclass and a stub `run_monitoring_selection`
      handling only the not-configured branch.
- [x] 🟢 Test passes.

#### Happy path (Step 4)

- [x] 🔴 Add `TestHappyPath` test class. Use `temp_env_vars` to set
      fake UUIDs. Pre-populate `FakeUnitOfWork` with the monitor
      assembly + AssemblyGSheet + monitor user + role. Inject
      `start_select_fn` (a spy that records its call args, creates a
      record in the fake repo, returns its task_id),
      `start_cleanup_fn` (spy), `poll_status_fn` (returns RUNNING
      then COMPLETED), `now_fn`/`sleep_fn` fake clock.
      Assert: `start_select_fn` called with
      `celery_apply_kwargs={"time_limit": 300, "soft_time_limit": 270}`;
      `MonitorResult.success` is True;
      `result.task_id` matches the seeded record;
      `start_cleanup_fn` called exactly once with `dry_run=False`.
- [x] 🟢 Implement steps 1-7 of the algorithm in
      `run_monitoring_selection` (env read, start, poll loop, cleanup
      dispatch). Implementation factors the polling into a small helper
      taking `now_fn`/`sleep_fn` so tests don't really sleep.
- [x] 🟢 Test passes.

#### Wrapper timeout (Step 5)

- [x] 🔴 Add a test: inject `poll_status_fn` returning RUNNING forever,
      a fake clock that jumps each `sleep_fn` call. Call with
      `wrapper_timeout_seconds=10` and a 2-second poll interval.
      Assert `success is False`, `"timeout" in message.lower()`,
      `health_check_fn` was called.
- [x] 🟢 Add the wall-clock guard and the half-budget
      `health_check_fn` call.
- [x] 🟢 Test passes.

#### Service-function exceptions (Step 6)

- [x] 🔴 Add a parameterised test
      `test_typed_exceptions_become_failure_results` over
      `[AssemblyNotFoundError, GoogleSheetConfigNotFoundError,
      InvalidSelection, InsufficientPermissions]`. Inject a
      `start_select_fn` that raises the parameter; assert
      `success is False`, message names the underlying error class.
- [x] 🟢 Wrap the call in a `try/except` covering exactly those four
      exception classes.
- [x] 🟢 Tests pass.

#### `get_latest_monitor_run` helper (Step 8)

- [x] 🔴 Add tests using `FakeUnitOfWork`:
  - Monitor configured, zero records → `None`.
  - Single SELECT_GSHEET record → returns it.
  - SELECT_GSHEET + later DELETE_OLD_TABS — default call returns
    the SELECT_GSHEET; `task_type=DELETE_OLD_TABS` returns the
    cleanup.
  - `MONITOR_ASSEMBLY_ID` unset → `None` (and DB not queried).
- [x] 🟢 Implement `get_latest_monitor_run` as a thin wrapper around
      `uow.selection_run_records.get_latest_for_assembly(monitor_assembly_id, task_type=…)`.
- [x] 🟢 Tests pass.
- [x] 🟢 `just test && just check` clean.
- [x] 📄 **Phase 2 commit/PR.**

---

### Phase 3 — Health endpoint integration

Adds the new `check_monitor_selection`, the new
`/health/monitor_selection` route, and the informational JSON fields
on `/health`. All tested at the HTTP boundary in `tests/e2e/`.

- [x] 🔴 Create `tests/e2e/test_health_check_monitoring.py`. Use
      `temp_env_vars` to configure `MONITOR_ASSEMBLY_ID`/
      `MONITOR_USER_ID`/`MONITOR_HEALTH_MAX_AGE_MINUTES` per scenario.
      Seed `SelectionRunRecord` rows directly via
      `postgres_session_factory`. Patch `check_database` and
      `check_celery_worker` to return healthy so the focus stays on
      the monitor checks.
      Cover one test per row in this matrix:

      | Scenario | Records | `/health` status | `/health/monitor_selection` status |
      | --- | --- | --- | --- |
      | Not configured | none | 200, `NOT_CONFIGURED` | **500**, `NOT_CONFIGURED` |
      | OK | SELECT_GSHEET COMPLETED 30 min ago + DELETE_OLD_TABS COMPLETED | 200, `OK`, cleanup `OK` | 200, `OK` |
      | Stale (old success) | SELECT_GSHEET COMPLETED 3 h ago | 500, `STALE` | 500, `STALE` |
      | Stale (no records) | configured, none | 500, `STALE` | 500, `STALE` |
      | Failed (selection) | SELECT_GSHEET FAILED | 500, `FAILED` | 500, `FAILED` |
      | Failed (cancelled) | SELECT_GSHEET CANCELLED | 500, `FAILED` | 500, `FAILED` |
      | Failed (cleanup) | SELECT_GSHEET COMPLETED + DELETE_OLD_TABS FAILED | 500, cleanup `FAILED` | 500 |
      | Pending within window | SELECT_GSHEET RUNNING 10 min old | 200, `PENDING` | 200, `PENDING` |
      | Stale (old pending) | SELECT_GSHEET RUNNING 3 h old | 500, `STALE` | 500, `STALE` |
      | URL field populated | any record | `monitor_selection_last_run_url` matches `…/assembly/<uuid>/selection/<run_uuid>` | same |

      Each row is one test method. Watch all fail.
- [x] 🟢 Add `check_monitor_selection() -> tuple[str, datetime | None,
      str, str]` to `src/opendlp/entrypoints/blueprints/health.py`.
      It reads config, queries the latest SELECT_GSHEET and
      DELETE_OLD_TABS records via `get_latest_monitor_run`, and
      returns the status string per the spec.
- [x] 🟢 Wire `check_monitor_selection` into the existing
      `health_check` view: add the four new JSON fields
      (`monitor_selection_status`, `monitor_selection_last_run_at`,
      `monitor_selection_message`, `monitor_selection_last_run_url`)
      plus `monitor_cleanup_status`. Update the
      `is_healthy` calculation. Preserve current `fail_on_warning`
      semantics for everything pre-existing.
- [x] 🟢 Add a new route `@health_bp.route("/health/monitor_selection")`
      that returns the same JSON shape but with `NOT_CONFIGURED` mapped
      to HTTP 500.
- [x] 🟢 All scenarios pass.
- [x] 🟢 Run existing `tests/e2e/test_health_check.py` — no regression.
- [x] 🟢 `just test && just check` clean.
- [x] 📄 **Phase 3 commit/PR.**

---

### Phase 4 — User-facing entry points: CLI + beat tasks

Wires the service function up to the two ways it actually runs.

#### CLI `monitor run-selection` (Step 10)

- [x] 🔴 Create `tests/integration/test_cli_monitor.py` using
      `cli_with_session_factory`. Patch `run_monitoring_selection`
      (module-level service function — patching is the right call
      here as flagged in the TDD preamble). Cases:
  - `MonitorResult(success=True, run_url="https://…")` → exit 0,
    "✓" in output, `View: https://…` line present.
  - `MonitorResult(success=False, message="boom", error="Traceback…")`
    with default `--strict` → exit 1, "✗" in output, indented error
    line present.
  - Same failure with `--no-strict` → exit 0, "✗" still present.
  - `MonitorResult(success=False, not_configured=True)` → exit 0,
    "⚠" in output.
- [x] 🟢 Create `src/opendlp/entrypoints/cli/monitor.py` with the
      `monitor` subgroup and the `run-selection` command.
- [x] 🟢 Register the subgroup in
      `src/opendlp/entrypoints/cli/__init__.py`.
- [x] 🟢 All four CLI tests pass.

#### Beat tasks (Step 11)

- [x] 🔴 In `tests/integration/test_celery_tasks.py` (extend) add:
  - `test_monitor_selection_periodic_invokes_service`: patch
    `run_monitoring_selection` to return a known `MonitorResult`;
    invoke `monitor_selection_periodic.run(session_factory=…)`
    directly (not via Celery dispatch); assert the returned dict has
    `success`, `duration_seconds`, `message`, `task_id` keys.
  - `test_prune_monitor_run_records_keeps_newest_only`: seed a real
    DB with N+5 records for the monitor assembly via
    `postgres_session_factory`; call
    `prune_monitor_run_records.run(session_factory=…, keep=N)`;
    assert exactly N remain.
  - `test_prune_monitor_run_records_no_op_when_unconfigured`:
    `clear_env_vars("MONITOR_ASSEMBLY_ID")`; call task; assert it
    returns 0 and didn't query the DB (or returned without error).
- [x] 🟢 Implement `monitor_selection_periodic` and
      `prune_monitor_run_records` in
      `src/opendlp/entrypoints/celery/tasks.py`.
- [x] 🟢 Add the two new entries to `beat_schedule` in
      `src/opendlp/entrypoints/celery/app.py`.
- [x] 🟢 All three tests pass.
- [x] 🟢 `just test && just check` clean.
- [x] 📄 **Phase 4 commit/PR.**

---

### Phase 5 — Documentation, fixtures, env example

No automated tests; the deliverable is the docs themselves. The
"red" here is "doc currently doesn't exist or doesn't say X"; the
"green" is "doc exists and says X".

- [x] 📄 Create `docs/monitoring.md` skeleton with sections per the
      Step 12 outline above. Mark concrete values as
      `**TODO (Doctor Chewie):**` so blanks are scannable.
- [x] 📄 Document the existing `/health` and `/health/bdd` endpoints
      in `docs/monitoring.md` (response shape, status-code rules,
      `fail_on_warning`). This is documentation of pre-existing
      behaviour and shouldn't change anything.
- [x] 📄 Document `/health/monitor_selection` (status enum, JSON
      shape, `monitor_selection_last_run_url`, `monitor_cleanup_status`).
- [x] 📄 Document the monitor-selection feature: cadence, deploy-time
      CLI, troubleshooting recipe based on the recent
      service-account-roles incident.
- [x] 📄 Create `docs/fixtures/monitoring/` directory with a README
      explaining the contents. (Actual CSVs added later by Doctor
      Chewie.)
- [x] 📄 Update `docs/configuration.md`: add a "Monitoring" subsection
      under env vars covering the three new variables; cross-link to
      `docs/monitoring.md`.
- [x] 📄 Update `backend/env.example`: add the three new variables
      with placeholder comments referencing `docs/monitoring.md`.
- [x] 📄 Update `docs/architecture.md`: in the `health` blueprint row,
      mention `/health/monitor_selection` alongside `/health` and
      `/health/bdd`.
- [x] 📄 Update `CLAUDE.md` "Further Documentation" list with a line
      for `docs/monitoring.md`.
- [x] 📄 Re-read all the new doc and fix anything that drifted from
      the actual code (link rot, renamed env vars, etc.).
- [x] 📄 **Phase 5 commit/PR.**

---

### Phase 6 — Doctor Chewie's handover items

These steps need values from Doctor Chewie before they can be
completed. They block the staging verification in Phase 7.

- [ ] 📄 Receive CSV exports of the current operational gsheet from
      Doctor Chewie.
- [ ] 📄 Drop them into `docs/fixtures/monitoring/respondents.csv` and
      `docs/fixtures/monitoring/categories.csv`.
- [ ] 📄 Receive concrete `number_to_select` and any non-default
      `SelectionSettings` values; fill the TODOs in
      `docs/monitoring.md`.
- [ ] 📄 Doctor Chewie creates a per-environment copy of the source
      gsheet (one for staging, one for prod) and shares each with the
      relevant service-account email.
- [ ] 📄 Bootstrap the monitor user + assembly + AssemblyGSheet +
      SelectionSettings + UserAssemblyRole on staging via the
      command sequence documented in `docs/monitoring.md`. Record the
      resulting UUIDs.
- [ ] 📄 Repeat the bootstrap on prod when ready.

---

### Phase 7 — Manual end-to-end verification (post-merge, staging first)

No new code; this is the "did we actually fix the original problem?"
walkthrough. Run on staging before promoting to prod.

- [ ] 📄 Set `MONITOR_ASSEMBLY_ID` and `MONITOR_USER_ID` in staging
      `.env`; restart staging.
- [ ] 📄 Run `opendlp monitor run-selection` on staging. Confirm
      exit 0 and the gsheet has new Selected/Remaining tabs.
- [ ] 📄 `curl https://staging…/health/monitor_selection` — confirm
      200 and `monitor_selection_status == "OK"`.
- [ ] 📄 `curl https://staging…/health` — confirm 200, monitor fields
      `OK`.
- [ ] 📄 Wait through one Celery beat tick (≤ 1 hour). Confirm a new
      record appears with success.
- [ ] 📄 Revoke the service-account share on the staging gsheet.
- [ ] 📄 Run `opendlp monitor run-selection` again — confirm exit 1,
      message names a permissions issue.
- [ ] 📄 `curl …/health/monitor_selection` — confirm 500, status
      `FAILED`, `monitor_selection_message` mentions permissions.
- [ ] 📄 Restore the share. Wait for the next beat tick (or run the
      CLI). Confirm both endpoints return to 200.
- [ ] 📄 Repeat the entire sequence on prod once staging looks happy
      and Doctor Chewie green-lights.

---

### Phase 8 — Archive working directory

After everything is merged and verified.

- [ ] 📄 `git mv docs/agent/582-monitor-selection-working
      docs/agent/history/582-monitor-selection-working`.
- [ ] 📄 Verify no doc anywhere still links to the working-dir path
      (search for `582-monitor-selection-working`).
- [ ] 📄 Final commit + push.

---

## Recap of agreed decisions

- **Option C** (real Assembly + monitor wraps `start_gsheet_select_task`).
- **Trigger via Celery beat**, hourly. CLI command for deploy gating.
- **Reuse `SelectionRunRecord`** with pruning. No new table.
- **Tab cleanup after every run; keep zero old tabs** (`dry_run=False`).
- **Health max age = 2 hours.** Cadence same on staging and prod.
- **Sheet provisioning is operator-side**: copy of an existing sheet,
  CSV exports + settings documented in `docs/monitoring.md`.
- **Notifications are an external concern.** Our job is `/health`
  correctness, not paging.
- **Skip the template-copy strategy.**
- **Tests follow `docs/testing.md`**: contract tests for repo methods,
  unit tests with `FakeUnitOfWork` for service logic, e2e for `/health`.
  DI over patch where practical.
- **Health endpoint splits**: keep `/health` largely as-is plus add
  `/health/monitor_selection` for focused monitoring.
- **`run_url` and `monitor_selection_last_run_url`** on the result and
  in JSON for direct navigation to a failing run.
- **Filter by task_type** when reading the latest monitor run; track
  cleanup separately as `monitor_cleanup_status`.
- **`env.example`** updated alongside new env vars.
- **Long-term docs land in `docs/monitoring.md`** (covering both the
  pre-existing `/health` endpoint and the new monitor feature) plus
  `docs/fixtures/monitoring/` for sample CSVs.
  `docs/agent/582-monitor-selection-working/` is treated as a working
  directory and archived to `docs/agent/history/` after merge.
