# Faster Tests Research

## Current State

### Test counts and measured timings (non-BDD)

| Suite | Test count | Measured time | Notes |
|-------|-----------|--------------|-------|
| Unit (`tests/unit/`) | 644 | **4.6s** | Fast, mostly fakes |
| Integration (`tests/integration/`) | 286 | **63s** | Mix of SQLite and PostgreSQL |
| E2E (`tests/e2e/`) | 419 | **~170s** | PostgreSQL + Flask test client |
| **Total (non-BDD)** | **1349** | **238s (3m58s)** | |
| BDD (`tests/bdd/`) | 128 | ~120-300s* | Playwright + Flask server + Celery |

*BDD estimated; not measured in this run.

`just test` runs `just test-html` which runs ALL tests including BDD with coverage.
`just test-nobdd` skips BDD but still runs unit + integration + e2e with coverage.

### Where the time goes (top slowest from `--durations=0`)

**Individually slow tests:**

| Duration | Phase | Test | Root cause |
|----------|-------|------|------------|
| 6.01s | call | `e2e/test_health_check::test_health_check_returns_500_when_database_fails` | Waiting for DB connection timeout |
| 2.19s | call | `integration/test_celery_tasks::test_run_select_saves_selected_ids` | Sortition algorithm execution |
| 2.19s | call | `integration/test_celery_tasks::test_run_select_success` | Sortition algorithm execution |
| 1.39s | call | `integration/test_2fa_setup_flow::test_regenerate_backup_codes` | Backup code hashing (werkzeug) |
| 1.26s | call | `integration/test_2fa_login_flow::test_login_with_2fa_backup_code` | Backup code verification (werkzeug) |
| 0.90s | call | `e2e/test_2fa_flow::test_setup_2fa_complete_flow` | 2FA setup including backup code hashing |
| 0.81s | call | `e2e/test_assembly_crud::test_assembly_appears_in_list_after_creation` | Multi-step CRUD flow |
| 0.78s | call | `e2e/test_assembly_gsheet_crud::test_create_gsheet_soft_validation...` | Flask + DB round trips |

**Fixture setup costs:**

| Duration | Test group | Root cause |
|----------|-----------|------------|
| 1.45s | `e2e/test_2fa_flow::test_disable_2fa` | `postgres_session_factory` + user creation + 2FA enable (backup code hashing) |
| 0.7-0.9s | ~8 integration tests with 2FA | `sqlite_session_factory` + `test_user_with_2fa` (backup code hashing) |
| 0.7-0.9s | ~100+ e2e tests | `postgres_session_factory` + user creation + login |
| 0.02-0.06s | Non-2FA integration tests | `sqlite_session_factory` alone (fast!) |

**Key correction:** The `sqlite_session_factory` fixture itself is fast (~16ms benchmarked). The 0.7s setup times on 2FA integration tests come from the `test_user_with_2fa` fixture which calls `two_factor_service.setup_2fa()` and `enable_2fa()` - these hash 10 backup codes using werkzeug's pbkdf2. The e2e test setup costs come from PostgreSQL round-trips + user creation + login flows, not from table creation.

### Current architecture

The project uses a UnitOfWork pattern with:
- `AbstractUnitOfWork` - interface with 12 repository types
- `SqlAlchemyUnitOfWork` - production implementation
- `FakeUnitOfWork` (in `tests/fakes.py`) - complete in-memory implementation of all 12 repositories

Unit tests already use `FakeUnitOfWork` extensively. Integration and e2e tests use real databases.

### Dual database support

The codebase currently supports both SQLite and PostgreSQL:
- `CrossDatabaseUUID` type in `orm.py` (45 usages across all tables) - stores UUIDs as native PostgreSQL UUID or SQLite CHAR(36)
- `FlaskTestSQLiteConfig` in `config.py` for SQLite-based testing
- `sqlite_session_factory` fixture in `tests/conftest.py`
- Integration tests split between SQLite (2FA, password reset, email confirmation, CLI, CSV import) and PostgreSQL (repositories, ORM, search, sortition)

