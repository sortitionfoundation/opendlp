"""ABOUTME: Tests for the shared `uow` test fixture
ABOUTME: The fixture hands tests an already-entered UnitOfWork so no test needs its own `with` block"""

import uuid

import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import UnitOfWorkError


class TestUowFixture:
    def test_is_already_inside_its_context(self, uow):
        assert uow.users.get(uuid.uuid4()) is None

    def test_repositories_persist_within_one_test(self, uow):
        user = User(email="fixture@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        assert uow.users.get(user.id) is user

    def test_is_strict_so_the_context_is_real(self, uow):
        """Leaving the block must withdraw the repositories, as on the real UnitOfWork."""
        uow.__exit__(None, None, None)

        with pytest.raises(UnitOfWorkError):
            uow.users.get(uuid.uuid4())

    def test_each_test_gets_a_fresh_store(self, uow):
        assert uow.fake_users._items == []
