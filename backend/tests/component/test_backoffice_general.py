# ABOUTME: Component tests for general backoffice routes over a FakeUnitOfWork
# ABOUTME: Drives dashboard, showcase, assembly data page, and data-source locking against a seeded fake store, no PostgreSQL

import re
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp import config
from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.entrypoints import context_processors
from opendlp.entrypoints.flask_app import create_app
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from tests.fakes import FakeStore, FakeUnitOfWork


def _clear_cached_config_readers() -> None:
    """Drop the cached answers of the context processors' config readers.

    These read whichever config FLASK_ENV names, and cache it for the life of
    the process, so a test that changes FLASK_ENV has to clear them on the way
    in and on the way out - otherwise it either reads the previous test's
    config or leaves its own for the next one.
    """
    context_processors.get_site_banner_config.cache_clear()
    context_processors.get_support_email.cache_clear()
    context_processors.get_help_site_urls.cache_clear()


@pytest.fixture
def production_client(fake_store: FakeStore, monkeypatch: pytest.MonkeyPatch):
    """A client for an app carrying the blueprints a production install has.

    register_blueprints() asks config.dev_tools_enabled(), which reads FLASK_ENV
    rather than the loaded config, so setting the variable here drops the dev
    blueprint while the app keeps the component config - in-memory sessions, a
    fake store, no PostgreSQL and no Redis. Building the whole production config
    would want a Redis session backend, which is not what these tests are about.

    It does have to be a production environment that *validates*, though: the
    cached readers above call get_config() with no name, so with FLASK_ENV set
    they build FlaskProductionConfig, which refuses a console email adapter and
    the development secret key.
    """
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("EMAIL_ADAPTER", "smtp")
    monkeypatch.setenv("SECRET_KEY", "component-test-key-not-the-dev-default")  # pragma: allowlist secret
    _clear_cached_config_readers()
    reload_flags()
    app = create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))
    yield app.test_client()
    _clear_cached_config_readers()


