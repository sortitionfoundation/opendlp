"""ABOUTME: Pytest configuration and fixtures for OpenDLP tests
ABOUTME: Provides test fixtures and configuration for unit, integration, and e2e tests"""

import io
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
import redis
import structlog
from click.testing import CliRunner
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tenacity import Retrying, retry, stop_after_delay
from werkzeug.security import generate_password_hash

from opendlp.adapters import database, orm
from opendlp.config import PostgresCfg, RedisCfg, get_api_url
from opendlp.feature_flags import reload_flags
from opendlp.logging import pre_chain
from opendlp.service_layer import security, totp_service

# the plugins have to be defined at the top level, even though they only apply to the BDD tests.
# https://daobook.github.io/pytest/how-to/writing_plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = [
    "tests.bdd.shared.ui_shared",
    "tests.bdd.shared.email_confirmation_steps",
]

# Directories whose tests run against real infrastructure. The infra markers are
# applied automatically by directory (pytest_collection_modifyitems) so that
# `pytest -m "not requires_db"` runs the fast tier (unit + component) without
# editing every test file.
_REQUIRES_DB_DIRS = ("/tests/e2e/", "/tests/integration/", "/tests/contract/", "/tests/bdd/")
_REQUIRES_REDIS_DIRS = ("/tests/e2e/", "/tests/bdd/")

# A disguised route test patches a blueprint's UnitOfWork seam to fake out a
# route while driving the Flask app. Such tests belong in tests/component/ on the
# real fake-backed seam, not in tests/unit/.
_DISGUISED_ROUTE_TEST = re.compile(r"blueprints\.[\w.]*get_flask_uow")


def pytest_collection_modifyitems(config, items):
    """Auto-apply infra markers by directory and enforce test placement."""
    placement_errors = []
    source_cache: dict[str, str] = {}
    for item in items:
        path = str(item.path)
        if any(directory in path for directory in _REQUIRES_DB_DIRS):
            item.add_marker(pytest.mark.requires_db)
        if any(directory in path for directory in _REQUIRES_REDIS_DIRS):
            item.add_marker(pytest.mark.requires_redis)

        if "/tests/unit/" in path:
            source = source_cache.get(path)
            if source is None:
                source = item.path.read_text()
                source_cache[path] = source
            if _DISGUISED_ROUTE_TEST.search(source):
                placement_errors.append(
                    f"{path}: patches a blueprint's get_flask_uow — this is a disguised route "
                    "test and belongs in tests/component/, not tests/unit/"
                )
        if "/tests/component/" in path and item.get_closest_marker("db_semantics"):
            placement_errors.append(
                f"{path}: marked db_semantics but lives in tests/component/ — db_semantics tests "
                "exercise the real database and must live in tests/e2e/ or tests/integration/"
            )

    if placement_errors:
        raise pytest.UsageError("Test placement errors:\n" + "\n".join(sorted(set(placement_errors))))


@pytest.fixture(autouse=True)
def reset_logging_handlers():
    """Reset sortition_algorithms logging handlers to avoid database writes in unit tests.

    This prevents SelectionRunRecordHandler from persisting across tests when it's
    set up by Celery tasks that call _set_up_celery_logging().
    """
    # Get the sortition_algorithms user logger
    user_logger = logging.getLogger("sortition_algorithms_user")
    # Store original handlers
    original_handlers = user_logger.handlers.copy()
    # Clear handlers to prevent SelectionRunRecordHandler from being used
    user_logger.handlers.clear()
    user_logger.addHandler(logging.NullHandler())
    yield
    # Restore original handlers
    user_logger.handlers = original_handlers


@pytest.fixture(autouse=True)
def set_test_env():
    """Automatically set test environment for all tests."""
    original_env = os.environ.get("FLASK_ENV")
    os.environ["FLASK_ENV"] = "testing"
    # Keep the legacy /dashboard available for tests that still target it.
    # Individual tests that exercise the new default can override these via
    # monkeypatch and reload_flags().
    ff_defaults = {
        "FF_OLD_DEFAULT_DASHBOARD": "true",
        "FF_DASHBOARD_SWITCH_LINKS": "true",
    }
    original_ffs = {key: os.environ.get(key) for key in ff_defaults}
    for key, value in ff_defaults.items():
        os.environ.setdefault(key, value)
    reload_flags()
    yield
    if original_env is not None:  # pragma: no cover
        os.environ["FLASK_ENV"] = original_env
    else:
        os.environ.pop("FLASK_ENV", None)
    for key, original_value in original_ffs.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:  # pragma: no cover
            os.environ[key] = original_value
    reload_flags()


