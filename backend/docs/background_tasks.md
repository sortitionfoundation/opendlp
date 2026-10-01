# Background Tasks

OpenDLP uses Celery for background task processing, enabling long-running operations like stratified selections to run asynchronously without blocking the web interface.

## Overview

The background task system provides:

- **Asynchronous execution** - Long-running tasks don't block HTTP requests
- **Progress tracking** - Real-time status updates for running tasks
- **Failure detection** - Automatic detection and handling of task failures
- **Timeout enforcement** - Configurable timeouts to prevent runaway tasks
- **Task monitoring** - Health checks and cleanup for orphaned tasks

## Architecture

### Components

1. **Celery Workers** - Execute background tasks
2. **Celery Beat** - Schedules periodic tasks (cleanup, monitoring)
3. **Redis** - Message broker and result backend
4. **Flask Application** - Submits tasks and polls status
5. **PostgreSQL** - Stores task status and results

### Task Flow

```
User Action → Flask Route → Submit Celery Task → Worker Executes → Update Status → User Sees Result
                                    ↓
                              Redis Queue
```

## Task Implementation

Tasks are defined in `src/opendlp/entrypoints/celery/tasks.py`.

### Current Tasks

#### load_gsheet

Loads data from a Google Sheets spreadsheet.

**Parameters:**
- `gsheet_id` - Google Sheets spreadsheet ID
- `tab_name` - Name of the tab to load

**Status tracking:** Creates `SelectionRunRecord` with progress updates

#### run_select

Runs stratified selection algorithm on loaded data.

**Parameters:**
- `selection_params` - Selection configuration
- `feature_data` - Population features
- `quota_data` - Target quotas

**Status tracking:** Creates `SelectionRunRecord` with progress updates

#### manage_old_tabs

Archives or deletes old Google Sheets tabs.

**Parameters:**
- `gsheet_id` - Google Sheets spreadsheet ID
- `action` - "archive" or "delete"

**Status tracking:** Creates `SelectionRunRecord` with progress updates

#### auto_export_respondents

Rewrites an assembly's respondent export tab in Google Sheets after its
respondents, or their schema, changed. Only runs for assemblies where an
organiser has ticked "Automatically export" on a successful Google Sheets
export.

**How it is queued:** every service that changes what the export would
contain calls `respondent_auto_export.request_auto_export(uow, assembly_id)`.
That sets a per-assembly `auto_export_pending:<id>` key in Redis (`SET NX`)
and queues the task with a 30-second countdown; while the key is set, further
requests are folded into the queued run. The countdown also lets the caller's
transaction commit before the task reads. Under continuous change an assembly
exports at most about once every 30 seconds. `request_auto_export` never
raises - a failure to schedule is logged and the change that asked for it
goes ahead.

**What it does:** takes a per-assembly Redis lock (re-queues itself if another
run holds it), deletes the pending key, re-reads the saved config (so a run
queued before the organiser pressed "Stop automatic export" does nothing),
and writes every respondent matching the saved status filter to the saved
tab. There is no `SelectionRunRecord` and no acting user.

Deleting the pending key before the read means a change that asks for an
export after the delete gets a fresh run. One small gap remains: a change
that asked just *before* the delete (so was folded into this run) but whose
transaction commits *after* the read is missed until the next change. The
window is the few milliseconds between a service calling
`request_auto_export` and its entrypoint committing, and it heals itself on
the next change. The proper fix is to request the export after commit, which
is the domain-events work noted in `docs/architecture.md`.

**Failures:** an `ExportTargetError` (sheet unshared, deleted, API error or
rate limit) is retried up to 3 times with exponential backoff and jitter.
Each attempt logs a warning with the `assembly_id`; the last one logs an
error. Nothing is shown to the organiser yet - recording failures in the
database so they can be seen in the UI, and switching auto-export off after
repeated permanent failures, are follow-up work.

**Parameters:**
- `assembly_id` - The assembly whose respondents to export
- `session_factory` - Optional, for tests
- `target_factory` - Builds the Google Sheets target from a URL; tests pass a fake
- `redis_client` - Optional, for tests

#### cleanup_orphaned_tasks (Periodic)

Automatically detects and marks failed tasks as FAILED.

**Frequency:** Every 5 minutes

**Purpose:** Catches tasks that crashed without updating their status

## Task Status Tracking

Task status is stored in `SelectionRunRecord` domain objects with the following states:

- **PENDING** - Task submitted but not yet started
- **RUNNING** - Task currently executing
- **COMPLETED** - Task finished successfully
- **FAILED** - Task failed or crashed

### Status Fields

- `status` - Current task state
- `progress_percentage` - 0-100 completion percentage
- `log_messages` - List of progress messages
- `error_message` - User-friendly error description
- `created_at` - Task submission time
- `completed_at` - Task completion/failure time
- `celery_task_id` - Celery task identifier

