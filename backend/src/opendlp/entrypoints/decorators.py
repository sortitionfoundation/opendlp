"""ABOUTME: Authentication and authorization decorators for Flask routes
ABOUTME: Provides role-based access control decorators for global and assembly-specific permissions"""

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user

from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.permissions import (
    can_call_confirmations,
    can_manage_assembly,
    can_view_assembly,
    has_global_admin,
    has_global_organiser,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.translations import _

F = TypeVar("F", bound=Callable[..., Any])


def require_global_role(required_role: GlobalRole) -> Callable[[F], F]:
    """Decorator that requires a minimum global role level.

    Args:
        required_role: The minimum global role required

    Returns:
        Decorator function that enforces the role requirement
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not current_user.is_authenticated:
                flash(_("Please sign in to access this page."), "error")
                return redirect(url_for("auth.login", next=request.url))

            # Check global role hierarchy: ADMIN > GLOBAL_ORGANISER > USER
            user_role_level = _get_role_level(current_user.global_role)
            required_role_level = _get_role_level(required_role)

            if user_role_level < required_role_level:
                current_app.logger.warning(
                    f"User {current_user.id} attempted to access {request.endpoint} "
                    f"with role {current_user.global_role} (required: {required_role})"
                )
                abort(403)

            return f(*args, **kwargs)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_admin(f: F) -> F:
    """Decorator that requires admin role."""
    return require_global_role(GlobalRole.ADMIN)(f)


def require_global_organiser(f: F) -> F:
    """Decorator that requires global organiser role or higher."""
    return require_global_role(GlobalRole.GLOBAL_ORGANISER)(f)


def require_assembly_permission(permission_func: Callable) -> Callable[[F], F]:
    """Decorator that requires specific assembly permission.

    Args:
        permission_func: Function that checks permission (user, assembly) -> bool

    Returns:
        Decorator that enforces the permission for assembly_id parameter
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not current_user.is_authenticated:
                flash(_("Please sign in to access this page."), "error")
                return redirect(url_for("auth.login", next=request.url))

            # Extract assembly_id from kwargs or args
            assembly_id = kwargs.get("assembly_id")
            if not assembly_id:
                # Try to get from URL parameters
                assembly_id = request.view_args.get("assembly_id") if request.view_args else None

            if not assembly_id:
                current_app.logger.error(f"No assembly_id found for permission check in {request.endpoint}")
                abort(400)

            try:
                assembly_uuid = uuid.UUID(str(assembly_id))

                with SqlAlchemyUnitOfWork() as uow:
                    assembly = uow.assemblies.get(assembly_uuid)
                    if not assembly:
                        abort(404)

                    if not permission_func(current_user, assembly):
                        current_app.logger.warning(
                            f"User {current_user.id} denied access to assembly {assembly_id} at {request.endpoint}"
                        )
                        abort(403)

                return f(*args, **kwargs)

            except (ValueError, TypeError):
                abort(400)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_assembly_view(f: F) -> F:
    """Decorator that requires assembly view permission."""
    return require_assembly_permission(can_view_assembly)(f)


def require_assembly_management(f: F) -> F:
    """Decorator that requires assembly management permission."""
    return require_assembly_permission(can_manage_assembly)(f)


def require_confirmation_calling(f: F) -> F:
    """Decorator that requires confirmation calling permission."""
    return require_assembly_permission(can_call_confirmations)(f)


def require_assembly_role(required_role: AssemblyRole) -> Callable[[F], F]:
    """Decorator that requires specific assembly role.

    Args:
        required_role: The assembly role required

    Returns:
        Decorator that enforces the assembly role requirement
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not current_user.is_authenticated:
                flash(_("Please sign in to access this page."), "error")
                return redirect(url_for("auth.login", next=request.url))

            # Extract assembly_id from kwargs or URL
            assembly_id = kwargs.get("assembly_id") or (
                request.view_args.get("assembly_id") if request.view_args else None
            )
            if not assembly_id:
                abort(400)

            try:
                assembly_uuid = uuid.UUID(str(assembly_id))

                # Check if user has global admin/organiser privileges (bypass assembly role)
                if has_global_admin(current_user) or has_global_organiser(current_user):
                    return f(*args, **kwargs)

                # Check specific assembly role
                user_has_role = any(
                    role.assembly_id == assembly_uuid and role.role == required_role
                    for role in current_user.assembly_roles
                )

                if not user_has_role:
                    current_app.logger.warning(
                        f"User {current_user.id} missing role {required_role} "
                        f"for assembly {assembly_id} at {request.endpoint}"
                    )
                    abort(403)

                return f(*args, **kwargs)

            except (ValueError, TypeError):
                abort(400)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_assembly_manager(f: F) -> F:
    """Decorator that requires assembly manager role."""
    return require_assembly_role(AssemblyRole.ASSEMBLY_MANAGER)(f)


def require_confirmation_caller(f: F) -> F:
    """Decorator that requires confirmation caller role."""
    return require_assembly_role(AssemblyRole.CONFIRMATION_CALLER)(f)


def _get_role_level(role: GlobalRole) -> int:
    """Get numeric level for role comparison."""
    role_levels = {
        GlobalRole.USER: 1,
        GlobalRole.GLOBAL_ORGANISER: 2,
        GlobalRole.ADMIN: 3,
    }
    return role_levels.get(role, 0)
