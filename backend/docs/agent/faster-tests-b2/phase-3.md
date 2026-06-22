# Phase 3 — `patch`/`MagicMock` audit + test-organisation ideas

> Status: **Audit only.** No code changed. This document inventories where the
> test suite mocks/patches around the Flask app, groups those tests by the
> strategy that fits them, and collects ideas for the long-term organisation of
> the Flask tests. Decisions are for Doctor Chewie; nothing here is implemented.

## 1. Purpose & method

Phase 2 proved that a Flask test can run against an in-memory `FakeUnitOfWork`
(shared `FakeStore`) instead of PostgreSQL, by injecting a `uow_factory` into
`create_app()` (see `tests/e2e/fake_pilot/`). Phase 3 asks: **which existing
tests that drive the Flask app do so by patching/mocking, and which of those
mocks are really standing in for the database / internal collaborators** — i.e.
could be replaced by the fake seam (higher fidelity, less brittle) rather than a
hand-rolled mock.

Method: grepped the whole suite for `patch`/`MagicMock`/`Mock`/`monkeypatch`
(~45 files), then read each one and recorded, per file: does it use the Flask
app; what it patches (exact dotted targets); whether each mock is an *external
boundary* or an *internal collaborator*; and whether it could move onto the fake
seam.

## 2. Classification of mocks

Every mock in the suite falls into one of four buckets. The bucket decides the
strategy.

| Bucket | What it is | Strategy |
| --- | --- | --- |
| **EXTERNAL-BOUNDARY** | Celery dispatch (`.delay`/`.apply_async`/`AsyncResult`/`control.revoke`), SMTP, OAuth providers, Google Sheets + the `sortition-algorithms` lib, PIL/Pillow, git subprocess, filesystem, Redis, the SQLAlchemy engine, slow crypto (password hashing), gettext/i18n | **Keep mocked.** These are the real seams of the system. Mocking them is correct. |
| **INTERNAL-COLLABORATOR** | `bootstrap.get_flask_uow`, a `MagicMock()` UoW, a repository, or an internal **service function** patched out (`submit_registration`, `add_registration_image`, `start_gsheet_load_task`, …) | **Candidate for the fake seam** — replace the mock with the real code driven by a `FakeUnitOfWork`. (Caveats in §4.) |
| **CONFIG / FEATURE-FLAG** | `monkeypatch.setenv("FF_…")` + `reload_flags()`, `patch("…config.get_…")`, `patch.dict(os.environ, …)` | **Mostly fine.** A cleaner config seam is a possible nice-to-have (§6), but these are not the target of Phase 3. |
| **OTHER** | clock control (`time.monotonic`), `MagicMock` domain-object stand-ins, i18n `_` patches, interaction-only spies | Case by case; mostly leave alone. |

**The single recurring internal seam** is
`opendlp.entrypoints.blueprints.<bp>.bootstrap.get_flask_uow` — patched in the
route-style tests. That is *exactly* what the `fake_pilot` `app` fixture
overrides via `create_app("testing", uow_factory=…)`. So wherever a test patches
that target, the fake seam can take its place without a per-test patch at all.

## 3. Findings by group

Tests sort into seven groups. Groups B and C are where the conversion value is.

### Group A — Already the target state (no action; hold up as the model)

Service-layer tests that already use the **real** `FakeUnitOfWork` (and inject
spies for boundaries) — no internal mocking. This is what converted route tests
should look like.

- `tests/unit/test_registration_image_service.py` — `FakeUnitOfWork()` + real
  domain + real `process_image`; **zero** internal mocks. The reference pattern.
- `tests/unit/test_monitoring_service.py` — `FakeUnitOfWork` + dependency-injected
  spy functions; mocks only the Celery boundary, and only as *negative* guards.
- `tests/unit/test_email_confirmation_service.py`,
  `tests/integration/test_email_confirmation_integration.py` — Fake seam; only
  the email adapter mocked.
- `tests/unit/test_password_reset_service.py`,
  `tests/integration/test_password_reset_flow.py` — Fake seam; only
  `hash_password` / `validate_password_strength` isolated.
