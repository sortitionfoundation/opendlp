"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes with separate design system from GOV.UK pages"""

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

backoffice_bp = Blueprint("backoffice", __name__, template_folder="backoffice")


@backoffice_bp.route("/hello")
def hello() -> ResponseReturnValue:
    """Simple hello world route to verify backoffice setup."""
    return render_template("backoffice/hello.html"), 200
