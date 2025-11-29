"""ABOUTME: Invite management service layer for generating and managing user invites
ABOUTME: Handles invite generation, listing, revocation, and expiry cleanup operations"""

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.user_invites import UserInvite, generate_invite_code
from opendlp.domain.value_objects import GlobalRole

from .exceptions import InsufficientPermissions, InviteNotFoundError, UserNotFoundError
from .permissions import has_global_organiser
from .unit_of_work import AbstractUnitOfWork


def generate_invite(
    uow: AbstractUnitOfWork,
    created_by_user_id: uuid.UUID,
    global_role: GlobalRole,
    expires_in_hours: int = 168,  # 7 days default
) -> UserInvite:
    """
    Generate a new user invite.

    Args:
        uow: Unit of Work for database operations
        created_by_user_id: ID of user creating the invite
        global_role: Global role the invite will grant
        expires_in_hours: Number of hours until invite expires

    Returns:
        Created UserInvite instance

    Raises:
        UserNotFoundError: If user not found
        InsufficientPermissions: If user cannot create invites
    """
    with uow:
        user = uow.users.get(created_by_user_id)
        if not user:
            raise UserNotFoundError(f"User {created_by_user_id} not found")

        # Check permissions - only global organisers and admins can create invites
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="generate invite", required_role="global-organiser or admin")

        # Generate unique invite code
        code = generate_invite_code()
        while uow.user_invites.get_by_code(code):
            code = generate_invite_code()

        # Create the invite
        invite = UserInvite(
            code=code,
            global_role=global_role,
            created_by=created_by_user_id,
            expires_at=datetime.now(UTC) + timedelta(hours=expires_in_hours),
        )

        uow.user_invites.add(invite)
        detached_invite = invite.create_detached_copy()
        uow.commit()
        return detached_invite


def generate_batch_invites(
    uow: AbstractUnitOfWork,
    created_by_user_id: uuid.UUID,
    global_role: GlobalRole,
    count: int,
    expires_in_hours: int = 168,
) -> list[UserInvite]:
    """
    Generate multiple invites at once.

    Args:
        uow: Unit of Work for database operations
        created_by_user_id: ID of user creating the invites
        global_role: Global role the invites will grant
        count: Number of invites to generate
        expires_in_hours: Number of hours until invites expire

    Returns:
        List of created UserInvite instances

    Raises:
        UserNotFoundError: If user not found
        ValueError: If count invalid
        InsufficientPermissions: If user cannot create invites
    """
    if count <= 0 or count > 100:  # Reasonable limit
        raise ValueError("Count must be between 1 and 100")

    with uow:
        user = uow.users.get(created_by_user_id)
        if not user:
            raise UserNotFoundError(f"User {created_by_user_id} not found")

        # Check permissions
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="generate batch invites", required_role="global-organiser or admin")

        invites = []
        expires_at = datetime.now(UTC) + timedelta(hours=expires_in_hours)

        for _ in range(count):
            # Generate unique invite code
            code = generate_invite_code()
            while uow.user_invites.get_by_code(code):
                code = generate_invite_code()

            invite = UserInvite(
                code=code,
                global_role=global_role,
                created_by=created_by_user_id,
                expires_at=expires_at,
            )

            uow.user_invites.add(invite)
            invites.append(invite.create_detached_copy())

        uow.commit()
        return invites


def list_invites(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    include_expired: bool = False,
) -> list[UserInvite]:
    """
    List invites that a user can see.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user requesting the list
        include_expired: Whether to include expired invites

    Returns:
        List of UserInvite instances

    Raises:
        UserNotFoundError: If user not found
        InsufficientPermissions: If user cannot view invites
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # Check permissions
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="list invites", required_role="global-organiser or admin")

        if include_expired:
            return list(uow.user_invites.all())
        else:
            return list(uow.user_invites.get_valid_invites())


def revoke_invite(
    uow: AbstractUnitOfWork,
    invite_id: uuid.UUID,
    user_id: uuid.UUID,
) -> UserInvite:
    """
    Revoke (mark as used) an invite to prevent its use.

    Args:
        uow: Unit of Work for database operations
        invite_id: ID of invite to revoke
        user_id: ID of user performing the revocation

    Returns:
        Revoked UserInvite instance

    Raises:
        UserNotFoundError: If user not found
        InviteNotFoundError: If invite not found
        InsufficientPermissions: If user cannot revoke invites
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        invite = uow.user_invites.get(invite_id)
        if not invite:
            raise InviteNotFoundError(f"Invite {invite_id} not found")

        # Check permissions
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="revoke invite", required_role="global-organiser or admin")

        # Mark invite as used (effectively revoking it)
        invite.use(user_id)

        uow.commit()
        # Explicit typing to satisfy mypy
        revoked_invite: UserInvite = invite.create_detached_copy()
        return revoked_invite


def get_invite_details(
    uow: AbstractUnitOfWork,
    invite_id: uuid.UUID,
    user_id: uuid.UUID,
) -> UserInvite:
    """
    Get details of a specific invite.

    Args:
        uow: Unit of Work for database operations
        invite_id: ID of invite to retrieve
        user_id: ID of user requesting the details

    Returns:
        UserInvite instance

    Raises:
        UserNotFoundError: If user not found
        InviteNotFoundError: If invite not found
        InsufficientPermissions: If user cannot view invite details
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # Check permissions
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="view invite details", required_role="global-organiser or admin")

        invite = uow.user_invites.get(invite_id)
        if not invite:
            raise InviteNotFoundError(f"Invite {invite_id} not found")

        # Explicit typing to satisfy mypy
        invite_details: UserInvite = invite.create_detached_copy()
        return invite_details


def cleanup_expired_invites(uow: AbstractUnitOfWork) -> int:
    """
    Clean up expired invites from the database.

    Args:
        uow: Unit of Work for database operations

    Returns:
        Number of invites cleaned up
    """
    with uow:
        invites = list(uow.user_invites.all())
        expired_count = 0

        now = datetime.now(UTC)
        for invite in invites:
            if invite.expires_at < now and not invite.used_by:
                # Remove unused expired invites
                # Note: In practice, you might want to keep them for audit purposes
                # and just mark them differently, but for simplicity we'll remove them
                uow.user_invites.delete(invite)
                expired_count += 1

        uow.commit()
        return expired_count


def get_invite_statistics(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> dict[str, float]:
    """
    Get statistics about invites.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user requesting statistics

    Returns:
        Dictionary with invite statistics

    Raises:
        UserNotFoundError: If user not found
        InsufficientPermissions: If user cannot view statistics
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # Check permissions
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="view invite statistics", required_role="global-organiser or admin")

        invites = list(uow.user_invites.all())
        now = datetime.now(UTC)

        total_invites = len(invites)
        used_invites = len([i for i in invites if i.used_by])
        expired_invites = len([i for i in invites if i.expires_at < now])
        active_invites = len([i for i in invites if i.is_valid()])

        conversion_rate = (used_invites / total_invites * 100) if total_invites > 0 else 0

        return {
            "total_invites": total_invites,
            "used_invites": used_invites,
            "expired_invites": expired_invites,
            "active_invites": active_invites,
            "conversion_rate": round(conversion_rate, 2),
        }
