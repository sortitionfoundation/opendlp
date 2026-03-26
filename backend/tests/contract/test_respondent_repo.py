"""ABOUTME: Contract tests for RespondentRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import Any

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus, SelectionRunStatus, SelectionTaskType
from tests.contract.conftest import ContractBackend


def _make_respondent(
    backend: ContractBackend,
    assembly_id: uuid.UUID,
    external_id: str = "",
    status: RespondentStatus = RespondentStatus.POOL,
    eligible: bool | None = None,
    can_attend: bool | None = None,
    attributes: dict[str, Any] | None = None,
) -> Respondent:
    if not external_id:
        external_id = f"EXT-{uuid.uuid4().hex[:8]}"
    respondent = Respondent(
        assembly_id=assembly_id,
        external_id=external_id,
        selection_status=status,
        eligible=eligible,
        can_attend=can_attend,
        attributes=attributes,
    )
    backend.repo.add(respondent)
    backend.commit()
    return respondent


class TestAddAndGet:
    def test_add_and_get_by_id(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        resp = _make_respondent(respondent_backend, assembly.id, external_id="R001")

        retrieved = respondent_backend.repo.get(resp.id)
        assert retrieved is not None
        assert retrieved.id == resp.id
        assert retrieved.external_id == "R001"

    def test_get_nonexistent_returns_none(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_respondents(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        r1 = _make_respondent(respondent_backend, assembly.id, external_id="R001")
        r2 = _make_respondent(respondent_backend, assembly.id, external_id="R002")

        all_resp = list(respondent_backend.repo.all())
        ids = {r.id for r in all_resp}
        assert r1.id in ids
        assert r2.id in ids


class TestGetByExternalId:
    def test_finds_by_composite_key(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        resp = _make_respondent(respondent_backend, assembly.id, external_id="R001")

        retrieved = respondent_backend.repo.get_by_external_id(assembly.id, "R001")
        assert retrieved is not None
        assert retrieved.id == resp.id

    def test_returns_none_for_nonexistent(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.get_by_external_id(uuid.uuid4(), "NOPE") is None


class TestGetByAssemblyId:
    def test_returns_respondents_for_assembly(self, respondent_backend: ContractBackend):
        a1 = respondent_backend.make_assembly()
        a2 = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, a1.id, external_id="R001")
        _make_respondent(respondent_backend, a1.id, external_id="R002")
        _make_respondent(respondent_backend, a2.id, external_id="R003")

        results = respondent_backend.repo.get_by_assembly_id(a1.id)
        assert len(results) == 2

    def test_filters_by_status(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001", status=RespondentStatus.POOL)
        selected = _make_respondent(
            respondent_backend, assembly.id, external_id="R002", status=RespondentStatus.SELECTED
        )

        results = respondent_backend.repo.get_by_assembly_id(assembly.id, status=RespondentStatus.SELECTED)
        assert len(results) == 1
        assert results[0].id == selected.id

    def test_filters_eligible_only(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        # eligible=None (unknown) should be included
        _make_respondent(respondent_backend, assembly.id, external_id="R001", eligible=None, can_attend=None)
        # eligible=True should be included
        _make_respondent(respondent_backend, assembly.id, external_id="R002", eligible=True, can_attend=True)
        # eligible=False should be excluded
        _make_respondent(respondent_backend, assembly.id, external_id="R003", eligible=False)
        # can_attend=False should be excluded
        _make_respondent(respondent_backend, assembly.id, external_id="R004", can_attend=False)

        results = respondent_backend.repo.get_by_assembly_id(assembly.id, eligible_only=True)
        assert len(results) == 2


class TestCountByAssemblyId:
    def test_counts_respondents(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001")
        _make_respondent(respondent_backend, assembly.id, external_id="R002")

        assert respondent_backend.repo.count_by_assembly_id(assembly.id) == 2

    def test_returns_zero_for_no_respondents(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.count_by_assembly_id(uuid.uuid4()) == 0


class TestCountAvailableForSelection:
    def test_counts_available(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        # Available: POOL + eligible not False + can_attend not False
        _make_respondent(respondent_backend, assembly.id, external_id="R001")
        _make_respondent(respondent_backend, assembly.id, external_id="R002", eligible=True, can_attend=True)
        # Not available: SELECTED
        _make_respondent(respondent_backend, assembly.id, external_id="R003", status=RespondentStatus.SELECTED)
        # Not available: eligible=False
        _make_respondent(respondent_backend, assembly.id, external_id="R004", eligible=False)
        # Not available: can_attend=False
        _make_respondent(respondent_backend, assembly.id, external_id="R005", can_attend=False)

        assert respondent_backend.repo.count_available_for_selection(assembly.id) == 2


class TestDelete:
    def test_delete_removes_respondent(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        resp = _make_respondent(respondent_backend, assembly.id, external_id="R001")

        respondent_backend.repo.delete(resp)
        respondent_backend.commit()

        assert respondent_backend.repo.get(resp.id) is None


class TestBulkAdd:
    def test_adds_multiple_respondents(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        items = [Respondent(assembly_id=assembly.id, external_id=f"BULK-{i}") for i in range(3)]

        respondent_backend.repo.bulk_add(items)
        respondent_backend.commit()

        assert respondent_backend.repo.count_by_assembly_id(assembly.id) == 3


class TestBulkMarkAsSelected:
    def test_marks_matching_respondents_as_selected(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001")
        _make_respondent(respondent_backend, assembly.id, external_id="R002")
        _make_respondent(respondent_backend, assembly.id, external_id="R003")

        # Create a real SelectionRunRecord so the FK constraint is satisfied
        run_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.RUNNING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
        )
        respondent_backend.persist(run_record)
        respondent_backend.commit()

        respondent_backend.repo.bulk_mark_as_selected(assembly.id, ["R001", "R003"], run_record.task_id)
        respondent_backend.commit()

        r1 = respondent_backend.repo.get_by_external_id(assembly.id, "R001")
        r2 = respondent_backend.repo.get_by_external_id(assembly.id, "R002")
        r3 = respondent_backend.repo.get_by_external_id(assembly.id, "R003")
        assert r1 is not None and r1.selection_status == RespondentStatus.SELECTED
        assert r2 is not None and r2.selection_status == RespondentStatus.POOL
        assert r3 is not None and r3.selection_status == RespondentStatus.SELECTED


class TestResetAllToPool:
    def test_resets_all_respondents(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001", status=RespondentStatus.SELECTED)
        _make_respondent(respondent_backend, assembly.id, external_id="R002", status=RespondentStatus.CONFIRMED)

        count = respondent_backend.repo.reset_all_to_pool(assembly.id)
        respondent_backend.commit()

        assert count == 2
        results = respondent_backend.repo.get_by_assembly_id(assembly.id)
        assert all(r.selection_status == RespondentStatus.POOL for r in results)

    def test_returns_zero_when_no_respondents(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.reset_all_to_pool(uuid.uuid4()) == 0


class TestCountNonPool:
    def test_counts_non_pool(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001", status=RespondentStatus.POOL)
        _make_respondent(respondent_backend, assembly.id, external_id="R002", status=RespondentStatus.SELECTED)
        _make_respondent(respondent_backend, assembly.id, external_id="R003", status=RespondentStatus.CONFIRMED)

        assert respondent_backend.repo.count_non_pool(assembly.id) == 2

    def test_returns_zero_when_all_pool(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001")

        assert respondent_backend.repo.count_non_pool(assembly.id) == 0


class TestGetAttributeColumns:
    def test_returns_sorted_keys(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(
            respondent_backend,
            assembly.id,
            external_id="R001",
            attributes={"gender": "Female", "age": "30-40", "region": "North"},
        )

        columns = respondent_backend.repo.get_attribute_columns(assembly.id)
        assert columns == ["age", "gender", "region"]

    def test_returns_empty_for_no_respondents(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.get_attribute_columns(uuid.uuid4()) == []


class TestGetAttributeValueCounts:
    def test_returns_value_counts(self, respondent_backend: ContractBackend):
        assembly = respondent_backend.make_assembly()
        _make_respondent(respondent_backend, assembly.id, external_id="R001", attributes={"gender": "Female"})
        _make_respondent(respondent_backend, assembly.id, external_id="R002", attributes={"gender": "Male"})
        _make_respondent(respondent_backend, assembly.id, external_id="R003", attributes={"gender": "Female"})

        counts = respondent_backend.repo.get_attribute_value_counts(assembly.id, "gender")
        assert counts == {"Female": 2, "Male": 1}

    def test_returns_empty_for_no_respondents(self, respondent_backend: ContractBackend):
        assert respondent_backend.repo.get_attribute_value_counts(uuid.uuid4(), "gender") == {}
