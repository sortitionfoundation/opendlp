# Monitoring

This document covers the OpenDLP health endpoints and the end-to-end
selection-monitoring feature added in issue #582.

## Health endpoints

OpenDLP exposes two long-standing JSON endpoints plus one focused
endpoint for monitor selection:

### `GET /health`

Aggregate health view. Returns 200 when all checks pass, 500 otherwise.

Checks performed:

- **`database_ok`** — bootstraps a Unit of Work and lists users.
- **`celery_worker_running`** — uses `celery_app.control.inspect()` to
  confirm at least one worker is active.
- **`service_account_email`** — returns the service-account email used
  for Google Sheets, or `"UNKNOWN"` if it can't be loaded.
- **`version`** — application version (from `generated_version.txt`).
- **`oauth_microsoft_*`** — Microsoft OAuth client-secret expiry
  (only relevant when `OAUTH_MICROSOFT_CLIENT_ID` is set).
- **Monitor selection** — see below.

#### Query parameter: `fail_on_warning`

Pass `?fail_on_warning=true` to make the endpoint return 500 in cases
that would otherwise be 200:

- Microsoft OAuth secret status `WARNING` (≤ 30 days) or `UNKNOWN`.
- Service account email `UNKNOWN`.

`fail_on_warning` is intended for stricter alerting (eg. paging) on
top of the default check. The aggregate endpoint never escalates a
`NOT_CONFIGURED` monitor result to a failure — see
`/health/monitor_selection` below for that semantic.

### `GET /health/bdd`

Reports environment-specific values used by the BDD test fixture to
verify it has reused the correct server. **Only available when
`FLASK_ENV` starts with `testing`.** Returns 404 in production.

### `GET /health/monitor_selection`

Focused endpoint for the end-to-end monitor selection feature.

Unlike `/health`, this endpoint treats `NOT_CONFIGURED` as **unhealthy
(500)**, on the assumption that anything pointing a watcher at this
URL is expecting it to be configured and working. Returning 500 on
a missing `MONITOR_ASSEMBLY_ID` correctly surfaces a forgotten env
var on a redeployed environment.

Status codes:

- 200 if `monitor_selection_status` is `OK`, `PENDING`, or `DEGRADED`
  AND `monitor_cleanup_status` is not `FAILED`.
- 500 otherwise.

JSON shape (also added to `/health`):

```jsonc
{
  "monitor_selection_status": "OK",
  "monitor_selection_last_run_at": "2026-05-07T15:00:00+00:00",
  "monitor_selection_message": "latest selection completed successfully",
  "monitor_selection_last_run_url": "https://opendlp.example.org/assembly/<uuid>/selection/<run_uuid>",
  "monitor_cleanup_status": "OK",
  "monitor_selection_consecutive_failures": 0,
  "monitor_selection_recent_failures": []
}
```

When runs are failing, `monitor_selection_recent_failures` lists the
current unbroken streak of failed runs (newest first), each carrying
the class name of the underlying error:

```jsonc
{
  "monitor_selection_status": "DEGRADED",
  "monitor_selection_consecutive_failures": 2,
  "monitor_selection_recent_failures": [
    {"error_class": "InfeasibleQuotasError", "status": "failed", "at": "2026-05-07T15:30:00+00:00"},
    {"error_class": "APIError", "status": "failed", "at": "2026-05-07T15:15:00+00:00"}
  ]
}
```

The `error_class` comes from the failed run's recorded error (falling
back to the run status when no exception was captured). It is exposed
so alerting can later apply different thresholds per error class — for
example tolerating more consecutive `APIError`s than permission errors.
That per-class logic is not yet implemented: today every error class
shares the same threshold.

Status enum:

