# ABOUTME: Component tests for the backoffice registration image helpers and JSON routes
# ABOUTME: Drives the real POST/PATCH/DELETE endpoints + services over a FakeUnitOfWork via the test client

import uuid
from io import BytesIO

import pytest
from PIL import Image

from opendlp.domain.registration_image import RegistrationImage
from opendlp.entrypoints.blueprints.backoffice_registration import _image_to_dict
from opendlp.service_layer.image_processing import process_image
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from tests.fakes import FakeUnitOfWork

_MAX_BYTES = 10 * 1024 * 1024
_MAX_EDGE = 2048


def _png(color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


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


@pytest.fixture
def registration_page(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id)
    return page


def _seed_image(fake_store, page, *, alt: str = "Logo", color=(255, 0, 0)) -> RegistrationImage:
    processed = process_image(_png(color), max_bytes=_MAX_BYTES, max_edge_px=_MAX_EDGE)
    image = RegistrationImage.from_processed(page.id, processed, alt=alt)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_images.add(image)
        uow.commit()
    return image.create_detached_copy()


def _stored_images(fake_store, page) -> list[RegistrationImage]:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.registration_images.list_by_page_id(page.id)


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
    def test_upload_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        response = client.post(f"/backoffice/assembly/{assembly_id}/registration/images")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_patch_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        image_id = uuid.uuid4()
        response = client.patch(
            f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}",
            json={"alt": "x"},
        )
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_delete_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        image_id = uuid.uuid4()
        response = client.delete(f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}")
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestUploadModalRoute:
    """The Assets panel loads the upload modal from the server via HTMX.

    HX-Request gets just the modal fragment (swapped into a container); a plain
    browser navigation gets the whole registration page with the modal already
    open, so the feature degrades to a full page reload when JS is unavailable.
    """

    def test_htmx_request_returns_modal_fragment(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/upload-modal",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.data.decode()
        # A fragment, not the whole document
        assert "<html" not in body.lower()
        # The modal form posts the upload back to the JSON-free upload endpoint
        upload_url = f"/backoffice/assembly/{existing_assembly.id}/registration/images"
        assert f'action="{upload_url}"' in body
        assert f'hx-post="{upload_url}"' in body
        assert 'name="image"' in body
        assert 'name="alt"' in body
        assert "csrf_token" in body

    def test_plain_request_returns_full_page_with_modal_open(
        self, logged_in_admin, existing_assembly, registration_page
    ):
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/upload-modal",
        )

        assert response.status_code == 200
        body = response.data.decode()
        # Full document (fallback) ...
        assert "<html" in body.lower()
        # ... with the upload modal rendered open inside it
        upload_url = f"/backoffice/assembly/{existing_assembly.id}/registration/images"
        assert f'action="{upload_url}"' in body

    def test_requires_login(self, client, existing_assembly):
        response = client.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/upload-modal",
        )
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestUploadRoute:
    """Upload is HTMX-aware: an HX-Request gets an empty body plus an HX-Trigger
    carrying the new image so the page can update client-side and close the modal;
    a plain form post redirects back with a flash (full page reload)."""

    def test_htmx_upload_returns_asset_list_fragment_and_stores_image(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "Hello world"},
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.data.decode()
        # An out-of-band asset-list fragment refreshes the panel (and empties the
        # modal container, closing the modal); a toast trigger announces success.
        assert 'id="image-asset-list"' in body
        assert "hx-swap-oob" in body
        assert "Hello world" in body
        assert "show-toast" in response.headers.get("HX-Trigger", "")

        stored = _stored_images(fake_store, registration_page)
        assert len(stored) == 1
        assert stored[0].alt == "Hello world"
        assert stored[0].original_filename == "logo.png"

    def test_htmx_upload_rejects_missing_alt_rerenders_modal(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "   "},
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )
        # 422 so the htmx-422-swap handler re-renders the modal with the error
        assert response.status_code == 422
        body = response.data.decode()
        assert "alt" in body.lower()
        assert 'name="alt"' in body
        assert _stored_images(fake_store, registration_page) == []

    def test_htmx_upload_rejects_missing_file_rerenders_modal(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"alt": "Logo"},
            content_type="multipart/form-data",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert _stored_images(fake_store, registration_page) == []

    def test_plain_form_upload_redirects_and_stores_image(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "Hello world"},
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/registration" in response.location

        stored = _stored_images(fake_store, registration_page)
        assert len(stored) == 1
        assert stored[0].alt == "Hello world"

    def test_plain_form_upload_missing_alt_redirects_without_storing(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "   "},
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        assert _stored_images(fake_store, registration_page) == []


