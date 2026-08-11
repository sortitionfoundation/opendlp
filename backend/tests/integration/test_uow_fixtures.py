"""ABOUTME: Tests for the shared `sql_uow` test fixture
ABOUTME: An already-entered SqlAlchemyUnitOfWork for integration tests that need only one context"""

import uuid

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


class TestSqlUowFixture:
    def test_is_already_inside_its_context(self, sql_uow):
        assert isinstance(sql_uow, SqlAlchemyUnitOfWork)
        assert sql_uow.users.get(uuid.uuid4()) is None

    def test_writes_are_visible_within_the_same_context(self, sql_uow):
        user = User(email=f"sql-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        sql_uow.users.add(user)
        sql_uow.commit()

        assert sql_uow.users.get(user.id) is not None

    def test_commits_on_teardown(self, sql_uow, postgres_session_factory):
        """The fixture exits its block at teardown, so uncommitted work still lands."""
        user = User(email=f"teardown-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        sql_uow.users.add(user)
        sql_uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as other:
            assert other.users.get(user.id) is not None
