# ABOUTME: Component tests for the "Your projects" links on legacy GOV.UK pages (admin and error pages)
# ABOUTME: Checks the header link and the page-body links point at the backoffice dashboard, not the retired one

import re

import pytest
from flask import Flask, render_template
from flask.testing import FlaskClient
from flask_login import login_user

from opendlp.domain.users import User

ERROR_TEMPLATES = ["400", "403", "404", "413", "500"]


def _your_projects_href(body: str) -> str:
    match = re.search(r'<a class="govuk-header__link"\s+href="([^"]+)">Your projects</a>', body)
    assert match is not None, "header has no Your projects link"
    return match.group(1)


def _assert_no_old_dashboard_links(body: str) -> None:
    assert 'href="/dashboard"' not in body


class TestLegacyHeaderYourProjectsLink:
    def test_admin_page_links_to_backoffice_dashboard(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/admin/")
        assert response.status_code == 200
        assert _your_projects_href(response.get_data(as_text=True)) == "/backoffice/dashboard"

    def test_404_page_links_to_backoffice_dashboard(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/no-such-page")
        assert response.status_code == 404
        assert _your_projects_href(response.get_data(as_text=True)) == "/backoffice/dashboard"


class TestPageBodyYourProjectsLinks:
    def test_admin_index_back_link_goes_to_backoffice_dashboard(self, logged_in_admin: FlaskClient) -> None:
        body = logged_in_admin.get("/admin/").get_data(as_text=True)
        assert re.search(r'<a href="/backoffice/dashboard"[^>]*>Back to Your projects</a>', body)
        _assert_no_old_dashboard_links(body)

    @pytest.mark.parametrize("code", ERROR_TEMPLATES)
    def test_error_page_links_to_backoffice_dashboard(self, app: Flask, regular_user: User, code: str) -> None:
        # The error pages only offer the Your projects link to a signed-in user.
        with app.test_request_context("/"):
            login_user(regular_user)
            body = render_template(f"errors/{code}.html")
        assert re.search(r'<a href="/backoffice/dashboard"\s+class="btn btn-outline-primary">', body)
        _assert_no_old_dashboard_links(body)