@pytest.fixture
def clear_env_vars():
    """Fixture to temporarily set environment variables for testing."""
    original_vars = {}

    def _set_env_vars(*args):
        for key in args:
            original_vars[key] = os.environ.get(key)
            os.environ.pop(key, None)

    yield _set_env_vars

    # Restore original environment variables
    for key, value in original_vars.items():
        if value is not None:  # pragma: no cover
            os.environ[key] = value


@pytest.fixture
def temp_env_vars():
    """Fixture to temporarily set environment variables for testing."""
    original_vars = {}

    def _set_env_vars(**kwargs):
        for key, value in kwargs.items():
            original_vars[key] = os.environ.get(key)
            os.environ[key] = value

    yield _set_env_vars

    # Restore original environment variables
    for key, value in original_vars.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


@pytest.fixture
def cli_with_session_factory(postgres_session_factory):
    """Fixture that provides a Click runner with test session factory in context."""

    def _invoke_cli_with_context(cli_command, args):
        """Helper to invoke CLI commands with test session factory in context."""
        runner = CliRunner()

        # Create context object with our test session factory
        ctx_obj = {"session_factory": postgres_session_factory}

        # Invoke with the context object
        return runner.invoke(cli_command, args, obj=ctx_obj)

    return _invoke_cli_with_context


def _get_worker_db_name(worker_id: str) -> str:
    """Return a database name unique to each xdist worker."""
    if worker_id == "master":
        return "opendlp"  # not running under xdist
    return f"opendlp_test_{worker_id}"  # e.g. opendlp_test_gw0


