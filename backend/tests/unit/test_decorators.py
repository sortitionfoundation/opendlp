"""ABOUTME: Unit tests for the route decorators in entrypoints/decorators.py
ABOUTME: Exercises require_capability directly, including the branch login_required usually shadows"""

from dataclasses import dataclass

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_login import LoginManager

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.decorators import require_capability
from opendlp.service_layer.permissions import can_create_assembly


def _user(global_role: GlobalRole) -> User:
    return User(
        email=f"{global_role.name.lower()}@example.com",
        global_role=global_role,
        password_hash="hash",  # pragma: allowlist secret
    )


@dataclass
class GatedApp:
    """A minimal app with one capability-gated route, plus a way to sign someone in.

    The route deliberately has no @login_required, which is what the real routes
    stack on top: the decorator has to be safe on its own, so this is what
    exercises its own anonymous branch.
    """

    client: FlaskClient
    signed_in: dict[str, User | None]

    def sign_in(self, user: User) -> None:
        self.signed_in["user"] = user
        with self.client.session_transaction() as session:
            session["_user_id"] = user.get_id()


@pytest.fixture
def gated() -> GatedApp:
    app = Flask(__name__)
    app.secret_key = "test-secret"  # pragma: allowlist secret
    signed_in: dict[str, User | None] = {"user": None}

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.user_loader(lambda _user_id: signed_in["user"])

    @app.route("/login", endpoint="auth.login")
    def login() -> str:
        return "sign in"

    @app.route("/gated")
    @require_capability(can_create_assembly)
    def gated_view() -> str:
        return "allowed"

    return GatedApp(client=app.test_client(), signed_in=signed_in)


class TestRequireCapability:
    def test_a_user_with_the_capability_is_let_through(self, gated: GatedApp) -> None:
        gated.sign_in(_user(GlobalRole.ORGANISER))

        response = gated.client.get("/gated")
        assert response.status_code == 200
        assert response.data == b"allowed"

    def test_an_admin_is_let_through(self, gated: GatedApp) -> None:
        gated.sign_in(_user(GlobalRole.ADMIN))

        assert gated.client.get("/gated").status_code == 200

    def test_a_user_without_the_capability_is_refused(self, gated: GatedApp) -> None:
        gated.sign_in(_user(GlobalRole.USER))

        assert gated.client.get("/gated").status_code == 403

    def test_an_anonymous_visitor_is_sent_to_sign_in(self, gated: GatedApp) -> None:
        """The decorator does not rely on @login_required having run first."""
        response = gated.client.get("/gated")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
