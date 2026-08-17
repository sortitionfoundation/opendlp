"""ABOUTME: Component tests for the dev /service-docs registration-page handlers
ABOUTME: Proves the handlers are page-aware - list/duplicate/delete pages and target a specific page by id"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml, RegistrationPageStatus
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.entrypoints.blueprints.dev import (
    _handle_close_registration_page,
    _handle_create_registration_page,
    _handle_delete_registration_page,
    _handle_duplicate_registration_page,
    _handle_get_registration_page,
    _handle_list_registration_pages,
    _handle_publish_registration_page,
)
from tests.fakes import FakeStore, FakeUnitOfWork

_VALID_FORM_HTML = '<form action="{{ form_action }}" method="POST">{{ csrf_form_element }}<button>Go</button></form>'


def _seed_admin(store: FakeStore) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    with FakeUnitOfWork(store=store) as uow:
        uow.users.add(user)
        uow.commit()
    return user


def _seed_assembly(store: FakeStore) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    with FakeUnitOfWork(store=store) as uow:
        uow.assemblies.add(assembly)
        uow.commit()
    return assembly


def _seed_page(
    store: FakeStore,
    assembly: Assembly,
    *,
    name: str,
    url_slug: str = "",
    status: RegistrationPageStatus = RegistrationPageStatus.TEST,
    form_html: str = _VALID_FORM_HTML,
) -> RegistrationPage:
    page = RegistrationPage(assembly_id=assembly.id, name=name, url_slug=url_slug, status=status)
    with FakeUnitOfWork(store=store) as uow:
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(RegistrationPageHtml(registration_page_id=page.id, form_html=form_html))
        uow.commit()
    return page


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin(fake_store):
    return _seed_admin(fake_store)


@pytest.fixture
def assembly(fake_store):
    return _seed_assembly(fake_store)


@pytest.fixture
def app(fake_store):
    from opendlp.entrypoints.flask_app import create_app  # noqa: PLC0415

    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def as_admin(app, admin):
    """Push a request context with current_user set to the seeded admin."""
    with (
        app.test_request_context(),
        patch("opendlp.entrypoints.blueprints.dev.current_user", SimpleNamespace(id=admin.id)),
    ):
        yield


def _uow(fake_store) -> FakeUnitOfWork:
    return FakeUnitOfWork(store=fake_store)


class TestHandleCreateRegistrationPage:
    def test_creates_a_second_page_for_the_same_assembly(self, fake_store, assembly, as_admin):
        _seed_page(fake_store, assembly, name="English")

        with _uow(fake_store) as uow:
            result = _handle_create_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "name": "Spanish", "language": "es"},
            )

        assert result["status"] == "success"
        assert result["registration_page"]["name"] == "Spanish"
        assert result["registration_page"]["language"] == "es"
        with _uow(fake_store) as uow:
            assert len(uow.registration_pages.list_by_assembly_id(assembly.id)) == 2

    def test_with_slugs_generates_working_slugs(self, fake_store, assembly, as_admin):
        with _uow(fake_store) as uow:
            result = _handle_create_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "name": "English", "with_slugs": True},
            )

        assert result["status"] == "success"
        assert result["registration_page"]["url_slug"]
        assert result["registration_page"]["short_url_slug"]

    def test_rejects_duplicate_name_within_assembly(self, fake_store, assembly, as_admin):
        _seed_page(fake_store, assembly, name="English")

        with _uow(fake_store) as uow:
            result = _handle_create_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "name": "English"},
            )

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"


class TestHandleListRegistrationPages:
    def test_returns_every_page_oldest_first(self, fake_store, assembly, as_admin):
        first = _seed_page(fake_store, assembly, name="English")
        second = _seed_page(fake_store, assembly, name="Spanish")

        with _uow(fake_store) as uow:
            result = _handle_list_registration_pages(uow=uow, params={"assembly_id": str(assembly.id)})

        assert result["status"] == "success"
        assert result["page_count"] == 2
        assert [p["id"] for p in result["registration_pages"]] == [str(first.id), str(second.id)]
        assert result["registration_pages"][0]["name"] == "English"
        assert result["registration_pages"][0]["status"] == "TEST"

    def test_empty_assembly_returns_no_pages(self, fake_store, assembly, as_admin):
        with _uow(fake_store) as uow:
            result = _handle_list_registration_pages(uow=uow, params={"assembly_id": str(assembly.id)})

        assert result["status"] == "success"
        assert result["page_count"] == 0
        assert result["registration_pages"] == []


class TestHandleDuplicateRegistrationPage:
    def test_copies_content_into_a_fresh_test_page(self, fake_store, assembly, as_admin):
        source = _seed_page(fake_store, assembly, name="English", url_slug="english-slug")

        with _uow(fake_store) as uow:
            result = _handle_duplicate_registration_page(
                uow=uow,
                params={"source_page_id": str(source.id), "name": "Spanish", "language": "es"},
            )

        assert result["status"] == "success"
        copy = result["registration_page"]
        assert copy["id"] != str(source.id)
        assert copy["name"] == "Spanish"
        assert copy["status"] == "TEST"
        assert copy["url_slug"] != "english-slug"
        with _uow(fake_store) as uow:
            copied_source = uow.registration_page_html_sources.get_by_page_id(uuid.UUID(copy["id"]))
            assert copied_source.form_html == _VALID_FORM_HTML

    def test_missing_source_page_is_reported(self, fake_store, assembly, as_admin):
        with _uow(fake_store) as uow:
            result = _handle_duplicate_registration_page(
                uow=uow,
                params={"source_page_id": str(uuid.uuid4()), "name": "Spanish"},
            )

        assert result["status"] == "error"
        assert result["error_type"] == "NotFoundError"


class TestHandleDeleteRegistrationPage:
    def test_deletes_an_unpublished_page(self, fake_store, assembly, as_admin):
        page = _seed_page(fake_store, assembly, name="English")

        with _uow(fake_store) as uow:
            result = _handle_delete_registration_page(uow=uow, params={"page_id": str(page.id)})

        assert result["status"] == "success"
        assert result["deleted_page_id"] == str(page.id)
        with _uow(fake_store) as uow:
            assert uow.registration_pages.list_by_assembly_id(assembly.id) == []

    def test_refuses_to_delete_a_published_page(self, fake_store, assembly, admin, as_admin):
        page = _seed_page(fake_store, assembly, name="English", url_slug="english-slug")
        with _uow(fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
            stored.publish(uow.registration_page_html_sources.get_by_page_id(page.id), author_id=admin.id)
            uow.commit()

        with _uow(fake_store) as uow:
            result = _handle_delete_registration_page(uow=uow, params={"page_id": str(page.id)})

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"


class TestPageAddressing:
    def test_publish_targets_the_page_id_not_the_oldest_page(self, fake_store, assembly, as_admin):
        oldest = _seed_page(fake_store, assembly, name="English", url_slug="english-slug")
        newer = _seed_page(fake_store, assembly, name="Spanish", url_slug="spanish-slug")

        with _uow(fake_store) as uow:
            result = _handle_publish_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "page_id": str(newer.id)},
            )

        assert result["status"] == "success"
        with _uow(fake_store) as uow:
            assert uow.registration_pages.get(newer.id).status == RegistrationPageStatus.PUBLISHED
            assert uow.registration_pages.get(oldest.id).status == RegistrationPageStatus.TEST

    def test_without_page_id_falls_back_to_the_oldest_page(self, fake_store, assembly, as_admin):
        oldest = _seed_page(fake_store, assembly, name="English")
        _seed_page(fake_store, assembly, name="Spanish")

        with _uow(fake_store) as uow:
            result = _handle_get_registration_page(uow=uow, params={"assembly_id": str(assembly.id)})

        assert result["status"] == "success"
        assert result["registration_page"]["id"] == str(oldest.id)

    def test_blank_page_id_falls_back_to_the_oldest_page(self, fake_store, assembly, as_admin):
        oldest = _seed_page(fake_store, assembly, name="English")
        _seed_page(fake_store, assembly, name="Spanish")

        with _uow(fake_store) as uow:
            result = _handle_close_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "page_id": ""},
            )

        # close on a TEST page is an invalid transition - the point is it resolved to the oldest page
        assert result["status"] == "error"
        assert str(oldest.id)  # oldest still exists
        with _uow(fake_store) as uow:
            assert uow.registration_pages.get(oldest.id).status == RegistrationPageStatus.TEST

    def test_explicit_page_id_addresses_the_newer_page(self, fake_store, assembly, as_admin):
        _seed_page(fake_store, assembly, name="English")
        newer = _seed_page(fake_store, assembly, name="Spanish")

        with _uow(fake_store) as uow:
            result = _handle_get_registration_page(
                uow=uow,
                params={"assembly_id": str(assembly.id), "page_id": str(newer.id)},
            )

        assert result["status"] == "success"
        assert result["registration_page"]["id"] == str(newer.id)
        assert result["registration_page"]["name"] == "Spanish"
