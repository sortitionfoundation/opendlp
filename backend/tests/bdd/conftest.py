import os
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters import database, orm
from opendlp.config import PostgresCfg
from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.entrypoints.celery.app import get_celery_app
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user, grant_user_assembly_role
from tests.conftest import (
    wait_for_celery_worker_to_come_up,
    wait_for_postgres_to_come_up,
    wait_for_webapp_to_come_up_on_port,
)
from tests.data import VALID_GSHEET_URL

from .config import ADMIN_EMAIL, ADMIN_PASSWORD, BDD_PORT, NORMAL_EMAIL, NORMAL_PASSWORD, Urls

BACKEND_PATH = Path(__file__).parent.parent.parent
CSV_FIXTURES_DIR = BACKEND_PATH / "tests" / "csv_fixtures" / "selection_data"

# The value is milliseconds - so 5000 is 5 seconds
# The default is 30 seconds - which means if a page fails to load
# then the tests take a long time to fail.
PLAYWRIGHT_TIMEOUT = 5_000
expect.set_options(timeout=PLAYWRIGHT_TIMEOUT)


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


def _reset_csv_files(csv_file_dir: Path) -> None:
    for csv_path in CSV_FIXTURES_DIR.glob("*.csv"):
        shutil.copy(csv_path, csv_file_dir)


@pytest.fixture(scope="session")
def test_csv_data_dir(tmp_path_factory) -> Generator[Path, None, None]:
    """
    Create a temporary directory with the original CSV files in
    """
    data_dir = tmp_path_factory.mktemp("selection_data")
    _reset_csv_files(data_dir)
    yield data_dir


@pytest.fixture
def reset_csv_data_dir(test_csv_data_dir: Path) -> Generator[Path, None, None]:
    """
    A per-test fixture which re-copies the CSV files in to reset
    the state after a test - so that an individual test could put
    different CSV files in that directory to test non-standard behaviour
    and then subsequent tests have the expected files there.
    """
    yield test_csv_data_dir
    _reset_csv_files(test_csv_data_dir)


@pytest.fixture(scope="session")
def test_server(test_database, test_csv_data_dir):
    """Start Flask test server in background"""
    # Check if server is already running
    try:
        wait_for_webapp_to_come_up_on_port(port=BDD_PORT, timeout=2)
        print("Test server already running, using existing instance")
        yield
        return
    except Exception:
        print("Starting test server...")

    # Start server in background
    env = os.environ.copy()
    env["FLASK_ENV"] = "testing_postgres"
    env["DB_PORT"] = "54322"
    env["REDIS_PORT"] = "63792"
    env["FLASK_APP"] = "src/opendlp/entrypoints/flask_app.py"
    # Use CSV data source for testing instead of Google Sheets
    env["USE_CSV_DATA_SOURCE"] = "true"
    env["TEST_CSV_DATA_DIR"] = str(test_csv_data_dir)

    process = subprocess.Popen(  # noqa: S603
        ["uv", "run", "flask", "run", f"--port={BDD_PORT}", "--host=127.0.0.1"],
        cwd=BACKEND_PATH,
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
def test_celery_worker(test_database, test_csv_data_dir):
    """Start celery worker in the background"""
    # create celery app with correct configuration
    celery_app = get_celery_app(redis_port=63792)
    # check if celery worker is already running
    try:
        wait_for_celery_worker_to_come_up(celery_app, timeout=2)
        print("Test celery worker already running, using existing instance")
        yield
        return
    except Exception:
        print("Starting test celery worker...")

    # Start celery worker in background
    env = os.environ.copy()
    env["FLASK_ENV"] = "testing_postgres"
    env["DB_PORT"] = "54322"
    env["REDIS_PORT"] = "63792"
    # Use CSV data source for testing instead of Google Sheets
    env["USE_CSV_DATA_SOURCE"] = "true"
    env["TEST_CSV_DATA_DIR"] = str(test_csv_data_dir)

    process = subprocess.Popen(  # noqa: S603
        ["uv", "run", "celery", "--app", "opendlp.entrypoints.celery.tasks", "worker", "--loglevel=info"],
        cwd=BACKEND_PATH,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # wait for celery worker
    wait_for_celery_worker_to_come_up(celery_app)
    print("Test celery worker started successfully")

    yield

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    print("Test celery worker stopped")


@pytest.fixture(scope="session")
def admin_user(test_database):
    """Create admin user for testing"""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    # Create admin user
    admin, _token = create_user(
        uow=uow,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        first_name="Test",
        last_name="Admin",
        global_role=GlobalRole.ADMIN,
        accept_data_agreement=True,
    )

    # Confirm email for test users (they need to login)
    with uow:
        user = uow.users.get_by_email(ADMIN_EMAIL)
        user.confirm_email()
        uow.commit()
        admin = user.create_detached_copy()

    return admin


@pytest.fixture(scope="session")
def normal_user(test_database):
    """Create admin user for testing"""
    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)

    # Create normal user
    user, _token = create_user(
        uow=uow,
        email=NORMAL_EMAIL,
        password=NORMAL_PASSWORD,
        first_name="Test",
        last_name="Normal",
        global_role=GlobalRole.USER,
        accept_data_agreement=True,
    )

    # Confirm email for test users (they need to login)
    with uow:
        fetched_user = uow.users.get_by_email(NORMAL_EMAIL)
        fetched_user.confirm_email()
        uow.commit()
        user = fetched_user.create_detached_copy()

    return user


@pytest.fixture
def assembly_creator(test_database, admin_user):
    """Create assembly for testing"""

    def _create_assembly(title: str, question: str = "", number_to_select: int = 10) -> Assembly:
        session_factory = test_database
        uow = SqlAlchemyUnitOfWork(session_factory)
        assembly = create_assembly(
            uow=uow, title=title, created_by_user_id=admin_user.id, question=question, number_to_select=number_to_select
        )
        return assembly

    return _create_assembly


@pytest.fixture
def assembly_user_role_creator(test_database, admin_user):
    """Create assembly user roles for testing"""

    def _create_assembly_user_role(
        assembly: Assembly, user: User, assembly_role: AssemblyRole = AssemblyRole.ASSEMBLY_MANAGER
    ) -> UserAssemblyRole:
        session_factory = test_database
        uow = SqlAlchemyUnitOfWork(session_factory)
        role = grant_user_assembly_role(
            uow=uow, user_id=user.id, assembly_id=assembly.id, role=assembly_role, current_user=admin_user
        )
        return role

    return _create_assembly_user_role


@pytest.fixture
def assembly_gsheet_creator(test_database, admin_user):
    """Create assembly for testing"""

    def _create_assembly_gsheet(title: str) -> tuple[Assembly, AssemblyGSheet]:
        session_factory = test_database
        uow = SqlAlchemyUnitOfWork(session_factory)
        assembly = create_assembly(uow=uow, title=title, created_by_user_id=admin_user.id, number_to_select=22)
        gsheet_assembly = add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url=VALID_GSHEET_URL,
            team="custom",
            id_column="nationbuilder_id",
            check_same_address=True,
            check_same_address_cols=["primary_address1", "primary_zip"],
            columns_to_keep=[
                "first_name",
                "last_name",
                "email",
                "mobile_number",
                "primary_address1",
                "primary_address2",
                "primary_city",
            ],
        )
        return assembly, gsheet_assembly

    return _create_assembly_gsheet