- `tests/unit/test_sortition_service.py`, `tests/unit/test_db_selection.py` —
  Fake seam; remaining mocks are the Celery and `sortition-algorithms` boundary.
- `tests/unit/test_sortition_progress.py` — monkeypatches `sp.bootstrap` *to
  inject* `FakeUnitOfWork` (the non-Flask equivalent of the seam) + clock.

### Group B — Disguised Flask route tests that mock the UoW (prime candidates)

These live in `tests/unit/` but **spin up `create_app("testing")` + a test
client / request context** and then patch `bootstrap.get_flask_uow` *plus* the
service layer. They are really route tests wearing a unit-test coat. The fake
seam removes the `get_flask_uow` patch entirely; the open question per file is
whether to also stop stubbing the services (§4).

| File | Tests | What it mocks | Verdict |
| --- | --- | --- | --- |
| `tests/unit/test_registration_routes.py` | ~21 | `bootstrap` + entire registration service layer (`find_*`, `resolve_visibility`, `render_*`, `submit_registration`); feature-flag env | **Strong candidate** for happy paths; error paths inject `side_effect` |
| `tests/unit/test_backoffice_registration_view.py` | ~13 | `bootstrap.get_flask_uow` + `current_user` + service fns to drive route branching | **Candidate**; some tests force failures via `side_effect` |
| `tests/unit/test_backoffice_registration_images.py` | ~20 | `bootstrap.get_flask_uow` + `current_user` + image service fns (upload/patch/delete happy paths) | **Candidate** for the happy-path classes; login-redirect & template-scan classes need no UoW |
| `tests/unit/test_dev_image_handlers.py` | ~9 | handlers take `uow` directly as `MagicMock()`; also `bootstrap.get_flask_uow` returning a `MagicMock` repo | **Candidate** — swap `MagicMock()` for `FakeUnitOfWork(store=…)` is very natural |
| `tests/unit/test_backoffice_registration_actions.py` | ~7 | `get_flask_uow` + *every* page service fn; asserts which service is called + flash text | **Weak** — pure dispatch test; only worth converting if re-pointed at real outcomes |

### Group C — True e2e (on Postgres) that are pure request→service→assertion

In `tests/e2e/`, already full-stack HTTP, and they mock **nothing internal** —
only config/feature-flags. These are the same shape as the Phase 2 pilot and
would convert to fake-backed cleanly (the pilot already did this for
`test_assembly_crud.py`).

- `tests/e2e/test_registration_public.py` (~16) — only `FF_REGISTRATION_PAGE`
  env. Routes → `registration_page_service` → UoW. **Good candidate.**
- `tests/e2e/test_registration_image_serve.py` (~7) — only feature-flag env;
  real PIL (legit). Images persist through the UoW. **Good candidate.**
- `tests/e2e/test_backoffice_respondents.py` (~45) — only a CSV-size config
  override in one test. CSV upload → `respondent_service` → UoW. **Good
  candidate** (modulo any Celery-backed import paths — check before converting).

### Group D — e2e dominated by the Celery boundary (PARTIAL at best)

Full-stack HTTP, real UoW data path, but the routes exist to *dispatch Celery
tasks and poll their status*. Even on a fake UoW the `.delay` / `.apply_async` /
`control.revoke` / status-poll tail must stay mocked. The data side could move
to the fake store, but the headline reason these tests are slow/awkward is the
Celery boundary, not the DB.

- `tests/e2e/test_gsheets_routes.py` (~44), `test_backoffice_gsheet_selection.py`
  (~56), `test_db_selection_backoffice.py` (~42), `test_db_selection_routes.py`
  (~55), `test_sortition_routes.py` (~70).