---

## Identified Bottlenecks (ordered by impact)

### 1. CRITICAL: E2E test fixture setup (~0.7-1.5s per test)

The e2e test suite (419 tests, ~170s) spends most of its time in fixture setup: creating the Flask app, setting up `postgres_session_factory`, creating users, and logging in. Each test pays this cost because fixtures are function-scoped.

The `postgres_session_factory` fixture creates and drops all tables per test (`create_all`/`drop_all`). While the table creation itself is modest, the PostgreSQL network round-trips add up over 419 tests.

### 2. HIGH: Backup code hashing (~0.7s per 2FA test setup, ~1.3s per 2FA call)

**STATUS: FIXED** - Extended the `patch_password_hashing` fixture to also patch `totp_service.generate_password_hash`. 2FA integration tests went from 8s to 1.6s.

### 3. MEDIUM: Tests misclassified as "integration"

Several files in `tests/integration/` don't use a database at all:
- `test_email.py` - tests email adapter configuration
- `test_feature_flag_context.py` - tests Flask context processor
- `test_flask_app.py` - tests Flask app creation and blueprint registration
- `test_respondents_routes.py` - tests route registration
- `test_targets_routes.py` - tests route registration

These are effectively unit tests.

### 4. MEDIUM: Individually slow tests

- `test_health_check_returns_500_when_database_fails` (6.01s) - waiting for DB connection timeout
- `test_run_select_*` tests (2.19s each) - running actual sortition algorithm

### 5. LOW: `time.sleep()` calls

- `tests/unit/domain/test_assembly.py`: three `time.sleep(0.01)` calls
- `tests/bdd/shared/email_confirmation_steps.py`: `time.sleep(0.1)`
- `tests/conftest.py:174`: `time.sleep(0.5)` in unused `restart_api` fixture

Minimal cumulative impact.

---

## Should We Drop SQLite and Standardise on PostgreSQL?

### Current SQLite usage

Integration tests that use `sqlite_session_factory`:
- `test_2fa_login_flow.py` (9 tests)
- `test_2fa_setup_flow.py` (9 tests)
- `test_admin_2fa.py` (8 tests)
- `test_email_confirmation_integration.py` (10 tests)
- `test_password_reset_flow.py` (10 tests)
- `test_csv_import_with_config.py` (7 tests)
- `test_respondent_service.py` (6 tests via `postgres_session_factory` - actually uses PostgreSQL)
- `test_cli_integration.py` (24 tests via `cli_with_session_factory`)

**Total: ~77 tests on SQLite, ~60 tests on PostgreSQL** (plus ~419 e2e tests on PostgreSQL).

### Performance comparison

Benchmarked: `create_all` + `start_mappers` + `clear_mappers` + `drop_all`:
- **SQLite (in-memory):** ~16ms per cycle
- **PostgreSQL (localhost):** ~50-100ms per cycle (network overhead)

For the actual test queries (tiny datasets, simple CRUD), the difference is negligible. The dominant cost is business logic (hashing, algorithm execution), not database I/O.

### Complexity cost of dual-database support

1. **`CrossDatabaseUUID`** (orm.py:77-119) - 43 lines of dialect-switching code, used in 45 column definitions across 14 tables
2. **`FlaskTestSQLiteConfig`** (config.py) - separate config class
3. **`sqlite_session_factory` fixture** (conftest.py) - duplicate fixture alongside `postgres_session_factory`
4. **`in_memory_sqlite_db` fixture** (conftest.py) - only exists for SQLite
5. **Subtle behaviour differences** - SQLite doesn't enforce foreign keys by default, has different transaction semantics, and doesn't support PostgreSQL-specific features like `JSON` column operators

### Recommendation: Yes, drop SQLite

**Arguments for dropping SQLite:**
- Eliminates ~90 lines of cross-database compatibility code
- Tests run against the same database as production - catches more real bugs
- Simplifies `orm.py` significantly (use `PostgresUUID` directly instead of `CrossDatabaseUUID`)
- One fewer fixture path to maintain
- SQLite's foreign key and transaction semantics differ from PostgreSQL, so SQLite integration tests can pass while PostgreSQL would fail (false confidence)
- The ~77 SQLite tests would add only ~3-5s when moved to PostgreSQL (77 tests x 50ms extra overhead)

