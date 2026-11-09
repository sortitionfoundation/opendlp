"""ABOUTME: Contract tests for RegistrationContentBlockRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from opendlp.domain.registration_content_block import RegistrationContentBlock

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend


def _make_block(
    backend: ContractBackend, assembly_id: uuid.UUID, sort_order: int = 10, heading: str = "Heading"
) -> RegistrationContentBlock:
    block = RegistrationContentBlock(assembly_id=assembly_id, sort_order=sort_order, heading=heading)
    backend.repo.add(block)
    backend.commit()
    return block


class TestAddAndGet:
    def test_add_and_get_by_id(self, registration_content_block_backend: ContractBackend) -> None:
        assembly = registration_content_block_backend.make_assembly()
        block = RegistrationContentBlock(
            assembly_id=assembly.id, sort_order=30, heading="About you", body_html="<p>Tell us</p>"
        )
        registration_content_block_backend.repo.add(block)
        registration_content_block_backend.commit()

        retrieved = registration_content_block_backend.repo.get(block.id)

        assert retrieved is not None
        assert retrieved.heading == "About you"
        assert retrieved.body_html == "<p>Tell us</p>"
        assert retrieved.sort_order == 30
        assert retrieved.assembly_id == assembly.id

    def test_get_nonexistent_returns_none(self, registration_content_block_backend: ContractBackend) -> None:
        assert registration_content_block_backend.repo.get(uuid.uuid4()) is None


class TestListByAssembly:
    def test_returns_empty_for_no_blocks(self, registration_content_block_backend: ContractBackend) -> None:
        assert registration_content_block_backend.repo.list_by_assembly(uuid.uuid4()) == []

    def test_orders_by_sort_order(self, registration_content_block_backend: ContractBackend) -> None:
        assembly = registration_content_block_backend.make_assembly()
        later = _make_block(registration_content_block_backend, assembly.id, sort_order=40, heading="Later")
        earlier = _make_block(registration_content_block_backend, assembly.id, sort_order=10, heading="Earlier")

        blocks = registration_content_block_backend.repo.list_by_assembly(assembly.id)

        assert [b.id for b in blocks] == [earlier.id, later.id]

    def test_scopes_by_assembly(self, registration_content_block_backend: ContractBackend) -> None:
        mine = registration_content_block_backend.make_assembly()
        theirs = registration_content_block_backend.make_assembly()
        block = _make_block(registration_content_block_backend, mine.id)
        _make_block(registration_content_block_backend, theirs.id)

        blocks = registration_content_block_backend.repo.list_by_assembly(mine.id)

        assert [b.id for b in blocks] == [block.id]


class TestDelete:
    def test_delete_removes_the_block(self, registration_content_block_backend: ContractBackend) -> None:
        assembly = registration_content_block_backend.make_assembly()
        block = _make_block(registration_content_block_backend, assembly.id)

        registration_content_block_backend.repo.delete(block)
        registration_content_block_backend.commit()

        assert registration_content_block_backend.repo.get(block.id) is None
        assert registration_content_block_backend.repo.list_by_assembly(assembly.id) == []
