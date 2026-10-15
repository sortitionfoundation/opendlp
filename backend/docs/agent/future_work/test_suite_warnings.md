# Future work: warnings in the non-BDD test run

`just test-nobdd` passes, but ends with four warnings. They were spotted on
`767-rich-text-editor`, and none comes from that branch's work. Each section is
written to be pasted into an issue. The first and last point at small bugs in
application code; the middle two are tidying.

## Deleting a registration page deletes its HTML source twice

### Problem

```
tests/e2e/test_backoffice_registration.py::test_delete_assembly_registration_page_success
  src/opendlp/service_layer/unit_of_work.py:245: SAWarning: DELETE statement on table
  'registration_page_html_sources' expected to delete 1 row(s); 0 were matched.
```

`delete_registration_page` in
`src/opendlp/service_layer/registration_page_service.py` deletes the page's HTML
source and then the page, both through `session.delete()`. The mapping has no
relationship between the two, so SQLAlchemy doesn't know which to delete
first, and here it deletes the page first. The foreign key
`registration_page_html_sources.page_id` has `ondelete="CASCADE"`, so Postgres
removes the source along with the page. SQLAlchemy's own `DELETE` of the source
then matches nothing, and it warns.

The result is right, because both rows are gone. But the warning shows up in
production logs on every page delete. And which order SQLAlchemy picks isn't
guaranteed, so the code works partly by luck.

### Possible fixes

- Rely on the cascade: delete only the page, and drop the explicit source
  delete. This is the smallest change, but it hides the source's removal in
  the schema.
- Or keep both deletes and make the order explicit: delete the source,
  `session.flush()`, then delete the page.

Either way, add an assertion that the source row is gone, and make the e2e test
fail on `SAWarning` (for example with `pytest.mark.filterwarnings("error::...")`)
so it can't come back silently.

## An integration test leaves a clashing instance in the session

### Problem

```
tests/integration/test_orm.py::TestSelectionRunRecordORM::test_selection_run_record_task_id_primary_key
  tests/integration/test_orm.py:1102: SAWarning: New instance <SelectionRunRecord ...> with identity key
  (...) conflicts with persistent instance <SelectionRunRecord ...>
```

The test checks that `task_id` is a primary key by adding a second
`SelectionRunRecord` with the same `task_id` and expecting `IntegrityError`.
The first record is still in the session's identity map, so SQLAlchemy warns
about the clash before Postgres gets the chance to refuse it.

### Possible fix

Call `postgres_session.expunge(record1)` (or `expunge_all()`) after the first
commit, so the second insert reaches the database and the test checks the
constraint, not the identity map. Or insert the second row with a Core
`insert()` statement.

## `RunReport.add_lines()` is deprecated

### Problem

```
tests/integration/test_celery_tasks.py::TestLoadGSheetTask::test_load_gsheet_with_invalid_csv
  src/opendlp/entrypoints/celery/tasks.py:433: DeprecationWarning: add_lines() is deprecated.
  Functions should return RunReport instead of list[str], and use add_report() to merge them.
```

`add_lines()` comes from the `sortition-algorithms` library. `tasks.py` calls it
six times (lines 433, 541, 622, 739, 802 and 1156), each to add a traceback to
the run report. The warning will become an error when the library removes the
method.

The `TODO` above the first call says more than the deprecation does: a full
traceback in a report that organisers see is an internal detail. The
traceback belongs in the logs, and the report should carry a short "an error
occurred, contact the admins" message. See the JSON-response and logging
rules in `CLAUDE.md`, which make the same point for API responses.

### Possible fix

Log the traceback with `logger.exception(...)`, and stop adding it to the
report. Where the report does need several lines, build a `RunReport` and merge
it with `add_report()`.

## `get_selection_run_status` builds an `AsyncResult` for an empty task id

### Problem

```
tests/unit/test_sortition_service.py::TestGetSelectionRunStatus::test_get_selection_run_status_exists
  PytestUnraisableExceptionWarning: Exception ignored in: <function AsyncResult.__del__ ...>
  ValueError: task_id must not be empty. Got  instead.
```

`get_selection_run_status` in `src/opendlp/service_layer/sortition.py` (around
line 814) calls `app.app.AsyncResult(run_record.celery_task_id)` without
checking the id first. The test's record has no `celery_task_id`, so it is
`""`. Constructing the result works, and `celery_result.id` is falsy, so the
code skips it. But when the object is garbage-collected, Celery's
`AsyncResult.__del__` asks the Redis backend to cancel the empty id, which
raises. Python can only report that, as an unraisable exception.

`_get_celery_task_state` in the same file already guards against this
(`if not run_record.celery_task_id: ... return None, ""`). The status function
doesn't. A record can have no Celery id in production too, if creating the
task failed, so the same noise could reach the worker logs.

### Possible fix

Check `run_record.celery_task_id` before building the `AsyncResult`, as
`_get_celery_task_state` does. Then the `celery_result.id` test becomes
unnecessary.
