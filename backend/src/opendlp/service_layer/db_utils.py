import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from opendlp.adapters import database, orm
from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite, generate_invite_code
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.service_layer.exceptions import UserAlreadyExists
from opendlp.service_layer.security import hash_password
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


def create_tables(engine: Engine) -> None:
    """Create all database tables.

    Args:
        engine: SQLAlchemy engine instance
    """
    try:
        orm.metadata.create_all(engine)
    except Exception as e:  # pragma: no cover
        raise database.DatabaseError(f"Failed to create tables: {e}") from e


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
        raise database.DatabaseError(f"Failed to drop tables: {e}") from e


def seed_database(
    session_factory: sessionmaker | None = None,
) -> tuple[Iterable[tuple[User, str]], Iterable[UserInvite], Iterable[Assembly]]:
    """Seed the database with test data."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        # Check if data already exists
        admin_email = "admin@opendlp.example"
        admin_user_id = uuid.uuid4()
        existing_users = uow.users.list()
        if existing_users:
            raise UserAlreadyExists(admin_email)

        now = datetime.now(UTC)

        # Create admin user
        admin_user = User(
            user_id=admin_user_id,
            email=admin_email,
            password_hash=hash_password("admin123"),
            first_name="Admin",
            last_name="User",
            global_role=GlobalRole.ADMIN,
            created_at=now,
            is_active=True,
        )
        uow.users.add(admin_user)

        # Create global organiser user
        organiser_user = User(
            user_id=uuid.uuid4(),
            email="organiser@opendlp.example",
            password_hash=hash_password("organiser123"),
            first_name="Global",
            last_name="Organiser",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_at=now,
            is_active=True,
        )
        uow.users.add(organiser_user)

        # Create regular user
        regular_user = User(
            user_id=uuid.uuid4(),
            email="user@opendlp.example",
            password_hash=hash_password("user123"),
            first_name="Regular",
            last_name="User",
            global_role=GlobalRole.USER,
            created_at=now,
            is_active=True,
        )
        uow.users.add(regular_user)
        # we need to commit so that the following items can refer to these
        user_passwords = (
            (admin_user.create_detached_copy(), "admin123"),
            (organiser_user.create_detached_copy(), "organiser123"),
            (regular_user.create_detached_copy(), "user123"),
        )
        uow.flush()  # make sqlalchemy commit enough to get user IDs

        # Create some sample invites
        admin_invite = UserInvite(
            global_role=GlobalRole.ADMIN,
            created_by=admin_user_id,
            expires_in_hours=168,
            invite_id=uuid.uuid4(),
            code=generate_invite_code(),
            created_at=now,
            expires_at=now.replace(hour=23, minute=59, second=59) + timedelta(days=7),
        )
        uow.user_invites.add(admin_invite)

        organiser_invite = UserInvite(
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=admin_user_id,
            expires_in_hours=168,
            invite_id=uuid.uuid4(),
            code=generate_invite_code(),
            created_at=now,
            expires_at=now.replace(hour=23, minute=59, second=59) + timedelta(days=7),
        )
        uow.user_invites.add(organiser_invite)

        user_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=admin_user_id,
            expires_in_hours=168,
            invite_id=uuid.uuid4(),
            code=generate_invite_code(),
            created_at=now,
            expires_at=now.replace(hour=23, minute=59, second=59) + timedelta(days=7),
        )
        uow.user_invites.add(user_invite)

        # Create sample assembly
        assembly = Assembly(
            assembly_id=uuid.uuid4(),
            title="Sample Citizens' Assembly",
            question="How can we improve public transportation in our city?",
            gsheet_url="https://docs.google.com/spreadsheets/d/example",
            status=AssemblyStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        uow.assemblies.add(assembly)

        invites = (
            admin_invite.create_detached_copy(),
            organiser_invite.create_detached_copy(),
            user_invite.create_detached_copy(),
        )
        assemblies = (assembly.create_detached_copy(),)

        uow.commit()

    return user_passwords, invites, assemblies
