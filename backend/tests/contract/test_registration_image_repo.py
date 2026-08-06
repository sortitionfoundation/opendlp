"""ABOUTME: Contract tests for RegistrationImageRepository.
ABOUTME: Runs against both fake and SQL backends, plus SQL-only constraint/cascade checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from opendlp.adapters import orm
from opendlp.adapters.sql_repository import SqlAlchemyRegistrationImageRepository
from tests.contract.conftest import (
    ContractBackend,
    make_assembly,
    make_registration_image,
)


class TestAddAndGet:
    def test_add_and_get_preserves_bytes(self, registration_image_backend: ContractBackend):
        data = b"\x89PNG\r\n\x1a\n binary payload \x00\x01\x02"
        image = registration_image_backend.make_registration_image(data=data, byte_size=len(data), sha256="hash1")

        retrieved = registration_image_backend.repo.get(image.id)
        assert retrieved is not None
        assert retrieved.id == image.id
        assert retrieved.data == data
        assert retrieved.sha256 == "hash1"

    def test_add_and_get_preserves_alt(self, registration_image_backend: ContractBackend):
        image = registration_image_backend.make_registration_image(alt="A red square")

        retrieved = registration_image_backend.repo.get(image.id)
        assert retrieved is not None
        assert retrieved.alt == "A red square"

    def test_add_and_get_preserves_original_filename(self, registration_image_backend: ContractBackend):
        image = registration_image_backend.make_registration_image(original_filename="holiday photo.png")

        retrieved = registration_image_backend.repo.get(image.id)
        assert retrieved is not None
        assert retrieved.original_filename == "holiday photo.png"

    def test_get_nonexistent_returns_none(self, registration_image_backend: ContractBackend):
        assert registration_image_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_images(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        a = registration_image_backend.make_registration_image(assembly_id=assembly_id)
        b = registration_image_backend.make_registration_image(assembly_id=assembly_id)

        ids = {image.id for image in registration_image_backend.repo.all()}
        assert {a.id, b.id} <= ids


class TestGetByAssemblyAndSha:
    def test_finds_matching_image(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        image = registration_image_backend.make_registration_image(assembly_id=assembly_id, sha256="abc")

        found = registration_image_backend.repo.get_by_assembly_and_sha(assembly_id, "abc")
        assert found is not None
        assert found.id == image.id

    def test_returns_none_for_wrong_sha(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        registration_image_backend.make_registration_image(assembly_id=assembly_id, sha256="abc")

        assert registration_image_backend.repo.get_by_assembly_and_sha(assembly_id, "other") is None

    def test_returns_none_for_wrong_assembly(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        registration_image_backend.make_registration_image(assembly_id=assembly_id, sha256="abc")

        assert registration_image_backend.repo.get_by_assembly_and_sha(uuid.uuid4(), "abc") is None


class TestListAndCountByAssemblyId:
    def test_lists_only_that_assembly_oldest_first(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        other_assembly_id = registration_image_backend.make_assembly().id
        older = registration_image_backend.make_registration_image(
            assembly_id=assembly_id, created_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        newer = registration_image_backend.make_registration_image(
            assembly_id=assembly_id, created_at=datetime(2026, 2, 1, tzinfo=UTC)
        )
        registration_image_backend.make_registration_image(assembly_id=other_assembly_id)

        listed = registration_image_backend.repo.list_by_assembly_id(assembly_id)
        assert [image.id for image in listed] == [older.id, newer.id]

    def test_count_by_assembly_id(self, registration_image_backend: ContractBackend):
        assembly_id = registration_image_backend.make_assembly().id
        registration_image_backend.make_registration_image(assembly_id=assembly_id)
        registration_image_backend.make_registration_image(assembly_id=assembly_id)

        assert registration_image_backend.repo.count_by_assembly_id(assembly_id) == 2
        assert registration_image_backend.repo.count_by_assembly_id(uuid.uuid4()) == 0


class TestDelete:
    def test_delete_removes_image(self, registration_image_backend: ContractBackend):
        image = registration_image_backend.make_registration_image()
        registration_image_backend.repo.delete(image)
        registration_image_backend.commit()

        assert registration_image_backend.repo.get(image.id) is None


def _persisted_assembly(session) -> uuid.UUID:
    assembly = make_assembly()
    session.add(assembly)
    session.flush()
    return assembly.id


class TestSqlConstraints:
    def test_duplicate_assembly_and_sha_violates_unique_index(self, postgres_session):
        assembly_id = _persisted_assembly(postgres_session)
        repo = SqlAlchemyRegistrationImageRepository(postgres_session)
        repo.add(make_registration_image(assembly_id, sha256="dup"))
        postgres_session.flush()
        repo.add(make_registration_image(assembly_id, sha256="dup"))

        with pytest.raises(IntegrityError):
            postgres_session.flush()

    def test_deleting_assembly_cascades_to_images(self, postgres_session):
        assembly_id = _persisted_assembly(postgres_session)
        repo = SqlAlchemyRegistrationImageRepository(postgres_session)
        repo.add(make_registration_image(assembly_id))
        postgres_session.flush()
        assert repo.count_by_assembly_id(assembly_id) == 1

        postgres_session.execute(orm.assemblies.delete().where(orm.assemblies.c.id == assembly_id))
        postgres_session.expire_all()

        assert repo.count_by_assembly_id(assembly_id) == 0