Note: several of these patch the **internal service function**
(`start_gsheet_load_task`, `check_db_selection_data`, `generate_selection_csvs`,
…) rather than the Celery boundary underneath it. Where the only thing that must
be faked is the Celery dispatch, the cleaner target is the `.delay` boundary, so
the route + service run for real over a fake UoW (see §6 "Centralise the Celery
boundary mock").

### Group E — Infra / boundary endpoint tests (low or no conversion value)

Full-stack HTTP, but the test *is about* an external boundary; its mocks are
legitimately external and there is no meaningful UoW data dimension.

- `tests/e2e/test_health_check.py` (~18) — **NO.** Mocks `check_database` /
  `check_celery_worker`; that is the whole point.
- `tests/e2e/test_health_check_monitoring.py` (~10) — **PARTIAL/low value.**
- `tests/e2e/test_feature_flags_e2e.py` (~3) — convertible but gains nothing;
  mocks are infra probes.
- `tests/e2e/test_oauth_flow.py` (~28) — **PARTIAL.** OAuth provider mocks stay
  (external); user/invite persistence could ride the fake store, but the app
  fixture is OAuth-custom and would need a fake-seam variant.

### Group F — Out of Flask context (CLI + Celery worker) — out of seam scope

These run **outside** any Flask app context and use an explicit
`session_factory`, so `get_flask_uow` does not apply to them at all.

- CLI: `tests/integration/test_cli_integration.py`,
  `tests/integration/test_cli_monitor.py`.
- Celery: `tests/unit/test_celery_tasks_progress.py`,
  `tests/unit/test_celery_app_signals.py`,
  `tests/integration/test_celery_tasks.py`,
  `tests/integration/test_sortition_db_task.py`,
  `tests/unit/test_bootstrap_session_factory.py`.

A few of these patch an *internal* service fn (`run_monitoring_selection` in the
CLI/Celery tests, the `_internal_*` task helpers) — those could in principle call
the real service over a plain `FakeUnitOfWork` instead of patching it, a small
separate cleanup. But they are **not** Flask-seam candidates and stay on the
explicit-`session_factory` pattern (this matches the Celery `uow_factory`
follow-on carved out in `plan.md` §7).

### Group G — Pure unit / adapter / config / i18n (no UoW; correct as-is)

No Flask app data path; the only mocks are external boundaries or config. Leave
alone.

- `tests/unit/test_email_adapters.py` (SMTP), `test_csv_gsheet_adapter.py`
  (GSheet/CSV adapter), `test_image_processing.py` (Pillow),
  `test_context_processors.py` (config/git subprocess),
  `test_unit_of_work.py` (the UoW's own test — mocks the SQLAlchemy session,
  correctly), `test_email_bootstrap.py` (env-driven adapter selection),
  `test_error_translation.py` / `test_report_translation.py` (i18n),
  `test_feature_flags.py`, `test_feature_flag_context.py`,
  `test_dashboard_feature_flags.py`, `test_locale_selection.py`.
- `tests/conftest.py` mocks: logging-to-DB suppression, fast password hashing,
  feature-flag env — all autouse, all legitimate boundary/config.

### Group tally

| Group | Strategy | Files |
| --- | --- | --- |
| A — already fake-backed | nothing; the model | ~9 |
| B — disguised route tests mocking the UoW | convert to fake seam | 5 |
| C — pure e2e, only config mocks | run fake-backed (like the pilot) | 3 |
| D — Celery-dominated e2e | keep on PG, or fake + mock only the Celery tail | 5 |
| E — infra/boundary endpoints | mostly leave (mocks are external) | 4 |
| F — CLI/Celery, out of Flask context | out of seam scope | 7 |
| G — pure unit/adapter/config | leave (mocks are external) | ~12 |

## 4. The real blocker isn't the UoW mock — it's interaction-style testing

Removing the `get_flask_uow` patch is the easy part (the seam does it). The
friction in Group B/C conversions is that many of these tests are
**interaction-based**, not **state-based**:

- They mock the service functions and then assert *"service X was called with
  kwargs Y"* or *"the route flashed message Z"*. That re-asserts the
  implementation and is brittle. Converting to fakes means **rewriting them to
  assert on real outcomes** — what ends up in the `FakeStore`, what the rendered
  response contains — which is the higher-fidelity test we want, but it is a
  genuine rewrite, not a mechanical swap.
- **Error-path tests** inject `side_effect=ValueError/RuntimeError` to force a
  service to fail. With real services over a fake store you need the *data* to
  naturally trigger the error, or you keep a targeted stub for just that branch.
  So expect "happy paths → fake seam; a few error paths keep a narrow stub".

This is the right tradeoff to flag to Doctor Chewie: the conversion is worth it
**for the fidelity gain** (real services exercised, fewer brittle call-arg
assertions), not primarily for speed. Speed is a side benefit.

## 5. Ideas for long-term test organisation

Doctor Chewie raised three questions: (a) pytest marks à la
`pytest.mark.django_db`; (b) should `tests/e2e/` hold only "true" e2e; (c) what
to call "Flask → fake repo" tests. Here are options and a recommendation.

### 5.1 Two orthogonal axes

It helps to separate **what layers a test exercises** (directory) from **what
infrastructure it needs** (marker). They are independent: a fake-backed route
test exercises the full Flask stack but needs *no* DB.

### 5.2 Directory taxonomy (the "what layers" axis)

Today the dirs mean:

- `tests/unit/` — *supposed* to be no-I/O logic over fakes, **but** it currently
  also holds the Group B disguised route tests (real Flask app + mocked UoW).
- `tests/integration/` — service/CLI/Celery over **real Postgres**, no Flask HTTP.
- `tests/e2e/` — Flask HTTP over **real Postgres** (and real Redis).
- `tests/contract/` — repository contract tests
- `tests/bdd/` — behave.

The new tier — **Flask HTTP over a fake repository, no DB** — does not fit any of
these. It is *not* "unit" (it runs the real app, blueprints, decorators,
templates, login) and *not* "e2e" (no DB round trip). Naming options:

| Name | Pros | Cons |
| --- | --- | --- |
| **`tests/component/`** *(recommended)* | Standard term (Fowler) for "full stack minus external deps"; unambiguous vs unit/e2e | New word to learn |
| `tests/web/` or `tests/routes/` | Concrete, says "Flask routes" | Sounds like it could include e2e too |
| keep in `tests/unit/`, distinguish by marker | no move | perpetuates the "disguised route test in unit/" confusion the audit found |
| call them "unit tests" | no new concept | wrong — they're multi-layer with real Flask; muddies what "unit" means |

**Recommendation:** introduce **`tests/component/`** for Flask-over-fake tests,
move the Group B disguised route tests there as they're converted, and **reserve
`tests/e2e/` for genuine Flask→Postgres→back round trips** (the answer to (b) is
*yes*). Don't call them "unit" tests. **Decided — see §8 D1.** Note that "reserve
e2e for real DB" does not mean stripping e2e bare: each route keeps one PG
happy-path smoke there (§8 D2).

### 5.3 Marker taxonomy (the "what infra" axis)

Add declarative markers for external dependencies and **register them** in
`pyproject.toml` with `--strict-markers` (today there are *no* registered
markers and no `addopts`, so typos would pass silently):

```toml
[tool.pytest.ini_options]
addopts = "--strict-markers"
markers = [
    "requires_db: needs a real PostgreSQL database",
    "requires_redis: needs a real Redis server",
    "requires_celery: needs a Celery worker / broker",
]
```

Difference from `pytest-django`'s `django_db`: there the mark is an *enabler*
(grants DB access, wraps the test in a transaction). Here the marks are
*declarations of need*, which buys two things:

1. **Selection** — `pytest -m "not requires_db"` runs the DB-free fast tier
   (unit + component) for a tight local loop; CI runs the full set.
2. **Auto-skip-if-unavailable** (optional, later) — a `conftest` hook can probe
   each resource once per session and `skip` marked tests when it's down, so a
   developer with no Postgres can still run everything that doesn't need it. The
   Phase 2 detour (a portless Postgres container silently erroring 25 tests)
   is exactly what this would have turned into a clean skip.

Start with registration + selection now; add the auto-skip hook if it earns its
keep.

> **Caveat that matters for the "fast tier" pitch:** fake-backed ≠
> dependency-free. The `fake_pilot` conftest **still needs Redis**
> (`test_redis_client`) for sessions and login rate-limiting. So a converted
> Group B/C test would be `requires_redis` but **not** `requires_db`. To make
> the fast tier *truly* serviceless we'd need a second seam for the session
> backend (a null/filesystem session in `create_app`), mirroring the UoW seam —
> see §6.

#### A "never fake this" marker for DB-fidelity tests

There is a distinct concept the three `requires_*` marks don't capture. Those
declare what infrastructure a test *needs to run*. Separately, some tests exist
**specifically to exercise real database semantics** — FK cascades, unique
constraints, JSON column operators, serialization round-trips (`plan.md` §5.5
"What cannot go fake"). The contract tests (`tests/contract/`) already pin
fake-vs-SQL parity per repository method, but it is genuinely valuable to also
exercise the most important of these end-to-end through the HTTP stack, where a
real cascade or constraint violation surfaces as the user would hit it.

Such a test must **never** be converted to the fake backend — the fake enforces
no constraints, so faking it would be silent false confidence. That is a
*positive intent* declaration ("the real DB *is* the point here"), different from
`requires_db` ("this happens to need a DB to run"). Options:

| Option | Pros | Cons |
| --- | --- | --- |
| **A dedicated marker, e.g. `@pytest.mark.db_semantics`** *(recommended)* | Greppable; machine-checkable; can back the §6.6 guard so a lint *forbids* faking a marked test; shows intent in selection (`-m db_semantics`) | One more registered marker |
| A docstring / module-level note | Zero infra | Not machine-checkable; easy to miss; can't be enforced |
| Rely on directory (keep them in `tests/integration/` only) | No new concept | Loses the "exercise it through the full HTTP stack in e2e" value the comment wants |

**Recommendation:** add `db_semantics` (implying `requires_db`) as the marker for
"this test's value is the real database — never move it to fakes". It pairs
directly with the §6.6 guard: the lint can both (a) flag disguised route tests in
`tests/unit/` *and* (b) refuse any attempt to convert a `db_semantics` test to
the component tier. A docstring alone is too weak precisely because we want a
guard that can enforce "don't fake this".

### 5.4 Putting the axes together

```
tests/
  unit/        # no Flask app, no I/O          -> (no infra markers)
  component/   # Flask HTTP + FakeUnitOfWork   -> requires_redis            (never db_semantics)
  integration/ # services/CLI/Celery + real PG -> requires_db (+ requires_celery)
  e2e/         # Flask HTTP + real PG          -> requires_db (+ requires_redis); holds the per-route PG smoke + db_semantics tests
  contract/    # repo contracts + real PG      -> requires_db
  bdd/         # behave, full stack            -> requires_db (+ ...)
```

`db_semantics` (§5.3) is orthogonal to the directory: it is a *positive* "never
fake this" marker applied to the e2e/integration tests whose whole point is real
DB behaviour. The §6.6 guard enforces that it never appears under `component/`.

## 6. Other maintainability recommendations

1. **Adopt a written "mock only at the boundary" rule.** The audit gives the
   canonical external-boundary list (§2): Celery dispatch, SMTP, OAuth, Google
   Sheets / `sortition-algorithms`, PIL, Redis, the DB engine, password hashing,
   the clock, i18n. **Never** mock the UoW, a repository, or an internal service
   — use a `FakeUnitOfWork` instead. Put this in `docs/testing.md` so new code
   copies the right pattern rather than the disguised-route-test pattern.

2. **Prefer state-based over interaction-based assertions** (§4) — this is the
   primary goal of the whole exercise, not a side effect. Assert on the
   `FakeStore` / rendered response, not "service X was called with Y". This is
   the single biggest fidelity + brittleness win and is *enabled* by the seam.
   Concretely, a converted test should make **no** `mock.assert_called_with(...)`
   style assertions about internal collaborators; if a test still needs those to
   prove anything, it has not really been converted. Where the audit calls a file
   a "dispatch test" (e.g. `test_backoffice_registration_actions.py`), the
   conversion work *is* re-pointing it at real outcomes — that rewrite is the
   deliverable, not an optional extra.

3. **Stop patching `get_flask_uow` per blueprint; inject via `create_app`.**
   Today 14 patches target `…blueprints.<bp>.bootstrap.get_flask_uow`. With the
   app-extension seam, a `fake_app`/`fake_client` fixture pair (generalising the
   `fake_pilot` conftest into a shared `tests/component/conftest.py`) means new
   tests need **no** UoW patch at all. Make converting a file cheap.

4. **Centralise the Celery boundary mock.** *(Deferred — a later round, NOT part
   of any work that follows from this document.)* The Celery dispatch is patched
   at *seven different dotted paths* across the suite (`…tasks.load_gsheet.delay`,
   `…run_select.apply_async`, `…run_select_from_db.delay`,
   `…app.app.control.revoke`, `…app.app.AsyncResult`, …). That drift is a
   maintenance liability worth fixing on its own schedule.

   **What a later round would require (notes, not a task list to start now):**

   - **Inventory the boundary.** The full set of patched symbols is the five
     dotted paths above plus the per-task `.delay`/`.apply_async` variants. Decide
     which represent *dispatch* (`.delay`, `.apply_async`), which represent
     *result/state* (`AsyncResult`, task `update_state`), and which represent
     *control* (`control.revoke`). They want different fixtures.
   - **Two fixtures, not one.** (i) a `no_celery` fixture that patches dispatch to
     a recording no-op (asserts "a task *would* have been queued" without running
     it) — for route tests that only care that dispatch happened; (ii) a
     `celery_eager` mode (`task_always_eager` + `task_eager_propagates`) for tests
     that want the task body to run synchronously in-process. These are different
     intents and a single fixture would conflate them.
   - **Where they live.** A shared `tests/conftest.py` (or a `tests/celery.py`
     helper) so the seven ad-hoc paths collapse to one import. Existing tests get
     migrated file-by-file; nothing is forced.
   - **Interaction with the fake seam.** `celery_eager` runs the task body, which
     uses an explicit `session_factory` against a real DB — so it is **not**
     compatible with the component (fake) tier and stays a `requires_db` (often
     `requires_celery`) concern. `no_celery` *is* compatible with the component
     tier (it just records dispatch). This is why the audit marks the Celery-heavy
     e2e files (Group D) "PARTIAL".
   - **Payoff.** Removes the "patch the internal service fn because the Celery
     path is awkward" anti-pattern in Group D, and lets some Group D route logic
     move to the component tier with only the dispatch tail faked.

5. **Add a second seam for the session backend** so the fast tier is truly
   serviceless (§5.3 caveat). A non-Redis session for the component tier drops
   the last service dependency. **Decided (§8 D7): Option 1** — reuse
   Flask-Session's own config, no new production seam. Options retained below for
   the record; Option 1 is the one to build.

   **Background.** Sessions are configured in `create_app` via Flask-Session
   pointed at Redis (`REDIS_*` config). The component tier needs *a* session
   store for login to work, but not necessarily Redis. Options, roughly in
   ascending effort:

   - **Option 1 — Reuse existing config, no new seam.** Flask-Session already
     supports a filesystem and a "null"/in-memory backend via `SESSION_TYPE`.
     Add a `"testing_component"` config (or just set `SESSION_TYPE=filesystem`
     in the component conftest) and pass no Redis. *Pros:* no production code
     change, uses a documented Flask-Session feature, smallest diff. *Cons:*
     filesystem sessions touch disk (still not zero-I/O, though no service);
     a true in-memory backend isn't first-class in Flask-Session and may need a
     tiny adapter.
   - **Option 2 — A `session_backend` parameter on `create_app`** mirroring
     `uow_factory` exactly: production passes nothing (Redis default), the
     component conftest passes an in-memory/filesystem backend. *Pros:*
     symmetric with the UoW seam, explicit, the wiring is visible. *Cons:* a
     real (if small) production-code seam to design and test; need to confirm
     Flask-Session lets us inject a backend object cleanly rather than only via
     `SESSION_TYPE` strings.
   - **Option 3 — Leave it.** Accept `tests/component/` as `requires_redis`.
     Redis is cheap, already running in CI and the test docker stack, and the
     pilot showed the real win was dropping *PostgreSQL*. *Pros:* zero work.
     *Cons:* the "run the fast tier with no services at all" pitch stays
     aspirational; a dev with no Redis still can't run the component tier.

   **Decision (Doctor Chewie): Option 1.** It's a clear improvement on what we
   value (no production seam, smallest diff) and good enough — the big win was
   dropping PostgreSQL, and this drops Redis for the component tier too.

   **Preferred in-memory variant (to spike):** rather than filesystem sessions
   (which still touch disk), use Flask-Session's cachelib backend with an
   in-process cache. Concretely, in the component config / conftest:

   ```python
   from cachelib.simple import SimpleCache

   SESSION_TYPE = "cachelib"
   SESSION_CACHELIB = SimpleCache()   # in-memory, per-process; no Redis, no disk
   ```

   Flask-Session wires this through its `CacheLibSessionInterface`
   (`flask_session.cachelib.CacheLibSessionInterface`) automatically when
   `SESSION_TYPE = "cachelib"`. Both `cachelib` and `flask-session` are already
   transitive deps (flask-session uses cachelib internally), so this likely needs
   no new dependency — **confirm during the spike** before relying on it, and add
   `cachelib` explicitly with `uv add` if it isn't a direct dependency. The spike
   is just: add the config, point the component conftest at it, confirm login/
   session round-trips work with no Redis running. Filesystem (`SESSION_TYPE =
   "filesystem"`) stays the trivial fallback if cachelib proves fiddly.

6. **Guard against new disguised route tests.** ✅ *Agreed with Doctor Chewie —
   in scope.* A lightweight collection-time check (or a lint) that flags a test
   in `tests/unit/` importing `create_app` / `test_client` would catch the Group
   B pattern at authoring time and steer it into `tests/component/` with the fake
   seam. The conftest reminder in `CLAUDE.md` (`_delete_all_test_data` ordering)
   shows the project already uses conftest-level guards; this is the same idea for
   test placement.

   The same guard should do double duty (see §5.3): refuse to let a
   `@pytest.mark.db_semantics` test be moved off the DB. So the guard has two
   rules — (a) no `create_app`/`test_client` import under `tests/unit/`, and
   (b) a `db_semantics` test must live under `tests/e2e/` (or `tests/integration/`),
   never `tests/component/`. A `pytest_collection_modifyitems` hook in the top
   `tests/conftest.py` is the natural home; it can hard-fail collection with a
   clear message pointing at the right directory.

## 7. Order of work (implementation status)

1. ✅ **Infra (done).** Registered the markers (`requires_db` / `requires_redis` /
   `requires_celery` / `db_semantics`) + `--strict-markers` in `pyproject.toml`,
   with auto-marking by directory in `tests/conftest.py`
   (`pytest_collection_modifyitems`). Created `tests/component/` with a shared
   `conftest.py` (fake-backed `app`/`client`, session_transaction login, seeded
   data fixtures). The cachelib in-memory session spike (§6.5 / §8 D7 Option 1)
   succeeded: added `FlaskTestComponentConfig` (`config "testing_component"`) with
   `SESSION_CACHELIB = SimpleCache()`, and login via session_transaction — so the
   component tier needs **no PostgreSQL and no Redis**.
2. **Cheapest, highest fidelity first:** Group C (`test_registration_public.py`,
   `test_registration_image_serve.py`) — only config mocks, pure request→
   service→assertion, near-identical to the pilot. Move the behavioural coverage
   to `tests/component/`; **keep one PG happy-path smoke per route in
   `tests/e2e/`** (§8 D2).
3. ✅ **Group B (done).** Converted all five Group B files to `tests/component/`
   driving real services over a `FakeUnitOfWork` with state-based assertions
   (`test_dev_image_handlers`, `test_backoffice_registration_actions`,
   `test_backoffice_registration_view`, `test_backoffice_registration_images`,
   `test_registration_routes`). Narrow single-service stubs kept only for a few
   `side_effect` error branches in `test_backoffice_registration_view`.
4. ✅ **Placement guard (done, §6.6):** the `pytest_collection_modifyitems` hook
   rejects unit tests that patch a blueprint's `get_flask_uow` (the precise
   disguised-route-test tell, rather than the broader create_app/test_client
   heuristic which fires on legitimate template/middleware tests) and rejects
   `db_semantics` tests under `tests/component/`.
