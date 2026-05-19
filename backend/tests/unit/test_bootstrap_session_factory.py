"""ABOUTME: Unit tests for bootstrap_session_factory engine memoization
ABOUTME: Verifies engines are cached per URI and disposed correctly post-fork"""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from opendlp import bootstrap


@pytest.fixture(autouse=True)
def reset_session_factory_cache() -> Iterator[None]:
    """Ensure each test starts with an empty cache and leaves it empty."""
    bootstrap._session_factory_cache.clear()
    yield
    bootstrap._session_factory_cache.clear()


class TestBootstrapSessionFactory:
    def test_repeated_calls_return_same_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The same db_uri must reuse the same engine instead of creating new ones."""
        monkeypatch.setattr(bootstrap, "get_db_uri", lambda: "postgresql://example/db")

        created_engines: list[MagicMock] = []

        def fake_create(db_uri: str) -> sessionmaker:
            engine = MagicMock(name=f"engine_for_{db_uri}")
            created_engines.append(engine)
            return sessionmaker(bind=engine)

        monkeypatch.setattr(bootstrap.database, "create_session_factory", fake_create)
        monkeypatch.setattr(bootstrap.database, "start_mappers", lambda: None)

        factory_a = bootstrap.bootstrap_session_factory()
        factory_b = bootstrap.bootstrap_session_factory()

        assert factory_a is factory_b
        assert len(created_engines) == 1

    def test_different_db_uri_produces_different_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A different URI must create its own engine (supports test DB URI overrides)."""
        uris = iter(["postgresql://one/db", "postgresql://two/db"])
        monkeypatch.setattr(bootstrap, "get_db_uri", lambda: next(uris))

        created_engines: list[MagicMock] = []

        def fake_create(db_uri: str) -> sessionmaker:
            engine = MagicMock(name=f"engine_for_{db_uri}")
            created_engines.append(engine)
            return sessionmaker(bind=engine)

        monkeypatch.setattr(bootstrap.database, "create_session_factory", fake_create)
        monkeypatch.setattr(bootstrap.database, "start_mappers", lambda: None)

        factory_a = bootstrap.bootstrap_session_factory()
        factory_b = bootstrap.bootstrap_session_factory()

        assert factory_a is not factory_b
        assert len(created_engines) == 2

    def test_explicit_session_factory_bypasses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicitly supplied session_factory must be returned untouched and not cached."""
        monkeypatch.setattr(bootstrap, "get_db_uri", lambda: "postgresql://example/db")

        def fail_create(db_uri: str) -> sessionmaker:
            pytest.fail("create_session_factory should not be called when session_factory is supplied")

        monkeypatch.setattr(bootstrap.database, "create_session_factory", fail_create)
        monkeypatch.setattr(bootstrap.database, "start_mappers", lambda: None)

        supplied = sessionmaker(bind=MagicMock())
        returned = bootstrap.bootstrap_session_factory(session_factory=supplied)

        assert returned is supplied
        assert bootstrap._session_factory_cache == {}

    def test_dispose_cached_engines_disposes_and_clears(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dispose_cached_engines must call engine.dispose() and empty the cache."""
        monkeypatch.setattr(bootstrap, "get_db_uri", lambda: "postgresql://example/db")

        engines: list[MagicMock] = []

        def fake_create(db_uri: str) -> sessionmaker:
            engine = MagicMock(name=f"engine_for_{db_uri}")
            engines.append(engine)
            return sessionmaker(bind=engine)

        monkeypatch.setattr(bootstrap.database, "create_session_factory", fake_create)
        monkeypatch.setattr(bootstrap.database, "start_mappers", lambda: None)

        bootstrap.bootstrap_session_factory()
        assert len(engines) == 1

        bootstrap.dispose_cached_engines()

        engines[0].dispose.assert_called_once()
        assert bootstrap._session_factory_cache == {}

        # Subsequent call rebuilds the engine instead of returning a disposed one.
        bootstrap.bootstrap_session_factory()
        assert len(engines) == 2
