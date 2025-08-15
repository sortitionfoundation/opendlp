"""ABOUTME: JSON API endpoints for authentication operations
ABOUTME: Provides REST API endpoints for login, logout, registration, and authentication status"""

from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user

from opendlp.service_layer.exceptions import InvalidCredentials, InvalidInvite, PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import authenticate_user, create_user
from opendlp.translations import _

api_auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")


@api_auth_bp.route("/status", methods=["GET"])
def auth_status() -> ResponseReturnValue:
    """Get current authentication status."""
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user": {
                "id": str(current_user.id),
                "email": current_user.email,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "global_role": current_user.global_role.value,
                "display_name": current_user.display_name,
            },
        })
    else:
        return jsonify({"authenticated": False})


@api_auth_bp.route("/login", methods=["POST"])
def api_login() -> ResponseReturnValue:
    """API login endpoint."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        email = data.get("email", "").strip()
        password = data.get("password", "")
        remember = data.get("remember", False)

        if not email or not password:
            return jsonify({"error": _("Email and password are required")}), 400

        with SqlAlchemyUnitOfWork() as uow:
            user = authenticate_user(uow, email, password)
            login_user(user, remember=remember)

            return jsonify({
                "success": True,
                "message": _("Login successful"),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "global_role": user.global_role.value,
                    "display_name": user.display_name,
                },
            })

    except InvalidCredentials:
        return jsonify({"error": _("Invalid email or password")}), 401

    except Exception as e:
        current_app.logger.error(f"API login error: {e}")
        return jsonify({"error": _("An error occurred during login")}), 500


@api_auth_bp.route("/logout", methods=["POST"])
@login_required
def api_logout() -> ResponseReturnValue:
    """API logout endpoint."""
    try:
        logout_user()
        return jsonify({"success": True, "message": _("Logout successful")})

    except Exception as e:
        current_app.logger.error(f"API logout error: {e}")
        return jsonify({"error": _("An error occurred during logout")}), 500


@api_auth_bp.route("/register", methods=["POST"])
def api_register() -> ResponseReturnValue:
    """API registration endpoint."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        # Extract required fields
        invite_code = data.get("invite_code", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()

        # Validate required fields
        if not all([email, password, invite_code]):
            return jsonify({"error": _("Email, password, and invite code are required")}), 400

        with SqlAlchemyUnitOfWork() as uow:
            user = create_user(
                uow=uow,
                email=email,
                password=password,
                invite_code=invite_code,
                first_name=first_name,
                last_name=last_name,
            )

            # Log the user in immediately after registration
            login_user(user)

            return jsonify({
                "success": True,
                "message": _("Registration successful"),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "global_role": user.global_role.value,
                    "display_name": user.display_name,
                },
            }), 201

    except UserAlreadyExists as e:
        return jsonify({"error": str(e)}), 409

    except InvalidInvite as e:
        return jsonify({"error": str(e)}), 400

    except PasswordTooWeak as e:
        return jsonify({"error": _("Password is too weak: %(error)s", error=str(e))}), 400

    except Exception as e:
        current_app.logger.error(f"API registration error: {e}")
        return jsonify({"error": _("An error occurred during registration")}), 500


@api_auth_bp.route("/validate-invite", methods=["POST"])
def api_validate_invite() -> ResponseReturnValue:
    """API endpoint to validate an invite code."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        invite_code = data.get("invite_code", "").strip()
        if not invite_code:
            return jsonify({"error": _("Invite code is required")}), 400

        with SqlAlchemyUnitOfWork() as uow:
            invite = uow.user_invites.get_by_code(invite_code)

            if not invite:
                return jsonify({"valid": False, "error": _("Invite code not found")}), 404

            if not invite.is_valid():
                return jsonify({"valid": False, "error": _("Invite code has expired or been used")}), 400

            return jsonify({
                "valid": True,
                "global_role": invite.global_role.value,
                "expires_at": invite.expires_at.isoformat(),
            })

    except Exception as e:
        current_app.logger.error(f"API invite validation error: {e}")
        return jsonify({"error": _("An error occurred validating the invite")}), 500


@api_auth_bp.route("/check-email", methods=["POST"])
def api_check_email() -> ResponseReturnValue:
    """API endpoint to check if an email is available."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        email = data.get("email", "").strip()
        if not email:
            return jsonify({"error": _("Email is required")}), 400

        with SqlAlchemyUnitOfWork() as uow:
            existing_user = uow.users.get_by_email(email)

            return jsonify({
                "available": existing_user is None,
                "message": _("Email is available") if existing_user is None else _("Email is already registered"),
            })

    except Exception as e:
        current_app.logger.error(f"API email check error: {e}")
        return jsonify({"error": _("An error occurred checking the email")}), 500


@api_auth_bp.route("/user", methods=["GET"])
@login_required
def api_current_user() -> ResponseReturnValue:
    """Get current user information."""
    return jsonify({
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "global_role": current_user.global_role.value,
            "display_name": current_user.display_name,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat(),
            "assembly_roles": [
                {
                    "assembly_id": str(role.assembly_id),
                    "role": role.role.value,
                    "created_at": role.created_at.isoformat(),
                }
                for role in current_user.assembly_roles
            ],
        }
    })


@api_auth_bp.errorhandler(404)
def api_not_found(error: Exception) -> ResponseReturnValue:
    """Handle 404 errors for API endpoints."""
    return jsonify({"error": "Endpoint not found"}), 404


@api_auth_bp.errorhandler(405)
def api_method_not_allowed(error: Exception) -> ResponseReturnValue:
    """Handle 405 errors for API endpoints."""
    return jsonify({"error": "Method not allowed"}), 405


@api_auth_bp.errorhandler(500)
def api_internal_error(error: Exception) -> ResponseReturnValue:
    """Handle 500 errors for API endpoints."""
    return jsonify({"error": "Internal server error"}), 500
