"""ABOUTME: SQLAlchemy table definitions and imperative mapping for OpenDLP
ABOUTME: Defines database schema with proper relationships, indexes, and JSON columns"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Column, Date, ForeignKey, String, Table, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import registry

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


# Create a registry for imperative mapping
mapper_registry = registry()
metadata = mapper_registry.metadata

# Users table
users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("email", String(255), nullable=False, unique=True),
    Column("first_name", String(100), nullable=False, default=""),
    Column("last_name", String(100), nullable=False, default=""),
    Column("password_hash", String(255), nullable=True),
    Column("oauth_provider", String(50), nullable=True),
    Column("oauth_id", String(255), nullable=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False, default=aware_utcnow),
    Column("is_active", Boolean, nullable=False, default=True),
)

# Assemblies table
assemblies = Table(
    "assemblies",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("title", String(255), nullable=False),
    Column("question", Text, nullable=False),
    Column("gsheet", String(500), nullable=False),
    Column("first_assembly_date", Date, nullable=False),
    Column("status", EnumAsString(AssemblyStatus, 50), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False, default=aware_utcnow),
    Column("updated_at", TIMESTAMP, nullable=False, default=aware_utcnow),
    # JSON column for flexible assembly configuration
    Column("config", JSON, nullable=True),
)

# User assembly roles table - many-to-many relationship
user_assembly_roles = Table(
    "user_assembly_roles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("assembly_id", UUID(as_uuid=True), ForeignKey("assemblies.id", ondelete="CASCADE"), nullable=False),
    Column("role", EnumAsString(AssemblyRole, 50), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False, default=aware_utcnow),
)

# User invites table
user_invites = Table(
    "user_invites",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("code", String(50), nullable=False, unique=True),
    Column("global_role", EnumAsString(GlobalRole, 50), nullable=False),
    Column("created_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False, default=aware_utcnow),
    Column("expires_at", TIMESTAMP, nullable=False),
    Column("used_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("used_at", TIMESTAMP, nullable=True),
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
