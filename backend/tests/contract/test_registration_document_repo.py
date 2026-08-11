"""ABOUTME: Contract tests for RegistrationDocumentRepository.
ABOUTME: Runs against both fake and SQL backends, plus SQL-only constraint/cascade checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from opendlp.adapters import orm
from opendlp.adapters.sql_repository import SqlAlchemyRegistrationDocumentRepository
from tests.contract.conftest import (
    ContractBackend,
    make_assembly,
    make_registration_document,
)


class TestAddAndGet:
    def test_add_and_get_preserves_bytes(self, registration_document_backend: ContractBackend):
        data = b"%PDF-1.7 binary payload \x00\x01\x02"
        doc = registration_document_backend.make_registration_document(data=data, byte_size=len(data), sha256="hash1")

        retrieved = registration_document_backend.repo.get(doc.id)
        assert retrieved is not None
        assert retrieved.id == doc.id
        assert retrieved.data == data
        assert retrieved.sha256 == "hash1"

    def test_add_and_get_preserves_label(self, registration_document_backend: ContractBackend):
        doc = registration_document_backend.make_registration_document(label="Information pack")

        retrieved = registration_document_backend.repo.get(doc.id)
        assert retrieved is not None
        assert retrieved.label == "Information pack"

    def test_add_and_get_preserves_original_filename(self, registration_document_backend: ContractBackend):
        doc = registration_document_backend.make_registration_document(original_filename="info pack.pdf")

        retrieved = registration_document_backend.repo.get(doc.id)
        assert retrieved is not None
        assert retrieved.original_filename == "info pack.pdf"

    def test_get_nonexistent_returns_none(self, registration_document_backend: ContractBackend):
        assert registration_document_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_documents(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        a = registration_document_backend.make_registration_document(assembly_id=assembly_id)
        b = registration_document_backend.make_registration_document(assembly_id=assembly_id)

        ids = {doc.id for doc in registration_document_backend.repo.all()}
        assert {a.id, b.id} <= ids


class TestGetByAssemblyAndSha:
    def test_finds_matching_document(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        doc = registration_document_backend.make_registration_document(assembly_id=assembly_id, sha256="abc")

        found = registration_document_backend.repo.get_by_assembly_and_sha(assembly_id, "abc")
        assert found is not None
        assert found.id == doc.id

    def test_returns_none_for_wrong_sha(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        registration_document_backend.make_registration_document(assembly_id=assembly_id, sha256="abc")

        assert registration_document_backend.repo.get_by_assembly_and_sha(assembly_id, "other") is None

    def test_returns_none_for_wrong_assembly(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        registration_document_backend.make_registration_document(assembly_id=assembly_id, sha256="abc")

        assert registration_document_backend.repo.get_by_assembly_and_sha(uuid.uuid4(), "abc") is None


class TestListAndCountByAssemblyId:
    def test_lists_only_that_assembly_oldest_first(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        other_assembly_id = registration_document_backend.make_assembly().id
        older = registration_document_backend.make_registration_document(
            assembly_id=assembly_id, created_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        newer = registration_document_backend.make_registration_document(
            assembly_id=assembly_id, created_at=datetime(2026, 2, 1, tzinfo=UTC)
        )
        registration_document_backend.make_registration_document(assembly_id=other_assembly_id)

        listed = registration_document_backend.repo.list_by_assembly_id(assembly_id)
        assert [doc.id for doc in listed] == [older.id, newer.id]

    def test_count_by_assembly_id(self, registration_document_backend: ContractBackend):
        assembly_id = registration_document_backend.make_assembly().id
        registration_document_backend.make_registration_document(assembly_id=assembly_id)
        registration_document_backend.make_registration_document(assembly_id=assembly_id)

        assert registration_document_backend.repo.count_by_assembly_id(assembly_id) == 2
        assert registration_document_backend.repo.count_by_assembly_id(uuid.uuid4()) == 0


class TestDelete:
    def test_delete_removes_document(self, registration_document_backend: ContractBackend):
        doc = registration_document_backend.make_registration_document()
        registration_document_backend.repo.delete(doc)
        registration_document_backend.commit()

        assert registration_document_backend.repo.get(doc.id) is None


def _persisted_assembly(session) -> uuid.UUID:
    assembly = make_assembly()
    session.add(assembly)
    session.flush()
    return assembly.id


class TestSqlConstraints:
    def test_duplicate_assembly_and_sha_violates_unique_index(self, postgres_session):
        assembly_id = _persisted_assembly(postgres_session)
        repo = SqlAlchemyRegistrationDocumentRepository(postgres_session)
        repo.add(make_registration_document(assembly_id, sha256="dup"))
        postgres_session.flush()
        repo.add(make_registration_document(assembly_id, sha256="dup"))

        with pytest.raises(IntegrityError):
            postgres_session.flush()

    def test_deleting_assembly_cascades_to_documents(self, postgres_session):
        assembly_id = _persisted_assembly(postgres_session)
        repo = SqlAlchemyRegistrationDocumentRepository(postgres_session)
        repo.add(make_registration_document(assembly_id))
        postgres_session.flush()
        assert repo.count_by_assembly_id(assembly_id) == 1

        postgres_session.execute(orm.assemblies.delete().where(orm.assemblies.c.id == assembly_id))
        postgres_session.expire_all()

        assert repo.count_by_assembly_id(assembly_id) == 0
