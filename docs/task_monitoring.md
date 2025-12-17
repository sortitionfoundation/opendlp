# Plan: Task Monitoring and Failure Detection for Celery Selection Tasks

## Problem Statement

When Celery tasks die unexpectedly (e.g., worker crash, out-of-memory kill), the SelectionRunRecord remains in RUNNING status indefinitely. Users see a perpetually "running" task with no updates, creating confusion and preventing retries.

## Goals

1. Detect when tasks have died/stopped unexpectedly
2. Automatically update SelectionRunRecord status to FAILED when detected
3. Provide clear user messaging while logging technical details
4. Prevent orphaned records from accumulating
5. Support configurable timeouts for long-running tasks

## Architecture Overview

The solution uses a **multi-layered approach**:

1. **Progress endpoint checks** (reactive) - Check Celery state when polling
2. **Celery failure callbacks** (proactive for graceful failures) - Update status when task code raises exceptions
3. **Periodic cleanup job** (proactive for hard crashes) - Scan for orphaned tasks before Celery forgets
4. **Task timeout enforcement** (preventative) - Kill runaway tasks automatically

---

## Component 1: Enhanced Progress Endpoint (REQUIRED)

### Changes to `gsheet_select_progress()` (gsheets.py:237)

**Current behavior:** Simply reads SelectionRunRecord from database and renders template

**New behavior:**

1. Check SelectionRunRecord status
2. If status is PENDING or RUNNING, query Celery for task state
3. If Celery state indicates failure/death, update SelectionRunRecord to FAILED
4. Render template with updated status

### Implementation Details

```python
def gsheet_select_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return progress fragment for HTMX polling of Google Sheets selection task status."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

            # NEW: Check task health before getting status
            check_and_update_task_health(uow, run_id)

            result = get_selection_run_status(uow, run_id)
        # ... rest of function
```

### New Service Layer Function

**File:** `src/opendlp/service_layer/sortition.py`

