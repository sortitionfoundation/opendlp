"""ABOUTME: Authentication routes for login, logout, and registration
ABOUTME: Handles user authentication flow with invite-based registration"""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user

from opendlp.entrypoints.forms import LoginForm, RegistrationForm
from opendlp.service_layer.exceptions import InvalidCredentials, InvalidInvite, PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import authenticate_user, create_user
from opendlp.translations import _

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    """User login page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        try:
            with SqlAlchemyUnitOfWork() as uow:
                # After form validation, these fields are guaranteed to be non-None
                assert form.email.data is not None
                assert form.password.data is not None
                user = authenticate_user(uow, form.email.data, form.password.data)
                login_user(user, remember=form.remember_me.data)

                # Redirect to next page if specified, otherwise dashboard
                next_page = request.args.get("next")
                if next_page and next_page.startswith("/"):
                    return redirect(next_page)
                return redirect(url_for("main.dashboard"))

        except InvalidCredentials:
            flash(_("Invalid email or password."), "error")
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash(_("An error occurred during login. Please try again."), "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout() -> ResponseReturnValue:
    """User logout."""
    logout_user()
    flash(_("You have been logged out."), "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register/<invite_code>", methods=["GET", "POST"])
def register(invite_code: str = "") -> ResponseReturnValue:
    """User registration with invite code."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()

    # Pre-populate invite code from URL
    if invite_code and not form.invite_code.data:
        form.invite_code.data = invite_code

    if form.validate_on_submit():
        try:
            with SqlAlchemyUnitOfWork() as uow:
                # After form validation, required fields are guaranteed to be non-None
                assert form.email.data is not None
                assert form.password.data is not None
                assert form.invite_code.data is not None
                user = create_user(
                    uow=uow,
                    email=form.email.data,
                    password=form.password.data,
                    invite_code=form.invite_code.data,
                    first_name=form.first_name.data or "",
                    last_name=form.last_name.data or "",
                )

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

    return render_template("auth/register.html", form=form)
