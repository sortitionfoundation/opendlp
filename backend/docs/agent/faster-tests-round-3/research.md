# Faster Tests Round 3 — Research

> Status: **Research only.** All measurements were taken on 2026-09-04; the two
> spike diffs were reverted after measuring and are reproduced in the appendix.
> Nothing in the repo changed except this document.

## Summary

The suite has slowed because of one systematic cost: **every component and e2e
test builds a brand-new Flask app, and ~90% of `create_app()` is werkzeug
re-compiling the same ~207 URL rules**. Doctor Chewie's caching hunch was right,
but the expensive part is route registration, not Jinja template loading.

A ~15-line spike (session-scoped app, per-test `FakeStore` swapped through the
existing `uow_factory` seam) was measured, not estimated:

| Run (this machine, 4 xdist workers unless "serial") | Before | After spike | Change |
| --- | --- | --- | --- |
| `tests/component` (1039 tests, xdist, no cov) | 74s | **17s** | 4.3× |
| `tests/component` (serial, no cov) | 222s | **37s** | 6.0× |
| `tests/e2e` (361 tests, xdist, no cov) | 35s | **20s** | 1.8× |
| Full non-BDD (4873 tests, xdist, no cov) | 128s | **52s** | 2.5× |
| Full non-BDD (xdist, with coverage — the `just test-nobdd` shape) | 220s | **110s** | 2.0× |

All 1039 component tests pass under the spike unmodified. The e2e tier needs a
small autouse "restore `app.config`" fixture (details below); with it, all 361
pass. Three unit config tests need a one-line fix each.

The other big lever is **coverage: it adds ~90s (+72%) to the full non-BDD
run** (128s → 220s before the spike; 52s → 110s after). Options below, the best
of which needs Python 3.14.

Recommended order of work:

1. Session-scoped app for `tests/component/` — biggest win, smallest change.
2. Session-scoped app for `tests/e2e/` — same idea plus a config-restore fixture.
3. `-n auto` in the GitHub Actions test job — the per-worker DB machinery
   already works there; roughly halves the CI test step.
4. Fix the CI Python matrix (it almost certainly tests 3.12 three times — see
   below), then consider the 3.13/3.14 upgrade.
5. Decide what to do about coverage overhead (local no-cov default now;
   `sysmon` core after 3.14).
6. Small: memoize `get_password_validators()`.

Deleting tests, by contrast, is **not** where the time is (analysis below).

## Method

- Machine: 4-core x86_64 Linux, local test containers (PostgreSQL 54322, Redis
  63792) already running. `-n auto --maxprocesses=8` therefore means 4 workers.
- Baseline timing run: the `just test-nobdd` pytest command plus `--durations=0`,
  output parsed and aggregated per directory/phase.
- Per-fixture attribution: `cProfile` around 20 repeated `create_app()` calls,
  and `python -m cProfile -o ... -m pytest` over two component files.
- Spike: edit the two conftests, re-run the affected tier(s), revert. The exact
  diffs are in the appendix.
- BDD was not measured this round. It runs serially after the non-BDD suite in
  `just test`, manages its own Flask/Celery processes, and cannot use xdist;
  everything here is about the non-BDD ~4900 tests.

## Where the time goes

Aggregating `--durations=0` from the baseline run (times are summed across the
4 workers, so ~4× wall clock; entries under 5ms are excluded by pytest):

| Tier | Tests | Total | setup | call | teardown |
| --- | --- | --- | --- | --- | --- |
| component | 1039 | 480s | **322s** | 158s | 0s |
| e2e | 361 | 168s | **99s** | 65s | 4s |
| unit | ~2900 | 35s | 15s | 20s | 1s |
| integration | 384 | 29s | 6s | 18s | 5s |
| contract | 608 | 14s | 1s | 5s | 7s |

Two thirds of the suite's recorded time is component + e2e **fixture setup**,
and profiling two component files showed the `app` fixture alone was 12.9s of
17.5s (74%). So the question "where is the time spent" has a one-line answer:
building Flask apps we then throw away.

### Anatomy of a `create_app()` call

