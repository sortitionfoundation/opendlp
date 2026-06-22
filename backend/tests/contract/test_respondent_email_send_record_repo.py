"""ABOUTME: Contract tests for RespondentEmailSendRecordRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from opendlp.domain.email_send_record import EmailSendOutcome
from tests.contract.conftest import ContractBackend, make_respondent_email_send_record


class TestAddAndGet:
    def test_add_and_get_round_trips_fields(self, respondent_email_send_record_backend: ContractBackend):
        backend = respondent_email_send_record_backend
        respondent = backend.make_respondent()
        record = make_respondent_email_send_record(
            respondent.id,
            from_email="team@example.com",
            outcome=EmailSendOutcome.FAILED,
            missing_variables=["first_name", "info_url"],
        )
        backend.repo.add(record)
        backend.commit()

        retrieved = backend.repo.get(record.id)
        assert retrieved is not None
        assert retrieved.respondent_id == respondent.id
        assert retrieved.outcome is EmailSendOutcome.FAILED
        assert retrieved.missing_variables == ["first_name", "info_url"]

    def test_get_nonexistent_returns_none(self, respondent_email_send_record_backend: ContractBackend):
        assert respondent_email_send_record_backend.repo.get(uuid.uuid4()) is None


class TestListByRespondent:
    def test_lists_only_matching_respondent(self, respondent_email_send_record_backend: ContractBackend):
        backend = respondent_email_send_record_backend
        respondent = backend.make_respondent()
        other = backend.make_respondent()
        mine = make_respondent_email_send_record(respondent.id)
        theirs = make_respondent_email_send_record(other.id)
        backend.repo.add(mine)
        backend.repo.add(theirs)
        backend.commit()

        results = backend.repo.list_by_respondent(respondent.id)
        ids = {r.id for r in results}
        assert mine.id in ids
        assert theirs.id not in ids