class TestDetailsModalRoute:
    """The per-image details/edit modal is loaded from the server via HTMX, opened
    from each Assets row. Like the upload modal, a plain navigation gets the full
    page with the modal already open so it works without JS."""

    def _url(self, assembly_id, image_id) -> str:
        return f"/backoffice/assembly/{assembly_id}/registration/images/{image_id}/details-modal"

    def test_htmx_request_returns_details_fragment(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        image = _seed_image(fake_store, registration_page, alt="A logo")

        response = logged_in_admin.get(self._url(existing_assembly.id, image.id), headers={"HX-Request": "true"})

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" not in body.lower()
        # The alt-edit form patches this image and the current alt is pre-filled
        item_url = f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}"
        assert f'hx-patch="{item_url}"' in body
        assert 'name="alt"' in body
        assert "A logo" in body
        # Delete control targets the same image
        assert f'hx-delete="{item_url}"' in body

    def test_plain_request_returns_full_page_with_modal_open(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        image = _seed_image(fake_store, registration_page, alt="A logo")

        response = logged_in_admin.get(self._url(existing_assembly.id, image.id))

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" in body.lower()
        item_url = f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}"
        assert f'hx-patch="{item_url}"' in body

    def test_requires_login(self, client, existing_assembly):
        response = client.get(self._url(existing_assembly.id, uuid.uuid4()))
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_unknown_image_redirects_to_registration(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.get(self._url(existing_assembly.id, uuid.uuid4()), headers={"HX-Request": "true"})
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/registration" in response.location


class TestPatchRoute:
    """Alt edits post (PATCH) from the details modal and return the refreshed
    asset-list fragment (out-of-band), which also closes the modal."""

    def test_patch_updates_alt_and_returns_asset_list_fragment(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        image = _seed_image(fake_store, registration_page, alt="Original")

        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}",
            data={"alt": "Renamed"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.data.decode()
        assert 'id="image-asset-list"' in body
        assert "hx-swap-oob" in body
        assert "Renamed" in body

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_images.get(image.id).alt == "Renamed"

    def test_patch_rejects_missing_alt_rerenders_modal(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        image = _seed_image(fake_store, registration_page, alt="Original")

        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}",
            data={"alt": "  "},
            headers={"HX-Request": "true"},
        )
        # 422 so the modal re-renders with the error inline
        assert response.status_code == 422
        body = response.data.decode()
        assert 'name="alt"' in body
        assert "alt" in body.lower()

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_images.get(image.id).alt == "Original"


class TestDeleteRoute:
    """Delete (DELETE) returns the refreshed asset-list fragment with the image gone."""

    def test_delete_returns_asset_list_fragment_and_removes_image(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        image = _seed_image(fake_store, registration_page, alt="Doomed")

        response = logged_in_admin.delete(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        body = response.data.decode()
        assert 'id="image-asset-list"' in body
        assert "hx-swap-oob" in body
        assert _stored_images(fake_store, registration_page) == []


class TestImageDetailsModalRendering:
    """Structural assertions on the server-rendered details modal, driven through
    the route (the modal is now real HTML, so we assert on the actual response)."""

    @pytest.fixture
    def rendered_modal(self, logged_in_admin, fake_store, existing_assembly, registration_page) -> str:
        image = _seed_image(fake_store, registration_page, alt="A logo")
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image.id}/details-modal",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        return response.data.decode()

    def test_thumbnail_and_metadata_present(self, rendered_modal):
        # Thumbnail uses the public URL; metadata block shows dimensions and file size
        assert "/assets/" in rendered_modal  # public image url
        assert "Dimensions" in rendered_modal
        assert "File size" in rendered_modal

    def test_filename_and_snippet_copy_use_clipboard_data_attrs(self, rendered_modal):
        # Copy buttons rely on the delegated clipboard helper in utilities.js
        assert "data-copy-text" in rendered_modal
        assert "image-details-filename" in rendered_modal
        assert "image-details-snippet" in rendered_modal

    def test_footer_has_delete_and_save_alt(self, rendered_modal):
        assert "Delete image" in rendered_modal
        assert "Save alt" in rendered_modal
