"""ABOUTME: Unit tests for the email template service layer
ABOUTME: Covers CRUD, permission checks, validation and auto-reply assignment"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import email_template_service as service
from opendlp.service_layer.exceptions import (
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
)
from tests.fakes import FakeUnitOfWork


def _admin(uow: FakeUnitOfWork) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def _assembly(uow: FakeUnitOfWork) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    return assembly


def _viewer(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"viewer-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


VALID = {"name": "Auto-reply", "subject": "Thanks {{ respondent.first_name_or_friend }}", "body_html": "<p>Hi</p>"}


class TestCreate:
    def test_create_persists_template(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        assert template.assembly_id == assembly.id
        assert template.name == "Auto-reply"
        assert uow.email_templates.get(template.id) is not None
        assert uow.committed

    def test_create_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.create_email_template(uow, viewer.id, assembly.id, **VALID)

    def test_create_rejects_invalid_template(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(EmailTemplateInvalid) as exc:
            service.create_email_template(uow, admin.id, assembly.id, name="", subject="", body_html="")
        assert exc.value.problems

    def test_create_rejects_oversized_body(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        huge = "<p>" + ("x" * (2 * 1024 * 1024)) + "</p>"

        with pytest.raises(EmailTemplateInvalid):
            service.create_email_template(uow, admin.id, assembly.id, name="N", subject="S", body_html=huge)


class TestUpdate:
    def test_update_changes_fields(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        updated = service.update_email_template(uow, admin.id, template.id, name="Renamed")

        assert updated.name == "Renamed"
        assert uow.email_templates.get(template.id).name == "Renamed"

    def test_update_rejects_invalid(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with pytest.raises(EmailTemplateInvalid):
            service.update_email_template(uow, admin.id, template.id, subject="")

    def test_update_missing_template_raises(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        with pytest.raises(EmailTemplateNotFoundError):
            service.update_email_template(uow, admin.id, uuid.uuid4(), name="x")


class TestGetAndList:
    def test_list_scoped_to_assembly(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        other = _assembly(uow)
        mine = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        service.create_email_template(uow, admin.id, other.id, **VALID)

        templates = service.list_email_templates(uow, admin.id, assembly.id)

        assert [t.id for t in templates] == [mine.id]

    def test_get_requires_view_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        outsider = User(email=f"out-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            service.get_email_template(uow, outsider.id, template.id)


class TestDelete:
    def test_delete_removes_template(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        service.delete_email_template(uow, admin.id, template.id)

        assert uow.email_templates.get(template.id) is None


class TestAssignAutoReply:
    def test_assign_sets_page_fk(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id)

        assert uow.registration_pages.get_by_assembly_id(assembly.id).auto_reply_email_template_id == template.id

    def test_assign_none_clears_fk(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        uow.registration_pages.add(page)

        service.assign_auto_reply_template(uow, admin.id, assembly.id, None)

        assert uow.registration_pages.get_by_assembly_id(assembly.id).auto_reply_email_template_id is None

    def test_assign_requires_existing_page(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with pytest.raises(RegistrationPageNotFoundError):
            service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id)

    def test_assign_rejects_template_from_other_assembly(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        other = _assembly(uow)
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        foreign = service.create_email_template(uow, admin.id, other.id, **VALID)

        with pytest.raises(EmailTemplateNotFoundError):
            service.assign_auto_reply_template(uow, admin.id, assembly.id, foreign.id)