```python
def check_and_update_task_health(
    uow: AbstractUnitOfWork,
    task_id: uuid.UUID,
    timeout_hours: int | None = None
) -> None:
    """
    Check if a task is still alive and update its status if it has died.

    Only checks tasks in PENDING or RUNNING state.
    Handles multiple failure scenarios:
    - Task is PENDING but Celery says it FAILED/REVOKED/REJECTED
    - Task is RUNNING but Celery has no record (>24hrs old, died)
    - Task is RUNNING but Celery says FAILURE/REVOKED/REJECTED
    - Task exceeded timeout (if configured)

    Args:
        uow: Unit of work for database operations
        task_id: UUID of the task (SelectionRunRecord.task_id)
        timeout_hours: Optional timeout in hours (overrides env config)
    """
    run_record = uow.selection_run_records.get_by_task_id(task_id)

    if not run_record or run_record.has_finished:
        return  # Nothing to check

    # Check timeout first
    timeout_hrs = timeout_hours or config.get_task_timeout_hours()
    if timeout_hrs and run_record.created_at:
        elapsed = datetime.now(UTC) - run_record.created_at
        if elapsed.total_seconds() > timeout_hrs * 3600:
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg="Task exceeded timeout",
                technical_msg=f"Task timed out after {timeout_hrs} hours",
                celery_state="TIMEOUT"
            )
            return

    # Query Celery for task state
    celery_result = app.app.AsyncResult(run_record.celery_task_id)
    celery_state = celery_result.state

    # Log current state for debugging
    current_app.logger.debug(
        f"Task health check: run_id={task_id}, "
        f"db_status={run_record.status.value}, "
        f"celery_state={celery_state}, "
        f"celery_id={run_record.celery_task_id}"
    )

    # Decision matrix based on DB status and Celery state
    if run_record.is_pending:
        if celery_state in ('FAILURE', 'REVOKED', 'REJECTED'):
            # Task failed before it even started running
            exc_info = _extract_exception_info(celery_result)
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg="Task failed to start",
                technical_msg=f"Celery state: {celery_state}, Exception: {exc_info}",
                celery_state=celery_state
            )

    elif run_record.is_running:
        if celery_state in ('FAILURE', 'REVOKED', 'REJECTED'):
            # Task crashed or was killed
            exc_info = _extract_exception_info(celery_result)
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg="Task stopped unexpectedly",
                technical_msg=f"Celery state: {celery_state}, Exception: {exc_info}",
                celery_state=celery_state
            )

        elif celery_state == 'PENDING' and run_record.celery_task_id:
            # Celery has forgotten the task (likely >24hrs) but DB says RUNNING
            # This means the worker died without updating status
            _mark_task_as_failed(
                uow,
                run_record,
                error_msg="Task stopped unexpectedly",
                technical_msg=(
                    "Task shows RUNNING in database but Celery has no record. "
                    "Worker likely crashed or was killed."
                ),
                celery_state="UNKNOWN"
            )

        # SUCCESS and STARTED states are fine, let normal polling handle them


def _mark_task_as_failed(
    uow: AbstractUnitOfWork,
    run_record: SelectionRunRecord,
    error_msg: str,
    technical_msg: str,
    celery_state: str
) -> None:
    """
    Update a SelectionRunRecord to FAILED status with error details.

    Args:
        uow: Unit of work for database operations
        run_record: The record to update
        error_msg: User-friendly error message
        technical_msg: Technical details for logs
        celery_state: The Celery state that triggered this failure
    """
    # Log technical details
    current_app.logger.warning(
        f"Marking task as failed: run_id={run_record.task_id}, "
        f"celery_id={run_record.celery_task_id}, "
        f"celery_state={celery_state}, "
        f"details={technical_msg}"
    )

    # Update record with user-friendly message
    run_record.status = SelectionRunStatus.FAILED
    run_record.error_message = (
        f"{error_msg}. Please contact the administrators if this problem persists."
    )
    run_record.log_messages.append(f"ERROR: {error_msg}")
    run_record.completed_at = datetime.now(UTC)
    flag_modified(run_record, "log_messages")

    uow.selection_run_records.add(run_record)
    uow.commit()


def _extract_exception_info(celery_result: AsyncResult) -> str:
    """Extract exception information from a failed Celery result."""
    try:
        if celery_result.info and isinstance(celery_result.info, Exception):
            return str(celery_result.info)
        elif celery_result.info and isinstance(celery_result.info, dict):
            return celery_result.info.get('exc_message', 'No exception message')
        else:
            return 'No exception info available'
    except Exception:
        return 'Could not extract exception info'
```

### Configuration Addition

**File:** `src/opendlp/config.py`

```python
def get_task_timeout_hours() -> int | None:
    """
    Get task timeout in hours from environment.
    Returns None if not set (no timeout).
    """
    timeout_str = os.environ.get("TASK_TIMEOUT_HOURS", "")
    if not timeout_str:
        return None
    try:
        timeout = int(timeout_str)
        if timeout <= 0:
            raise ValueError("TASK_TIMEOUT_HOURS must be positive")
        return timeout
    except ValueError as e:
        logging.warning(f"Invalid TASK_TIMEOUT_HOURS value '{timeout_str}': {e}")
        return None
```

**Pros:**

- Immediate detection when user is actively polling
- No additional infrastructure needed
- Simple to implement and test
- Handles the "user waiting for updates" case perfectly

**Cons:**

- Only detects failures when someone is watching
- Won't catch failures that happen when no one is polling
- Adds small overhead to each progress poll

---

## Component 2: Celery Failure Callbacks (RECOMMENDED)

### Changes to Task Definitions

**File:** `src/opendlp/entrypoints/celery/tasks.py`

