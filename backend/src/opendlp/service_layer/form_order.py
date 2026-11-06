"""ABOUTME: Shared helpers for the one ordered list of registration questions and content blocks.
ABOUTME: Where a new item goes, and recording that the questions changed; kept apart to avoid import cycles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opendlp.domain.registration_content_block import FormItem, form_items
from opendlp.service_layer.constants import SORT_ORDER_STEP

if TYPE_CHECKING:
    import uuid

    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


def current_form_items(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> list[FormItem]:
    """The assembly's questions and blocks in list order, attached to the open ``uow``."""
    fields = list(uow.respondent_field_definitions.list_by_assembly(assembly_id))
    blocks = list(uow.registration_content_blocks.list_by_assembly(assembly_id))
    return form_items(fields, blocks)


def next_form_sort_order(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> int:
    """The sort order that puts a new question or block at the end of the list."""
    return max((item.sort_order for item in current_form_items(uow, assembly_id)), default=0) + SORT_ORDER_STEP


def renumber(items: list[FormItem]) -> None:
    """Give the items, in this order, sort orders 10, 20, 30..."""
    for position, item in enumerate(items, start=1):
        item.sort_order = position * SORT_ORDER_STEP


def record_questions_changed(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> None:
    """Note that the questions or the blocks among them changed, for the "form is behind" warning.

    Called by every write to them, deletes included - a deleted row leaves
    nothing behind to compare against, which is why this lives on the assembly.
    """
    assembly = uow.assemblies.get(assembly_id)
    if assembly is not None:
        assembly.mark_questions_changed()
