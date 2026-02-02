"""ABOUTME: SQLAlchemy table definitions and imperative mapping for OpenDLP
ABOUTME: Defines database schema with proper relationships, indexes, and JSON columns"""

import json
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sortition_algorithms.utils import RunReport
from sqlalchemy import TIMESTAMP, Boolean, Column, Date, ForeignKey, Index, Integer, String, Table, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import registry
from sqlalchemy.sql.sqltypes import String as SQLString

from opendlp.domain.value_objects import (
    AssemblyRole,
    AssemblyStatus,
    GlobalRole,
    SelectionRunStatus,
    SelectionTaskType,
)


def aware_utcnow() -> datetime:  # pragma: no cover
    return datetime.now(UTC)


class EnumAsString(TypeDecorator):
    """Custom type for storing Python Enums as strings."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[Enum], *args: Any, **kwargs: Any) -> None:
        self.enum_class = enum_class
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:  # pragma: no cover
            return value
        return value.value if hasattr(value, "value") else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:  # pragma: no cover
            return value
        return self.enum_class(value)


class TZAwareDatetime(TypeDecorator):
    """Custom type for timezone-aware datetime objects."""

    impl = TIMESTAMP
    cache_ok = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Ensure timezone=True for PostgreSQL
        kwargs.setdefault("timezone", True)
        super().__init__(*args, **kwargs)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return value

        # If the datetime is naive, assume it's UTC and make it aware
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value  # type: ignore[no-any-return]


class CrossDatabaseUUID(TypeDecorator):
    """Cross-database UUID type that works with both PostgreSQL and SQLite."""

    impl = SQLString
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """Choose the appropriate UUID implementation based on the dialect."""
        if dialect.name == "postgresql":
            # Use native PostgreSQL UUID type
            return dialect.type_descriptor(PostgresUUID(as_uuid=True))
        else:
            # For SQLite and other databases, use CHAR(36) to store UUID as string
            return dialect.type_descriptor(SQLString(36))

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Convert UUID object to string for storage."""
        if value is None:
            return value

        if isinstance(value, uuid.UUID):
            return str(value)
        elif isinstance(value, str):
            # Validate it's a proper UUID string
            try:
                uuid.UUID(value)
                return value
            except ValueError as e:
                raise ValueError(f"Invalid UUID string: {value}") from e
        else:
            raise TypeError(f"Expected UUID or string, got {type(value)}")

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        """Convert stored value back to UUID object."""
        if value is None:
            return value

        if isinstance(value, uuid.UUID):
            # Already a UUID (PostgreSQL case)
            return value
        elif isinstance(value, str):
            # String UUID (SQLite case)
            return uuid.UUID(value)
        else:
            # This shouldn't happen, but handle gracefully
            return uuid.UUID(str(value))


class RunReportJSON(TypeDecorator):
    """Custom type for storing RunReport objects as JSON using cattrs."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Convert RunReport object to JSON string for storage."""
        if value is None:
            return None

        if isinstance(value, RunReport):
            # Unstructure the RunReport to a dict and convert to JSON string
            unstructured = value.serialize()
            return json.dumps(unstructured)
        else:
            raise TypeError(f"Expected RunReport or None, got {type(value)}")

    def process_result_value(self, value: Any, dialect: Dialect) -> RunReport | None:
        """Convert JSON string back to RunReport object."""
        if value is None:
            return None

        if isinstance(value, str):
            try:
                # Parse JSON string and structure back to RunReport
                unstructured = json.loads(value)
                return RunReport.deserialize(unstructured)
            except Exception:
                # If deserialization fails, just return empty RunReport
                # The JSON is still stored in the database, but we can't reconstruct the RunReport
                return RunReport()
        else:
            try:
                # Already a dict (shouldn't happen with JSON type, but handle it)
                return RunReport.deserialize(value)
            except Exception:
                return RunReport()


# Create a registry for imperative mapping
mapper_registry = registry()
metadata = mapper_registry.metadata

