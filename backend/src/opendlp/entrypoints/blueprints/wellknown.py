"""ABOUTME: Well-known URL endpoints for robots.txt, security.txt, and change-password redirect.
ABOUTME: Serves standard well-known URIs as defined by RFC 8615 and related specifications."""

from flask import Blueprint, redirect, send_from_directory, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user

from opendlp import config

_WELL_KNOWN_DIR = config.get_static_path() / "well-known"
_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days

wellknown_bp = Blueprint("wellknown", __name__)


@wellknown_bp.route("/robots.txt")
def robots_txt() -> ResponseReturnValue:
    """Serve robots.txt from the site root."""
    return send_from_directory(
        _WELL_KNOWN_DIR,
        "robots.txt",
        mimetype="text/plain",
        max_age=_CACHE_MAX_AGE_SECONDS,
    )


@wellknown_bp.route("/.well-known/security.txt")
def security_txt() -> ResponseReturnValue:
    """Serve security.txt per RFC 9116."""
    return send_from_directory(
        _WELL_KNOWN_DIR,
        "security.txt",
        mimetype="text/plain",
        max_age=_CACHE_MAX_AGE_SECONDS,
    )


@wellknown_bp.route("/.well-known/change-password")
def change_password() -> ResponseReturnValue:
    """Redirect to the appropriate password-change page.

    Signed-in users go to the profile change-password form.
    Anonymous users go to the forgot-password (reset) flow.
    See https://w3c.github.io/webappsec-change-password-url/
    """
    if current_user.is_authenticated:
        return redirect(url_for("profile.change_password"), code=302)
    return redirect(url_for("auth.forgot_password"), code=302)
