"""ABOUTME: User management service layer with business logic for user operations
ABOUTME: Handles user creation, authentication, role assignment, and invite validation"""

import uuid

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole

from .exceptions import InvalidCredentials, InvalidInvite, PasswordTooWeak, UserAlreadyExists
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
        invite_code: Required invite code for registration

    Returns:
        Created User instance

    Raises:
        UserAlreadyExists: If email already exists
        InvalidInvite: If invite code is invalid/expired/used
        ValueError: If password validation fails
    """
    with uow:
        # Check for existing users
        existing_user = uow.users.get_by_email(email)
        if existing_user:
            raise UserAlreadyExists(email=email)

        # Validate and use invite code
        invite_role = GlobalRole.USER  # default
        if invite_code:
            invite_role = validate_and_use_invite(uow, invite_code)

        # temporary user to pass to password validation
        temp_user = TempUser(email=email, first_name=first_name, last_name=last_name)

        # Handle password validation and hashing
        password_hash = None
        if password:
            is_valid, error_msg = validate_password_strength(password, temp_user)
            if not is_valid:
                raise PasswordTooWeak(error_msg)
            password_hash = hash_password(password)

        # Create the user
        user = User(
            email=email,
            global_role=invite_role,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
        )

        uow.users.add(user)
        uow.commit()
        return user


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

        return user


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


def validate_and_use_invite(uow: AbstractUnitOfWork, invite_code: str, user_id: uuid.UUID | None = None) -> GlobalRole:
    """
    Validate an invite code and mark it as used.

    Args:
        uow: Unit of Work for database operations
        invite_code: The invite code to validate
        user_id: Optional user ID if marking as used

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

    # Mark as used if user_id provided
    if user_id:
        invite.use(user_id)

    return invite.global_role


def find_or_create_oauth_user(
    uow: AbstractUnitOfWork,
    provider: str,
    oauth_id: str,
    email: str,
    first_name: str = "",
    last_name: str = "",
    invite_code: str | None = None,
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
        )
        return user, True
