"""ABOUTME: User management service layer with business logic for user operations
ABOUTME: Handles user creation, authentication, role assignment, and invite validation"""

import uuid

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole

from .exceptions import (
    InsufficientPermissions,
    InvalidCredentials,
    InvalidInvite,
    PasswordTooWeak,
    ServiceLayerError,
    UserAlreadyExists,
)
from .permissions import can_manage_assembly, has_global_admin
from .security import TempUser, hash_password, validate_password_strength, verify_password
from .unit_of_work import AbstractUnitOfWork


def create_user(
    uow: AbstractUnitOfWork,
    email: str,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
    oauth_provider: str | None = None,
    oauth_id: str | None = None,
    invite_code: str | None = None,
    global_role: GlobalRole | None = None,
    is_active: bool = True,
    accept_data_agreement: bool = False,
) -> User:
    """
    Create a new user with proper validation.

    Args:
        uow: Unit of Work for database operations
        email: User's email address
        password: Plain text password (will be hashed)
        first_name: User's first name (optional)
        last_name: User's last name (optional)
        oauth_provider: OAuth provider (e.g., 'google')
        oauth_id: OAuth provider user ID
        invite_code: invite code for registration
        global_role: role for the user
        accept_data_agreement: whether user has accepted data agreement

    Returns:
        Created User instance

    Raises:
        UserAlreadyExists: If email already exists
        InvalidInvite: If invite code is invalid/expired/used
        ValueError: If password validation fails
    """
    if global_role and invite_code:
        raise ServiceLayerError("create_user: Cannot have both invite_code and global_role")
    if not global_role and not invite_code:
        raise ServiceLayerError("create_user: Need either invite_code or global_role")
    with uow:
        # Check for existing users
        existing_user = uow.users.get_by_email(email)
        if existing_user:
            raise UserAlreadyExists(email=email)

        # temporary user to pass to password validation
        temp_user = TempUser(email=email, first_name=first_name, last_name=last_name)

        # Handle password validation and hashing
        password_hash = None
        if password:
            is_valid, error_msg = validate_password_strength(password, temp_user)
            if not is_valid:
                raise PasswordTooWeak(error_msg)
            password_hash = hash_password(password)

        # Validate invite code (but don't mark as used yet)
        # Do this AFTER checking the password, so the invite validation happens
        # before creating the user, but we mark it as used only after user creation succeeds.
        user_role = validate_invite(uow, invite_code) if invite_code else global_role
        assert isinstance(user_role, GlobalRole)

        # Create the user
        user = User(
            email=email,
            global_role=user_role,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
            is_active=is_active,
        )

        # Mark data agreement as accepted if provided
        if accept_data_agreement:
            user.mark_data_agreement_agreed()

        uow.users.add(user)

        # Mark invite as used now that user creation succeeded
        if invite_code:
            use_invite(uow, invite_code, user.id)

        detached_user = user.create_detached_copy()
        uow.commit()
        return detached_user


def authenticate_user(uow: AbstractUnitOfWork, email: str, password: str) -> User:
    """
    Authenticate a user with email and password.

    Args:
        uow: Unit of Work for database operations
        email: User's email address
        password: Plain text password

    Returns:
        Authenticated User instance

    Raises:
        InvalidCredentials: If authentication fails
    """
    with uow:
        user = uow.users.get_by_email(email)

        if not user or not user.is_active:
            raise InvalidCredentials()

        if not user.password_hash or not verify_password(password, user.password_hash):
            raise InvalidCredentials()

        return user.create_detached_copy()


