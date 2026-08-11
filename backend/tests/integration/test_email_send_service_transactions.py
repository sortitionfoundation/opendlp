"""ABOUTME: Integration tests for the transaction boundary of the templated-email send service
ABOUTME: The send record must belong to the caller's transaction, not commit itself behind the caller's back"""

import uuid
from unittest.mock import MagicMock

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.respondents import Respondent
from opendlp.service_layer.email_send_service import send_templated_email
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


def _sending_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.send_email.return_value = True
    return adapter


@pytest.fixture
def sendable_ids(postgres_session_factory):
    """Commit an assembly, template and respondent, and return their ids.

    Ids rather than the objects: the objects detach when this UnitOfWork exits.
    """
    assembly = Assembly(title="Climate Assembly", question="?", reply_to_email="team@example.com")
    template = EmailTemplate(assembly_id=assembly.id, name="Reply", subject="Thanks", body_html="<p>Thanks</p>")
    respondent = Respondent(assembly_id=assembly.id, external_id=f"ext-{uuid.uuid4()}", email="ada@example.com")

    ids = (assembly.id, template.id, respondent.id)
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.assemblies.add(assembly)
        uow.email_templates.add(template)
        uow.respondents.add(respondent)
        uow.commit()

    return ids


def _send(uow, ids):
    assembly_id, template_id, respondent_id = ids
    send_templated_email(
        uow,
        _sending_adapter(),
        template=uow.email_templates.get(template_id),
        assembly=uow.assemblies.get(assembly_id),
        respondent=uow.respondents.get(respondent_id),
    )


class TestSendRecordTransactionBoundary:
    def test_the_record_lands_when_the_caller_commits(self, postgres_session_factory, sendable_ids):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            _send(uow, sendable_ids)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert len(uow.respondent_email_send_records.list_by_respondent(sendable_ids[2])) == 1

    def test_the_record_rolls_back_with_the_caller(self, postgres_session_factory, sendable_ids):
        """A service function that commits its own work would leave this record behind."""
        with pytest.raises(ValueError), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:  # noqa: PT012
            _send(uow, sendable_ids)
            raise ValueError("the caller failed after the send")

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondent_email_send_records.list_by_respondent(sendable_ids[2]) == []
