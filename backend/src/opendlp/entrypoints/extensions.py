"""ABOUTME: Flask extensions initialization and configuration
ABOUTME: Sets up Flask-Login, Flask-Session, security headers, and database session management"""

import uuid

from flask import Flask
from flask_login import LoginManager
from flask_session import Session
from flask_talisman import Talisman

from opendlp.domain.users import User
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


# Initialize extensions
login_manager = LoginManager()
session_store = Session()
talisman = Talisman()


def init_extensions(app: Flask) -> None:
    """Initialize Flask extensions with app instance."""

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    # Initialize Flask-Session with Redis
    session_store.init_app(app)

    # Initialize Flask-Talisman for security headers
    talisman.init_app(
        app,
        force_https=app.config.get("FORCE_HTTPS", False),  # False in development
        strict_transport_security=True,
        content_security_policy={
            "default-src": "'self'",
            "script-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "font-src": "'self' https://cdn.jsdelivr.net",
            "img-src": "'self' data:",
        },
    )


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user from database for Flask-Login."""

    try:
        user_uuid = uuid.UUID(user_id)
        with SqlAlchemyUnitOfWork() as uow:
            return uow.users.get(user_uuid)
    except (ValueError, TypeError):
        return None