5. **Update `docs/testing.md`** per §9 as the above lands.
6. ✅ **Leave Groups E/F/G alone** — their mocks are correct.

Explicitly **out of this sequence:** centralising the Celery boundary mock (§6.4)
— deferred to its own later round (§8 D6). (The session-backend seam is now
decided — Option 1 — and folded into step 1 as a spike, no longer deferred.)

## 8. Decisions (resolved with Doctor Chewie)

- **D1 — Directory taxonomy.** ✅ **Yes to `tests/component/`** for Flask-HTTP-
  over-`FakeUnitOfWork` tests. Reserve `tests/e2e/` for genuine Flask→Postgres→
  back round trips. Do **not** call component tests "unit" tests.
- **D2 — Keep a Postgres smoke per route.** ✅ **At least one PostgreSQL smoke
  test per Flask route**, simple happy path, living in **`tests/e2e/`**. So the
  pattern is *not* "move a suite wholesale to fakes": each route keeps a thin
  real-DB happy-path e2e test, and the richer behavioural coverage (branches,
  validation, edge cases) moves to the component tier on fakes. The pilot's
  re-export of `test_assembly_crud` was a *measurement* device, not this pattern;
  the long-term shape is "one PG happy-path smoke in e2e + the rest as component
  tests". This makes the divergence risk (`plan.md` §6) cheap to catch: if the
  fake and the DB ever disagree on the happy path, the e2e smoke fails.
