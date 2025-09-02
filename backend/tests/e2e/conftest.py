import pytest

from opendlp.adapters.database import start_mappers
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user


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
        admin = create_user(
            uow=uow,
            email="admin@example.com",
            password="adminpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="Admin",
            global_role=GlobalRole.ADMIN,
            accept_data_agreement=True,
        )
        return admin.create_detached_copy()


@pytest.fixture
def regular_user(postgres_session_factory):
    """Create a regular user for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email="user@example.com",
            password="userpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()
