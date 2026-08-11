# Clean up UnitOfWork usage

Status: step 1 committed (`8bc870fc`). Steps 2-4 and the read-only workstream
not started.

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
146 functions open their own `with uow:`   (124 service_layer/, 20 blueprints/dev.py,
                                            2 blueprint helpers in blueprints/auth.py)
 97 functions expect the caller to manage it
```

You cannot tell which convention a function follows without opening it, so call
sites guess, and roughly half the time they guess wrong. 37 call sites currently
use a `uow` outside any `with` block.

`get_assembly_with_permissions` (`service_layer/assembly_service.py`) is the
canonical case: it opens its own `with uow:` and is called from _inside_ routes'
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

### Note on the reference architecture

CLAUDE.md cites _Architecture Patterns with Python_, and that book puts
`with uow:` **in the service layer** - today's majority convention, not the one
chosen here. The book assumes one service call per request and has no answer for
routes composing several reads and writes, which is where this codebase is.

This is therefore a deliberate departure from the cited reference. It must be
written up in CLAUDE.md so it does not get "fixed" back.

## Options considered

### A - re-entrant UnitOfWork (depth counter). Rejected.

Increment on enter, only commit/close at depth 0. The obvious contained fix -
one class, no call-site churn - and rejected as the _destination_:

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

### B - `with uow:` at entrypoints only. Chosen.

All 146 self-managing functions to convert - 124 in `service_layer/`, 20 in
`blueprints/dev.py`, 2 blueprint helpers in `blueprints/auth.py` - plus 36 call
sites (37 less the one in `respondents_legacy.py`, which is being deleted). The
edits are mechanical, local, and individually reviewable. Sized in steps 2-4
below.

### C - one service call per entrypoint, `with uow:` in the service layer. Rejected.

The _Architecture Patterns with Python_ shape: each route makes exactly one
service call, and that function owns the transaction. Attractive because it
matches the cited reference and confines transactions to one layer.

Measured across 198 routes (excluding `dev.py`):

| Service calls per route | Routes |
| ----------------------- | ------ |
| 0                       | 29     |
| 1                       | 99     |
| 2                       | 30     |
| 3                       | 20     |
| 4                       | 17     |
| 5                       | 3      |

So ~70 routes compose several service calls and would need a new composed
function; the 29 with zero drive repositories directly and would need one
written from scratch. About 99 routes touched, against option B's 146 mechanical
function edits.

The count understates the cost. `gsheets.py::view_assembly_selection` is the
worst case - GET, 3 uow blocks, 5 service calls, **156 lines, 31 template
variables**:

- Collapsing it needs a page-context DTO of ~31 fields.
- Presentation logic is interleaved with the reads (`data_source`, which tabs
  are enabled, which modal is open). That either moves into the service layer,
  where it does not belong, or into a separate presentation helper called after
  the single service call - correct, but that is _two_ new layers.
- Each read carries its own `try/except` with a different fallback ("no gsheet
  is fine", "no CSV is fine", "log and carry on for history"). Preserving that
  behaviour pushes route-level error presentation down into the service layer.

`view_assembly_respondents` (105 lines, 14 template vars) and
`view_schema` (76 lines, 14) are the same shape, smaller.

Estimated at 3-5x option B's effort on the production side, with materially
higher risk of behaviour change.

#### What option C avoids, and what it still costs

Sizing the test work (see step 2) turned up a real advantage for C that the
first draft of this section missed. Under C, service functions **keep** their
own `with uow:`, so the ~800 bare service calls and ~575 bare repository
accesses in the tests keep working unchanged. Option B's roughly 768 test
migrations are avoided almost entirely. That is a genuine point in C's favour.

Two things that are *not* objections to C, having checked:

- Intra-service nesting is nearly absent. Of 100 service-to-service calls that
  pass a `uow`, only **3** have a self-managing function calling another
  self-managing function (`submit_registration`, `get_user_accessible_assemblies`,
  `find_or_create_oauth_user`). C would not have to untangle a web of nested
  service calls.
- Private helpers already follow a clean rule: all **20** private
  (`_`-prefixed) service functions are caller-manages, without exception.

What C does still cost, beyond the route rewrites:

- The public service layer is genuinely inconsistent, not latently rule-governed:
  **124 public functions self-manage, 49 public functions are caller-manages**.
  C has to convert those 49 in the *opposite* direction to option B.

So the honest comparison is not "B is cheaper" but a difference in risk profile:

| | Option B | Option C |
|---|---|---|
| Function conversions | 146 | 49 (opposite direction) |
| Call sites | 36 | - |
| Route rewrites | - | ~99, with new DTOs |
| Test migrations | ~768 | close to zero |
| Risk per edit | low, mechanical | high, judgement per route |

Option B is high-volume and low-risk: most of its edits are a fixture swap that
a reviewer can scan. Option C is lower-volume and higher-risk: each route rewrite
relocates presentation logic and can silently change behaviour. Both fix the leak
and both make routes atomic.

B remains the choice on that basis, but the test-churn asymmetry is material
enough that it is worth re-confirming rather than assuming.

**The distinction worth keeping:** "one service call per route" is a
_code-organisation_ goal; "who owns the transaction boundary" is a _correctness_
question. Option C conflates them. Under option B you can still extract a
page-context function for the 156-line routes - it is simply caller-manages, so
it is pure refactoring with no transaction semantics at stake. Take that
tidiness opportunistically where it pays, rather than betting the migration on
it.

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

## Step 2 - move the context up to the entrypoints

Convert self-managing functions to caller-manages, one module at a time. Mostly
the service layer, but slices 10 and 11 cover blueprint helpers that open their
own blocks and fall under the same rule. Each slice is its own commit and must
leave the suite green.

Suggested order, smallest blast radius last:

| Slice | Module                                                                                         | Self-managing fns |
| ----- | ---------------------------------------------------------------------------------------------- | ----------------- |
| 1     | `assembly_service.py`                                                                          | 25                |
| 2     | `user_service.py`                                                                              | 18                |
| 3     | `registration_page_service.py`                                                                 | 16                |
| 4     | `respondent_service.py`                                                                        | 11                |
| 5     | `respondent_field_schema_service.py`                                                           | 11                |
| 6     | `invite_service.py`, `email_template_service.py`                                               | 7, 7              |
| 7     | `two_factor_service.py`, `password_reset_service.py`                                           | 6, 5              |
| 8     | `registration_image_service.py`, `registration_document_service.py`                            | 5, 5              |
| 9     | `email_confirmation_service.py`, `registration_submission_service.py`, `email_send_service.py` | 4, 2, 2           |
| 10    | `blueprints/dev.py`                                                                            | 20                |
| 11    | `blueprints/auth.py` helpers                                                                   | 2                 |

Start with `assembly_service.py`: it holds `get_assembly_with_permissions`, which
is what nearly everything nests through, so converting it removes most nesting in
one go.

### Slice 10 - `blueprints/dev.py` (in scope)

`dev.py` is in scope. The rule there is the same as everywhere else: `with uow:`
only at the top level.

It is the cheapest slice in the list despite the count, because every handler is
dispatched from one place:

- 5 routes, and 25 `_handle_*` helpers - 20 self-managing, 5 already
  caller-manages.
- `_execute_service` looks the handler up in `_SERVICE_HANDLERS`, calls
  `bootstrap.get_flask_uow()`, and returns `handler(uow, params)`.

So the whole module is one `with uow:` around that single `handler(uow, params)`
call, plus stripping the block from the 20 self-managing handlers. One commit.

Note this does change `dev.py` behaviour: today each handler commits
independently, afterwards there is one transaction per request. For a dev-only
scratch tool that is fine, and arguably an improvement.

### Slice 11 - `blueprints/auth.py` helpers

`_verify_2fa_code_for_user` and `_complete_2fa_login` are blueprint helpers, not
service-layer functions, but they open their own blocks and so fall under the
same "top level only" rule. Their `with uow:` blocks move up into `verify_2fa`,
which already has three of its own - so this slice also collapses that route's
block count.

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

### What changes in the tests

This is the largest part of the work, larger than the production change, and it
had not been sized until now.

Tests call service functions directly and construct their own UnitOfWork inline
rather than taking one from a fixture:

```python
def test_create_assembly_success_admin(self):
    uow = FakeUnitOfWork()
    uow.users.add(admin_user)
    assembly = assembly_service.create_assembly(uow=uow, title=..., ...)
