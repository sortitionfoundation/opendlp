# Domain events and a message bus in the service layer

Status: **third draft, no open questions** (2026-11-23). Nothing is
implemented. Doctor Chewie's answers from two review rounds are folded into the
design and recorded in [Decisions](#decisions). Awaiting the go-ahead to
implement phases 1 and 2.

Source: [chapter 8](https://www.cosmicpython.com/book/chapter_08_events_and_message_bus.html)
of _Architecture Patterns with Python_, with chapters 9 and 10 read for where
the pattern goes next. Events only; no commands.

## Summary

- The book's chapter 8 does not drop in unchanged. Three things in this
  codebase bend it: only entrypoints open `with uow:`, most writes go through
  service functions and bulk repository methods rather than aggregate methods,
  and the first real handler needs to read the database before it decides
  whether to do anything.
- Proposed shape: services **record events on the UnitOfWork**
  (`uow.record(event)`). Handlers run **inside the caller's transaction**, with
  the caller's `uow`. A handler that needs a side effect outside the database
  registers an **after-commit callback** (`uow.after_commit(fn)`), which runs
  only if the commit succeeds and can never fail the request.
- First conversion: the 27 `request_auto_export(uow, assembly_id)` call sites
  become `uow.record(RespondentsChanged(assembly_id))` with one handler. This
  also removes the reliance on the 30-second countdown for ordering.
- The activity log is the feature that justifies the machinery. It gets its own
  plan, built on this one.
- I recommend **not** moving the `number_to_select` recalculation onto events,
  and **not** treating user-started Celery tasks or Google Sheets calls as
  events. Reasons are in [What fits and what does not](#what-fits-and-what-does-not).

## What exists today

| Piece | Where | Relevance |
| --- | --- | --- |
| UnitOfWork | `service_layer/unit_of_work.py` | 24 repositories, bound only inside `with uow:`. `commit()`, `commit_and_reset()`, `rollback()`. No event collection. |
| UoW convention | `docs/architecture.md`, `scripts/check_uow_convention.py` | Only entrypoints open the context. A function that takes a `uow` must not open one. |
| After-commit note | `docs/architecture.md` "After-commit side effects: the case for domain events" | Says to build events when a second after-commit side effect arrives. |
| Auto-export trigger | `service_layer/respondent_auto_export.py` `request_auto_export` | Reads the export config, sets a Redis debounce key, queues a Celery task with a 30s countdown. Never raises. |
| Its call sites | 27 calls: `respondent_service` (6), `respondent_field_schema_service` (13), `derivation_service`, `assembly_service`, `registration_submission_service`, `target_source_service`, `celery/tasks.py` (2) | Each is commented as a `RespondentsChanged` candidate. |
| Recalculation | `assembly_service.update_assembly_with_changes` → `target_service.recalculate_minmax_for_assembly` | A direct call that **returns** the changed values, which the route shows to the organiser. |
| Task dispatch | `service_layer/sortition.py` (7 `start_*` functions) | Each inserts a `SelectionRunRecord`, commits, calls `.delay()`, stores the Celery id, commits again. |
| Registration auto-reply | `blueprints/registration.py` `_send_registration_auto_reply` | Called by the route after the submission commits, in a second `with uow:`, wrapped in a broad `except`. |
| Existing logs | `Respondent.comments`, `TwoFactorAuditLog`, `SelectionRunRecord`, `RespondentEmailSendRecord` | Written directly by services and domain methods. |
| Test fake | `tests/fakes.py` `FakeUnitOfWork` | Its `__exit__` does not call `commit()`. Around 700 tests build `SqlAlchemyUnitOfWork(session_factory)` directly. |

Facts that shape the design:

1. **The commit happens when the entrypoint's block exits**, with a few
   services committing mid-block (`sortition.py`, `registration_submission_service`,
   `run_auto_export`). Any dispatch tied to commit has to work for both.
2. **Services are functions over repositories.** Several writes never load an
   aggregate: `bulk_mark_as_selected`, CSV import, reset to pool, delete all.
   The book's `product.events.append(...)` has nowhere to live for those.
3. **Imperative mapping skips `__init__` on load.** An `events` list set in
   `__init__` is missing on every loaded object. The book patches this with a
   SQLAlchemy `load` listener. It would be needed on every aggregate, along
   with a `seen` set on 24 repositories.
4. **`request_auto_export` reads the database** to see whether auto-export is
   on. So the first handler needs a live transaction, not just the event.
5. **The service layer already imports `entrypoints.celery.tasks`**, and
   `tasks.py` imports `respondent_auto_export` inside two functions to break
   the cycle. A handler registry adds to that cycle unless it is wired late.

## How the book does it, and where we differ

| Book (chapter 8) | Here | Why |
| --- | --- | --- |
| Events are dataclasses in `domain/events.py` | Same | No reason to differ. |
| The aggregate appends to `self.events` | The service calls `uow.record(event)` | Facts 2 and 3. The book lists "service layer raises events" as its option 2. |
| Repositories track `seen` aggregates | Not needed | Events are already on the UoW. |
| The UoW publishes after `commit()` | Handlers run in the transaction. External effects go through `uow.after_commit()` | Fact 4, and the split between "must be true at commit" and "may fail alone". See below. |
| Handlers are called with the event only (ch 8), then `(event, uow)` and each opens its own `with uow:` (ch 9) | Handlers get `(event, uow)` and never open a context | The UoW convention. |
| Event handler errors are logged and swallowed (ch 10) | In-transaction handlers propagate. After-commit callbacks are logged and swallowed | A swallowed database error poisons the transaction (`docs/architecture.md`). |
| `HANDLERS` is a module-level dict | Same, wired through `bootstrap` | Fact 5. |

The book itself calls commit-time publishing "neat but also magic". This design
keeps the magic to one place: callbacks that fire after commit.

## Proposed design

### 1. Events

New module `src/opendlp/domain/events.py`:

```python
@dataclass(frozen=True)
class Event:
    """Something that happened, named in the past tense."""


@dataclass(frozen=True)
class RespondentsChanged(Event):
    assembly_id: uuid.UUID
```

Rules for events:

- Frozen dataclasses holding IDs and small values. **No personal data**: an
  event says which respondent, never what their answers are. This keeps events
  safe to log and keeps the activity log inside the erasure strategy.
- Past tense. An imperative name means it is a command, which is out of scope.
- Events live in memory for one unit of work. Nothing is persisted (no outbox).

### 2. Recording and dispatch

Declared on `AbstractUnitOfWork` as abstract methods. The code lives in a
separate class, `UnitOfWorkEvents` in `service_layer/unit_of_work_events.py`.
The real and fake UoW each own one and delegate to it, so the abstract class
stays an interface with no state of its own:

```python
def record(self, event: Event) -> None:
    """Note that something happened, and run its in-transaction handlers now."""

def after_commit(self, callback: Callable[[], None]) -> None:
    """Run callback once this unit of work has committed. Dropped on rollback."""
```

- `record` appends the event to `uow.events` (kept for tests and logging) and
  calls each handler registered for its type as `handler(event, uow)`.
- Handlers run synchronously, in the caller's transaction. An exception
  propagates and fails the request, like any other service code.
- A handler may call `uow.record(...)` itself. A depth guard raises on runaway
  chains instead of recursing forever.
- `commit()` runs the pending callbacks after the database commit succeeds.
  Each is wrapped: an exception is logged with `structlog` and the rest still
  run. `rollback()` and a failed commit discard them.
- `UnitOfWorkEvents` does the dispatch, the depth guard and the callback list.
  Each UoW tells it where the transaction has got to: `start()` on entering
  the context, `run_callbacks()` after a commit, `discard_callbacks()` on a
  rollback. `record` passes the UoW in, so it holds no reference back to it.
- Callbacks take no `uow` and do no database work. They queue a Celery task or
  touch Redis. Work that needs the database belongs in the task.

The rule this gives a developer:

| The reaction... | Goes in |
| --- | --- |
| must be true when the change commits | an in-transaction handler |
| must happen only if the change commits, and may fail alone | an after-commit callback |
| produces a value the caller needs | a direct call, not an event |

### 3. Handlers and wiring

New module `src/opendlp/service_layer/handlers.py` holding the handler
functions and one dict:

```python
EVENT_HANDLERS: dict[type[Event], list[Handler]] = {
    events.RespondentsChanged: [respondent_auto_export.handle_respondents_changed],
}
```

- The UoW resolves the registry lazily on first `record`, defaulting to
  `EVENT_HANDLERS`. This keeps `SqlAlchemyUnitOfWork(session_factory)` working
  unchanged for the ~700 tests that build one directly, and avoids an import
  cycle at module load.
- A UoW can be built with an explicit registry. `FakeUnitOfWork` defaults to an
  empty one, so a unit test of a service asserts on `uow.events` and runs no
  handlers.
- Dispatch is by exact type, as in the book (D5).

### 4. First conversion: auto-export

`request_auto_export` splits along the transaction boundary:

```python
def handle_respondents_changed(event: RespondentsChanged, uow: AbstractUnitOfWork) -> None:
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(event.assembly_id, EXPORT_KIND)
    if config is None or not config.auto_export:
        return
    uow.after_commit(partial(schedule_auto_export, event.assembly_id))
```

`schedule_auto_export` keeps the Redis debounce and the `apply_async` call. The
27 call sites become `uow.record(events.RespondentsChanged(assembly_id))`.

What changes in behaviour:

- A rolled-back change no longer queues an export.
- The task can no longer run before the change commits. The 30-second
  countdown stays, but only as the debounce.
- Schema changes record `RespondentSchemaChanged(assembly_id)`, handled the
  same way (D4). Both events carry the assembly id and nothing else.
- `tasks.py` loses its two function-local imports of `respondent_auto_export`
  at the record sites. The locked-out re-request path in the task stays a
  direct call to `schedule_auto_export`.

### 5. Testing

| Level | What |
| --- | --- |
| Unit | `record` calls handlers with the uow; `after_commit` runs on commit, not on rollback, not on a failed commit; a failing callback is logged and the others run; the depth guard. Each handler called directly with a fake uow. Each of the 27 sites asserts `RespondentsChanged in uow.events`, replacing patches of `request_auto_export`. |
| Integration | Against Postgres: a service call followed by block exit queues one task (patched `apply_async`); an exception in the block queues none. |
| E2E | Registration POST on an auto-exporting assembly still dispatches the task. Existing tests should pass unchanged. |
| BDD | No new scenario. The existing auto-export scenario covers the visible behaviour. |

`FakeUnitOfWork.__exit__` does not call `commit()` today, so callbacks on the
fake would fire on an explicit `commit()` only. A clean exit will fire them
too, to match the real UoW (D12). That touches a widely used fake, so it is its
own commit with the full suite run after it.

After the callbacks run, `SqlAlchemyUnitOfWork` checks that the session has
nothing new, dirty or deleted, and raises if it has (D7). A callback that
writes to the database is a bug, and this makes it fail in the first test that
exercises it.

### 6. Docs

- `docs/architecture.md`: replace "the case for domain events" with a
  description of what was built, and the three-row rule above.
- `docs/background_tasks.md`: the auto-export trigger paragraph.
- `AGENTS.md`: a short "Events" section next to the UnitOfWork convention.
- `docs/agent/future_work/registration_auto_reply_as_event.md`: a new note
  (D8). The auto-reply is sent by the route after the submission commits. It
  fits the after-commit shape, but it needs the request locale and the email
  adapter and it writes a send record, so it would become a Celery task queued
  by a `RespondentRegistered` event. The note records that, and that the change
  would also take an SMTP send out of a public request.

## What fits and what does not

| Candidate | Verdict | Reasoning |
| --- | --- | --- |
| Respondent changes → auto-export | **Yes, phase 2** | Many publishers, one optional reaction, must follow commit. The textbook case. |
| Activity log | **Yes, phase 3** | Many publishers, one subscriber. An in-transaction handler writes the entry, so a change and its log entry commit together. |
| `number_to_select` → target recalculation | **No** | `update_assembly_with_changes` returns the recalculated values and the route shows them. A handler cannot return. Chapter 9 calls returning results from the bus "a temporary ugly hack". It is also an invariant, as D19 of the 666 plan argued. `update_assembly` should record an event for the activity log, and the recalculation stays a direct call. |
| Celery tasks started by a user (selection, replacement, manage tabs) | **No** | "Run a selection" is a command with one recipient, and the caller needs the task id back. These tasks should **record** events (`SelectionStarted`, `SelectionCompleted`, `SelectionFailed`) for the activity log in phase 3. |
| Celery tasks as a way to run handlers | **Later** | A generic "handle this event in a worker" task is the route to slow handlers. It needs serialisable events. Nothing needs it yet. |
| Google Sheets reads and writes | **No** | Each is a request with an answer the user waits for (export, access check, load). Changes to the sheet config and completed exports are worth recording as events for the log. |
| Registration auto-reply email | **Not now** | It is an after-commit, best-effort reaction, which fits. But it writes a send record, so under the "no database in callbacks" rule it would have to become a Celery task. Noted in `future_work/` (D8). |
| Invite, password reset and confirmation emails | **No** | The user is told whether the send worked. |
| `Respondent.comments` | **Leave** | Per-respondent history written by domain methods. The activity log links to it, it does not replace it (D10). |
| `TwoFactorAuditLog` | **Leave** | Works, and belongs to the user aggregate, not an assembly. |

## Phases

Branch `event-message-bus` off `main`.

1. **Plumbing.** No behaviour change.
   1. `domain/events.py` with `Event`, `RespondentsChanged` and
      `RespondentSchemaChanged`.
   2. `UnitOfWorkEvents` holding the dispatch and the callbacks. `record`,
      `after_commit` and `events` abstract on `AbstractUnitOfWork`, delegated
      by `SqlAlchemyUnitOfWork`; callbacks run in its `commit()` and
      `commit_and_reset()`, with the nothing-pending check; discarded on
      rollback. Unit tests.
   3. `service_layer/handlers.py` with an empty registry, resolved lazily.
      A test that `import opendlp.service_layer.unit_of_work` works from a
      fresh interpreter.
   4. `FakeUnitOfWork`: empty registry by default, callbacks on `commit()`.
   5. `FakeUnitOfWork` fires callbacks on a clean exit. Own commit, full suite.
2. **Auto-export conversion.**
   1. Split `request_auto_export` into `handle_respondents_changed` and
      `schedule_auto_export`; register the handler for both events. Handler
      and scheduling unit tests; the integration tests for commit and rollback.
   2. Replace the 27 call sites, one commit per service module, each with its
      test asserting the event. Re-grep for writers first: the 1029 inventory
      was taken in September and replacement selection has landed since.
   3. Remove `request_auto_export` once nothing calls it, and the candidate
      comments that go with it.
   4. Docs, including the `future_work/` note. `just check`, `just test`.
3. **Activity log.** A separate plan under `docs/agent/` for sc-922: the event
   catalogue, the `ActivityLogEntry` model and table, the handler, the UI.
   What this review already settled for it is in
   [Carried forward to the activity log plan](#carried-forward-to-the-activity-log-plan).

Each numbered step is a commit that leaves the suite green.

Phases 1 and 2 need no migration, no new dependency and no new translatable
strings. `tenacity` (in the dev group today) is not needed: Celery already
retries the export.

## Risks

- **At-most-once callbacks.** A process that dies between the commit and the
  callback loses the side effect. For auto-export the next change asks again.
  Anything that must not be lost needs a transactional outbox, which is out of
  scope and worth naming now so nobody assumes delivery.
- **Hidden control flow.** `uow.record(...)` hides what happens next. The
  registry is one dict in one file, and that file is the answer to "what does
  this event do". Handler chains should stay at depth one where possible.
- **Handlers in the transaction can break requests.** A bug in the activity
  log handler would fail every write it listens to. That is the accepted price
  of atomic logging (D3).
- **Mid-block commits fire callbacks early.** Where a service commits and then
  carries on, callbacks registered before that commit fire at it. This is
  correct, and matches today's behaviour in `registration_submission_service`.
- **Import cycle.** `unit_of_work` → `handlers` → `respondent_auto_export` →
  `tasks` → `bootstrap` → `unit_of_work`. Lazy registry resolution avoids it;
  the implementation must prove that with a plain `import opendlp` test.

## Decisions

D1–D12 are from the first review round and D13 from the second, both
2026-11-23.

| # | Question | Decision |
| --- | --- | --- |
| D1 | Record events on the UoW or on the aggregate? | On the UoW: `uow.record(event)`. |
| D2 | When do in-transaction handlers run? | At `record`, synchronously. No queue drained at commit. |
| D3 | Does a failing in-transaction handler fail the request? | Yes. No savepoint per handler; the activity log is atomic with the change it describes. |
| D4 | How many events in the auto-export conversion? | Two coarse ones, `RespondentsChanged` and `RespondentSchemaChanged`. Granular events arrive with the activity log. |
| D5 | Exact-type or base-class dispatch? | Exact type for now. Revisit in the activity log plan, when one handler wants many respondent events. |
| D6 | Does the `number_to_select` recalculation move onto events? | No. It stays a direct call because the route shows its return value. |
| D7 | Is "no database work in after-commit callbacks" a hard rule? | Yes, enforced by a nothing-pending check on the session after the callbacks run. |
| D8 | Registration auto-reply onto events? | Not in this work. Written up in `future_work/` as part of the docs step. |
| D9 | Activity log: who is the actor when there is no user? | The log distinguishes the non-user actors, because the assembly managers reading it will not know the system well. Stored as an actor kind, D13. |
| D10 | Activity log and respondent comments | The log links to the respondent and leaves the detail in the comments. Bulk operations hold counts. No personal data in the log. |
| D11 | Activity log: which events first? | Project details changed, targets changed, respondents imported / deleted / reset, selection started / completed / failed, export configured / run / failed, registration page changes, team membership changes. |
| D12 | Does `FakeUnitOfWork` fire callbacks on a clean exit? | Yes, as its own commit. |
| D13 | How is a non-user actor stored? | An actor kind (`user`, `public`, `system`) next to a nullable user id. Not reserved UUIDs: an actor column holding one could not keep its foreign key to `users.id` without placeholder user rows. |

## Carried forward to the activity log plan

Settled here so that plan can start from them:

- The reader is an assembly manager of that assembly, who may not know the
  system well (D9). Entries have to read as plain sentences, and every label
  goes through gettext.
- Every logged event carries an actor (D13):

  ```python
  class ActorKind(Enum):
      USER = "user"
      PUBLIC = "public"
      SYSTEM = "system"


  @dataclass(frozen=True)
  class Actor:
      kind: ActorKind
      user_id: uuid.UUID | None = None
  ```

  - **a user** — including a task that user started, which is logged against
    them (`run_record.user_id` already holds this);
  - **the public** — a registration form submission;
  - **the system** — anything automatic, such as the auto-export or a cleanup
    job.

  The log table gets `actor_kind` and a nullable `actor_user_id` with a real
  foreign key to `users.id`. The kinds get a labels dict like
  `global_role_labels`, so "the public" and "the system" translate. A kind
  added later is a new enum value, which needs the two-release split from
  `docs/deploy.md`.
- The all-zeros UUID that `registration_submission_service` writes as the
  author of the "Created via registration form" comment stays as it is. It is
  an inline literal today; it gets a named constant when that plan touches it.
- Several schema services take no `user_id` today. Logging their changes means
  threading an actor through them, which is work for that plan to size.
- The log holds IDs and counts, never respondent details (D10), so erasing a
  respondent leaves the log valid.
- The first slice of events is D11.
- Whether handlers dispatch on a base class is decided there (D5).

## Out of scope

- Commands and command handlers (chapter 10).
- Persisted events, an outbox, or publishing to anything outside the process.
- Dependency injection of adapters into handlers (chapter 13). The first
  handler needs none.
- Changing how selection tasks are started or tracked.
