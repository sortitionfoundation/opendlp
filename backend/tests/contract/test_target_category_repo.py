"""ABOUTME: Contract tests for TargetCategoryRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from opendlp.domain.targets import TargetCategory
from tests.contract.conftest import ContractBackend


def _make_category(
    backend: ContractBackend,
    assembly_id: uuid.UUID,
    name: str = "",
    sort_order: int = 0,
) -> TargetCategory:
    if not name:
        name = f"Category {uuid.uuid4().hex[:6]}"
    cat = TargetCategory(assembly_id=assembly_id, name=name, sort_order=sort_order)
    backend.repo.add(cat)
    backend.commit()
    return cat


class TestAddAndGet:
    def test_add_and_get_by_id(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        cat = _make_category(target_category_backend, assembly.id, name="Gender")

        retrieved = target_category_backend.repo.get(cat.id)
        assert retrieved is not None
        assert retrieved.id == cat.id
        assert retrieved.name == "Gender"

    def test_get_nonexistent_returns_none(self, target_category_backend: ContractBackend):
        assert target_category_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_categories(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        c1 = _make_category(target_category_backend, assembly.id, name="Gender")
        c2 = _make_category(target_category_backend, assembly.id, name="Age")

        all_cats = list(target_category_backend.repo.all())
        ids = {c.id for c in all_cats}
        assert c1.id in ids
        assert c2.id in ids


class TestGetByAssemblyId:
    def test_returns_categories_for_assembly(self, target_category_backend: ContractBackend):
        a1 = target_category_backend.make_assembly()
        a2 = target_category_backend.make_assembly()
        _make_category(target_category_backend, a1.id, name="Gender")
        _make_category(target_category_backend, a1.id, name="Age")
        _make_category(target_category_backend, a2.id, name="Region")

        cats = target_category_backend.repo.get_by_assembly_id(a1.id)
        assert len(cats) == 2
        assert all(c.assembly_id == a1.id for c in cats)

    def test_returns_empty_for_no_categories(self, target_category_backend: ContractBackend):
        assert target_category_backend.repo.get_by_assembly_id(uuid.uuid4()) == []

    def test_ordered_by_sort_order(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        _make_category(target_category_backend, assembly.id, name="Second", sort_order=2)
        _make_category(target_category_backend, assembly.id, name="First", sort_order=1)

        cats = target_category_backend.repo.get_by_assembly_id(assembly.id)
        assert cats[0].name == "First"
        assert cats[1].name == "Second"


class TestCountByAssemblyId:
    def test_counts_categories(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        _make_category(target_category_backend, assembly.id, name="Gender")
        _make_category(target_category_backend, assembly.id, name="Age")

        assert target_category_backend.repo.count_by_assembly_id(assembly.id) == 2

    def test_returns_zero_for_no_categories(self, target_category_backend: ContractBackend):
        assert target_category_backend.repo.count_by_assembly_id(uuid.uuid4()) == 0


class TestDelete:
    def test_delete_removes_category(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        cat = _make_category(target_category_backend, assembly.id, name="Gender")

        target_category_backend.repo.delete(cat)
        target_category_backend.commit()

        assert target_category_backend.repo.get(cat.id) is None

    def test_delete_leaves_other_categories(self, target_category_backend: ContractBackend):
        assembly = target_category_backend.make_assembly()
        c1 = _make_category(target_category_backend, assembly.id, name="Gender")
        c2 = _make_category(target_category_backend, assembly.id, name="Age")

        target_category_backend.repo.delete(c1)
        target_category_backend.commit()

        assert target_category_backend.repo.get(c1.id) is None
        assert target_category_backend.repo.get(c2.id) is not None


class TestDeleteAllForAssembly:
    def test_deletes_all_for_assembly(self, target_category_backend: ContractBackend):
        a1 = target_category_backend.make_assembly()
        a2 = target_category_backend.make_assembly()
        _make_category(target_category_backend, a1.id, name="Gender")
        _make_category(target_category_backend, a1.id, name="Age")
        _make_category(target_category_backend, a2.id, name="Region")

        count = target_category_backend.repo.delete_all_for_assembly(a1.id)
        target_category_backend.commit()

        assert count == 2
        assert target_category_backend.repo.get_by_assembly_id(a1.id) == []
        # a2's categories should be untouched
        assert len(target_category_backend.repo.get_by_assembly_id(a2.id)) == 1

    def test_returns_zero_when_none_to_delete(self, target_category_backend: ContractBackend):
        assert target_category_backend.repo.delete_all_for_assembly(uuid.uuid4()) == 0
