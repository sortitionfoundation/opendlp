# ABOUTME: Component tests for serving registration images from the repository
# ABOUTME: Seeds a page + image in a FakeStore then GETs the public asset route — no PostgreSQL

from io import BytesIO

import pytest
from flask.testing import FlaskClient
from PIL import Image

from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.users import User
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_image_service import add_registration_image
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    page_for_assembly,
    publish_registration_page,
    update_registration_page_html,
)
from tests.fakes import FakeStore, FakeUnitOfWork


def _page_id(uow, assembly_id):  # type: ignore[no-untyped-def]
    """The id of the assembly's single registration page."""
    page = page_for_assembly(uow, assembly_id)
    assert page is not None
    return page.id


MINIMAL_FORM_HTML = "<form method='post' action='{{ form_action }}'>{{ csrf_form_element }}</form>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch):
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (30, 20), (12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_page_with_image(store: FakeStore, admin: User, *, status: str = "published") -> tuple[str, RegistrationImage]:
    with FakeUnitOfWork(store=store) as uow:
        assembly = create_assembly(
            uow=uow,
            title=f"Image Assembly {status}",
            created_by_user_id=admin.id,
            question="Test question?",
        )
        assembly_id = assembly.id

    with FakeUnitOfWork(store=store) as uow:
        page = create_registration_page_with_slugs(uow, admin.id, assembly_id, name="Registration page")
        url_slug = page.url_slug

    with FakeUnitOfWork(store=store) as uow:
        update_registration_page_html(uow, admin.id, _page_id(uow, assembly_id), MINIMAL_FORM_HTML)

    if status in ("published", "closed"):
        with FakeUnitOfWork(store=store) as uow:
            publish_registration_page(uow, admin.id, _page_id(uow, assembly_id))
    if status == "closed":
        with FakeUnitOfWork(store=store) as uow:
            close_registration_page(uow, admin.id, _page_id(uow, assembly_id))

    with FakeUnitOfWork(store=store) as uow:
        image = add_registration_image(uow, admin.id, assembly_id, _png())

    return url_slug, image


class TestServeRegistrationImage:
    def test_serves_published_image_with_headers(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, image = _seed_page_with_image(fake_store, admin_user)

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")

        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert response.data == image.data
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "immutable" in response.headers["Cache-Control"]
        assert response.get_etag()[0] == image.sha256

    def test_serves_test_mode_image(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, image = _seed_page_with_image(fake_store, admin_user, status="test")

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 200

    def test_404_for_closed_page(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, image = _seed_page_with_image(fake_store, admin_user, status="closed")

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 404

    def test_404_for_unknown_slug(self, client: FlaskClient) -> None:
        response = client.get("/register/no-such-slug/assets/deadbeef.png")
        assert response.status_code == 404

    def test_404_for_unknown_sha(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, _image = _seed_page_with_image(fake_store, admin_user)

        response = client.get(f"/register/{url_slug}/assets/0000000000000000.png")
        assert response.status_code == 404

    def test_304_with_matching_etag(self, client: FlaskClient, fake_store, admin_user: User) -> None:
        url_slug, image = _seed_page_with_image(fake_store, admin_user)

        response = client.get(
            f"/register/{url_slug}/assets/{image.sha256}.png",
            headers={"If-None-Match": f'"{image.sha256}"'},
        )
        assert response.status_code == 304

    def test_404_when_feature_disabled(self, client: FlaskClient, fake_store, admin_user: User, monkeypatch) -> None:
        url_slug, image = _seed_page_with_image(fake_store, admin_user)
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "false")
        reload_flags()

        response = client.get(f"/register/{url_slug}/assets/{image.sha256}.png")
        assert response.status_code == 404


class TestAssetsAreSharedAcrossPages:
    def test_image_uploaded_once_serves_from_every_page_of_the_assembly(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        """Language variants share a logo, so one upload must serve from all of them."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(
                uow=uow,
                title="Shared Asset Assembly",
                created_by_user_id=admin_user.id,
                question="Test question?",
            )
            assembly_id = assembly.id

        slugs = []
        for name, language in (("English", "en"), ("Espanol", "es")):
            with FakeUnitOfWork(store=fake_store) as uow:
                page = create_registration_page_with_slugs(
                    uow, admin_user.id, assembly_id, name=name, language=language
                )
                slugs.append(page.url_slug)
            with FakeUnitOfWork(store=fake_store) as uow:
                update_registration_page_html(uow, admin_user.id, page.id, MINIMAL_FORM_HTML)
            with FakeUnitOfWork(store=fake_store) as uow:
                publish_registration_page(uow, admin_user.id, page.id)

        with FakeUnitOfWork(store=fake_store) as uow:
            image = add_registration_image(uow, admin_user.id, assembly_id, _png())

        for slug in slugs:
            response = client.get(f"/register/{slug}/assets/{image.sha256}.png")
            assert response.status_code == 200, f"image not served from {slug}"

    def test_image_does_not_serve_from_another_assembly(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        owning_slug, image = _seed_page_with_image(fake_store, admin_user, status="published")

        with FakeUnitOfWork(store=fake_store) as uow:
            other = create_assembly(
                uow=uow,
                title="Unrelated Assembly",
                created_by_user_id=admin_user.id,
                question="Test question?",
            )
            other_id = other.id
        with FakeUnitOfWork(store=fake_store) as uow:
            other_page = create_registration_page_with_slugs(uow, admin_user.id, other_id, name="Registration page")
        with FakeUnitOfWork(store=fake_store) as uow:
            update_registration_page_html(uow, admin_user.id, other_page.id, MINIMAL_FORM_HTML)
        with FakeUnitOfWork(store=fake_store) as uow:
            publish_registration_page(uow, admin_user.id, other_page.id)

        assert client.get(f"/register/{owning_slug}/assets/{image.sha256}.png").status_code == 200
        assert client.get(f"/register/{other_page.url_slug}/assets/{image.sha256}.png").status_code == 404
