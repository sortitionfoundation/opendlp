"""ABOUTME: Contract tests for RespondentFieldMappingEntryRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from opendlp.domain.respondent_field_schema import (
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
)

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend


def _make_derived_field(backend: ContractBackend) -> RespondentFieldDefinition:
    """Persist a field definition for entries to hang off (the SQL side needs the FK row)."""
    assembly = backend.make_assembly()
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=f"region_{uuid.uuid4().hex[:6]}",
        label="Region",
        group=RespondentFieldGroup.DERIVED,
        sort_order=10,
    )
    backend.persist(field)
    backend.commit()
    return field


def _add_entries(
    backend: ContractBackend, field_id: uuid.UUID, pairs: list[tuple[str, str]]
) -> list[RespondentFieldMappingEntry]:
    entries = [
        RespondentFieldMappingEntry(field_id=field_id, lookup_key=key, output_value=value) for key, value in pairs
    ]
    backend.repo.bulk_add(entries)
    backend.commit()
    return entries


class TestAddAndGet:
    def test_add_and_get_by_id(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        entry = RespondentFieldMappingEntry(field_id=field.id, lookup_key="SW1A1AA", output_value="London")
        backend.repo.add(entry)
        backend.commit()

        retrieved = backend.repo.get(entry.id)
        assert retrieved is not None
        assert retrieved.field_id == field.id
        assert retrieved.lookup_key == "SW1A1AA"
        assert retrieved.output_value == "London"

    def test_get_nonexistent_returns_none(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        assert respondent_field_mapping_entry_backend.repo.get(uuid.uuid4()) is None

    def test_bulk_add_and_count(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("AB1", "North"), ("AB2", "North"), ("CD1", "South")])

        assert backend.repo.count_for_field(field.id) == 3
        assert backend.repo.count_for_field(uuid.uuid4()) == 0


class TestGetMany:
    def test_returns_only_matching_keys_for_the_field(
        self, respondent_field_mapping_entry_backend: ContractBackend
    ) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        other_field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("AB1", "North"), ("AB2", "North"), ("CD1", "South")])
        _add_entries(backend, other_field.id, [("AB1", "Elsewhere")])

        found = backend.repo.get_many(field.id, ["AB1", "CD1", "MISSING"])

        assert {(e.lookup_key, e.output_value) for e in found} == {("AB1", "North"), ("CD1", "South")}

    def test_empty_key_list_returns_empty(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("AB1", "North")])

        assert backend.repo.get_many(field.id, []) == []


class TestListForField:
    def test_orders_by_lookup_key(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("CD1", "South"), ("AB1", "North"), ("BC1", "Mid")])

        entries = backend.repo.list_for_field(field.id)
        assert [e.lookup_key for e in entries] == ["AB1", "BC1", "CD1"]

    def test_limit_caps_the_result(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("CD1", "South"), ("AB1", "North"), ("BC1", "Mid")])

        entries = backend.repo.list_for_field(field.id, limit=2)
        assert [e.lookup_key for e in entries] == ["AB1", "BC1"]

    def test_unknown_field_returns_empty(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        assert respondent_field_mapping_entry_backend.repo.list_for_field(uuid.uuid4()) == []


class TestDeleteAllForField:
    def test_deletes_only_that_fields_entries(self, respondent_field_mapping_entry_backend: ContractBackend) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        other_field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("AB1", "North"), ("AB2", "North")])
        _add_entries(backend, other_field.id, [("AB1", "Elsewhere")])

        deleted = backend.repo.delete_all_for_field(field.id)
        backend.commit()

        assert deleted == 2
        assert backend.repo.count_for_field(field.id) == 0
        assert backend.repo.count_for_field(other_field.id) == 1

    def test_delete_then_bulk_add_replaces_the_table(
        self, respondent_field_mapping_entry_backend: ContractBackend
    ) -> None:
        backend = respondent_field_mapping_entry_backend
        field = _make_derived_field(backend)
        _add_entries(backend, field.id, [("AB1", "North")])

        backend.repo.delete_all_for_field(field.id)
        _add_entries(backend, field.id, [("AB1", "South"), ("AB2", "South")])

        entries = backend.repo.list_for_field(field.id)
        assert {(e.lookup_key, e.output_value) for e in entries} == {("AB1", "South"), ("AB2", "South")}