- **D3 — `db_semantics` marker.** Proposed (§5.3): a marker for tests whose value
  *is* real DB behaviour (cascades/constraints/JSON operators), which must never
  be faked. Recommended over a docstring because the §6.6 guard can enforce it.
- **D4 — State-based assertions are the goal.** Confirmed primary objective
  (§6.2): converted tests assert on outcomes, not on `mock.assert_called_with`.
- **D5 — Disguised-route-test guard.** ✅ Agreed, in scope (§6.6).
- **D6 — Celery boundary centralisation.** Deferred to a later, separate round;
  notes on what it needs are in §6.4. **Not** to be done as part of this work.
- **D7 — Session-backend seam.** ✅ **Option 1** (§6.5): reuse Flask-Session's
  own config for the component tier — no new production seam. Preferred in-memory
  variant to spike: `SESSION_TYPE = "cachelib"` with `SimpleCache()` (via
  `flask_session.cachelib.CacheLibSessionInterface`); filesystem is the fallback.
  Confirm `cachelib` is an available dependency during the spike.

## 9. `docs/testing.md` updates needed

`docs/testing.md` is the canonical testing guide and currently predates all of
this. When the component tier and markers land, it needs these changes (noted
here, not yet applied):

- **Testing Levels — add a "Component Tests (`tests/component/`)" section**
  between Integration and End-to-End. Describe: full Flask app + test client, but
  `FakeUnitOfWork` via the injected `uow_factory` (point at `tests/e2e/fake_pilot/`
  as the seed pattern); no PostgreSQL; needs Redis today (until the §6.5 seam).
  Give the canonical fixture pattern (`fake_app`/`fake_client`/`fake_store`).