**Arguments for keeping SQLite:**
- Developers can run some integration tests without Docker/PostgreSQL running
- Slightly faster per-test overhead (16ms vs 50-100ms)

**Verdict:** The simplification benefit outweighs the minor speed advantage. The test Docker compose for PostgreSQL is already required for e2e tests, so requiring it for integration tests too is not a meaningful burden. If fast no-database feedback is desired, converting service-layer tests to `FakeUnitOfWork` (approach A1) is a better solution.

---

## Approaches: Tests-Only Changes

These changes only modify test code and fixtures, not production code.

### A1. Convert service-layer integration tests to use FakeUnitOfWork

**Impact: MEDIUM (~5-10s savings, plus better test design)**

The following integration tests use `sqlite_session_factory` but are really testing service-layer logic. They could use `FakeUnitOfWork` instead:

| File | Tests | Why FakeUoW works |
|------|-------|-------------------|
| `test_2fa_login_flow.py` | 9 | Tests TOTP/backup code verification logic |
| `test_2fa_setup_flow.py` | 9 | Tests 2FA enable/disable/regenerate flows |
| `test_admin_2fa.py` | 8 | Tests admin 2FA management and audit logs |
| `test_email_confirmation_integration.py` | 10 | Tests token creation/validation/expiry |
| `test_password_reset_flow.py` | 10 | Tests token lifecycle and rate limiting |
| `test_csv_import_with_config.py` | 7 | Mixed - see note below |

Note: `test_user_assembly_role_management.py` already uses `FakeUnitOfWork` - it's a good example of this pattern.

**`test_csv_import_with_config` specifics:** Some tests here genuinely exercise ORM relationship cascades (e.g. `test_import_creates_default_config` verifies `assembly.csv` is auto-created via the SQLAlchemy one-to-one relationship, and `test_update_csv_config` verifies changes persist across separate UoW contexts). These should stay as database tests. Approach: split the file into two classes - a `TestCSVImportServiceLogic` class using `FakeUnitOfWork` for the pure service logic, and keep a `TestCSVImportDatabaseIntegration` class for the ~3 tests that verify ORM cascades and persistence.

**Risk:** Low. The `FakeUnitOfWork` is comprehensive and already used for similar tests in `tests/unit/`.

### A2. Patch backup code hashing in tests

**STATUS: DONE**

Extended `patch_password_hashing` in `tests/conftest.py` to also monkeypatch `totp_service.generate_password_hash` with the fast 1-iteration version. Result: 2FA integration tests went from 8.02s to 1.62s.

### A3. Session-scoped `postgres_session_factory` with BDD-style cleanup

**STATUS: DONE** - Implemented session-scoped `_postgres_tables` fixture and `_delete_all_test_data()` cleanup function. E2e tests went from ~170s to ~63s. Total non-BDD test time went from ~238s to ~71s.

**Impact: HIGH (estimated 30-60s savings on e2e tests)**

Instead of `create_all`/`drop_all` per test, create tables once per session and use explicit DELETE cleanup between tests (the BDD pattern).

**Why rollback won't work:** `SqlAlchemyUnitOfWork.__exit__` calls `self.session.commit()` (line 130 of `unit_of_work.py`), which commits the outer transaction. A wrapping rollback-based fixture can't undo committed data. This is inherent to the UoW pattern - the whole point is that `__exit__` commits.

**Proposed approach (BDD-style cleanup):**

