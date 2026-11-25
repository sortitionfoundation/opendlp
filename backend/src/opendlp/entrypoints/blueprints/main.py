"""ABOUTME: The public home page, and redirects from the addresses of the retired signed-in pages
ABOUTME: Sends /dashboard and /assemblies/<id> to their backoffice pages so old bookmarks keep working"""

import uuid

from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> ResponseReturnValue:
    """Public home page, shown to every visitor.

    A signed-in user sees it too, with a link to their dashboard in place of Sign in.
    """
    dashboard_url = url_for("backoffice.dashboard") if current_user.is_authenticated else ""
    return render_template("public/home.html", dashboard_url=dashboard_url), 200


@main_bp.route("/dashboard")
@login_required
def dashboard_redirect() -> ResponseReturnValue:
    """Where the list of projects used to be."""
    return redirect(url_for("backoffice.dashboard"))


@main_bp.route("/assemblies/<uuid:assembly_id>")
@login_required
def assembly_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Where a project's page used to be. The project page decides who may see it."""
    return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
