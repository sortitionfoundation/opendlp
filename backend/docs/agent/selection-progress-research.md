# Selection progress integration — research

Research for wiring sortition-algorithms' new `ProgressReporter` API into
OpenDLP so the backoffice progress modal shows live progress while
`run_stratification()` is running under Celery.

## Context — what sortition-algorithms provides

Added in sortition-algorithms commits `b50f8ac` → `8d3a922` (all dated
2026-04-09) and shipped from version **0.12.x**. OpenDLP is pinned to
`sortition-algorithms==0.12.4` in `pyproject.toml:28` — the `progress`
module is already importable.

### The protocol

```python
# sortition_algorithms/progress.py
@runtime_checkable
class ProgressReporter(Protocol):
    def start_phase(self, name: str, total: int | None = None, *, message: str | None = None) -> None: ...
    def update(self, current: int, *, message: str | None = None) -> None: ...
    def end_phase(self) -> None: ...
```

Key properties:

- **Flat phases.** Each `start_phase` implicitly ends the previous one.
- **`name`** is a stable machine-readable identifier (part of the public
  API — new phases are non-breaking, renames are breaking).
- **`message`** is a human-readable description the library always
  supplies — but the library is English-only, so OpenDLP has to translate
  if it wants to show phase text in non-English locales.
- **`total`** may be `None` for convergence loops — `current` then just
  counts iterations.
- **The library does not throttle.** It calls `update` every inner-loop
  iteration (hundreds/second on fast solvers). **Throttling is the
  caller's responsibility.**
- Exceptions raised by a caller's reporter are caught and logged via
  `ErrorSwallowingReporter` — a buggy reporter can never kill a 10-minute
  selection.
- Single-threaded from the library side, but the reporter may be read
  from another thread (e.g. a Flask poll) — that locking is the caller's
  problem. Postgres transactions handle our case fine.

### Phases emitted

The phase set depends on `selection_algorithm` in `Settings`:

| `name`                   | `total`                        | When                                                       |
| ------------------------ | ------------------------------ | ---------------------------------------------------------- |
| `legacy_attempt`         | `max_attempts`                 | each retry of the legacy algorithm                         |
| `multiplicative_weights` | ~200 (MW rounds)               | initial diverse-committee search (maximin / leximin / nash) |
| `maximin_optimization`   | `None`                         | maximin convergence loop                                   |
| `nash_optimization`      | `None`                         | Nash convergence loop                                      |
| `leximin_outer`          | `people.count`                 | leximin "fix probabilities" outer loop                     |
| `diversimax`             | `None`                         | diversimax single-shot ILP — emitted once, no updates      |

For our default algorithm (`maximin` — see
`domain/selection_settings.py:84`), a typical run emits
`multiplicative_weights` (with a finite total) followed by
`maximin_optimization` (indeterminate, iteration counter only).

### How callers plug in

```python
success, panels, report = run_stratification(
    features=features,
    people=people,
    number_people_wanted=n,
    settings=settings,
    progress_reporter=my_reporter,   # new kwarg
)
```

The parameter is keyword-only, defaults to `None`, and the library wraps
whatever you pass in `ErrorSwallowingReporter`. No reporter = no-op
singleton, identical behaviour to today.

### Recipe in the docs

`docs/progress.md` in sortition-algorithms literally contains a Flask +
Celery + database-row recipe (§ "Database-row reporter"). The pattern:

- Timestamp the last DB write; drop updates within `min_interval_seconds`.
- Always force-flush on `start_phase` so phase transitions are visible
  without polling lag.
- `end_phase` is a no-op.

That is almost exactly what we want.

## How OpenDLP drives selection today

### Call chain — DB selection (backoffice)

1. **Form POST** → `db_selection_backoffice.start_db_selection` at
   `src/opendlp/entrypoints/blueprints/db_selection_backoffice.py:82`.
2. Calls `start_db_select_task` at
   `src/opendlp/service_layer/sortition.py:459`. This:
   - Creates a `SelectionRunRecord` with `status=PENDING`,
     `task_type=SELECT_FROM_DB` or `TEST_SELECT_FROM_DB`.
   - Commits it to the DB.
   - Submits the Celery task `run_select_from_db` with `task_id`.
3. Redirects the browser back to the assembly selection page with
   `?current_selection=<task_id>`, which renders the progress modal.

### Celery task chain

`src/opendlp/entrypoints/celery/tasks.py` (~1000 lines) contains three
Celery tasks used by backoffice DB selection / gsheet selection:

