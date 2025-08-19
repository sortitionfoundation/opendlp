"""ABOUTME: Pytest configuration and fixtures for OpenDLP tests
ABOUTME: Provides test fixtures and configuration for unit, integration, and e2e tests"""

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
from tenacity import retry, stop_after_delay

from opendlp.adapters import database, orm
from opendlp.config import FlaskTestConfig, PostgresCfg, RedisCfg, get_api_url, get_config


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration for the entire test session."""
    # Ensure we're using test configuration
    os.environ["FLASK_ENV"] = "testing"
    return FlaskTestConfig()


@pytest.fixture(scope="function")
def config():
    """Provide configuration for individual test functions."""
    return get_config()


@pytest.fixture(autouse=True)
def set_test_env():
    """Automatically set test environment for all tests."""
    original_env = os.environ.get("FLASK_ENV")
    os.environ["FLASK_ENV"] = "testing"
    yield
    if original_env is not None:
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
        if value is not None:
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
def mappers():
    database.start_mappers()
    yield
    database.clear_mappers()


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
        ["docker", "compose", "restart", "-t", "0", "redis_pubsub"],  # noqa: S607
        check=True,
    )


@retry(stop=stop_after_delay(10))
def wait_for_postgres_to_come_up(engine):
    return engine.connect()


@retry(stop=stop_after_delay(10))
def wait_for_webapp_to_come_up():
    return urllib.request.urlopen(get_api_url()).read()  # noqa: S310


@retry(stop=stop_after_delay(10))
def wait_for_redis_to_come_up():
    r = redis.Redis(RedisCfg.from_env().to_url())
    return r.ping()
