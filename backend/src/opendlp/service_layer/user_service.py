"""ABOUTME: User management service layer with business logic for user operations
ABOUTME: Handles user creation, authentication, role assignment, and invite validation"""

import uuid
from datetime import UTC, datetime

import structlog

from opendlp.adapters.email import EmailAdapter
from opendlp.adapters.template_renderer import TemplateRenderer
from opendlp.adapters.url_generator import URLGenerator
from opendlp.domain.assembly import Assembly
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, assembly_role_options

from . import two_factor_service
from .email_confirmation_service import create_confirmation_token
from .exceptions import (
    AssemblyNotFoundError,
    CannotDisableSelf,
    CannotRemoveLastAuthMethod,
    EmailNotConfirmed,
    InsufficientPermissions,
    InvalidCredentials,
    InvalidInvite,
    NotFoundError,
    PasswordTooWeak,
    ServiceLayerError,
    UserAlreadyExists,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly, has_global_admin
from .security import TempUser, hash_password, validate_password_strength, verify_password
from .unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)


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
    auto_confirm_email: bool = False,
) -> tuple[User, EmailConfirmationToken | None]:
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
        auto_confirm_email: if True, mark email as confirmed immediately
            (used for CLI-created users where no confirmation email is sent)

    Returns:
        Tuple of (User instance, EmailConfirmationToken or None)
        Token is None for OAuth users or auto-confirmed users

    Raises:
        UserAlreadyExists: If email already exists
        InvalidInvite: If invite code is invalid/expired/used
        ValueError: If password validation fails

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if global_role and invite_code:
        raise ServiceLayerError("create_user: Cannot have both invite_code and global_role")
    if not global_role and not invite_code:
        raise ServiceLayerError("create_user: Need either invite_code or global_role")
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
    # OAuth users and CLI-created users are auto-confirmed
    email_confirmed_at = datetime.now(UTC) if (oauth_provider or auto_confirm_email) else None

    user = User(
        email=email,
        global_role=user_role,
        first_name=first_name,
        last_name=last_name,
        password_hash=password_hash,
        oauth_provider=oauth_provider,
        oauth_id=oauth_id,
        is_active=is_active,
        email_confirmed_at=email_confirmed_at,
    )

    # Mark data agreement as accepted if provided
    if accept_data_agreement:
        user.mark_data_agreement_agreed()

    uow.users.add(user)

    # Mark invite as used now that user creation succeeded
    if invite_code:
        use_invite(uow, invite_code, user.id)

    # Create confirmation token for password users who need email confirmation
    token = None
    if password and not oauth_provider and not auto_confirm_email:
        token = create_confirmation_token(uow, user.id)

    detached_user = user.create_detached_copy()
    detached_token = token.create_detached_copy() if token else None
    return detached_user, detached_token


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
        EmailNotConfirmed: If email is not confirmed

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get_by_email(email)

    if not user or not user.is_active:
        raise InvalidCredentials()

    if not user.password_hash or not verify_password(password, user.password_hash):
        raise InvalidCredentials()

    # Check email confirmation for password users
    if not user.email_confirmed_at:
        raise EmailNotConfirmed()

    return user.create_detached_copy()


