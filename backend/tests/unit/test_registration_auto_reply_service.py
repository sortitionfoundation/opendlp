"""ABOUTME: Service-level tests for the registration auto-reply over a FakeUnitOfWork.
ABOUTME: Submits a registration then sends the templated auto-reply and checks the record."""

import uuid
from unittest.mock import MagicMock

import pytest

from opendlp.adapters.email import ConsoleEmailAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.email_send_record import EmailSendOutcome
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
from opendlp.service_layer.email_send_service import send_registration_auto_reply, send_test_auto_reply
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.registration_submission_service import submit_registration
from tests.fakes import FakeUnitOfWork

_SCHEMA = [
    ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.YES_REQUIRED),
    ("consent", FieldType.BOOL_OR_NONE, True, FieldOnRegistrationPage.YES_REQUIRED),
    ("first_name", FieldType.TEXT, False, FieldOnRegistrationPage.YES_REQUIRED),
]


def _build(uow, status: RegistrationPageStatus) -> tuple[FakeUnitOfWork, str]:
    assembly = Assembly(
        title="Climate Assembly",
        question="What should we do about transport?",
        status=AssemblyStatus.ACTIVE,
        reply_to_name="The Team",
        reply_to_email="team@example.com",
    )
    uow.assemblies.add(assembly)
    template = EmailTemplate(
        assembly_id=assembly.id,
        name="Auto-reply",
        subject="Thanks {{ respondent.first_name_or_friend }}",
        body_html="<p>Hi {{ respondent.first_name_or_friend }}, you registered for {{ assembly.title }}.</p>",
    )
    uow.email_templates.add(template)
    uow.registration_pages.add(
        RegistrationPage(
            assembly_id=assembly.id,
            url_slug="join-us",
            status=status,
            auto_reply_email_template_id=template.id,
        )
    )
    for sort, (key, ftype, is_fixed, on_page) in enumerate(_SCHEMA):
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key=key,
                label=key.replace("_", " ").capitalize(),
                group=RespondentFieldGroup.OTHER,
                sort_order=(sort + 1) * 10,
                field_type=ftype,
                is_fixed=is_fixed,
                on_registration_page=on_page,
            )
        )
    return uow, "join-us"


def test_live_submission_sends_auto_reply_and_records_it(uow) -> None:
    _, slug = _build(uow, RegistrationPageStatus.PUBLISHED)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )
    assert result.is_valid

    record = send_registration_auto_reply(uow, adapter, respondent=result.respondent)

    assert record is not None
    assert record.outcome is EmailSendOutcome.SENT
    assert record.missing_variables == []
    stored = uow.respondent_email_send_records.list_by_respondent(result.respondent.id)
    assert len(stored) == 1

    kwargs = adapter.send_email.call_args.kwargs
    assert kwargs["to"] == ["ada@example.com"]
    assert kwargs["subject"] == "Thanks Ada"
    assert kwargs["reply_to"] == ("The Team", "team@example.com")
    assert "Hi Ada, you registered for Climate Assembly." in kwargs["html_body"]


def test_autoescapes_untrusted_respondent_name(uow) -> None:
    _, slug = _build(uow, RegistrationPageStatus.PUBLISHED)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "<script>bad()</script>"},
    )

    send_registration_auto_reply(uow, adapter, respondent=result.respondent)

    html_body = adapter.send_email.call_args.kwargs["html_body"]
    assert "<script>bad()</script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_console_adapter_send_succeeds_end_to_end(uow) -> None:
    _, slug = _build(uow, RegistrationPageStatus.PUBLISHED)

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )

    record = send_registration_auto_reply(uow, ConsoleEmailAdapter(), respondent=result.respondent)

    assert record is not None
    assert record.outcome is EmailSendOutcome.SENT


def _page(uow) -> RegistrationPage:
    return next(p for p in uow.registration_pages._items)


def _admin(uow) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def test_test_send_uses_sample_respondent_and_writes_no_record(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=_page(uow).id, to_email="manager@example.com")

    assert result.sent is True
    assert result.missing_variables == []
    kwargs = adapter.send_email.call_args.kwargs
    assert kwargs["to"] == ["manager@example.com"]
    assert kwargs["subject"] == "Thanks Alex"
    assert kwargs["reply_to"] == ("The Team", "team@example.com")
    assert "Hi Alex, you registered for Climate Assembly." in kwargs["html_body"]
    assert uow.respondent_email_send_records._items == []


def test_test_send_reports_missing_variables(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    page = _page(uow)
    template = uow.email_templates.get(page.auto_reply_email_template_id)
    template.subject = "Hi {{ nonexistent_variable }}"
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=page.id, to_email="manager@example.com")

    assert result.sent is True
    assert result.missing_variables == ["nonexistent_variable"]


def test_test_send_reports_adapter_failure(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    adapter = MagicMock()
    adapter.send_email.return_value = False

    result = send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=_page(uow).id, to_email="manager@example.com")

    assert result.sent is False


def test_test_send_requires_manage_permission(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    user = User(email="plain@example.com", global_role=GlobalRole.USER, password_hash="hash")
    uow.users.add(user)
    adapter = MagicMock()

    with pytest.raises(InsufficientPermissions):
        send_test_auto_reply(uow, adapter, user_id=user.id, page_id=_page(uow).id, to_email="manager@example.com")
    adapter.send_email.assert_not_called()


def test_test_send_with_unknown_user_or_page_raises(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    adapter = MagicMock()

    with pytest.raises(UserNotFoundError):
        send_test_auto_reply(uow, adapter, user_id=uuid.uuid4(), page_id=_page(uow).id, to_email="m@example.com")
    with pytest.raises(RegistrationPageNotFoundError):
        send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=uuid.uuid4(), to_email="m@example.com")
    adapter.send_email.assert_not_called()


def test_test_send_with_missing_assembly_raises(uow) -> None:
    admin = _admin(uow)
    orphan = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="orphan-page")
    uow.registration_pages.add(orphan)

    with pytest.raises(AssemblyNotFoundError):
        send_test_auto_reply(uow, MagicMock(), user_id=admin.id, page_id=orphan.id, to_email="m@example.com")


def test_test_send_with_dangling_template_id_raises(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    page = _page(uow)
    page.auto_reply_email_template_id = uuid.uuid4()

    with pytest.raises(EmailTemplateNotFoundError):
        send_test_auto_reply(uow, MagicMock(), user_id=admin.id, page_id=page.id, to_email="m@example.com")


def test_test_send_survives_adapter_exception(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    adapter = MagicMock()
    adapter.send_email.side_effect = RuntimeError("smtp down")

    result = send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=_page(uow).id, to_email="m@example.com")

    assert result.sent is False


def test_test_send_without_template_raises(uow) -> None:
    _build(uow, RegistrationPageStatus.TEST)
    admin = _admin(uow)
    page = _page(uow)
    page.auto_reply_email_template_id = None
    adapter = MagicMock()

    with pytest.raises(EmailTemplateNotFoundError):
        send_test_auto_reply(uow, adapter, user_id=admin.id, page_id=page.id, to_email="manager@example.com")
    adapter.send_email.assert_not_called()


def test_test_submission_sends_auto_reply(uow) -> None:
    _, slug = _build(uow, RegistrationPageStatus.TEST)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )

    record = send_registration_auto_reply(uow, adapter, respondent=result.respondent)

    assert record is not None
    assert record.outcome is EmailSendOutcome.SENT
    adapter.send_email.assert_called_once()
