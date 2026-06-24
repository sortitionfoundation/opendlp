# ABOUTME: Component tests for the HTMX-loaded preview/share and skeleton modals
# ABOUTME: Drives the real GET modal routes over a FakeUnitOfWork via the test client


import pytest

from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def registration_page(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id)
    return page


class TestPreviewModalRoute:
    """The Preview / Share modal is loaded from the server via HTMX.

    HX-Request gets the modal fragment; a plain navigation gets the whole page with
    the modal already open, so it degrades to a full page reload without JS.
    """

    def _url(self, assembly_id) -> str:
        return f"/backoffice/assembly/{assembly_id}/registration/preview-modal"

    def test_htmx_request_returns_modal_fragment(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.get(self._url(existing_assembly.id), headers={"HX-Request": "true"})

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" not in body.lower()
        # TEST status (default for a new page) → the preview/test title + notice
        assert "Preview and Test Responses" in body
        assert "test mode" in body.lower()
        # The registration URL (built from the page slug) is shown
        assert registration_page.url_slug in body
        # Short URL + QR are configured by create_registration_page_with_slugs
        assert "QR Code" in body

    def test_plain_request_returns_full_page_with_modal_open(
        self, logged_in_admin, existing_assembly, registration_page
    ):
        response = logged_in_admin.get(self._url(existing_assembly.id))

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" in body.lower()
        assert "Preview and Test Responses" in body
        assert registration_page.url_slug in body

    def test_requires_login(self, client, existing_assembly):
        response = client.get(self._url(existing_assembly.id))
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_no_registration_page_redirects(self, logged_in_admin, existing_assembly):
        # No registration page created → nothing to preview
        response = logged_in_admin.get(self._url(existing_assembly.id), headers={"HX-Request": "true"})
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/registration" in response.location


class TestSkeletonModalRoute:
    """The Form Skeleton modal is loaded from the server via HTMX, with the
    generated starter HTML server-rendered into the textarea."""

    def _url(self, assembly_id) -> str:
        return f"/backoffice/assembly/{assembly_id}/registration/skeleton-modal"

    def test_htmx_request_returns_modal_fragment(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.get(self._url(existing_assembly.id), headers={"HX-Request": "true"})

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" not in body.lower()
        assert "Form Skeleton" in body
        assert "<textarea" in body
        assert 'id="skeleton-html-textarea"' in body
        # Copy uses the delegated clipboard helper, reading the textarea content
        assert 'data-copy-target="skeleton-html-textarea"' in body

    def test_plain_request_returns_full_page_with_modal_open(
        self, logged_in_admin, existing_assembly, registration_page
    ):
        response = logged_in_admin.get(self._url(existing_assembly.id))

        assert response.status_code == 200
        body = response.data.decode()
        assert "<html" in body.lower()
        assert "Form Skeleton" in body
        assert 'id="skeleton-html-textarea"' in body

    def test_requires_login(self, client, existing_assembly):
        response = client.get(self._url(existing_assembly.id))
        assert response.status_code == 302
        assert "/auth/login" in response.location