def get_user_assemblies(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> list[Assembly]:
    """Get all assemblies a user has access to.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # TODO: consider if we want a user to have multiple roles
    # Maybe we need to have two roles where one is not a superset of the other?
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Note this is called from create_user() inside a `with uow:` block
    # so we don't need a `with uow:` block in this function.
    invite = uow.user_invites.get_by_code(invite_code)
    if not invite:
        raise InvalidInvite(invite_code, "Invite code not found")

    if not invite.is_valid():
        if invite.used_by:
            raise InvalidInvite(invite_code, "Invite code already used")
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
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

    This function handles three scenarios:
    1. OAuth user exists -> return existing user
    2. Email matches existing user -> link OAuth to that account
    3. New user -> create with invite code required

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

    Raises:
        InvalidInvite: If invite code is invalid/expired when creating new user

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Check for existing OAuth user
    existing_user = uow.users.get_by_oauth_credentials(provider, oauth_id)
    if existing_user:
        return existing_user.create_detached_copy(), False

    # Check for existing user with same email (account linking)
    existing_user = uow.users.get_by_email(email)
    if existing_user:
        # Link OAuth to existing account and auto-confirm email
        existing_user.add_oauth_credentials(provider, oauth_id)
        if not existing_user.email_confirmed_at:
            existing_user.confirm_email()
        detached_user = existing_user.create_detached_copy()
        uow.commit()
        return detached_user, False

    # Create new user - invite code required
    if not invite_code:
        raise InvalidInvite(reason="Invite code required for new user registration")

    user, _token = create_user(
        uow=uow,
        email=email,
        first_name=first_name,
        last_name=last_name,
        oauth_provider=provider,
        oauth_id=oauth_id,
        invite_code=invite_code,
        accept_data_agreement=accept_data_agreement,
    )
    # Token will be None for OAuth users (they're auto-confirmed)
    return user, True


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
        UserNotFoundError: If admin user not found
        InsufficientPermissions: If user is not admin

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"User {admin_user_id} not found")

    if not has_global_admin(admin_user):
        raise InsufficientPermissions("Only admins can list all users")

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
        UserNotFoundError: If user not found
        InsufficientPermissions: If requesting user is not admin

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")

    if not has_global_admin(admin_user):
        raise InsufficientPermissions("Only admins can view user details")

    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assert isinstance(user, User)
    return user.create_detached_copy()


def update_user(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    first_name: str | None = None,
    last_name: str | None = None,
    global_role: GlobalRole | None = None,
) -> User:
    """
    Update user details (admin only).

    Enabling and disabling an account is not done here - see `disable_user`
    and `enable_user`, which carry the lockout side effects with them.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to update
        admin_user_id: ID of admin performing the update
        first_name: New first name
        last_name: New last name
        global_role: New global role

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If user not found or invalid update
        InsufficientPermissions: If requesting user is not admin
        ValueError: If operation is not allowed on self

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")

    if not has_global_admin(admin_user):
        raise InsufficientPermissions("Only admins can update users")

    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assert isinstance(user, User)

    # Prevent admin from changing their own role (avoid lockout)
    if user_id == admin_user_id and global_role is not None and global_role != user.global_role:
        raise ValueError("Cannot change your own admin role")

    # Apply updates
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if global_role is not None:
        user.global_role = global_role

    return user.create_detached_copy()


def _target_of_admin_account_action(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> User:
    """Check the admin may enable and disable accounts, and return the one they are acting on."""
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")

    if not has_global_admin(admin_user):
        raise InsufficientPermissions("Only admins can enable or disable users")

    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assert isinstance(user, User)
    return user


def _warn_about_outstanding_invites(uow: AbstractUnitOfWork, user: User) -> None:
    """Log any usable invites the disabled user created, for a sysadmin to review.

    Disabling an account does nothing to invites it has already handed out, so
    someone with the account could still have a route back in through one. We
    log the ids rather than the codes - a code is a credential.
    """
    outstanding = [invite for invite in uow.user_invites.get_invites_created_by(user.id) if invite.is_valid()]
    if not outstanding:
        return

    logger.warning(
        "user.disabled.outstanding_invites",
        user_id=str(user.id),
        invite_count=len(outstanding),
        invite_ids=[str(invite.id) for invite in outstanding],
    )


def disable_user(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> User:
    """
    Lock a user out of the system (admin only).

    Beyond clearing the active flag this ends every session the user has, makes
    their password unusable, clears any 2FA enrolment and invalidates
    outstanding password reset and email confirmation tokens - so an attacker
    holding any of those loses them all at once. Re-enabling the account does
    not undo any of it; the user has to set a new password.

    No email is sent: if we suspect a compromise, whoever has the account may
    also have the mailbox.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to disable
        admin_user_id: ID of admin performing the action

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If either user is not found
        InsufficientPermissions: If requesting user is not admin
        CannotDisableSelf: If the admin is disabling their own account

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = _target_of_admin_account_action(uow, user_id, admin_user_id)

    if user_id == admin_user_id:
        raise CannotDisableSelf()

    if not user.is_active:
        logger.info("user.disabled.already_inactive", user_id=str(user_id), admin_user_id=str(admin_user_id))
        return user.create_detached_copy()

    user.is_active = False
    user.invalidate_sessions()
    user.set_unusable_password()

    uow.password_reset_tokens.invalidate_user_tokens(user_id)
    uow.email_confirmation_tokens.invalidate_user_tokens(user_id)

    # A compromised account is exactly where the enrolled authenticator may be
    # the attacker's, so it goes too. admin_disable_2fa raises rather than
    # no-ops when there is nothing to disable, hence the guard.
    totp_cleared = user.totp_enabled and not user.oauth_provider
    if totp_cleared:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_user_id)

    _warn_about_outstanding_invites(uow, user)

    # The field is "credentials_reset" rather than anything with "password" in
    # the name: censor_pii redacts values under such a key, which would make
    # this line say [REDACTED] instead of what happened.
    logger.warning(
        "user.disabled",
        user_id=str(user_id),
        admin_user_id=str(admin_user_id),
        sessions_invalidated=True,
        credentials_reset=True,
        totp_cleared=totp_cleared,
    )

    return user.create_detached_copy()


def enable_user(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> User:
    """
    Let a previously disabled user back into the system (admin only).

    Deliberately narrow: it sets the active flag and nothing else. In
    particular the session epoch stays where `disable_user` left it, so the
    sessions that were cancelled stay cancelled. The caller is expected to send
    the user the account re-enabled email.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to enable
        admin_user_id: ID of admin performing the action

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If either user is not found
        InsufficientPermissions: If requesting user is not admin

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = _target_of_admin_account_action(uow, user_id, admin_user_id)

    if user.is_active:
        logger.info("user.enabled.already_active", user_id=str(user_id), admin_user_id=str(admin_user_id))
        return user.create_detached_copy()

    user.is_active = True

    logger.warning("user.enabled", user_id=str(user_id), admin_user_id=str(admin_user_id))

    return user.create_detached_copy()


def totp_cleared_by_lockout(uow: AbstractUnitOfWork, user: User) -> bool:
    """Check whether the user's 2FA was cleared by the lockout they are coming out of.

    Used to tell a re-enabled user that they need to enrol again. The 2FA audit
    log is the record of it, so ask that rather than storing the fact twice.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if user.sessions_invalidated_at is None:
        return False

    return any(
        log.action == two_factor_service.ADMIN_DISABLED_ACTION and log.timestamp >= user.sessions_invalidated_at
        for log in uow.two_factor_audit_logs.get_logs_for_user(user.id, limit=10)
    )


def send_account_reenabled_email(
    email_adapter: EmailAdapter,
    template_renderer: TemplateRenderer,
    url_generator: URLGenerator,
    user: User,
    totp_cleared: bool = False,
) -> bool:
    """
    Tell a user their account has been re-enabled, and how to get back in.

    Password users are sent to the forgot password page rather than a reset
    link: their password was made unusable by the lockout, and a token minted
    here would likely expire before they read the email.

    Args:
        email_adapter: Email adapter for sending emails
        template_renderer: Template renderer for rendering email templates
        url_generator: URL generator for creating the links
        user: User whose account has been re-enabled
        totp_cleared: Whether their 2FA was cleared by the lockout

    Returns:
        True if email sent successfully, False otherwise
    """
    if not user.email:
        # An erased user has no address to write to - see docs/personal-data.md
        logger.warning("user.reenabled_email_skipped_no_address", user_id=str(user.id))
        return False

    try:
        context = {
            "user_name": user.display_name if user.first_name or user.last_name else None,
            "email_address": user.email,
            "uses_oauth": not user.has_usable_password() and bool(user.oauth_provider),
            "forgot_password_url": url_generator.generate_url("auth.forgot_password", _external=True),
            "login_url": url_generator.generate_url("auth.login", _external=True),
            "totp_cleared": totp_cleared,
        }

        text_body = template_renderer.render_template("emails/account_reenabled.txt", **context)
        html_body = template_renderer.render_template("emails/account_reenabled.html", **context)

        success = email_adapter.send_email(
            to=[user.email],
            subject="Your OpenDLP Account Has Been Re-enabled",
            text_body=text_body,
            html_body=html_body,
        )

        if success:
            logger.info("user.reenabled_email_sent", user_id=str(user.id))
        else:
            logger.error("user.reenabled_email_failed", user_id=str(user.id))

        return success

    except Exception as e:
        logger.error("user.reenabled_email_failed", user_id=str(user.id), error=str(e))
        return False


def get_user_stats(uow: AbstractUnitOfWork, admin_user_id: uuid.UUID) -> dict[str, int]:
    """
    Get user statistics (admin only).

    Args:
        uow: Unit of Work for database operations
        admin_user_id: ID of admin user requesting stats

    Returns:
        Dictionary with user statistics

    Raises:
        UserNotFoundError: If admin user not found
        InsufficientPermissions: If requesting user is not admin

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    admin_user = uow.users.get(admin_user_id)
    if not admin_user:
        raise UserNotFoundError(f"Admin user {admin_user_id} not found")

    if not has_global_admin(admin_user):
        raise InsufficientPermissions("Only admins can view user statistics")

    all_users = list(uow.users.all())

    # Count password-based users (not OAuth) for 2FA statistics
    password_users = [u for u in all_users if not u.oauth_provider]
    users_with_2fa = [u for u in password_users if u.totp_enabled]

    return {
        "total_users": len(all_users),
        "active_users": len([u for u in all_users if u.is_active]),
        "inactive_users": len([u for u in all_users if not u.is_active]),
        "admin_users": len([u for u in all_users if u.global_role == GlobalRole.ADMIN]),
        "organiser_users": len([u for u in all_users if u.global_role == GlobalRole.GLOBAL_ORGANISER]),
        "password_users": len(password_users),
        "users_with_2fa": len(users_with_2fa),
        "regular_users": len([u for u in all_users if u.global_role == GlobalRole.USER]),
    }


def grant_user_assembly_role(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    role: AssemblyRole,
    current_user: User,
    email_adapter: EmailAdapter | None = None,
    template_renderer: TemplateRenderer | None = None,
    url_generator: URLGenerator | None = None,
) -> tuple[UserAssemblyRole, User]:
    """
    Grant or update a user's role on an assembly.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to grant role to
        assembly_id: ID of assembly
        role: Role to assign
        current_user: User performing the action (must have permission)
        email_adapter: Optional email adapter for sending notification emails
        template_renderer: Optional template renderer for rendering email templates
        url_generator: Optional URL generator for creating assembly URLs

    Returns:
        Tuple of (created or updated UserAssemblyRole, detached copy of target User)

    Raises:
        InsufficientPermissions: If current_user lacks permission to grant roles
        UserNotFoundError: If user not found
        AssemblyNotFoundError: If assembly not found

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Check permissions: must be admin or global organiser or assembly manager
    if not has_global_admin(current_user):
        # Load the assembly to check if user can manage it
        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(current_user, assembly):
            raise InsufficientPermissions(
                action="grant_user_assembly_role",
                required_role="admin, global-organiser, or assembly manager",
            )

    # Validate target user exists
    target_user = uow.users.get(user_id)
    if not target_user:
        raise UserNotFoundError(f"User {user_id} not found")

    # Validate assembly exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    # Check if role already exists
    existing_role = next(
        (r for r in target_user.assembly_roles if r.assembly_id == assembly_id),
        None,
    )

    is_new_role = existing_role is None

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

    detached_user = target_user.create_detached_copy()

    # Send email notification if this is a new role assignment and all adapters are provided
    if is_new_role and email_adapter and template_renderer and url_generator:
        send_assembly_role_assigned_email(
            email_adapter=email_adapter,
            template_renderer=template_renderer,
            url_generator=url_generator,
            user=detached_user,
            assembly=assembly,
            role=role,
        )

    return assembly_role, detached_user


def revoke_user_assembly_role(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    current_user: User,
) -> tuple[UserAssemblyRole, User]:
    """
    Revoke a user's role on an assembly.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to revoke role from
        assembly_id: ID of assembly
        current_user: User performing the action (must have permission)

    Returns:
        Tuple of (revoked UserAssemblyRole, detached copy of target User)

    Raises:
        InsufficientPermissions: If current_user lacks permission to revoke roles
        UserNotFoundError: If user, assembly, or role not found

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Check permissions: must be admin or global organiser or assembly manager
    if not has_global_admin(current_user):
        # Load the assembly to check if user can manage it
        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(current_user, assembly):
            raise InsufficientPermissions(
                action="revoke_user_assembly_role",
                required_role="admin, global-organiser, or assembly manager",
            )

    # Validate target user exists
    target_user = uow.users.get(user_id)
    if not target_user:
        raise UserNotFoundError(f"User {user_id} not found")

    # Validate assembly exists
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    # Find the role to revoke
    existing_role = next(
        (r for r in target_user.assembly_roles if r.assembly_id == assembly_id),
        None,
    )

    if not existing_role:
        raise NotFoundError(f"User {user_id} has no role on assembly {assembly_id}")
    assert isinstance(existing_role, UserAssemblyRole)

    # Remove the role
    target_user.assembly_roles.remove(existing_role)
    uow.user_assembly_roles.remove_role(user_id, assembly_id)

    detached_user = target_user.create_detached_copy()
    return existing_role, detached_user


def get_assembly_members(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    current_user: User,
) -> list[tuple[User, UserAssemblyRole]]:
    """
    Get all users with their roles for a given assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: Assembly to fetch members for
        current_user: User requesting the data (must be able to view the assembly)

    Returns:
        List of (User, UserAssemblyRole) tuples for every member of the assembly

    Raises:
        AssemblyNotFoundError: If assembly not found
        InsufficientPermissions: If current_user cannot view the assembly

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_view_assembly(current_user, assembly):
        raise InsufficientPermissions(
            action="get_assembly_members",
            required_role="assembly role or global privileges",
        )

    return uow.user_assembly_roles.get_users_with_roles_for_assembly(assembly_id)


def search_assembly_candidate_users(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    search_term: str,
    current_user: User,
) -> list[User]:
    """
    Search for users who can be added to an assembly (i.e. not already members).

    Args:
        uow: Unit of Work for database operations
        assembly_id: Assembly to search candidates for
        search_term: Term to match against email and display_name (case-insensitive)
        current_user: User performing the search (must have permission)

    Returns:
        List of matching users who do not already have a role on the assembly.
        Empty list when search_term is blank.

    Raises:
        InsufficientPermissions: If current_user lacks permission to manage members

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if not has_global_admin(current_user):
        raise InsufficientPermissions(
            action="search_assembly_candidate_users",
            required_role="admin or global-organiser",
        )

    if not search_term:
        return []

    matching = uow.users.search_users_not_in_assembly(assembly_id, search_term)
    return [user.create_detached_copy() for user in matching]


def update_own_profile(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    """
    Update a user's own profile information.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user updating their profile
        first_name: New first name (optional)
        last_name: New last name (optional)

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If user not found

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assert isinstance(user, User)

    # Apply updates
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name

    return user.create_detached_copy()


def change_own_password(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
) -> None:
    """
    Change a user's password (requires current password).

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user changing their password
        current_password: User's current password for verification
        new_password: New password to set

    Raises:
        UserNotFoundError: If user not found
        InvalidCredentials: If current password is incorrect
        PasswordTooWeak: If new password doesn't meet requirements

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assert isinstance(user, User)

    # Verify current password
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise InvalidCredentials("Current password is incorrect")

    # Validate new password strength
    temp_user = TempUser(email=user.email, first_name=user.first_name, last_name=user.last_name)
    is_valid, error_msg = validate_password_strength(new_password, temp_user)
    if not is_valid:
        raise PasswordTooWeak(error_msg)

    # Update password
    user.password_hash = hash_password(new_password)


def link_oauth_to_user(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    provider: str,
    oauth_id: str,
    oauth_email: str,
) -> User:
    """
    Link OAuth credentials to existing user account.

    If the user already has a different OAuth provider linked, it will be automatically
    replaced with the new provider (single provider choice model).

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to link OAuth to
        provider: OAuth provider (e.g., 'google', 'microsoft')
        oauth_id: Provider's user ID
        oauth_email: Email from OAuth provider (must match user's email)

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If user not found
        ValueError: If emails don't match or OAuth already linked to another account

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assert isinstance(user, User)

    # Verify email match for security
    if user.email.lower() != oauth_email.lower():
        raise ValueError("OAuth email does not match your account email")

    # Check if OAuth credentials already linked to different account
    existing_oauth_user = uow.users.get_by_oauth_credentials(provider, oauth_id)
    if existing_oauth_user and existing_oauth_user.id != user_id:
        raise ValueError(f"This {provider} account is already linked to another user")

    # Link OAuth credentials
    user.add_oauth_credentials(provider, oauth_id)

    return user.create_detached_copy()


def remove_password_auth(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> User:
    """
    Remove password authentication from user account.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to remove password from

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If user not found
        CannotRemoveLastAuthMethod: If user has no OAuth authentication

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assert isinstance(user, User)
    if not user.oauth_provider:
        raise CannotRemoveLastAuthMethod()

    user.remove_password()

    return user.create_detached_copy()


def remove_oauth_auth(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> User:
    """
    Remove OAuth authentication from user account.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to remove OAuth from

    Returns:
        Updated User instance

    Raises:
        UserNotFoundError: If user not found
        CannotRemoveLastAuthMethod: If user has no password authentication

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assert isinstance(user, User)

    if not user.password_hash:
        raise CannotRemoveLastAuthMethod()

    user.remove_oauth()

    return user.create_detached_copy()


def send_assembly_role_assigned_email(
    email_adapter: EmailAdapter,
    template_renderer: TemplateRenderer,
    url_generator: URLGenerator,
    user: User,
    assembly: Assembly,
    role: AssemblyRole,
) -> bool:
    """
    Send email notification when user is assigned a role on an assembly.

    Args:
        email_adapter: Email adapter for sending emails
        template_renderer: Template renderer for rendering email templates
        url_generator: URL generator for creating assembly URL
        user: User being assigned the role
        assembly: Assembly the user is being added to
        role: Role being assigned to the user

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Generate assembly URL
        # Using _external=True to get full URL with domain
        assembly_url = url_generator.generate_url(
            "main.view_assembly",
            assembly_id=assembly.id,
            _external=True,
        )

        # Get human-readable role name
        role_name = assembly_role_options.get(role.name, role.value)

        # Prepare template context
        context = {
            "user_name": user.display_name if user.first_name or user.last_name else None,
            "assembly_title": assembly.title,
            "assembly_question": assembly.question or None,
            "assembly_url": assembly_url,
            "role": role.name,
            "role_name": role_name,
        }

        # Render email templates
        text_body = template_renderer.render_template("emails/assembly_role_assigned.txt", **context)
        html_body = template_renderer.render_template("emails/assembly_role_assigned.html", **context)

        # Send email
        success = email_adapter.send_email(
            to=[user.email],
            subject=f"Added to Assembly: {assembly.title}",
            text_body=text_body,
            html_body=html_body,
        )

        if success:
            logger.info("Assembly role assigned email sent", user_id=str(user.id), assembly_id=str(assembly.id))
        else:
            logger.error(
                "Failed to send assembly role assigned email", user_id=str(user.id), assembly_id=str(assembly.id)
            )

        return success

    except Exception as e:
        logger.error(
            "Error sending assembly role assigned email",
            user_id=str(user.id),
            assembly_id=str(assembly.id),
            error=str(e),
        )
        return False
