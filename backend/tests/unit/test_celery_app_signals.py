"""ABOUTME: Unit tests for Celery worker_process_init signal handler
ABOUTME: Verifies post-fork hook disposes SQLAlchemy engines inherited from parent"""

import pytest
from celery.signals import worker_process_init

from opendlp import bootstrap
from opendlp.entrypoints.celery import app as celery_app_module


class TestResetDbConnectionsAfterFork:
    def test_handler_calls_dispose_cached_engines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Direct invocation of the handler must dispose cached engines."""
        called: list[bool] = []

        def fake_dispose() -> None:
            called.append(True)

        monkeypatch.setattr(bootstrap, "dispose_cached_engines", fake_dispose)

        celery_app_module.reset_db_connections_after_fork()

        assert called == [True]

    def test_handler_is_wired_to_worker_process_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sending the worker_process_init signal must trigger our handler."""
        called: list[bool] = []

        def fake_dispose() -> None:
            called.append(True)

        monkeypatch.setattr(bootstrap, "dispose_cached_engines", fake_dispose)

        worker_process_init.send(sender=None)

        assert called, "worker_process_init signal did not invoke the connected handler"


class TestRedisTransportTimeouts:
    """Broker and result-backend socket operations must be bounded.

    Celery's defaults (120s socket_timeout, unbounded connect) can hold a
    gunicorn worker far past its own timeout when Redis stalls.
    """

    def test_broker_and_backend_transport_options_bound_socket_operations(self) -> None:
        for options in (
            celery_app_module.app.conf.broker_transport_options,
            celery_app_module.app.conf.result_backend_transport_options,
        ):
            assert options["socket_timeout"] <= 10
            assert options["socket_connect_timeout"] <= 5