```python
@pytest.fixture(scope="session")
def _postgres_tables(postgres_engine):
    """Create tables once for the entire test session."""
    orm.metadata.create_all(postgres_engine)
    database.start_mappers()
    yield
    database.clear_mappers()
    orm.metadata.drop_all(postgres_engine)

@pytest.fixture
def postgres_session_factory(postgres_engine, _postgres_tables):
    """Provide a session factory, clean up data after each test."""
    session_factory = sessionmaker(bind=postgres_engine)
    yield session_factory
    # BDD-style cleanup: delete all data respecting FK constraints
    session = session_factory()
    try:
        session.execute(orm.totp_verification_attempts.delete())
        session.execute(orm.two_factor_audit_log.delete())
        session.execute(orm.user_backup_codes.delete())
        session.execute(orm.email_confirmation_tokens.delete())
        session.execute(orm.password_reset_tokens.delete())
        session.execute(orm.selection_run_records.delete())
        session.execute(orm.respondents.delete())
        session.execute(orm.target_categories.delete())
        session.execute(orm.assembly_gsheets.delete())
        session.execute(orm.assembly_csv.delete())
        session.execute(orm.user_invites.delete())
        session.execute(orm.user_assembly_roles.delete())
        session.execute(orm.assemblies.delete())
        session.execute(orm.users.delete())
        session.commit()
    finally:
        session.close()
```

This is proven in the BDD tests (`tests/bdd/conftest.py:382-397`, `delete_all_except_standard_users`). The BDD version keeps admin/normal users; the integration/e2e version would delete everything since there are no session-scoped users.

**Savings:** Eliminates per-test `create_all`/`drop_all` (which involves DDL round-trips to PostgreSQL). The DELETE cleanup is faster than DDL since it operates on data, not schema. Also eliminates per-test `start_mappers`/`clear_mappers` cycling.

