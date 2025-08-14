"""ABOUTME: Authentication routes for login, logout, and registration
ABOUTME: Handles user authentication flow with invite-based registration"""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug import Response

from opendlp.service_layer.exceptions import InvalidCredentials, InvalidInvite, PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import authenticate_user, create_user
from opendlp.translations import _

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Response | str:
    """User login page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not username or not password:
            flash(_("Please provide both username and password."), "error")
            return render_template("auth/login.html")

        try:
            with SqlAlchemyUnitOfWork() as uow:
                user = authenticate_user(uow, username, password)
                login_user(user, remember=remember)

                # Redirect to next page if specified, otherwise dashboard
                next_page = request.args.get("next")
                if next_page and next_page.startswith("/"):
                    return redirect(next_page)
                return redirect(url_for("main.dashboard"))

        except InvalidCredentials:
            flash(_("Invalid username or password."), "error")
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash(_("An error occurred during login. Please try again."), "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout() -> Response:
    """User logout."""
    logout_user()
    flash(_("You have been logged out."), "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register/<invite_code>", methods=["GET", "POST"])
def register(invite_code: str = "") -> Response | str:
    """User registration with invite code."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Get invite code from URL or form
    if not invite_code:
        invite_code = request.form.get("invite_code", "").strip()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        invite_code = request.form.get("invite_code", "").strip()

        # Basic validation
        if not all([username, email, password, password_confirm, invite_code]):
            flash(_("All fields are required."), "error")
            return render_template("auth/register.html", invite_code=invite_code)

        if password != password_confirm:
            flash(_("Passwords do not match."), "error")
            return render_template("auth/register.html", invite_code=invite_code)

        try:
            with SqlAlchemyUnitOfWork() as uow:
                user = create_user(uow=uow, username=username, email=email, password=password, invite_code=invite_code)

                # Log the user in immediately after registration
                login_user(user)
                flash(_("Registration successful! Welcome to OpenDLP."), "success")
                return redirect(url_for("main.dashboard"))

        except UserAlreadyExists as e:
            flash(str(e), "error")
        except InvalidInvite as e:
            flash(str(e), "error")
        except PasswordTooWeak as e:
            flash(_("Password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            current_app.logger.error(f"Registration error: {e}")
            flash(_("An error occurred during registration. Please try again."), "error")

    return render_template("auth/register.html", invite_code=invite_code)