- `run_select_from_db` (line 687): load from DB → run selection → write
  back to DB.
- `run_select` (line 760): load from gsheet → run selection → write
  back to gsheet.
- `load_gsheet` (line 740): gsheet load only, used for the "validate
  data" flow.

Each composes private `_internal_*` helpers. **The single call site for
`run_stratification()`** is `_internal_run_select` at **line 393**:

```python
# tasks.py:353-455 — _internal_run_select
success, selected_panels, report = run_stratification(
    features=features,
    people=people,
    number_people_wanted=number_people_wanted,
    settings=settings,
    test_selection=test_selection,
    already_selected=already_selected,
)
```

This is the only place that needs to pass a `progress_reporter=`.

### How progress-ish state is updated today

The celery task already writes log lines to the DB record via
`_update_selection_record` (`tasks.py:117`). Key points:

- Each call does a full `bootstrap(session_factory=session_factory)` →
  open UoW → mutate record → `uow.commit()` → close. New session per
  write. Fine for rates of ~1Hz.
- `log_messages` is a JSON list column; updates use `list.append()` +
  `flag_modified(record, "log_messages")` to convince SQLAlchemy the JSON
  blob changed.
- The helper accepts `log_message` or `log_messages=[...]` but **always**
  treats the DB row as append-only. There is no in-place update of a
  single field.
- `session_factory` is threaded through all `_internal_*` helpers so
  tests can inject a fake. A new progress reporter should take the same
  parameter.
- A separate `SelectionRunRecordHandler` (line 43) routes Python
  `logging` records into `_append_run_log`, so library `logger.debug`
  lines already land in `log_messages`. The new progress events are
  **separate** from these log lines and should not trigger appends to
  `log_messages` — otherwise a 200-round MW loop becomes 200 log lines.

### Domain + ORM

`domain/assembly.py:210` — `SelectionRunRecord` is a frozen-ish dataclass
mapped imperatively:

```python
@dataclass
class SelectionRunRecord:
    assembly_id: uuid.UUID
    task_id: uuid.UUID
    status: SelectionRunStatus
    task_type: SelectionTaskType
    celery_task_id: str = ""
    log_messages: list[str] = field(default_factory=list)     # JSON
    settings_used: dict[str, Any] = field(default_factory=dict)  # JSON
    error_message: str = ""
    created_at: datetime | None = None
    completed_at: datetime | None = None
    user_id: uuid.UUID | None = None
    comment: str = ""
    status_stages: list[dict[str, str]] | None = None         # JSON — UNUSED
    selected_ids: list[list[str]] | None = None               # JSON
    run_report: RunReport = field(default_factory=RunReport)
    remaining_ids: list[str] | None = None                    # JSON
```

`adapters/orm.py:331-358` — matching imperative table.

Notes:

