"""ABOUTME: Unit tests for the backoffice registration image helpers and JSON routes
ABOUTME: Covers _image_to_dict, _add_image_honouring_alt and the POST/PATCH/DELETE endpoints"""

import io
import uuid
from unittest.mock import patch

import pytest

from opendlp.domain.registration_image import RegistrationImage
from opendlp.entrypoints.blueprints.backoffice_registration import (
    _add_image_honouring_alt,
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


def _image(*, alt: str = "Logo", sha256: str = "a" * 64) -> RegistrationImage:
    return RegistrationImage(
        registration_page_id=uuid.uuid4(),
        byte_size=123,
        width=100,
        height=80,
        sha256=sha256,
        data=b"\x89PNG...",
        alt=alt,
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

    def test_falls_back_to_short_sha_when_alt_blank(self, app):
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


class TestAddImageHonouringAlt:
    def test_no_dedup_returns_image_directly(self, app, assembly_id):
        stored = _image(alt="Hello")
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.backoffice_registration.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.add_registration_image",
                return_value=stored,
            ) as add,
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.set_registration_image_alt",
            ) as set_alt,
        ):
            cu.id = uuid.uuid4()
            result = _add_image_honouring_alt(assembly_id, b"raw-bytes", alt="Hello")

        add.assert_called_once()
        set_alt.assert_not_called()
        assert result is stored

    def test_dedup_returning_different_alt_triggers_followup_update(self, app, assembly_id):
        stored = _image(alt="")  # existing row with empty alt (legacy upload)
        updated = _image(alt="New alt")
        with (
            app.test_request_context(),
            patch("opendlp.entrypoints.blueprints.backoffice_registration.current_user") as cu,
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.add_registration_image",
                return_value=stored,
            ),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.set_registration_image_alt",
                return_value=updated,
            ) as set_alt,
        ):
            cu.id = uuid.uuid4()
            result = _add_image_honouring_alt(assembly_id, b"raw-bytes", alt="New alt")

        set_alt.assert_called_once()
        _, kwargs = set_alt.call_args
        # alt argument is passed by keyword in the helper
        assert kwargs.get("alt") == "New alt"
        assert result is updated


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
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration._add_image_honouring_alt",
                return_value=stored,
            ) as helper,
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
        helper.assert_called_once()

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
