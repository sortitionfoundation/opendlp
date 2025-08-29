import os
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from opendlp.adapters import database, orm
from opendlp.config import PostgresCfg
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.conftest import wait_for_postgres_to_come_up, wait_for_webapp_to_come_up_on_port

from .config import ADMIN_EMAIL, ADMIN_PASSWORD, BDD_PORT, Urls


@pytest.fixture(scope="session")
def test_database():
    """Set up test database with proper configuration"""
    # Ensure test environment
    os.environ["FLASK_ENV"] = "testing_postgres"

    # Use test postgres config (port 54322)
    postgres_cfg = PostgresCfg.from_env()
    postgres_cfg.port = 54322

    engine = create_engine(postgres_cfg.to_url(), echo=False)
    wait_for_postgres_to_come_up(engine)

    # Create tables
    orm.metadata.create_all(engine)
    database.start_mappers()

    session_factory = sessionmaker(bind=engine)

    yield session_factory

    # Cleanup
    database.clear_mappers()
    orm.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def test_server(test_database):
    """Start Flask test server in background"""
    # Check if server is already running
    try:
        wait_for_webapp_to_come_up_on_port(BDD_PORT)
        print("Test server already running, using existing instance")
        yield
        return
    except Exception:
        print("Starting test server...")

    # Start server in background
    backend_path = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    env["FLASK_ENV"] = "testing_postgres"
    env["DB_PORT"] = "54322"
    env["FLASK_APP"] = "src/opendlp/entrypoints/flask_app.py"

    process = subprocess.Popen(  # noqa: S603
        ["uv", "run", "flask", "run", f"--port={BDD_PORT}", "--host=127.0.0.1"],
        cwd=backend_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    wait_for_webapp_to_come_up_on_port(BDD_PORT)
    print("Test server started successfully")

    yield

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    print("Test server stopped")


@pytest.fixture(scope="session")
def admin_user(test_database):
    """Create admin user for testing"""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    # Create admin user
    admin = create_user(
        uow=uow,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        first_name="Test",
        last_name="Admin",
        global_role=GlobalRole.ADMIN,
        accept_data_agreement=True,
    )

    return admin


@pytest.fixture(scope="session")
def browser():
    """Browser instance for all tests"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("CI", "false").lower() == "true")
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def context(browser, test_server):
    """Browser context that waits for server to be ready"""
    context = browser.new_context()
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context):
    """Fresh page for each test"""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture
def logged_out_page(page: Page, admin_user, clean_database):
    # Clear any existing session/cookies to ensure clean state
    page.context.clear_cookies()
    return page


@pytest.fixture
def logged_in_page(page: Page, admin_user, clean_database):
    """Page with admin user logged in"""
    page.goto(Urls.login)
    page.fill('input[name="email"]', ADMIN_EMAIL)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)
    return page


@pytest.fixture
def clean_database(test_database):
    """Clean database state before each test"""
    session_factory = test_database
    session = session_factory()

    try:
        # Clean up test data (keep admin user)
        session.execute(orm.user_invites.delete())
        session.execute(orm.assemblies.delete())
        session.execute(orm.user_assembly_roles.delete())
        # Keep admin user, clean others
        session.execute(orm.users.delete().where(orm.users.c.email != ADMIN_EMAIL))
        session.commit()
        yield
    finally:
        session.close()


@pytest.fixture
def user_invite(test_database, admin_user, clean_database) -> str:
    """Create a valid user invite in the database"""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    invite = generate_invite(
        uow=uow,
        created_by_user_id=admin_user.id,
        global_role=GlobalRole.USER,
        expires_in_hours=24,  # 24 hours for testing
    )

    return invite.code
