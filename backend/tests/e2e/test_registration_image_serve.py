"""ABOUTME: E2E tests for serving registration images from the database
ABOUTME: Seeds a page and image in the DB then GETs the public asset route"""

from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from flask.testing import FlaskClient
from PIL import Image

from opendlp.domain.registration_image import RegistrationImage
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_image_service import add_registration_image
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

MINIMAL_FORM_HTML = "<form method='post' action='{{ form_action }}'>{{ csrf_form_element }}</form>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (30, 20), (12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_page_with_image(session_factory, admin_user, *, status: str = "published") -> tuple[str, RegistrationImage]:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title=f"Image Assembly {status}",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        page = create_registration_page_with_slugs(uow, admin_user.id, assembly_id)
        url_slug = page.url_slug

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        update_registration_page_html(uow, admin_user.id, assembly_id, MINIMAL_FORM_HTML)

    if status in ("published", "closed"):
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            publish_registration_page(uow, admin_user.id, assembly_id)
    if status == "closed":
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            close_registration_page(uow, admin_user.id, assembly_id)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        image = add_registration_image(uow, admin_user.id, assembly_id, _png())

    return url_slug, image


class TestServeRegistrationImage:
    def test_serves_published_image_with_headers(
        self, client: FlaskClient, postgres_session_factory, admin_user
    ) -> None:
        url_slug, image = _seed_page_with_image(postgres_session_factory, admin_user)

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")

        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert response.data == image.data
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "immutable" in response.headers["Cache-Control"]
        assert response.get_etag()[0] == image.sha256

    def test_serves_test_mode_image(self, client: FlaskClient, postgres_session_factory, admin_user) -> None:
        url_slug, image = _seed_page_with_image(postgres_session_factory, admin_user, status="test")

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 200

    def test_404_for_closed_page(self, client: FlaskClient, postgres_session_factory, admin_user) -> None:
        url_slug, image = _seed_page_with_image(postgres_session_factory, admin_user, status="closed")

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 404

    def test_404_for_unknown_slug(self, client: FlaskClient) -> None:
        response = client.get("/register/no-such-slug/assets/deadbeef.png")
        assert response.status_code == 404

    def test_404_for_unknown_sha(self, client: FlaskClient, postgres_session_factory, admin_user) -> None:
        url_slug, _image = _seed_page_with_image(postgres_session_factory, admin_user)

        response = client.get(f"/register/{url_slug}/assets/0000000000000000.png")
        assert response.status_code == 404

    def test_304_with_matching_etag(self, client: FlaskClient, postgres_session_factory, admin_user) -> None:
        url_slug, image = _seed_page_with_image(postgres_session_factory, admin_user)

        response = client.get(
            f"/register/{url_slug}/assets/{image.sha256}.png",
            headers={"If-None-Match": f'"{image.sha256}"'},
        )
        assert response.status_code == 304

    def test_404_when_feature_disabled(
        self, client: FlaskClient, postgres_session_factory, admin_user, monkeypatch
    ) -> None:
        url_slug, image = _seed_page_with_image(postgres_session_factory, admin_user)
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "false")
        reload_flags()

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 404
