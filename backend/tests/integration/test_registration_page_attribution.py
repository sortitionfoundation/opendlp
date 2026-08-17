"""ABOUTME: Integration tests for attributing a submission to the registration page it came through
ABOUTME: Covers respondent provenance and the auto-reply picking that page's own template"""

from typing import Any

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.assembly import Assembly
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


class _RecordingEmailAdapter(EmailAdapter):
    """Captures what would have been sent so a test can assert on it."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_email(
        self,
        to: list[str | tuple[str, str]],
        subject: str,
        text_body: str,
        html_body: str | None = None,
        from_email: str | tuple[str, str] | None = None,
        reply_to: str | tuple[str, str] | None = None,
    ) -> bool:
        self.sent.append({"to": to, "subject": subject, "html_body": html_body})
        return True


def _assembly_with_two_pages(uow: FakeUnitOfWork) -> tuple[Assembly, RegistrationPage, RegistrationPage]:
    assembly = Assembly(title="Climate Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)

    english = RegistrationPage(
        assembly_id=assembly.id,
        url_slug="climate-en",
        name="English",
        language="en",
        status=RegistrationPageStatus.PUBLISHED,
    )
    spanish = RegistrationPage(
        assembly_id=assembly.id,
        url_slug="climate-es",
        name="Espanol",
        language="es",
        status=RegistrationPageStatus.PUBLISHED,
    )
    uow.registration_pages.add(english)
    uow.registration_pages.add(spanish)

    for key, ftype, on_page in (
        ("email", FieldType.EMAIL, FieldOnRegistrationPage.YES_REQUIRED),
        ("first_name", FieldType.TEXT, FieldOnRegistrationPage.YES_OPTIONAL),
    ):
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key=key,
                label=key,
                group=RespondentFieldGroup.OTHER,
                sort_order=10,
                field_type=ftype,
                is_fixed=key == "email",
                on_registration_page=on_page,
            )
        )
    return assembly, english, spanish


class TestRespondentProvenance:
    def test_submissions_record_the_page_they_came_through(self, uow) -> None:
        """Without this the whole point of A/B testing - comparing variants - is unmeasurable."""
        _assembly, english, spanish = _assembly_with_two_pages(uow)

        first = submit_registration(uow, url_slug="climate-en", form_data={"email": "ada@example.com"})
        second = submit_registration(uow, url_slug="climate-es", form_data={"email": "grace@example.com"})

        assert first.respondent is not None
        assert second.respondent is not None
        assert first.respondent.registration_page_id == english.id
        assert second.respondent.registration_page_id == spanish.id

    def test_both_variants_feed_the_same_pool(self, uow) -> None:
        assembly, _english, _spanish = _assembly_with_two_pages(uow)

        submit_registration(uow, url_slug="climate-en", form_data={"email": "ada@example.com"})
        submit_registration(uow, url_slug="climate-es", form_data={"email": "grace@example.com"})

        respondents = uow.respondents.get_by_assembly_id(assembly.id)
        assert len(respondents) == 2
        assert {r.assembly_id for r in respondents} == {assembly.id}


class TestAutoReplyFollowsTheSubmittingPage:
    def test_reply_uses_the_submitting_pages_template_not_a_siblings(self, uow) -> None:
        """A Spanish registrant must not receive the English page's auto-reply."""
        assembly, english, spanish = _assembly_with_two_pages(uow)

        english_template = EmailTemplate(
            assembly_id=assembly.id, name="EN reply", subject="Thanks", body_html="<p>Thank you</p>"
        )
        spanish_template = EmailTemplate(
            assembly_id=assembly.id, name="ES reply", subject="Gracias", body_html="<p>Gracias</p>"
        )
        uow.email_templates.add(english_template)
        uow.email_templates.add(spanish_template)
        english.set_auto_reply_template(english_template.id)
        spanish.set_auto_reply_template(spanish_template.id)

        result = submit_registration(uow, url_slug="climate-es", form_data={"email": "grace@example.com"})
        assert result.respondent is not None

        adapter = _RecordingEmailAdapter()
        send_registration_auto_reply(uow, adapter, respondent=result.respondent)

        assert len(adapter.sent) == 1
        assert adapter.sent[0]["subject"] == "Gracias"

    def test_no_reply_when_the_submitting_page_has_no_template(self, uow) -> None:
        assembly, english, _spanish = _assembly_with_two_pages(uow)
        template = EmailTemplate(
            assembly_id=assembly.id, name="EN reply", subject="Thanks", body_html="<p>Thank you</p>"
        )
        uow.email_templates.add(template)
        english.set_auto_reply_template(template.id)

        result = submit_registration(uow, url_slug="climate-es", form_data={"email": "grace@example.com"})
        assert result.respondent is not None

        adapter = _RecordingEmailAdapter()
        record = send_registration_auto_reply(uow, adapter, respondent=result.respondent)

        assert record is None
        assert adapter.sent == []

    def test_no_reply_for_a_respondent_with_no_page(self, uow) -> None:
        """CSV and manual respondents never came through a registration page."""
        assembly, english, _spanish = _assembly_with_two_pages(uow)
        template = EmailTemplate(
            assembly_id=assembly.id, name="EN reply", subject="Thanks", body_html="<p>Thank you</p>"
        )
        uow.email_templates.add(template)
        english.set_auto_reply_template(template.id)

        result = submit_registration(uow, url_slug="climate-en", form_data={"email": "ada@example.com"})
        assert result.respondent is not None
        result.respondent.registration_page_id = None

        adapter = _RecordingEmailAdapter()
        record = send_registration_auto_reply(uow, adapter, respondent=result.respondent)

        assert record is None
        assert adapter.sent == []