```python
def _on_task_failure(
    self: Task,
    exc: Exception,
    task_id: str,  # This is celery_task_id
    args: tuple,
    kwargs: dict,
    einfo: Any
) -> None:
    """
    Callback executed when a Celery task fails.

    Note: This only fires if the worker process is alive when the exception occurs.
    Hard crashes (SIGKILL, OOM) won't trigger this callback.
    """
    # Extract our task_id from kwargs (the SelectionRunRecord task_id)
    our_task_id = kwargs.get('task_id')
    if not our_task_id:
        logging.error(f"Task {task_id} failed but no task_id in kwargs")
        return

    session_factory = kwargs.get('session_factory')

    # Format error details
    error_msg = f"Task failed with exception: {type(exc).__name__}"
    technical_msg = f"{type(exc).__name__}: {str(exc)}\n{einfo}"

    logging.error(
        f"Celery task failure callback: our_task_id={our_task_id}, "
        f"celery_task_id={task_id}, exception={technical_msg}"
    )

    # Update the database record
    try:
        with bootstrap(session_factory=session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(our_task_id)
            if record and not record.has_finished:
                record.status = SelectionRunStatus.FAILED
                record.error_message = (
                    "Task failed unexpectedly. "
                    "Please contact the administrators if this problem persists."
                )
                record.log_messages.append(f"ERROR: {error_msg}")
                record.completed_at = datetime.now(UTC)
                flag_modified(record, "log_messages")
                uow.commit()
    except Exception as update_exc:
        logging.error(
            f"Failed to update task record in failure callback: {update_exc}"
        )


@app.task(bind=True, on_failure=_on_task_failure)
def load_gsheet(...):
    # existing implementation
    ...

@app.task(bind=True, on_failure=_on_task_failure)
def run_select(...):
    # existing implementation
    ...

@app.task(bind=True, on_failure=_on_task_failure)
def manage_old_tabs(...):
    # existing implementation
    ...
```

**Pros:**

- Catches "graceful" failures immediately (unhandled exceptions in task code)
- Updates status before Celery forgets about the task
- Centralizes failure handling logic
- Provides detailed exception information

**Cons:**

- Doesn't help with hard crashes (SIGKILL, OOM, worker machine dies)
- Requires callback to successfully connect to database
- Adds complexity to task definitions

**Trade-off:** This is "defense in depth" - it handles exceptions/crashes that happen within Python, but not when the entire process dies. Since it's relatively easy to add and helps with a subset of failures, I recommend including it.

---

## Component 3: Periodic Cleanup Job (RECOMMENDED)

### New Celery Beat Task

**File:** `src/opendlp/entrypoints/celery/tasks.py`

```python
@app.task
def cleanup_orphaned_tasks(session_factory: sessionmaker | None = None) -> dict[str, int]:
    """
    Periodic task to find and mark orphaned selection tasks as FAILED.

    Scans all PENDING/RUNNING tasks and checks their Celery status.
    This catches failures that weren't detected by polling or callbacks.

    Returns:
        Dict with counts of tasks checked, marked failed, etc.
    """
    from opendlp.service_layer.sortition import check_and_update_task_health

    stats = {
        'checked': 0,
        'marked_failed': 0,
        'errors': 0
    }

    try:
        with bootstrap(session_factory=session_factory) as uow:
            # Find all non-finished tasks
            pending_or_running = uow.selection_run_records.get_all_unfinished()
            stats['checked'] = len(pending_or_running)

            for record in pending_or_running:
                try:
                    initial_status = record.status
                    check_and_update_task_health(uow, record.task_id)

                    # Check if it was marked as failed
                    updated_record = uow.selection_run_records.get_by_task_id(record.task_id)
                    if updated_record and initial_status != updated_record.status:
                        if updated_record.is_failed:
                            stats['marked_failed'] += 1

                except Exception as e:
                    stats['errors'] += 1
                    logging.error(
                        f"Error checking task health for {record.task_id}: {e}"
                    )

        logging.info(
            f"Orphaned task cleanup completed: {stats['checked']} checked, "
            f"{stats['marked_failed']} marked failed, {stats['errors']} errors"
        )

    except Exception as e:
        logging.error(f"Orphaned task cleanup failed: {e}")
        stats['errors'] += 1

    return stats
```

