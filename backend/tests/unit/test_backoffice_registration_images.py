"""ABOUTME: Unit tests for the backoffice registration image helpers and JSON routes
ABOUTME: Covers _image_to_dict and the POST/PATCH/DELETE endpoints"""

import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from opendlp.domain.registration_image import RegistrationImage
from opendlp.entrypoints.blueprints.backoffice_registration import (
    _image_to_dict,
)
from opendlp.entrypoints.flask_app import create_app


@pytest.fixture
def app():
    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def assembly_id() -> uuid.UUID:
    return uuid.uuid4()


def _image(*, alt: str = "Logo", sha256: str = "a" * 64, original_filename: str = "") -> RegistrationImage:
    return RegistrationImage(
        registration_page_id=uuid.uuid4(),
        byte_size=123,
        width=100,
        height=80,
        sha256=sha256,
        data=b"\x89PNG...",
        alt=alt,
        original_filename=original_filename,
        created_by=uuid.uuid4(),
    )


class TestImageToDict:
    def test_builds_public_url_and_snippet_when_slug_present(self, app):
        image = _image(alt="A nice logo", sha256="b" * 64)
        with app.test_request_context():
            result = _image_to_dict(image, url_slug="my-slug")

        assert result["id"] == str(image.id)
        assert result["alt"] == "A nice logo"
        assert result["file_name"] == f"{'b' * 64}.png"
        assert result["display_name"] == "A nice logo"
        assert "/register/my-slug/assets/" in result["public_url"]
        assert result["public_url"].endswith(f"{'b' * 64}.png")
        # Domain helper html-escapes both src and alt
        assert result["img_snippet"].startswith('<img src="')
        assert 'alt="A nice logo"' in result["img_snippet"]
        assert result["width"] == 100
        assert result["height"] == 80
        assert result["byte_size"] == 123

    def test_includes_original_filename(self, app):
        image = _image(alt="A nice logo", original_filename="logo.png")
        with app.test_request_context():
            result = _image_to_dict(image, url_slug="my-slug")
        assert result["original_filename"] == "logo.png"

    def test_falls_back_to_original_filename_when_alt_blank(self, app):
        image = _image(alt="   ", sha256="c" * 64, original_filename="holiday photo.png")
        with app.test_request_context():
            result = _image_to_dict(image, url_slug="my-slug")
        assert result["display_name"] == "holiday photo.png"

    def test_falls_back_to_short_sha_when_alt_and_filename_blank(self, app):
        image = _image(alt="   ", sha256="c" * 64)
        with app.test_request_context():
            result = _image_to_dict(image, url_slug="my-slug")
        assert result["display_name"] == f"{'c' * 8}.png"

    def test_omits_public_url_and_snippet_when_no_slug(self, app):
        image = _image(sha256="d" * 64)
        with app.test_request_context():
            result = _image_to_dict(image, url_slug="")
        assert result["public_url"] == ""
        assert result["img_snippet"] == ""


class TestImageRoutesRequireLogin:
    def test_upload_redirects_anonymous_to_login(self, client, assembly_id):
        response = client.post(f"/backoffice/assembly/{assembly_id}/registration/images")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_patch_redirects_anonymous_to_login(self, client, assembly_id):
        image_id = uuid.uuid4()
        response = client.patch(
            f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}",
            json={"alt": "x"},
        )
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_delete_redirects_anonymous_to_login(self, client, assembly_id):
        image_id = uuid.uuid4()
        response = client.delete(f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}")
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestUploadRouteHappyPath:
    """The route is shielded by login_required + current_user, so we bypass auth
    via LOGIN_DISABLED and patch the service-layer functions."""

    @pytest.fixture
    def authed_client(self, app):
        app.config["LOGIN_DISABLED"] = True
        return app.test_client()

    def test_upload_with_file_and_alt_returns_201_and_image_dict(self, app, authed_client, assembly_id):
        stored = _image(alt="Hello world")
        with (
            patch("opendlp.entrypoints.blueprints.backoffice_registration.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.add_registration_image",
                return_value=stored,
            ) as add,
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration._resolve_page_url_slug",
                return_value="my-slug",
            ),
        ):
            cu.id = uuid.uuid4()
            response = authed_client.post(
                f"/backoffice/assembly/{assembly_id}/registration/images",
                data={
                    "image": (io.BytesIO(b"\x89PNG-fake-bytes"), "logo.png"),
                    "alt": "Hello world",
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 201
        body = response.get_json()
        assert body["image"]["alt"] == "Hello world"
        assert body["image"]["id"] == str(stored.id)
        add.assert_called_once()
        # The uploaded filename is threaded through to the service layer.
        _, kwargs = add.call_args
        assert kwargs.get("original_filename") == "logo.png"

    def test_upload_rejects_missing_alt(self, authed_client, assembly_id):
        response = authed_client.post(
            f"/backoffice/assembly/{assembly_id}/registration/images",
            data={"image": (io.BytesIO(b"bytes"), "logo.png"), "alt": "   "},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert "alt" in response.get_json()["error"].lower()

    def test_upload_rejects_missing_file(self, authed_client, assembly_id):
        response = authed_client.post(
            f"/backoffice/assembly/{assembly_id}/registration/images",
            data={"alt": "Logo"},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400


class TestPatchRouteHappyPath:
    @pytest.fixture
    def authed_client(self, app):
        app.config["LOGIN_DISABLED"] = True
        return app.test_client()

    def test_patch_updates_alt_and_returns_image(self, authed_client, assembly_id):
        updated = _image(alt="Renamed")
        image_id = uuid.uuid4()
        with (
            patch("opendlp.entrypoints.blueprints.backoffice_registration.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.set_registration_image_alt",
                return_value=updated,
            ) as set_alt,
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration._resolve_page_url_slug",
                return_value="my-slug",
            ),
        ):
            cu.id = uuid.uuid4()
            response = authed_client.patch(
                f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}",
                json={"alt": "Renamed"},
            )

        assert response.status_code == 200
        body = response.get_json()
        assert body["image"]["alt"] == "Renamed"
        set_alt.assert_called_once()
        _, kwargs = set_alt.call_args
        assert kwargs.get("alt") == "Renamed"

    def test_patch_rejects_missing_alt(self, authed_client, assembly_id):
        image_id = uuid.uuid4()
        response = authed_client.patch(
            f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}",
            json={"alt": "  "},
        )
        assert response.status_code == 400


class TestDeleteRouteHappyPath:
    @pytest.fixture
    def authed_client(self, app):
        app.config["LOGIN_DISABLED"] = True
        return app.test_client()

    def test_delete_returns_204(self, authed_client, assembly_id):
        image_id = uuid.uuid4()
        with (
            patch("opendlp.entrypoints.blueprints.backoffice_registration.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.delete_registration_image",
                return_value=None,
            ) as delete,
        ):
            cu.id = uuid.uuid4()
            response = authed_client.delete(
                f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}",
            )

        assert response.status_code == 204
        assert response.data == b""
        delete.assert_called_once()


