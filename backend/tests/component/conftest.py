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
from tests.conftest import restore_flask_app_state
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


@pytest.fixture(autouse=True)
def _mock_login_rate_limit_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent login rate limiting from connecting to Redis in component tests.

    The same seam as the registration limiter, on the other Redis-backed rate
    limit. Any component test that posts to /auth/login reaches it twice: once
    checking the counters on the way in, and again recording the attempt on the
    way out if the credentials were rejected.
    """
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # no counter = not rate-limited
    monkeypatch.setattr(
        "opendlp.service_layer.login_rate_limit_service._get_redis",
        lambda: mock_redis,
    )


class _InMemoryRedis:
    """The slice of the Redis API the CSV upload stash uses, backed by a dict.

    A MagicMock won't do here: the diff-confirmation flow stashes an upload on
    one request and reads it back on the next, so the stub has to remember what
    it was given. The TTL is ignored - nothing expires within a test.
    """

    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}

    def set(self, key: str, value: str | bytes, ex: int | None = None) -> None:
        self._values[key] = value.encode("utf-8") if isinstance(value, str) else value

    def get(self, key: str) -> bytes | None:
        return self._values.get(key)

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


@pytest.fixture(autouse=True)
def _in_memory_csv_upload_stash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Back the pending-CSV stash with a dict for every component test.

    Component tests have no Redis, but the upload-then-confirm-diff flow needs
    the stash to hold the CSV across two requests. Each test gets its own store.
    """
    fake_redis = _InMemoryRedis()
    monkeypatch.setattr(
        "opendlp.service_layer.csv_upload_stash._get_redis",
        lambda: fake_redis,
    )


@pytest.fixture
def fake_store():
    """A single in-memory store shared by every UnitOfWork in a test."""
    return FakeStore()


@pytest.fixture
def shared_uow(fake_store):
    """An already-entered UnitOfWork over the same store the Flask app is wired to.

    Strict, so it behaves like the real UnitOfWork the routes use.
    """
    with FakeUnitOfWork(store=fake_store) as entered:
        yield entered


@pytest.fixture(scope="session")
def _component_app_and_store_holder():
    """One Flask app shared by every component test in the session.

    create_app() is expensive (werkzeug compiles every URL rule again for each
    new app), so the app is built once per pytest worker. Routes resolve
    get_flask_uow() at request time, so the factory registered here reads the
    current test's FakeStore out of the holder — the `app` fixture below swaps
    it for each test.
    """
    holder: dict[str, FakeStore] = {}
    app = create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=holder["store"]))
    return app, holder


@pytest.fixture
def app(_component_app_and_store_holder, fake_store):
    """Flask app whose UnitOfWork factory is backed by the shared FakeStore.

    No PostgreSQL and no Redis: routes resolve get_flask_uow() to a
    FakeUnitOfWork over fake_store, and sessions use an in-memory cachelib cache.

    The Flask app instance is shared across tests; only the store is per-test.
    A test that needs a differently *constructed* app overrides this fixture
    (see test_oauth_flow.py); a test that only needs different app *config* can
    assign to app.config — the autouse guard below restores it between tests.
    """
    app, holder = _component_app_and_store_holder
    holder["store"] = fake_store
    yield app
    # Empty the holder so a request served outside any test that set up a store
    # fails loudly on the missing key rather than silently reading stale data.
    holder.pop("store", None)


@pytest.fixture(autouse=True)
def _restore_shared_app_state(_component_app_and_store_holder):
    """Undo app.config / extension mutations a test makes on the shared app.

    The app outlives each test, so mutations would leak into every later test
    in the worker (e.g. a test flipping WTF_CSRF_ENABLED would 400 every later
    POST). Deliberately depends on the session app, not `app`: a module's own
    `app` override is per-test (mutations die with it, no guard needed), and
    depending on `app` here would instantiate that override before the
    module's other autouse fixtures, upsetting their ordering.
    """
    shared_app, _ = _component_app_and_store_holder
    with restore_flask_app_state(shared_app):
        yield


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
