"""ABOUTME: Database connection setup and imperative mapping for OpenDLP
ABOUTME: Configures SQLAlchemy sessions and maps domain objects to tables"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import clear_mappers as sqla_clear_mappers
from sqlalchemy.orm import relationship, sessionmaker

from opendlp.adapters import orm
from opendlp.config import get_db_uri, to_bool
from opendlp.domain import assembly, user_invites, users


class DatabaseError(Exception):
    """Base exception for database-related errors."""

    pass


def create_session_factory(database_url: str = "", echo: bool = False) -> sessionmaker:
    """Create a SQLAlchemy session factory with proper configuration."""
    database_url = database_url or get_db_uri()
    echo = to_bool(os.environ.get("DB_ECHO")) or echo
    extra_args: dict[str, int | bool] = {}
    if database_url.startswith("postgresql://"):
        extra_args = {
            "pool_pre_ping": True,  # Verify connections before use
            "pool_recycle": 3600,  # Recycle connections after 1 hour
            "pool_size": 10,  # Connection pool size
            "max_overflow": 20,  # Additional connections beyond pool_size
        }
    engine = create_engine(database_url, echo=echo, **extra_args)

    return sessionmaker(bind=engine, expire_on_commit=False)


# Track if mappers have been started
_mappers_started = False


def start_mappers() -> None:
    """Start imperative mapping between domain objects and database tables.

    This function must be called before using any domain objects with SQLAlchemy.
    The mapping is done imperatively to keep domain objects independent of SQLAlchemy.
    """
    global _mappers_started

    if _mappers_started:
        return

    try:
        # Map User domain object to users table
        orm.mapper_registry.map_imperatively(
            users.User,
            orm.users,
            properties={
                # assembly_roles will be loaded separately to maintain domain independence
            },
        )

        # Map UserAssemblyRole domain object to user_assembly_roles table
        orm.mapper_registry.map_imperatively(users.UserAssemblyRole, orm.user_assembly_roles)

        # Map Assembly domain object to assemblies table
        orm.mapper_registry.map_imperatively(
            assembly.Assembly,
            orm.assemblies,
            properties={
                "gsheet": relationship(
                    assembly.AssemblyGSheet,
                    back_populates="assembly",
                    cascade="all, delete-orphan",
                    uselist=False,  # Makes this a one-to-one relationship
                ),
            },
        )

        # Map UserInvite domain object to user_invites table
        orm.mapper_registry.map_imperatively(user_invites.UserInvite, orm.user_invites)

        # Map AssemblyGSheet domain object to assembly_gsheets table
        orm.mapper_registry.map_imperatively(
            assembly.AssemblyGSheet,
            orm.assembly_gsheets,
            properties={
                "assembly": relationship(
                    assembly.Assembly,
                    back_populates="gsheet",
                ),
            },
        )

        # Map SelectionRunRecord domain object to selection_run_records table
        orm.mapper_registry.map_imperatively(assembly.SelectionRunRecord, orm.selection_run_records)

        _mappers_started = True

    except Exception as e:  # pragma: no cover
        raise DatabaseError(f"Failed to start mappers: {e}") from e


def clear_mappers() -> None:
    sqla_clear_mappers()

    global _mappers_started
    _mappers_started = False
