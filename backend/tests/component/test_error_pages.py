# ABOUTME: Component tests for the error pages - 400 (an expired form), 403, 404, 413 and 500 - on the OpenDLP design system
# ABOUTME: Each renders on the public layout with its status, offers Your projects or the home page, and the 500 page needs no database

import re

import pytest
from flask import Flask, render_template
from flask.testing import FlaskClient
from flask_login import login_user

from opendlp.domain.users import User
from opendlp.entrypoints.flask_app import create_app
from tests.fakes import FakeStore, FakeUnitOfWork

ERROR_PAGES = ["400", "403", "404", "413", "500"]
# The pages whose reader may need a person: the support address is offered.
PAGES_WITH_SUPPORT = ["403", "500"]

YOUR_PROJECTS_BUTTON = re.compile(r'<a href="/backoffice/dashboard"\s+role="button"[^>]*>\s*<span>Your projects</span>')
HOME_PAGE_BUTTON = re.compile(r'<a href="/"\s+role="button"[^>]*>\s*<span>Go to the home page</span>')
SUPPORT_LINK = re.compile(r'<a href="mailto:[^"]+@[^"]+"[^>]*>OpenDLP support</a>')


def _title(body: str) -> str:
    match = re.search(r"<title>\s*(.*?)\s*- OpenDLP</title>", body, re.DOTALL)
    assert match is not None, "page has no title"
    return match.group(1)


def _assert_on_the_public_layout(body: str) -> None:
    """The page is on the design system's public layout, with nothing of GOV.UK Frontend."""
    assert "govuk-" not in body
    assert "css/application.css" not in body
    assert "backoffice/dist/main.css" in body
    assert 'id="main-content"' in body


def _sign_in(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()
        session["_fresh"] = True


class TestEachStatusRendersItsPage:
    def test_a_missing_page_gets_the_404_page(self, client: FlaskClient) -> None:
        response = client.get("/no-such-page")

        assert response.status_code == 404
        body = response.get_data(as_text=True)
        assert _title(body) == "Page not found"
        assert "Check the web address is correct." in body
        _assert_on_the_public_layout(body)

    def test_a_page_the_user_may_not_see_gets_the_403_page(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/admin/users")

        assert response.status_code == 403
        body = response.get_data(as_text=True)
        assert _title(body) == "You don't have access to this page"
        assert "Your account doesn't have the role this page needs." in body
        _assert_on_the_public_layout(body)

    def test_an_upload_over_the_size_limit_gets_the_413_page(self, app: Flask, client: FlaskClient) -> None:
        app.config["MAX_CONTENT_LENGTH"] = 16

        response = client.post("/auth/login", data={"email": "someone@example.com", "password": "a long password"})

        assert response.status_code == 413
        body = response.get_data(as_text=True)
        assert _title(body) == "The file is too large"
        assert "Try again with a smaller file." in body
        _assert_on_the_public_layout(body)

    def test_a_form_with_an_expired_csrf_token_gets_the_expired_form_page(
        self, app: Flask, client: FlaskClient
    ) -> None:
        app.config["WTF_CSRF_ENABLED"] = True

        response = client.post("/auth/login", data={"email": "someone@example.com", "password": "x"})

        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert _title(body) == "The form has expired"
        assert (
            "The form could not be submitted because it had been open too long or could not be verified "
            "for security reasons. Please go back, reload the page, and try again."
        ) in body
        _assert_on_the_public_layout(body)


@pytest.mark.parametrize("code", ERROR_PAGES)
class TestTheWayBack:
    def test_a_visitor_who_is_not_signed_in_is_offered_the_home_page(self, app: Flask, code: str) -> None:
        with app.test_request_context("/"):
            body = render_template(f"errors/{code}.html")

        assert HOME_PAGE_BUTTON.search(body)
        assert not YOUR_PROJECTS_BUTTON.search(body)

    def test_a_signed_in_user_is_offered_your_projects(self, app: Flask, regular_user: User, code: str) -> None:
        with app.test_request_context("/"):
            login_user(regular_user)
            body = render_template(f"errors/{code}.html")

        assert YOUR_PROJECTS_BUTTON.search(body)
        assert not HOME_PAGE_BUTTON.search(body)

    def test_the_support_address_is_offered_where_the_reader_may_need_a_person(self, app: Flask, code: str) -> None:
        with app.test_request_context("/"):
            body = render_template(f"errors/{code}.html")

        assert bool(SUPPORT_LINK.search(body)) == (code in PAGES_WITH_SUPPORT)


def _app_with_a_failing_route(uow_factory) -> Flask:  # type: ignore[no-untyped-def]
    """An app whose /fails route raises, answered with the 500 page as in production.

    The testing config propagates exceptions to the test instead of handing them
    to the 500 handler, so that is switched off here.
    """
    app = create_app("testing_component", uow_factory=uow_factory)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/fails")
    def fails() -> str:
        raise RuntimeError("a deliberate failure")

    return app


def _database_down() -> FakeUnitOfWork:
    raise ConnectionError("the database is down")


class TestTheServerErrorPage:
    def test_a_failure_gets_the_500_page(self, fake_store: FakeStore) -> None:
        client = _app_with_a_failing_route(lambda: FakeUnitOfWork(store=fake_store)).test_client()

        response = client.get("/fails")

        assert response.status_code == 500
        body = response.get_data(as_text=True)
        assert _title(body) == "Sorry, something went wrong"
        assert "The problem is on our end." in body
        assert SUPPORT_LINK.search(body)
        assert HOME_PAGE_BUTTON.search(body)
        _assert_on_the_public_layout(body)

    def test_a_signed_in_user_is_offered_your_projects(self, fake_store: FakeStore, regular_user: User) -> None:
        client = _app_with_a_failing_route(lambda: FakeUnitOfWork(store=fake_store)).test_client()
        _sign_in(client, regular_user)

        response = client.get("/fails")

        assert response.status_code == 500
        assert YOUR_PROJECTS_BUTTON.search(response.get_data(as_text=True))

    def test_the_page_renders_when_the_database_is_down(self, regular_user: User) -> None:
        """Signed in, the user is loaded from the database - which here is what failed.

        render_template() would load the user again for the page, fail the same
        way, and leave the visitor with the server's bare error. The page renders
        instead, offering what it offers a visitor who is not signed in.
        """
        client = _app_with_a_failing_route(_database_down).test_client()
        _sign_in(client, regular_user)

        response = client.get("/backoffice/dashboard")

        assert response.status_code == 500
        body = response.get_data(as_text=True)
        assert _title(body) == "Sorry, something went wrong"
        assert HOME_PAGE_BUTTON.search(body)
        assert not YOUR_PROJECTS_BUTTON.search(body)
        _assert_on_the_public_layout(body)

    def test_a_flashed_message_still_shows(self, fake_store: FakeStore) -> None:
        """Routes that answer a failure with the 500 page may flash what failed first."""
        app = _app_with_a_failing_route(lambda: FakeUnitOfWork(store=fake_store))
        client = app.test_client()
        with client.session_transaction() as session:
            session["_flashes"] = [("error", "The user list could not be loaded")]

        response = client.get("/fails")

        assert "The user list could not be loaded" in response.get_data(as_text=True)
