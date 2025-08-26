"""ABOUTME: Flask application factory with configuration, blueprints, and error handling
ABOUTME: Creates and configures Flask app instance with all necessary extensions and routes"""

import logging

from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

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
    app = Flask(
        __name__,
        template_folder=str(config.get_templates_path()),
        static_folder=str(config.get_static_path()),
    )

    # Load configuration
    flask_config = config.get_config(config_name)
    app.config.from_object(flask_config)

    # Initialize extensions
    init_extensions(app, flask_config)

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Configure logging
    configure_logging(app)

    return app


def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    from .blueprints.auth import auth_bp
    from .blueprints.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")


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


def configure_logging(app: Flask) -> None:
    """Configure application logging."""
    if not app.debug and not app.testing:
        # Production logging setup
        if app.config.get("LOG_TO_STDOUT"):
            stream_handler = logging.StreamHandler()
            # TODO: get log level from config
            stream_handler.setLevel(logging.INFO)
            app.logger.addHandler(stream_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info("OpenDLP application startup")
