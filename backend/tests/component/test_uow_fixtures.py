"""ABOUTME: Tests for the shared `shared_uow` component-test fixture
ABOUTME: An already-entered UnitOfWork over the same FakeStore the Flask app is wired to"""

import uuid

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole


class TestSharedUowFixture:
    def test_is_already_inside_its_context(self, shared_uow):
        assert shared_uow.users.get(uuid.uuid4()) is None

    def test_sees_the_same_store_as_the_app(self, shared_uow, fake_store):
        user = User(email="shared@example.com", global_role=GlobalRole.USER, password_hash="hash")
        shared_uow.users.add(user)

        assert fake_store.users.get(user.id) is user

    def test_sees_data_seeded_by_other_fixtures(self, shared_uow, admin_user):
        assert shared_uow.users.get(admin_user.id) is not None