```

Both the `uow.users.add(...)` and the `create_assembly(uow=uow, ...)` sit outside
any `with uow:` block, and today that is correct because the service function
opens its own. After step 2 neither works.

| | Count |
|---|---|
| Service calls outside any `with uow:` | 800, in 33 files |
| Bare `uow.<repo>` outside any `with uow:` | 575, in 29 files |
| Test files affected | 47 |

Worst files: `test_registration_page_service.py` (147 service calls),
`test_assembly_service_targets.py` (80), `test_respondent_field_schema_service.py`
(79), `test_sortition_service.py` (90 bare repository accesses).

#### Use a fixture, do not indent 700 test bodies

The obvious fix - wrap each test body in `with FakeUnitOfWork() as uow:` -
re-indents every affected test and makes the diff unreviewable. Instead provide
an already-entered UnitOfWork as a fixture:

```python
@pytest.fixture
def uow():
    with FakeUnitOfWork() as u:
        yield u
```

The test then drops its construction line and takes `uow` as a parameter, with
no reflow of the body:

```python
def test_create_assembly_success_admin(self, uow):
    uow.users.add(admin_user)
    assembly = assembly_service.create_assembly(uow=uow, title=..., ...)
```

The block is held open for the whole test, so every existing bare call is inside
a context and needs no edit. `__exit__` runs at teardown, after the assertions.

#### How far the fixture goes

Counted by how many UnitOfWork instances a single test constructs:

| | 1 uow | 2+ uow |
|---|---|---|
| `FakeUnitOfWork` | 538 (425 unit, 104 component, 9 integration) | 22 component |
| `SqlAlchemyUnitOfWork` | 133 (82 e2e, 44 integration, 7 unit) | **75** (42 e2e, 33 integration) |

The 538 single-fake tests are a mechanical fixture swap.

**The 75 multi-`SqlAlchemyUnitOfWork` tests must not get the fixture treatment.**
They open a second UnitOfWork precisely to prove that data committed by the first
is visible to a fresh session. Collapsing them into one fixture-held transaction
would leave them asserting nothing while still passing - the worst possible
outcome. Migrate those by hand, keeping the explicit second block.

The 22 multi-fake component tests need the same read, but the stakes are lower
since a shared `FakeStore` has no real transaction to be fooled by.

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

Not all are bugs _today_ - where the callee is self-managing, the call is
currently correct. After step 2 every one of them becomes a bug, so treat this
list as the step 2 worklist rather than a defect list.

One is a scanner false positive needing no change: `cli/database.py`, an
`assert isinstance(uow, SqlAlchemyUnitOfWork)` that never touches the database.

The `auth.py` sites passing `uow` to `_verify_2fa_code_for_user` /
`_complete_2fa_login` are correct today, because those helpers manage their own
context - but slice 11 converts them, so these sites do need changing.

### Legacy blueprints

`respondents_legacy.py` is being deleted and has deliberately not been kept
up to date, so its 1 site is **out of scope** - it goes when the blueprint goes.
That leaves 36 sites.

Open question for the other three legacy modules: `gsheets_legacy.py` (2 sites),
`targets_legacy.py` and `db_selection_legacy.py` (0 sites each, but both have
routes that will need blocks once their callees convert). If they are on the
same deletion path, excluding them shrinks the worklist further; if not, they
migrate with everything else. Decide before starting slice 1.

Note this only affects **call sites**: none of the 146 self-managing functions
live in a legacy blueprint, so the service-layer migration is unaffected either
way.

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

### Tighten `FakeUnitOfWork` too - yes

An earlier draft of this plan said aligning the fake was "a real cost, not a free
win", on the grounds that it breaks the ubiquitous
`uow = FakeUnitOfWork(); uow.users.add(...)` idiom. That objection does not
survive the test analysis above: **that idiom is exactly what step 2 changes
anyway.** Once those tests take an entered `uow` from a fixture, enforcing the
rule in the fake costs almost nothing extra.

It is also worth more than it first appears. 538 of the affected tests are
fake-backed, so without a strict fake the great majority of the suite cannot
catch a convention regression at all - only e2e could.

Mirror the real implementation: `__enter__` marks the context open, `__exit__`
marks it closed and swaps each repository for a placeholder that raises.

Keep the `fake_<name>` aliases as the deliberate seam for arranging or
inspecting state *outside* a block. They already exist on `FakeUnitOfWork` (set
up alongside the plain names in `__init__`) and are used exactly 3 times in the
whole suite, so repurposing them is free.

#### Roll it out incrementally

Tightening the fake in one commit turns every unmigrated test red at once. Add
an opt-in flag instead - `FakeUnitOfWork(strict=True)` - and have the new `uow`
fixture construct a strict one. Migrated modules use the fixture and are
enforced; unmigrated tests keep constructing a loose fake directly. The final
commit of step 3 flips the default and deletes the flag.

That also gives the migration a per-slice signal: a slice is done when its tests
pass against a strict fake.

## Step 4 - make the convention enforceable

Add a checker to the repo (e.g. `scripts/check_uow_convention.py`, wired into
`just check`) that fails if any function in `service_layer/` opens `with uow:`.
Cheap to write with `ast`: walk each `FunctionDef`, look for a `With` whose
`context_expr` is a `Name` called `uow`.

A companion check for "uses `uow` outside any `with uow:` block" is useful during
the migration but noisier - it cannot tell a bug from a call to a self-managing
callee. After step 2 that ambiguity disappears and the check becomes exact.

Watch for two scanner blind spots found the hard way: uses _before_ the first
`with` block in a function, and the `with uow:` header's own `Name` node
counting as a use.

### Write the convention down

The script enforces the rule; the docs explain it. Both are needed, or the next
person reads the failure and "fixes" it by adding the `with uow:` back.

- **`docs/architecture.md`** - the convention itself, and the note above on why
  it departs from _Architecture Patterns with Python_. This is the file the
  code-review skill's "Review `docs/architecture`" bullet resolves to, so
  putting it here gets it read.
- **`CLAUDE.md`** - a short entry under "Development Patterns" pointing at the
  above.

### Add a pre-merge review check

Add a bullet to "Things to Check" in `.claude/skills/sf-code-review/SKILL.md`, so
the convention is checked before merge as well as in `just check`.

The skill's own "Do NOT report" section excludes "anything CI already enforces",
so the review bullet must **not** restate the script. The script catches the
mechanical rule exactly; give the reviewer the judgement calls it cannot make:

- Does a `with uow:` block wrap `render_template`, or external I/O such as a
  gspread write or an SMTP send? That holds a transaction open across the slow
  part of the request.
- Should this path be read-only rather than transactional? (See the read-only
  workstream below.)
- Is a broad `except Exception` or `contextlib.suppress(Exception)` swallowing a
  database error inside a transaction, leaving it poisoned for the statements
  that follow?
- Is a new route composing many sequential reads that would be better as one
  caller-manages page-context function?

## Read-only workstream (separable, do after step 2)

Most of this codebase never writes. A read-only path needs no transaction at
all, and that removes the failure mode structurally rather than guarding
against it.

|                                   | Count     |
| --------------------------------- | --------- |
| GET-only routes (excl. `dev.py`)  | 87        |
| ...that never write, transitively | **64**    |
| ...that do write on a GET         | **23**    |
| Service-layer functions           | 394       |
| ...that write                     | 100 (25%) |

### Why it is worth doing

**It would have prevented the hang outright.** The leaked session held
`AccessShareLock` _because it sat in an open transaction_. On an AUTOCOMMIT
read-only connection each `SELECT` takes and releases its lock immediately, so
the teardown `DROP TABLE` would never have blocked. Three-quarters of the
service layer is read-only, so the surface is large.

It also makes the nesting bug moot on those paths: an inner block committing the
outer's partial work does not matter when there is nothing to commit.

### Shape

A `ReadOnlyUnitOfWork` exposing the same repositories over a connection with
`isolation_level="AUTOCOMMIT"` and PostgreSQL's `default_transaction_read_only`
set, so an accidental write fails at the database rather than silently
succeeding. Routes that only read resolve it instead of the read-write
UnitOfWork.

### Three caveats, all real

1. **23 GET routes currently write**, via `get_or_create_csv_config`,
   `get_or_create_selection_settings`, `check_and_update_task_health`,
   `find_or_create_oauth_user` and `link_oauth_to_user`. Non-idempotent GETs are
   a smell in their own right - lazily creating a settings row on a page view -
   and each needs excluding or refactoring before its route can go read-only.
   Full list is reproducible with the write-analysis scanner (appendix).
2. **It mitigates the hang, not the leak.** An abandoned read-only session still
   holds a pooled connection until the GC collects it; it just is not holding
   locks meanwhile. Step 3's guard is still wanted.
3. **It trades snapshot consistency for lock-freedom.** The engine currently
   runs `SERIALIZABLE`, so a page doing several reads sees one consistent
   snapshot. Under AUTOCOMMIT it would not - a page reading respondents and then
   counting them could see a torn view. Probably acceptable here, but it is a
   genuine semantic change and must be a deliberate choice, not a side effect.

### Sequencing

After step 2. Introducing a read-only variant while the 60/40 convention split
is still live means writing it against a moving target.

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

### Legacy `uow2` - no action

`AbstractUnitOfWork.commit_and_reset` exists specifically to replace "the older
pattern of opening `uow`/`uow2`/`uow3` in one request", and
`respondents_legacy.py` still opens a `uow2`.

Leave it. That blueprint is being deleted and has deliberately not been kept up
to date, so the `uow2` goes with it. Listed here only so nobody spends time
"fixing" it. See "Legacy blueprints" under step 2 for the scope decision.

### No app-context teardown for the UnitOfWork

`bootstrap.get_flask_uow()` hands out a UnitOfWork per call and nothing is
registered with `teardown_appcontext`. There is no backstop if a request leaves
a session open. Consider registering one as defence in depth, independent of the
convention work.

### `blueprints/dev.py` - resolved, now slice 10

In scope, with `with uow:` at the top level only. Moved into step 2 as slice 10.

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

### Which service functions write, and which GET routes write

Produces the read-only workstream figures. `writes()` is a heuristic - it looks
for write-shaped calls on a `uow`/repository - and the transitive closure then
marks any caller of a writer as a writer. Treat the output as a starting list to
confirm by hand, not as proof.

```python
import ast, pathlib, sys