# Users table
users = Table(
    "users",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("email", String(255), nullable=False, index=True, unique=True),
    Column("first_name", String(100), nullable=False, default=""),
    Column("last_name", String(100), nullable=False, default=""),
    Column("password_hash", String(255), nullable=True),
    Column("oauth_provider", String(50), nullable=True),
    Column("oauth_id", String(255), nullable=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("user_data_agreement_agreed_at", TZAwareDatetime(), nullable=True),
    # Two-factor authentication fields
    Column("totp_secret_encrypted", String(255), nullable=True),
    Column("totp_enabled", Boolean, nullable=False, default=False),
    Column("totp_enabled_at", TZAwareDatetime(), nullable=True),
    # Email confirmation field
    Column("email_confirmed_at", TZAwareDatetime(), nullable=True),
    Index("ix_users_oauth_provider_id", "oauth_provider", "oauth_id"),
)

# Assemblies table
assemblies = Table(
    "assemblies",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("title", String(255), nullable=False),
    Column("question", Text, nullable=False, default=""),
    Column("first_assembly_date", Date, nullable=True),
    Column("number_to_select", Integer, nullable=False, default=0),
    Column("status", EnumAsString(AssemblyStatus, 50), index=True, nullable=False),
    Column("created_at", TZAwareDatetime(), index=True, nullable=False, default=aware_utcnow),
    Column("updated_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    # JSON column for flexible assembly configuration
    Column("config", JSON, nullable=True),
)

# User assembly roles table - many-to-many relationship
user_assembly_roles = Table(
    "user_assembly_roles",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
    Column(
        "assembly_id", CrossDatabaseUUID(), ForeignKey("assemblies.id", ondelete="CASCADE"), index=True, nullable=False
    ),
    Column("role", EnumAsString(AssemblyRole, 50), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Index("ix_user_assembly_roles_user_assembly", "user_id", "assembly_id"),
)

# User invites table
user_invites = Table(
    "user_invites",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("code", String(50), nullable=False, index=True, unique=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_by", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("expires_at", TZAwareDatetime(), nullable=False, index=True),
    Column("used_by", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
    Column("used_at", TZAwareDatetime(), nullable=True),
)

# Password reset tokens table
password_reset_tokens = Table(
    "password_reset_tokens",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("token", String(100), nullable=False, index=True, unique=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow, index=True),
    Column("expires_at", TZAwareDatetime(), nullable=False, index=True),
    Column("used_at", TZAwareDatetime(), nullable=True),
)

# Email confirmation tokens table
email_confirmation_tokens = Table(
    "email_confirmation_tokens",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("token", String(100), nullable=False, index=True, unique=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow, index=True),
    Column("expires_at", TZAwareDatetime(), nullable=False, index=True),
    Column("used_at", TZAwareDatetime(), nullable=True),
)

# Assembly GSheets table
assembly_gsheets = Table(
    "assembly_gsheets",
    metadata,
    Column("assembly_gsheet_id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column(
        "assembly_id", CrossDatabaseUUID(), ForeignKey("assemblies.id", ondelete="CASCADE"), nullable=False, unique=True
    ),
    Column("url", String(500), nullable=False),
    Column("select_registrants_tab", String(100), nullable=False, default="Respondents"),
    Column("select_targets_tab", String(100), nullable=False, default="Categories"),
    Column("replace_registrants_tab", String(100), nullable=False, default="Remaining"),
    Column("replace_targets_tab", String(100), nullable=False, default="Replacement Categories"),
    Column("already_selected_tab", String(100), nullable=False, default="Selected"),
    Column("generate_remaining_tab", Boolean, nullable=False, default=True),
    Column("id_column", String(100), nullable=False, default="nationbuilder_id"),
    Column("check_same_address", Boolean, nullable=False, default=True),
    Column("check_same_address_cols", JSON, nullable=False, default=list),
    Column("columns_to_keep", JSON, nullable=False, default=list),
    Column("selection_algorithm", String(50), nullable=False, default="maximin"),
)

# Selection run records table
selection_run_records = Table(
    "selection_run_records",
    metadata,
    Column("task_id", CrossDatabaseUUID(), primary_key=True),
    Column(
        "assembly_id", CrossDatabaseUUID(), ForeignKey("assemblies.id", ondelete="CASCADE"), nullable=False, index=True
    ),
    Column("status", EnumAsString(SelectionRunStatus, 50), nullable=False, index=True),
    Column("task_type", EnumAsString(SelectionTaskType, 50), nullable=False, index=True),
    Column("celery_task_id", String(50), nullable=False, index=True),
    Column("log_messages", JSON, nullable=False, default=list),
    Column("settings_used", JSON, nullable=False, default=dict),
    Column("error_message", Text, nullable=False, default=""),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow, index=True),
    Column("completed_at", TZAwareDatetime(), nullable=True),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
    Column("comment", Text, nullable=False, default=""),
    Column("status_stages", JSON, nullable=True),
    Column("selected_ids", JSON, nullable=True),
    Column("run_report", RunReportJSON(), nullable=True),
)

# User backup codes table for 2FA recovery
user_backup_codes = Table(
    "user_backup_codes",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("code_hash", String(255), nullable=False),
    Column("used_at", TZAwareDatetime(), nullable=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
)

# TOTP verification attempts table for rate limiting
totp_verification_attempts = Table(
    "totp_verification_attempts",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("attempted_at", TZAwareDatetime(), nullable=False, default=aware_utcnow, index=True),
    Column("success", Boolean, nullable=False),
)

# Two-factor authentication audit log table
two_factor_audit_log = Table(
    "two_factor_audit_log",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("action", String(50), nullable=False),
    Column("performed_by", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("timestamp", TZAwareDatetime(), nullable=False, default=aware_utcnow, index=True),
    Column("metadata", JSON, nullable=True),
)
