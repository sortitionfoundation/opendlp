"""ABOUTME: Permission checking utilities for assembly and global role authorization
ABOUTME: Provides functions and decorators for role-based access control throughout the system"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, get_role_level

from .exceptions import AssemblyNotFoundError, InsufficientPermissions, UserNotFoundError


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


def can_edit_respondent(user: User, assembly: Assembly) -> bool:
    """Who can edit respondent attributes via the backoffice edit page."""
    if user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
        return True
    for role in user.assembly_roles:
        if role.assembly_id == assembly.id and role.role in (
            AssemblyRole.ASSEMBLY_MANAGER,
            AssemblyRole.CONFIRMATION_CALLER,
        ):
            return True
    return False


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


# Capability functions. Ask one of these rather than comparing global roles, so
# a future permissions refactor has one file to replace. Every capability has
# one of two shapes: (user) -> bool, or (user, assembly) -> bool.


def can_create_assembly(user: User) -> bool:
    """Whether the user may create a new assembly."""
    return user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER)


def can_see_all_assemblies(user: User) -> bool:
    """Whether the user sees every assembly, rather than only those they hold a role on."""
    return user.global_role == GlobalRole.ADMIN


def can_administer_site(user: User) -> bool:
    """Whether the user may manage users, invites and the site admin UI."""
    return has_global_admin(user)


def can_manage_assembly_members(user: User, assembly: Assembly) -> bool:
    """Whether the user may add and remove members of this assembly."""
    return can_manage_assembly(user, assembly)


@dataclass(frozen=True)
class UserCapabilities:
    """The global capabilities of one user, in the form templates ask for them.

    Injected into every template context as `perms`, including for anonymous
    visitors, so a template never has to check `current_user.is_authenticated`
    before asking what is permitted.
    """

    create_assembly: bool = False
    see_all_assemblies: bool = False
    administer_site: bool = False


NO_CAPABILITIES = UserCapabilities()


def capabilities_for(user: User) -> UserCapabilities:
    """Gather one user's global capabilities for template use."""
    return UserCapabilities(
        create_assembly=can_create_assembly(user),
        see_all_assemblies=can_see_all_assemblies(user),
        administer_site=can_administer_site(user),
    )


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
                user_level = get_role_level(user.global_role)
                required_level = get_role_level(required_role)
                if isinstance(user, User) and user_level < required_level:
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
                    raise UserNotFoundError(f"User {user_id} not found")

                assembly = uow.assemblies.get(assembly_id)
                if not assembly:
                    raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

                # Check permission using the provided function
                if not permission_func(user, assembly):
                    raise InsufficientPermissions(
                        action=func.__name__, required_role=f"permission check: {permission_func.__name__}"
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator
