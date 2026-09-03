"""ABOUTME: Shared fixtures for component tests (Flask app over a FakeUnitOfWork)
ABOUTME: Builds a fake-backed app with in-memory sessions and seeds data through a shared FakeStore — no PostgreSQL, no Redis"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from flask.testing import FlaskClient
from flask_babel import format_datetime

from opendlp.domain.assembly import Assembly
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
def organiser_user(fake_store):
    """Create a confirmed organiser in the shared store, holding no assembly roles."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email="organiser@example.com",
            password="uncommon-passphrase-42",  # pragma: allowlist secret
            first_name="Test",
            last_name="Organiser",
            global_role=GlobalRole.ORGANISER,
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
def logged_in_organiser(client, organiser_user):
    """Client logged in as an organiser with no assembly roles."""
    return _login(client, organiser_user)


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


@pytest.fixture
def assembly_without_a_creator(fake_store):
    """An assembly with nobody recorded as its creator.

    Both an assembly created before we recorded the creator, and one whose
    creator has since been deleted - the foreign key is SET NULL, so the two
    are indistinguishable by the time a template sees them.
    """
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = Assembly(
            title="Orphan Assembly",
            question="Who made this?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        uow.assemblies.add(assembly)
        uow.commit()
        return assembly.create_detached_copy()


def expected_timestamp(app, moment: datetime) -> str:
    """Render a datetime the way the templates do, so tests do not hardcode a locale's format."""
    with app.test_request_context():
        return format_datetime(moment, "long")
