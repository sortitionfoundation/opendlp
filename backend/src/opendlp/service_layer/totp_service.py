"""ABOUTME: TOTP service for two-factor authentication core functions
ABOUTME: Handles TOTP secret generation, encryption, QR codes, and code verification"""

import base64
import io
import secrets
import uuid

import pyotp
import qrcode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from werkzeug.security import check_password_hash, generate_password_hash

from opendlp.config import get_totp_encryption_key
from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


def derive_user_encryption_key(master_key: bytes, user_id: uuid.UUID) -> bytes:
    """Derive a user-specific encryption key from the master key using HKDF.

    This ensures each user has a different encryption key even with the same master key.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"opendlp-totp-encryption",  # Fixed salt for deterministic derivation
        info=user_id.bytes,  # User ID as context info
    )
    return hkdf.derive(master_key)


def generate_totp_secret() -> str:
    """Generate a new random TOTP secret (base32 encoded)."""
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str, user_id: uuid.UUID) -> str:
    """Encrypt TOTP secret for storage using Fernet symmetric encryption.

    Args:
        secret: The plaintext TOTP secret
        user_id: The user's UUID for key derivation

    Returns:
        Base64-encoded encrypted secret
    """
    master_key = get_totp_encryption_key()
    user_key = derive_user_encryption_key(master_key, user_id)

    # Fernet requires a base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(user_key)
    f = Fernet(fernet_key)

    encrypted_bytes = f.encrypt(secret.encode("utf-8"))
    return encrypted_bytes.decode("ascii")


def decrypt_totp_secret(encrypted_secret: str, user_id: uuid.UUID) -> str:
    """Decrypt TOTP secret from storage.

    Args:
        encrypted_secret: The base64-encoded encrypted secret
        user_id: The user's UUID for key derivation

    Returns:
        The plaintext TOTP secret
    """
    master_key = get_totp_encryption_key()
    user_key = derive_user_encryption_key(master_key, user_id)

    # Fernet requires a base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(user_key)
    f = Fernet(fernet_key)

    decrypted_bytes = f.decrypt(encrypted_secret.encode("ascii"))
    return decrypted_bytes.decode("utf-8")


def generate_qr_code_data_url(secret: str, email: str, issuer: str = "OpenDLP") -> str:
    """Generate a QR code as a data URL for the authenticator app.

    Args:
        secret: The TOTP secret
        email: The user's email address
        issuer: The application name

    Returns:
        Data URL string (data:image/png;base64,...)
    """
    # Create provisioning URI for the authenticator app
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name=issuer)

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to data URL
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return f"data:image/png;base64,{img_base64}"


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret.

    Args:
        secret: The TOTP secret
        code: The 6-digit code from the authenticator app

    Returns:
        True if the code is valid, False otherwise
    """
    totp = pyotp.TOTP(secret)
    # valid_window=1 allows codes from the previous and next 30-second window
    # This compensates for clock drift between server and client
    return totp.verify(code, valid_window=1)


def generate_backup_codes(count: int = 8) -> list[str]:
    """Generate random backup codes.

    Args:
        count: Number of backup codes to generate (default: 8)

    Returns:
        List of backup codes in format: XXXX-XXXX
    """
    codes = []
    for _ in range(count):
        # Generate 8 random hex characters
        code_bytes = secrets.token_bytes(4)
        code_hex = code_bytes.hex().upper()
        # Format as XXXX-XXXX
        formatted = f"{code_hex[:4]}-{code_hex[4:]}"
        codes.append(formatted)

    return codes


def hash_backup_code(code: str) -> str:
    """Hash a backup code for secure storage.

    Uses werkzeug's password hashing (pbkdf2:sha256) for consistency with user passwords.
    """
    return generate_password_hash(code)


def verify_backup_code(uow: AbstractUnitOfWork, user_id: uuid.UUID, code: str) -> bool:
    """Verify a backup code and mark it as used if valid.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        code: The backup code to verify

    Returns:
        True if the code is valid and was successfully used, False otherwise
    """
    # Get all unused backup codes for the user
    unused_codes = uow.user_backup_codes.get_unused_codes_for_user(user_id)

    # Check each unused code against the provided code
    for backup_code in unused_codes:
        if check_password_hash(backup_code.code_hash, code):
            # Valid code found - mark it as used
            backup_code.mark_as_used()
            uow.commit()
            return True

    return False


def count_remaining_backup_codes(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> int:
    """Count how many unused backup codes a user has.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID

    Returns:
        Number of remaining unused backup codes
    """
    unused_codes = uow.user_backup_codes.get_unused_codes_for_user(user_id)
    return len(list(unused_codes))


def create_backup_codes_for_user(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> list[str]:
    """Generate and store new backup codes for a user.

    This will DELETE all existing backup codes for the user first.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID

    Returns:
        List of plaintext backup codes (to show to the user once)
    """
    # Delete existing backup codes
    uow.user_backup_codes.delete_codes_for_user(user_id)

    # Generate new codes
    plaintext_codes = generate_backup_codes(8)

    # Hash and store them
    for code in plaintext_codes:
        hashed = hash_backup_code(code)
        backup_code = UserBackupCode(
            user_id=user_id,
            code_hash=hashed,
        )
        uow.user_backup_codes.add(backup_code)

    uow.commit()

    return plaintext_codes


def check_totp_rate_limit(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, max_attempts: int = 5, window_minutes: int = 15
) -> tuple[bool, int]:
    """Check if a user has exceeded the TOTP verification rate limit.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        max_attempts: Maximum number of failed attempts allowed
        window_minutes: Time window in minutes for counting attempts

    Returns:
        Tuple of (is_allowed, attempts_remaining)
    """
    # Count failed attempts in the time window
    # For now, we'll implement a simple in-memory approach
    # TODO: Implement proper database-backed rate limiting using totp_verification_attempts table
    # cutoff_time = datetime.now(UTC) - timedelta(minutes=window_minutes)

    # Placeholder: Allow all attempts for now
    # This will be properly implemented when we add the TotpVerificationAttempt domain model
    return (True, max_attempts)


def record_totp_attempt(uow: AbstractUnitOfWork, user_id: uuid.UUID, success: bool) -> None:
    """Record a TOTP verification attempt.

    Args:
        uow: Unit of Work for database access
        user_id: The user's UUID
        success: Whether the verification was successful
    """
    # TODO: Implement when we add TotpVerificationAttempt domain model and repository
    # For now, this is a no-op
    pass