@pytest.fixture(scope="session")
def browser():
    """Browser instance for all tests"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("CI", "false").lower() == "true")
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def context(browser, test_server, test_celery_worker):
    """Browser context that waits for server to be ready"""
    context = browser.new_context()
    context.set_default_navigation_timeout(PLAYWRIGHT_TIMEOUT)
    context.set_default_timeout(PLAYWRIGHT_TIMEOUT)
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context):
    """Fresh page for each test"""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture
def logged_out_page(page: Page):
    # Clear any existing session/cookies to ensure clean state
    page.context.clear_cookies()
    return page


def _login(page: Page, email: str, password: str) -> None:
    page.goto(Urls.login)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)


def _is_admin_signed_in(page: Page) -> bool:
    """
    Check if the user signed in is an admin

    - check for site admin link
    - assumes that we are on a signed in page already
    """
    admin_link = page.get_by_role("link", name="Site Admin")
    return admin_link.is_visible()


@pytest.fixture
def admin_logged_in_page(page: Page, admin_user):
    """Page with admin user logged in"""
    # we might already be logged in - try
    page.goto(Urls.dashboard)
    page.wait_for_load_state()
    if page.url == Urls.dashboard:
        if not _is_admin_signed_in(page):
            page.context.clear_cookies()
            _login(page, admin_user.email, ADMIN_PASSWORD)
    else:
        _login(page, admin_user.email, ADMIN_PASSWORD)
    return page


@pytest.fixture
def normal_logged_in_page(page: Page, normal_user):
    """Page with admin user logged in"""
    # we might already be logged in - try
    page.goto(Urls.dashboard)
    page.wait_for_load_state()
    if page.url == Urls.dashboard:
        if _is_admin_signed_in(page):
            page.context.clear_cookies()
            _login(page, normal_user.email, NORMAL_PASSWORD)
    else:
        _login(page, normal_user.email, NORMAL_PASSWORD)
    return page


def delete_all_except_standard_users(session: Session) -> None:
    # Clean up test data (keep admin user)
    session.execute(orm.user_invites.delete())
    session.execute(orm.assemblies.delete())
    session.execute(orm.user_assembly_roles.delete())
    # Keep admin user, clean others
    session.execute(orm.users.delete().where(orm.users.c.email.not_in((ADMIN_EMAIL, NORMAL_EMAIL))))
    session.commit()


@pytest.fixture(autouse=True)
def clean_database(test_database):
    """Clean database state before each test"""
    session_factory = test_database
    session = session_factory()

    try:
        yield
    finally:
        # Clean up test data (keep admin user)
        delete_all_except_standard_users(session)
        session.close()


@pytest.fixture
def user_invite(test_database, admin_user) -> str:
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
