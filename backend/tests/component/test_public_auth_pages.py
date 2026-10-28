# ABOUTME: Component tests that the public account pages render on the OpenDLP design system
# ABOUTME: Each page must load the public layout and carry no GOV.UK Frontend markup or assets

import uuid

import pytest
from flask.testing import FlaskClient

# Pages a signed-out visitor can GET without a token or a half-finished login.
PUBLIC_AUTH_PAGES = [
    "/auth/login",
]


@pytest.mark.parametrize("url", PUBLIC_AUTH_PAGES)
def test_page_has_no_govuk_markup(client: FlaskClient, url: str) -> None:
    """A migrated page never mixes in GOV.UK classes or the GOV.UK stylesheet."""
    response = client.get(url)

    assert response.status_code == 200
    assert b"govuk-" not in response.data
    assert b"css/application.css" not in response.data


@pytest.mark.parametrize("url", PUBLIC_AUTH_PAGES)
def test_page_uses_the_public_layout(client: FlaskClient, url: str) -> None:
    """The public layout's skip link and main landmark are present."""
    response = client.get(url)

    assert b'href="#main-content"' in response.data
    assert b'id="main-content"' in response.data


def test_verify_2fa_page_has_no_govuk_markup(client: FlaskClient) -> None:
    """The second sign-in step, reached with a pending 2FA session, is on the design system too."""
    with client.session_transaction() as session:
        session["pending_2fa_user_id"] = str(uuid.uuid4())

    response = client.get("/auth/login/verify-2fa")

    assert response.status_code == 200
    assert b'name="verification_code"' in response.data
    assert b"govuk-" not in response.data
    assert b'id="main-content"' in response.data
