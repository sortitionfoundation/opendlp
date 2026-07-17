# ABOUTME: Component tests for serving registration documents from the repository
# ABOUTME: Seeds a page + PDF in a FakeStore then GETs the public document route — no PostgreSQL

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_document import RegistrationDocument
from opendlp.domain.users import User
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_document_service import add_registration_document
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from tests.fakes import FakeStore, FakeUnitOfWork

MINIMAL_FORM_HTML = "<form method='post' action='{{ form_action }}'>{{ csrf_form_element }}</form>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch):
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _pdf(body: str = "document body") -> bytes:
    return f"%PDF-1.7\n1 0 obj {body}\n%%EOF\n".encode()


def _seed_page_with_document(
    store: FakeStore, admin: User, *, status: str = "published", body: str = "document body"
) -> tuple[str, RegistrationDocument]:
    with FakeUnitOfWork(store=store) as uow:
        assembly = create_assembly(
            uow=uow,
            title=f"Document Assembly {status} {body}",
            created_by_user_id=admin.id,
            question="Test question?",
        )
        assembly_id = assembly.id

    with FakeUnitOfWork(store=store) as uow:
        page = create_registration_page_with_slugs(uow, admin.id, assembly_id)
        url_slug = page.url_slug

    with FakeUnitOfWork(store=store) as uow:
        update_registration_page_html(uow, admin.id, assembly_id, MINIMAL_FORM_HTML)

    if status in ("published", "closed"):
        with FakeUnitOfWork(store=store) as uow:
            publish_registration_page(uow, admin.id, assembly_id)
    if status == "closed":
        with FakeUnitOfWork(store=store) as uow:
            close_registration_page(uow, admin.id, assembly_id)

    with FakeUnitOfWork(store=store) as uow:
        document = add_registration_document(uow, admin.id, assembly_id, _pdf(body), original_filename="info pack.pdf")

    return url_slug, document


class TestServeRegistrationDocument:
    def test_serves_published_document_with_headers(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, document = _seed_page_with_document(fake_store, admin_user)

        response = client.get(f"/register/{url_slug}/documents/{document.sha256}.pdf")

        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data == document.data
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Content-Disposition"].startswith("attachment")
        assert "info pack.pdf" in response.headers["Content-Disposition"]
        assert "immutable" in response.headers["Cache-Control"]
        assert response.get_etag()[0] == document.sha256

    def test_serves_test_mode_document(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, document = _seed_page_with_document(fake_store, admin_user, status="test")

        response = client.get(f"/register/{url_slug}/documents/{document.sha256}.pdf")
        assert response.status_code == 200

    def test_404_for_closed_page(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, document = _seed_page_with_document(fake_store, admin_user, status="closed")

        response = client.get(f"/register/{url_slug}/documents/{document.sha256}.pdf")
        assert response.status_code == 404

    def test_404_for_unknown_slug(self, client: FlaskClient) -> None:
        response = client.get("/register/no-such-slug/documents/deadbeef.pdf")
        assert response.status_code == 404

    def test_404_for_unknown_sha(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, _document = _seed_page_with_document(fake_store, admin_user)

        response = client.get(f"/register/{url_slug}/documents/0000000000000000.pdf")
        assert response.status_code == 404

    def test_404_for_sha_of_another_page(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        # A document is scoped to its page: a valid sha on page A must not be
        # fetchable via page B's slug. Distinct bytes give the pages distinct shas.
        url_slug_a, document = _seed_page_with_document(fake_store, admin_user, body="page a body")
        url_slug_b, _other = _seed_page_with_document(fake_store, admin_user, body="page b body")

        response = client.get(f"/register/{url_slug_b}/documents/{document.sha256}.pdf")
        assert response.status_code == 404
        # sanity check: the same sha resolves under its own page
        assert client.get(f"/register/{url_slug_a}/documents/{document.sha256}.pdf").status_code == 200

    def test_304_with_matching_etag(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, document = _seed_page_with_document(fake_store, admin_user)

        response = client.get(
            f"/register/{url_slug}/documents/{document.sha256}.pdf",
            headers={"If-None-Match": f'"{document.sha256}"'},
        )
        assert response.status_code == 304

    def test_404_when_feature_disabled(self, client: FlaskClient, fake_store, admin_user: User, monkeypatch) -> None:
        url_slug, document = _seed_page_with_document(fake_store, admin_user)
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "false")
        reload_flags()

        response = client.get(f"/register/{url_slug}/documents/{document.sha256}.pdf")
        assert response.status_code == 404