### Repository Addition

**File:** `src/opendlp/service_layer/repositories.py`

```python
class SelectionRunRecordRepository(AbstractRepository):
    # ... existing methods ...

    def get_all_unfinished(self) -> list[SelectionRunRecord]:
        """Get all SelectionRunRecords that are PENDING or RUNNING."""
        return (
            self.session.query(SelectionRunRecord)
            .filter(
                orm.selection_run_records.c.status.in_([
                    SelectionRunStatus.PENDING.value,
                    SelectionRunStatus.RUNNING.value
                ])
            )
            .all()
        )
```

### Celery Beat Configuration

**File:** `src/opendlp/entrypoints/celery/app.py`

```python
def get_celery_app(redis_host: str = "", redis_port: int = 0) -> Celery:
    # ... existing code ...

    # Configure periodic task schedule
    app.conf.beat_schedule = {
        'cleanup-orphaned-tasks': {
            'task': 'opendlp.entrypoints.celery.tasks.cleanup_orphaned_tasks',
            'schedule': 300.0,  # Run every 5 minutes
        },
    }

    return app
```

### Running Celery Beat

**Documentation update needed:** Users must run Celery Beat in addition to workers.

```bash
# Start Celery worker (existing)
celery -A opendlp.entrypoints.celery.app worker --loglevel=info

# Start Celery Beat scheduler (new)
celery -A opendlp.entrypoints.celery.app beat --loglevel=info
```

**Docker Compose Update:** Add a beat service to `compose.yaml`

```yaml
celery-beat:
  build: .
  command: celery -A opendlp.entrypoints.celery.app beat --loglevel=info
  environment:
    - DB_HOST=postgres
    - REDIS_HOST=redis
  depends_on:
    - postgres
    - redis
```

**Pros:**

- Catches failures even when no one is polling
- Runs before Celery forgets tasks (can log actual Celery state)
- Prevents accumulation of orphaned records
- Configurable frequency

**Cons:**

- Requires running Celery Beat (additional process)
- Adds infrastructure complexity
- Not immediate (runs on schedule)
- Small overhead scanning database periodically

**Trade-off:** This provides the best "safety net" for hard crashes. Recommended for production use.

---

## Component 4: Task Timeout Enforcement (OPTIONAL)

### Using Celery's Built-in Timeouts

Celery supports task-level timeouts that SIGTERM/SIGKILL the worker after a time limit.

**File:** `src/opendlp/entrypoints/celery/tasks.py`

```python
def _get_task_timeout_seconds() -> int | None:
    """Get timeout in seconds from config, or None for no timeout."""
    timeout_hours = config.get_task_timeout_hours()
    if timeout_hours:
        return timeout_hours * 3600
    return None


@app.task(
    bind=True,
    on_failure=_on_task_failure,
    time_limit=_get_task_timeout_seconds(),  # Hard timeout (SIGKILL)
    soft_time_limit=_get_task_timeout_seconds() - 60 if _get_task_timeout_seconds() else None  # Soft timeout (exception)
)
def run_select(...):
    ...
```

**However**, this has issues:

- Kills the entire worker process (not just the task)
- Doesn't give task a chance to clean up
- Can corrupt state if task is mid-database write

### Alternative: Timeout in Health Check

The `check_and_update_task_health()` function in Component 1 already implements timeout checking based on `created_at` timestamp. This is safer because:

- Doesn't kill processes
- Just marks task as failed in database
- User can see timeout error message
- No risk of data corruption

**Recommendation:** Use the health check timeout approach, not Celery's time_limit.

**Pros:**

- Prevents tasks from running forever
- Configurable per-environment
- User gets clear timeout message

**Cons:**

- Task continues consuming resources until detected
- Doesn't free up worker capacity immediately

---

## Environment Variable Configuration

Add to `.env` files:

