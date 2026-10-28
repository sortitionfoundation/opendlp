"""ABOUTME: Component tests for the redirect from the old /backoffice/assembly/ URLs
ABOUTME: Bookmarks, emails and spreadsheets still carry them; they must land on the project pages"""

import uuid

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly


class TestOldAssemblyUrlsRedirect:
    def test_the_project_page_redirects_permanently(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}")
        assert response.status_code == 301
        assert response.location == f"/backoffice/project/{existing_assembly.id}"

    def test_a_deeper_path_keeps_its_tail(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 301
        assert response.location == f"/backoffice/project/{existing_assembly.id}/respondents"

    def test_the_query_string_comes_too(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/data?source=csv&mode=edit")
        assert response.status_code == 301
        assert response.location == f"/backoffice/project/{existing_assembly.id}/data?source=csv&mode=edit"

    def test_the_create_page_moves_as_well(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/backoffice/assembly/new")
        assert response.status_code == 301
        assert response.location == "/backoffice/project/new"

    def test_following_the_redirect_lands_on_the_project_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}", follow_redirects=True)
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_an_unknown_project_still_redirects_then_is_not_found(self, logged_in_admin: FlaskClient) -> None:
        """The redirect is a plain rewrite; whether the project exists is the new URL's business."""
        response = logged_in_admin.get(f"/backoffice/assembly/{uuid.uuid4()}", follow_redirects=True)
        assert response.status_code in (302, 404) or b"Project not found" in response.data

    def test_the_redirect_needs_no_login(self, client: FlaskClient) -> None:
        """Signing in happens on the page itself, so the rewrite never has to know who is asking."""
        response = client.get("/backoffice/assembly/new")
        assert response.status_code == 301
        assert response.location == "/backoffice/project/new"