class TestImageDetailsModalTemplate:
    """Structural assertions on the Image Details modal in assembly_registration.html.

    The modal HTML lives inline in the registration template, gated by
    ``<template x-if="imageDetailsModalOpen && editingImage">`` so Alpine controls
    visibility client-side. Rendering the page through the route requires a real
    authenticated user (the base layout reads ``current_user.global_role`` in a
    context processor), which is heavyweight for verifying static modal markup.

    We instead scan the template file and confirm the enhanced modal carries the
    expected structural markers — thumbnail binding, read-only inputs with copy
    handlers, danger-styled Delete button, and the renamed "Save alt" button.
    """

    @pytest.fixture
    def modal_block(self) -> str:
        """Return only the Image Details modal subsection of the template."""
        path = Path(__file__).resolve().parents[2] / "templates/backoffice/assembly_registration.html"
        text = path.read_text(encoding="utf-8")
        start_marker = "{# Image Details / Edit Alt Modal #}"
        end_marker = "{# Toast notification #}"
        start = text.find(start_marker)
        end = text.find(end_marker, start)
        assert start != -1 and end != -1, "Image Details modal section not found in template"
        return text[start:end]

    @pytest.fixture
    def alpine_data_block(self) -> str:
        """Return the Alpine data block (where the JS handlers live)."""
        path = Path(__file__).resolve().parents[2] / "templates/backoffice/assembly_registration.html"
        return path.read_text(encoding="utf-8")

    def test_thumbnail_binds_to_public_url_with_no_preview_fallback(self, modal_block):
        assert ':src="editingImage.public_url"' in modal_block
        assert ':alt="editingImage.alt' in modal_block
        # Fallback hint when the page has no slug yet (public_url is blank)
        assert "No preview" in modal_block

    def test_read_only_filename_input_has_copy_handler(self, modal_block):
        assert 'id="image-details-filename"' in modal_block
        assert "readonly" in modal_block
        assert ':value="editingImage.file_name"' in modal_block
        # Click-to-select the value
        assert "$event.target.select()" in modal_block
        # Copy uses the new generic clipboard helper
        assert "copyToClipboard(editingImage.file_name" in modal_block

    def test_original_filename_shown_in_metadata_block_only_when_present(self, modal_block):
        """Original filename sits inside the top metadata block alongside Dimensions
        and File size, gated by an x-if so the row collapses out of the grid for
        older uploads that have no original_filename stored. It's display-only —
        no input, no copy button."""
        assert 'x-text="editingImage.original_filename"' in modal_block
        assert 'x-if="editingImage.original_filename"' in modal_block
        # No standalone copy input/button for the original filename
        assert 'id="image-details-original-filename"' not in modal_block
        assert "copyToClipboard(editingImage.original_filename" not in modal_block

    def test_read_only_snippet_input_has_copy_handler(self, modal_block):
        assert 'id="image-details-snippet"' in modal_block
        assert ':value="editingImage.img_snippet"' in modal_block
        # Snippet copy reuses the existing helper (which guards on missing public URL)
        assert "copyImageSnippet(editingImage)" in modal_block

    def test_footer_has_delete_on_left_and_renamed_save_button(self, modal_block):
        # Danger-styled Delete handler exists and is wired through a non-confirming method
        assert 'variant="danger"' in modal_block
        assert "deleteEditingImage()" in modal_block
        assert "Delete image" in modal_block
        # The primary save button is renamed to clarify what's persisted
        assert "Save alt" in modal_block
        # Old generic "Save" label is no longer the button text
        assert 'button(_("Save"),' not in modal_block

    def test_alpine_data_block_exposes_copy_helper_and_delete_method(self, alpine_data_block):
        # Generic clipboard helper used by the filename copy button
        assert "copyToClipboard(text, successMessage)" in alpine_data_block
        # Modal-scoped delete that closes the modal on success and skips the panel's confirm()
        assert "deleteEditingImage()" in alpine_data_block
        assert "this.imageDetailsModalOpen = false" in alpine_data_block