@pytest.fixture
def showcase_production_client(production_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    """The same install, having opted in to the showcase the way staging does."""
    monkeypatch.setenv("FF_SHOWCASE", "true")
    reload_flags()
    return production_client


@pytest.fixture
def assembly_with_gsheet(fake_store: FakeStore, admin_user) -> tuple[Assembly, AssemblyGSheet]:
    """An assembly with existing gsheet configuration in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with GSheet",
            created_by_user_id=admin_user.id,
            question="What should we configure?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            number_to_select=22,
        )
        detached_assembly = assembly.create_detached_copy()

    with FakeUnitOfWork(store=fake_store) as uow:
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


class TestBackofficeDashboard:
    """Test backoffice dashboard functionality."""

    def test_dashboard_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.get("/backoffice/dashboard")
        assert response.status_code == 302
        assert "login" in response.location

    def test_dashboard_shows_existing_assemblies(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """Dashboard shows existing assemblies."""
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_dashboard_accessible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        """Regular users can view the dashboard."""
        response = logged_in_user.get("/backoffice/dashboard")
        assert response.status_code == 200

    def test_english_wording(self, logged_in_admin: FlaskClient, existing_assembly) -> None:
        """The list page is headed Your projects, once, with no second heading under it."""
        response = logged_in_admin.get("/backoffice/dashboard")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert re.search(r"<title>\s*Your projects\s*- OpenDLP</title>", body)
        assert re.search(r"<h1[^>]*>Your projects</h1>", body)
        assert "<h2" not in body
        assert "Welcome back, Test Admin!" in body
        assert "Created: " in body
        assert "Starts: " in body


class TestBackofficeShowcase:
    """Test backoffice showcase page."""

    def test_showcase_page_loads(self, client: FlaskClient) -> None:
        """Showcase page loads without authentication."""
        response = client.get("/backoffice/showcase")
        assert response.status_code == 200
        # Showcase demonstrates the design system components
        assert b"showcase" in response.data.lower() or b"component" in response.data.lower()

    def test_showcase_renders_every_shared_icon(self, client: FlaskClient) -> None:
        """The icons section draws each macro in the shared set, named so it can be found.

        Somebody about to draw a fourth info circle should be able to see the
        three that already exist, and read off what to type instead.
        """
        icons_file = config.get_templates_path() / "backoffice" / "components" / "icons.html"
        names = re.findall(r"\{%\s*macro\s+(icon_[a-z0-9_]+)", icons_file.read_text())
        assert names

        response = client.get("/backoffice/showcase")
        assert response.status_code == 200
        body = response.data.decode()
        missing = [name for name in names if name not in body]
        assert not missing, f"showcase does not list these icons: {missing}"

    def test_search_demo_empty_query(self, client: FlaskClient) -> None:
        """Search demo returns empty for no query."""
        response = client.get("/backoffice/showcase/search-demo")
        assert response.status_code == 200
        data = response.get_json()
        assert data == []

    def test_search_demo_with_query(self, client: FlaskClient) -> None:
        """Search demo returns mock results."""
        response = client.get("/backoffice/showcase/search-demo?q=alice")
        assert response.status_code == 200
        data = response.get_json()
        # Should match mock user with "alice"
        assert len(data) >= 1
        assert any("alice" in item["label"].lower() or "alice" in item["sublabel"].lower() for item in data)

    def test_the_dev_patterns_link_is_offered_where_dev_tools_are_loaded(self, client: FlaskClient) -> None:
        """Outside production the alert section points at the live patterns page."""
        response = client.get("/backoffice/showcase")
        assert response.status_code == 200
        # The href, not the path: other sections name /backoffice/dev/patterns
        # as plain text, which is fine wherever it is served.
        assert 'href="/backoffice/dev/patterns?tab=floating-alerts"' in response.data.decode()


class TestShowcaseOnAProductionInstall:
    """The showcase as a production install serves it - no dev blueprint.

    A production install registers a smaller set of blueprints, and the
    showcase is one of the few pages it serves that is written with the dev
    tools in mind. url_for() on an endpoint that is not registered raises, so
    a link added here without a guard is a 500 that only production sees.
    """

    def test_the_dev_blueprint_is_absent(self, production_client: FlaskClient) -> None:
        """The premise of every other test here, so it is worth stating.

        Without this, a fixture that quietly stopped being production-shaped
        would leave the tests below passing while guarding nothing.
        """
        assert production_client.get("/backoffice/dev").status_code == 404

    def test_the_showcase_is_not_published_unless_asked_for(self, production_client: FlaskClient) -> None:
        """Off by default: the live install does not publish it at all."""
        assert production_client.get("/backoffice/showcase").status_code == 404
        assert production_client.get("/backoffice/showcase/search-demo").status_code == 404

    def test_the_showcase_renders_where_the_install_opts_in(self, showcase_production_client: FlaskClient) -> None:
        """A staging server sets FF_SHOWCASE, and every section has to render.

        This is the whole point of the class: rendering is what catches a
        reference to a route that production does not have.
        """
        response = showcase_production_client.get("/backoffice/showcase")
        assert response.status_code == 200
        assert b"Alert Component" in response.data

    def test_the_search_demo_comes_with_it(self, showcase_production_client: FlaskClient) -> None:
        """The showcase's own endpoint, so it is reachable wherever the page is."""
        response = showcase_production_client.get("/backoffice/showcase/search-demo?q=alice")
        assert response.status_code == 200
        assert response.get_json()

    def test_it_does_not_offer_a_link_to_the_dev_tools(self, showcase_production_client: FlaskClient) -> None:
        """No dead invitation to a route this install does not have."""
        body = showcase_production_client.get("/backoffice/showcase").data.decode()
        assert 'href="/backoffice/dev/patterns' not in body


class TestWhereTheDataSourceTabWas:
    """The Data Source tab is a card on the project details page; its address still leads somewhere useful."""

    @pytest.mark.parametrize("query", ["", "?source=gsheet", "?source=csv&mode=edit", "?source=invalid"])
    def test_the_data_address_goes_to_the_data_source_card(
        self, logged_in_admin: FlaskClient, existing_assembly, query: str
    ) -> None:
        """Whatever an old bookmark carried in its query string."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/data{query}")

        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/project/{existing_assembly.id}#data-source")

    def test_view_assembly_data_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/project/{existing_assembly.id}/data")
        assert response.status_code == 302
        assert "login" in response.location

    def test_the_details_page_ignores_a_source_left_on_an_old_link(
        self, logged_in_admin: FlaskClient, existing_assembly
    ) -> None:
        """?source= used to choose the data source for an undecided project; the stored choice does now."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}?source=gsheet")

        assert response.status_code == 200
        html = response.data.decode()
        assert "In OpenDLP" in html
        assert "source=gsheet" not in html