@pytest.fixture(scope="session")
def _worker_database(worker_id):
    """Create a per-worker database for xdist parallel execution."""
    db_name = _get_worker_db_name(worker_id)
    if db_name == "opendlp":
        yield db_name
        return

    # Connect to the default 'opendlp' database to issue CREATE DATABASE
    admin_cfg = PostgresCfg.from_env()
    admin_cfg.port = 54322
    admin_engine = create_engine(
        admin_cfg.to_url(),
        isolation_level="AUTOCOMMIT",  # CREATE DATABASE can't run inside a transaction
    )
    with admin_engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        )
        if not result.fetchone():
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    yield db_name

    # Teardown: drop the worker database
    admin_engine = create_engine(
        admin_cfg.to_url(),
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as conn:
        # db_name is safe: only values from _get_worker_db_name (opendlp_test_gw<N>)
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "  # noqa: S608
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def worker_db_url(_worker_database):
    """Full PostgreSQL URL for this worker's database."""
    postgres_cfg = PostgresCfg.from_env()
    postgres_cfg.port = 54322
    postgres_cfg.db_name = _worker_database
    return postgres_cfg.to_url()


@pytest.fixture(scope="session")
def postgres_engine(_worker_database):
    """Create a test database engine using PostgreSQL."""
    postgres_cfg = PostgresCfg.from_env()
    postgres_cfg.port = 54322
    postgres_cfg.db_name = _worker_database
    engine = create_engine(
        postgres_cfg.to_url(),
        echo=False,
        isolation_level="SERIALIZABLE",
        pool_size=2,
        max_overflow=3,
    )
    wait_for_postgres_to_come_up(engine)

    yield engine

    engine.dispose()


@pytest.fixture(scope="session")
def _postgres_tables(postgres_engine):
    """Create tables once for the entire test session."""
    orm.metadata.create_all(postgres_engine)
    database.start_mappers()
    yield
    database.clear_mappers()
    orm.metadata.drop_all(postgres_engine)


def _delete_all_test_data(session_factory):
    """Delete all data from all tables, respecting foreign key constraints.

    When adding a new table to the ORM, add a corresponding delete statement
    here. Tables must be deleted in dependency order: child tables before
    parent tables, so that foreign key constraints are satisfied.
    """
    session = session_factory()
    try:
        # Child tables (no other table references these)
        session.execute(orm.totp_verification_attempts.delete())
        session.execute(orm.two_factor_audit_log.delete())
        session.execute(orm.user_backup_codes.delete())
        session.execute(orm.email_confirmation_tokens.delete())
        session.execute(orm.password_reset_tokens.delete())
        session.execute(orm.selection_run_records.delete())
        session.execute(orm.respondent_email_send_records.delete())
        session.execute(orm.respondents.delete())
        session.execute(orm.respondent_field_definitions.delete())
        session.execute(orm.registration_images.delete())
        session.execute(orm.registration_page_html_sources.delete())
        session.execute(orm.registration_pages.delete())
        session.execute(orm.email_templates.delete())
        session.execute(orm.target_categories.delete())
        session.execute(orm.assembly_gsheets.delete())
        session.execute(orm.assembly_csv.delete())
        session.execute(orm.selection_settings.delete())
        session.execute(orm.user_invites.delete())
        session.execute(orm.user_assembly_roles.delete())
        # Parent tables (referenced by child tables above)
        session.execute(orm.assemblies.delete())
        session.execute(orm.users.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture
def postgres_session_factory(postgres_engine, _postgres_tables):
    """Provide a session factory, cleaning up all data after each test."""
    session_factory = sessionmaker(bind=postgres_engine)
    yield session_factory
    _delete_all_test_data(session_factory)


@pytest.fixture
def postgres_session(postgres_session_factory):
    """Create a test database session."""
    session = postgres_session_factory()

    yield session

    session.rollback()
    session.close()


@pytest.fixture
def restart_api():
    (Path(__file__).parent / "../src/allocation/entrypoints/flask_app.py").touch()
    time.sleep(0.5)
    wait_for_webapp_to_come_up()


@pytest.fixture
def restart_redis_pubsub():
    wait_for_redis_to_come_up()
    if not shutil.which("docker"):
        print("skipping restar, assumes running in container")
        return
    subprocess.run(
        ["docker", "compose", "restart", "-t", "0", "redis_pubsub"],
        check=True,
    )


@retry(stop=stop_after_delay(10))
def wait_for_postgres_to_come_up(engine):
    return engine.connect()


@retry(stop=stop_after_delay(10))
def wait_for_webapp_to_come_up():
    return urllib.request.urlopen(get_api_url()).read()  # noqa: S310


@retry(stop=stop_after_delay(10))
def wait_for_webapp_to_come_up_on_port(port: int = 5002, timeout: int = 10):
    for attempt in Retrying(stop=stop_after_delay(timeout)):
        with attempt:
            return urllib.request.urlopen(f"http://localhost:{port}").read()
    return None


@retry(stop=stop_after_delay(10))
def wait_for_redis_to_come_up():
    r = redis.Redis(RedisCfg.from_env().to_url())
    return r.ping()


def wait_for_celery_worker_to_come_up(celery_app, timeout: int = 10) -> bool:
    """Check if Celery worker is ready to accept tasks."""
    for attempt in Retrying(stop=stop_after_delay(timeout)):
        with attempt:
            inspect = celery_app.control.inspect()
            active_nodes = inspect.ping()

            if not active_nodes:
                raise Exception("No active Celery workers found")

            return True
    return False


@pytest.fixture(autouse=True)
def patch_password_hashing(monkeypatch):
    """Proper password hashing is slow - let's do a much quicker password hashing in tests"""

    def mock_generate(password):
        # this means we only use 1 iteration of sha256, rather than the default
        # 1 million. Should make things faster
        return generate_password_hash(password, method="pbkdf2:sha256:1")

    monkeypatch.setattr(security, "generate_password_hash", mock_generate)
    monkeypatch.setattr(totp_service, "generate_password_hash", mock_generate)


def _get_worker_redis_db(worker_id: str) -> int:
    """Return a Redis database number unique to each xdist worker.

    Redis supports databases 0-15. Database 0 is used by Celery, so we
    start worker databases from 1. Without xdist (worker_id == "master")
    we use database 1.
    """
    if worker_id == "master":
        return 1
    # worker_id is like "gw0", "gw1", etc — extract the number and offset by 1
    worker_num = int(worker_id.replace("gw", ""))
    db = worker_num + 1
    if db > 15:
        raise ValueError(f"Too many xdist workers for Redis databases (max 15): {worker_id}")
    return db


@pytest.fixture(scope="session")
def test_redis_client(worker_id):
    """Provide a per-worker Redis client using separate Redis databases.

    Each xdist worker gets its own Redis database (1-15) to avoid
    interference between parallel test runs. Database 0 is reserved
    for Celery.
    """
    db = _get_worker_redis_db(worker_id)
    r = redis.Redis(host="localhost", port=63792, db=db, decode_responses=True)
    r.flushdb()
    yield r
    r.flushdb()


@pytest.fixture
def capture_json_handler():
    """Attach a JSON ProcessorFormatter handler wired exactly like logging.py.

    Yields the StringIO buffer the rendered log lines are written to, then
    removes the temporary handler again. Uses the real foreign_pre_chain from
    logging.py so redaction wiring is genuinely exercised. Needed because
    caplog does not capture structlog-rendered output.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=pre_chain,
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
