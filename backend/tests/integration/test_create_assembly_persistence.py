"""ABOUTME: Integration tests that creating an assembly persists against a real Postgres.
ABOUTME: The new assembly row and the creator's role row are inserted in one commit, FK ordering and all."""

import uuid

import pytest
from sqlalchemy import text

from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, DataSource, GlobalRole, RespondentsSource, TargetsSource
from opendlp.service_layer.assembly_service import create_assembly, get_assembly_creator_name, set_data_sources
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


class TestCreatorNameForTheDetailsPage:
    """The details page names the creator, which means a second query against a real user row."""

    def test_names_the_creator(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Named creator", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            reloaded = fresh.assemblies.get(assembly.id)
            assert get_assembly_creator_name(fresh, reloaded) == organiser.display_name

    def test_deleting_the_creator_leaves_nobody_to_name(self, postgres_session_factory, organiser):
        """SET NULL means the page falls back to the bare timestamp rather than erroring."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Creator departs", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.session.delete(uow.users.get(organiser.id))
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            assert get_assembly_creator_name(fresh, fresh.assemblies.get(assembly.id)) == ""


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


class TestDataSourceChoicesPersistence:
    def test_the_choices_survive_the_round_trip(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Chosen",
                created_by_user_id=organiser.id,
                data_source=DataSource.OPENDLP,
                targets_source=TargetsSource.CSV,
                respondents_source=RespondentsSource.REGISTRATION,
            )
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            reloaded = fresh.assemblies.get(assembly.id)
            assert reloaded.data_source == DataSource.OPENDLP
            assert reloaded.targets_source == TargetsSource.CSV
            assert reloaded.respondents_source == RespondentsSource.REGISTRATION

    def test_a_row_written_without_the_columns_reads_as_undecided(self, postgres_session_factory, organiser):
        """What the previous release inserts during a zero-downtime deploy: the server default fills the gap."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Old release", created_by_user_id=organiser.id)
            uow.commit()
        session = postgres_session_factory()
        try:
            row_id = uuid.uuid4()
            session.execute(
                text(
                    "INSERT INTO assemblies (id, title, question, number_to_select, status, created_at, updated_at)"
                    " SELECT :new_id, 'Inserted bare', question, number_to_select, status, created_at, updated_at"
                    " FROM assemblies WHERE id = :id"
                ),
                {"new_id": row_id, "id": assembly.id},
            )
            session.commit()
        finally:
            session.close()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            bare = fresh.assemblies.get(row_id)
            assert bare.data_source == DataSource.UNDECIDED
            assert bare.targets_source == TargetsSource.UNDECIDED
            assert bare.respondents_source == RespondentsSource.UNDECIDED

    def test_set_data_sources_is_persisted(self, postgres_session_factory, organiser):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = create_assembly(uow=uow, title="Changed later", created_by_user_id=organiser.id)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            set_data_sources(uow, organiser.id, assembly.id, data_source=DataSource.GSHEET)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as fresh:
            assert fresh.assemblies.get(assembly.id).data_source == DataSource.GSHEET