## Task Timeout Configuration

Tasks can be configured with a timeout to prevent them from running indefinitely:

```bash
# In .env or environment variables
TASK_TIMEOUT_HOURS=24
```

When a task exceeds the timeout, it is automatically marked as FAILED.

**Default:** 24 hours if not specified

## Task Failure Detection

OpenDLP implements multiple layers of failure detection to handle different failure scenarios:

### 1. Progress Endpoint Checks (Reactive)

When users poll for task progress, the system checks Celery task state and updates the database if the task has failed.

**Handles:**
- Tasks that failed gracefully
- Tasks that timed out
- Tasks forgotten by Celery

### 2. Celery Failure Callbacks (Proactive)

Tasks register failure callbacks that automatically update the database when a Python exception occurs.

**Handles:**
- Unhandled exceptions in task code
- Graceful failures with stack traces

### 3. Periodic Cleanup Job (Safety Net)

A scheduled task runs every 5 minutes to scan for orphaned tasks and mark them as FAILED.

**Handles:**
- Hard crashes (SIGKILL, OOM)
- Worker crashes
- Tasks that died without updating status

**Implementation:** See `../docs/task_monitoring.md` for detailed architecture and implementation plan.

## Running Background Tasks

### Development

Start Celery worker:

```bash
# Terminal 1: Start Flask app
just run

# Terminal 2: Start Celery worker
celery -A opendlp.entrypoints.celery.app worker --loglevel=info

# Terminal 3: Start Celery beat (for periodic tasks)
celery -A opendlp.entrypoints.celery.app beat --loglevel=info
```

### Production with Docker

All services are managed by Docker Compose:

```bash
docker compose -f compose.production.yaml up -d
```

Services:
- `app` - Flask application (Gunicorn)
- `app_celery` - Celery worker
- `app_celery_beat` - Celery beat scheduler
- `postgres` - PostgreSQL database
- `redis` - Redis message broker

See [docs/docker.md](docker.md) for detailed Docker setup.

## Monitoring Tasks

### View Task Status

In Flask routes or templates:

```python
from opendlp.bootstrap import get_flask_uow
from opendlp.service_layer.sortition import get_selection_run_status

with get_flask_uow() as uow:
    status = get_selection_run_status(uow, task_id)
    print(f"Status: {status.status}")
    print(f"Progress: {status.progress_percentage}%")
    print(f"Messages: {status.log_messages}")
```

### View Celery Logs

```bash
# Development
# Check terminal running celery worker

# Production (Docker)
docker compose -f compose.production.yaml logs app_celery -f
docker compose -f compose.production.yaml logs app_celery_beat -f
```

### Check Task Health

The cleanup job logs task health checks:

```bash
docker compose -f compose.production.yaml logs app_celery_beat | grep cleanup
```

## Error Handling

### User-Facing Errors

When tasks fail, users see:
- Clear error message in the UI
- Option to retry the operation
- Link to contact support if issue persists

Error messages are internationalized and use translation codes from the sortition-algorithms library. See [docs/sortition_error_translations.md](sortition_error_translations.md).

### Technical Errors

Technical details are logged but not shown to users:
- Full stack traces in Celery logs
- Celery task state information
- Database query errors
- External service failures

## Performance Considerations

### Task Concurrency

Configure worker concurrency based on server resources:

```bash
# 4 concurrent tasks
celery -A opendlp.entrypoints.celery.app worker --concurrency=4

# Auto-scale based on load
celery -A opendlp.entrypoints.celery.app worker --autoscale=10,3
```

### Memory Usage

Long-running selection tasks can use significant memory. Monitor worker memory and adjust Docker memory limits if needed:

```yaml
# compose.production.yaml
app_celery:
  mem_limit: 2g
  mem_reservation: 1g
```

### Task Retries

Tasks can be configured to retry on failure:

```python
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def my_task(self):
    try:
        # Task code
        pass
    except Exception as exc:
        # Retry after 60 seconds
        raise self.retry(exc=exc)
```

## Best Practices

1. **Keep tasks idempotent** - Tasks should be safe to retry
2. **Update progress frequently** - Give users feedback on long-running tasks
3. **Handle errors gracefully** - Catch exceptions and return user-friendly messages
4. **Set reasonable timeouts** - Prevent tasks from running forever
5. **Monitor task queue depth** - Alert if too many tasks are pending
6. **Log important events** - Make troubleshooting easier

## Further Reading

- Task monitoring implementation: `../docs/task_monitoring.md`
- Celery documentation: https://docs.celeryproject.org/
- Redis configuration: https://redis.io/documentation
- Architecture decision record: `../docs/adr/0012-background-task-runner.md`
