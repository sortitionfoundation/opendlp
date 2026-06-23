# ABOUTME: Component tests for the forgot-password / reset-password auth routes over a FakeUnitOfWork
# ABOUTME: Covers the happy paths plus the error/anti-enumeration/validation branches, no PostgreSQL/Redis

from datetime import UTC, datetime, timedelta

from flask.testing import FlaskClient

from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


def _make_password_user(fake_store: FakeStore, email: str = "reset-me@example.com", *, active: bool = True) -> User:
    """Seed an active password user (no OAuth) in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=email,
            password="OriginalPass123!",  # pragma: allowlist secret
            first_name="Reset",
            last_name="Me",
            global_role=GlobalRole.USER,
            is_active=active,
        )
        return user.create_detached_copy()


def _make_oauth_user(fake_store: FakeStore, email: str = "oauth-reset@example.com") -> User:
    """Seed an OAuth-only user (no password) in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=email,
            oauth_provider="google",
            oauth_id="google-reset-id",
            first_name="OAuth",
            last_name="User",
            global_role=GlobalRole.USER,
        )
        return user.create_detached_copy()


def _seed_token(
    fake_store: FakeStore,
    user_id,
    token: str = "reset-token-123",  # noqa: S107  # test token, not a credential
    *,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> str:
    """Seed a password reset token with explicit expiry/used state."""
    with FakeUnitOfWork(store=fake_store) as uow:
        reset_token = PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at, used_at=used_at)
        uow.password_reset_tokens.add(reset_token)
        uow.commit()
    return token


def _tokens_for(fake_store: FakeStore, user_id) -> list[PasswordResetToken]:
    with FakeUnitOfWork(store=fake_store) as uow:
        return [t for t in uow.password_reset_tokens.all() if t.user_id == user_id]


class TestForgotPassword:
    def test_get_renders_form(self, client: FlaskClient) -> None:
        response = client.get("/auth/forgot-password")
        assert response.status_code == 200
        assert b"Reset your password" in response.data

    def test_redirects_when_already_authenticated(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/auth/forgot-password")
        assert response.status_code == 302

    def test_unknown_email_shows_anti_enumeration_success(self, client: FlaskClient, fake_store: FakeStore) -> None:
        response = client.post("/auth/forgot-password", data={"email": "nobody@example.com"})
        assert response.status_code == 302
        assert "/auth/login" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert list(uow.password_reset_tokens.all()) == []

    def test_active_password_user_creates_token(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        response = client.post("/auth/forgot-password", data={"email": user.email})
        assert response.status_code == 302
        assert "/auth/login" in response.location
        assert len(_tokens_for(fake_store, user.id)) == 1

    def test_oauth_user_creates_no_token(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_oauth_user(fake_store)
        response = client.post("/auth/forgot-password", data={"email": user.email})
        assert response.status_code == 302
        assert _tokens_for(fake_store, user.id) == []

    def test_inactive_user_creates_no_token(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store, email="inactive@example.com", active=False)
        response = client.post("/auth/forgot-password", data={"email": user.email})
        assert response.status_code == 302
        assert _tokens_for(fake_store, user.id) == []

    def test_invalid_email_format_rerenders_form(self, client: FlaskClient) -> None:
        response = client.post("/auth/forgot-password", data={"email": "not-an-email"})
        assert response.status_code == 200
        assert b"Reset your password" in response.data

    def test_rate_limited_after_three_requests(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store, email="ratelimited@example.com")
        for index in range(3):
            _seed_token(fake_store, user.id, token=f"recent-{index}")

        response = client.post("/auth/forgot-password", data={"email": user.email})

        assert response.status_code == 200  # re-renders with the rate-limit error
        # No new token was created beyond the three recent ones.
        assert len(_tokens_for(fake_store, user.id)) == 3


class TestResetPassword:
    def test_get_with_valid_token_renders_form(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id)
        response = client.get(f"/auth/reset-password/{token}")
        assert response.status_code == 200
        assert b"Set new password" in response.data

    def test_get_with_unknown_token_redirects(self, client: FlaskClient) -> None:
        response = client.get("/auth/reset-password/does-not-exist")
        assert response.status_code == 302
        assert "/auth/forgot-password" in response.location

    def test_get_with_expired_token_redirects(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id, expires_at=datetime.now(UTC) - timedelta(hours=1))
        response = client.get(f"/auth/reset-password/{token}")
        assert response.status_code == 302
        assert "/auth/forgot-password" in response.location

    def test_redirects_when_already_authenticated(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/auth/reset-password/any-token")
        assert response.status_code == 302
        assert "/auth/forgot-password" not in response.location

    def test_post_valid_token_resets_password(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id)
        with FakeUnitOfWork(store=fake_store) as uow:
            original_hash = uow.users.get(user.id).password_hash

        response = client.post(
            f"/auth/reset-password/{token}",
            data={
                "password": "BrandNewPass456!",  # pragma: allowlist secret
                "password_confirm": "BrandNewPass456!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 302
        assert "/auth/login" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).password_hash != original_hash
            assert uow.password_reset_tokens.get_by_token(token).is_used()

    def test_post_weak_password_rerenders_and_keeps_token(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id)

        response = client.post(
            f"/auth/reset-password/{token}",
            data={
                "password": "password",  # pragma: allowlist secret  # passes length, fails strength
                "password_confirm": "password",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 200
        assert b"Set new password" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert not uow.password_reset_tokens.get_by_token(token).is_used()

    def test_post_mismatched_confirmation_rerenders(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id)

        response = client.post(
            f"/auth/reset-password/{token}",
            data={
                "password": "BrandNewPass456!",  # pragma: allowlist secret
                "password_confirm": "DifferentPass789!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 200
        assert b"Passwords must match" in response.data

    def test_post_used_token_redirects(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id, used_at=datetime.now(UTC) - timedelta(minutes=5))

        response = client.post(
            f"/auth/reset-password/{token}",
            data={
                "password": "BrandNewPass456!",  # pragma: allowlist secret
                "password_confirm": "BrandNewPass456!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 302
        assert "/auth/forgot-password" in response.location

    def test_post_expired_token_redirects(self, client: FlaskClient, fake_store: FakeStore) -> None:
        user = _make_password_user(fake_store)
        token = _seed_token(fake_store, user.id, expires_at=datetime.now(UTC) - timedelta(hours=1))

        response = client.post(
            f"/auth/reset-password/{token}",
            data={
                "password": "BrandNewPass456!",  # pragma: allowlist secret
                "password_confirm": "BrandNewPass456!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 302
        assert "/auth/forgot-password" in response.location
