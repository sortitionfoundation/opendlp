"""ABOUTME: Fixtures for the fake-backed e2e pilot (Phase 2 of the B2 plan)
ABOUTME: Overrides app + data fixtures to run e2e tests against a shared in-memory FakeStore (no PostgreSQL)"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.celery.app import reset_celery_app
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def fake_store():
    """A single in-memory store shared by every UnitOfWork in a test."""
    return FakeStore()


@pytest.fixture
def app(temp_env_vars, fake_store, test_redis_client):
    """Flask app whose UnitOfWork factory is backed by the shared FakeStore.

    No PostgreSQL is involved: routes resolve get_flask_uow() to a
    FakeUnitOfWork over fake_store. Redis is still used for login rate limiting,
    exactly as in the PostgreSQL e2e app.
    """
    temp_env_vars(
        REDIS_PORT="63792",
        REDIS_DB=str(test_redis_client.connection_pool.connection_kwargs["db"]),
    )
    reset_celery_app()
    return create_app("testing", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def admin_user(fake_store):
    """Create an admin user in the shared store (mirrors the PostgreSQL fixture)."""
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
    """Create a regular user in the shared store (mirrors the PostgreSQL fixture)."""
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
def existing_assembly(fake_store, admin_user):
    """Create an assembly in the shared store (mirrors the PostgreSQL fixture)."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Existing Assembly",
            created_by_user_id=admin_user.id,
            question="What is the existing question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        return assembly.create_detached_copy()
