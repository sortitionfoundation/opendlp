# More adapters: email and background tasks

Status: **agreed design, not built** (2026-11-27). Doctor Chewie's answers from
the first review round are folded in and recorded under
[Decisions](#decisions). The message bus was considered and parked; see D7.

Two ports are covered here:

1. **Email.** A fake already exists. The gap is how tests get it into the code.
2. **Background tasks (Celery).** There is no port at all. The service layer
   imports the Celery task module directly, which is where the circular imports
   come from.

They share a problem: **how does an adapter reach the code that needs it**,
including an event handler, which only gets `(event, uow)`. That is covered in
[How adapters reach the code](#how-adapters-reach-the-code).

---

## 1. Email

### What exists

- `EmailAdapter` (ABC) in `src/opendlp/adapters/email.py`, with
  `ConsoleEmailAdapter` and `SMTPEmailAdapter`.
- `bootstrap.get_email_adapter()` builds one from `EMAIL_ADAPTER` on every
  call. Production refuses `console`.
- **`FakeEmailAdapter` already exists** in `tests/fakes.py:1483`. It records
  each send in `.sent` (a list of dicts), can be told to fail
  (`succeed=False`) and can report a sender address.
- Services take the adapter as a parameter (`send_confirmation_email`,
  `send_templated_email`, `send_password_reset_email`, ...). The entrypoint
  calls `get_email_adapter()` and passes it down. That part is fine.

So we have the fake already, but not the wiring.

### What is wrong with the wiring

Tests get a fake in four different ways:

| How                                                                                  | Where                                                                                                                                | Problem                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.get_email_adapter", ...)` | `test_admin_user_management.py`, `test_project_details_page.py`                                                                      | Patches the name where it was imported. A blueprint that switches from `from bootstrap import get_email_adapter` to `bootstrap.get_email_adapter()` silently stops being patched.                                                         |
| `monkeypatch.setattr(be_reg.bootstrap, "get_email_adapter", ...)`                    | `test_backoffice_registration_email.py`, `test_registration_stepper_journey.py`                                                      | The opposite import style, so the opposite fragility.                                                                                                                                                                                     |
| `patch("...registration.bootstrap.get_email_adapter", return_value=adapter)`         | `test_registration_auto_reply.py` (5 times)                                                                                          | Same as above, as a context manager.                                                                                                                                                                                                      |
| `MagicMock()` with `send_email.return_value = True`                                  | `test_email_send_service.py`, `test_email_confirmation_service.py`, `test_registration_auto_reply_service.py`, two integration files | Asserts on `call_args.kwargs[...]`, which passes whatever the signature becomes. A `MagicMock` also has every method, so a test cannot notice a call to one that does not exist. `FakeEmailAdapter` would do the same job and type-check. |

And a test that forgets to patch gets the `console` adapter, which prints to
stdout. Nothing fails; the email just goes nowhere you can assert on.

The BDD server is a separate process, so an in-memory fake cannot help it. Its
"should receive a confirmation email" step is a no-op. That is filed as
[future_work/bdd_email_file_adapter.md](../future_work/bdd_email_file_adapter.md)
(option E3 below).

### Options considered

- **E1. Register the adapter on the app, like the other factories.** Chosen.
- **E2. A `memory` value for `EMAIL_ADAPTER`**, sends landing in a module-level
  list (the Django `locmem` / Flask-Mail `outbox` pattern). Rejected: the
  module-level state needs clearing between tests, and it does not help BDD
  either.
- **E3. A `file` value for `EMAIL_ADAPTER`, for BDD.** Deferred to future work
  (D2).
- **E4. Replace the `MagicMock` adapters with `FakeEmailAdapter`.** Chosen.

### Design

**E1.** `create_app` already puts `uow_factory`,
`gsheet_export_target_factory` and `gsheet_access_client_factory` in
`app.extensions`, and tests override them. Add `email_adapter_factory` the same
way, defaulting to the config-driven builder. `bootstrap.get_email_adapter()`
reads it when there is an app context, and falls back to config otherwise (CLI,
Celery).

- `tests/conftest.py` and `tests/component/conftest.py` install a fresh
  `FakeEmailAdapter` per test, exposed as an `email_outbox` fixture. The
  component app is built once per session, so the per-test `app` fixture
  resets it, not `create_app`.
- All the import-site monkeypatches go. A test that wants a failing send sets
  `email_outbox.succeed = False`.
- "Forgot to patch" becomes impossible for Flask tests: the fake is the default.

**E4.** Mechanical: each `MagicMock()` email adapter becomes a
`FakeEmailAdapter()`, and `call_args.kwargs["to"]` becomes `adapter.sent[0]["to"]`.
Same branch as E1, so "how do I fake email" has one answer.

Stopping the old patterns coming back is covered for both ports together in
[Keeping the old patterns out](#keeping-the-old-patterns-out).

---

## 2. Background tasks (Celery)

### What exists

The service layer calls Celery directly:

| Call                                                                               | Where                                    |
| ---------------------------------------------------------------------------------- | ---------------------------------------- |
| `tasks.load_gsheet.delay(...)`                                                     | `sortition.py` x2                        |
| `tasks.run_select.delay(...)` / `.apply_async(kwargs=..., **celery_apply_kwargs)`  | `sortition.py` x2                        |
| `tasks.manage_old_tabs.delay(...)`                                                 | `sortition.py`                           |
| `tasks.run_select_from_db.delay(...)`                                              | `sortition.py` x2                        |
| `tasks.auto_export_respondents.apply_async(..., countdown=30)`                     | `respondent_auto_export.py`              |
| `app.app.AsyncResult(id)` → `.successful()`, `.state`, `.info`, `.get(timeout=10)` | `sortition.py` (status and health check) |
| `app.app.control.revoke(id, terminate=True)`                                       | `sortition.py` (cancel)                  |
| `celery_app.control.inspect()`                                                     | `blueprints/health.py`, `cli/celery.py`  |

There is a TODO above two of the dispatches saying exactly this:

```python
# Submit Celery task
# TODO: should this be behind another adapter? That comes from bootstrap?
# would be handy for unit tests
```

#### The import cycle

`service_layer/sortition.py` and `service_layer/respondent_auto_export.py`
import `opendlp.entrypoints.celery.tasks`. That is the service layer importing
an entrypoint, the wrong way round. `tasks.py` in turn needs the service layer,
so it defers three imports to call time:

```python
from opendlp.service_layer import respondent_auto_export  # noqa: PLC0415
from opendlp.service_layer.sortition import check_and_update_task_health  # noqa: PLC0415
from opendlp.service_layer.monitoring import run_monitoring_selection  # noqa: PLC0415
```

A fourth deferred import, in `UnitOfWorkEvents._handlers_for`, gives the same
chain as its reason: "handlers -> services -> celery tasks -> bootstrap ->
unit_of_work".

Importing any of those service modules also builds the Celery app (it is
created at import time in `celery/app.py`), and pulls in `tasks.py`'s imports,
which include `entrypoints.context_processors`.

#### How tests cope

- About 30 `patch("opendlp.service_layer.sortition.tasks.<task>.delay")` or
  `.apply_async` sites, mostly `tests/unit/test_sortition_service.py`, plus
  component and e2e tests.
- 16 `patch("opendlp.service_layer.sortition.app.app.AsyncResult")` sites, and
  an autouse fixture in `tests/component/conftest.py` that replaces
  `AsyncResult` with a `_NoCeleryResult` stub for every component test.
- 3 `patch(...app.app.control.revoke)` sites.
- Two hand-written result stand-ins (`_NoCeleryResult`,
  `_FinishedCeleryResult`).
- Integration tests run tasks by calling the task function directly with a
  `session_factory=` argument (`test_sortition_db_task.py`,
  `test_auto_export_task.py`).
- BDD runs a real Celery worker against Redis.

Every one of the patch strings encodes the import path
`service_layer.sortition.tasks...`, so they all break if the import moves.
That is part of why the cycle has not been fixed.

### The port

One method per task (T2, decision D3), so mypy checks every argument. The
arguments here are rich pickled objects (data sources, settings), and a typo in
a kwargs dict would otherwise only show up in a worker log. The port lives in
`src/opendlp/service_layer/task_runner.py`:

```python
#: A dispatch that has been checked and is ready to publish. Calling it sends
#: the task to the broker.
Dispatch = Callable[[], None]


class TaskRunner(ABC):
    @abstractmethod
    def load_gsheet(self, *, task_id: uuid.UUID, data_source: ..., settings: Settings) -> Dispatch: ...
    @abstractmethod
    def run_select(self, *, task_id: uuid.UUID, data_source: ..., number_people_wanted: int, settings: Settings,
                   test_selection: bool, gen_rem_tab: bool, for_replacements: bool = False,
                   time_limit: int | None = None, soft_time_limit: int | None = None) -> Dispatch: ...
    @abstractmethod
    def manage_old_tabs(self, *, task_id: uuid.UUID, data_source: ..., dry_run: bool) -> Dispatch: ...
    @abstractmethod
    def run_select_from_db(self, *, task_id: uuid.UUID, assembly_id: uuid.UUID, ...) -> Dispatch: ...
    @abstractmethod
    def auto_export_respondents(self, *, assembly_id: uuid.UUID, countdown: int) -> Dispatch: ...

    @abstractmethod
    def status(self, celery_task_id: str) -> TaskStatus: ...
    @abstractmethod
    def revoke(self, celery_task_id: str) -> None: ...
```

- **A task method does not publish. It checks and returns a `Dispatch`.** It
  pickles the arguments there and then, inside the caller's transaction, so a
  serialisation bug raises to the caller (see D5). The service decides when to
  call the returned `Dispatch`: straight after an explicit commit for
  user-started tasks, or via `uow.after_commit` for the auto-export. See
  [When dispatch happens](#when-dispatch-happens).
- `run_select`'s `time_limit` / `soft_time_limit` replace the open-ended
  `celery_apply_kwargs` that monitoring passes today.
- `TaskStatus` is a small frozen dataclass (`state: str`, `value: Any`,
  `error: str`) built by the adapter. The service layer stops touching
  `AsyncResult`, and the two hand-written stand-ins disappear.
  `_process_celery_final_result` and `_extract_exception_info` become functions
  of a `TaskStatus`.
- `control.inspect()` (worker liveness) is used only by the health endpoint and
  a CLI command, both entrypoints. It stays out of the port. It can be added as
  `workers_alive()` if the health check ever wants faking.
- Adding a task means a method on the ABC, on `CeleryTaskRunner`, and on each
  fake. That is the price of T2.

#### The real adapter

`CeleryTaskRunner` lives in `src/opendlp/entrypoints/celery/runner.py`. It
imports `tasks.py`, and only bootstrap and `create_app` import it. Each method:

1. builds the kwargs;
2. runs `pickle.dumps(kwargs)` and lets any error propagate;
3. returns a closure that calls
   `tasks.<task>.apply_async(kwargs=kwargs, task_id=str(task_id), countdown=..., time_limit=...)`.

It doesn't reuse the pickled bytes; Celery serialises again on publish. The
dump is a check, not an optimisation.

#### Our id as the Celery id

Today each dispatch commits the `SelectionRunRecord`, calls `.delay()`, writes
`result.id` into `record.celery_task_id`, and commits again. Celery accepts a
caller-chosen id (`apply_async(task_id=...)`), so the adapter submits with
`str(record.task_id)`, and the service sets
`record.celery_task_id = str(task_id)` before the single commit. Then:

- one commit, not two, when the dispatch succeeds;
- the "record has no Celery id because dispatch failed" branch, and the
  `AsyncResult` for an empty id that raises when garbage-collected, stop
  arising for new records. Old rows keep their stored Celery-generated id. So
  the `celery_task_id` column stays, and `status` / `revoke` keep reading it
  rather than deriving it from `task_id`. No migration.

#### What can make a dispatch fail

`apply_async` publishes to Redis; it does not wait for a worker. So it can only
fail at the point of publishing:

1. **Redis unreachable or refusing writes** (down, restarting, network,
   `maxmemory`, socket timeout). Celery already retries the publish three times
   within about a second (`task_publish_retry_policy` in Celery 5.6.3). And
   flask-session uses the same Redis (`SESSION_REDIS` is built from the same
   `RedisCfg`), so the organiser's request already loaded its session from
   Redis moments earlier. A failure here needs Redis to go down in that window
   and stay down through the retries. If Redis is really down, they get an
   error page before they reach the button.
2. **Misconfiguration** (wrong Redis host). Permanent, but monitoring catches
   it, and so does nearly every page.
3. **Unpicklable arguments.** A code or data bug, deterministic, and it would
   recur on every retry. This is the one that matters. **It is caught at
   prepare time, inside the transaction, and raises to the caller as today.**
   The fakes do the same pickle round-trip, so CI catches it too. Today nothing
   pickles task arguments in CI except the BDD worker, because every other test
   patches `.delay`.

The commonest real failure, a dead or stuck worker, isn't a dispatch failure.
The publish succeeds and the record sits PENDING until `_fail_if_stuck_pending`
fails it (`PENDING_TASK_TIMEOUT_MINUTES = 60`), whatever we do at dispatch. The
organiser can cancel it sooner: `cancel_task` already tolerates a failed revoke.

#### When dispatch happens

Two shapes, chosen by whether there is a record and a person waiting on it (D5).

**User-started tasks (the seven `start_*` functions): dispatch explicitly after
the commit, and fail fast.** The service already runs inside the entrypoint's
open `with uow:` block, so it commits the record, then publishes, and on failure
marks the record FAILED in the same open UnitOfWork:

```python
uow.selection_run_records.add(record)   # celery_task_id = str(task_id), our own id
uow.commit()                            # the worker can now find the record
try:
    dispatch()                          # the pickle check already passed, at prepare time
except Exception as exc:
    mark_dispatch_failed(record, exc)   # FAILED, error message, log line, completed_at
    uow.commit()
    raise TaskDispatchError(...) from exc
```

- One commit on the happy path. A second commit only on failure.
- The organiser hears at once: the route catches `TaskDispatchError` and flashes
  a translated message. The record is FAILED immediately, so the writing guard
  does not block the assembly for an hour, and they can retry.
- No convention is bent. This is work inside the transaction the entrypoint
  owns, the same shape `sortition.py` has today. It doesn't use
  `after_commit`, whose callbacks must not touch the database
  (`docs/architecture.md`).
- What is given up: "the worker cannot start before the commit" holds because
  `commit()` is on the line above `dispatch()`, not by construction. Put the
  sequence in one helper, `_commit_and_dispatch(uow, record, dispatch)` in
  `sortition.py`, which all seven start functions use, so it is written once.
- `TaskDispatchError` is a new `OpenDLPError` with a `CuratedMessage`, so
  routes and JSON responses can show its message. The real broker error goes
  to the log, not to the user.
- `mark_dispatch_failed` reuses `_mark_task_as_failed` where it fits, with
  `celery_state="DISPATCH_FAILED"`.

**The auto-export: dispatch in `uow.after_commit`.** It has no record to mark
and no one waiting, and a failure must never fail the change that asked for
it. `schedule_auto_export` already runs as an after-commit callback and
already swallows Redis and broker errors. That stays as it is.

#### A publish that failed may still have arrived

A socket timeout during the publish can happen after Redis accepted the
message. Then we mark the record FAILED, and a worker later picks up the task
anyway.

- **Writing tasks are already safe.** `_claim_assembly_for_writing` refuses any
  record that is no longer PENDING ("This task was cancelled or failed before
  it started") and leaves it alone.
- **Read-only tasks are not claimed**: `load_gsheet`, and `manage_old_tabs`
  with `dry_run=True`. They call
  `_update_selection_record(status=RUNNING)`, which would move a FAILED record
  to RUNNING and then COMPLETED. That is harmless to the data, but confusing to
  read. **Add a guard:** a small `_start_unclaimed_run(task_id, report, session_factory)`
  that, like the claim, moves the record to RUNNING only if it is still PENDING.
  Otherwise it logs, adds the same report line, and makes the task return its
  failure tuple without running. Both unclaimed tasks call it where they set
  RUNNING today. It also covers a load the organiser cancelled before a worker
  picked it up, which today would run anyway.

#### The fakes

In `tests/fakes/tasks.py` (see [Splitting tests/fakes.py](#splitting-testsfakespy)):

**`RecordingTaskRunner` (fake run).** Each task method pickle-round-trips its
arguments and returns a `Dispatch`. When that is called (straight after the
commit for user-started tasks, on commit for the auto-export, which
`FakeUnitOfWork` already does), it appends a `SubmittedTask(name, kwargs, options)`
to `.submitted`. So a test that does not commit sees nothing submitted, which is
the real behaviour. Setting `runner.fail_dispatch = ConnectionError(...)` makes
the next `Dispatch` raise, for testing the fail-fast path. `status` reports `PENDING` for anything submitted, and
`revoke` records the id. This replaces the ~30 `.delay` patches and the
`revoke` patches: tests assert on
`runner.submitted[0].kwargs["number_people_wanted"]`. It is the default for
unit and component tests.

**Outcomes (fake run with outcome).** Methods on the same class, so a test sets
what `status` will say:
`runner.finish(task_id, value=(True, [frozenset({"F3"})], report))`,
`runner.fail(task_id, error="boom")`, `runner.set_state(task_id, "STARTED")`.
This replaces the 16 `AsyncResult` patches and `_NoCeleryResult` /
`_FinishedCeleryResult`. Start with one class; split it only if it gets
confusing.

**`BlockingTaskRunner` (run and wait).** The `Dispatch` runs the task in-process
via Celery's own `Task.apply(kwargs=..., task_id=...)`, which gives a bound task
a real `self.request`. The fake keeps the returned `EagerResult` and answers
`status` from it.

- **Real database only** (D6). Tasks open their own sessions from a
  `session_factory` (`bootstrap(session_factory=...)`,
  `DatabaseProgressReporter`, `_append_run_log`), not from a UnitOfWork, so
  with a `FakeUnitOfWork` the task would read a different store. This fake is
  for integration and e2e tests. It replaces the "call the task function
  directly with `session_factory=`" pattern, and lets an e2e test go route →
  selection → result page in one process. The fake takes a `session_factory`
  and passes it to the task.
- **Pickle round-trip** as the other fake does. `apply()` does not serialise.
- **Countdown and time limits are ignored.** The auto-export's 30 s countdown
  runs at once, and monitoring's `time_limit` is not enforced. Say so in the
  docstring.
- **Not `task_always_eager`.** Celery's own testing docs advise against the
  global eager switch for unit tests, and it is global state where this is an
  object a fixture owns.

### What the circular imports become

Once the service layer depends only on the `TaskRunner` ABC:

- `sortition.py` and `respondent_auto_export.py` stop importing
  `entrypoints.celery`. Importing them no longer builds a Celery app.
- `tasks.py` imports `respondent_auto_export`, `sortition` and `monitoring` at
  the top; its three `noqa: PLC0415` imports go.
- `handlers.py` no longer reaches Celery. But `unit_of_work_events` still has
  to defer its import of the default handlers: they are now built by bootstrap
  (below), and bootstrap imports `unit_of_work`. That import stays deferred,
  and its comment is updated to give the new, shorter reason.

#### Layering check

Add a second check to `scripts/check_uow_convention.py` (D8): fail if any module
under `domain/` or `service_layer/` imports from `opendlp.entrypoints`. Also
fail if `domain/` imports `opendlp.bootstrap`. Deferred imports inside
functions count. The script already walks the AST of every module, so the new
check is a visitor over `ast.Import` / `ast.ImportFrom`. Its tests go alongside
the existing ones in `tests/unit/test_check_uow_convention.py`.

The script's name and ABOUTME then undersell it. Rename it to
`scripts/check_architecture.py` and update the two `justfile` lines that call
it.

`domain/assembly.py` imports `opendlp.bootstrap` today, so the check needs that
fixed first or an allowlist entry for it. See
[future_work/domain_imports_bootstrap.md](../future_work/domain_imports_bootstrap.md).
The other edge found on the way, `tasks.py` importing a Flask context processor
module, is an entrypoint importing an entrypoint, so the check allows it. It is
filed as
[future_work/service_account_email_in_context_processors.md](../future_work/service_account_email_in_context_processors.md).

---

## How adapters reach the code

The codebase has three answers today:

1. **Parameter from the entrypoint**: email adapter, template renderer, URL
   generator, gsheet export target factory.
2. **`app.extensions` factory**: UoW, gsheet export target, gsheet access
   client.
3. **Module-level import**: Celery.

And one place none of them reach: **event handlers**, which are called as
`handler(event, uow)`. The auto-export handler queues a Celery task, so it
needs the task runner. The future-work note
[registration_auto_reply_as_event.md](../future_work/registration_auto_reply_as_event.md)
would have a handler queue an email task, which would need the same.

Options considered: thread parameters (A1); hang adapters on the UnitOfWork as
`uow.tasks` (A2); inject dependencies into handlers at bootstrap (A3). **Chosen:
A1 + A3** (D4). Services take their adapters as parameters. Handlers get theirs
from bootstrap, which builds the handler table with them already supplied. This
is the dependency-injection half of chapter 13 of _Architecture Patterns with
Python_, without the message bus.

### A1: services take the runner as a parameter

- Each `start_*_task`, `cancel_task`, `get_selection_run_status` and
  `check_and_update_task_health` takes `task_runner: TaskRunner`. So do the
  monitoring functions that call them.
- Entrypoints get it from `bootstrap.get_task_runner()`, which returns the
  process's runner: a `CeleryTaskRunner`, unless `set_task_runner()` installed
  another. As built, there is no `app.extensions["task_runner"]` layer as first
  planned: no production app needs a runner of its own, and one process-wide
  runner means a test that builds its own app gets the fake too, without the
  per-fixture install that email needs.
- Roughly 20 blueprint call sites, the CLI monitor command, and the Celery
  tasks that call `check_and_update_task_health` / `run_monitoring_selection`
  pass it.
- `monitoring.py` already takes `start_select_fn` for its tests. It keeps that,
  and gains `task_runner`.

### A3: bootstrap builds the handler table

- `service_layer/handlers.py` changes from a module-level `EVENT_HANDLERS`
  dict to a function:

  ```python
  def build_event_handlers(task_runner: TaskRunner) -> EventHandlers:
      export = partial(respondent_auto_export.handle_respondents_changed, task_runner=task_runner)
      return {
          events.RespondentsChanged: [export],
          events.RespondentSchemaChanged: [export],
      }
  ```

  It is still the one place to look to find out what an event causes. Its
  ABOUTME and comment stay true.

- `handle_respondents_changed(event, uow, *, task_runner)` passes the runner on
  to `schedule_auto_export`, which calls
  `task_runner.auto_export_respondents(...)()` inside the callback it already
  registers. Its arguments are a UUID and an int, so the pickle check cannot
  fail there in practice. It runs inside the existing `try`, which already
  swallows Redis trouble.
- `bootstrap.default_event_handlers()` returns
  `build_event_handlers(get_task_runner())`. `default_uow_factory()` and
  `bootstrap()` pass it as `event_handlers=` when they build a
  `SqlAlchemyUnitOfWork`. So in a request the route and its handlers share one
  runner.
- **A `SqlAlchemyUnitOfWork` built directly** keeps today's meaning for
  `event_handlers=None`: "the application's handlers". There are several
  hundred of those in tests. `UnitOfWorkEvents._handlers_for` resolves `None`
  through `bootstrap.default_event_handlers()` (deferred import, as noted
  above).
- **Tests**: an autouse fixture in `tests/conftest.py` replaces bootstrap's
  process-wide default runner with a `RecordingTaskRunner`, exposed as a
  `task_runner` fixture. Every test, including the ones that build
  `SqlAlchemyUnitOfWork` directly, then gets the fake without being edited, and
  the route and handlers in one test share it. Integration and e2e tests that
  want tasks to run override the fixture with a `BlockingTaskRunner`.
- `FakeUnitOfWork` keeps running no handlers by default. A test that wants them
  passes `event_handlers=build_event_handlers(task_runner)` instead of
  `handlers.EVENT_HANDLERS`.

Email stays A1 only for now. When the auto-reply moves onto an event,
`build_event_handlers` gains an `email_adapter` parameter in the same way.

---

## Splitting `tests/fakes.py`

It is 1,631 lines, and 100 test files import from it. Split it into a package
(D1). Keep `tests/fakes/__init__.py` re-exporting every public name, so the
100 `from tests.fakes import ...` lines don't change. New code may import from
the submodules.

| Module          | Contents                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uow.py`        | `FakeStore`, `ClosedRepository`, `FakeUnitOfWork`, `_REPO_NAMES`                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `repositories/` | The repository fakes, about 1,070 lines in all, so a package of its own: `base.py` (`FakeRepository`), `users.py` (users, invites, signup surveys, roles, backup codes, 2FA audit, TOTP attempts, password reset and email confirmation tokens), `assemblies.py` (assemblies, gsheet and export gsheet configs, selection run records, target categories), `registration.py` (pages, page HTML, images, documents, content blocks, email templates, send records), `respondents.py` (respondents, field definitions, mapping entries) |
| `email.py`      | `FakeEmailAdapter`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `rendering.py`  | `FakeTemplateRenderer`, `FakeURLGenerator`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `google.py`     | `FakeGSheetExportTarget`, `FakeGSpreadClient` and its private helpers, the recorded `GOOGLE_*` error bodies, `google_api_error`                                                                                                                                                                                                                                                                                                                                                                                                       |
| `redis.py`      | `FakeRedis`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tasks.py`      | `RecordingTaskRunner`, `BlockingTaskRunner` (new)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

A pure move, its own PR, done first so the later diffs land in the right files.
Each new module gets its ABOUTME header. Two docs name the old file and need
updating in the same PR: `docs/testing.md:71` (where to add a repository fake:
now `tests/fakes/repositories/`) and `docs/respondent_export.md:74`
(`FakeGSheetExportTarget`: now `tests/fakes/google.py`).

---

## Keeping the old patterns out

Docs alone won't do it. The docs currently **recommend** the patterns this plan
removes. The Mocking Policy in `docs/testing.md` says:

> **Mock only at the boundary.** Mock things the system genuinely talks to over
> a boundary: Celery dispatch (`.delay`/`.apply_async`/`AsyncResult`/`control.revoke`),
> SMTP/email sending, ...

So the docs must change, and as with the UoW convention, a check should back
them up. The repo already has the right kind of check: `tests/conftest.py`
rejects "disguised route tests" at collection time, with a regex over the test
file's source (`_DISGUISED_ROUTE_TEST`). Do the same here (D9).

### Docs

- **`docs/testing.md`, Mocking Policy:** take Celery dispatch and email sending
  out of the "mock at the boundary" list. Replace them with "these
  boundaries have fakes; use them", and add a short table:

  | Boundary      | Fake                                           | Fixture        |
  | ------------- | ---------------------------------------------- | -------------- |
  | Email         | `FakeEmailAdapter`                             | `email_outbox` |
  | Celery        | `RecordingTaskRunner` / `BlockingTaskRunner`   | `task_runner`  |
  | UnitOfWork    | `FakeUnitOfWork` over a `FakeStore`            | `fake_store`   |
  | Google Sheets | `FakeGSheetExportTarget`, `FakeGSpreadClient`  | (per test)     |

  Then a sentence on what to do when a new adapter is added: write a fake in
  `tests/fakes/`, register it as a fixture, and add a row here.
- **`docs/testing.md`, Component Tests, "When NOT to use":** drop "anything
  dispatching Celery". With `RecordingTaskRunner` a component test can assert
  that a route dispatched a task. What it still can't do is *run* the task,
  so "anything that needs a task to run" moves to integration and e2e, with
  `BlockingTaskRunner`.
- **`AGENTS.md`:** one line under Development Patterns, because agents are the
  most likely to reach for `MagicMock` or `patch(".delay")` from habit:
  "In tests, fake email and Celery with the `email_outbox` and `task_runner`
  fixtures; never patch `get_email_adapter`, `.delay`, `.apply_async` or
  `AsyncResult`. See docs/testing.md."
- **`docs/background_tasks.md`:** a short "Dispatching a task" section: the
  `TaskRunner` port, `_commit_and_dispatch`, when to use `after_commit`
  instead, and the pickle-at-prepare rule.

### Collection-time guard

Extend `pytest_collection_modifyitems` in `tests/conftest.py`. It already reads
each unit test file's source for the disguised-route check. Widen that read to
all test files and add these patterns, each with a message that names the fixture to
use instead:

| Pattern (regex over the test file source)                              | Message points to                    |
| ---------------------------------------------------------------------- | ------------------------------------ |
| `(patch\|setattr)\([^)]*get_email_adapter`                             | `email_outbox`                       |
| `email_adapter\s*=\s*(Magic)?Mock\(`                                   | `FakeEmailAdapter` / `email_outbox`  |
| `opendlp\.[\w.]*\.(delay\|apply_async)\b` inside a `patch(` string     | `task_runner`                        |
| `(patch\|setattr)\([^)]*(AsyncResult\|control\.revoke)`                | `task_runner` (outcome methods)      |

- **Allowlist:** the adapters' own tests have to reach the real boundary.
  `tests/unit/test_email_adapters.py` patches `smtplib`, which no pattern
  matches. The `CeleryTaskRunner` tests (new, e.g.
  `tests/unit/test_celery_task_runner.py`) patch `apply_async` and
  `AsyncResult`. Keep a small set of allowed paths next to the patterns, with
  a comment saying why each is there.
- **When it turns on:** each pattern goes in with the PR that removes its last
  use. The email patterns in step 1, the Celery ones in step 2. So the guard
  never needs a backlog allowlist.
- Regexes over source text are crude. They will miss a patch built from a
  variable and catch a commented-out line. The disguised-route guard has the
  same blind spots and has been worth having. Say so in a comment, as
  `check_uow_convention.py` does for its own.

---

## Order of work

Each step is its own PR and leaves the suite green.

0. **Split `tests/fakes.py`** into the package. No behaviour change.
1. **Email wiring** (E1 + E4). Small, independent, removes the import-site
   patches. Lands the email patterns of the collection-time guard, the email
   row of the Mocking Policy table, and the `AGENTS.md` line (D9).
2. **`TaskRunner` port, `CeleryTaskRunner`, `RecordingTaskRunner`, and A1 + A3
   wiring.** `sortition.py` and `respondent_auto_export.py` switch over. Our id
   becomes the Celery id. User-started tasks use `_commit_and_dispatch`, which
   fails fast with `TaskDispatchError`, and the pickle check happens at prepare
   time. Tests move from patches to the fake. The deferred imports in
   `tasks.py` go. Lands the Celery patterns of the guard and the Celery docs
   changes (D9). This is the big one. If it is too big to review, split it:
   first the port with Celery-generated ids and two commits, then the own-id and
   fail-fast change.
3. **Guard the unclaimed tasks** (`_start_unclaimed_run` in `load_gsheet` and
   dry-run `manage_old_tabs`). Small and independent of the port: it fixes
   today's "cancelled load still runs" case too, so it can go first if
   convenient.
4. **Layering check** in the renamed `scripts/check_architecture.py`, after
   [domain_imports_bootstrap](../future_work/domain_imports_bootstrap.md) or
   with an allowlist entry for it.
5. **`BlockingTaskRunner`**, and move the integration and e2e tests that run
   tasks by hand onto it. Update the Component Tests "When NOT to use" text to
   point at it.

Future work, not scheduled:
[bdd_email_file_adapter](../future_work/bdd_email_file_adapter.md),
[domain_imports_bootstrap](../future_work/domain_imports_bootstrap.md),
[service_account_email_in_context_processors](../future_work/service_account_email_in_context_processors.md).

---

## Decisions

- **D1. Split `tests/fakes.py`** into a package, re-exporting from
  `__init__.py`.
- **D2. Email: E1 + E4 now; E3 (file adapter for BDD) later**, filed in
  `future_work/`.
- **D3. Typed submission (T2)**: one method per task on the port. Rejected:
  submit-by-name (T1), which avoids importing `tasks.py` but loses type
  checking of the arguments.
- **D4. A1 + A3**: services take adapters as parameters; bootstrap builds the
  handler table with dependencies supplied. Rejected: `uow.tasks` (A2), which
  needs no signature changes but widens the UnitOfWork beyond a transaction and
  its repositories.
- **D5. User-started tasks dispatch explicitly after the commit and fail
  fast; the auto-export dispatches in `after_commit`.** Our id is the Celery id,
  and arguments are pickled at prepare time. A failed publish marks the record
  FAILED in the entrypoint's open UnitOfWork and raises `TaskDispatchError`.
  Rejected: running every dispatch in `after_commit`, where a failure is
  swallowed and leaves the record PENDING for up to an hour, and where marking
  it failed would mean a callback touching the database. Rejected: a callback
  that opens its own UnitOfWork to mark the record, which is the first
  exception to the no-database-in-callbacks rule, for a rare case.
- **D5a. Read-only tasks check the record is still PENDING before running**
  (`_start_unclaimed_run`). A publish that times out may still arrive after we
  marked the record FAILED. Writing tasks already refuse that through the claim.
- **D6. `BlockingTaskRunner` needs a real database.** Moving tasks from
  `session_factory` to a `UowFactory`, so it would work with `FakeUnitOfWork`,
  is not done now.
- **D7. No message bus for now.** A3 is the step towards one that this work
  needs. Commands, and moving services behind a bus, are not planned.
- **D8. The layering check goes into the existing AST script**, renamed
  `check_architecture.py`. No `import-linter`.
- **D9. Old test patterns are kept out by docs and a guard.** `docs/testing.md`
  (Mocking Policy and Component Tests), `AGENTS.md` and
  `docs/background_tasks.md` are updated. A collection-time guard in
  `tests/conftest.py`, like the disguised-route guard, rejects patches of
  `get_email_adapter`, `MagicMock` email adapters, and patches of Celery
  dispatch and results. Each pattern lands with the PR that removes its last
  use.

## Open questions

None blocking. Two small ones to settle during implementation:

- Whether `RecordingTaskRunner` and the outcome methods stay one class.
- Whether step 2 lands as one PR or two.
