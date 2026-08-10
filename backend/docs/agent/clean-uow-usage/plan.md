# Clean up UnitOfWork usage

Status: step 1 committed (`8bc870fc`), steps 2-4 not started.

## The problem

`pytest --ignore=tests/bdd -n auto --maxprocesses=8` hung at 99% on one
developer's laptop while passing serially and passing on a VM. The cause was not
flakiness in the test harness.

### Evidence

With the run wedged, `pg_stat_activity` showed one xdist worker deadlocked
against itself:

```
pid 271 | opendlp_test_gw7 | idle in transaction | SELECT ... FROM assembly_respondent_gsheets
                                                   WHERE assembly_id = ... LIMIT 1
pid 269 | opendlp_test_gw7 | active, Lock/relation | DROP TABLE assembly_respondent_gsheets
```

`pg_locks` confirmed pid 271 held `AccessShareLock` on
`assembly_respondent_gsheets` and nothing else, so its transaction consisted of
that single leaked `SELECT`. The `DROP TABLE` came from
`orm.metadata.drop_all()` in the `_postgres_tables` session-teardown fixture,
needed `ACCESS EXCLUSIVE`, and waited indefinitely because no `lock_timeout` was
set. The worker's last test was
`tests/e2e/test_backoffice_respondents.py::TestBackofficeViewRespondentsPage::test_view_respondents_page_with_csv_source`,
which GETs the respondents page.

### Root cause

`view_assembly_respondents` (`entrypoints/blueprints/respondents.py`) closes its
`with uow:` block, then keeps using `uow` for three more reads. The comment on
those lines documents this as intentional reuse.

`SqlAlchemyUnitOfWork.__exit__` calls `self.session.close()` but leaves
`self._session` pointing at the Session. **A closed SQLAlchemy Session is still
usable** - the next query silently autobegins a new transaction that nothing
goes on to commit or close. The connection stays checked out and `idle in
transaction`.

### Why it only bit under xdist

The abandoned Session sits in a reference cycle, so it survives until the
generational collector runs; collection returns the connection to the pool and
rolls the transaction back. Run enough tests afterwards and it is cleaned up in
time. The deadlock only occurs when the leaking test is the **last test on its
worker**. `-n auto` derives worker count from CPU count, so the test-to-worker
distribution - and therefore whether that test lands last - differs per machine.

### The bigger finding

The leak is a symptom. Scanning the tree found the codebase split between two
opposite conventions for who owns the transaction boundary:

```
146 functions open their own `with uow:`   (~126 in service_layer/, 20 in blueprints/dev.py)
 97 functions expect the caller to manage it
```

You cannot tell which convention a function follows without opening it, so call
sites guess, and roughly half the time they guess wrong. 37 call sites currently
use a `uow` outside any `with` block.

`get_assembly_with_permissions` (`service_layer/assembly_service.py`) is the
canonical case: it opens its own `with uow:` and is called from *inside* routes'
`with uow:` blocks. **Same-UnitOfWork nesting is therefore pervasive**, and
because `__exit__` commits and closes unconditionally, an inner block commits
the outer block's partial work and closes its session mid-flight:

```python
with uow:
    assembly = get_assembly_with_permissions(uow, ...)   # commits + closes here
    respondents, total_count = get_respondents_for_assembly_paginated(uow, ...)
    ...                                                   # runs on a resurrected session
```

So routes are not atomic today. This is a live correctness bug independent of
the test hang, and it has not been demonstrated at runtime - it is read off the
code. Worth a reproducing test before relying on it.

## The decision

**Only entrypoints open `with uow:`.** Flask routes, CLI commands and Celery
tasks own the transaction boundary. Service-layer functions never open their own
context; they assume an open one.

### Why not a re-entrant UnitOfWork (depth counter)

A depth counter was the obvious contained fix - increment on enter, only
commit/close at depth 0 - and it was rejected as the destination:

- A naive counter is wrong on the exception path, and live code hits it. There
  are `contextlib.suppress(Exception)` blocks wrapped around calls to
  self-managing service functions. Today the inner `__exit__` rolls back and
  closes and the outer resurrects a clean session, so it recovers by accident.
  Under a naive counter the inner exit does nothing, the suppressed failure
  leaves the transaction dirty, and the outer block continues poisoned.
- Doing it correctly needs savepoints (`begin_nested()`) plus a rollback-only
  flag, i.e. Spring's `setRollbackOnly`. That is real complexity whose failure
  mode is partial commits.
- It legitimises nesting, so transaction boundaries stay implicit and the 60/40
  convention split never gets resolved.

### Note on the reference architecture

CLAUDE.md cites *Architecture Patterns with Python*, and that book puts
`with uow:` **in the service layer** - today's majority convention, not the one
chosen here. The book assumes one service call per request and has no answer for
routes composing several reads and writes, which is where this codebase is.

This is therefore a deliberate departure from the cited reference. It must be
written up in CLAUDE.md so it does not get "fixed" back.

