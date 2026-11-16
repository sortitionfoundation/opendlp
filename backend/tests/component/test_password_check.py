"""ABOUTME: Component tests for the sign-up page's live password check, POST /auth/password-check
ABOUTME: Verdicts per rule from the validators, and the endpoint's safety: CSRF, rate limit, no caching, no logged password"""

import re
from io import StringIO
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient

URL = "/auth/password-check"
ANN = {"email": "ann.smith@example.org", "first_name": "Ann", "last_name": "Smith"}
STRONG = "Kx7#mQ2vLp"  # pragma: allowlist secret


def _check(client: FlaskClient, password: str, **details: str):
    return client.post(URL, json={"password": password, **details})


class TestVerdicts:
    """A boolean per rule, from the validators that run when the form is sent."""

    def test_a_password_that_meets_every_rule(self, client: FlaskClient):
        response = _check(client, STRONG, **ANN)

        assert response.status_code == 200
        assert response.get_json() == {
            "rules": {"length": True, "not-numbers-only": True, "not-common": True, "not-similar": True}
        }

    @pytest.mark.parametrize(
        ("password", "unmet"),
        [
            pytest.param("Kx7#mQ2vL", {"length"}, id="9 characters"),
            pytest.param("4719305826", {"not-numbers-only"}, id="numbers only"),
            pytest.param("password123", {"not-common"}, id="a commonly used password"),
            pytest.param("ann.smith@example", {"not-similar"}, id="too similar to the email address"),
        ],
    )
    def test_each_rule_is_answered_on_its_own(self, client: FlaskClient, password: str, unmet: set[str]):
        rules = _check(client, password, **ANN).get_json()["rules"]

        assert {key for key, met in rules.items() if not met} == unmet

    def test_the_personal_information_rule_uses_the_details_sent(self, client: FlaskClient):
        assert _check(client, "ann.smith@example").get_json()["rules"]["not-similar"] is True
        assert _check(client, "ann.smith@example", **ANN).get_json()["rules"]["not-similar"] is False

    def test_details_that_are_not_text_are_left_out(self, client: FlaskClient):
        response = client.post(URL, json={"password": "ann.smith@example", "email": ["ann.smith@example.org"]})

        assert response.status_code == 200
        assert response.get_json()["rules"]["not-similar"] is True

    def test_the_answer_holds_verdicts_and_never_a_validator_message(self, client: FlaskClient):
        response = _check(client, "password123", **ANN)

        rules = response.get_json()["rules"]
        assert all(isinstance(met, bool) for met in rules.values())
        assert "This password is too common" not in response.get_data(as_text=True)

    def test_it_answers_without_signing_in(self, client: FlaskClient):
        """The sign-up page is for people who have no account yet."""
        response = _check(client, STRONG)

        assert response.status_code == 200
        assert "rules" in response.get_json()


class TestRequests:
    """What the endpoint accepts: a POST with the password in a JSON body, and nothing else."""

    def test_only_post_is_allowed(self, client: FlaskClient):
        assert client.get(URL).status_code == 405

    def test_the_password_is_read_from_the_body_only(self, client: FlaskClient):
        response = client.post(f"{URL}?password=Kx7%23mQ2vLp")

        assert response.status_code == 400
        assert response.get_json() == {"error": "There is no password to check"}

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({}, id="no password"),
            pytest.param({"password": 4719305826}, id="a number, not text"),
            pytest.param(["Kx7#mQ2vLp"], id="not an object"),
        ],
    )
    def test_a_body_without_a_password_is_refused(self, client: FlaskClient, body: object):
        response = client.post(URL, json=body)

        assert response.status_code == 400
        assert set(response.get_json()) == {"error"}

    def test_the_csrf_protection_applies(self, app: Flask, client: FlaskClient):
        """Refused without the sign-up page's token, answered with it in X-CSRFToken."""
        app.config["WTF_CSRF_ENABLED"] = True

        assert _check(client, STRONG).status_code == 400

        page = client.get("/auth/register").get_data(as_text=True)
        token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page)
        assert token is not None
        response = client.post(URL, json={"password": STRONG}, headers={"X-CSRFToken": token.group(1)})
        assert response.status_code == 200


class TestNothingKept:
    """No answer is stored on the way, and the password reaches no log."""

    def test_an_answer_is_marked_no_store(self, client: FlaskClient):
        assert _check(client, STRONG).headers["Cache-Control"] == "no-store"

    def test_a_refusal_is_marked_no_store(self, client: FlaskClient, password_check_redis: MagicMock):
        assert client.post(URL, json={}).headers["Cache-Control"] == "no-store"

        password_check_redis.get.return_value = "999"
        assert _check(client, STRONG).headers["Cache-Control"] == "no-store"

    def test_the_password_is_not_logged(
        self, client: FlaskClient, password_check_redis: MagicMock, capture_json_handler: StringIO
    ):
        password = "Unmistakable-7q2x9w"  # pragma: allowlist secret
        _check(client, password, **ANN)
        password_check_redis.get.return_value = "999"
        _check(client, password, **ANN)

        output = capture_json_handler.getvalue()
        assert "Password check rate limit exceeded" in output
        assert password not in output


class TestRateLimit:
    """Checks are counted per IP, and refused over the limit - the page then leaves its lines unticked."""

    def test_an_answered_check_is_counted_against_the_ip(self, client: FlaskClient, password_check_redis: MagicMock):
        _check(client, STRONG)

        pipeline = password_check_redis.pipeline.return_value
        pipeline.incr.assert_called_once_with("password_check_ratelimit:ip:127.0.0.1")
        pipeline.execute.assert_called_once()

    def test_over_the_limit_a_check_is_refused_with_429(
        self, app: Flask, client: FlaskClient, password_check_redis: MagicMock
    ):
        password_check_redis.get.return_value = str(app.config["PASSWORD_CHECK_RATE_LIMIT_PER_IP"])

        response = _check(client, STRONG)

        assert response.status_code == 429
        assert set(response.get_json()) == {"error"}
        assert response.headers["Retry-After"] == str(app.config["PASSWORD_CHECK_RATE_LIMIT_WINDOW_MINUTES"] * 60)

    def test_a_refused_check_is_not_counted(self, app: Flask, client: FlaskClient, password_check_redis: MagicMock):
        """So a page that keeps asking does not keep itself over the limit."""
        password_check_redis.get.return_value = str(app.config["PASSWORD_CHECK_RATE_LIMIT_PER_IP"])

        _check(client, STRONG)

        password_check_redis.pipeline.assert_not_called()
