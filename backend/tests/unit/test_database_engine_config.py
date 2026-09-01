"""ABOUTME: Unit tests for SQLAlchemy engine configuration in create_session_factory
ABOUTME: Locks in the timeouts and keepalives that stop database waits hanging workers"""

from unittest.mock import MagicMock

import pytest

from opendlp.adapters import database


@pytest.fixture
def captured_engine_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    def fake_create_engine(url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured.update(kwargs)
        return MagicMock(name="engine")

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    return captured


class TestPostgresEngineConfig:
    def test_pool_is_bounded_and_fails_fast(self, captured_engine_kwargs: dict) -> None:
        database.create_session_factory("postgresql://user:pw@example/db")  # pragma: allowlist secret

        assert captured_engine_kwargs["pool_pre_ping"] is True
        assert captured_engine_kwargs["pool_size"] == 3
        assert captured_engine_kwargs["max_overflow"] == 7
        # Must stay below the gunicorn worker timeout so pool starvation
        # surfaces as a logged error, not a killed worker.
        assert captured_engine_kwargs["pool_timeout"] <= 10

    def test_connections_carry_timeouts_and_keepalives(self, captured_engine_kwargs: dict) -> None:
        database.create_session_factory("postgresql://user:pw@example/db")  # pragma: allowlist secret

        connect_args = captured_engine_kwargs["connect_args"]
        assert connect_args["connect_timeout"] <= 10
        assert connect_args["keepalives"] == 1
        options = connect_args["options"]
        assert "statement_timeout=30000" in options
        assert "lock_timeout=10000" in options
        assert "idle_in_transaction_session_timeout=300000" in options

    def test_non_postgres_url_gets_no_postgres_args(self, captured_engine_kwargs: dict) -> None:
        database.create_session_factory("sqlite://")

        assert "connect_args" not in captured_engine_kwargs
        assert "pool_size" not in captured_engine_kwargs