- **Testing Levels — tighten the "Unit Tests" section.** It currently says "No
  database, no Flask context" — which is the *intent* but not the current reality
  (the Group B disguised route tests violate it). State the rule firmly and point
  Flask-driven tests at the component tier.
- **Testing Levels — tighten "End-to-End Tests".** State that e2e means a real
  Postgres round trip, that **each route keeps at least one PG happy-path smoke
  here** (D2), and that `db_semantics`-marked tests live here and must never be
  faked.
- **New subsection — "Mocking policy"** under "Writing Good Tests": the "mock
  only at the boundary" rule (§6.1) with the canonical external-boundary list,
  and "prefer state-based over interaction-based assertions" (§6.2).
- **Test Configuration** — document the registered markers
  (`requires_db` / `requires_redis` / `requires_celery` / `db_semantics`) and
  `--strict-markers`, plus the `pytest -m "not requires_db"` fast-tier selection.
- **Test Database section** — clarify the matrix: unit = no DB; component = no DB
  (Redis only); integration/e2e/contract/bdd = Postgres on 54322. Update the
  "Unit Tests: ... some use PostgreSQL" line, which describes today's muddle.
- **Running Tests + Continuous Integration** — add `tests/component/` to the
  example commands and to the CI pipeline step list.

These are documentation follow-ups, gated on the corresponding code landing — not
part of the audit itself.
