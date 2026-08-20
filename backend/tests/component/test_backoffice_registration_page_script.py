# ABOUTME: Component tests for the registration page's JavaScript after its script extraction
# ABOUTME: Pins the bundle tag and the JSON data block that replaced 580 lines of inline script

import json
import re
from io import BytesIO

import pytest
from PIL import Image

from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPageStatus
from opendlp.service_layer.image_processing import process_image
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from tests.fakes import FakeUnitOfWork

_MAX_BYTES = 10 * 1024 * 1024
_MAX_EDGE = 2048

# The sentinel the per-item URLs are rendered with, matched by ID_SENTINEL in
# src/js/lib/url-utils.js. urlWithId() swaps it for the real id at call time, so a
# change on either side without the other silently produces a URL that 404s.
ID_SENTINEL = "00000000-0000-0000-0000-000000000000"

# Every Alpine binding in the template that the extracted component has to satisfy.
# Alpine does not report an unknown property, so a rename in src/js/ that is not made
# here leaves the page silently doing nothing where the binding was.
BOUND_NAMES = [
    "registrationPageController()",
    "markEditDirty()",
    "allowLeave()",
    "guardLeave($event)",
    "openConfirmClose()",
    "cancelConfirmClose()",
    "closeLeaveModal()",
    "discardAndLeave()",
    "fetchSkeleton()",
    "closeSkeletonModal()",
    "showPlainSkeleton()",
    "showStyledSkeleton()",
    "copySkeletonToClipboard()",
    "skeletonHtmlPlain",
    "skeletonHtmlStyled",
    "openImageUploadModal()",
    "closeImageUploadModalIfAllowed()",
    "onImageFileSelected($event)",
    "submitImageUpload()",
    "deleteImage(image)",
    "copyImageSnippet(image)",
    "openImageDetailsModal(image)",
    "closeImageDetailsModalIfAllowed()",
    "deleteEditingImage()",
    "submitImageEdit()",
    "openDocumentUploadModal()",
    "closeDocumentUploadModalIfAllowed()",
    "onDocumentFileSelected($event)",
    "submitDocumentUpload()",
    "deleteDocument(doc)",
    "copyDocumentSnippet(doc)",
    "openDocumentDetailsModal(doc)",
    "closeDocumentDetailsModalIfAllowed()",
    "deleteEditingDocument()",
    "submitDocumentEdit()",
    "copyToClipboard($el)",
    "formatBytes(editingImage.byte_size)",
    "formatBytes(editingDocument.byte_size)",
    "toastVisible",
    "toastMessage",
]

# Every message key the component reads. A key missing from the data block reads as
# undefined, which shows the user an empty toast rather than an error.
MESSAGE_KEYS = [
    "skeletonFetchFailed",
    "copied",
    "copyFailed",
    "snippetCopied",
    "noPublicUrl",
    "uploadFailed",
    "altRequired",
    "imageUploaded",
    "imageUploadNetworkError",
    "confirmDeleteImage",
    "deleteImageFailed",
    "imageDeleted",
    "deleteImageNetworkError",
    "updateImageFailed",
    "imageUpdated",
    "updateImageNetworkError",
    "labelRequired",
    "documentUploaded",
    "documentUploadNetworkError",
    "confirmDeleteDocument",
    "deleteDocumentFailed",
    "documentDeleted",
    "deleteDocumentNetworkError",
    "updateDocumentFailed",
    "documentUpdated",
    "updateDocumentNetworkError",
]


