"""ABOUTME: Unit tests for the dev /service-docs image-service handlers
ABOUTME: Covers _serialise_image and the six _handle_* functions for the Images tab"""

import base64
import uuid
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.registration_image import RegistrationImage
from opendlp.entrypoints.blueprints.dev import (
    _handle_add_registration_image,
    _handle_delete_registration_image,
    _handle_get_registration_image_for_serving,
    _handle_list_image_snippets,
    _handle_list_registration_images,
    _handle_set_registration_image_alt,
    _serialise_image,
)
from opendlp.entrypoints.flask_app import create_app


@pytest.fixture
def app():
    return create_app("testing")


@pytest.fixture
def assembly_id() -> uuid.UUID:
    return uuid.uuid4()


def _image(*, alt: str = "Logo", sha256: str = "a" * 64, original_filename: str = "") -> RegistrationImage:
    return RegistrationImage(
        registration_page_id=uuid.uuid4(),
        byte_size=321,
        width=200,
        height=150,
        sha256=sha256,
        data=b"\x89PNG-bytes",
        alt=alt,
        original_filename=original_filename,
        created_by=uuid.uuid4(),
    )


class TestSerialiseImage:
    def test_emits_expected_fields(self):
        image = _image(alt="Hello", sha256="e" * 64, original_filename="logo.png")
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
    def test_decodes_base64_and_returns_serialised_image(self, app, assembly_id):
        stored = _image(alt="Decoded")
        raw_bytes = b"\x89PNG\r\n\x1a\nfake"
        b64 = base64.b64encode(raw_bytes).decode()
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch(
                "opendlp.entrypoints.blueprints.dev.add_registration_image",
                return_value=stored,
            ) as add,
        ):
            cu.id = uuid.uuid4()
            result = _handle_add_registration_image(
                uow=MagicMock(),
                params={
                    "assembly_id": str(assembly_id),
                    "image_base64": b64,
                    "alt": "Decoded",
                    "original_filename": "logo.png",
                },
            )

        assert result["status"] == "success"
        assert result["image"]["alt"] == "Decoded"
        _, kwargs = add.call_args
        assert kwargs["raw"] == raw_bytes
        assert kwargs["alt"] == "Decoded"
        assert kwargs["original_filename"] == "logo.png"

    def test_strips_data_url_prefix(self, app, assembly_id):
        stored = _image()
        raw_bytes = b"\x89PNG-data-url"
        b64 = base64.b64encode(raw_bytes).decode()
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch(
                "opendlp.entrypoints.blueprints.dev.add_registration_image",
                return_value=stored,
            ) as add,
        ):
            cu.id = uuid.uuid4()
            _handle_add_registration_image(
                uow=MagicMock(),
                params={
                    "assembly_id": str(assembly_id),
                    "image_base64": f"data:image/png;base64,{b64}",
                    "alt": "Alt",
                },
            )

        _, kwargs = add.call_args
        assert kwargs["raw"] == raw_bytes


class TestHandleListRegistrationImages:
    def test_returns_serialised_list(self, app, assembly_id):
        images = [_image(alt="A", sha256="1" * 64), _image(alt="B", sha256="2" * 64)]
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch(
                "opendlp.entrypoints.blueprints.dev.list_registration_images",
                return_value=images,
            ) as list_fn,
        ):
            cu.id = uuid.uuid4()
            result = _handle_list_registration_images(
                uow=MagicMock(),
                params={"assembly_id": str(assembly_id)},
            )

        assert result["status"] == "success"
        assert result["total_count"] == 2
        assert {img["alt"] for img in result["images"]} == {"A", "B"}
        list_fn.assert_called_once()


class TestHandleDeleteRegistrationImage:
    def test_deletes_and_returns_id(self, app, assembly_id):
        image_id = uuid.uuid4()
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.dev.delete_registration_image") as delete,
        ):
            cu.id = uuid.uuid4()
            result = _handle_delete_registration_image(
                uow=MagicMock(),
                params={"assembly_id": str(assembly_id), "image_id": str(image_id)},
            )

        assert result == {"status": "success", "deleted_image_id": str(image_id)}
        delete.assert_called_once()


class TestHandleSetRegistrationImageAlt:
    def test_updates_alt_and_returns_serialised_image(self, app, assembly_id):
        image_id = uuid.uuid4()
        updated = _image(alt="Renamed")
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch(
                "opendlp.entrypoints.blueprints.dev.set_registration_image_alt",
                return_value=updated,
            ) as set_alt,
        ):
            cu.id = uuid.uuid4()
            result = _handle_set_registration_image_alt(
                uow=MagicMock(),
                params={
                    "assembly_id": str(assembly_id),
                    "image_id": str(image_id),
                    "alt": "Renamed",
                },
            )

        assert result["status"] == "success"
        assert result["image"]["alt"] == "Renamed"
        _, kwargs = set_alt.call_args
        assert kwargs["alt"] == "Renamed"


class TestHandleListImageSnippets:
    def test_pairs_image_with_html_snippet(self, app, assembly_id):
        image_a = _image(alt="Alpha", sha256="3" * 64)
        image_b = _image(alt="Beta", sha256="4" * 64)
        page = MagicMock()
        page.url_slug = "my-slug"
        # Mock the page repo lookup the handler does to derive the URL slug
        repo_uow = MagicMock()
        repo_uow.__enter__ = MagicMock(return_value=repo_uow)
        repo_uow.__exit__ = MagicMock(return_value=False)
        repo_uow.registration_pages.get_by_assembly_id = MagicMock(return_value=page)
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.dev.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.dev.bootstrap.bootstrap", return_value=repo_uow),
            patch(
                "opendlp.entrypoints.blueprints.dev.list_image_snippets",
                return_value=[(image_a, '<img src="..." alt="Alpha">'), (image_b, '<img src="..." alt="Beta">')],
            ),
        ):
            cu.id = uuid.uuid4()
            result = _handle_list_image_snippets(
                uow=MagicMock(),
                params={"assembly_id": str(assembly_id)},
            )

        assert result["status"] == "success"
        assert result["total_count"] == 2
        assert result["snippets"][0]["image"]["alt"] == "Alpha"
        assert "Alpha" in result["snippets"][0]["html"]


class TestHandleGetRegistrationImageForServing:
    def test_found_returns_serialised_image(self, app):
        image = _image(alt="Public", sha256="5" * 64)
        with (
            app.test_request_context(),
            patch(
                "opendlp.entrypoints.blueprints.dev.get_registration_image_for_serving",
                return_value=image,
            ) as lookup,
        ):
            result = _handle_get_registration_image_for_serving(
                uow=MagicMock(),
                params={"url_slug": "my-slug", "image_name": f"{'5' * 64}.png"},
            )

        assert result == {"status": "success", "found": True, "image": _serialise_image(image)}
        lookup.assert_called_once()

    def test_not_found_returns_none(self, app):
        with (
            app.test_request_context(),
            patch(
                "opendlp.entrypoints.blueprints.dev.get_registration_image_for_serving",
                return_value=None,
            ),
        ):
            result = _handle_get_registration_image_for_serving(
                uow=MagicMock(),
                params={"url_slug": "bad-slug", "image_name": "x.png"},
            )

        assert result == {"status": "success", "found": False, "image": None}
