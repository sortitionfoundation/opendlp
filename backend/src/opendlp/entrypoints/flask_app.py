"""ABOUTME: Flask application factory with configuration, blueprints, and error handling
ABOUTME: Creates and configures Flask app instance with all necessary extensions and routes"""

from flask import Flask, Response, render_template
from flask_login import current_user
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import opendlp.logging
from opendlp import config
from opendlp.entrypoints.extensions import init_extensions


def create_app(config_name: str = "") -> Flask:
    """
    Flask application factory.

    Args:
        config_name: Configuration name (development, testing, production)

    Returns:
        Configured Flask application instance
    """
    opendlp.logging.logging_setup(config.get_log_level())

    app = Flask(
        __name__,
        template_folder=str(config.get_templates_path()),
        static_folder=str(config.get_static_path()),
    )

    # Load configuration
    flask_config = config.get_config(config_name)
    app.config.from_object(flask_config)

    # Apply ProxyFix middleware to trust reverse proxy headers (X-Forwarded-* headers from Caddy)
    # Trust 1 layer of proxy (the reverse proxy in front of the app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    # Initialize extensions
    init_extensions(app, flask_config)

    # Register context processors
    register_context_processors(app)

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Register after request handlers
    register_after_request_handlers(app)

    app.logger.info("OpenDLP application startup")

    return app


def register_context_processors(app: Flask) -> None:
    """Register template context processors."""
    from .context_processors import static_versioning_context_processor

    app.context_processor(static_versioning_context_processor)


def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    from .blueprints.admin import admin_bp
    from .blueprints.auth import auth_bp
    from .blueprints.gsheets import gsheets_bp
    from .blueprints.main import main_bp
    from .blueprints.profile import profile_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(gsheets_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(profile_bp)


def register_error_handlers(app: Flask) -> None:
    """Register error handlers for common HTTP errors."""

    @app.errorhandler(404)
    def not_found(error: HTTPException) -> tuple[str, int]:
        """Handle 404 Not Found errors."""
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error: HTTPException) -> tuple[str, int]:
        """Handle 500 Internal Server errors."""
        app.logger.error(f"Server Error: {error}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden(error: HTTPException) -> tuple[str, int]:
        """Handle 403 Forbidden errors."""
        return render_template("errors/403.html"), 403


def register_after_request_handlers(app: Flask) -> None:
    """Register after request handlers."""

    @app.after_request
    def add_cache_headers_for_authenticated_users(response: Response) -> Response:
        """
        Add no-cache headers for authenticated users to prevent browser caching of sensitive pages.

        This prevents browsers from caching pages that contain user-specific or sensitive information
        when a user is logged in. Public pages (when not logged in) can still be cached normally.
        """
        # Check if user is authenticated
        if current_user.is_authenticated:
            # Add comprehensive no-cache headers
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
