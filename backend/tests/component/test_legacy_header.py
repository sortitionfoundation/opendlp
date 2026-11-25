# ABOUTME: Component tests for the "Your projects" link in the header of the legacy GOV.UK base.html
# ABOUTME: Checks the header link points at the backoffice dashboard, not the retired one

import re

from flask import Flask, render_template
from flask_login import login_user

from opendlp.domain.users import User


def _your_projects_href(body: str) -> str:
    match = re.search(r'<a class="govuk-header__link"\s+href="([^"]+)">Your projects</a>', body)
    assert match is not None, "header has no Your projects link"
    return match.group(1)


class TestLegacyHeaderYourProjectsLink:
    def test_header_links_to_backoffice_dashboard(self, app: Flask, regular_user: User) -> None:
        # The header offers Your projects only to a signed-in user. It was
        # checked on the error pages until they moved to the public layout;
        # base.html still serves the legacy pages under main/.
        with app.test_request_context("/"):
            login_user(regular_user)
            body = render_template("base.html")
        assert _your_projects_href(body) == "/backoffice/dashboard"
