"""ABOUTME: Unit tests for the templated-email send service
ABOUTME: Covers generic send, send records and the registration auto-reply skip rules"""

import uuid
from unittest.mock import MagicMock

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_send_record import EmailSendOutcome
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer import email_send_service as service
from tests.fakes import FakeUnitOfWork


def _assembly(reply_to_name: str = "", reply_to_email: str = "") -> Assembly:
    return Assembly(title="My Assembly", question="?", reply_to_name=reply_to_name, reply_to_email=reply_to_email)


def _template(assembly_id: uuid.UUID, **kwargs: object) -> EmailTemplate:
    defaults: dict = {
        "name": "Auto-reply",
        "subject": "Thanks {{ respondent.first_name_or_friend }}",
        "body_html": "<p>Hi {{ respondent.first_name_or_friend }}</p>",
    }
    defaults.update(kwargs)
    return EmailTemplate(assembly_id=assembly_id, **defaults)


def _respondent(assembly_id: uuid.UUID, email: str = "person@example.com", **kwargs: object) -> Respondent:
    return Respondent(
        assembly_id=assembly_id, external_id="ext-1", email=email, attributes={"firstname": "Sam"}, **kwargs
    )


class TestSendTemplatedEmail:
    def test_sends_and_records_success(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly = _assembly(reply_to_name="The Team", reply_to_email="team@example.com")
        respondent = _respondent(assembly.id)
        template = _template(assembly.id)

        record = service.send_templated_email(uow, adapter, template=template, assembly=assembly, respondent=respondent)

        adapter.send_email.assert_called_once()
        kwargs = adapter.send_email.call_args.kwargs
        assert kwargs["to"] == [respondent.email]
        assert kwargs["subject"] == "Thanks Sam"
        assert kwargs["reply_to"] == ("The Team", "team@example.com")
        assert record.outcome is EmailSendOutcome.SENT
        assert uow.respondent_email_send_records.get(record.id) is not None

    def test_reply_to_is_bare_email_when_no_name(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly = _assembly(reply_to_email="team@example.com")
        respondent = _respondent(assembly.id)

        service.send_templated_email(
            uow, adapter, template=_template(assembly.id), assembly=assembly, respondent=respondent
        )

        assert adapter.send_email.call_args.kwargs["reply_to"] == "team@example.com"

    def test_reply_to_none_when_unset(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly = _assembly()
        respondent = _respondent(assembly.id)

        service.send_templated_email(
            uow, adapter, template=_template(assembly.id), assembly=assembly, respondent=respondent
        )

        assert adapter.send_email.call_args.kwargs["reply_to"] is None

    def test_records_failure_when_adapter_returns_false(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = False
        assembly = _assembly()
        respondent = _respondent(assembly.id)

        record = service.send_templated_email(
            uow, adapter, template=_template(assembly.id), assembly=assembly, respondent=respondent
        )

        assert record.outcome is EmailSendOutcome.FAILED

    def test_records_failure_when_adapter_raises(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.side_effect = RuntimeError("smtp down")
        assembly = _assembly()
        respondent = _respondent(assembly.id)

        record = service.send_templated_email(
            uow, adapter, template=_template(assembly.id), assembly=assembly, respondent=respondent
        )

        assert record.outcome is EmailSendOutcome.FAILED

    def test_records_missing_variables(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly = _assembly()
        respondent = _respondent(assembly.id)
        template = _template(assembly.id, body_html="<p>{{ missing_thing }}</p>")

        record = service.send_templated_email(uow, adapter, template=template, assembly=assembly, respondent=respondent)

        assert "missing_thing" in record.missing_variables


class TestSendRegistrationAutoReply:
    def _setup(self, uow: FakeUnitOfWork, *, with_template: bool = True, respondent: Respondent | None = None):
        assembly = _assembly(reply_to_email="team@example.com")
        uow.assemblies.add(assembly)
        template = _template(assembly.id)
        if with_template:
            uow.email_templates.add(template)
            page = RegistrationPage(assembly_id=assembly.id, auto_reply_email_template_id=template.id)
        else:
            page = RegistrationPage(assembly_id=assembly.id)
        uow.registration_pages.add(page)
        if respondent is None:
            respondent = _respondent(assembly.id)
        return assembly, respondent

    def test_sends_for_live_submission(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly, respondent = self._setup(uow)

        record = service.send_registration_auto_reply(uow, adapter, respondent=respondent, assembly_id=assembly.id)

        assert record is not None
        adapter.send_email.assert_called_once()
        assert uow.respondent_email_send_records.get(record.id) is not None

    def test_skips_when_no_template_configured(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        assembly, respondent = self._setup(uow, with_template=False)

        result = service.send_registration_auto_reply(uow, adapter, respondent=respondent, assembly_id=assembly.id)

        assert result is None
        adapter.send_email.assert_not_called()

    def test_skips_when_no_page(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        assembly = _assembly()
        uow.assemblies.add(assembly)
        respondent = _respondent(assembly.id)

        result = service.send_registration_auto_reply(uow, adapter, respondent=respondent, assembly_id=assembly.id)

        assert result is None
        adapter.send_email.assert_not_called()

    def test_skips_and_warns_when_respondent_has_no_email(self, capture_json_handler):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        assembly, _ = self._setup(uow)
        no_email = _respondent(assembly.id, email="")

        result = service.send_registration_auto_reply(uow, adapter, respondent=no_email, assembly_id=assembly.id)

        assert result is None
        adapter.send_email.assert_not_called()
        assert uow.respondent_email_send_records.list_by_respondent(no_email.id) == []
        assert "has no email" in capture_json_handler.getvalue()

    def test_no_email_without_template_is_silent(self, capture_json_handler):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        assembly, _ = self._setup(uow, with_template=False)
        no_email = _respondent(assembly.id, email="")

        result = service.send_registration_auto_reply(uow, adapter, respondent=no_email, assembly_id=assembly.id)

        assert result is None
        assert "has no email" not in capture_json_handler.getvalue()

    def test_sends_for_test_submission(self):
        uow = FakeUnitOfWork()
        adapter = MagicMock()
        adapter.send_email.return_value = True
        assembly, _ = self._setup(uow)
        test_respondent = _respondent(assembly.id, selection_status=RespondentStatus.TEST_SUBMISSION)

        result = service.send_registration_auto_reply(uow, adapter, respondent=test_respondent, assembly_id=assembly.id)

        assert result is not None
        assert result.outcome is EmailSendOutcome.SENT
        adapter.send_email.assert_called_once()
