"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

backoffice_bp = Blueprint("backoffice", __name__, template_folder="backoffice")


@backoffice_bp.route("/showcase")
def showcase() -> ResponseReturnValue:
    """Component showcase page demonstrating the backoffice design system."""
    return render_template("backoffice/showcase.html"), 200
