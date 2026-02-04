"""ABOUTME: Flask application factory with configuration, blueprints, and error handling
ABOUTME: Creates and configures Flask app instance with all necessary extensions and routes"""

import secrets
import uuid

import structlog
from flask import Config, Flask, Response, g, render_template, request
from flask_login import current_user
from secure import Secure, headers
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import opendlp.logging
from opendlp import config
from opendlp.entrypoints.extensions import init_extensions


def generate_csp_nonce() -> str:
    """Generate a cryptographically secure nonce for CSP."""
    return secrets.token_urlsafe(16)


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

    # Register before/after request handlers
    register_before_request_handlers(app)
    register_after_request_handlers(app)

    app.logger.info("OpenDLP application startup")

    return app


def register_context_processors(app: Flask) -> None:
    """Register template context processors."""
    from .context_processors import static_versioning_context_processor

    app.context_processor(static_versioning_context_processor)

    @app.context_processor
    def inject_csp_nonce() -> dict[str, str]:
        """Inject CSP nonce into all template contexts."""
        return {"csp_nonce": g.get("csp_nonce", "")}


def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    from .blueprints.admin import admin_bp
    from .blueprints.auth import auth_bp
    from .blueprints.gsheets import gsheets_bp
    from .blueprints.health import health_bp
    from .blueprints.main import main_bp
    from .blueprints.profile import profile_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(gsheets_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(profile_bp)
    app.register_blueprint(health_bp)


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


def register_before_request_handlers(app: Flask) -> None:
    """Register before request handlers."""

    @app.before_request
    def set_csp_nonce() -> None:
        """Generate and store CSP nonce for this request."""
        g.csp_nonce = generate_csp_nonce()

    @app.before_request
    def add_context_for_structlog() -> None:
        """
        Add items to structlog for this request:
        - the request path
        - a UUID for this request - so we can find all log messages for a request easily
        - the origin of the request

        Idea from https://www.structlog.org/en/25.5.0/contextvars.html#example-flask-and-thread-local-data
        """
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            view=request.path,
            request_id=str(uuid.uuid4()),
            peer=request.access_route[0],
        )


def get_secure_headers(config: Config) -> Secure:
    secure_headers = Secure(
        cache=headers.CacheControl().no_store(),
        coop=headers.CrossOriginOpenerPolicy().same_origin(),
        csp=headers.ContentSecurityPolicy()
        .default_src("'self'")
        .script_src(
            "'self'",
            "'nonce-NONCE_PLACEHOLDER'",
            "'strict-dynamic'",
            "https://cdn.jsdelivr.net",
        )
        .style_src("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
        .font_src("'self'", "https://cdn.jsdelivr.net")
        .img_src("'self'", "data:")
        .frame_ancestors("'none'")
        .form_action("'self'")
        .object_src("'none'"),
        permissions=headers.PermissionsPolicy().geolocation().microphone().camera(),
        referrer=headers.ReferrerPolicy().strict_origin_when_cross_origin(),
        server=headers.Server().set(""),
        xcto=headers.XContentTypeOptions().nosniff(),
        xfo=headers.XFrameOptions().deny(),
    )
    # for local dev, we skip some headers. But for production we include them
    if not config.get("DEBUG", False):
        secure_headers.headers_list.append(headers.StrictTransportSecurity().max_age(31536000))
    return secure_headers


def register_after_request_handlers(app: Flask) -> None:
    """Register after request handlers."""

    secure_headers = get_secure_headers(app.config)

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

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        """
        Add security headers to the response, replacing CSP nonce placeholder with actual nonce.
        """
        secure_headers.set_headers(response)  # type: ignore[arg-type]

        # Replace nonce placeholder with actual nonce for this request
        nonce = g.get("csp_nonce", "")
        if nonce and "Content-Security-Policy" in response.headers:
            response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
                "NONCE_PLACEHOLDER", nonce
            )

        return response
