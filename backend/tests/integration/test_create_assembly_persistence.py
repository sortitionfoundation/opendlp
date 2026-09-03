"""ABOUTME: Integration tests that creating an assembly persists against a real Postgres.
ABOUTME: The new assembly row and the creator's role row are inserted in one commit, FK ordering and all."""

import pytest
from sqlalchemy import text

from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def organiser(postgres_session):
    user = User(
        email="creator@example.com",
        global_role=GlobalRole.ORGANISER,
        password_hash="hash",  # pragma: allowlist secret
    )
    postgres_session.add(user)
    postgres_session.commit()
    return user


class TestCreateAssemblyPersistence:
    def test_assembly_and_creator_role_land_in_one_commit(self, postgres_session_factory, organiser):
        """The role row references the assembly row, so the inserts have to be ordered correctly.

        SQLAlchemy sorts inserts by table dependency, but this is exactly the
        kind of thing that only fails against a real database.
        """
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Committed together", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            reloaded_user = fresh.users.get(organiser.id)
            assert reloaded_user.get_assembly_role(assembly.id) == AssemblyRole.ASSEMBLY_MANAGER

    def test_created_by_user_id_survives_the_round_trip(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Has a creator", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            assert fresh.assemblies.get(assembly.id).created_by_user_id == organiser.id

    def test_the_creator_sees_it_on_their_dashboard(self, postgres_session_factory, organiser):
        """The point of granting the role: an organiser can reach what they create."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Mine", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            visible = list(fresh.assemblies.get_assemblies_for_user(organiser.id))
            assert [a.id for a in visible] == [assembly.id]

    def test_deleting_the_creator_leaves_the_assembly(self, postgres_session_factory, organiser):
        """The FK is SET NULL, not CASCADE - losing a user must not lose their assemblies."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Outlives its creator", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.session.delete(uow.users.get(organiser.id))
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            survivor = fresh.assemblies.get(assembly.id)
            assert survivor is not None
            assert survivor.created_by_user_id is None


class TestCreatedByColumnShape:
    """The column's shape is load-bearing, and autogenerate does not compare ON DELETE rules.

    `alembic check` confirms the migration and the ORM agree on the column
    existing; it does not confirm the delete rule, so read it back explicitly.
    """

    def test_the_foreign_key_is_set_null(self, postgres_session):
        rule = postgres_session.execute(
            text(
                """
                SELECT rc.delete_rule
                FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = rc.constraint_name
                WHERE kcu.table_name = 'assemblies' AND kcu.column_name = 'created_by_user_id'
                """
            )
        ).scalar_one()

        assert rule == "SET NULL"

    def test_the_column_is_nullable(self, postgres_session):
        """Assemblies created before the column existed have no creator to record."""
        nullable = postgres_session.execute(
            text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'assemblies' AND column_name = 'created_by_user_id'
                """
            )
        ).scalar_one()

        assert nullable == "YES"
