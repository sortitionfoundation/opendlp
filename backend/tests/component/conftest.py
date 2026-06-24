"""ABOUTME: Shared fixtures for component tests (Flask app over a FakeUnitOfWork)
ABOUTME: Builds a fake-backed app with in-memory sessions and seeds data through a shared FakeStore — no PostgreSQL, no Redis"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer import sortition
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


class _NoCeleryResult:
    """Stub for a Celery AsyncResult when no result backend is present.

    The component tier has no broker/result backend, so the selection-status
    code path treats every task as "no live Celery result" and relies on the
    seeded SelectionRunRecord (the authoritative source) instead.
    """

    id = None
    state = "PENDING"

    def successful(self) -> bool:
        return False

    def failed(self) -> bool:
        return False

    def ready(self) -> bool:
        return False


@pytest.fixture(autouse=True)
def stub_celery_async_result(monkeypatch):
    """Stub the Celery result-backend boundary for every component test.

    Mirrors the no-PostgreSQL/no-Redis seams: the Celery result backend is an
    external boundary the component tier does not run, so AsyncResult is
    replaced with an inert stub. This keeps the progress/status routes driven
    by the seeded SelectionRunRecord and avoids dangling AsyncResult objects.
    """
    monkeypatch.setattr(sortition.app.app, "AsyncResult", lambda *args, **kwargs: _NoCeleryResult())


@pytest.fixture(autouse=True)
def _mock_registration_rate_limit_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent rate limiting service from connecting to Redis in component tests.

    Component tests have no Redis. This stubs _get_redis so the service always
    reports no prior activity (counters at zero) and writes are no-ops.
    """
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # no counter = not rate-limited
    mock_pipeline = MagicMock()
    mock_redis.pipeline.return_value = mock_pipeline
    monkeypatch.setattr(
        "opendlp.service_layer.registration_bot_protection_service._get_redis",
        lambda: mock_redis,
    )


@pytest.fixture
def fake_store():
    """A single in-memory store shared by every UnitOfWork in a test."""
    return FakeStore()


@pytest.fixture
def app(fake_store):
    """Flask app whose UnitOfWork factory is backed by the shared FakeStore.

    No PostgreSQL and no Redis: routes resolve get_flask_uow() to a
    FakeUnitOfWork over fake_store, and sessions use an in-memory cachelib cache.
    """
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def client(app):
    """Test client for the fake-backed app."""
    return app.test_client()


def _login(client: FlaskClient, user: User) -> FlaskClient:
    """Log a user in by writing the Flask-Login session directly (no auth round trip)."""
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()
        session["_fresh"] = True
    return client


@pytest.fixture
def admin_user(fake_store):
    """Create a confirmed admin user in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        admin, _ = create_user(
            uow=uow,
            email="admin@example.com",
            password="adminpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="Admin",
            global_role=GlobalRole.ADMIN,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user = uow.users.get(admin.id)
        user.confirm_email()
        uow.commit()
        return user.create_detached_copy()


@pytest.fixture
def regular_user(fake_store):
    """Create a confirmed regular user in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email="user@example.com",
            password="userpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


@pytest.fixture
def logged_in_admin(client, admin_user):
    """Client logged in as the admin user."""
    return _login(client, admin_user)


@pytest.fixture
def logged_in_user(client, regular_user):
    """Client logged in as the regular user."""
    return _login(client, regular_user)


@pytest.fixture
def existing_assembly(fake_store, admin_user):
    """Create an assembly in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Existing Assembly",
            created_by_user_id=admin_user.id,
            question="What is the existing question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        return assembly.create_detached_copy()
