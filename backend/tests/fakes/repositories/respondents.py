"""ABOUTME: In-memory repositories for respondents, their field definitions and field mappings
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid
from typing import Any

from opendlp.domain.respondent_field_schema import (
    RespondentFieldDefinition,
    RespondentFieldMappingEntry,
    field_list_order,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import (
    COUNTED_RESPONDENT_STATUSES,
    SELECTED_RESPONDENT_STATUSES,
    RespondentAction,
    RespondentStatus,
)
from opendlp.service_layer.repositories import (
    RespondentFieldDefinitionRepository,
    RespondentFieldMappingEntryRepository,
    RespondentRepository,
)
from tests.fakes.repositories.base import FakeRepository


def _as_text(value: Any) -> str | None:
    """A respondent attribute as the SQL repository would return it.

    ``attributes`` is a JSON column typed ``dict[str, Any]``, and every query
    that groups by one reads it with ``.as_string()`` - Postgres ``->>``, which
    renders whatever is there as text. So the fake has to render it the same way
    or it keys a non-string value differently from the real repository and misses
    matches the real one makes. JSON null is absent rather than the string
    "null", matching ``->>``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class FakeRespondentRepository(FakeRepository, RespondentRepository):
    """Fake in-memory RespondentRepository."""

    def get_by_assembly_id(
        self,
        assembly_id: uuid.UUID,
        status: RespondentStatus | None = None,
        eligible_only: bool = False,
        include_deleted: bool = False,
    ) -> list[Respondent]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if status:
            results = [r for r in results if r.selection_status == status]
        elif not include_deleted:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        if eligible_only:
            results = [r for r in results if r.eligible is not False and r.can_attend is not False]
        return results

    def count_by_registration_page(self, assembly_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Count respondents per registration page for an assembly."""
        counts: dict[uuid.UUID, int] = {}
        for item in self._items:
            if item.assembly_id != assembly_id or item.registration_page_id is None:
                continue
            counts[item.registration_page_id] = counts.get(item.registration_page_id, 0) + 1
        return counts

    def count_by_registration_page_and_status(
        self, assembly_id: uuid.UUID
    ) -> dict[uuid.UUID | None, dict[RespondentStatus, int]]:
        counts: dict[uuid.UUID | None, dict[RespondentStatus, int]] = {}
        for item in self._items:
            if item.assembly_id != assembly_id:
                continue
            page_counts = counts.setdefault(item.registration_page_id, {})
            page_counts[item.selection_status] = page_counts.get(item.selection_status, 0) + 1
        return counts

    def get_by_assembly_id_statuses(
        self,
        assembly_id: uuid.UUID,
        statuses: list[RespondentStatus] | None = None,
    ) -> list[Respondent]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if statuses is None:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        else:
            results = [r for r in results if r.selection_status in statuses]
        return sorted(results, key=lambda r: r.created_at)

    def get_by_assembly_id_paginated(
        self,
        assembly_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
        status: RespondentStatus | None = None,
        eligible_only: bool = False,
        include_deleted: bool = False,
    ) -> tuple[list[Respondent], int]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if status:
            results = [r for r in results if r.selection_status == status]
        elif not include_deleted:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        if eligible_only:
            results = [r for r in results if r.eligible is not False and r.can_attend is not False]
        total_count = len(results)
        offset = (page - 1) * per_page
        paginated = results[offset : offset + per_page]
        return paginated, total_count

    def get_by_external_id(self, assembly_id: uuid.UUID, external_id: str) -> Respondent | None:
        for r in self._items:
            if r.assembly_id == assembly_id and r.external_id == external_id:
                return r
        return None

    def get_by_external_ids(self, assembly_id: uuid.UUID, external_ids: list[str]) -> list[Respondent]:
        wanted = set(external_ids)
        found = [r for r in self._items if r.assembly_id == assembly_id and r.external_id in wanted]
        return sorted(found, key=lambda r: r.external_id)

    def count_by_assembly_id(self, assembly_id: uuid.UUID, include_deleted: bool = False) -> int:
        return sum(
            1
            for r in self._items
            if r.assembly_id == assembly_id and (include_deleted or r.selection_status != RespondentStatus.DELETED)
        )

    def count_available_for_selection(self, assembly_id: uuid.UUID) -> int:
        return sum(
            1
            for r in self._items
            if r.assembly_id == assembly_id
            and r.selection_status == RespondentStatus.POOL
            and r.eligible is not False
            and r.can_attend is not False
        )

    def delete(self, item: Respondent) -> None:
        self._items = [r for r in self._items if r.id != item.id]

    def bulk_add(self, items: list[Respondent]) -> None:
        self._items.extend(items)

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [r for r in self._items if r.assembly_id != assembly_id]
        return before - len(self._items)

    def bulk_mark_as_selected(
        self,
        assembly_id: uuid.UUID,
        external_ids: list[str],
        selection_run_id: uuid.UUID,
        author_id: uuid.UUID,
    ) -> None:
        for r in self._items:
            if r.assembly_id == assembly_id and r.external_id in external_ids:
                r.mark_as_selected(selection_run_id)
                r.add_comment(
                    text="Selected in run",
                    author_id=author_id,
                    action=RespondentAction.SELECT,
                    selection_run_id=selection_run_id,
                )

    def _with_attribute(self, assembly_id: uuid.UUID, key: str) -> list[Respondent]:
        return [
            r
            for r in self._items
            if r.assembly_id == assembly_id and r.selection_status != RespondentStatus.DELETED and key in r.attributes
        ]

    def remove_attribute(self, assembly_id: uuid.UUID, key: str) -> int:
        changed = self._with_attribute(assembly_id, key)
        for r in changed:
            r.attributes = {k: v for k, v in r.attributes.items() if k != key}
        return len(changed)

    def rename_attribute(self, assembly_id: uuid.UUID, old_key: str, new_key: str) -> int:
        changed = self._with_attribute(assembly_id, old_key)
        for r in changed:
            r.attributes = {(new_key if k == old_key else k): v for k, v in r.attributes.items() if k != new_key}
        return len(changed)

    def reset_all_to_pool(self, assembly_id: uuid.UUID, author_id: uuid.UUID, selection_run_id: uuid.UUID) -> int:
        count = 0
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status not in (
                RespondentStatus.POOL,
                RespondentStatus.DELETED,
            ):
                r.reset_to_pool(author_id, selection_run_id)
                count += 1
        return count

    def count_by_status(self, assembly_id: uuid.UUID) -> dict[RespondentStatus, int]:
        counts: dict[RespondentStatus, int] = {}
        for r in self._items:
            if r.assembly_id == assembly_id:
                counts[r.selection_status] = counts.get(r.selection_status, 0) + 1
        return counts

    def get_attribute_columns(self, assembly_id: uuid.UUID) -> list[str]:
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status != RespondentStatus.DELETED and r.attributes:
                return sorted(r.attributes.keys())
        return []

    def get_attribute_value_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
        return self._value_counts(assembly_id, attribute_name, COUNTED_RESPONDENT_STATUSES)

    def get_selected_attribute_value_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
        return self._value_counts(assembly_id, attribute_name, SELECTED_RESPONDENT_STATUSES)

    def get_attribute_value_counts_by_status(
        self,
        assembly_id: uuid.UUID,
        attribute_name: str,
    ) -> dict[str, dict[RespondentStatus, int]]:
        counts: dict[str, dict[RespondentStatus, int]] = {}
        for r in self._items:
            if r.assembly_id != assembly_id or r.selection_status == RespondentStatus.DELETED:
                continue
            val = _as_text(r.attributes.get(attribute_name) if r.attributes else None)
            if val is None:
                continue
            by_status = counts.setdefault(val, {})
            by_status[r.selection_status] = by_status.get(r.selection_status, 0) + 1
        return counts

    def get_attribute_value_available_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._items:
            if r.assembly_id != assembly_id or r.selection_status != RespondentStatus.POOL:
                continue
            if r.eligible is False or r.can_attend is False:
                continue
            val = _as_text(r.attributes.get(attribute_name) if r.attributes else None)
            if val is not None:
                counts[val] = counts.get(val, 0) + 1
        return counts

    def get_attribute_distinct_counts(self, assembly_id: uuid.UUID, attribute_names: list[str]) -> dict[str, int]:
        return {
            name: len(self._value_counts(assembly_id, name, COUNTED_RESPONDENT_STATUSES)) for name in attribute_names
        }

    def _value_counts(
        self,
        assembly_id: uuid.UUID,
        attribute_name: str,
        statuses: list[RespondentStatus],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status in statuses and r.attributes:
                val = _as_text(r.attributes.get(attribute_name))
                if val is not None:
                    counts[val] = counts.get(val, 0) + 1
        return counts


class FakeRespondentFieldDefinitionRepository(FakeRepository, RespondentFieldDefinitionRepository):
    """Fake in-memory RespondentFieldDefinitionRepository."""

    def bulk_add(self, items: list[RespondentFieldDefinition]) -> None:
        self._items.extend(items)

    def get_by_assembly_and_key(self, assembly_id: uuid.UUID, field_key: str) -> RespondentFieldDefinition | None:
        for f in self._items:
            if f.assembly_id == assembly_id and f.field_key == field_key:
                return f
        return None

    def list_by_assembly(self, assembly_id: uuid.UUID) -> list[RespondentFieldDefinition]:
        fields = [f for f in self._items if f.assembly_id == assembly_id]
        return sorted(fields, key=field_list_order)

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        return sum(1 for f in self._items if f.assembly_id == assembly_id)

    def delete(self, item: RespondentFieldDefinition) -> None:
        self._items = [f for f in self._items if f.id != item.id]

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [f for f in self._items if f.assembly_id != assembly_id]
        return before - len(self._items)


class FakeRespondentFieldMappingEntryRepository(FakeRepository, RespondentFieldMappingEntryRepository):
    """Fake in-memory RespondentFieldMappingEntryRepository."""

    def bulk_add(self, items: list[RespondentFieldMappingEntry]) -> None:
        self._items.extend(items)

    def get_many(self, field_id: uuid.UUID, lookup_keys: list[str]) -> list[RespondentFieldMappingEntry]:
        wanted = set(lookup_keys)
        return [e for e in self._items if e.field_id == field_id and e.lookup_key in wanted]

    def list_for_field(self, field_id: uuid.UUID, limit: int | None = None) -> list[RespondentFieldMappingEntry]:
        entries = sorted(
            (e for e in self._items if e.field_id == field_id),
            key=lambda e: e.lookup_key,
        )
        return entries[:limit] if limit is not None else entries

    def count_for_field(self, field_id: uuid.UUID) -> int:
        return sum(1 for e in self._items if e.field_id == field_id)

    def delete_all_for_field(self, field_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [e for e in self._items if e.field_id != field_id]
        return before - len(self._items)
