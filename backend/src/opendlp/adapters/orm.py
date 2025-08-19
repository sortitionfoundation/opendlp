"""ABOUTME: SQLAlchemy table definitions and imperative mapping for OpenDLP
ABOUTME: Defines database schema with proper relationships, indexes, and JSON columns"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Column, Date, ForeignKey, String, Table, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import registry
from sqlalchemy.sql.sqltypes import String as SQLString

from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole


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

        return value


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


# Create a registry for imperative mapping
mapper_registry = registry()
metadata = mapper_registry.metadata

# Users table
users = Table(
    "users",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("email", String(255), nullable=False, unique=True),
    Column("first_name", String(100), nullable=False, default=""),
    Column("last_name", String(100), nullable=False, default=""),
    Column("password_hash", String(255), nullable=True),
    Column("oauth_provider", String(50), nullable=True),
    Column("oauth_id", String(255), nullable=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("is_active", Boolean, nullable=False, default=True),
)

# Assemblies table
assemblies = Table(
    "assemblies",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("title", String(255), nullable=False),
    Column("question", Text, nullable=False, default=""),
    Column("gsheet", String(500), nullable=False, default=""),
    Column("first_assembly_date", Date, nullable=True),
    Column("status", EnumAsString(AssemblyStatus, 50), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("updated_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    # JSON column for flexible assembly configuration
    Column("config", JSON, nullable=True),
)

# User assembly roles table - many-to-many relationship
user_assembly_roles = Table(
    "user_assembly_roles",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("user_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("assembly_id", CrossDatabaseUUID(), ForeignKey("assemblies.id", ondelete="CASCADE"), nullable=False),
    Column("role", EnumAsString(AssemblyRole, 50), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
)

# User invites table
user_invites = Table(
    "user_invites",
    metadata,
    Column("id", CrossDatabaseUUID(), primary_key=True, default=uuid.uuid4),
    Column("code", String(50), nullable=False, unique=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_by", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("expires_at", TZAwareDatetime(), nullable=False),
    Column("used_by", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("used_at", TZAwareDatetime(), nullable=True),
)


# Create indexes for performance
def create_indexes() -> None:
    """Create database indexes for commonly queried fields."""
    from sqlalchemy import Index

    # User indexes
    Index("ix_users_email", users.c.email)
    Index("ix_users_oauth_provider_id", users.c.oauth_provider, users.c.oauth_id)

    # Assembly indexes
    Index("ix_assemblies_status", assemblies.c.status)
    Index("ix_assemblies_created_at", assemblies.c.created_at)

    # User assembly roles indexes
    Index("ix_user_assembly_roles_user_id", user_assembly_roles.c.user_id)
    Index("ix_user_assembly_roles_assembly_id", user_assembly_roles.c.assembly_id)
    Index("ix_user_assembly_roles_user_assembly", user_assembly_roles.c.user_id, user_assembly_roles.c.assembly_id)

    # User invites indexes
    Index("ix_user_invites_code", user_invites.c.code)
    Index("ix_user_invites_created_by", user_invites.c.created_by)
    Index("ix_user_invites_expires_at", user_invites.c.expires_at)
    Index("ix_user_invites_used_by", user_invites.c.used_by)
