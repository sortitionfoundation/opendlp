"""ABOUTME: Well-known URL endpoints for robots.txt, security.txt, and change-password redirect.
ABOUTME: Serves standard well-known URIs as defined by RFC 8615 and related specifications."""

from flask import Blueprint, abort, current_app, jsonify, redirect, send_from_directory, url_for
from flask.typing import ResponseReturnValue

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


@wellknown_bp.route("/.well-known/microsoft-identity-association.json")
def microsoft_identity_association() -> ResponseReturnValue:
    """Serve the publisher domain verification file for the Microsoft Entra app.

    Microsoft fetches this to confirm we control the domain the app claims as its
    publisher domain. Returns 404 when no application ID is configured, rather than
    publishing a document with an empty applicationId.
    See https://learn.microsoft.com/en-us/entra/identity-platform/howto-configure-publisher-domain
    """
    application_id = current_app.config.get("OAUTH_MICROSOFT_APPLICATION_ID", "")
    if not application_id:
        abort(404)
    payload = {"associatedApplications": [{"applicationId": application_id}]}
    return jsonify(payload)


@wellknown_bp.route("/.well-known/change-password")
def change_password() -> ResponseReturnValue:
    """Redirect to the appropriate password-change page.

    Signed-in users go to the profile change-password form.
    Anonymous users will try to go to the profile change-password form, and be redirected
    to the sign in page.
    See https://w3c.github.io/webappsec-change-password-url/
    """
    return redirect(url_for("profile.change_password"), code=302)