def _png(color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def registration_page(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        return create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id, name="Registration page")


@pytest.fixture
def page_html(logged_in_admin, registration_page, existing_assembly) -> str:
    response = logged_in_admin.get(
        f"/backoffice/assembly/{existing_assembly.id}/registration/{registration_page.url_slug}"
    )
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def every_view_html(logged_in_admin, fake_store, registration_page, existing_assembly) -> str:
    """Every section of the page, in every state, joined together.

    One component drives three sections, edit mode and the published state, but
    each renders only its own markup - so a binding lives on exactly one of them,
    and checking the default view alone would miss most of them.
    """
    base = f"/backoffice/assembly/{existing_assembly.id}/registration/{registration_page.url_slug}"
    views = [f"{base}?section={section}" for section in ("form", "email", "preview")]
    views.append(f"{base}?section=form&edit=1")

    def render(url: str) -> str:
        response = logged_in_admin.get(url)
        assert response.status_code == 200, f"{url} did not render"
        return response.get_data(as_text=True)

    pages = [render(url) for url in views]

    # Closing a registration is only offered once it is published, so its
    # confirmation renders nowhere above.
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_pages.get(registration_page.id).status = RegistrationPageStatus.PUBLISHED
        uow.commit()
    pages.append(render(f"{base}?section=preview"))

    return "\n".join(pages)


def _seed_image(fake_store, page, *, alt: str) -> RegistrationImage:
    processed = process_image(_png(), max_bytes=_MAX_BYTES, max_edge_px=_MAX_EDGE)
    image = RegistrationImage.from_processed(page.assembly_id, processed, alt=alt)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_images.add(image)
        uow.commit()
    return image.create_detached_copy()


def _page_data(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="registration-page-data"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "the registration page data block is missing"
    return json.loads(match.group(1))


class TestTheBundle:
    def test_is_loaded(self, page_html: str):
        """The component comes from an entry point built out of src/js/backoffice/registration-page.js."""
        assert "backoffice/js/registration-page.js" in page_html

    def test_is_cache_busted_and_nonced(self, page_html: str):
        match = re.search(
            r'<script nonce="[^"]+"\s+src="[^"]*backoffice/js/registration-page\.js\?v=[^"]+"',
            page_html,
        )
        assert match, "the bundle must carry a CSP nonce and a static_hashes cache-buster"

    def test_registers_the_component_before_alpine_starts(self, page_html: str):
        """The bundle must run before Alpine, or its alpine:init listener is registered too late.

        Its <script> sits after Alpine's in the document, which is only correct
        because Alpine's is deferred and the bundle's is not: a non-deferred script
        runs during parsing, a deferred one only once parsing has finished. Drop the
        defer, or add one to the bundle, and the page silently loses every binding.
        """
        alpine_tag = re.search(r"<script[^>]*alpine-csp\.js[^>]*>", page_html, re.DOTALL | re.IGNORECASE)
        bundle_tag = re.search(
            r"<script[^>]*backoffice/js/registration-page\.js[^>]*>", page_html, re.DOTALL | re.IGNORECASE
        )
        assert alpine_tag and bundle_tag
        assert "defer" in alpine_tag.group(0), "Alpine must stay deferred"
        assert "defer" not in bundle_tag.group(0), "the registration page bundle must not be deferred"

    def test_the_page_carries_no_executable_inline_script(self, page_html: str):
        """The page used to define 580 lines of Alpine component in an inline block.

        It must not again. The JSON data block is not executable and does not count -
        it has a type attribute the browser will not run.
        """
        inline_bodies = re.findall(
            r'<script(?![^>]*\ssrc=)(?![^>]*type="application/json")[^>]*>(.*?)</script>',
            page_html,
            re.DOTALL | re.IGNORECASE,
        )
        assert [body for body in inline_bodies if body.strip()] == []

    def test_is_not_loaded_on_the_page_list(self, logged_in_admin, existing_assembly):
        """Nothing on the registration page list is driven by this component, so the bundle would be dead weight."""
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/registration")

        assert response.status_code == 200
        assert "backoffice/js/registration-page.js" not in response.get_data(as_text=True)


class TestTheBindings:
    @pytest.mark.parametrize("name", BOUND_NAMES)
    def test_binding_is_present(self, every_view_html: str, name: str):
        assert name in every_view_html


class TestTheDataBlock:
    def test_carries_the_csrf_token_the_json_routes_require(self, page_html: str):
        assert _page_data(page_html)["csrfToken"]

    def test_carries_every_route_the_component_calls(self, page_html: str, existing_assembly):
        urls = _page_data(page_html)["urls"]

        assert set(urls) == {
            "skeleton",
            "uploadImage",
            "imageItem",
            "uploadDocument",
            "documentItem",
        }
        for name, url in urls.items():
            assert str(existing_assembly.id) in url, f"{name} is not addressed to this assembly"

    def test_renders_the_per_item_routes_with_the_sentinel_id(self, page_html: str):
        urls = _page_data(page_html)["urls"]

        assert urls["imageItem"].endswith(ID_SENTINEL)
        assert urls["documentItem"].endswith(ID_SENTINEL)

    @pytest.mark.parametrize("key", MESSAGE_KEYS)
    def test_carries_the_message(self, page_html: str, key: str):
        assert _page_data(page_html)["messages"][key]

    def test_says_whether_the_editor_is_unlocked(self, logged_in_admin, registration_page, existing_assembly):
        url = f"/backoffice/assembly/{existing_assembly.id}/registration/{registration_page.url_slug}"

        read_only = logged_in_admin.get(url).get_data(as_text=True)
        editing = logged_in_admin.get(f"{url}?edit=1").get_data(as_text=True)

        assert _page_data(read_only)["editMode"] is False
        assert _page_data(editing)["editMode"] is True

    def test_seeds_the_assets_already_on_the_page(
        self, logged_in_admin, fake_store, registration_page, existing_assembly
    ):
        """The list is mutated in place after load, so it has to start out populated."""
        _seed_image(fake_store, registration_page, alt="Assembly logo")

        html = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/{registration_page.url_slug}"
        ).get_data(as_text=True)

        data = _page_data(html)
        assert [image["alt"] for image in data["images"]] == ["Assembly logo"]
        assert data["documents"] == []

    def test_escapes_a_display_name_that_would_otherwise_close_the_script_tag(
        self, logged_in_admin, fake_store, registration_page, existing_assembly
    ):
        """An organiser controls the alt text, so it reaches the page as untrusted input.

        This is the reason the configuration is a JSON block rendered with |tojson
        rather than an x-data attribute: the escaping is the filter's job, done once,
        rather than something each value has to be trusted not to need.
        """
        _seed_image(fake_store, registration_page, alt='</script><script>alert("xss")</script>')

        html = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/registration/{registration_page.url_slug}"
        ).get_data(as_text=True)

        assert "<script>alert" not in html
        assert _page_data(html)["images"][0]["alt"] == '</script><script>alert("xss")</script>'


class TestTheDataBlockWithoutAPage:
    def test_is_not_rendered_at_all(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/registration")

        assert 'id="registration-page-data"' not in response.get_data(as_text=True)

    def test_the_route_still_renders(self, logged_in_admin, existing_assembly):
        assert logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/registration").status_code == 200
