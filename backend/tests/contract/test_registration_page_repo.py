"""ABOUTME: Contract tests for RegistrationPageRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageAction,
    RegistrationPageActivity,
    RegistrationPageStatus,
)

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend


def _add_page(backend: ContractBackend, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> RegistrationPage:
    if assembly_id is None:
        assembly_id = backend.make_assembly().id
    page = RegistrationPage(assembly_id=assembly_id, **kwargs)
    backend.repo.add(page)
    backend.commit()
    return page


class TestAddAndGet:
    def test_add_and_get_by_id(self, registration_page_backend: ContractBackend):
        page = _add_page(registration_page_backend, url_slug="my-page")

        retrieved = registration_page_backend.repo.get(page.id)
        assert retrieved is not None
        assert retrieved.id == page.id
        assert retrieved.url_slug == "my-page"

    def test_get_nonexistent_returns_none(self, registration_page_backend: ContractBackend):
        assert registration_page_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_pages(self, registration_page_backend: ContractBackend):
        p1 = _add_page(registration_page_backend)
        p2 = _add_page(registration_page_backend)

        ids = {p.id for p in registration_page_backend.repo.all()}
        assert p1.id in ids
        assert p2.id in ids

    def test_status_and_activity_round_trip(self, registration_page_backend: ContractBackend):
        author_id = uuid.uuid4()
        page = _add_page(
            registration_page_backend,
            url_slug="round-trip",
            status=RegistrationPageStatus.PUBLISHED,
            activity=[
                RegistrationPageActivity(
                    text="initial publish",
                    author_id=author_id,
                    created_at=datetime.now(UTC),
                    action=RegistrationPageAction.PUBLISH,
                ),
            ],
        )

        retrieved = registration_page_backend.repo.get(page.id)
        assert retrieved is not None
        assert retrieved.status is RegistrationPageStatus.PUBLISHED
        assert len(retrieved.activity) == 1
        entry = retrieved.activity[0]
        assert entry.action is RegistrationPageAction.PUBLISH
        assert entry.author_id == author_id
        assert entry.text == "initial publish"


class TestListByAssemblyId:
    def test_finds_the_only_page(self, registration_page_backend: ContractBackend):
        assembly = registration_page_backend.make_assembly()
        page = _add_page(registration_page_backend, assembly_id=assembly.id)

        pages = registration_page_backend.repo.list_by_assembly_id(assembly.id)
        assert [p.id for p in pages] == [page.id]

    def test_returns_empty_when_assembly_has_no_pages(self, registration_page_backend: ContractBackend):
        assert registration_page_backend.repo.list_by_assembly_id(uuid.uuid4()) == []

    def test_returns_every_page_of_the_assembly_in_created_order(self, registration_page_backend: ContractBackend):
        """An assembly may have many registration pages - A/B variants and translations."""
        assembly = registration_page_backend.make_assembly()
        now = datetime.now(UTC)
        first = _add_page(
            registration_page_backend,
            assembly_id=assembly.id,
            name="English",
            created_at=now - timedelta(hours=2),
        )
        second = _add_page(
            registration_page_backend,
            assembly_id=assembly.id,
            name="Español",
            created_at=now - timedelta(hours=1),
        )
        third = _add_page(
            registration_page_backend,
            assembly_id=assembly.id,
            name="Cymraeg",
            created_at=now,
        )

        pages = registration_page_backend.repo.list_by_assembly_id(assembly.id)
        assert [p.id for p in pages] == [first.id, second.id, third.id]

    def test_excludes_pages_of_other_assemblies(self, registration_page_backend: ContractBackend):
        assembly = registration_page_backend.make_assembly()
        other = registration_page_backend.make_assembly()
        mine = _add_page(registration_page_backend, assembly_id=assembly.id, name="Mine")
        _add_page(registration_page_backend, assembly_id=other.id, name="Theirs")

        pages = registration_page_backend.repo.list_by_assembly_id(assembly.id)
        assert [p.id for p in pages] == [mine.id]

    def test_many_pages_may_be_published_at_once(self, registration_page_backend: ContractBackend):
        """Every language variant of an assembly is live simultaneously."""
        assembly = registration_page_backend.make_assembly()
        for index in range(3):
            _add_page(
                registration_page_backend,
                assembly_id=assembly.id,
                name=f"Variant {index}",
                url_slug=f"variant-{index}",
                status=RegistrationPageStatus.PUBLISHED,
            )

        pages = registration_page_backend.repo.list_by_assembly_id(assembly.id)
        assert len(pages) == 3
        assert all(p.status is RegistrationPageStatus.PUBLISHED for p in pages)


class TestNameAndLanguage:
    def test_name_and_language_round_trip(self, registration_page_backend: ContractBackend):
        """Read back past the identity map so this proves storage, not object identity."""
        page = _add_page(registration_page_backend, name="Español", language="es")

        retrieved = registration_page_backend.fresh_get_registration_page(page.id)
        assert retrieved is not None
        assert retrieved.name == "Español"
        assert retrieved.language == "es"

    def test_name_and_language_default_to_empty(self, registration_page_backend: ContractBackend):
        page = _add_page(registration_page_backend)

        retrieved = registration_page_backend.fresh_get_registration_page(page.id)
        assert retrieved is not None
        assert retrieved.name == ""
        assert retrieved.language == ""


class TestGetByUrlSlug:
    def test_finds_by_url_slug(self, registration_page_backend: ContractBackend):
        page = _add_page(registration_page_backend, url_slug="find-me")

        retrieved = registration_page_backend.repo.get_by_url_slug("find-me")
        assert retrieved is not None
        assert retrieved.id == page.id

    def test_returns_none_for_unknown_slug(self, registration_page_backend: ContractBackend):
        _add_page(registration_page_backend, url_slug="find-me")
        assert registration_page_backend.repo.get_by_url_slug("not-here") is None

    def test_returns_none_for_empty_input(self, registration_page_backend: ContractBackend):
        # A page with an unset url_slug must not be matched by an empty lookup.
        _add_page(registration_page_backend)
        assert registration_page_backend.repo.get_by_url_slug("") is None


class TestGetByShortUrlSlug:
    def test_finds_by_short_url_slug(self, registration_page_backend: ContractBackend):
        page = _add_page(registration_page_backend, short_url_slug="fm")

        retrieved = registration_page_backend.repo.get_by_short_url_slug("fm")
        assert retrieved is not None
        assert retrieved.id == page.id

    def test_returns_none_for_unknown_slug(self, registration_page_backend: ContractBackend):
        _add_page(registration_page_backend, short_url_slug="fm")
        assert registration_page_backend.repo.get_by_short_url_slug("nh") is None

    def test_returns_none_for_empty_input(self, registration_page_backend: ContractBackend):
        _add_page(registration_page_backend)
        assert registration_page_backend.repo.get_by_short_url_slug("") is None


class TestDelete:
    def test_delete_removes_page(self, registration_page_backend: ContractBackend):
        page = _add_page(registration_page_backend)

        registration_page_backend.repo.delete(page)
        registration_page_backend.commit()

        assert registration_page_backend.repo.get(page.id) is None