## Step 1 - stop the hang (DONE, `8bc870fc`)

`tests/conftest.py`:

- `LOCK_TIMEOUT_MS = 30_000` applied to the test engine via
  `connect_args={"options": "-c lock_timeout=..."}`, so a lock wait raises
  instead of hanging pytest with no output.
- `_postgres_tables` skips `drop_all` under xdist. Each worker owns a whole
  database that `_worker_database` drops next, after `pg_terminate_backend`, so
  the table drop was redundant work that could block on a leaked lock.

`tests/integration/test_db_test_harness.py` covers both: the engine reports a
non-zero `lock_timeout`, and a conflicting lock request raises `OperationalError`
rather than waiting.

This makes the suite survivable, not correct. The session leak is untouched.

## Step 2 - migrate the service layer

Convert self-managing service functions to caller-manages, one module at a time.
Each slice is its own commit and must leave the suite green.

Suggested order, smallest blast radius last:

| Slice | Module | Self-managing fns |
|---|---|---|
| 1 | `assembly_service.py` | 25 |
| 2 | `user_service.py` | 18 |
| 3 | `registration_page_service.py` | 16 |
| 4 | `respondent_service.py` | 11 |
| 5 | `respondent_field_schema_service.py` | 11 |
| 6 | `invite_service.py`, `email_template_service.py` | 7, 7 |
| 7 | `two_factor_service.py`, `password_reset_service.py` | 6, 5 |
| 8 | `registration_image_service.py`, `registration_document_service.py` | 5, 5 |
| 9 | `email_confirmation_service.py`, `registration_submission_service.py`, `email_send_service.py` | 4, 2, 2 |

Start with `assembly_service.py`: it holds `get_assembly_with_permissions`, which
is what nearly everything nests through, so converting it removes most nesting in
one go.

### Mechanics per slice

1. Remove `with uow:` from the function body. Drop any internal `uow.commit()`
   where the caller's block now owns the commit - but keep it where the function
   deliberately commits mid-sequence, and convert those to `commit_and_reset()`.
2. Update the docstring to state the caller manages the context. Several
   caller-manages functions already say "The caller is expected to manage the
   `uow` context (`with uow: ...`)" - reuse that wording verbatim.
3. Fix every call site: wrap in the caller's existing block where one exists,
   otherwise open one at the entrypoint.
4. Keep the block off `render_template` and external I/O. `export_respondents_to_gsheet`
   already holds a caller-managed uow across a gspread network write; do not make
   that shape more common than it has to be, or production accrues
   idle-in-transaction connections.
5. Run `just test-nobdd && just test-bdd-headless` (never concurrently - they
   share a database).

### Known call sites needing attention

37 sites use `uow` outside any block. Distribution on the clean tree:

```
9  entrypoints/blueprints/respondents.py
7  entrypoints/blueprints/targets.py
5  entrypoints/blueprints/respondent_field_schema.py
5  entrypoints/blueprints/gsheets.py
3  entrypoints/blueprints/backoffice.py
3  entrypoints/blueprints/auth.py
2  entrypoints/blueprints/gsheets_legacy.py
1  entrypoints/cli/invites.py
1  entrypoints/cli/database.py
1  entrypoints/blueprints/respondents_legacy.py
```

Not all are bugs *today* - where the callee is self-managing, the call is
currently correct. After step 2 every one of them becomes a bug, so treat this
list as the step 2 worklist rather than a defect list.

Two are false positives from the scanner and need no change:
`cli/database.py` (an `assert isinstance(uow, SqlAlchemyUnitOfWork)`) and
`auth.py` sites that pass `uow` to `_verify_2fa_code_for_user` /
`_complete_2fa_login`, which are entrypoint-level helpers.

## Step 3 - add the guard

Once no service function opens its own context, make misuse impossible rather
than merely discouraged. Landed as the final commit of the migration, because
until then it breaks everything.

In `SqlAlchemyUnitOfWork`:

- Track whether the context is open. `session` raises if it is not.
- `__exit__` uses `try/finally` so a failing commit still releases the
  connection - the current implementation leaks the session if `commit()`
  raises.
- `__exit__` clears `self._session` so a closed Session can never be
  resurrected.
- `__exit__` swaps each repository attribute for a placeholder that raises on
  attribute access. This matters: repositories hold their **own** reference to
  the session, so guarding only the `session` property does not catch
  `uow.users.get(...)` after the block.

Use `setattr` with names read off `AbstractUnitOfWork.__annotations__` rather
than defining `__getattr__` on the UnitOfWork - a `__getattr__` would make mypy
accept any attribute name and lose typo detection across the whole codebase.

Decide separately whether `FakeUnitOfWork` should enforce the same rule.
Currently it does not, so component tests will not catch regressions - only e2e
will. Aligning it would break the very common `uow = FakeUnitOfWork(); uow.users.add(...)`
idiom in unit tests, so this is a real cost, not a free win.

## Step 4 - make the convention enforceable

