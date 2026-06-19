# Plan: B2 — Inject UnitOfWork via bootstrap.py

> Status: **Reviewed with Doctor Chewie; ready to implement Phase 1.** No code
> has been written yet. The open questions have been resolved — see
> [§8 Decisions](#8-decisions-resolved-with-doctor-chewie). Phase 1 is the only
> phase to build now; Phases 2–3 and the Celery follow-on are documented for
> later.

## 1. Where this comes from

`docs/agent/history/faster-tests-research.md` lists eight approaches to speeding
up the test suite. Everything except **B2** has been implemented:

- A2 (patch backup-code hashing) — done
- A3 (session-scoped postgres + BDD-style cleanup) — done, took non-BDD tests
  from ~238s to ~71s
- A1, A4, A5, A7, B1 — done or partially done

B2 is described in the research doc as:

> Currently, Flask routes create `SqlAlchemyUnitOfWork` internally. By
> centralising UoW creation in `bootstrap.py`, routes can get UoW instances
> without knowing the concrete implementation. … In tests, these functions
> could be monkeypatched to return `FakeUnitOfWork`, letting e2e tests run
> without PostgreSQL.

So B2 has **two distinct parts** that the research doc bundles together:

1. **The refactor** — a clean, single seam for obtaining a UoW, replacing the
   251 direct `bootstrap.bootstrap()` calls scattered across the web layer.
2. **The payoff** — actually running (some) e2e tests against `FakeUnitOfWork`
   so they need no PostgreSQL, for a speed win.

These are separable. Part 1 is cheap, mostly mechanical, and improves the
architecture regardless. Part 2 is where the speed claim lives, and it is
substantially harder and riskier than the research doc implies (see §6).
**Decision: build Part 1 (Phase 1) now and document Part 2 for later** — see
§8.

## 2. Current state — how UoWs are obtained today

### 2.1 `bootstrap.py`

`bootstrap()` is **already** a UoW factory and already accepts an injected uow:

```python
def bootstrap(
    start_orm: bool = True,
    uow: AbstractUnitOfWork | None = None,
    session_factory: sessionmaker | None = None,
) -> AbstractUnitOfWork:
    session_factory = bootstrap_session_factory(start_orm, session_factory)
    if uow is None:
        uow = SqlAlchemyUnitOfWork(session_factory)
    return uow
```

`bootstrap_session_factory()` resolves `get_db_uri()` and caches one
`sessionmaker` per DB URI in a module-global `_session_factory_cache`.

### 2.2 Call sites

`bootstrap.bootstrap()` (or the bare `bootstrap()`) is called in **251 places
in `entrypoints/blueprints/`** plus:

- `entrypoints/decorators.py` — the `require_assembly_permission` decorator
  loads the assembly to check access.
- `entrypoints/extensions.py` — the flask-login `user_loader` (`load_user`)
  loads the current user on **every authenticated request**.
- `entrypoints/forms.py` — three WTForms validators hit the DB.
- `entrypoints/cli/*.py` — CLI commands (pass an explicit `session_factory`).
- `entrypoints/celery/tasks.py` — Celery tasks (pass an explicit
  `session_factory`, run **outside** any Flask app context).

**Two import styles are in use, and the difference matters for testability:**

```python
# Style A — module attribute access (monkeypatchable centrally)
from opendlp import bootstrap
uow = bootstrap.bootstrap()

# Style B — name bound at import time (NOT centrally monkeypatchable)
from opendlp.bootstrap import bootstrap
uow = bootstrap()          # decorators.py, forms.py
```

Style B means you cannot swap the implementation for all call sites by patching
one attribute — `decorators.py` and `forms.py` hold their own reference. This is
exactly the kind of fragility a single, app-resolved seam fixes.

### 2.3 Multi-UoW-per-request pattern

Many routes open **more than one** UoW context in a single request (`uow`,
`uow2`, `uow3`) — 8 blueprint files, ~69 references. Example from
`respondents.py::_run_csv_import`: one UoW imports the CSV, a second updates the
CSV config. With PostgreSQL both see the same committed data because they share
the database.

#### `commit_and_reset()` — collapsing intra-route multi-UoW (Doctor Chewie's idea)

We can add a method to `AbstractUnitOfWork` that commits mid-context and lets
work continue in the **same** UoW, so a route needs only one `with` block:

```python
# SqlAlchemyUnitOfWork
def commit_and_reset(self) -> None:
    """Commit so far, then keep using the same session for more work."""
    self.session.commit()
    # session stays usable: the factory uses expire_on_commit=False

# FakeUnitOfWork
def commit_and_reset(self) -> None:
    self.committed = True   # nothing to flush; just carry on
```

This works because `SqlAlchemyUnitOfWork.__exit__` only `close()`s the session
at the end, and the session factory is built with `expire_on_commit=False`, so a
session is fully usable after a `commit()`. The `respondents._run_csv_import`
example becomes:

```python
with get_flask_uow() as uow:
    import_respondents_from_csv(uow=uow, ...)
    uow.commit_and_reset()          # CSV import is now durable
    update_csv_config(uow=uow, ...) # second unit of work, same session
```

**This is a genuine architecture win** (a single, clear UoW per route, matching
the DDD intent) and it shrinks the surface Phase 2 must reason about. But two
caveats:

1. It is **not a purely mechanical** change — each multi-UoW route must be read
   to confirm the commit points and any deliberate error-isolation between the
   two units of work is preserved. So it is route-by-route work, applied to the
   multi-UoW files (legacy included) during/after the mechanical migration.
2. It does **not remove** the need for a shared in-memory store in Phase 2.
   Even with one UoW per route, a single request still creates *separate* UoW
   instances in `load_user`, the permission decorator, and form validators; and
   fixtures seed data in one request that later requests must see. Cross-request
   persistence and cross-helper visibility still require a shared `FakeStore`
   (§5.2).

**Recommendation:** adopt `commit_and_reset()` as the target pattern and apply
it to the multi-UoW routes (legacy included) as part of Phase 1 (it is exactly
the kind of architecture gain you value). The shared-store work in Phase 2 stands
regardless.

### 2.4 How e2e tests inject the database today

There is **no monkeypatching of `bootstrap`** today. Instead
(`tests/e2e/conftest.py`):

1. The `app` fixture sets `DB_URI=worker_db_url` via env var, then calls
   `create_app("testing_postgres")`.
2. Blueprints call `bootstrap.bootstrap()`, which reads `get_db_uri()` →
   the same `worker_db_url` → the same cached `sessionmaker`.
3. Fixtures (`admin_user`, `existing_assembly`, …) build data through
   `SqlAlchemyUnitOfWork(postgres_session_factory)` bound to that same URL.

So today the test app and the test fixtures share state purely through "they
point at the same PostgreSQL database". There is currently **no seam** for
substituting an in-memory implementation into a running app.

**Decision (Doctor Chewie):** add the seam to `create_app()` itself. The factory
is passed in at app-construction time and stashed on the app, and routes read it
back from the current app:

```python
def create_app(config_name: str = "", uow_factory: UowFactory | None = None) -> Flask:
    ...
    app.extensions["uow_factory"] = uow_factory or bootstrap.default_uow_factory
    ...
```

Production calls `create_app(config_name)` and gets the default
`SqlAlchemyUnitOfWork` factory. Tests call
`create_app("testing", uow_factory=lambda: FakeUnitOfWork(store=shared))`. This
is the single seam — no monkeypatching, and it covers every web call site
regardless of import style (see §4.1).

### 2.5 `FakeUnitOfWork` today (`tests/fakes.py`)

- `__init__` builds **fresh, empty** repositories every time it is constructed.
  Two `FakeUnitOfWork()` instances share nothing.
- `commit()` just sets `self.committed = True`.
- `rollback()` **clears every repository's `_items`** — i.e. rollback wipes the
  whole store, not just uncommitted changes. This is fine for today's unit
  tests (one UoW, discarded after the test) but is **actively wrong** for a
  shared, persistent store (§6.2).
- It is comprehensive: implements all 17 repositories and is already used
  heavily in `tests/unit/`.

## 3. Goal

**Phase 1 (do now):** Introduce one clean seam for obtaining a UoW in the web
layer, resolved from the Flask app so it can be swapped without monkeypatching.
Migrate **all** web-layer call sites to it — including the legacy blueprints, so
no copy of the old pattern survives — and adopt `commit_and_reset()` for
multi-UoW routes. Leave CLI and Celery on the existing explicit-`session_factory`
pattern for now. No behaviour change in production; little or no speed change yet
— the value of Phase 1 is architectural.

> **Celery (follow-on, documented not done):** Celery tasks run in a separate
> worker process and can only use a real DB session, so they can never use
> `FakeUnitOfWork`. But converting them to accept an injected `uow_factory`
> (instead of threading `session_factory` through every helper) is a worthwhile
> consistency/architecture improvement. It is carved out as its own phase to
> keep Phase 1 bounded — see §7. The CLI is already adequately covered by the
> explicit-`session_factory` pattern and has little code, so it stays as-is.

**Phase 2 (documented now, build later):** Build a shared-store `FakeUnitOfWork`,
wire a fake-backed app + fixture path, convert a pilot subset of e2e tests, and
**measure** the speed-up. See §5.

## 4. Phase 1 design — the seam

### 4.1 Where the factory lives

Resolve the UoW factory from the **Flask app**, not a module global. This gives
a single seam that works for *all* web call sites regardless of import style,
and isolates tests from each other (no global mutation to reset).

Add to `bootstrap.py`:

```python
from collections.abc import Callable

UowFactory = Callable[[], unit_of_work.AbstractUnitOfWork]


def default_uow_factory() -> unit_of_work.AbstractUnitOfWork:
    """Production factory: a SqlAlchemyUnitOfWork over the cached session factory."""
    return unit_of_work.SqlAlchemyUnitOfWork(bootstrap_session_factory())


def get_flask_uow() -> unit_of_work.AbstractUnitOfWork:
    """Return a UoW for the current request, using the app-configured factory.

    Must be called within a Flask application context. CLI and Celery code
    must keep using ``bootstrap()`` with an explicit session_factory.
    """
    from flask import current_app  # local import to keep bootstrap importable without Flask
    factory: UowFactory = current_app.extensions.get("uow_factory", default_uow_factory)
    return factory()


def get_flask_uow_factory() -> UowFactory:
    """Return the app-configured UoW factory itself.

    For routes that pass a factory down into a service, or (pre-
    ``commit_and_reset``) open multiple UoW contexts.
    """
    from flask import current_app
    return current_app.extensions.get("uow_factory", default_uow_factory)
```

The names are `get_flask_uow()` / `get_flask_uow_factory()` (Doctor Chewie's
choice) to make it obvious these resolve from the Flask app and must not be used
from CLI/Celery code.

Register the factory during app creation by giving `create_app()` an optional
parameter (§2.4 decision):

```python
def create_app(config_name: str = "", uow_factory: UowFactory | None = None) -> Flask:
    ...
    app.extensions["uow_factory"] = uow_factory or bootstrap.default_uow_factory
```

Production omits the argument and gets `default_uow_factory`. Tests pass a fake
factory in at construction time (see §5 / Phase 2).

> **Seam mechanism (decided):** resolve from `current_app.extensions` rather
> than monkeypatching module functions (the research doc's wording). The
> app-extension approach covers every web call site regardless of import style —
> including the Style-B imports in `decorators.py`/`forms.py` that a monkeypatch
> would miss — and avoids global mutation that tests would have to reset.

### 4.2 Call-site migration

Single-UoW routes (mechanical):

```python
# before
uow = bootstrap.bootstrap()
with uow:
    ...

# after
with get_flask_uow() as uow:
    ...
```

Multi-UoW routes collapse to one context via `commit_and_reset()` (§2.3) —
read each route to confirm the commit points:

```python
with get_flask_uow() as uow:
    import_respondents_from_csv(uow=uow, ...)
    uow.commit_and_reset()
    update_csv_config(uow=uow, ...)
```

Files to migrate in Phase 1 (`entrypoints/`):

| Area | Files / count |
| --- | --- |
| Blueprints (all 18, incl. the 4 `*_legacy`) | 251 calls |
| Decorators | `decorators.py` (1) |
| Extensions | `extensions.py` `load_user` (1) |
| Forms | `forms.py` (3) |

That is **~256 call sites**. The four `*_legacy` blueprints (`gsheets_legacy`,
`db_selection_legacy`, `targets_legacy`, `respondents_legacy`, ~69 calls) are
**included** — converting them too means no working copy of the old
`bootstrap.bootstrap()` pattern is left for anyone to reuse (D6). They will be
deleted eventually, so the extra churn is small and one-directional.

CLI (`cli/*.py`) **stays as-is** — already adequately covered by the explicit-
`session_factory` pattern, and small. Celery (`celery/tasks.py`) also stays on
`session_factory` in Phase 1, but is converted to an injected `uow_factory` in a
dedicated follow-on phase (§7) — its worker session can only ever be a real DB
session, so this is an architecture/consistency change, not a fakes enabler.

### 4.3 Why this is safe in production

`get_flask_uow()` with no configured factory falls back to
`default_uow_factory`, which is exactly today's behaviour (`SqlAlchemyUnitOfWork`
over the cached factory). `create_app` registers the default explicitly, making
the wiring visible. No runtime behaviour change.

### 4.4 Phase 1 verification

- `just test` and `just check` stay green (existing e2e suite still runs against
  PostgreSQL, now through the seam with the default factory).
- A new unit test asserting `get_flask_uow()` returns the app-configured
  factory's product and falls back to `default_uow_factory` when none is set.
- A unit/integration test for `commit_and_reset()` on both
  `SqlAlchemyUnitOfWork` (data durable after the call, session still usable) and
  `FakeUnitOfWork`.
- Grep guard: no remaining `bootstrap.bootstrap()` / bare `bootstrap()` anywhere
  in the web layer (`entrypoints/blueprints` — including `*_legacy.py` —
  `decorators.py`, `extensions.py`, `forms.py`).

Phase 1 delivers little or no speed improvement on its own. Its value is
architectural, and it is the prerequisite for Phase 2.

## 5. Phase 2 design — fake-backed e2e tests (the speed payoff)

### 5.1 The shape

With the seam in place, an e2e test can build an app whose `uow_factory`
returns a `FakeUnitOfWork` sharing a single in-memory store, seed data through
that same store, drive the Flask test client, and assert — all without
PostgreSQL.

```python
@pytest.fixture
def fake_store():
    return FakeStore()            # shared repositories (see 5.2)

@pytest.fixture
def fake_app(temp_env_vars, fake_store, test_redis_client):
    # NB: not testing_postgres — the factory is injected at construction time
    return create_app("testing", uow_factory=lambda: FakeUnitOfWork(store=fake_store))
```

### 5.2 Required change: a shared-store `FakeUnitOfWork`

Today every `FakeUnitOfWork()` is empty and independent. For e2e we need
**every** `get_flask_uow()` in a request — `load_user`, the permission
decorator, form validators, and the route's own UoW — to see the same data, and
that data to persist **across requests** within a test. (Even after
`commit_and_reset()` collapses the route's own multiple contexts into one,
`load_user`/decorator/validators are still separate instances, so the shared
store is still required.)

Plan: extract the 17 repositories into a `FakeStore` object constructed once per
test and shared by every `FakeUnitOfWork` instance:

```python
class FakeStore:
    def __init__(self):
        self.users = FakeUserRepository()
        self.assemblies = FakeAssemblyRepository()
        ...   # all 17

class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self, store: FakeStore | None = None):
        self._store = store or FakeStore()
        self.users = self._store.users
        ...   # bind all 17 from the store
```

This keeps the existing zero-arg `FakeUnitOfWork()` behaviour (fresh private
store) for current unit tests, and adds `FakeUnitOfWork(store=shared)` for e2e.

### 5.3 Required change: rollback semantics

The current `rollback()` **clears the entire store**. In a shared, persistent
store that is catastrophic: any request that raises (or any UoW exited via an
exception path) would wipe all seeded data. Options, in rough order of effort:

- **(a) No-op rollback for the shared store.** Simplest. Accept that the fake
  does not model transactional rollback — uncommitted partial writes survive.
  This diverges from PostgreSQL semantics and could hide or introduce bugs, but
  most e2e assertions are about end state, not rollback.
- **(b) Copy-on-enter snapshot.** `__enter__` snapshots each repo's `_items`;
  `rollback()` restores the snapshot. Models real rollback better; costs a
  shallow copy per UoW per request. Moderate effort.
- **(c) Leave rollback wiping, but only for private stores.** I.e. shared-store
  UoWs use (a) or (b); private-store UoWs keep today's wipe. Avoids touching
  existing unit-test behaviour.

**Decided (D5):** **(b) restricted to shared stores** (i.e. (c)+(b)) —
correct-ish semantics where it matters, no change to existing unit tests.

### 5.4 Parallel fixture path

The e2e fixtures (`admin_user`, `regular_user`, `existing_assembly`,
`assembly_with_gsheet`, login helpers, plus whatever lives in the wider
`tests/conftest.py`) all build data through `SqlAlchemyUnitOfWork`. A
fake-backed run needs equivalents that build through the shared `FakeStore`.
The service functions themselves (`create_user`, `create_assembly`, …) are
UoW-agnostic, so the fixtures can call them with a `FakeUnitOfWork(store=...)`.
This is duplicated fixture wiring, not duplicated logic.

### 5.5 What cannot go fake

- **Anything touching Celery** (selection runs, gsheet load, db-select). Tasks
  execute in a worker with their own `session_factory`; they will not see the
  fake store. These e2e tests must stay on PostgreSQL.
- **Tests asserting real DB constraints / cascades / JSON operators** — the
  fake does not enforce FKs or unique constraints. Moving these to fakes would
  be false confidence (the same argument the research doc used to justify
  dropping SQLite in B1).
- **Anything relying on `expire_all()` cross-process visibility** (run-record
  polling) — meaningless against an in-memory store.

So Phase 2 is necessarily a **subset** of e2e tests, chosen for being pure
request → service → assertion flows (auth pages, profile, admin user/invite
management, assembly CRUD, target editing). A pilot should quantify how many
tests qualify and how much time they currently take.

> **Celery, for follow-on work:** because tasks run in a separate worker with a
> real DB session, e2e tests that dispatch and wait on a Celery task (selection
> runs, gsheet load, db-select) can never be backed by the fake store and must
> stay on PostgreSQL. The Celery `uow_factory` conversion in §7 is purely an
> architecture/consistency change there — it does **not** make these tests
> fake-able.

### 5.6 Pilot before rollout

1. Convert **one** e2e file (candidate: `test_admin_user_management.py` or
   `test_assembly_crud.py`) to the fake-backed fixtures.
2. Measure: fake-backed runtime vs current PostgreSQL runtime for that file.
3. Validate the tests still genuinely exercise the same code paths (login,
   permission decorator, route, service) and catch a deliberately-introduced
   regression.
4. Only then decide whether to convert more.

## 6. Honest assessment & risks

- **Phase 1 is low-risk and worth doing for the architecture alone.** Doctor
  Chewie values the clean UoW seam even if it yields little or no speed gain. It
  touches **~256 call sites** (the legacy blueprints are included, so no copy of
  the old pattern survives — D6); most are a mechanical swap, and only the
  multi-UoW routes need per-route thought for `commit_and_reset()`.
- **Phase 2's speed win is unproven.** A3 already removed per-test
  `create_all`/`drop_all`; the remaining e2e cost is PostgreSQL round-trips on
  small datasets plus login flows (hashing already patched). Fakes remove the
  round-trips but the login/permission/render work remains, so the pilot must
  measure before broad rollout.
- **Speed still matters even though A6 exists.** pytest-xdist (A6) can't run the
  BDD tests as currently written, so a full run including BDD can still take
  ~10 minutes. Fake-backed e2e tests cut wall-clock for the non-BDD path and are
  complementary to A6, not a substitute. Either way, the architecture gain is
  the floor and any speed gain is upside.
- **Divergence risk:** fake-backed e2e tests can pass while PostgreSQL would
  fail (FK/constraint/transaction differences) — the same false-confidence
  concern B1 raised about SQLite. Mitigation: keep all constraint/cascade and
  Celery tests on PostgreSQL; treat fake-backed tests as "fast smoke" not
  "integration".
- **Maintenance:** two app/fixture wiring paths and a more complex
  `FakeUnitOfWork`.

## 7. Phasing

**Phase 1 — web-layer seam (do now).**
- Add `UowFactory`, `default_uow_factory`, `get_flask_uow`,
  `get_flask_uow_factory` to `bootstrap.py`.
- Add the `uow_factory` parameter to `create_app()` and register the default.
- Add `commit_and_reset()` to `AbstractUnitOfWork` /
  `SqlAlchemyUnitOfWork` / `FakeUnitOfWork`.
- Migrate **all ~256** web call sites (including the four `*_legacy`
  blueprints, so no copy of the old pattern remains — D6); collapse multi-UoW
  routes onto `commit_and_reset()`.
- Keep everything green; self-contained PR.

**Phase 2 — fake-backed e2e pilot (the speed payoff; build later).** Shared-store
`FakeUnitOfWork` (`FakeStore`, §5.2) + rollback semantics (option (b) for shared
stores, §5.3) + fake-backed `create_app(uow_factory=...)` fixture path + convert
one pilot e2e file; **measure**. Then decide whether to convert more.

**Phase 3 — `patch`/`MagicMock` audit (Doctor Chewie's idea).** Once fakes are
the established seam, review existing uses of `unittest.mock.patch` and
`MagicMock` across the test suite to see which can be replaced with the real
service code driven by fakes — generally higher-fidelity and less brittle.

**Follow-on (any time after Phase 1) — Celery `uow_factory`.** Convert
`celery/tasks.py` (and its helpers) from threading `session_factory` everywhere
to an injected `uow_factory`. DB-only — no fakes possible in the worker. An
architecture/consistency win, carved out so it doesn't enlarge Phase 1.

**Later / undecided.** Broad e2e conversion beyond the pilot is deferred until
the pilot numbers are in. (The legacy blueprints themselves will still be
deleted on their own retirement schedule — Phase 1 just moves them onto the new
seam in the meantime.)

## 8. Decisions (resolved with Doctor Chewie)

- **D1 — Scope.** Do **Phase 1 now** (the web-layer seam), with Phases 2–3 and
  the Celery follow-on documented here but built later.
- **D2 — Speed vs architecture.** Both matter. Speed is still a real goal —
  full runs including BDD can take ~10 minutes and BDD can't use xdist — but the
  clean UoW architecture is valued in its own right and is worth doing even if
  the speed gain turns out mild or nil.
- **D3 — Seam mechanism.** App-extension lookup via
  `current_app.extensions["uow_factory"]`, seeded by a `create_app(uow_factory=)`
  parameter. No monkeypatching.
- **D4 — Naming.** `get_flask_uow()` / `get_flask_uow_factory()`.
- **D5 — Fake rollback semantics.** Snapshot/restore restricted to shared stores
  (option (b)+(c)); existing private-store unit-test behaviour unchanged.
- **D6 — Legacy blueprints.** **Convert them too**, in Phase 1. Leaving them on
  the old `bootstrap.bootstrap()` pattern would leave a working example for
  someone to copy; migrating everything means there is no old pattern left to
  reuse. (They will still be deleted eventually, but the small extra churn now
  is worth the consistency.)
- **D7 — Celery.** Convert to an injected `uow_factory` as a follow-on phase
  (DB-only; no fakes in the worker). CLI stays as-is.
- **D8 — `commit_and_reset()`.** Adopt it (§2.3) and apply to all multi-UoW
  routes (legacy included) during Phase 1.

### Remaining things to confirm during implementation (not blocking)

- Exact set of multi-UoW routes that need per-route review for
  `commit_and_reset()` commit points (start from the 8 files in §2.3, legacy
  included).
- Which single e2e file to use for the Phase 2 pilot (`test_assembly_crud.py` or
  `test_admin_user_management.py`).
