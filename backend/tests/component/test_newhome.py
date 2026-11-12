# ABOUTME: Component tests for the draft home page served at /newhome
# ABOUTME: Checks it renders for every visitor, links to the account pages, and is not linked from the live home page

from flask import Flask, url_for
from flask.testing import FlaskClient

from opendlp.feature_flags import default_dashboard_endpoint


class TestNewHome:
    def test_renders_for_anonymous_visitor(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        assert response.status_code == 200
        assert "Bringing" in response.text
        assert "simplicity" in response.text
        assert "to sortition" in response.text
        assert "How does OpenDLP work?" in response.text
        assert "Key benefits" in response.text
        assert "Who is OpenDLP for?" in response.text

    def test_does_not_redirect_signed_in_user(self, logged_in_user: FlaskClient) -> None:
        """Reviewers are signed in, so unlike / the draft must not send them to the dashboard."""
        response = logged_in_user.get("/newhome")
        assert response.status_code == 200
        assert "Bringing" in response.text

    def test_links_to_sign_in_and_registration(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        assert 'href="/auth/login"' in response.text
        assert 'href="/auth/register"' in response.text

    def test_uses_the_opendlp_logo_files(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        assert "img/opendlp-logo-light.svg" in response.text
        assert "img/opendlp-small-sized-logo.svg" in response.text
        assert "img/opendlp-favicon.svg" in response.text

    def test_footer_links_to_known_destinations(self, client: FlaskClient, app: Flask) -> None:
        response = client.get("/newhome")
        assert 'href="#how-it-works"' in response.text
        assert 'id="how-it-works"' in response.text
        assert f'href="mailto:{app.config["SUPPORT_EMAIL"]}"' in response.text
        assert "https://github.com/sortitionfoundation/opendlp" in response.text
        assert f'href="{app.config["HELP_SITE_HOME"]}"' in response.text
        assert f'href="{app.config["KNOWLEDGE_HUB_URL"]}"' in response.text
        assert 'href="#"' not in response.text

    def test_footer_drops_links_without_a_page(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        for label in ("Documentation", "Release notes", "Report a vulnerability", "Privacy policy", "Terms of use"):
            assert label not in response.text

    def test_footer_names_the_legal_entity_and_licence(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        footer = response.text[response.text.index("<footer") :]
        assert "Sortition Europe" in footer
        assert "Open source under the Apache License 2.0" in footer
        assert "LEGAL ENTITY" not in footer
        assert "REGISTRATION NUMBER" not in footer

    def test_intro_splits_the_complexity_sentence(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        assert "<p>Democratic lotteries can be technically complex to implement.</p>" in response.text
        assert "<p>There are few public resources available to support them.</p>" in response.text

    def test_hero_actions_are_primary_buttons(self, client: FlaskClient) -> None:
        response = client.get("/newhome")
        hero_start = response.text.index("<h1")
        hero = response.text[hero_start : response.text.index("</section>", hero_start)]
        assert hero.count("btn--primary") == 2
        assert "btn--secondary" not in hero

    def test_is_not_linked_from_the_live_home_page(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "/newhome" not in response.text

    def test_header_has_home_link_sign_in_and_help(self, client: FlaskClient, app: Flask) -> None:
        response = client.get("/newhome")
        header_start = response.text.index("<section")
        header = response.text[header_start : response.text.index("</section>", header_start)]
        assert 'href="/newhome"' in header
        assert 'href="/auth/login"' in header
        assert f'href="{app.config["HELP_SITE_HOME"]}' in header

    def test_header_offers_dashboard_to_signed_in_user(self, logged_in_user: FlaskClient, app: Flask) -> None:
        """The button goes where / would redirect a signed-in user, in place of Sign in."""
        response = logged_in_user.get("/newhome")
        header_start = response.text.index("<section")
        header = response.text[header_start : response.text.index("</section>", header_start)]
        with app.test_request_context():
            dashboard_url = url_for(default_dashboard_endpoint())
        assert f'href="{dashboard_url}"' in header
        assert "Dashboard" in header
        assert 'href="/auth/login"' not in header
        assert logged_in_user.get("/").location == dashboard_url