Add a checker to the repo (e.g. `scripts/check_uow_convention.py`, wired into
`just check`) that fails if any function in `service_layer/` opens `with uow:`.
Cheap to write with `ast`: walk each `FunctionDef`, look for a `With` whose
`context_expr` is a `Name` called `uow`.

A companion check for "uses `uow` outside any `with uow:` block" is useful during
the migration but noisier - it cannot tell a bug from a call to a self-managing
callee. After step 2 that ambiguity disappears and the check becomes exact.

Watch for two scanner blind spots found the hard way: uses *before* the first
`with` block in a function, and the `with uow:` header's own `Name` node
counting as a use.

## Other cleanups noticed

Not part of the UnitOfWork work, but found while investigating. Each deserves
its own issue.

### Test warnings

The suite only started reaching its summary once the hang was fixed, which
surfaced three warnings. CLAUDE.md requires pristine test output, so these will
block eventually:

- `entrypoints/celery/tasks.py:369` - `add_lines() is deprecated. Functions
  should return RunReport instead of list[str], and use add_report() to merge
  them.` (sortition-algorithms API change.)
- `tests/integration/test_orm.py:1065` - `SAWarning: New instance
  <SelectionRunRecord> with identity key ... conflicts with persistent
  instance`. The test is probably adding an object that is already in the
  identity map.
- `tests/unit/test_sortition_service.py::TestGetSelectionRunStatus::test_get_selection_run_status_exists`
  - `PytestUnraisableExceptionWarning` from Celery's `AsyncResult.__del__`
  (`ValueError: task_id must not be empty`). A result object is being finalised
  with an empty id.

### Exception handling around service calls

Several routes wrap service calls in `contextlib.suppress(Exception)` or bare
`except Exception` to mean "this config may not exist yet" - for example the
gsheet and CSV-status lookups in `respondents.py` and
`respondent_field_schema.py`, and `_can_manage` in `targets.py` (which carries a
`# noqa: S110`).

This conflicts with CLAUDE.md's "catch narrowly" rule, and it actively hides
database errors: a suppressed DB failure leaves the transaction poisoned and the
next query fails somewhere unrelated. Narrow these to the specific domain
exceptions (`NotFoundError` and friends). Worth doing **before** step 2, since
the migration makes these run inside the caller's transaction.

### Legacy `uow2`

`AbstractUnitOfWork.commit_and_reset` exists specifically to replace "the older
pattern of opening `uow`/`uow2`/`uow3` in one request", but
`respondents_legacy.py` still opens a `uow2`. Fold it into the migration or
delete it with the legacy blueprint.

### No app-context teardown for the UnitOfWork

`bootstrap.get_flask_uow()` hands out a UnitOfWork per call and nothing is
registered with `teardown_appcontext`. There is no backstop if a request leaves
a session open. Consider registering one as defence in depth, independent of the
convention work.

### `blueprints/dev.py`

20 self-managing functions. It is a dev-only scratch space held to a lower bar
by design (see the note at the top of that file), so decide explicitly whether
it is in or out of scope for step 2 rather than letting it drift.

## Appendix - scanner scripts

Working versions used to produce the figures above. Run as
`uv run python <script> src/opendlp`.

### Which functions open their own context

```python
import ast, pathlib, sys

def opens_own_context(func):
    return any(
        isinstance(n, ast.With)
        and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "uow" for i in n.items)
        for n in ast.walk(func)
    )

def takes_uow(func):
    a = func.args
    return "uow" in [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]

for path in sorted(pathlib.Path(sys.argv[1]).rglob("*.py")):
    for func in ast.walk(ast.parse(path.read_text())):
        if isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef) and takes_uow(func):
            verdict = "SELF-MANAGING" if opens_own_context(func) else "caller-manages"
            print(f"{verdict:15} {func.name:45} {path}:{func.lineno}")
```

### Which call sites use `uow` outside any block

```python
import ast, pathlib, sys

def scan(path):
    hits = []
    for func in ast.walk(ast.parse(path.read_text())):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        covered, headers = {}, set()
        for stmt in ast.walk(func):
            if not isinstance(stmt, ast.With):
                continue
            for item in stmt.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Name):
                    headers.add(id(ctx))
                    if "uow" in ctx.id.lower():
                        start = stmt.body[0].lineno
                        end = stmt.body[-1].end_lineno or stmt.body[-1].lineno
                        covered.setdefault(ctx.id, []).append((start, end))
        for node in ast.walk(func):
            if not isinstance(node, ast.Name) or node.id not in covered:
                continue
            if id(node) in headers or isinstance(node.ctx, ast.Store):
                continue
            if any(a <= node.lineno <= b for a, b in covered[node.id]):
                continue
            hits.append((node.lineno, func.name, node.id))
    return sorted(set(hits))

for path in sorted(pathlib.Path(sys.argv[1]).rglob("*.py")):
    for line, func, name in scan(path):
        print(f"{path}:{line}  {func}()  uses `{name}` outside any `with` block")
```
