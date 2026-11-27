"""ABOUTME: In-memory repositories for assemblies, their Google Sheets configs, selection runs and targets
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid
from collections.abc import Collection, Iterable
from datetime import datetime
from typing import Any

from opendlp.domain.assembly import Assembly, AssemblyGSheet, RunSummary, SelectionRunRecord
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.targets import TargetCategory
from opendlp.domain.value_objects import (
    AssemblyStatus,
    GSheetExportKind,
    SelectionTaskType,
)
from opendlp.service_layer.repositories import (
    AssemblyExportGSheetRepository,
    AssemblyGSheetRepository,
    AssemblyRepository,
    SelectionRunRecordRepository,
    TargetCategoryRepository,
)
from tests.fakes.repositories.base import FakeRepository
from tests.fakes.repositories.users import FakeUserRepository


class FakeAssemblyRepository(FakeRepository, AssemblyRepository):
    """Fake implementation of AssemblyRepository."""

    def __init__(self, users: FakeUserRepository) -> None:
        super().__init__()
        # Required, not optional: assembly roles hang off the User in the fake,
        # so get_assemblies_for_user cannot be answered without it. Defaulting it
        # to None would let a caller receive a confidently empty list instead of
        # an error.
        self._users = users

    def _newest_first(self, assemblies: Iterable[Assembly]) -> list[Assembly]:
        """Order as the SQL repository does, so a test cannot pass here and fail there."""
        return sorted(assemblies, key=lambda assembly: assembly.created_at, reverse=True)

    def get_active_assemblies(self) -> Iterable[Assembly]:
        """Get all assemblies that are currently active, newest first."""
        return self._newest_first(assembly for assembly in self._items if assembly.is_active())

    def get_assemblies_for_user(
        self, user_id: uuid.UUID, status: AssemblyStatus = AssemblyStatus.ACTIVE
    ) -> Iterable[Assembly]:
        """Get the assemblies with this status the user holds a role on, newest first.

        A role lookup, like the SQL repository: it asks nothing about the user's
        global role. A user id with no roles has no assemblies.
        """
        user = self._users.get(user_id)
        assembly_ids = {role.assembly_id for role in user.assembly_roles} if user else set()
        return [assembly for assembly in self.get_assemblies_by_status(status) if assembly.id in assembly_ids]

    def get_assemblies_by_status(self, status: AssemblyStatus) -> Iterable[Assembly]:
        """Get assemblies by their status, newest first."""
        return self._newest_first(assembly for assembly in self._items if assembly.status == status)

    def list_filtered(
        self, member_user_id: uuid.UUID | None = None, include_archived: bool = False
    ) -> Iterable[Assembly]:
        assemblies = [a for a in self._items if include_archived or a.is_active()]
        if member_user_id is not None:
            user = self._users.get(member_user_id)
            assembly_ids = {role.assembly_id for role in user.assembly_roles} if user else set()
            assemblies = [a for a in assemblies if a.id in assembly_ids]
        return self._newest_first(assemblies)

    def search_by_title(self, search_term: str) -> Iterable[Assembly]:
        """Search the active assemblies by title (case-insensitive partial match), newest first."""
        search_term = search_term.lower()
        return [assembly for assembly in self.get_active_assemblies() if search_term in assembly.title.lower()]


class FakeAssemblyGSheetRepository(FakeRepository, AssemblyGSheetRepository):
    """Fake implementation of AssemblyGSheetRepository."""

    def get(self, item_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its ID."""
        for item in self._items:
            if item.assembly_gsheet_id == item_id:
                return item
        return None

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its assembly ID."""
        for item in self._items:
            if item.assembly_id == assembly_id:
                return item
        return None

    def delete(self, item: AssemblyGSheet) -> None:
        """Delete an AssemblyGSheet from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeAssemblyExportGSheetRepository(FakeRepository, AssemblyExportGSheetRepository):
    """Fake implementation of AssemblyExportGSheetRepository."""

    def get(self, item_id: uuid.UUID) -> AssemblyExportGSheet | None:
        """Get an AssemblyExportGSheet by its ID."""
        for item in self._items:
            if item.assembly_export_gsheet_id == item_id:
                return item
        return None

    def get_by_assembly_and_kind(
        self,
        assembly_id: uuid.UUID,
        export_kind: GSheetExportKind,
    ) -> AssemblyExportGSheet | None:
        """Get the saved export sheet for one assembly and export kind."""
        for item in self._items:
            if item.assembly_id == assembly_id and item.export_kind == export_kind:
                return item
        return None

    def delete(self, item: AssemblyExportGSheet) -> None:
        """Delete an AssemblyExportGSheet from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeSelectionRunRecordRepository(FakeRepository, SelectionRunRecordRepository):
    """Fake implementation of SelectionRunRecordRepository."""

    def get(self, item_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its ID."""
        # SelectionRunRecord doesn't have an id field, only task_id
        return self.get_by_task_id(item_id)

    def get_by_task_id(self, task_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its task ID."""
        for item in self._items:
            if item.task_id == task_id:
                return item
        return None

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> Iterable[SelectionRunRecord]:
        """Get all SelectionRunRecords for a specific assembly."""
        return [item for item in self._items if item.assembly_id == assembly_id]

    def get_latest_for_assembly(
        self,
        assembly_id: uuid.UUID,
        task_type: SelectionTaskType | None = None,
    ) -> SelectionRunRecord | None:
        """Get the most recent SelectionRunRecord for an assembly, optionally filtered by task_type."""
        assembly_records = list(self.get_by_assembly_id(assembly_id))
        if task_type is not None:
            assembly_records = [r for r in assembly_records if r.task_type == task_type]
        if not assembly_records:
            return None
        return max(assembly_records, key=lambda r: r.created_at or datetime.min)

    def get_recent_for_assembly(
        self,
        assembly_id: uuid.UUID,
        task_type: SelectionTaskType = SelectionTaskType.SELECT_GSHEET,
        limit: int = 3,
    ) -> list[SelectionRunRecord]:
        """Get up to ``limit`` most recent records of a task type for an assembly, newest first."""
        matching = [r for r in self._items if r.assembly_id == assembly_id and r.task_type == task_type]
        matching.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
        return matching[:limit]

    def prune_by_status(self, assembly_id: uuid.UUID, keep_successful: int = 500, keep_failed: int = 40) -> int:
        """Prune records for an assembly, keeping the newest ``keep_successful`` completed and
        ``keep_failed`` failed/cancelled runs. In-flight (pending/running) records are always
        kept. Returns count deleted."""

        def newest(predicate: Any, limit: int) -> list[SelectionRunRecord]:
            if limit <= 0:
                return []
            matching = sorted(
                [r for r in self._items if r.assembly_id == assembly_id and predicate(r)],
                key=lambda r: r.created_at or datetime.min,
                reverse=True,
            )
            return matching[:limit]

        keep_ids = {r.task_id for r in newest(lambda r: r.is_completed, keep_successful)}
        keep_ids.update(r.task_id for r in newest(lambda r: r.is_failed or r.is_cancelled, keep_failed))
        keep_ids.update(
            r.task_id for r in self._items if r.assembly_id == assembly_id and (r.is_pending or r.is_running)
        )

        before = len(self._items)
        self._items = [r for r in self._items if r.assembly_id != assembly_id or r.task_id in keep_ids]
        return before - len(self._items)

    def get_running_tasks(self) -> Iterable[SelectionRunRecord]:
        """Get all currently running selection tasks."""
        return [item for item in self._items if item.is_running]

    def get_all_unfinished(self) -> list[SelectionRunRecord]:
        """Get all SelectionRunRecords that are PENDING or RUNNING."""
        return [item for item in self._items if item.is_pending or item.is_running]

    def get_unfinished_for_assembly(
        self, assembly_id: uuid.UUID, task_types: Collection[SelectionTaskType] | None = None
    ) -> list[SelectionRunRecord]:
        """Get the PENDING or RUNNING records for an assembly, oldest first."""
        matching = [
            r
            for r in self._items
            if r.assembly_id == assembly_id
            and (r.is_pending or r.is_running)
            and (task_types is None or r.task_type in task_types)
        ]
        matching.sort(key=lambda r: r.created_at or datetime.min)
        return matching

    def get_by_assembly_id_paginated(
        self, assembly_id: uuid.UUID, page: int = 1, per_page: int = 50, since: datetime | None = None
    ) -> tuple[list[tuple[SelectionRunRecord, None]], int]:
        """Get paginated SelectionRunRecords for an assembly with user information.

        Note: Fake implementation returns None for user in each tuple.
        """
        # Get all records for the assembly
        all_records = sorted(
            [
                item
                for item in self._items
                if item.assembly_id == assembly_id
                and (since is None or (item.created_at is not None and item.created_at >= since))
            ],
            key=lambda r: r.created_at or datetime.min,
            reverse=True,  # Newest first
        )

        total_count = len(all_records)

        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_records = all_records[start_idx:end_idx]

        # Return tuples of (record, None) to match the real repository signature
        return [(record, None) for record in page_records], total_count

    def get_history_summaries(self, assembly_id: uuid.UUID) -> list[RunSummary]:
        """Get a summary of every SelectionRunRecord for an assembly, oldest first."""
        records = sorted(
            [item for item in self._items if item.assembly_id == assembly_id],
            key=lambda r: r.created_at or datetime.min,
        )
        return [
            RunSummary(task_id=r.task_id, task_type=r.task_type, status=r.status, created_at=r.created_at)
            for r in records
            if r.created_at is not None
        ]


class FakeTargetCategoryRepository(FakeRepository, TargetCategoryRepository):
    """Fake in-memory TargetCategoryRepository."""

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> list[TargetCategory]:
        return sorted(
            [c for c in self._items if c.assembly_id == assembly_id],
            key=lambda c: c.sort_order,
        )

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        return sum(1 for c in self._items if c.assembly_id == assembly_id)

    def delete(self, item: TargetCategory) -> None:
        self._items = [c for c in self._items if c.id != item.id]

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [c for c in self._items if c.assembly_id != assembly_id]
        return before - len(self._items)