| Status            | Meaning                                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `NOT_CONFIGURED`  | `MONITOR_ASSEMBLY_ID` is unset.                                                                                                  |
| `OK`              | Latest `SELECT_GSHEET` completed successfully within the max-age window AND latest `DELETE_OLD_TABS` (if any) succeeded.         |
| `STALE`           | Latest successful selection is older than the threshold, OR no selection runs exist yet, OR a pending/running run is too old.   |
| `DEGRADED`        | Latest `SELECT_GSHEET` was `FAILED`/`CANCELLED`, but fewer than the consecutive-failure threshold have failed in a row. Still healthy (200). |
| `FAILED`          | The most recent runs all failed — at least the consecutive-failure threshold in a row — OR latest `DELETE_OLD_TABS` failed.      |
| `PENDING`         | Latest run is in flight and within the max-age window.                                                                           |
| `UNKNOWN`         | Bootstrap or DB query failed (couldn't determine state).                                                                         |

The consecutive-failure threshold is `CONSECUTIVE_FAILURE_THRESHOLD`
(currently 3) in `service_layer/monitoring.py`. A single failed run
reports `DEGRADED` and stays healthy; only a sustained run of failures
escalates to `FAILED`. A successful or in-flight latest run resets the
streak.

The `monitor_cleanup_status` field is `OK` or `FAILED` based on the
most recent `DELETE_OLD_TABS` record (if any). A failing cleanup
marks the aggregate `monitor_selection_status` as `FAILED` so it
surfaces in alerts even if selection itself is healthy.

## Monitor selection feature

### What it does

Every 15 minutes, a Celery beat task runs `monitor_selection_periodic`,
which dispatches a full `start_gsheet_select_task` against a
dedicated monitor assembly + monitor user. After a successful
selection, it dispatches a `start_gsheet_manage_tabs_task` cleanup
to delete the auto-generated output tabs.

This exercises the full chain:

- DB connection + the Unit of Work
- Celery dispatch and result-backend round-trip
- Google Sheets API authentication and the service-account permission
- the sortition algorithm's read/select/write path
- the tab-cleanup path

If any of those break (eg. service-account permissions revoked,
sortition library regression, tab-naming convention drift), the
selection or cleanup will start failing and — once the
consecutive-failure threshold is reached — go `FAILED` at
`/health/monitor_selection` within roughly an hour (three
15-minute cycles). A single failure shows as `DEGRADED` sooner.

### Cadence

- **Every 15 minutes via Celery beat**: `monitor_selection_periodic`.
- **Daily via Celery beat**: `prune_monitor_run_records` keeps the
  most recent 100 monitor `SelectionRunRecord`s and deletes older
  ones (≈ 1 day at the 15-minute cadence).
- **On demand via CLI**: `opendlp monitor run-selection`.

### CLI command

```sh
opendlp monitor run-selection
```

Runs one full monitor selection and prints the result. Used in deploy
scripts to gate production rollout: if the monitor selection fails
immediately after a deploy, the script exits non-zero and the deploy
is aborted/rolled back.

Options:

- `--strict` (default): exit 1 on failure.
- `--no-strict`: exit 0 even on failure (still prints `✗`). Useful
  for ad-hoc inspection without aborting a script.

If monitoring is not configured (`MONITOR_ASSEMBLY_ID` unset) the
command exits 0 with a `⚠` warning.

## Per-environment provisioning

Each deployed environment (staging, prod) needs its own monitor
assembly with its own copy of the source Google Sheet.

The URLs for the instance will be recorded in the infrastructure
repo, that sets up the deployed instance.

### Source CSVs

The source-of-truth fixtures used to seed the monitor sheet live in
[`docs/fixtures/monitoring/`](fixtures/monitoring/).

- `respondents.csv` — people tab content
- `categories.csv` — targets tab content

### Selection parameters

With the above CSV files, you should use:

- `number_to_select`: 30
- `id_column`: `unique_id`
- Any non-default `SelectionSettings` values:
  - set "Check Same Address" to False

### Bootstrap commands

Run once per environment (via `flask shell` or a bootstrap script):

1. Create a monitor user (a system account, not a real human).
   This might require a new email address, or email alias.
   The user should be a normal user (not an admin).
   Get their ID from looking at the user list in the Site Admin
   section and going to the view page. The UUID is the last segment
   of the URL - `/admin/user/<UUID>`

2. Create the monitor assembly. **TODO (Doctor Chewie):** spell out
   the Assembly + AssemblyGSheet + SelectionSettings +
   UserAssemblyRole sequence with concrete tab names once we settle
   on them.

3. Add the monitor user to the monitor assembly with the "Assembly Manager"
   role.

4. Set the IDs in the environment's `.env`:

   ```bash
   MONITOR_ASSEMBLY_ID=<assembly UUID>
   # maybe record the user email in a comment, to help find them
   MONITOR_USER_ID=<user UUID>
   ```

5. Restart the application + Celery worker + Celery beat so they
   pick up the new env vars.

### Wiring into deploy scripts

After a successful deploy, run `opendlp monitor run-selection` to
verify the system is healthy end-to-end:

```bash
# In your deploy script, after the new container/version is running:
opendlp monitor run-selection
```

A non-zero exit indicates the new deploy can't actually run a
selection — abort the rollout / roll back.

## Troubleshooting

### `/health/monitor_selection` returns 500 with status `FAILED`

`FAILED` means the most recent runs have all failed (at least the
consecutive-failure threshold in a row). The
`monitor_selection_recent_failures` array lists the streak with an
`error_class` per run, and `monitor_selection_message` shows the
latest error (eg. `GoogleSheetConfigNotFoundError`, `InvalidSelection`,
`InsufficientPermissions`). Common causes:

- **Service account permissions.** The most common cause: the
  Google service-account email lost edit access to the monitor
  sheet. Re-share the sheet with the service-account email shown
  by `/health` (`service_account_email`) and run the CLI manually
  to confirm recovery.
- **Sortition algorithm regression.** A library upgrade introduced
  an `InfeasibleQuotasError` or similar against the fixed monitor
  data. Roll back the upgrade or update the source CSVs to match.
- **Tab-naming drift.** `delete_old_output_tabs` couldn't find any
  tabs, or found tabs it couldn't delete. Inspect the monitor sheet
  manually and reconcile.

### `/health/monitor_selection` returns 200 with status `DEGRADED`

At least one recent run failed, but not enough in a row to go red.
Inspect `monitor_selection_recent_failures` for the error classes.
This is expected for transient blips; if it persists it will escalate
to `FAILED` once the consecutive-failure threshold is reached.

### `/health/monitor_selection` returns 200 with status `PENDING` for hours

The beat task didn't return — the worker is wedged. Check
`opendlp celery list-tasks` and Celery worker logs.

### `/health/monitor_selection` returns 500 with status `NOT_CONFIGURED`

Set `MONITOR_ASSEMBLY_ID` and `MONITOR_USER_ID` in the environment
(both are required) and restart.
