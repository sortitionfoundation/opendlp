"""ABOUTME: Unit tests for the email template service layer
ABOUTME: Covers CRUD, permission checks, validation and auto-reply assignment"""

import uuid
from datetime import date

import pytest
import structlog

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import email_template_service as service
from opendlp.service_layer.email_template_service import AutoReplyReadinessSeverity
from opendlp.service_layer.exceptions import (
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.registration_page_service import page_for_assembly
from tests.fakes import FakeUnitOfWork


def _email_field(assembly_id, on_page: FieldOnRegistrationPage) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key="email",
        label="Email",
        group=RespondentFieldGroup.NAME_AND_CONTACT,
        sort_order=10,
        field_type=FieldType.EMAIL,
        is_fixed=True,
        on_registration_page=on_page,
    )


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
    def test_create_persists_template(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        assert template.assembly_id == assembly.id
        assert template.name == "Auto-reply"
        assert uow.email_templates.get(template.id) is not None

    def test_create_requires_manage_permission(self, uow):
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.create_email_template(uow, viewer.id, assembly.id, **VALID)

    def test_create_rejects_invalid_template(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(EmailTemplateInvalid) as exc:
            service.create_email_template(uow, admin.id, assembly.id, name="", subject="", body_html="")
        assert exc.value.problems

    def test_create_rejects_oversized_body(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        huge = "<p>" + ("x" * (2 * 1024 * 1024)) + "</p>"

        with pytest.raises(EmailTemplateInvalid):
            service.create_email_template(uow, admin.id, assembly.id, name="N", subject="S", body_html=huge)

    def test_create_stores_reply_to(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        template = service.create_email_template(
            uow, admin.id, assembly.id, **VALID, reply_to_name="The Team", reply_to_email="team@example.com"
        )

        stored = uow.email_templates.get(template.id)
        assert stored.reply_to_name == "The Team"
        assert stored.reply_to_email == "team@example.com"

    def test_create_defaults_reply_to_to_blank(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        assert template.reply_to() is None

    def test_oversized_body_problem_is_translated(self, uow, monkeypatch):
        monkeypatch.setattr(service, "_", lambda msgid, **kwargs: "TR:" + (msgid % kwargs))
        admin, assembly = _admin(uow), _assembly(uow)
        huge = "<p>" + ("x" * (2 * 1024 * 1024)) + "</p>"

        with pytest.raises(EmailTemplateInvalid) as exc:
            service.create_email_template(uow, admin.id, assembly.id, name="N", subject="S", body_html=huge)
        assert any(p.startswith("TR:The email body must be at most") for p in exc.value.problems)


class TestUpdate:
    def test_update_changes_fields(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        updated = service.update_email_template(uow, admin.id, template.id, name="Renamed")

        assert updated.name == "Renamed"
        assert uow.email_templates.get(template.id).name == "Renamed"

    def test_update_rejects_invalid(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with pytest.raises(EmailTemplateInvalid):
            service.update_email_template(uow, admin.id, template.id, subject="")

    def test_update_sets_reply_to(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        updated = service.update_email_template(
            uow, admin.id, template.id, reply_to_name="The Team", reply_to_email="team@example.com"
        )

        assert updated.reply_to() == ("The Team", "team@example.com")
        assert uow.email_templates.get(template.id).reply_to_email == "team@example.com"

    def test_update_rejects_invalid_reply_to(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with pytest.raises(EmailTemplateInvalid) as exc:
            service.update_email_template(uow, admin.id, template.id, reply_to_email="not-an-email")
        assert exc.value.problems == ["The email address for replies is not valid"]

    def test_update_missing_template_raises(self, uow):
        admin = _admin(uow)

        with pytest.raises(EmailTemplateNotFoundError):
            service.update_email_template(uow, admin.id, uuid.uuid4(), name="x")


class TestGetAndList:
    def test_list_scoped_to_assembly(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        other = _assembly(uow)
        mine = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        service.create_email_template(uow, admin.id, other.id, **VALID)

        templates = service.list_email_templates(uow, admin.id, assembly.id)

        assert [t.id for t in templates] == [mine.id]

    def test_get_requires_view_permission(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        outsider = User(email=f"out-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            service.get_email_template(uow, outsider.id, template.id)


class TestDelete:
    def test_delete_removes_template(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        service.delete_email_template(uow, admin.id, template.id)

        assert uow.email_templates.get(template.id) is None


class TestAssignAutoReply:
    def test_assign_sets_page_fk(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id)

        assert page_for_assembly(uow, assembly.id).auto_reply_email_template_id == template.id

    def test_assign_none_clears_fk(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)
        page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        uow.registration_pages.add(page)

        service.assign_auto_reply_template(uow, admin.id, assembly.id, None)

        assert page_for_assembly(uow, assembly.id).auto_reply_email_template_id is None

    def test_assign_requires_existing_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with pytest.raises(RegistrationPageNotFoundError):
            service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id)

    def test_assign_rejects_template_from_other_assembly(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        other = _assembly(uow)
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        foreign = service.create_email_template(uow, admin.id, other.id, **VALID)

        with pytest.raises(EmailTemplateNotFoundError):
            service.assign_auto_reply_template(uow, admin.id, assembly.id, foreign.id)

    def test_assign_does_not_block_when_email_field_missing(self, uow):
        # "Advise, don't block": assignment succeeds even if the email field is NO.
        admin, assembly = _admin(uow), _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.NO))
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id)

        assert page_for_assembly(uow, assembly.id).auto_reply_email_template_id == template.id

    def test_assign_logs_reply_to_warning_for_the_assigned_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_REQUIRED))
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        template = service.create_email_template(uow, admin.id, assembly.id, **VALID)

        with structlog.testing.capture_logs() as logs:
            service.assign_auto_reply_template(uow, admin.id, assembly.id, template.id, page_id=page.id)

        readiness = [log for log in logs if log["event"].startswith("Auto-reply readiness")]
        assert len(readiness) == 1
        assert readiness[0]["log_level"] == "warning"
        assert "may not be monitored" in readiness[0]["positional_args"][2]


class TestAutoReplyReadiness:
    def test_required_email_is_ready(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_REQUIRED))

        assert service.auto_reply_readiness_problems(uow, assembly.id) == []

    def test_optional_email_warns(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_OPTIONAL))

        problems = service.auto_reply_readiness_problems(uow, assembly.id)

        assert len(problems) == 1
        assert problems[0].severity is AutoReplyReadinessSeverity.WARNING

    def test_email_not_on_page_is_error(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.NO))

        problems = service.auto_reply_readiness_problems(uow, assembly.id)

        assert len(problems) == 1
        assert problems[0].severity is AutoReplyReadinessSeverity.ERROR

    def test_a_sole_email_question_stands_in_for_the_email_field(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.NO))
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key="contact_address",
                label="Your email",
                group=RespondentFieldGroup.NAME_AND_CONTACT,
                sort_order=20,
                field_type=FieldType.EMAIL,
                on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
            )
        )

        assert service.auto_reply_readiness_problems(uow, assembly.id) == []

    def test_missing_email_field_is_error(self, uow):
        assembly = _assembly(uow)

        problems = service.auto_reply_readiness_problems(uow, assembly.id)

        assert len(problems) == 1
        assert problems[0].severity is AutoReplyReadinessSeverity.ERROR


class TestReplyToReadiness:
    def _page_with_template(self, uow, assembly: Assembly, **template_kwargs) -> RegistrationPage:
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_REQUIRED))
        template = EmailTemplate(assembly_id=assembly.id, **VALID, **template_kwargs)
        uow.email_templates.add(template)
        page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        uow.registration_pages.add(page)
        return page

    def test_warns_when_no_reply_to_resolves(self, uow):
        assembly = _assembly(uow)
        page = self._page_with_template(uow, assembly)

        problems = service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id)

        assert len(problems) == 1
        assert problems[0].severity is AutoReplyReadinessSeverity.WARNING
        assert "may not be monitored" in problems[0].message

    def test_no_warning_when_template_has_reply_to(self, uow):
        assembly = _assembly(uow)
        page = self._page_with_template(uow, assembly, reply_to_email="team@example.com")

        assert service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id) == []

    def test_no_warning_when_assembly_has_reply_to(self, uow):
        assembly = _assembly(uow)
        assembly.set_reply_to(email="assembly@example.com")
        page = self._page_with_template(uow, assembly)

        assert service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id) == []

    def test_no_warning_when_page_has_no_auto_reply(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_REQUIRED))
        page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)

        assert service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id) == []

    def test_reply_to_warning_shows_alongside_email_field_problem(self, uow):
        assembly = _assembly(uow)
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_OPTIONAL))
        template = EmailTemplate(assembly_id=assembly.id, **VALID)
        uow.email_templates.add(template)
        page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        uow.registration_pages.add(page)

        problems = service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id)

        assert len(problems) == 2
        assert all(p.severity is AutoReplyReadinessSeverity.WARNING for p in problems)

    def test_without_page_only_email_field_is_checked(self, uow):
        assembly = _assembly(uow)
        self._page_with_template(uow, assembly)

        assert service.auto_reply_readiness_problems(uow, assembly.id) == []


