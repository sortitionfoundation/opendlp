"""ABOUTME: Unit tests for the login form's remember-me consent properties
ABOUTME: The checkbox is the consent for the persistent remember_token cookie"""

from opendlp.entrypoints.flask_app import create_app
from opendlp.entrypoints.forms import LoginForm


class TestRememberMeConsent:
    """The remember_token cookie is not strictly necessary, so the checkbox itself
    carries the consent. That only holds if it is unticked by default and its label
    tells the user what ticking it does. See docs/personal-data.md.
    """

    def test_remember_me_is_unticked_by_default(self) -> None:
        app = create_app("testing")
        with app.test_request_context("/auth/login"):
            form = LoginForm()

            assert form.remember_me.data is False

    def test_remember_me_label_states_the_cookie_consequence(self) -> None:
        app = create_app("testing")
        with app.test_request_context("/auth/login"):
            form = LoginForm()
            label = str(form.remember_me.label.text)

            assert "cookie" in label.lower()
