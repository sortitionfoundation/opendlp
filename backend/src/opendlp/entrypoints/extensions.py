"""ABOUTME: Flask extensions initialization and configuration
ABOUTME: Sets up Flask-Login, Flask-Session, security headers, and database session management"""

import uuid

from authlib.integrations.flask_client import OAuth
from flask import Flask, request, session
from flask_babel import Babel
from flask_login import LoginManager
from flask_session import Session
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from whitenoise import WhiteNoise

from opendlp import bootstrap
from opendlp.config import FlaskBaseConfig
from opendlp.domain.users import User
from opendlp.translations import gettext

# Initialize extensions
login_manager = LoginManager()
session_store = Session()
talisman = Talisman()
babel = Babel()
csrf = CSRFProtect()
oauth = OAuth()


def init_extensions(app: Flask, config: FlaskBaseConfig) -> None:
    """Initialize Flask extensions with app instance."""

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    # note we do NOT wrap this in lazy_gettext() - as putting LazyString
    # objects into the session in Redis causes errors. Instead we set
    # the `localize_callback` - the string will be passed to that within
    # a request callback and just return a normal string.
    login_manager.login_message = "Please sign in to access this page."
    login_manager.login_message_category = "info"
    login_manager.localize_callback = gettext

    # Initialize Flask-Session with Redis
    session_store.init_app(app)

    # Initialize Flask-Talisman for security headers
    talisman.init_app(
        app,
        force_https=app.config.get("FORCE_HTTPS", False),  # False in development
        strict_transport_security=True,
        content_security_policy={
            "default-src": "'self'",
            "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
            "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "font-src": "'self' https://cdn.jsdelivr.net",
            "img-src": "'self' data:",
            "connect-src": "'self'",
        },
    )

    # Initialize Flask-Babel for i18n/l10n
    babel.init_app(app, locale_selector=get_locale)

    # Initialize Flask-WTF CSRF protection
    csrf.init_app(app)

    # Initialise whitenoise - for serving staticfiles
    if config.APPLICATION_ROOT == "/":
        whitenoise_prefix = "static/"
    else:
        app_root = config.APPLICATION_ROOT.strip("/")
        whitenoise_prefix = f"{app_root}/static/"

    # Configure whitenoise with proper settings to prevent file truncation
    app.wsgi_app = WhiteNoise(  # type: ignore[method-assign]
        app.wsgi_app,
        root="static/",
        prefix=whitenoise_prefix,
        # max_age=31536000,  # 1 year cache for static files
        charset="utf-8",  # Explicit charset to prevent encoding issues
    )

    # Initialize Authlib OAuth (only if configured)
    oauth.init_app(app)

    # Register Google OAuth provider (only if client ID is configured)
    if app.config.get("OAUTH_GOOGLE_CLIENT_ID"):
        oauth.register(
            name="google",
            client_id=app.config["OAUTH_GOOGLE_CLIENT_ID"],
            client_secret=app.config["OAUTH_GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def get_locale() -> str:
    """Get the best language match for the user."""
    from flask import current_app

    supported_languages = current_app.config.get("LANGUAGES", ["en"])

    # Check URL parameter first (for language switching)
    requested_language = request.args.get("lang")
    if requested_language and requested_language in supported_languages:
        session["language"] = requested_language
        return requested_language

    # Check session (user preference)
    if "language" in session and session["language"] in supported_languages:
        return str(session["language"])

    # Check user preferences (if logged in)
    from flask_login import current_user

    if (
        hasattr(current_user, "preferred_language")
        and current_user.preferred_language
        and current_user.preferred_language in supported_languages
    ):
        return str(current_user.preferred_language)

    # Fall back to browser language detection
    return request.accept_languages.best_match(supported_languages) or supported_languages[0]


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user from database for Flask-Login."""

    try:
        user_uuid = uuid.UUID(user_id)
        uow = bootstrap.bootstrap()
        with uow:
            db_user = uow.users.get(user_uuid)
            if db_user:
                user = db_user.create_detached_copy()
                assert isinstance(user, User)
                return user
            return None
    except (ValueError, TypeError):
        return None