Microbenchmark (component config, fake UoW):

- Importing `opendlp.entrypoints.flask_app`: 2.3s, **once per process** — this
  is the unavoidable per-worker floor, not a per-test cost.
- First `create_app()` in a process: ~550ms (lazy imports).
- Every subsequent `create_app()`: **~90–140ms**, of which ~90% is
  `register_blueprints()` → `werkzeug.routing.Rule.compile()`. Werkzeug builds
  each rule's regex **and** generates+compiles Python code for its URL builder
  (`_compile_builder` does AST construction and `compile()`), for ~207 routes,
  per app.
- The rest: whitenoise re-scanning the static directory (~15ms), extensions,
  config, handlers.
- First render of a template chain on a fresh app pays Jinja compilation again
  (~20–100ms depending on the page), because each app gets a new Jinja
  environment with a cold cache.

So Doctor Chewie's two hypotheses, checked against the profile:

- *"cache flask app creation"* — **yes**, this is the fix, worth ~140ms+ per
  test across ~1400 tests.
- *"have the main flask app cache jinja template loading"* — real but minor
  (~20–30ms per fresh app on typical pages, and only for the templates a test
  actually renders). Caching the app gets this for free, since the Jinja env
  and its compiled-template cache live on the app. A shared
  `jinja2.FileSystemBytecodeCache` would help fresh-app tests a little, but is
  not worth doing on its own.

## Finding 1: session-scoped apps (the big one)

### Component tier — drop-in, 4–6× faster

The seam built in round B2 makes this almost embarrassingly easy: routes
resolve their UnitOfWork factory from `app.extensions["uow_factory"]` **at
request time**, so a session-scoped app can have its per-test `FakeStore`
swapped in through a mutable holder:

```python
@pytest.fixture(scope="session")
def _component_app_and_store_holder():
    holder: dict = {}
    app = create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=holder["store"]))
    return app, holder


@pytest.fixture
def app(_component_app_and_store_holder, fake_store):
    app, holder = _component_app_and_store_holder
    holder["store"] = fake_store
    return app
```

Results: **74s → 17s** (xdist) and **222s → 37s** (serial), all 1039 tests
passing with no other change. The serial number is the one that matters for
`just test`, which runs everything in a single serial process.

Why it works with no fallout:

- `client` is function-scoped, so each test starts with fresh cookies; stale
  sessions in the shared `SimpleCache` are unreachable.
- The autouse Redis/Celery stubs are `monkeypatch`-based module patches,
  independent of the app object.
- Files that need a differently-configured app (`test_oauth_flow`,
  `test_registration_bot_protection`, `test_registration_auto_reply`,
  `test_dev_registration_page_handlers`) already override `app` locally and
  keep their function-scoped custom apps. That is the escape hatch, and it
  costs only those files their 140ms/test.

What the real implementation must add beyond the spike:

- **A config/extension restore guard.** `test_registration_bot_protection.py`
  and `test_respondent_export.py` mutate `app.config` /
  `app.extensions["gsheet_export_target_factory"]` without restoring. Under the
  spike they happened to pass (their own `app` override, or no later test
  asserting the default), but a shared app must not depend on luck. Add an
  autouse fixture that snapshots `app.config` and the mutable extension slots
  and restores them after each test — measured as free in the e2e spike — and/or
  convert the mutation sites to `monkeypatch.setitem(app.config, ...)`.
- A comment on the session fixture explaining the holder pattern and that
  tests needing different app *construction* (not config) override `app`.
- `tests/component/` docs in `docs/testing.md` updated to describe the shared
  app and the "don't mutate app state without monkeypatch" rule.

### E2e tier — needs a restore fixture, then ~1.8× faster

Same idea (one app per xdist worker, since `worker_db_url` and the Redis DB are
session-constant per worker):

```python
@pytest.fixture(scope="session")
def app(worker_db_url, test_redis_client):
    os.environ["DB_URI"] = worker_db_url
    os.environ["REDIS_PORT"] = "63792"
    os.environ["REDIS_DB"] = str(test_redis_client.connection_pool.connection_kwargs["db"])
    reset_celery_app()
    start_mappers()
    return create_app("testing_postgres")
```

