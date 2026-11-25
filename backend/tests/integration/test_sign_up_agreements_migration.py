"""ABOUTME: Tests the migration that records the terms, and the version of each document, agreed at sign-up.
ABOUTME: Runs its upgrade and downgrade against PostgreSQL in a transaction that is rolled back afterwards."""

import importlib
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection

migration = importlib.import_module("migrations.versions.c654b45ee8dc_record_the_terms_and_the_document_")

NEW_COLUMNS = {"user_data_agreement_version", "terms_agreed_at", "terms_version"}
AGREED_AT = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def connection(postgres_engine, postgres_session_factory) -> Iterator[Connection]:
    """A connection whose schema changes are undone at the end: PostgreSQL's DDL is transactional.

    The test database's tables are made from the current models, so they start
    with the migration already applied.
    """
    with postgres_engine.connect() as conn:
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()


def _run(connection: Connection, step: Callable[[], None]) -> None:
    """Run the migration's upgrade() or downgrade() on this connection, as alembic would."""
    with Operations.context(MigrationContext.configure(connection)):
        step()


def _columns(connection: Connection) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(connection).get_columns("users")}


def _insert_user(connection: Connection) -> uuid.UUID:
    """A user as an older release left them: agreed to the data agreement, with nothing else recorded."""
    user_id = uuid.uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO users (id, email, first_name, last_name, password_hash, global_role,
                               created_at, is_active, totp_enabled, user_data_agreement_agreed_at)
            VALUES (:id, :email, '', '', 'hash', 'organiser', now(), true, false, :agreed_at)
            """
        ),
        {"id": user_id, "email": f"older-{user_id}@example.com", "agreed_at": AGREED_AT},
    )
    return user_id


class TestSignUpAgreementsMigration:
    def test_downgrade_drops_the_three_columns_and_keeps_the_agreement_time(self, connection):
        _run(connection, migration.downgrade)

        columns = _columns(connection)
        assert NEW_COLUMNS.isdisjoint(columns)
        assert "user_data_agreement_agreed_at" in columns

    def test_upgrade_adds_them_back_nullable(self, connection):
        _run(connection, migration.downgrade)
        _run(connection, migration.upgrade)

        columns = _columns(connection)
        assert NEW_COLUMNS.issubset(columns)
        assert all(columns[name]["nullable"] for name in NEW_COLUMNS)
        assert isinstance(columns["terms_version"]["type"], sa.String)
        assert columns["terms_version"]["type"].length == 50
        assert columns["user_data_agreement_version"]["type"].length == 50
        assert isinstance(columns["terms_agreed_at"]["type"], sa.DateTime)
        assert columns["terms_agreed_at"]["type"].timezone is True

    def test_an_existing_user_keeps_their_agreement_time_and_has_no_versions(self, connection):
        _run(connection, migration.downgrade)
        user_id = _insert_user(connection)

        _run(connection, migration.upgrade)

        row = connection.execute(
            sa.text(
                "SELECT user_data_agreement_agreed_at, user_data_agreement_version, terms_agreed_at, terms_version "
                "FROM users WHERE id = :id"
            ),
            {"id": user_id},
        ).one()
        assert row.user_data_agreement_agreed_at == AGREED_AT
        assert row.user_data_agreement_version is None
        assert row.terms_agreed_at is None
        assert row.terms_version is None
