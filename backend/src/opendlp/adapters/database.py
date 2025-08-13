"""ABOUTME: Database connection setup and imperative mapping for OpenDLP
ABOUTME: Configures SQLAlchemy sessions and maps domain objects to tables"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from opendlp.adapters import orm
from opendlp.domain import assembly, user_invites, users


class DatabaseError(Exception):
    """Base exception for database-related errors."""

    pass


def create_session_factory(database_url: str, echo: bool = False) -> sessionmaker:
    """Create a SQLAlchemy session factory with proper configuration."""
    engine = create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_size=10,  # Connection pool size
        max_overflow=20,  # Additional connections beyond pool_size
    )

    # Create indexes
    orm.create_indexes()

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
        orm.mapper_registry.map_imperatively(assembly.Assembly, orm.assemblies)

        # Map UserInvite domain object to user_invites table
        orm.mapper_registry.map_imperatively(user_invites.UserInvite, orm.user_invites)

        _mappers_started = True

    except Exception as e:  # pragma: no cover
        raise DatabaseError(f"Failed to start mappers: {e}") from e


def create_tables(engine: Engine) -> None:
    """Create all database tables.

    Args:
        engine: SQLAlchemy engine instance
    """
    try:
        orm.metadata.create_all(engine)
    except Exception as e:  # pragma: no cover
        raise DatabaseError(f"Failed to create tables: {e}") from e


def drop_tables(engine: Engine) -> None:
    """Drop all database tables.

    Args:
        engine: SQLAlchemy engine instance

    Warning:
        This will permanently delete all data in the database!
    """
    try:
        orm.metadata.drop_all(engine)
    except Exception as e:  # pragma: no cover
        raise DatabaseError(f"Failed to drop tables: {e}") from e
