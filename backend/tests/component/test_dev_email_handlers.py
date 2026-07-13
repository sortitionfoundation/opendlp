"""ABOUTME: Component tests for the dev /service-docs email-template handlers
ABOUTME: Drives the 7 _handle_* functions through real services over a FakeUnitOfWork, asserting on real outcomes"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.entrypoints.blueprints.dev import (
    _handle_assign_auto_reply_template,
    _handle_auto_reply_readiness_problems,
    _handle_create_email_template,
    _handle_delete_email_template,
    _handle_get_email_template,
    _handle_list_email_templates,
    _handle_update_email_template,
    _serialise_email_template,
)
from tests.fakes import FakeStore, FakeUnitOfWork


def _seed_admin(store: FakeStore) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    with FakeUnitOfWork(store=store) as uow:
        uow.users.add(user)
        uow.commit()
    return user


def _seed_assembly(store: FakeStore) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    with FakeUnitOfWork(store=store) as uow:
        uow.assemblies.add(assembly)
        uow.commit()
    return assembly


def _seed_page(store: FakeStore, assembly_id: uuid.UUID, *, auto_reply_template_id=None) -> RegistrationPage:
    page = RegistrationPage(
        assembly_id=assembly_id,
        url_slug="my-slug",
        status=RegistrationPageStatus.TEST,
        auto_reply_email_template_id=auto_reply_template_id,
    )
    with FakeUnitOfWork(store=store) as uow:
        uow.registration_pages.add(page)
        uow.commit()
    return page


def _seed_template(
    store: FakeStore,
    assembly_id: uuid.UUID,
    *,
    name="Registration auto-reply",
    subject="Hi {{ respondent.first_name_or_friend }}",
    body_html="<p>Hello!</p>",
) -> EmailTemplate:
    template = EmailTemplate(assembly_id=assembly_id, name=name, subject=subject, body_html=body_html)
    with FakeUnitOfWork(store=store) as uow:
        uow.email_templates.add(template)
        uow.commit()
    return template


def _seed_email_field(store: FakeStore, assembly_id: uuid.UUID, *, on_page: FieldOnRegistrationPage) -> None:
    """The auto-reply readiness check inspects the assembly's email field's on_registration_page value."""
    field = RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key="email",
        label="Email",
        group=RespondentFieldGroup.OTHER,
        sort_order=10,
        field_type=FieldType.EMAIL,
        is_fixed=True,
        on_registration_page=on_page,
    )
    with FakeUnitOfWork(store=store) as uow:
        uow.respondent_field_definitions.add(field)
        uow.commit()


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin(fake_store):
    return _seed_admin(fake_store)


@pytest.fixture
def assembly(fake_store):
    return _seed_assembly(fake_store)


@pytest.fixture
def app(fake_store):
    from opendlp.entrypoints.flask_app import create_app  # noqa: PLC0415

    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def as_admin(app, admin):
    """Push a request context with current_user set to the seeded admin."""
    with (
        app.test_request_context(),
        patch("opendlp.entrypoints.blueprints.dev.current_user", SimpleNamespace(id=admin.id)),
    ):
        yield


def _uow(fake_store) -> FakeUnitOfWork:
    return FakeUnitOfWork(store=fake_store)


class TestSerialiseEmailTemplate:
    def test_emits_expected_fields_with_body_preview(self):
        template = EmailTemplate(
            assembly_id=uuid.uuid4(),
            name="Auto-reply",
            subject="Thanks!",
            body_html="<p>" + "x" * 500 + "</p>",
        )
        result = _serialise_email_template(template)
        assert result["id"] == str(template.id)
        assert result["assembly_id"] == str(template.assembly_id)
        assert result["name"] == "Auto-reply"
        assert result["subject"] == "Thanks!"
        # Long bodies are truncated with an ellipsis for the preview.
        assert result["body_html_preview"].endswith("...")
        assert len(result["body_html_preview"]) < len(template.body_html)
        # Byte size reflects the full body, not the truncated preview.
        assert result["body_html_bytes"] == len(template.body_html.encode("utf-8"))

    def test_short_body_is_not_truncated(self):
        template = EmailTemplate(assembly_id=uuid.uuid4(), name="A", subject="B", body_html="<p>short</p>")
        assert _serialise_email_template(template)["body_html_preview"] == "<p>short</p>"


class TestHandleCreateEmailTemplate:
    def test_creates_and_returns_serialised_template(self, fake_store, assembly, as_admin):
        result = _handle_create_email_template(
            uow=_uow(fake_store),
            params={
                "assembly_id": str(assembly.id),
                "name": "New template",
                "subject": "Subject",
                "body_html": "<p>Body</p>",
            },
        )

        assert result["status"] == "success"
        assert result["template"]["name"] == "New template"
        with _uow(fake_store) as uow:
            stored = uow.email_templates.list_by_assembly(assembly.id)
        assert len(stored) == 1

    def test_invalid_template_returns_error_with_problems(self, fake_store, assembly, as_admin):
        # Empty name/subject/body all violate the domain-level validator.
        result = _handle_create_email_template(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id), "name": "", "subject": "", "body_html": ""},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "EmailTemplateInvalid"
        assert result["problems"], "expected the list of validation problems to be surfaced"


class TestHandleListEmailTemplates:
    def test_returns_all_templates_for_assembly(self, fake_store, assembly, as_admin):
        _seed_template(fake_store, assembly.id, name="A")
        _seed_template(fake_store, assembly.id, name="B")

        result = _handle_list_email_templates(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id)},
        )
        assert result["status"] == "success"
        assert result["total_count"] == 2
        names = {t["name"] for t in result["templates"]}
        assert names == {"A", "B"}


class TestHandleGetEmailTemplate:
    def test_returns_serialised_template(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id, name="Detailed")

        result = _handle_get_email_template(
            uow=_uow(fake_store),
            params={"template_id": str(template.id)},
        )
        assert result["status"] == "success"
        assert result["template"]["id"] == str(template.id)
        assert result["template"]["name"] == "Detailed"

    def test_missing_template_returns_error(self, fake_store, assembly, as_admin):
        result = _handle_get_email_template(
            uow=_uow(fake_store),
            params={"template_id": str(uuid.uuid4())},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "EmailTemplateNotFoundError"


class TestHandleUpdateEmailTemplate:
    def test_updates_fields_and_returns_serialised_template(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id, name="Old", subject="Old subj", body_html="<p>Old</p>")

        result = _handle_update_email_template(
            uow=_uow(fake_store),
            params={
                "template_id": str(template.id),
                "name": "Renamed",
                "subject": "New subj",
                "body_html": "<p>New</p>",
            },
        )
        assert result["status"] == "success"
        with _uow(fake_store) as uow:
            saved = uow.email_templates.get(template.id)
        assert saved.name == "Renamed"
        assert saved.subject == "New subj"

    def test_invalid_update_returns_error_with_problems(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id)

        result = _handle_update_email_template(
            uow=_uow(fake_store),
            params={
                "template_id": str(template.id),
                "name": "",
                "subject": "",
                "body_html": "",
            },
        )
        assert result["status"] == "error"
        assert result["error_type"] == "EmailTemplateInvalid"
        assert result["problems"]


class TestHandleDeleteEmailTemplate:
    def test_deletes_and_returns_id(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id)

        result = _handle_delete_email_template(
            uow=_uow(fake_store),
            params={"template_id": str(template.id)},
        )
        assert result == {"status": "success", "deleted_template_id": str(template.id)}
        with _uow(fake_store) as uow:
            assert uow.email_templates.list_by_assembly(assembly.id) == []


class TestHandleAssignAutoReplyTemplate:
    def test_assign_sets_the_page_fk(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id)
        _seed_page(fake_store, assembly.id)

        result = _handle_assign_auto_reply_template(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id), "template_id": str(template.id)},
        )
        assert result["status"] == "success"
        assert result["auto_reply_email_template_id"] == str(template.id)
        with _uow(fake_store) as uow:
            page = uow.registration_pages.get_by_assembly_id(assembly.id)
        assert page.auto_reply_email_template_id == template.id

    def test_clear_unassigns_the_template(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id)
        _seed_page(fake_store, assembly.id, auto_reply_template_id=template.id)

        result = _handle_assign_auto_reply_template(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id), "template_id": ""},
        )
        assert result["status"] == "success"
        assert result["auto_reply_email_template_id"] is None
        with _uow(fake_store) as uow:
            page = uow.registration_pages.get_by_assembly_id(assembly.id)
        assert page.auto_reply_email_template_id is None

    def test_no_page_returns_error(self, fake_store, assembly, as_admin):
        template = _seed_template(fake_store, assembly.id)

        result = _handle_assign_auto_reply_template(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id), "template_id": str(template.id)},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "RegistrationPageNotFoundError"


class TestHandleAutoReplyReadinessProblems:
    def test_no_email_field_reports_error_severity(self, fake_store, assembly, as_admin):
        # No email field configured at all — the auto-reply cannot deliver.
        result = _handle_auto_reply_readiness_problems(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id)},
        )
        assert result["status"] == "success"
        assert result["problem_count"] == 1
        assert result["problems"][0]["severity"] == "error"

    def test_optional_email_field_reports_warning(self, fake_store, assembly, as_admin):
        _seed_email_field(fake_store, assembly.id, on_page=FieldOnRegistrationPage.YES_OPTIONAL)

        result = _handle_auto_reply_readiness_problems(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id)},
        )
        assert result["problem_count"] == 1
        assert result["problems"][0]["severity"] == "warning"

    def test_required_email_field_reports_no_problems(self, fake_store, assembly, as_admin):
        _seed_email_field(fake_store, assembly.id, on_page=FieldOnRegistrationPage.YES_REQUIRED)

        result = _handle_auto_reply_readiness_problems(
            uow=_uow(fake_store),
            params={"assembly_id": str(assembly.id)},
        )
        assert result["status"] == "success"
        assert result["problem_count"] == 0
        assert result["problems"] == []
