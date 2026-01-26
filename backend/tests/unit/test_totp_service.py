"""Unit tests for TOTP service functions."""

import base64
import secrets
import time
import uuid

import pyotp
import pytest
from cryptography.fernet import InvalidToken

from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.service_layer import totp_service
from tests.fakes import FakeUnitOfWork


def _setup_test_encryption_key(temp_env_vars):
    """Helper to set up a test encryption key in the environment."""
    raw_key = secrets.token_bytes(32)
    test_key = base64.b64encode(raw_key).decode()
    temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)
    return test_key


class TestGenerateTotpSecret:
    """Tests for generate_totp_secret()."""

    def test_generates_valid_base32_secret(self):
        """Test that generate_totp_secret() returns a valid base32 string."""
        secret = totp_service.generate_totp_secret()

        assert isinstance(secret, str)
        assert len(secret) == 32  # pyotp.random_base32() returns 32 characters
        # Base32 alphabet: A-Z and 2-7
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)  # pragma: allowlist secret

    def test_generates_unique_secrets(self):
        """Test that multiple calls generate different secrets."""
        secret1 = totp_service.generate_totp_secret()
        secret2 = totp_service.generate_totp_secret()

        assert secret1 != secret2


class TestEncryptDecryptTotpSecret:
    """Tests for encrypt_totp_secret() and decrypt_totp_secret()."""

    def test_encrypt_returns_encrypted_string(self, temp_env_vars):
        """Test that encryption returns a different string."""
        _setup_test_encryption_key(temp_env_vars)
        secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        user_id = uuid.uuid4()

        encrypted = totp_service.encrypt_totp_secret(secret, user_id)

        assert isinstance(encrypted, str)
        assert encrypted != secret
        assert len(encrypted) > len(secret)

    def test_decrypt_returns_original_secret(self, temp_env_vars):
        """Test that decryption returns the original secret."""
        _setup_test_encryption_key(temp_env_vars)
        secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        user_id = uuid.uuid4()

        encrypted = totp_service.encrypt_totp_secret(secret, user_id)
        decrypted = totp_service.decrypt_totp_secret(encrypted, user_id)

        assert decrypted == secret

    def test_different_user_ids_produce_different_encrypted_values(self, temp_env_vars):
        """Test that the same secret encrypted for different users produces different ciphertexts."""
        _setup_test_encryption_key(temp_env_vars)
        secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        user_id1 = uuid.uuid4()
        user_id2 = uuid.uuid4()

        encrypted1 = totp_service.encrypt_totp_secret(secret, user_id1)
        encrypted2 = totp_service.encrypt_totp_secret(secret, user_id2)

        assert encrypted1 != encrypted2

    def test_decryption_with_wrong_user_id_fails(self, temp_env_vars):
        """Test that decryption with a different user ID fails."""
        _setup_test_encryption_key(temp_env_vars)
        secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        user_id1 = uuid.uuid4()
        user_id2 = uuid.uuid4()

        encrypted = totp_service.encrypt_totp_secret(secret, user_id1)

        with pytest.raises(InvalidToken):
            totp_service.decrypt_totp_secret(encrypted, user_id2)

    def test_raises_error_if_encryption_key_not_set(self, clear_env_vars):
        """Test that encryption raises ValueError if TOTP_ENCRYPTION_KEY is not set."""
        clear_env_vars("TOTP_ENCRYPTION_KEY")

        with pytest.raises(ValueError, match="TOTP_ENCRYPTION_KEY environment variable must be set"):
            totp_service.encrypt_totp_secret("secret", uuid.uuid4())


class TestGenerateQrCodeDataUrl:
    """Tests for generate_qr_code_data_url()."""

    def test_generates_data_url(self):
        """Test that QR code generation returns a valid data URL."""
        secret = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        email = "test@example.com"

        data_url = totp_service.generate_qr_code_data_url(secret, email)

        assert data_url.startswith("data:image/png;base64,")
        assert len(data_url) > 100  # Should be a reasonably sized image

    def test_generates_different_qr_codes_for_different_secrets(self):
        """Test that different secrets produce different QR codes."""
        secret1 = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        secret2 = "KBSWY3DPEHPK3PXP"  # pragma: allowlist secret
        email = "test@example.com"

        qr1 = totp_service.generate_qr_code_data_url(secret1, email)
        qr2 = totp_service.generate_qr_code_data_url(secret2, email)

        assert qr1 != qr2


class TestVerifyTotpCode:
    """Tests for verify_totp_code()."""

    def test_verifies_valid_code(self):
        """Test that a valid TOTP code is accepted."""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        result = totp_service.verify_totp_code(secret, valid_code)

        assert result is True

    def test_rejects_invalid_code(self):
        """Test that an invalid TOTP code is rejected."""
        secret = pyotp.random_base32()

        result = totp_service.verify_totp_code(secret, "000000")

        assert result is False

    def test_accepts_code_from_previous_window(self):
        """Test that codes from the previous 30-second window are accepted (clock drift tolerance)."""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Get code from 30 seconds ago
        past_time = int(time.time()) - 30
        past_code = totp.at(past_time)

        result = totp_service.verify_totp_code(secret, past_code)

        assert result is True  # Should still be valid due to valid_window=1