- `status_stages` is declared on both the domain and ORM but **never
  read or written anywhere in `src/`** (grep confirms it's dead code).
  A future high-level "load → select → write" stages display could
  repurpose it, but for *algorithm-level* live progress I recommend a
  dedicated column — the shapes don't match.
- `SelectionRunStatus` (`domain/value_objects.py:53`) is the enum
  `PENDING | RUNNING | COMPLETED | FAILED | CANCELLED`.
- Algorithm choice lives in
  `SelectionSettings.selection_algorithm` (default `"maximin"`).
  `start_db_select_task` already serialises this into
  `settings_used["selection_algorithm"]`, so the template can render a
  sensible "unknown phase" fallback by checking the algorithm.

## How the backoffice displays progress today

### Page + HTMX polling

`view_assembly_selection` (`blueprints/gsheets.py:145`) renders
`templates/backoffice/assembly_selection.html`. When
`?current_selection=<uuid>` is present it includes one of two modal
templates:

```jinja
{% if data_source == "csv" %}
    {% include "backoffice/components/db_selection_progress_modal.html" %}
{% else %}
    {% include "backoffice/components/selection_progress_modal.html" %}
{% endif %}
```

(`assembly_selection.html:38-44`)

Each modal wraps its contents in a `progress_modal()` macro
(`templates/backoffice/components/modal.html:76-153`) that sets up an
HTMX self-replace:

```html
hx-get="{{ htmx_poll_url }}"
hx-trigger="every 2s"
hx-swap="outerHTML"
```

Polling targets:

- gsheet: `gsheets.selection_progress_modal` →
  `GET /assembly/<id>/selection/modal-progress/<run_id>` at
  `blueprints/gsheets.py:304`.
- DB: `db_selection_backoffice.db_selection_progress_modal` →
  `GET /assembly/<id>/selection/db/modal-progress/<run_id>` at
  `blueprints/db_selection_backoffice.py:124`.

Both endpoints:

1. Check permissions and task health via
   `service_layer.sortition.check_and_update_task_health`.
2. Call `get_selection_run_status(uow, run_id)` (`sortition.py:625`)
   which returns a `RunResult` dataclass containing `run_record`,
   `run_report`, `log_messages`, `success`.
3. Re-render the same `*_progress_modal.html` fragment.

Polling **stops** once `run_record.has_finished` is true — the template
sets `htmx_poll_url = ""` when finished, so the fragment is static.

### What the modal currently shows during RUNNING

`templates/backoffice/components/db_selection_progress_modal.html` (and
the twin `selection_progress_modal.html`):

- Task type label (`run_record.task_type_verbose`).
- Status badge.
- A generic spinner with text `_("Processing...")` — no phase info.
- Scrollable log message list (from `log_messages`).
- On completion: download buttons / "View spreadsheet" link + full run
  report in a `<details>`.
- Cancel button while running.

**What it lacks:** any indication of *which* phase is running, how far
through it is, or any sense of forward motion beyond "new log lines
eventually appear". That is exactly what this task should fix.

## Design for the integration

The cleanest shape follows the docs recipe almost verbatim but adapts it
to OpenDLP's bootstrap/UoW pattern and i18n.

### Storage — one new JSON column

Add a single nullable JSON column to `selection_run_records`:

```python
# adapters/orm.py
Column("progress", JSON, nullable=True),
```

Payload shape:

```json
{
  "phase": "multiplicative_weights",
  "current": 45,
  "total": 200,
  "updated_at": "2026-04-09T16:10:42.312+00:00"
}
```

Plus a matching `progress` field on the domain dataclass. Rationale:

- `SelectionRunRecord` already leans on JSON columns for flexible state
  (`log_messages`, `settings_used`, `status_stages`, `run_report`,
  `selected_ids`, `remaining_ids`) — one more is in keeping with the
  pattern.
- Single JSON blob = one UPDATE per tick, not four column writes.
- Null payload means "no progress reported yet / task hasn't reached a
  tracked phase" — easy sentinel for templates.
- Phase `name` is the library's stable identifier — translation happens
  in the template.
- `status_stages` stays untouched for a potential future
  OpenDLP-level stage display (load → select → write).

Migration: `uv run alembic revision --autogenerate -m "add progress
column to selection_run_records"`. Remember to add a DELETE to
`tests/conftest.py::_delete_all_test_data()` only if we add a new table
— this only adds a column, so no conftest change needed.

### The reporter

A new class in the celery tasks module (or a small dedicated module under
`src/opendlp/adapters/` — probably
`adapters/sortition_progress.py` to keep tasks.py from growing):

```python
# adapters/sortition_progress.py
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from opendlp.bootstrap import bootstrap


class DatabaseProgressReporter:
    """Persist sortition-algorithms progress events to a SelectionRunRecord.

    Throttles writes to at most once per ``min_interval_seconds``. Phase
    transitions always flush immediately so the modal sees them with
    polling-interval lag at most.
    """

    def __init__(
        self,
        task_id: uuid.UUID,
        *,
        session_factory: sessionmaker | None = None,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self._task_id = task_id
        self._session_factory = session_factory
        self._min_interval = min_interval_seconds
        self._last_write = 0.0
        self._phase_name = ""
        self._phase_total: int | None = None

    def start_phase(self, name: str, total: int | None = None, *, message: str | None = None) -> None:
        self._phase_name = name
        self._phase_total = total
        self._write(current=0, force=True)

    def update(self, current: int, *, message: str | None = None) -> None:
        self._write(current=current, force=False)

    def end_phase(self) -> None:
        # Intentionally no-op. The next start_phase (or task completion)
        # supplies the next visible state.
        pass

    def _write(self, *, current: int, force: bool) -> None:
        now = time.monotonic()
        if not force and (now - self._last_write) < self._min_interval:
            return
        self._last_write = now

        with bootstrap(session_factory=self._session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(self._task_id)
            if record is None:
                return  # task was cancelled/deleted — drop silently
            record.progress = {
                "phase": self._phase_name,
                "current": current,
                "total": self._phase_total,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if hasattr(record, "_sa_instance_state"):
                flag_modified(record, "progress")
            uow.commit()
```

Things I deliberately chose:

- **Library `message` is discarded.** The library is English-only; we
  translate in the template by switching on `phase` name. Storing
  English strings in the DB would pin them to one language.
- **`update()` does not log.** The log_messages list stays reserved for
  the existing `_append_run_log` calls (task-level narration and any
  library `logger.debug` lines routed through
  `SelectionRunRecordHandler`). A 200-round MW loop should produce one
  progress row update ~every second, not 200 log lines.
- **Phase transitions DO force-flush.** This keeps the UI snappy at
  phase boundaries even though ticks are rate-limited.
- **A separate bootstrap per write** — same pattern as
  `_update_selection_record`. 1Hz is well within Postgres comfort.
- **Silent no-op if the record is gone.** Cancel deletes / terminates
  the task but the reporter may still call once before the worker
  process notices.
- **`session_factory` threaded through** so tests can inject a fake.
  Matches the existing idiom.

Throttle default of 1.0s matches the modal's 2s poll interval and the
docs recipe.

### Wiring it into the celery tasks

The reporter is instantiated once per Celery task invocation and
threaded through the `_internal_*` helpers as a `progress_reporter`
argument (defaulting to `None` for the benefit of existing test call
sites; a `None` default becomes `NullProgressReporter` via a local
`coerce_reporter` helper — same idiom the library uses). No reporter
state crosses the Celery serialisation boundary — it's constructed
inside the worker process.

```python
# tasks.py — top of each @app.task function
from opendlp.adapters.sortition_progress import DatabaseProgressReporter

@app.task(bind=True, on_failure=_on_task_failure)
def run_select(self, task_id, data_source, ..., session_factory=None):
    _set_up_celery_logging(task_id, session_factory=session_factory)
    reporter = DatabaseProgressReporter(
        task_id=task_id,
        session_factory=session_factory,
    )

    success, features, people, already_selected, load_report = _internal_load_gsheet(
        ..., progress_reporter=reporter, session_factory=session_factory
    )
    ...
    success, selected_panels, select_report = _internal_run_select(
        ..., progress_reporter=reporter, session_factory=session_factory
    )
    ...
    write_report = _internal_write_selected(
        ..., progress_reporter=reporter, session_factory=session_factory
    )
```

Inside `_internal_run_select`, the reporter is passed straight to the
library:

```python
# _internal_run_select (tasks.py:353)
success, selected_panels, report = run_stratification(
    features=features,
    people=people,
    number_people_wanted=number_people_wanted,
    settings=settings,
    test_selection=test_selection,
    already_selected=already_selected,
    progress_reporter=progress_reporter,   # OpenDLP DatabaseProgressReporter
)
```

Tasks that need a reporter instance:

- `run_select` — used by gsheet selection. Covers `read_gsheet` →
  library phases → `write_gsheet`.
- `run_select_from_db` — used by DB selection. Covers the library
  phases only (we're not adding DB read/write phases in this pass; see
  below).
- `load_gsheet` — used by the standalone gsheet "validate data"
  action. Covers `read_gsheet` only.

### Gsheet read / write phases

Loading a spreadsheet via gspread and writing the selected/remaining
tabs back are both slow enough to dominate quick selections, so they
get their own OpenDLP-emitted phases layered on top of the library's
phases. The simplest viable shape is: two OpenDLP phase names with no
`current` / `total` at all — the user just sees a translated label
saying "Reading spreadsheet…" / "Writing results back to spreadsheet…",
which is already a huge upgrade over a bare spinner.

Option comparison (these were Chewie's three suggestions):

| Option                                       | Verdict      | Why                                                                                                                                                                        |
| -------------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Call `reporter.start_phase("read_gsheet")`   | **Chosen**   | Reuses the single DB-write path inside the reporter, no duplication of JSON-shape logic, matches the library's own API so it's one mental model. Plumbing is trivial.     |
| Write directly to the `progress` field       | Rejected     | Duplicates the JSON shape in two places (reporter + direct writes) and would drift if the shape changes.                                                                  |
| Add `phase=` arg to `_update_selection_record` | Rejected   | Couples status/log mutations with progress writes. Progress writes need to be status-neutral; `_update_selection_record` would have to special-case them. More tangle.    |

So `_internal_load_gsheet` and `_internal_write_selected` each grow a
`progress_reporter` argument (default `None`, coerced inside) and start
their phase once:

```python
# _internal_load_gsheet
def _internal_load_gsheet(..., progress_reporter=None, session_factory=None):
    reporter = progress_reporter or NullProgressReporter()
    reporter.start_phase("read_gsheet", total=None)
    ...
```

```python
# _internal_write_selected
def _internal_write_selected(..., progress_reporter=None, session_factory=None):
    reporter = progress_reporter or NullProgressReporter()
    reporter.start_phase("write_gsheet", total=None)
    ...
```

No `update()` calls — these phases have no granular ticks. The next
`start_phase` (from the library's MW loop, or from
`_internal_write_selected`) implicitly ends the previous one, so
`end_phase` is unnecessary. The write sites never touch the JSON column
themselves — everything flows through the reporter.

**Not covered in this pass:** `read_db` / `write_db` phases for
`_internal_load_db` and `_internal_write_db_results`. These are fast
enough today that the library phases dominate total time; if that
changes, adding them later is a two-line change on top of the same
infrastructure. Worth noting in the template so the unknown-phase
fallback stays honest.

### Clearing `progress` on completion

Decision: the `progress` JSON is cleared to `None` when the task
reaches any terminal status (`COMPLETED`, `FAILED`, `CANCELLED`) so
finished rows don't show a stale "45 of 200" forever.

Implementation: add the behaviour to `_update_selection_record` — if
the incoming `status` is in `{COMPLETED, FAILED, CANCELLED}`, set
`record.progress = None` as part of the same transaction. Also call
`flag_modified(record, "progress")` when attached. This is the *only*
place `_update_selection_record` touches `progress`; live writes still
go exclusively through the reporter. The separation stays: writes =
reporter, terminal-state cleanup = status updater.

`_on_task_failure` (`tasks.py:67`) also marks records as failed in some
hard-failure paths and should clear `progress` too. Easiest: factor
the clear into the `_update_selection_record` call it already makes.

### Exposing progress to the page

`get_selection_run_status()` currently returns a `RunResult` with
`run_record`, `run_report`, `log_messages`, `success`. The modal poll
templates already receive the entire `run_record`, so adding a new
domain/ORM field makes `run_record.progress` available to the template
with **no service-layer changes required**.

### Rendering — template changes

Both `db_selection_progress_modal.html` and `selection_progress_modal.html`
need a new block that renders between the status badge and the log
messages. Proposed macro `progress_indicator(progress, selection_algorithm)`
in `templates/backoffice/components/modal.html` so both templates share
it:

- When `run_record.progress` is `None`: fall back to the current generic
  `spinner(_("Processing..."))`.
- Otherwise, switch on `progress.phase` → translated label (see below)
  and render either a determinate bar (`current / total`) if `total` is
  not null, or a spinner + iteration counter otherwise.
- Include a "last update" relative time is optional — polling makes it
  redundant.

Phase → translated label map (initial proposal — bikeshed later). The
first two are OpenDLP-emitted; the remainder come straight from
sortition-algorithms.

| phase                   | source   | label                                                |
| ----------------------- | -------- | ---------------------------------------------------- |
| `read_gsheet`           | OpenDLP  | `_("Reading spreadsheet…")`                          |
| `write_gsheet`          | OpenDLP  | `_("Writing results back to spreadsheet…")`          |
| `legacy_attempt`        | library  | `_("Running selection attempt %(current)s of %(total)s", ...)` |
| `multiplicative_weights`| library  | `_("Finding diverse committees (%(current)s of %(total)s rounds)", ...)` |
| `maximin_optimization`  | library  | `_("Optimising for maximin fairness (iteration %(current)s)", ...)` |
| `nash_optimization`     | library  | `_("Optimising for Nash fairness (iteration %(current)s)", ...)` |
| `leximin_outer`         | library  | `_("Optimising for leximin fairness (%(current)s of %(total)s fixed)", ...)` |
| `diversimax`            | library  | `_("Running diversimax optimisation")`               |

These strings need to flow through `just translate-regen`.

For `read_gsheet` / `write_gsheet` / convergence phases with
`total=None`, the template should render a spinner + label, no
progress bar. For phases with a finite `total`, render a determinate
bar using `current / total`.

**Unknown phase fallback:** if the library adds a new phase we haven't
translated yet (or we add a new OpenDLP one like `read_db`), render
the raw phase name in a plain format so the UI still shows motion. Do
not crash the modal.

### Tests

- **Unit** (`tests/unit/adapters/test_sortition_progress.py`):
  - Constructing reporter doesn't touch the DB.
  - `start_phase` always writes, even if called in quick succession.
  - `update` within `min_interval` is dropped (inject a clock via
    monkeypatching `time.monotonic`).
  - `update` beyond `min_interval` writes.
  - Missing record is a silent no-op, not an exception.
- **Integration** (`tests/integration/`):
  - Run `_internal_run_select` against a real fake UoW / in-memory DB
    with a tiny dataset, check `progress` column is populated with at
    least one phase transition.
- **E2E / BDD:** optional — the existing BDD flow for starting a
  selection can assert the `progress` column becomes non-null, but the
  test would need a pool big enough for the MW loop to tick more than
  once. Probably not worth the runtime cost.
- **Template unit test:** snapshot the rendered modal for each phase to
  guard against the macro regressing when phases are added.

Sortition-algorithms already tests that a raising reporter cannot kill
`run_stratification` (commit `10b757e`), so OpenDLP doesn't need to
re-verify that.

### Things I considered and rejected

- **Repurposing `status_stages`.** Dead field today, but the shape
  (`list[{name, status}]`) is wrong for live progress and repurposing it
  leaves less room for a future "load → select → write" stage display.
- **Discrete columns (`progress_phase`, `progress_current`,
  `progress_total`).** More migration churn, no real benefit for a
  rarely-queried column, doesn't match the existing JSON-heavy pattern.
- **Writing *live* progress via `_update_selection_record`.** That
  helper is append-only for log_messages and couples status mutations
  to the write. Live progress writes need to be status-neutral and
  should not trigger log_messages churn, so they go through the
  reporter instead. (The terminal-state *clear* of `progress` back to
  `None` does happen inside `_update_selection_record` — it's a status
  mutation, so it belongs there.)
- **Storing English `message` strings in the DB.** Forces the DB row's
  locale to whatever the worker was running as. Phase names are a
  stable public API — translate at render time.
- **Composite / Rich reporter.** The library ships
  `RichProgressReporter` for CLI use. Worker stdout gets captured into
  OpenDLP logs anyway, so piling on a second reporter gains nothing in
  production. Skip it.
- **Reducing the modal poll interval.** 2s is fine — writes are
  throttled to 1Hz so anything faster is wasted HTTP churn.

## Files that will need to change

Implementation will touch roughly:

- `migrations/versions/<new>.py` — add `progress` JSON column. Create
  with `uv run alembic revision --autogenerate -m "add progress
  column to selection_run_records"`.
- `src/opendlp/adapters/orm.py` — add column to the
  `selection_run_records` table definition.
- `src/opendlp/domain/assembly.py` — add
  `progress: dict[str, Any] | None = None` field to
  `SelectionRunRecord` (JSON-backed).
- `src/opendlp/adapters/sortition_progress.py` — new module, the
  `DatabaseProgressReporter` class (~60 lines).
- `src/opendlp/entrypoints/celery/tasks.py`:
  - Instantiate `DatabaseProgressReporter` at the top of each of the
    three tasks that need it: `run_select`, `run_select_from_db`,
    `load_gsheet`.
  - Thread `progress_reporter` through the three `_internal_*` helpers
    that need it: `_internal_load_gsheet`, `_internal_run_select`,
    `_internal_write_selected`.
  - In `_internal_load_gsheet` and `_internal_write_selected`, call
    `reporter.start_phase("read_gsheet" | "write_gsheet", total=None)`
    at the start.
  - In `_internal_run_select`, pass `progress_reporter=reporter` to
    `run_stratification()`.
  - In `_update_selection_record`, clear `record.progress = None` when
    the incoming status is terminal (`COMPLETED`, `FAILED`,
    `CANCELLED`).
- `templates/backoffice/components/modal.html` — new
  `progress_indicator` macro with phase → translated label mapping
  (determinate bar vs spinner depending on whether `total` is set).
- `templates/backoffice/components/db_selection_progress_modal.html` —
  call the new macro in place of the generic spinner.
- `templates/backoffice/components/selection_progress_modal.html` — same.
- Translation files — re-run `just translate-regen` after touching the
  Jinja strings.
- Tests in `tests/unit/adapters/` and `tests/integration/`.

No service-layer changes needed — `get_selection_run_status` already
returns the full `run_record`, so the template sees `progress`
automatically once the domain field exists.

## Implementation plan — phased TDD checklist

Ordered so each phase is independently testable and shippable.
**Every phase follows red → green**: write a failing test first, watch
it fail for the expected reason, then make the minimum change to pass.
Commit at the end of each phase using a conventional-commit subject so
the history is reviewable.

### Phase 1 — schema: `progress` JSON column ✅

Standalone schema change. No behaviour yet.

- [x] **RED:** `tests/integration/test_selection_run_record_progress.py`
  round-trip tests.
- [x] **GREEN:** `progress` field on `SelectionRunRecord`, column on
  `selection_run_records`, migration `0dd36337f48e`.
- [x] `just check` clean, `just test-nobdd` passes (1949 tests).
- [x] **Committed.**

### Phase 2 — `DatabaseProgressReporter` in isolation ✅

- [x] **RED:** `tests/unit/test_sortition_progress.py` with eight
  unit tests covering throttling, phase transitions, missing record,
  and `end_phase` no-op. Monkeypatches `time.monotonic` and
  `bootstrap` inside the module.
- [x] **GREEN:** `src/opendlp/adapters/sortition_progress.py`
  implemented.
- [x] `just check` clean, unit + integration suite passes (1027
  tests).
- [x] **Committed.**

### Phase 3 — clear progress on terminal status ✅

- [x] **RED:** `TestUpdateSelectionRecordClearsProgress` in
  `tests/integration/test_celery_tasks.py` — four tests covering
  `COMPLETED`, `FAILED`, `CANCELLED` (should clear) and `RUNNING`
  (should preserve).
- [x] **GREEN:** added terminal-status clearing to
  `_update_selection_record` in `entrypoints/celery/tasks.py`.
- [x] `just check` clean, celery integration tests pass.
- [x] **Committed.**

### Phase 4 — wire reporter into `_internal_run_select` ✅

- [x] **RED:** `tests/unit/test_celery_tasks_progress.py` with two
  tests that mock `run_stratification` and assert the reporter
  kwarg is forwarded (and defaults to `None`).
- [x] **GREEN:** added `progress_reporter: ProgressReporter | None`
  kwarg to `_internal_run_select` and forwarded it into
  `run_stratification()`.
- [x] `just check` clean, celery + unit tests pass.
- [x] **Committed.**

### Phase 5 — emit `read_gsheet` phase from `_internal_load_gsheet` ✅

- [x] **RED:** `TestInternalLoadGsheetEmitsReadPhase` in
  `tests/unit/test_celery_tasks_progress.py` — recording reporter,
  mocked `select_data`, asserts a `start_phase("read_gsheet",
  total=None)` was emitted.
- [x] **GREEN:** added `progress_reporter` kwarg to
  `_internal_load_gsheet`; emits `start_phase("read_gsheet",
  total=None)` at the top, coerces `None` → `NullProgressReporter`.
- [x] `just check` clean, celery tests pass.
- [x] **Committed.**

### Phase 6 — emit `write_gsheet` phase from `_internal_write_selected` ✅

- [x] **RED:** `TestInternalWriteSelectedEmitsWritePhase` in
  `tests/unit/test_celery_tasks_progress.py`.
- [x] **GREEN:** `progress_reporter` kwarg plus
  `start_phase("write_gsheet", total=None)` at the top.
- [x] `just check` clean.
- [x] **Committed.**

### Phase 7 — instantiate reporter in each Celery task ✅

- [x] **RED:** `TestCeleryTasksInstantiateReporter` in
  `tests/unit/test_celery_tasks_progress.py` — three tests that
  patch `DatabaseProgressReporter` and the `_internal_*` helpers and
  assert the same reporter instance is forwarded to each helper.
- [x] **GREEN:** `run_select`, `run_select_from_db`, and `load_gsheet`
  now each instantiate a `DatabaseProgressReporter` at the top and
  pass it through to the `_internal_*` helpers they call.
- [x] `just check` clean, 1038 tests pass.
- [x] **Committed.**

### Phase 8 — template: `progress_indicator` macro ✅

- [x] **RED:** `tests/unit/test_progress_indicator_macro.py` — ten
  Jinja render tests covering None, read/write gsheet, library
  phases with and without totals, and unknown-phase fallback.
- [x] **GREEN:** `progress_indicator(progress)` macro in
  `templates/backoffice/components/modal.html`. If/elif chain over
  phase names, determinate bar when total is known, spinner-plus-label
  otherwise.
- [x] `just check` clean.
- [x] **Committed.**

### Phase 9 — wire macro into both modal templates ✅

- [x] **RED:** `tests/unit/test_progress_modal_wiring.py` — renders
  the full modal templates with a mock run_record and asserts the
  progress indicator output appears.
- [x] **GREEN:** both
  `templates/backoffice/components/db_selection_progress_modal.html`
  and `templates/backoffice/components/selection_progress_modal.html`
  now import `progress_indicator` and call it in place of the
  generic spinner.
- [x] `just check` clean, 1052 tests pass.
- [x] **Committed.**

### Phase 10 — translations

- [ ] Run `just translate-regen` to extract the new `_()` strings
  into the `.pot` and `.po` files.
- [ ] Eyeball the diff for the new message IDs; confirm no
  accidentally-extracted strings.
- [ ] For any language file that has translations, add placeholder
  translations (or leave fuzzy) per the project's existing
  convention — follow what `docs/translations.md` says.
- [ ] Run `just test` + `just check`.
- [ ] **Commit:** `i18n: extract selection progress phase strings`.

### Phase 11 — manual smoke test + cleanup

- [ ] Start local stack: `just start-services-docker` + `just run` +
  Celery worker.
- [ ] Start a DB selection against a test assembly with enough
  respondents that the MW loop takes a few seconds. Observe:
  - Modal shows "Reading spreadsheet…" briefly (if gsheet path) —
    OR jumps straight into a library phase for DB path.
  - Modal shows "Finding diverse committees (X of 200 rounds)" with
    a determinate bar advancing.
  - Modal shows the convergence-phase spinner + iteration counter.
  - (gsheet path only) Modal shows "Writing results back to
    spreadsheet…" near the end.
  - When the task finishes, the `progress` column is back to `None`
    (check via `just psql`) and the modal shows the completion UI.
- [ ] Test a deliberate failure path (e.g. break the spreadsheet
  URL) — confirm progress clears on `FAILED` too.
- [ ] Cancel a mid-run selection — confirm progress clears on
  `CANCELLED`.
- [ ] Grep for any stray `TODO` / debug print statements left in
  the diff.
- [ ] **Commit** any cleanup.
- [ ] Open PR; summary should mention the phase set and link to this
  research doc.

### Phases at a glance

| # | Phase                                        | New files                                          | Touched files                                                   |
| - | -------------------------------------------- | -------------------------------------------------- | --------------------------------------------------------------- |
| 1 | `progress` column + domain field             | migration, round-trip test                         | `domain/assembly.py`, `adapters/orm.py`                         |
| 2 | `DatabaseProgressReporter` in isolation      | `adapters/sortition_progress.py`, unit tests       | —                                                               |
| 3 | Clear progress on terminal status            | new tests                                          | `entrypoints/celery/tasks.py`                                   |
| 4 | Wire reporter into `_internal_run_select`    | new tests                                          | `entrypoints/celery/tasks.py`                                   |
| 5 | Emit `read_gsheet` phase                     | new tests                                          | `entrypoints/celery/tasks.py`                                   |
| 6 | Emit `write_gsheet` phase                    | new tests                                          | `entrypoints/celery/tasks.py`                                   |
| 7 | Instantiate reporter in Celery tasks         | new task-level tests                               | `entrypoints/celery/tasks.py`                                   |
| 8 | `progress_indicator` template macro          | new template tests                                 | `templates/backoffice/components/modal.html`                    |
| 9 | Wire macro into modals                       | extend tests                                       | two `*_progress_modal.html` templates                           |
| 10 | Translations                                 | —                                                  | `.po` / `.pot` files                                            |
| 11 | Manual smoke + cleanup                       | —                                                  | —                                                               |

After Phase 9, the feature is user-visible; Phases 10-11 are polish.
Phases 1-3 can merge independently without shipping user-facing
change if we want smaller PRs. Phases 4-9 are tightly coupled and
probably ship as one PR.

## Decisions (resolved with Chewie)

1. **New JSON column `progress`, not a repurpose of `status_stages`.**
   `status_stages` stays untouched for now; may be deleted in a later
   pass but not in this one.
2. **Throttle interval: 1.0s.** Matches the docs recipe and the 2s
   poll interval. If MW loops feel laggy we can revisit.
3. **No cancel-awareness inside the reporter.** Celery revoke +
   library `TaskRevokedError` on the next yield already handles
   cancellation, and `ErrorSwallowingReporter` would swallow any
   raise-to-short-circuit anyway.
4. **Clear `progress` to `None` on terminal status.** Done inside
   `_update_selection_record` whenever the incoming status is
   `COMPLETED`, `FAILED`, or `CANCELLED`. Keeps finished rows clean.
5. **Gsheet read/write get OpenDLP-emitted phases
   (`read_gsheet` / `write_gsheet`).** Emitted via the same reporter by
   `_internal_load_gsheet` and `_internal_write_selected`, using
   `reporter.start_phase(..., total=None)` — no `update` ticks. DB
   read/write phases are explicitly **not** added in this pass; they
   can be layered on later if their duration ever starts to matter.