**Risk:** Low-medium. DELETE cleanup is slightly less isolated than drop/create (e.g. auto-increment sequences won't reset), but this doesn't matter for tests that use UUIDs. The BDD tests have been using this pattern successfully.

**Extra:** We need to remember to add new tables to the delete list - and add them in an order that will work with foreign keys etc. At the least, add a note to AGENTS.md (or one of the files it references) to point out this needs to be maintained. Probably best to add it where we talk about adding database migrations, which would need to be read when a new table is added.

### A4. Move misclassified tests to unit

**Impact: LOW (cleaner organisation, enables running `pytest tests/unit/` for fast feedback)**

Move from `tests/integration/` to `tests/unit/`:
- `test_email.py`
- `test_feature_flag_context.py`
- `test_flask_app.py`
- `test_respondents_routes.py`
- `test_targets_routes.py`

**Risk:** Very low.

### A5. Add pytest markers for selective test running

**Impact: MEDIUM (developer experience, not raw speed)**

Add markers like `@pytest.mark.db`, `@pytest.mark.slow`:

```ini
[tool.pytest.ini_options]
markers = [
    "db: tests that require a database",
    "slow: tests that take more than 1 second",
]
```

Developers could run `pytest -m "not db"` for instant feedback during development.

**Risk:** Very low. Purely additive.

### A6. Parallel test execution with pytest-xdist

**Impact: Only worth doing for PostgreSQL tests**

Unit test parallelisation has been tried and the xdist worker startup overhead means it saves less than 5 seconds (unit tests already run in 4.6s). This is only worth pursuing if PostgreSQL-backed tests can be parallelised.

**For PostgreSQL parallelisation**, the options are:
- **Per-worker databases:** Use `pytest-xdist` worker IDs to create separate PostgreSQL databases per worker. Each worker gets `opendlp_test_worker0`, `opendlp_test_worker1`, etc. This gives full isolation but requires database creation logic in conftest.
- **Shared schema, isolated data:** With A3's BDD-style cleanup, workers would collide on data. Would need unique test data (e.g. unique email addresses per worker) to avoid conflicts.

**Recommended:** Per-worker databases. The `conftest.py` `postgres_engine` fixture would use the `worker_id` xdist fixture to append a suffix to the database name.

**Risk:** Medium. Requires careful fixture design and database provisioning.

### A7. Profile and optimise individually slow tests

**Impact: MEDIUM (~10s savings)**

- `test_health_check_returns_500_when_database_fails` (6.01s) - reduce the connection timeout for this specific test
- `test_run_select_*` (2.19s each) - these run the actual sortition algorithm, may be hard to optimise without mocking

**Risk:** Low per test.

---

## Approaches: Requiring Production Code Changes

### B1. Drop SQLite support, standardise on PostgreSQL

**Impact: Simplifies codebase, enables simpler test fixtures**

1. Replace `CrossDatabaseUUID` with `PostgresUUID(as_uuid=True)` across all 45 column definitions
2. Remove `FlaskTestSQLiteConfig` from `config.py`
3. Remove `in_memory_sqlite_db` and `sqlite_session_factory` fixtures
4. Convert the ~77 SQLite integration tests to use `postgres_session_factory`
5. Remove the `SQLITE_DB_URI` constant

This is a prerequisite for making the test fixtures simpler (only one database to worry about) and eliminates a class of false-positive test results where SQLite passes but PostgreSQL wouldn't.

**Risk:** Low-medium. Straightforward mechanical change. Developers must have PostgreSQL running (via Docker) to run any database tests. See the analysis in "Should We Drop SQLite?" section above.

### B2. Inject UnitOfWork via bootstrap.py

**Impact: MEDIUM-HIGH**

Currently, Flask routes create `SqlAlchemyUnitOfWork` internally. By centralising UoW creation in `bootstrap.py`, routes can get UoW instances without knowing the concrete implementation.

`bootstrap.py` already has a `bootstrap()` function that accepts a `uow` parameter. The proposal is to add two functions:

```python
def get_uow() -> AbstractUnitOfWork:
    """Get a single UnitOfWork instance for the current request.
    Used by routes that only need one UoW context."""
    return SqlAlchemyUnitOfWork(bootstrap_session_factory())

def get_uow_factory() -> Callable[[], AbstractUnitOfWork]:
    """Get a factory that creates UnitOfWork instances.
    Used by routes that need multiple UoW contexts (e.g. create-then-read patterns)."""
    session_factory = bootstrap_session_factory()
    return lambda: SqlAlchemyUnitOfWork(session_factory)
```

Routes would call `get_uow()` or `get_uow_factory()` instead of constructing `SqlAlchemyUnitOfWork` directly. In tests, these functions could be monkeypatched to return `FakeUnitOfWork`, letting e2e tests run without PostgreSQL.

**Risk:** Medium. Requires updating all route files to use the new pattern. The refactor is mechanical but touches many files.

---

## Recommended Priority Order

### Quick wins (do first):

1. **A2** - DONE: Patch backup code hashing in tests (~15-20s saved)
2. **A4** - Move 5 misclassified integration tests to unit (cleaner organisation)
3. **A7** - Fix the 6s health check timeout test

### Medium-term (more effort, bigger payoff):

4. **B1** - Drop SQLite, standardise on PostgreSQL (simplifies everything that follows)
5. **A3** - Session-scoped `postgres_session_factory` with BDD-style cleanup (30-60s saved on e2e)
6. **A1** - Convert service-layer tests to `FakeUnitOfWork` (cleaner test design; split `test_csv_import_with_config` into service-logic and DB-integration classes)
7. **A6** - Parallel test execution with pytest-xdist using per-worker databases

### Longer-term:

8. **B2** - UoW creation via `bootstrap.py` with `get_uow()` and `get_uow_factory()` (would let e2e tests run without DB)

---

## Expected Results

| Approach | Time saved | Effort |
|----------|-----------|--------|
| A2 (patch backup code hashing) | ~15-20s | DONE |
| A4 (move misclassified tests) | ~0s (cleanliness) | 1 hour |
| A7 (fix health check timeout) | ~5s | 30 min |
| B1 (drop SQLite) | ~0s directly, enables A3 | 1 day |
| A3 (session-scoped postgres + cleanup) | ~30-60s | 1 day |
| A1 (FakeUoW conversion) | ~5-10s | 1-2 days |
| A6 (parallel execution, per-worker DBs) | 50-70% of remaining time | 2-3 days |

**Realistic target with A2 + A3 + A6:** Non-BDD test time from **~4 minutes down to under 1 minute**.