class TestTemplateContentReadiness:
    def _page_with_body(self, uow, assembly: Assembly, body_html: str, subject: str = "Thanks") -> RegistrationPage:
        uow.respondent_field_definitions.add(_email_field(assembly.id, FieldOnRegistrationPage.YES_REQUIRED))
        template = EmailTemplate(
            assembly_id=assembly.id,
            name="Auto-reply",
            subject=subject,
            body_html=body_html,
            reply_to_email="team@example.com",
        )
        uow.email_templates.add(template)
        page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        uow.registration_pages.add(page)
        return page

    def test_warns_about_placeholders_left_to_replace(self, uow):
        assembly = _assembly(uow)
        page = self._page_with_body(uow, assembly, "<p>[Date]: the first session.</p><p>[Your name]</p>")

        problems = service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id)

        assert len(problems) == 1
        assert problems[0].severity is AutoReplyReadinessSeverity.WARNING
        assert "[Date], [Your name]" in problems[0].message

    def test_warns_when_the_first_assembly_date_is_shown_but_not_set(self, uow):
        assembly = _assembly(uow)
        page = self._page_with_body(uow, assembly, "<p>We start on {{ assembly.first_assembly_date_text }}.</p>")

        problems = service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id)

        assert len(problems) == 1
        assert "does not have one yet" in problems[0].message

    def test_no_date_warning_once_the_assembly_has_a_date(self, uow):
        assembly = _assembly(uow)
        assembly.first_assembly_date = date(2026, 11, 14)
        page = self._page_with_body(uow, assembly, "<p>We start on {{ assembly.first_assembly_date_text }}.</p>")

        assert service.auto_reply_readiness_problems(uow, assembly.id, page_id=page.id) == []