WRITE_METHODS = {"add", "delete", "remove", "update", "save", "commit", "commit_and_reset", "flush"}
root = pathlib.Path(sys.argv[1])

def writes(func):
    for n in ast.walk(func):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in WRITE_METHODS:
            target = ast.unparse(n.func)
            if "uow" in target or "repository" in target or "repositories" in target:
                return True
    return False

service_funcs = {}
for path in root.rglob("*.py"):
    if "service_layer" not in str(path):
        continue
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            service_funcs[node.name] = node

writing = {n for n, f in service_funcs.items() if writes(f)}
for _ in range(5):  # propagate: calling a writer makes you a writer
    for name, f in service_funcs.items():
        if name in writing:
            continue
        if any(isinstance(n, ast.Call) and ast.unparse(n.func).split(".")[-1] in writing for n in ast.walk(f)):
            writing.add(name)

print(f"service-layer functions: {len(service_funcs)}, of which write: {len(writing)}")

for path in sorted((root / "entrypoints" / "blueprints").glob("*.py")):
    if path.name == "dev.py":
        continue
    for func in ast.walk(ast.parse(path.read_text())):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        methods = None
        for dec in func.decorator_list:
            if isinstance(dec, ast.Call) and ast.unparse(dec.func).endswith(".route"):
                methods = ("GET",)
                for kw in dec.keywords:
                    if kw.arg == "methods":
                        methods = tuple(ast.literal_eval(kw.value))
        if methods != ("GET",):
            continue
        callers = {
            ast.unparse(n.func).split(".")[-1]
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and ast.unparse(n.func).split(".")[-1] in writing
        }
        if callers:
            print(f"WRITES-ON-GET  {path.name:32} {func.name:40} via {', '.join(sorted(callers))}")
```
