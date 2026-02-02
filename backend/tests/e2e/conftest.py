from datetime import UTC, datetime, timedelta

import pytest

from opendlp.adapters.database import start_mappers
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def app(temp_env_vars):
    """Create test Flask application."""
    temp_env_vars(DB_URI="postgresql://opendlp:abc123@localhost:54322/opendlp")  # pragma: allowlist secret
    start_mappers()  # Initialize SQLAlchemy mappings
    app = create_app("testing_postgres")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def admin_user(postgres_session_factory):
    """Create an admin user for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin, _ = create_user(
            uow=uow,
            email="admin@example.com",
            password="adminpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="Admin",
            global_role=GlobalRole.ADMIN,
            accept_data_agreement=True,
        )

    # Confirm email so user can log in
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = uow.users.get(admin.id)
        user.confirm_email()
        uow.commit()
        return user.create_detached_copy()


@pytest.fixture
def regular_user(postgres_session_factory):
    """Create a regular user for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user, _ = create_user(
            uow=uow,
            email="user@example.com",
            password="userpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )

    # Confirm email so user can log in
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


@pytest.fixture
def logged_in_admin(client, admin_user):
    """Helper to login as admin user."""
    client.post(
        "/auth/login",
        data={
            "email": admin_user.email,
            "password": "adminpass123",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/auth/login"),
        },
    )
    return client


@pytest.fixture
def logged_in_user(client, regular_user):
    """Helper to login as regular user."""
    client.post(
        "/auth/login",
        data={
            "email": regular_user.email,
            "password": "userpass123",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/auth/login"),
        },
    )
    return client


@pytest.fixture
def existing_assembly(postgres_session_factory, admin_user):
    """Create an existing assembly for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Existing Assembly",
            created_by_user_id=admin_user.id,
            question="What is the existing question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        return assembly.create_detached_copy()


@pytest.fixture
def assembly_with_gsheet(postgres_session_factory, admin_user):
    """Create an assembly with existing gsheet configuration."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with GSheet",
            created_by_user_id=admin_user.id,
            question="What should we configure?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=22,
        )
        detached_assembly = assembly.create_detached_copy()

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        gsheet = add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit",
            team="uk",
            select_registrants_tab="TestRespondents",
            select_targets_tab="TestCategories",
            id_column="test_id_column",
            check_same_address=True,
            generate_remaining_tab=False,
        )
        detached_gsheet = gsheet.create_detached_copy()
    return detached_assembly, detached_gsheet
