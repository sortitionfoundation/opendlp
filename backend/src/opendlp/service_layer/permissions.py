"""ABOUTME: Permission checking utilities for assembly and global role authorization
ABOUTME: Provides functions and decorators for role-based access control throughout the system"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole

from .exceptions import InsufficientPermissions


def can_manage_assembly(user: User, assembly: Assembly) -> bool:
    """
    Check if user can manage (edit/delete) an assembly.

    Args:
        user: User to check permissions for
        assembly: Assembly to check permissions on

    Returns:
        True if user can manage the assembly
    """
    # Global admins can manage all assemblies
    if user.global_role == GlobalRole.ADMIN:
        return True

    # Global organisers can manage all assemblies
    if user.global_role == GlobalRole.GLOBAL_ORGANISER:
        return True

    # Check assembly-specific roles
    for role in user.assembly_roles:
        if role.assembly_id == assembly.id and role.role == AssemblyRole.ASSEMBLY_MANAGER:
            return True

    return False


def can_view_assembly(user: User, assembly: Assembly) -> bool:
    """
    Check if user can view an assembly.

    Args:
        user: User to check permissions for
        assembly: Assembly to check permissions on

    Returns:
        True if user can view the assembly
    """
    # Global admins and organisers can view all assemblies
    if user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
        return True

    # Check assembly-specific roles
    return any(role.assembly_id == assembly.id for role in user.assembly_roles)


def can_call_confirmations(user: User, assembly: Assembly) -> bool:
    """
    Check if user can call confirmations for an assembly.

    Args:
        user: User to check permissions for
        assembly: Assembly to check permissions on

    Returns:
        True if user can call confirmations
    """
    # Global admins can call confirmations for all assemblies
    if user.global_role == GlobalRole.ADMIN:
        return True

    # Check for confirmation caller role
    for role in user.assembly_roles:
        if role.assembly_id == assembly.id and role.role in (
            AssemblyRole.ASSEMBLY_MANAGER,
            AssemblyRole.CONFIRMATION_CALLER,
        ):
            return True

    return False


def has_global_admin(user: User) -> bool:
    """Check if user has global admin privileges."""
    return user.global_role == GlobalRole.ADMIN


def has_global_organiser(user: User) -> bool:
    """Check if user has global organiser privileges."""
    return user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER)


def require_global_role(required_role: GlobalRole) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to require a specific global role for a service function.

    Args:
        required_role: Minimum global role required

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Expect user as first argument after uow
            if len(args) >= 2:
                user = args[1]  # Assuming uow is first, user is second
                if isinstance(user, User) and not _has_minimum_global_role(user, required_role):
                    raise InsufficientPermissions(action=func.__name__, required_role=required_role.value)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_assembly_permission(
    permission_func: Callable[[User, Assembly], bool],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to require assembly permission for a service function.

    Args:
        permission_func: Function that checks permission (user, assembly) -> bool

    Returns:
        Decorator function

    Usage:
        @require_assembly_permission(can_manage_assembly)
        def update_assembly(uow, user_id, assembly_id, **updates):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract UoW, user_id, and assembly_id from arguments
            # Expect signature: func(uow, user_id, assembly_id, ...)
            if len(args) >= 3:
                uow, user_id, assembly_id = args[0], args[1], args[2]

                # Get user and assembly from repositories
                user = uow.users.get(user_id)
                if not user:
                    raise ValueError(f"User {user_id} not found")

                assembly = uow.assemblies.get(assembly_id)
                if not assembly:
                    raise ValueError(f"Assembly {assembly_id} not found")

                # Check permission using the provided function
                if not permission_func(user, assembly):
                    raise InsufficientPermissions(
                        action=func.__name__, required_role=f"permission check: {permission_func.__name__}"
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def _has_minimum_global_role(user: User, required_role: GlobalRole) -> bool:
    """
    Check if user has at least the required global role.

    Role hierarchy: ADMIN > GLOBAL_ORGANISER > USER
    """
    role_hierarchy = {
        GlobalRole.USER: 0,
        GlobalRole.GLOBAL_ORGANISER: 1,
        GlobalRole.ADMIN: 2,
    }

    user_level = role_hierarchy.get(user.global_role, 0)
    required_level = role_hierarchy.get(required_role, 0)

    return user_level >= required_level