First attempt: 110 of 361 failed. The cause was instructive: every failure
traced to **unrestored `app.config` mutations leaking through the shared app**.
The smoking gun was `test_auth_flow.py::test_csrf_protection_enabled`, which
sets `WTF_CSRF_ENABLED = True` and never sets it back — with per-test apps that
leak was invisible; with a shared app every later POST in the worker got a CSRF
400. Adding this autouse fixture took the tier to **361/361 passing at 20s
(from 35s)**:

```python
@pytest.fixture(autouse=True)
def _restore_app_config(app):
    saved_config = dict(app.config)
    saved_export_factory = app.extensions.get("gsheet_export_target_factory")
    yield
    app.config.clear()
    app.config.update(saved_config)
    app.extensions["gsheet_export_target_factory"] = saved_export_factory
```

Remaining loose ends for the real implementation:

- The session fixture sets `DB_URI` process-wide and permanently (it must stay
  set while any e2e test runs, because `bootstrap_session_factory()` reads
  `get_db_uri()` lazily). Three `tests/unit/test_config.py` tests that assert
  config defaults then see `DB_URI` when they run after an e2e test on the same
  worker. Fix: those tests should `clear_env_vars("DB_URI")` — arguably they
  should already, since `DB_URI` is in `ENV_KEYS_TESTS_MAY_INHERIT` and could
  leak from a developer's `.env` today.
- `reset_celery_app()` and `start_mappers()` move from per-test to per-session.
  No test failed because of this, but it deserves a comment: any future test
  that deliberately breaks the celery app or mappers must repair them.
- The `_restore_app_config` fixture belongs in both e2e and component
  conftests.

### Alternatives considered and rejected

- **A dict of cached apps keyed by config hash** (Doctor Chewie's variant):
  works, but the key is hard to get right — `create_app` reads `os.environ`
  in many places, so "hash of the config object and environment" is really
  "hash of everything", and a wrong key silently reuses the wrong app. One
  session app per tier plus local `app` overrides for the handful of special
  files gives the same win with an obvious failure mode (a test that needs a
  custom app declares one).
- **Caching werkzeug's rule compilation** (memoize `Rule.compile` artifacts
  across apps): would keep fresh apps per test and still kill ~90% of the
  cost, but it reaches into werkzeug internals whose compiled builders are not
  documented as shareable between maps. Too clever; boring wins.
- **Jinja `FileSystemBytecodeCache`**: minor on its own (see above); free once
  the app is shared.

## Finding 2: coverage costs 72% of the run

Same command with and without `--cov` (baseline code, xdist):

- With coverage: **220s**. Without: **128s**.
- After the spikes the gap is proportionally worse: 110s vs 52s — coverage
  becomes the *dominant* remaining cost.

Options, not mutually exclusive:

- **Run the local default target without coverage.** `just test-nobdd` is the
  edit-test loop; CI and `just test` keep coverage. Cheapest 90 seconds
  available. (Add a `just test-cov` for when a local report is wanted.)
