"""ABOUTME: Component tests for the addresses of the retired signed-in pages under /dashboard and /assemblies
ABOUTME: Two redirect to their backoffice pages so old bookmarks work; every other one is gone"""

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly


class TestOldAddressesRedirect:
    def test_the_old_dashboard_redirects_to_the_list_of_projects(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 302
        assert response.location == "/backoffice/dashboard"

    def test_the_old_project_page_redirects_to_the_project_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}")
        assert response.status_code == 302
        assert response.location == f"/backoffice/project/{existing_assembly.id}"

    def test_following_the_old_project_page_lands_on_the_project(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}", follow_redirects=True)
        assert response.status_code == 200
        assert existing_assembly.title.encode() in response.data

    def test_a_stranger_is_turned_away_by_the_project_page_not_shown_the_project(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The redirect asks no permission of its own; the page it leads to does."""
        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}", follow_redirects=True)
        assert existing_assembly.title.encode() not in response.data

    @pytest.mark.parametrize("path", ["/dashboard", "/assemblies/3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b"])
    def test_a_signed_out_visitor_is_sent_to_sign_in_first(self, client: FlaskClient, path: str) -> None:
        response = client.get(path)
        assert response.status_code == 302
        assert response.location.startswith("/auth/login")
        assert "next=" in response.location


class TestRetiredPagesAreGone:
    """One address from each retired group of pages, so re-registering one by accident shows up here."""

    @pytest.mark.parametrize(
        "path",
        [
            "/assemblies/new",
            "/assemblies/{id}/edit",
            "/assemblies/{id}/data",
            "/assemblies/{id}/members",
            "/assemblies/{id}/gsheet",
            "/assemblies/{id}/gsheet_select",
            "/assemblies/{id}/db_select",
            "/assemblies/{id}/targets",
            "/assemblies/{id}/respondents",
        ],
    )
    def test_a_retired_page_is_not_found(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, path: str
    ) -> None:
        response = logged_in_admin.get(path.format(id=existing_assembly.id))
        assert response.status_code == 404

    def test_the_old_project_page_takes_nothing_but_a_get(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(f"/assemblies/{existing_assembly.id}", data={})
        assert response.status_code == 405