```bash
# Task timeout in hours (optional, no timeout if not set)
# Tasks running longer than this will be marked as failed
TASK_TIMEOUT_HOURS=6

# Cleanup job frequency in seconds (only needed if using Component 3)
ORPHAN_CLEANUP_INTERVAL=300  # 5 minutes
```

---

## Implementation Priority & Dependencies

### Phase 1: Minimum Viable Solution (MUST HAVE)

1. Component 1: Enhanced Progress Endpoint
   - Implement `check_and_update_task_health()`
   - Add timeout configuration
   - Update progress endpoints to call health check

**Effort:** ~3-4 hours
**Value:** Solves immediate user pain when they're watching tasks

### Phase 2: Graceful Failure Handling (SHOULD HAVE)

2. Component 2: Celery Failure Callbacks
   - Implement `_on_task_failure()` callback
   - Register callbacks on all task decorators

**Effort:** ~2 hours
**Value:** Catches Python exceptions/crashes before Celery forgets

### Phase 3: Full Coverage (NICE TO HAVE)

3. Component 3: Periodic Cleanup Job
   - Implement `cleanup_orphaned_tasks()` task
   - Add repository method `get_all_unfinished()`
   - Configure Celery Beat
   - Update Docker Compose / deployment docs

**Effort:** ~4-5 hours
**Value:** Safety net for hard crashes, prevents orphan accumulation

---

## Testing Strategy

### Unit Tests

**File:** `tests/unit/service_layer/test_sortition.py`

```python
def test_check_task_health_marks_pending_failed_task():
    """Test detection of task that failed before starting."""
    # Create record in PENDING state
    # Mock Celery to return FAILURE state
    # Call check_and_update_task_health()
    # Assert record is now FAILED with appropriate error message

def test_check_task_health_marks_running_crashed_task():
    """Test detection of task that crashed while running."""
    # Create record in RUNNING state
    # Mock Celery to return PENDING (forgotten) state
    # Call check_and_update_task_health()
    # Assert record is now FAILED

def test_check_task_health_marks_timed_out_task():
    """Test timeout detection."""
    # Create record with old created_at timestamp
    # Call check_and_update_task_health() with timeout_hours=1
    # Assert record is marked FAILED due to timeout

def test_check_task_health_ignores_completed_tasks():
    """Test that finished tasks aren't checked."""
    # Create record in COMPLETED state
    # Call check_and_update_task_health()
    # Assert no changes made
```

### Integration Tests

**File:** `tests/integration/test_celery_tasks.py`

```python
def test_task_failure_callback_updates_record():
    """Test on_failure callback updates database."""
    # Start a task designed to fail
    # Wait for completion
    # Assert SelectionRunRecord shows FAILED status
    # Assert error_message is populated

def test_cleanup_orphaned_tasks_finds_old_tasks():
    """Test periodic cleanup finds and marks orphaned tasks."""
    # Create some old RUNNING records
    # Mock Celery to return PENDING for them
    # Run cleanup_orphaned_tasks()
    # Assert records are marked FAILED
```

### End-to-End Tests

**File:** `tests/e2e/test_selection_monitoring.py`

```python
def test_user_sees_failure_when_task_crashes():
    """Test user polling sees updated status."""
    # Start selection task
    # Kill celery worker
    # Poll progress endpoint
    # Assert page shows FAILED status
    # Assert user-friendly error message displayed
```

---

## Documentation Updates

1. **README.md**: Document new environment variables
2. **docs/deployment.md**: Add Celery Beat setup instructions
3. **CLAUDE.md**: Update with new task monitoring architecture

---

## Rollout Plan

1. **Development**: Implement Phase 1, test thoroughly
2. **Staging**: Deploy Phase 1, monitor for detection accuracy
3. **Production**: Deploy Phase 1 + 2 together
4. **Later**: Add Phase 3 (cleanup job) once Celery Beat is in infrastructure

---

## Open Questions for Discussion

