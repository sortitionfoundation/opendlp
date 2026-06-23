# ABOUTME: Component tests for two-factor authentication routes over a FakeUnitOfWork
# ABOUTME: Drives the real 2FA Flask routes + services (real pyotp/TOTP crypto in-process) against a seeded fake store

import base64
import secrets

import pyotp
import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture(autouse=True)
def totp_encryption_key(temp_env_vars):
    """Provide a real TOTP encryption key so pyotp/crypto run in-process."""
    raw_key = secrets.token_bytes(32)
    temp_env_vars(TOTP_ENCRYPTION_KEY=base64.b64encode(raw_key).decode())


@pytest.fixture
def user_with_2fa(fake_store: FakeStore) -> dict:
    """A confirmed user with 2FA enabled, plus their TOTP secret and backup codes."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email="2fauser@example.com",
            password="SecurePassword123!",  # pragma: allowlist secret
            first_name="2FA",
            last_name="User",
            global_role=GlobalRole.USER,
        )
        user_id = user.id

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user_id)
        user_obj.confirm_email()
        uow.commit()

    with FakeUnitOfWork(store=fake_store) as uow:
        totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
        valid_code = pyotp.TOTP(totp_secret).now()
        two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

    return {"id": user_id, "totp_secret": totp_secret, "backup_codes": backup_codes}


def _login_session(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


class Test2FASetupFlow:
    def test_setup_2fa_invalid_code_fails(self, logged_in_user: FlaskClient) -> None:
        """2FA setup fails with an invalid verification code."""
        response = logged_in_user.get("/profile/2fa/setup")
        assert response.status_code == 200

        response = logged_in_user.post(
            "/profile/2fa/enable",
            data={"totp_code": "000000"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data


class Test2FALoginFlow:
    def test_login_with_2fa_backup_code(self, client: FlaskClient, user_with_2fa: dict) -> None:
        """Successful 2FA verification using a backup code completes login."""
        with client.session_transaction() as session:
            session["pending_2fa_user_id"] = str(user_with_2fa["id"])

        response = client.post(
            "/auth/login/verify-2fa",
            data={"verification_code": user_with_2fa["backup_codes"][0]},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

        with client.session_transaction() as session:
            assert "_user_id" in session
            flashes = session.get("_flashes", [])
            assert any("backup code" in message.lower() for _, message in flashes)

    def test_login_with_2fa_invalid_code_fails(self, client: FlaskClient, user_with_2fa: dict) -> None:
        """2FA verification with an invalid code fails and does not log the user in."""
        with client.session_transaction() as session:
            session["pending_2fa_user_id"] = str(user_with_2fa["id"])

        response = client.post(
            "/auth/login/verify-2fa",
            data={"verification_code": "000000"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data

        with client.session_transaction() as session:
            assert "_user_id" not in session


class Test2FAManagement:
    def test_regenerate_backup_codes(self, client: FlaskClient, fake_store: FakeStore, user_with_2fa: dict) -> None:
        """A 2FA user can regenerate their backup codes with a valid TOTP code."""
        user = FakeUnitOfWork(store=fake_store).users.get(user_with_2fa["id"]).create_detached_copy()
        _login_session(client, user)

        valid_code = pyotp.TOTP(user_with_2fa["totp_secret"]).now()
        response = client.post(
            "/profile/2fa/backup-codes/regenerate",
            data={"totp_code": valid_code},
            follow_redirects=False,
        )

        assert response.status_code == 200 or (
            response.status_code == 302 and "backup-codes" in response.headers["Location"]
        )
