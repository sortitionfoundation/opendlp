"""ABOUTME: Pytest configuration and fixtures for OpenDLP tests
ABOUTME: Provides test fixtures and configuration for unit, integration, and e2e tests"""

import logging
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
import redis
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tenacity import Retrying, retry, stop_after_delay
from werkzeug.security import generate_password_hash

from opendlp.adapters import database, orm
from opendlp.config import PostgresCfg, RedisCfg, get_api_url
from opendlp.service_layer import security

# the plugins have to be defined at the top level, even though they only apply to the BDD tests.
# https://daobook.github.io/pytest/how-to/writing_plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = [
    "tests.bdd.shared.ui_shared",
    "tests.bdd.shared.email_confirmation_steps",
]


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
    yield
    if original_env is not None:  # pragma: no cover
        os.environ["FLASK_ENV"] = original_env
    else:
        os.environ.pop("FLASK_ENV", None)


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
def in_memory_sqlite_db():
    engine = create_engine("sqlite:///:memory:")
    return engine


@pytest.fixture
def sqlite_session_factory(in_memory_sqlite_db):
    orm.metadata.create_all(in_memory_sqlite_db)
    database.start_mappers()

    yield sessionmaker(bind=in_memory_sqlite_db)

    database.clear_mappers()
    orm.metadata.drop_all(in_memory_sqlite_db)


@pytest.fixture
def cli_with_session_factory(sqlite_session_factory):
    """Fixture that provides a Click runner with test session factory in context."""

    def _invoke_cli_with_context(cli_command, args):
        """Helper to invoke CLI commands with test session factory in context."""
        runner = CliRunner()

        # Create context object with our test session factory
        ctx_obj = {"session_factory": sqlite_session_factory}

        # Invoke with the context object
        return runner.invoke(cli_command, args, obj=ctx_obj)

    return _invoke_cli_with_context


@pytest.fixture(scope="session")
def postgres_engine():
    """Create a test database engine using PostgreSQL."""
    postgres_cfg = PostgresCfg.from_env()
    postgres_cfg.port = 54322
    engine = create_engine(postgres_cfg.to_url(), echo=False, isolation_level="SERIALIZABLE")
    wait_for_postgres_to_come_up(engine)

    yield engine

    engine.dispose()


@pytest.fixture
def postgres_session_factory(postgres_engine):
    orm.metadata.create_all(postgres_engine)
    database.start_mappers()

    session_factory = sessionmaker(bind=postgres_engine)
    yield session_factory

    database.clear_mappers()
    orm.metadata.drop_all(postgres_engine)


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
    subprocess.run(  # noqa: S603
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
