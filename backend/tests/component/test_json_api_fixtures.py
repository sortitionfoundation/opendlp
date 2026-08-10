# ABOUTME: Records the API fixtures the Vitest suite imports, and pins each JSON response shape
# ABOUTME: Drives the real routes over a FakeUnitOfWork, validates against the schema, diffs the fixture

from io import BytesIO

import pytest
from PIL import Image

from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from tests.api_fixtures import assert_matches_schema, check_api_fixture, normalise
from tests.fakes import FakeUnitOfWork

SLUG_PLACEHOLDER = "example-assembly"
SHA_PLACEHOLDER = "0" * 64


def _png(color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf(marker: bytes = b"body") -> bytes:
    return b"%PDF-1.4\n" + marker + b"\n%%EOF"


@pytest.fixture
def registration_page(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        return create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id)


def _replacements(page, body, asset_key: str) -> dict[str, str]:
    """Map this run's generated slug and content hash onto stable placeholders.

    The slug is random per page and the hash depends on the exact encoder output,
    so both would otherwise churn the fixture on every run for no real change.
    """
    file_name = body[asset_key]["file_name"]
    return {
        page.url_slug: SLUG_PLACEHOLDER,
        file_name.rsplit(".", 1)[0]: SHA_PLACEHOLDER,
    }


class TestRegistrationImageFixtures:
    def test_upload_response_matches_schema_and_fixture(self, logged_in_admin, existing_assembly, registration_page):
        """The 201 from an image upload is the shape the assets panel renders a new row from."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "Assembly logo"},
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        check_api_fixture(
            "registration-image-upload",
            body,
            schema_name="registration-image",
            replacements=_replacements(registration_page, body, "image"),
        )

    def test_alt_update_response_matches_schema_and_fixture(
        self, logged_in_admin, existing_assembly, registration_page
    ):
        """The 200 from a PATCH carries the same image shape as the upload, not a subset."""
        upload = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "Assembly logo"},
            content_type="multipart/form-data",
        )
        image_id = upload.get_json()["image"]["id"]

        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images/{image_id}",
            json={"alt": "Assembly logo, renamed"},
        )

        assert response.status_code == 200
        body = response.get_json()
        check_api_fixture(
            "registration-image-alt-update",
            body,
            schema_name="registration-image",
            replacements=_replacements(registration_page, body, "image"),
        )


class TestRegistrationDocumentFixtures:
    def test_upload_response_matches_schema_and_fixture(self, logged_in_admin, existing_assembly, registration_page):
        """The 201 from a PDF upload is the shape the assets panel renders a new row from."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf"), "label": "Information pack"},
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        check_api_fixture(
            "registration-document-upload",
            body,
            schema_name="registration-document",
            replacements=_replacements(registration_page, body, "document"),
        )


class TestErrorEnvelopeFixtures:
    def test_validation_error_matches_schema_and_fixture(self, logged_in_admin, existing_assembly, registration_page):
        """A rejected upload returns the standard error envelope, not a bespoke shape."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "   "},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        check_api_fixture("image-upload-error", response.get_json(), schema_name="error")

    def test_permission_error_matches_schema(self, logged_in_user, existing_assembly, registration_page):
        """A 403 uses the same envelope as a 400 - the status code carries the difference."""
        response = logged_in_user.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/images",
            data={"image": (BytesIO(_png()), "logo.png"), "alt": "Assembly logo"},
            content_type="multipart/form-data",
        )

        assert response.status_code == 403
        assert_matches_schema(response.get_json(), "error")


class TestSchemasRejectDrift:
    """The schemas have to actually fail on the changes they exist to catch."""

    def test_an_added_field_is_rejected(self):
        body = {"image": {"id": "x"}, "unexpected": "field"}
        with pytest.raises(Exception, match="unexpected"):
            assert_matches_schema(body, "registration-image")

    def test_a_missing_field_is_rejected(self):
        with pytest.raises(Exception, match="required"):
            assert_matches_schema({}, "registration-image")

    def test_an_error_body_carrying_an_extra_key_is_rejected(self):
        with pytest.raises(Exception, match="traceback"):
            assert_matches_schema({"error": "Nope", "traceback": "..."}, "error")


class TestNormalise:
    def test_replaces_every_uuid_with_one_placeholder(self):
        body = {"a": "6d1f9e0c-1111-4111-8111-111111111111", "b": "9c2e8f1d-2222-4222-8222-222222222222"}
        assert normalise(body) == {
            "a": "00000000-0000-4000-8000-000000000000",
            "b": "00000000-0000-4000-8000-000000000000",
        }

    def test_applies_caller_replacements_inside_longer_strings(self):
        body = {"url": "/register/wandering-heron/assets/abc.png"}
        assert normalise(body, {"wandering-heron": "example-assembly"}) == {
            "url": "/register/example-assembly/assets/abc.png"
        }

    def test_recurses_into_lists_and_leaves_non_strings_alone(self):
        body = {"images": [{"width": 20, "ok": True, "id": "6d1f9e0c-1111-4111-8111-111111111111"}]}
        assert normalise(body) == {"images": [{"width": 20, "ok": True, "id": "00000000-0000-4000-8000-000000000000"}]}

    def test_leaves_keys_alone_so_a_rename_still_shows_as_a_diff(self):
        assert normalise({"6d1f9e0c-1111-4111-8111-111111111111": "x"}) == {"6d1f9e0c-1111-4111-8111-111111111111": "x"}
