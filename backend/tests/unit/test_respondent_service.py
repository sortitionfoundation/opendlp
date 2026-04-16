"""ABOUTME: Unit tests for respondent service layer functions
ABOUTME: Uses FakeUnitOfWork to test service-level behaviour without a database"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import respondent_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    RespondentNotFoundError,
    UserNotFoundError,
)
from tests.fakes import FakeUnitOfWork


def _seed(uow: FakeUnitOfWork, *, global_role: GlobalRole = GlobalRole.ADMIN) -> tuple[User, Assembly, Respondent]:
    user = User(email="admin@example.com", global_role=global_role, password_hash="hash")
    uow.users.add(user)

    assembly = Assembly(title="Test Assembly")
    uow.assemblies.add(assembly)

    respondent = Respondent(assembly_id=assembly.id, external_id="R001", email="alice@example.com")
    uow.respondents.add(respondent)

    return user, assembly, respondent


class TestGetRespondent:
    def test_returns_respondent_for_admin(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        result = respondent_service.get_respondent(uow, user.id, assembly.id, respondent.id)

        assert result.id == respondent.id
        assert result.external_id == "R001"
        assert result.email == "alice@example.com"

    def test_returns_detached_copy(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        result = respondent_service.get_respondent(uow, user.id, assembly.id, respondent.id)

        assert result is not respondent

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)

        with pytest.raises(UserNotFoundError):
            respondent_service.get_respondent(uow, uuid.uuid4(), assembly.id, respondent.id)

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _, respondent = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            respondent_service.get_respondent(uow, user.id, uuid.uuid4(), respondent.id)

    def test_raises_when_user_lacks_permission(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            respondent_service.get_respondent(uow, outsider.id, assembly.id, respondent.id)

    def test_raises_when_respondent_missing(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.get_respondent(uow, user.id, assembly.id, uuid.uuid4())

    def test_raises_when_respondent_belongs_to_other_assembly(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        other_assembly = Assembly(title="Other")
        uow.assemblies.add(other_assembly)
        other_respondent = Respondent(assembly_id=other_assembly.id, external_id="R-OTHER")
        uow.respondents.add(other_respondent)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.get_respondent(uow, user.id, assembly.id, other_respondent.id)