1. **Cleanup frequency**: 5 minutes seems reasonable. Too frequent?
2. **Timeout default**: Should there be a default timeout (e.g., 6 hours) or require explicit configuration?
3. **User notification**: Should users be emailed when tasks fail? (Out of scope for this plan)
4. **Retry mechanism**: Should failed tasks be auto-retried? (Out of scope for this plan)
5. **Celery result expiry**: Currently 24 hours. Should we increase this? (Celery config)

---

## Summary

This plan provides **defense in depth** with three complementary mechanisms:

1. ✅ **Progress endpoint checks** - Catches failures when users are watching
2. ✅ **Failure callbacks** - Catches Python exceptions immediately
3. ✅ **Periodic cleanup** - Safety net for hard crashes

**Minimum implementation** (Phase 1) solves your immediate problem. **Full implementation** (all phases) provides robust monitoring that will catch any failure scenario.

The timeout checking is built into the health check, so no dangerous Celery time_limit configuration needed.

**Estimated total effort:** 9-11 hours for full implementation across all three phases.

---

## Implementation Status

### ✅ Phase 1: Enhanced Progress Endpoint (COMPLETED)

**Implemented:**

- `check_and_update_task_health()` function in `src/opendlp/service_layer/sortition.py`
- `get_task_timeout_hours()` config function in `src/opendlp/config.py`
- Helper functions `_mark_task_as_failed()` and `_extract_exception_info()`
- Updated progress endpoints in `src/opendlp/entrypoints/blueprints/gsheets.py`:
  - `gsheet_select_progress()`
  - `gsheet_replace_progress()`
  - `gsheet_manage_tabs_progress()`
- Unit tests in `tests/unit/test_config.py` and `tests/unit/test_sortition_service.py`
- All 331 unit tests passing

**Configuration:**

- Environment variable: `TASK_TIMEOUT_HOURS` (default: 24 hours)

### ✅ Phase 2: Celery Failure Callbacks (COMPLETED)

**Implemented:**

- `_on_task_failure()` callback function in `src/opendlp/entrypoints/celery/tasks.py`
- Registered callback on all 3 Celery tasks:
  - `load_gsheet()`
  - `run_select()`
  - `manage_old_tabs()`
- Integration tests in `tests/integration/test_celery_tasks.py::TestOnTaskFailure`
- All 16 integration tests passing

**Note:** Callbacks only fire for graceful failures (exceptions), not hard crashes (SIGKILL, OOM).

### ✅ Phase 3: Periodic Cleanup Job (COMPLETED)

**Implemented:**

- `cleanup_orphaned_tasks()` Celery task in `src/opendlp/entrypoints/celery/tasks.py`
- Repository method `get_all_unfinished()` in:
  - Abstract interface: `src/opendlp/service_layer/repositories.py`
  - SQL implementation: `src/opendlp/adapters/sql_repository.py`
  - Fake implementation: `tests/fakes.py`
- Celery Beat schedule configuration in `src/opendlp/entrypoints/celery/app.py`
  - Runs every 5 minutes (300 seconds)
- Docker Compose services:
  - `app_celery_beat` in `compose.yaml`
  - `app_celery_beat` in `compose.production.yaml`
- Integration tests in `tests/integration/test_celery_tasks.py::TestCleanupOrphanedTasks`

**Deployment:**
To enable the periodic cleanup job in production, start the Celery Beat service:

```bash
# Development
just start-docker  # Automatically includes app_celery_beat service

# Production
docker compose -f compose.production.yaml up -d
```

The cleanup job will:

1. Run every 5 minutes
2. Check all PENDING and RUNNING tasks
3. Mark orphaned tasks as FAILED with appropriate error messages
4. Log all actions for monitoring

**Monitoring:**
Check Celery Beat logs to verify cleanup is running:

```bash
docker compose logs app_celery_beat -f
```

You should see log messages every 5 minutes:

- "Starting cleanup_orphaned_tasks periodic job"
- "Found N unfinished task(s) to check"
- "Cleanup completed: {'checked': N, 'marked_failed': M, 'errors': 0}"
