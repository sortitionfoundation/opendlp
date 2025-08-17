import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine

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


def seed_database() -> tuple[Iterable[tuple[User, str]], Iterable[UserInvite], Iterable[Assembly]]:
    """Seed the database with test data."""
    with SqlAlchemyUnitOfWork() as uow:
        # Check if data already exists
        admin_email = "admin@opendlp.example"
        existing_users = uow.users.list()
        if existing_users:
            raise UserAlreadyExists(admin_email)

        now = datetime.now(UTC)

        # Create admin user
        admin_user = User(
            user_id=uuid.uuid4(),
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
        uow.commit()

    with SqlAlchemyUnitOfWork() as uow:
        # Create some sample invites
        admin_invite = UserInvite(
            global_role=GlobalRole.ADMIN,
            created_by=admin_user.id,
            expires_in_hours=168,
            invite_id=uuid.uuid4(),
            code=generate_invite_code(),
            created_at=now,
            expires_at=now.replace(hour=23, minute=59, second=59) + timedelta(days=7),
        )
        uow.user_invites.add(admin_invite)

        organiser_invite = UserInvite(
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=admin_user.id,
            expires_in_hours=168,
            invite_id=uuid.uuid4(),
            code=generate_invite_code(),
            created_at=now,
            expires_at=now.replace(hour=23, minute=59, second=59) + timedelta(days=7),
        )
        uow.user_invites.add(organiser_invite)

        user_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
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
            gsheet="https://docs.google.com/spreadsheets/d/example",
            status=AssemblyStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        uow.assemblies.add(assembly)

        uow.commit()

    return (
        ((admin_user, "admin123"), (organiser_user, "organiser123"), (regular_user, "user123")),
        (admin_invite, organiser_invite, user_invite),
        (assembly,),
    )