- **`COVERAGE_CORE=sysmon`** (coverage.py's `sys.monitoring` core): measured a
  no-go today — `covdefaults` turns on branch coverage, and on Python 3.12
  coverage warns `sys.monitoring can't measure branches in this version` and
  falls back. Branch-capable sysmon needs **Python 3.14**. After a 3.14
  upgrade this should cut most of the overhead for one env-var; re-measure
  then.
- Dropping branch coverage to enable sysmon on 3.12 is possible but trades
  away real signal; not recommended.

## Finding 3: Python 3.13/3.14 (scope added by Doctor Chewie)

- `pyproject.toml` has `requires-python = ">=3.12,<3.13"` and `uv.lock` is
  resolved for `==3.12.*`.
- **The CI matrix on 3.13/3.14 is therefore suspect.** The setup action runs
  `uv sync --frozen`; with the lock pinned to `==3.12.*`, uv on a 3.14
  interpreter either errors or falls back to a uv-managed 3.12 interpreter
  (locally it hard-errors: *"The requested interpreter resolved to Python
  3.14.4, which is incompatible with the project's Python requirement:
  `==3.12.*`"*). Since those CI legs are green, the likely explanation is that
  setup-uv provisions 3.12 and all three matrix legs test the same
  interpreter. **Action: check a recent Actions log for the `3.14` leg — the
  `uv sync` step prints `Using CPython <version>`.** (Not verifiable from this
  machine; `gh` is unauthenticated.)
- I could not measure 3.14 locally for the same reason — a genuine test needs
  `requires-python = ">=3.12"` plus a re-lock, which is a real change, not a
  spike.
- Why the upgrade is attractive for test speed specifically:
  - 3.13 and 3.14 each carry general interpreter speedups (3.14's tail-calling
    interpreter is roughly 5–10% on typical workloads); our suite is
    CPU-bound in exactly the interpreter-heavy places (route compilation,
    template rendering, fake-store work).
  - **3.14 unlocks branch-capable `sysmon` coverage** (Finding 2) — likely the
    single biggest per-run saving after the session-scoped apps.
  - No needed package is known to block: the lock's dependencies all publish
    3.13/3.14 wheels according to the CI runs — but that claim is only as good
    as the matrix actually testing those versions, which is the point above.
- Suggested sequence: fix the matrix first (`requires-python = ">=3.12"`,
  `uv lock`, confirm the 3.13/3.14 legs print the right interpreter), let it
  soak, then bump the dev/default pin when comfortable.

## Finding 4: pytest-xdist in GitHub Actions (scope added by Doctor Chewie)

`main.yml`'s test step runs pytest **serially**:

```yaml
run: uv run python -m pytest tests --ignore tests/bdd --cov --cov-config=pyproject.toml --cov-report=xml --cov-fail-under=80
```

Adding `-n auto` should be close to a flag flip, because everything xdist needs
already works in that environment:

- The per-worker database machinery (`_worker_database` in `tests/conftest.py`)
  creates `opendlp_test_gwN` databases by connecting to the `opendlp` database
  on port 54322 — exactly what the workflow's postgres service container
  provides. Per-worker Redis DBs 1–15 likewise map onto the redis service.
- `--cov` composes with xdist (pytest-cov combines worker data files); the
  local `just test-nobdd` has run this exact combination for months.
- GitHub's `ubuntu-latest` public runners have 4 vCPUs, the same as this
  machine — expect the test step to drop roughly in half (here: 220s → 110s
  shape; CI adds container/network overhead so measure, don't promise).
- The win multiplies by three because of the version matrix, and again on
  release builds via `workflow_call`.

Caveats to note in the PR:

- `bdd.yml` must stay serial — BDD tests manage their own Flask/Celery server
  processes (same reason `just test-bdd` is serial locally).
- If a test order dependency has been hiding in the serial CI run, xdist will
  surface it. The local parallel runs are green, so the risk is low.
- Add `--maxprocesses=8` for symmetry with the justfile, or leave `-n auto`
  bare; on 4-vCPU runners it makes no difference.

## Smaller findings

- **`get_password_validators()` rebuilds its validators per call** —
  `SafeCommonPasswordValidator()` re-reads Django's gzipped common-password
  list every time (~10ms). Every `create_user` in a fixture pays it. Build the
  tuple once at module level (validators are stateless); saves ~10s of worker
  time across the suite and a little production latency too.
- **`tests/unit/test_env_scrub.py`**: two tests at ~3s each re-scan the source
  tree with AST walks. A module/session-scoped fixture holding the scan result
  would halve that. Low priority.
- **Parametrized render-assert files** (`test_backoffice_registration_page_script.py`
  at 88s worker time / 79 tests, `test_dev_patterns_page.py` at 24s): each
  parametrized case re-renders the same 5 views into `every_view_html`. The
  session-scoped app removes most of the cost; if they are still noisy
  afterwards, module-scope the rendered-HTML fixture (it is read-only) so the
  rendering happens once per module rather than once per assertion.
- **Whitenoise re-scans `static/` on every app** (~15ms): moot once apps are
  session-scoped.
- The individually slow tests are legitimately slow work, not waste:
  `test_run_select_*` (~3.5–4s) run the real sortition solver;
  `test_check_with_insufficient_respondents_shows_error` (~1.3s) likewise.
  Round 1 already fixed the pathological cases.

## Tests we could delete?

Investigated, and the answer is: deletion is not where the time is.

- `tests/unit/` is 2167 test functions but only ~35s of worker time — deleting
  even a quarter of them saves seconds while costing coverage.
- `tests/contract/` runs everything twice by design and still costs only 14s.
- The genuinely duplicated-looking coverage is the **e2e tiers that were never
  trimmed to the D2 "one PostgreSQL smoke per route" pattern** after their
  behavioural coverage moved to `tests/component/`: `test_gsheets_routes.py`
  (34 e2e tests vs 10 component), `test_backoffice_gsheet_selection.py` (27
  vs 29), `test_sortition_routes.py` (19 vs 54), `test_backoffice_assembly.py`
  (19 vs 45). Most of these are the Celery-dominated Group D files where full
  conversion was deliberately deferred, so trimming means judgement per file,
  not bulk deletion — and the whole e2e tier is only ~35s wall in parallel, so
  this is a tidiness play more than a speed play.
- `tests/e2e/test_targets_legacy_pages.py` (37 tests, ~19s worker time) tests
  the legacy blueprints. It should die **with** the legacy blueprints, not
  before — flag it in the legacy-retirement issue so the deletion isn't
  forgotten.

## Raw data

Scratch outputs from the measurement session (not kept in the repo): baseline
`--durations=0` run, no-cov run, cProfile dumps, and spike timing logs. The
commands to reproduce:

```bash
# durations baseline (the just test-nobdd command + --durations=0)
uv run python -m pytest --tb=short --ignore=tests/bdd --cov --cov-config=pyproject.toml -n auto --maxprocesses=8 --durations=0 -q

# coverage overhead: same without --cov
# tier timing: uv run python -m pytest tests/component -q -n auto --maxprocesses=8
# create_app profile: cProfile around 20 create_app("testing_component") calls
```

## Appendix: the spike diffs

Component conftest (`tests/component/conftest.py`):

```python
@pytest.fixture(scope="session")
def _component_app_and_store_holder():
    """One Flask app for the whole session; per-test store swapped via the holder."""
    holder: dict = {}
    app = create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=holder["store"]))
    return app, holder


@pytest.fixture
def app(_component_app_and_store_holder, fake_store):
    app, holder = _component_app_and_store_holder
    holder["store"] = fake_store
    return app
```

E2e conftest (`tests/e2e/conftest.py`) — replaces the function-scoped `app`,
plus the restore guard:

```python
@pytest.fixture(scope="session")
def app(worker_db_url, test_redis_client):
    """Create one test Flask application per xdist worker."""
    os.environ["DB_URI"] = worker_db_url
    os.environ["REDIS_PORT"] = "63792"
    os.environ["REDIS_DB"] = str(test_redis_client.connection_pool.connection_kwargs["db"])
    reset_celery_app()
    start_mappers()
    return create_app("testing_postgres")


@pytest.fixture(autouse=True)
def _restore_app_config(app):
    """Undo any app.config / extension mutations a test makes on the shared app."""
    saved_config = dict(app.config)
    saved_export_factory = app.extensions.get("gsheet_export_target_factory")
    yield
    app.config.clear()
    app.config.update(saved_config)
    app.extensions["gsheet_export_target_factory"] = saved_export_factory
```

Known follow-ups when landing the e2e half: `tests/unit/test_config.py` (three
tests need `clear_env_vars("DB_URI")`), and convert the `app.config` mutation
sites (`test_registration_bot_protection.py`, `test_respondent_export.py`,
`test_registration_public.py`, `test_auth_flow.py::test_csrf_protection_enabled`)
to `monkeypatch.setitem` for hygiene even though the restore guard covers them.
