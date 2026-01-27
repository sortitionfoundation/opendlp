"""ABOUTME: Two-factor authentication orchestration service
ABOUTME: High-level functions for 2FA setup, management, and verification flows"""

import uuid

from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.service_layer import totp_service
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import lazy_gettext as _l


class TwoFactorSetupError(Exception):
    """Raised when 2FA setup fails."""

    pass


class TwoFactorVerificationError(Exception):
    """Raised when 2FA verification fails."""

    pass


def setup_2fa(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> tuple[str, str, list[str]]:
    """Initiate 2FA setup for a user.

    This generates a new TOTP secret and backup codes, but does NOT enable 2FA yet.
    The user must verify they can generate valid codes before 2FA is enabled.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID

    Returns:
        Tuple of (totp_secret, qr_code_data_url, backup_codes)
        - totp_secret: The plaintext secret (to be encrypted and stored after verification)
        - qr_code_data_url: Data URL for QR code image
        - backup_codes: List of plaintext backup codes (to show once)

    Raises:
        TwoFactorSetupError: If user is OAuth user or already has 2FA enabled
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        if user.oauth_provider:
            raise TwoFactorSetupError(_l("Cannot enable 2FA for OAuth users"))

        if user.totp_enabled:
            raise TwoFactorSetupError(_l("2FA is already enabled for this user"))

        # Generate TOTP secret
        totp_secret = totp_service.generate_totp_secret()

        # Generate QR code
        qr_code_url = totp_service.generate_qr_code_data_url(totp_secret, user.email)

        # Generate backup codes
        backup_codes = totp_service.generate_backup_codes()

        return totp_secret, qr_code_url, backup_codes


def enable_2fa(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    totp_secret: str,
    totp_code: str,
    backup_codes: list[str],
) -> None:
    """Complete 2FA setup by verifying the TOTP code and enabling 2FA.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        totp_secret: The plaintext TOTP secret from setup_2fa()
        totp_code: The 6-digit code from the authenticator app
        backup_codes: The backup codes from setup_2fa() to store

    Raises:
        TwoFactorVerificationError: If TOTP code is invalid
        TwoFactorSetupError: If user cannot enable 2FA
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        if user.oauth_provider:
            raise TwoFactorSetupError(_l("Cannot enable 2FA for OAuth users"))

        # Verify the TOTP code
        if not totp_service.verify_totp_code(totp_secret, totp_code):
            raise TwoFactorVerificationError(_l("Invalid authentication code"))

        # Encrypt and store the TOTP secret
        encrypted_secret = totp_service.encrypt_totp_secret(totp_secret, user_id)

        # Enable 2FA on the user
        user.enable_totp(encrypted_secret)

        # Delete any existing backup codes and create new ones
        uow.user_backup_codes.delete_codes_for_user(user_id)

        for code in backup_codes:
            from opendlp.domain.user_backup_codes import UserBackupCode

            hashed = totp_service.hash_backup_code(code)
            backup_code = UserBackupCode(user_id=user_id, code_hash=hashed)
            uow.user_backup_codes.add(backup_code)

        # Create audit log entry
        audit_log = TwoFactorAuditLog(
            user_id=user_id,
            action="enabled",
            performed_by=user_id,
            metadata={"method": "totp"},
        )
        uow.two_factor_audit_logs.add(audit_log)

        uow.commit()


def disable_2fa(uow: AbstractUnitOfWork, user_id: uuid.UUID, totp_code: str) -> None:
    """Disable 2FA for a user (user-initiated).

    Requires a valid TOTP code to confirm the action.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        totp_code: The 6-digit code from the authenticator app

    Raises:
        TwoFactorVerificationError: If TOTP code is invalid
        TwoFactorSetupError: If user doesn't have 2FA enabled
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        if not user.totp_enabled:
            raise TwoFactorSetupError(_l("2FA is not enabled for this user"))

        # Decrypt the secret and verify the code
        decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
        if not totp_service.verify_totp_code(decrypted_secret, totp_code):
            raise TwoFactorVerificationError(_l("Invalid authentication code"))

        # Disable 2FA
        user.disable_totp()

        # Delete all backup codes
        uow.user_backup_codes.delete_codes_for_user(user_id)

        # Create audit log entry
        audit_log = TwoFactorAuditLog(
            user_id=user_id,
            action="disabled",
            performed_by=user_id,
            metadata={"method": "user_requested"},
        )
        uow.two_factor_audit_logs.add(audit_log)

        uow.commit()


def regenerate_backup_codes(uow: AbstractUnitOfWork, user_id: uuid.UUID, totp_code: str) -> list[str]:
    """Regenerate backup codes for a user.

    Requires a valid TOTP code to confirm the action.
    All existing backup codes will be deleted.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        totp_code: The 6-digit code from the authenticator app

    Returns:
        List of new plaintext backup codes

    Raises:
        TwoFactorVerificationError: If TOTP code is invalid
        TwoFactorSetupError: If user doesn't have 2FA enabled
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        if not user.totp_enabled:
            raise TwoFactorSetupError(_l("2FA is not enabled for this user"))

        # Decrypt the secret and verify the code
        decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
        if not totp_service.verify_totp_code(decrypted_secret, totp_code):
            raise TwoFactorVerificationError(_l("Invalid authentication code"))

        # Generate new backup codes
        backup_codes = totp_service.create_backup_codes_for_user(uow, user_id)

        # Create audit log entry
        audit_log = TwoFactorAuditLog(
            user_id=user_id,
            action="backup_codes_regenerated",
            performed_by=user_id,
            metadata={"codes_count": len(backup_codes)},
        )
        uow.two_factor_audit_logs.add(audit_log)

        uow.commit()

        return backup_codes


def admin_disable_2fa(uow: AbstractUnitOfWork, user_id: uuid.UUID, admin_user_id: uuid.UUID) -> None:
    """Disable 2FA for a user (admin-initiated).

    This does not require a TOTP code - it's for admin recovery scenarios.
    The action is logged in the audit trail with the admin's ID.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID whose 2FA should be disabled
        admin_user_id: The admin user's UUID performing the action

    Raises:
        TwoFactorSetupError: If user doesn't have 2FA enabled or is OAuth user
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        admin_user = uow.users.get(admin_user_id)
        if admin_user is None:
            raise TwoFactorSetupError(_l("Admin user not found"))

        if not user.totp_enabled:
            raise TwoFactorSetupError(_l("2FA is not enabled for this user"))

        if user.oauth_provider:
            raise TwoFactorSetupError(_l("Cannot disable 2FA for OAuth users (they don't use 2FA)"))

        # Disable 2FA
        user.disable_totp()

        # Delete all backup codes
        uow.user_backup_codes.delete_codes_for_user(user_id)

        # Create audit log entry
        audit_log = TwoFactorAuditLog(
            user_id=user_id,
            action="admin_disabled",
            performed_by=admin_user_id,
            metadata={"admin_email": admin_user.email},
        )
        uow.two_factor_audit_logs.add(audit_log)

        uow.commit()


def get_2fa_status(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> dict:
    """Get the 2FA status for a user.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID

    Returns:
        Dictionary with 2FA status information
    """
    with uow:
        user = uow.users.get(user_id)
        if user is None:
            raise TwoFactorSetupError(_l("User not found"))

        return {
            "enabled": user.totp_enabled,
            "enabled_at": user.totp_enabled_at,
            "is_oauth_user": user.oauth_provider is not None,
            "backup_codes_remaining": totp_service.count_remaining_backup_codes(uow, user_id),
        }


def get_2fa_audit_logs(uow: AbstractUnitOfWork, user_id: uuid.UUID, limit: int = 100) -> list[TwoFactorAuditLog]:
    """Get 2FA audit logs for a user.

    Note: This function does not manage the UOW session - the caller must use `with uow:`.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        limit: Maximum number of logs to return (default: 100)

    Returns:
        List of TwoFactorAuditLog entries, most recent first
    """
    user = uow.users.get(user_id)
    if user is None:
        raise TwoFactorSetupError(_l("User not found"))

    return list(uow.two_factor_audit_logs.get_logs_for_user(user_id, limit=limit))
