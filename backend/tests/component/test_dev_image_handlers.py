"""ABOUTME: Component tests for the dev /service-docs image-service handlers
ABOUTME: Drives the six _handle_* functions through real services over a FakeUnitOfWork, asserting on real outcomes"""

import base64
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.entrypoints.blueprints.dev import (
    _handle_add_registration_image,
    _handle_delete_registration_image,
    _handle_get_registration_image_for_serving,
    _handle_list_image_snippets,
    _handle_list_registration_images,
    _handle_set_registration_image_alt,
    _serialise_image,
)
from opendlp.service_layer.image_processing import process_image
from tests.fakes import FakeStore, FakeUnitOfWork

_MAX_BYTES = 10 * 1024 * 1024
_MAX_EDGE = 2048


def _png(color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_admin(store: FakeStore) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    with FakeUnitOfWork(store=store) as uow:
        uow.users.add(user)
        uow.commit()
    return user


def _seed_page(store: FakeStore, *, url_slug: str = "my-slug") -> RegistrationPage:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    page = RegistrationPage(assembly_id=assembly.id, url_slug=url_slug, status=RegistrationPageStatus.PUBLISHED)
    with FakeUnitOfWork(store=store) as uow:
        uow.assemblies.add(assembly)
        uow.registration_pages.add(page)
        uow.commit()
    return page


def _seed_image(store: FakeStore, page: RegistrationPage, color=(255, 0, 0)) -> RegistrationImage:
    processed = process_image(_png(color), max_bytes=_MAX_BYTES, max_edge_px=_MAX_EDGE)
    image = RegistrationImage.from_processed(page.id, processed)
    with FakeUnitOfWork(store=store) as uow:
        uow.registration_images.add(image)
        uow.commit()
    return image


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin(fake_store):
    return _seed_admin(fake_store)


@pytest.fixture
def page(fake_store):
    return _seed_page(fake_store)


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


class TestSerialiseImage:
    def test_emits_expected_fields(self):
        image = RegistrationImage(
            registration_page_id=uuid.uuid4(),
            byte_size=321,
            width=200,
            height=150,
            sha256="e" * 64,
            data=b"\x89PNG-bytes",
            alt="Hello",
            original_filename="logo.png",
            created_by=uuid.uuid4(),
        )
        result = _serialise_image(image)
        assert result["id"] == str(image.id)
        assert result["alt"] == "Hello"
        assert result["sha256"] == "e" * 64
        assert result["file_name"] == f"{'e' * 64}.png"
        assert result["original_filename"] == "logo.png"
        assert result["width"] == 200
        assert result["height"] == 150
        assert result["byte_size"] == 321


class TestHandleAddRegistrationImage:
    def test_decodes_base64_and_stores_image(self, fake_store, page, as_admin):
        b64 = base64.b64encode(_png()).decode()
        result = _handle_add_registration_image(
            uow=_uow(fake_store),
            params={
                "assembly_id": str(page.assembly_id),
                "image_base64": b64,
                "alt": "Decoded",
                "original_filename": "logo.png",
            },
        )

        assert result["status"] == "success"
        assert result["image"]["alt"] == "Decoded"
        assert result["image"]["original_filename"] == "logo.png"
        with _uow(fake_store) as uow:
            stored = uow.registration_images.list_by_page_id(page.id)
        assert len(stored) == 1
        assert stored[0].alt == "Decoded"

    def test_strips_data_url_prefix(self, fake_store, page, as_admin):
        b64 = base64.b64encode(_png()).decode()
        result = _handle_add_registration_image(
            uow=_uow(fake_store),
            params={
                "assembly_id": str(page.assembly_id),
                "image_base64": f"data:image/png;base64,{b64}",
                "alt": "Alt",
            },
        )

        assert result["status"] == "success"
        with _uow(fake_store) as uow:
            assert len(uow.registration_images.list_by_page_id(page.id)) == 1

    def test_invalid_base64_returns_error(self, fake_store, page, as_admin):
        result = _handle_add_registration_image(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "image_base64": "not!base64!", "alt": "x"},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestHandleListRegistrationImages:
    def test_returns_serialised_list(self, fake_store, page, as_admin):
        _seed_image(fake_store, page, color=(255, 0, 0))
        _seed_image(fake_store, page, color=(0, 255, 0))

        result = _handle_list_registration_images(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id)},
        )

        assert result["status"] == "success"
        assert result["total_count"] == 2
        assert len(result["images"]) == 2


class TestHandleDeleteRegistrationImage:
    def test_deletes_and_returns_id(self, fake_store, page, as_admin):
        image = _seed_image(fake_store, page)

        result = _handle_delete_registration_image(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "image_id": str(image.id)},
        )

        assert result == {"status": "success", "deleted_image_id": str(image.id)}
        with _uow(fake_store) as uow:
            assert uow.registration_images.list_by_page_id(page.id) == []


class TestHandleSetRegistrationImageAlt:
    def test_updates_alt_and_returns_serialised_image(self, fake_store, page, as_admin):
        image = _seed_image(fake_store, page)

        result = _handle_set_registration_image_alt(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "image_id": str(image.id), "alt": "Renamed"},
        )

        assert result["status"] == "success"
        assert result["image"]["alt"] == "Renamed"
        with _uow(fake_store) as uow:
            assert uow.registration_images.get(image.id).alt == "Renamed"


class TestHandleListImageSnippets:
    def test_pairs_image_with_html_snippet(self, fake_store, page, as_admin):
        _seed_image(fake_store, page, color=(0, 0, 255))

        result = _handle_list_image_snippets(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id)},
        )

        assert result["status"] == "success"
        assert result["total_count"] == 1
        assert page.url_slug in result["snippets"][0]["html"]


class TestHandleGetRegistrationImageForServing:
    def test_found_returns_serialised_image(self, fake_store, page, as_admin):
        image = _seed_image(fake_store, page)

        result = _handle_get_registration_image_for_serving(
            uow=_uow(fake_store),
            params={"url_slug": page.url_slug, "image_name": f"{image.sha256}.png"},
        )

        assert result["status"] == "success"
        assert result["found"] is True
        assert result["image"]["id"] == str(image.id)

    def test_not_found_returns_none(self, fake_store, page, as_admin):
        result = _handle_get_registration_image_for_serving(
            uow=_uow(fake_store),
            params={"url_slug": "bad-slug", "image_name": "x.png"},
        )

        assert result == {"status": "success", "found": False, "image": None}
