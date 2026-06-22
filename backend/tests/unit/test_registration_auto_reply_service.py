"""ABOUTME: Service-level tests for the registration auto-reply over a FakeUnitOfWork.
ABOUTME: Submits a registration then sends the templated auto-reply and checks the record."""

from unittest.mock import MagicMock

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
from opendlp.domain.value_objects import AssemblyStatus
from opendlp.service_layer.email_send_service import send_registration_auto_reply
from opendlp.service_layer.registration_submission_service import submit_registration
from tests.fakes import FakeUnitOfWork

_SCHEMA = [
    ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.YES_REQUIRED),
    ("consent", FieldType.BOOL_OR_NONE, True, FieldOnRegistrationPage.YES_REQUIRED),
    ("first_name", FieldType.TEXT, False, FieldOnRegistrationPage.YES_REQUIRED),
]


def _build(status: RegistrationPageStatus) -> tuple[FakeUnitOfWork, str]:
    uow = FakeUnitOfWork()
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


def test_live_submission_sends_auto_reply_and_records_it() -> None:
    uow, slug = _build(RegistrationPageStatus.PUBLISHED)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )
    assert result.is_valid

    record = send_registration_auto_reply(
        uow, adapter, respondent=result.respondent, assembly_id=result.respondent.assembly_id
    )

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


def test_autoescapes_untrusted_respondent_name() -> None:
    uow, slug = _build(RegistrationPageStatus.PUBLISHED)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "<script>bad()</script>"},
    )

    send_registration_auto_reply(uow, adapter, respondent=result.respondent, assembly_id=result.respondent.assembly_id)

    html_body = adapter.send_email.call_args.kwargs["html_body"]
    assert "<script>bad()</script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_console_adapter_send_succeeds_end_to_end() -> None:
    uow, slug = _build(RegistrationPageStatus.PUBLISHED)

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )

    record = send_registration_auto_reply(
        uow, ConsoleEmailAdapter(), respondent=result.respondent, assembly_id=result.respondent.assembly_id
    )

    assert record is not None
    assert record.outcome is EmailSendOutcome.SENT


def test_test_submission_sends_auto_reply() -> None:
    uow, slug = _build(RegistrationPageStatus.TEST)
    adapter = MagicMock()
    adapter.send_email.return_value = True

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "consent": "yes", "first_name": "Ada"},
    )

    record = send_registration_auto_reply(
        uow, adapter, respondent=result.respondent, assembly_id=result.respondent.assembly_id
    )

    assert record is not None
    assert record.outcome is EmailSendOutcome.SENT
    adapter.send_email.assert_called_once()