def get_user_assemblies(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> list[Assembly]:
    """Get all assemblies a user has access to."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Global admins and organisers can see all assemblies
        if user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
            return list(uow.assemblies.get_active_assemblies())

        # Regular users see only assemblies they have specific roles for
        return list(uow.assemblies.get_assemblies_for_user(user_id))


def assign_assembly_role(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    role: AssemblyRole,
) -> UserAssemblyRole:
    """
    Assign an assembly role to a user.

    Args:
        uow: Unit of Work for database operations
        user_id: User to assign role to
        assembly_id: Assembly for the role
        role: Role to assign

    Returns:
        Created UserAssemblyRole instance
    """
    # TODO: consider if we want a user to have multiple roles
    # Maybe we need to have two roles where one is not a superset of the other?
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Check if role already exists
        existing_role = next((r for r in user.assembly_roles if r.assembly_id == assembly_id), None)

        if existing_role:
            # Update existing role
            assert isinstance(existing_role, UserAssemblyRole)
            existing_role.role = role
            assembly_role = existing_role
        else:
            # Create new role
            assembly_role = UserAssemblyRole(
                user_id=user_id,
                assembly_id=assembly_id,
                role=role,
            )
            user.assembly_roles.append(assembly_role)

        uow.commit()
        return assembly_role


def validate_invite(uow: AbstractUnitOfWork, invite_code: str) -> GlobalRole:
    """
    Validate an invite code without marking it as used.

    Args:
        uow: Unit of Work for database operations
        invite_code: The invite code to validate

    Returns:
        GlobalRole that the invite grants

    Raises:
        InvalidInvite: If invite is invalid, expired, or already used
    """
    # Note this is called from create_user() inside a `with uow:` block
    # so we don't need a `with uow:` block in this function.
    invite = uow.user_invites.get_by_code(invite_code)
    if not invite:
        raise InvalidInvite(invite_code, "Invite code not found")

    if not invite.is_valid():
        if invite.used_by:
            raise InvalidInvite(invite_code, "Invite code already used")
        else:
            raise InvalidInvite(invite_code, "Invite code expired")

    return invite.global_role


def use_invite(uow: AbstractUnitOfWork, invite_code: str, user_id: uuid.UUID) -> None:
    """
    Mark an invite code as used by a user.

    Args:
        uow: Unit of Work for database operations
        invite_code: The invite code to mark as used
        user_id: ID of the user using the invite

    Raises:
        InvalidInvite: If invite is not found
        ValueError: If invite is already used or invalid
    """
    # Note this is called from create_user() inside a `with uow:` block
    # so we don't need a `with uow:` block in this function.
    invite = uow.user_invites.get_by_code(invite_code)
    if not invite:
        raise InvalidInvite(invite_code, "Invite code not found")

    invite.use(user_id)


def validate_and_use_invite(uow: AbstractUnitOfWork, invite_code: str, user_id: uuid.UUID | None = None) -> GlobalRole:
    """
    Validate an invite code and optionally mark it as used.

    DEPRECATED: Use validate_invite() and use_invite() separately for clearer logic.

    Args:
        uow: Unit of Work for database operations
        invite_code: The invite code to validate
        user_id: Optional user ID if marking as used

    Returns:
        GlobalRole that the invite grants

    Raises:
        InvalidInvite: If invite is invalid, expired, or already used
    """
    role = validate_invite(uow, invite_code)
    if user_id:
        use_invite(uow, invite_code, user_id)
    return role


def find_or_create_oauth_user(
    uow: AbstractUnitOfWork,
    provider: str,
    oauth_id: str,
    email: str,
    first_name: str = "",
    last_name: str = "",
    invite_code: str | None = None,
    accept_data_agreement: bool = False,
) -> tuple[User, bool]:
    """
    Find existing OAuth user or create new one.

    Args:
        uow: Unit of Work for database operations
        provider: OAuth provider (e.g., 'google')
        oauth_id: Provider's user ID
        email: User's email from OAuth
        first_name: User's first name from OAuth
        last_name: User's last name from OAuth
        invite_code: Required for new user creation
        accept_data_agreement: whether user has accepted data agreement

    Returns:
        Tuple of (User, created_flag) where created_flag is True if user was created
    """
    with uow:
        # Check for existing OAuth user
        existing_user = uow.users.get_by_oauth_credentials(provider, oauth_id)
        if existing_user:
            return existing_user, False

        # Check for existing user with same email (potential account linking)
        existing_user = uow.users.get_by_email(email)
        if existing_user:
            # Link OAuth to existing account
            existing_user.oauth_provider = provider
            existing_user.oauth_id = oauth_id
            uow.commit()
            return existing_user, False

        # Create new user
        user = create_user(
            uow=uow,
            email=email,
            first_name=first_name,
            last_name=last_name,
            oauth_provider=provider,
            oauth_id=oauth_id,
            invite_code=invite_code,
            accept_data_agreement=accept_data_agreement,
        )
        return user.create_detached_copy(), True


def list_users_paginated(
    uow: AbstractUnitOfWork,
    admin_user_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
    role_filter: str | None = None,
    active_filter: bool | None = None,
    search_term: str | None = None,
) -> tuple[list[User], int, int]:
    """
    List users with pagination and filtering (admin only).

    Args:
        uow: Unit of Work for database operations
        admin_user_id: ID of admin user requesting the list
        page: Page number (1-indexed)
        per_page: Number of results per page
        role_filter: Filter by global role
        active_filter: Filter by active status
        search_term: Search term for email/name

    Returns:
        Tuple of (users list, total count, total pages)

    Raises:
        ValueError: If admin user not found
        InsufficientPermissions: If user is not admin
    """
    with uow:
        admin_user = uow.users.get(admin_user_id)
        if not admin_user:
            raise ValueError(f"User {admin_user_id} not found")

        if not has_global_admin(admin_user):
            raise InvalidCredentials("Only admins can list all users")

        # Calculate offset
        offset = (page - 1) * per_page

        # Get paginated users
        users, total_count = uow.users.filter_paginated(
            role=role_filter,
            active=active_filter,
            search=search_term,
            limit=per_page,
            offset=offset,
        )

        # Calculate total pages
        total_pages = (total_count + per_page - 1) // per_page

        return [user.create_detached_copy() for user in users], total_count, total_pages


def get_user_by_id(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> User:
    """
    Get a user by ID (admin only).

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to fetch
        admin_user_id: ID of admin user requesting the data

    Returns:
        User instance

    Raises:
        ValueError: If user not found
        InsufficientPermissions: If requesting user is not admin
    """
    with uow:
        admin_user = uow.users.get(admin_user_id)
        if not admin_user:
            raise ValueError(f"Admin user {admin_user_id} not found")

        if not has_global_admin(admin_user):
            raise InvalidCredentials("Only admins can view user details")

        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        assert isinstance(user, User)
        return user.create_detached_copy()


def update_user(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    first_name: str | None = None,
    last_name: str | None = None,
    global_role: GlobalRole | None = None,
    is_active: bool | None = None,
) -> User:
    """
    Update user details (admin only).

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to update
        admin_user_id: ID of admin performing the update
        first_name: New first name
        last_name: New last name
        global_role: New global role
        is_active: New active status

    Returns:
        Updated User instance

    Raises:
        ValueError: If user not found or invalid update
        InsufficientPermissions: If requesting user is not admin
    """
    with uow:
        admin_user = uow.users.get(admin_user_id)
        if not admin_user:
            raise ValueError(f"Admin user {admin_user_id} not found")

        if not has_global_admin(admin_user):
            raise InvalidCredentials("Only admins can update users")

        user = uow.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        assert isinstance(user, User)

        # Prevent admin from changing their own role (avoid lockout)
        if user_id == admin_user_id and global_role is not None and global_role != user.global_role:
            raise ValueError("Cannot change your own admin role")

        # Prevent admin from deactivating themselves
        if user_id == admin_user_id and is_active is False:
            raise ValueError("Cannot deactivate your own account")

        # Apply updates
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if global_role is not None:
            user.global_role = global_role
        if is_active is not None:
            user.is_active = is_active

        detached_user = user.create_detached_copy()
        uow.commit()
        return detached_user


def get_user_stats(uow: AbstractUnitOfWork, admin_user_id: uuid.UUID) -> dict[str, int]:
    """
    Get user statistics (admin only).

    Args:
        uow: Unit of Work for database operations
        admin_user_id: ID of admin user requesting stats

    Returns:
        Dictionary with user statistics

    Raises:
        ValueError: If admin user not found
        InsufficientPermissions: If requesting user is not admin
    """
    with uow:
        admin_user = uow.users.get(admin_user_id)
        if not admin_user:
            raise ValueError(f"Admin user {admin_user_id} not found")

        if not has_global_admin(admin_user):
            raise InvalidCredentials("Only admins can view user statistics")

        all_users = list(uow.users.all())

        return {
            "total_users": len(all_users),
            "active_users": len([u for u in all_users if u.is_active]),
            "inactive_users": len([u for u in all_users if not u.is_active]),
            "admin_users": len([u for u in all_users if u.global_role == GlobalRole.ADMIN]),
            "organiser_users": len([u for u in all_users if u.global_role == GlobalRole.GLOBAL_ORGANISER]),
            "regular_users": len([u for u in all_users if u.global_role == GlobalRole.USER]),
        }


def grant_user_assembly_role(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    role: AssemblyRole,
    current_user: User,
) -> UserAssemblyRole:
    """
    Grant or update a user's role on an assembly.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to grant role to
        assembly_id: ID of assembly
        role: Role to assign
        current_user: User performing the action (must have permission)

    Returns:
        Created or updated UserAssemblyRole instance

    Raises:
        InsufficientPermissions: If current_user lacks permission to grant roles
        ValueError: If user or assembly not found
    """
    with uow:
        # Check permissions: must be admin or global organiser or assembly manager
        if not has_global_admin(current_user):
            # Load the assembly to check if user can manage it
            assembly = uow.assemblies.get(assembly_id)
            if not assembly:
                raise ValueError(f"Assembly {assembly_id} not found")

            if not can_manage_assembly(current_user, assembly):
                raise InsufficientPermissions(
                    action="grant_user_assembly_role",
                    required_role="admin, global-organiser, or assembly manager",
                )

        # Validate target user exists
        target_user = uow.users.get(user_id)
        if not target_user:
            raise ValueError(f"User {user_id} not found")

        # Validate assembly exists
        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Check if role already exists
        existing_role = next(
            (r for r in target_user.assembly_roles if r.assembly_id == assembly_id),
            None,
        )

        if existing_role:
            # Update existing role
            assert isinstance(existing_role, UserAssemblyRole)
            existing_role.role = role
            assembly_role = existing_role
        else:
            # Create new role
            assembly_role = UserAssemblyRole(
                user_id=user_id,
                assembly_id=assembly_id,
                role=role,
            )
            uow.user_assembly_roles.add(assembly_role)
            target_user.assembly_roles.append(assembly_role)

        uow.commit()
        return assembly_role


def revoke_user_assembly_role(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    current_user: User,
) -> UserAssemblyRole:
    """
    Revoke a user's role on an assembly.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to revoke role from
        assembly_id: ID of assembly
        current_user: User performing the action (must have permission)

    Returns:
        The revoked UserAssemblyRole instance

    Raises:
        InsufficientPermissions: If current_user lacks permission to revoke roles
        ValueError: If user, assembly, or role not found
    """
    with uow:
        # Check permissions: must be admin or global organiser or assembly manager
        if not has_global_admin(current_user):
            # Load the assembly to check if user can manage it
            assembly = uow.assemblies.get(assembly_id)
            if not assembly:
                raise ValueError(f"Assembly {assembly_id} not found")

            if not can_manage_assembly(current_user, assembly):
                raise InsufficientPermissions(
                    action="revoke_user_assembly_role",
                    required_role="admin, global-organiser, or assembly manager",
                )

        # Validate target user exists
        target_user = uow.users.get(user_id)
        if not target_user:
            raise ValueError(f"User {user_id} not found")

        # Validate assembly exists
        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise ValueError(f"Assembly {assembly_id} not found")

        # Find the role to revoke
        existing_role = next(
            (r for r in target_user.assembly_roles if r.assembly_id == assembly_id),
            None,
        )

        if not existing_role:
            raise ValueError(f"User {user_id} has no role on assembly {assembly_id}")
        assert isinstance(existing_role, UserAssemblyRole)

        # Remove the role
        target_user.assembly_roles.remove(existing_role)
        uow.user_assembly_roles.remove_role(user_id, assembly_id)

        uow.commit()
        return existing_role
