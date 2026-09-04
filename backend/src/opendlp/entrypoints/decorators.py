"""ABOUTME: Authentication and authorization decorators for Flask routes
ABOUTME: Provides role-based access control decorators for global and assembly-specific permissions"""

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import structlog
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from opendlp.bootstrap import get_flask_uow
from opendlp.domain.value_objects import GlobalRole, get_role_level
from opendlp.feature_flags import has_feature
from opendlp.service_layer.permissions import (
    can_create_assembly,
    can_manage_assembly,
)
from opendlp.translations import _

F = TypeVar("F", bound=Callable[..., Any])


logger = structlog.get_logger(__name__)


def require_feature(flag_name: str) -> Callable[[F], F]:
    """Decorator that returns 404 unless the named feature flag is enabled.

    Args:
        flag_name: Name of the feature flag (without the FF_ prefix) to require

    Returns:
        Decorator function that enforces the feature flag requirement
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not has_feature(flag_name):
                abort(404)
            return f(*args, **kwargs)

        return decorated_function  # type: ignore[return-value]

    return decorator


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

            # Check global role hierarchy: ADMIN > ORGANISER > USER
            user_role_level = get_role_level(current_user.global_role)
            required_role_level = get_role_level(required_role)

            if user_role_level < required_role_level:
                logger.warning(
                    f"User {current_user.id} attempted to access {request.endpoint} "
                    f"with role {current_user.global_role} (required: {required_role})"
                )
                abort(403)

            return f(*args, **kwargs)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_admin[F: Callable[..., Any]](f: F) -> F:
    """Decorator that requires admin role."""
    return require_global_role(GlobalRole.ADMIN)(f)


def require_capability(check: Callable[[Any], bool]) -> Callable[[F], F]:
    """Decorator that requires a global capability, named rather than a role.

    Args:
        check: A capability function from service_layer.permissions taking a user

    Returns:
        Decorator function that enforces the capability
    """

    def decorator(f: F) -> F:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if not current_user.is_authenticated:
                flash(_("Please sign in to access this page."), "error")
                return redirect(url_for("auth.login", next=request.url))

            if not check(current_user):
                logger.warning(
                    "User denied a capability",
                    user_id=str(current_user.id),
                    capability=check.__name__,
                    endpoint=request.endpoint,
                )
                abort(403)

            return f(*args, **kwargs)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_create_assembly[F: Callable[..., Any]](f: F) -> F:
    """Decorator that requires the capability to create an assembly."""
    return require_capability(can_create_assembly)(f)


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
                logger.error(f"No assembly_id found for permission check in {request.endpoint}")
                abort(400)

            try:
                assembly_uuid = uuid.UUID(str(assembly_id))

                uow = get_flask_uow()
                with uow:
                    assembly = uow.assemblies.get(assembly_uuid)
                    if not assembly:
                        abort(404)

                    if not permission_func(current_user, assembly):
                        logger.warning(
                            f"User {current_user.id} denied access to assembly {assembly_id} at {request.endpoint}"
                        )
                        abort(403)

                return f(*args, **kwargs)

            except (ValueError, TypeError):
                abort(400)

        return decorated_function  # type: ignore[return-value]

    return decorator


def require_assembly_management[F: Callable[..., Any]](f: F) -> F:
    """Decorator that requires assembly management permission."""
    return require_assembly_permission(can_manage_assembly)(f)
