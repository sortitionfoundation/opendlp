"""ABOUTME: Unit tests for respondent service layer functions
ABOUTME: Uses FakeUnitOfWork to test service-level behaviour without a database"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, RespondentAction, RespondentStatus
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


def _make_assembly_manager(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"manager-{uuid.uuid4().hex[:6]}@example.com", global_role=GlobalRole.USER, password_hash="h")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
    )
    uow.users.add(user)
    return user


def _make_confirmation_caller(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"caller-{uuid.uuid4().hex[:6]}@example.com", global_role=GlobalRole.USER, password_hash="h")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


class TestDeleteRespondent:
    def test_admin_can_delete(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED
        assert respondent.email == ""
        assert len(respondent.comments) == 1
        assert respondent.comments[0].text == "gdpr request"
        assert respondent.comments[0].author_id == user.id
        assert respondent.comments[0].action is RespondentAction.DELETE

    def test_global_organiser_can_delete(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow, global_role=GlobalRole.GLOBAL_ORGANISER)

        respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED

    def test_assembly_manager_can_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        manager = _make_assembly_manager(uow, assembly)

        respondent_service.delete_respondent(uow, manager.id, assembly.id, respondent.id, comment="gdpr request")

        assert respondent.selection_status == RespondentStatus.DELETED

    def test_confirmation_caller_cannot_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        caller = _make_confirmation_caller(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            respondent_service.delete_respondent(uow, caller.id, assembly.id, respondent.id, comment="gdpr request")
        assert respondent.selection_status == RespondentStatus.POOL

    def test_unrelated_user_cannot_delete(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="h")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            respondent_service.delete_respondent(uow, outsider.id, assembly.id, respondent.id, comment="gdpr request")

    def test_empty_comment_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="comment is required"):
            respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="")
        assert respondent.selection_status == RespondentStatus.POOL

    def test_whitespace_comment_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="comment is required"):
            respondent_service.delete_respondent(uow, user.id, assembly.id, respondent.id, comment="   ")

    def test_raises_when_respondent_in_other_assembly(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)
        other = Assembly(title="Other")
        uow.assemblies.add(other)
        other_respondent = Respondent(assembly_id=other.id, external_id="R-X")
        uow.respondents.add(other_respondent)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.delete_respondent(uow, user.id, assembly.id, other_respondent.id, comment="hi")

    def test_raises_when_respondent_missing(self):
        uow = FakeUnitOfWork()
        user, assembly, _ = _seed(uow)

        with pytest.raises(RespondentNotFoundError):
            respondent_service.delete_respondent(uow, user.id, assembly.id, uuid.uuid4(), comment="hi")

    def test_raises_when_user_missing(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow)

        with pytest.raises(UserNotFoundError):
            respondent_service.delete_respondent(uow, uuid.uuid4(), assembly.id, respondent.id, comment="hi")

    def test_raises_when_assembly_missing(self):
        uow = FakeUnitOfWork()
        user, _, respondent = _seed(uow)

        with pytest.raises(AssemblyNotFoundError):
            respondent_service.delete_respondent(uow, user.id, uuid.uuid4(), respondent.id, comment="hi")


class TestAddRespondentComment:
    def test_manager_can_add_comment(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        manager = _make_assembly_manager(uow, assembly)

        respondent_service.add_respondent_comment(uow, manager.id, assembly.id, respondent.id, text="followed up")

        assert len(respondent.comments) == 1
        assert respondent.comments[0].text == "followed up"
        assert respondent.comments[0].action is RespondentAction.NONE
        assert respondent.comments[0].author_id == manager.id

    def test_confirmation_caller_cannot_add_comment(self):
        uow = FakeUnitOfWork()
        _, assembly, respondent = _seed(uow, global_role=GlobalRole.USER)
        caller = _make_confirmation_caller(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            respondent_service.add_respondent_comment(uow, caller.id, assembly.id, respondent.id, text="note")

    def test_empty_text_rejected(self):
        uow = FakeUnitOfWork()
        user, assembly, respondent = _seed(uow)

        with pytest.raises(ValueError, match="Comment text is required"):
            respondent_service.add_respondent_comment(uow, user.id, assembly.id, respondent.id, text="")


class TestGetRespondentsIncludeDeleted:
    def test_excludes_deleted_by_default(self):
        uow = FakeUnitOfWork()
        user, assembly, live = _seed(uow)
        dead = Respondent(
            assembly_id=assembly.id,
            external_id="R-DEAD",
            selection_status=RespondentStatus.DELETED,
        )
        uow.respondents.add(dead)

        results = respondent_service.get_respondents_for_assembly(uow, user.id, assembly.id)
        assert {r.id for r in results} == {live.id}

    def test_includes_deleted_when_requested(self):
        uow = FakeUnitOfWork()
        user, assembly, live = _seed(uow)
        dead = Respondent(
            assembly_id=assembly.id,
            external_id="R-DEAD",
            selection_status=RespondentStatus.DELETED,
        )
        uow.respondents.add(dead)

        results = respondent_service.get_respondents_for_assembly(uow, user.id, assembly.id, include_deleted=True)
        assert {r.id for r in results} == {live.id, dead.id}