class TestGenerateBackupCodes:
    """Tests for generate_backup_codes()."""

    def test_generates_correct_count(self):
        """Test that the correct number of backup codes is generated."""
        codes = totp_service.generate_backup_codes(8)

        assert len(codes) == 8

    def test_generates_formatted_codes(self):
        """Test that backup codes are properly formatted."""
        codes = totp_service.generate_backup_codes(5)

        for code in codes:
            assert len(code) == 9  # XXXX-XXXX format
            assert code[4] == "-"
            assert all(c in "0123456789ABCDEF-" for c in code)

    def test_generates_unique_codes(self):
        """Test that all generated codes are unique."""
        codes = totp_service.generate_backup_codes(8)

        assert len(codes) == len(set(codes))


class TestHashVerifyBackupCode:
    """Tests for hash_backup_code() and verify_backup_code()."""

    def test_hash_returns_hashed_string(self):
        """Test that hashing returns a different string."""
        code = "1234-5678"

        hashed = totp_service.hash_backup_code(code)

        assert isinstance(hashed, str)
        assert hashed != code
        assert len(hashed) > len(code)

    def test_verify_accepts_correct_code(self):
        """Test that verify_backup_code() accepts a valid code."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()
        code = "ABCD-1234"

        # Create a backup code in the database
        hashed = totp_service.hash_backup_code(code)
        backup_code = UserBackupCode(user_id=user_id, code_hash=hashed)
        uow.user_backup_codes.add(backup_code)

        result = totp_service.verify_backup_code(uow, user_id, code)

        assert result is True
        # Verify the code was marked as used
        codes = list(uow.user_backup_codes.get_codes_for_user(user_id))
        assert codes[0].is_used()

    def test_verify_rejects_incorrect_code(self):
        """Test that verify_backup_code() rejects an invalid code."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()
        code = "ABCD-1234"
        wrong_code = "WXYZ-9999"

        # Create a backup code in the database
        hashed = totp_service.hash_backup_code(code)
        backup_code = UserBackupCode(user_id=user_id, code_hash=hashed)
        uow.user_backup_codes.add(backup_code)

        result = totp_service.verify_backup_code(uow, user_id, wrong_code)

        assert result is False
        # Verify the code was NOT marked as used
        codes = list(uow.user_backup_codes.get_codes_for_user(user_id))
        assert not codes[0].is_used()

    def test_verify_rejects_already_used_code(self):
        """Test that verify_backup_code() rejects a code that has already been used."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()
        code = "ABCD-1234"

        # Create a used backup code
        hashed = totp_service.hash_backup_code(code)
        backup_code = UserBackupCode(user_id=user_id, code_hash=hashed)
        backup_code.mark_as_used()
        uow.user_backup_codes.add(backup_code)

        result = totp_service.verify_backup_code(uow, user_id, code)

        assert result is False


class TestCreateBackupCodesForUser:
    """Tests for create_backup_codes_for_user()."""

    def test_creates_backup_codes_in_database(self):
        """Test that backup codes are created and stored."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()

        codes = totp_service.create_backup_codes_for_user(uow, user_id)

        assert len(codes) == 8
        assert uow.committed is True

        # Verify codes are in database
        stored_codes = list(uow.user_backup_codes.get_codes_for_user(user_id))
        assert len(stored_codes) == 8

    def test_deletes_existing_codes_before_creating_new_ones(self):
        """Test that old backup codes are deleted when generating new ones."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()

        # Create initial codes
        old_code = UserBackupCode(user_id=user_id, code_hash="old_hash")
        uow.user_backup_codes.add(old_code)

        # Generate new codes
        new_codes = totp_service.create_backup_codes_for_user(uow, user_id)

        assert len(new_codes) == 8
        # Verify only the new codes exist
        stored_codes = list(uow.user_backup_codes.get_codes_for_user(user_id))
        assert len(stored_codes) == 8
        assert old_code not in stored_codes


class TestCountRemainingBackupCodes:
    """Tests for count_remaining_backup_codes()."""

    def test_counts_unused_codes(self):
        """Test that only unused codes are counted."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()

        # Add 3 unused codes and 2 used codes
        for i in range(3):
            code = UserBackupCode(user_id=user_id, code_hash=f"hash_{i}")
            uow.user_backup_codes.add(code)

        for i in range(3, 5):
            code = UserBackupCode(user_id=user_id, code_hash=f"hash_{i}")
            code.mark_as_used()
            uow.user_backup_codes.add(code)

        count = totp_service.count_remaining_backup_codes(uow, user_id)

        assert count == 3
