"""ABOUTME: Unit tests for the registration image service layer
ABOUTME: Covers add/list/delete, quota, dedup, snippet building and public serving"""

import uuid
from io import BytesIO

import pytest
from PIL import Image

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_image import ImageValidationError, RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageAction, RegistrationPageStatus
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import registration_image_service as service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    ImageQuotaExceeded,
    InsufficientPermissions,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.image_processing import process_image
from tests.fakes import FakeUnitOfWork

_BIG = 10 * 1024 * 1024
_EDGE = 2048


def _png(color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _admin(uow: FakeUnitOfWork) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def _assembly(uow: FakeUnitOfWork) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    return assembly


def _viewer(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"viewer-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


def _page(
    uow: FakeUnitOfWork,
    assembly: Assembly,
    *,
    url_slug: str = "a-page",
    status: RegistrationPageStatus = RegistrationPageStatus.PUBLISHED,
) -> RegistrationPage:
    page = RegistrationPage(assembly_id=assembly.id, url_slug=url_slug, status=status)
    uow.registration_pages.add(page)
    return page


def _stored_image(uow: FakeUnitOfWork, page: RegistrationPage, color=(255, 0, 0)) -> RegistrationImage:
    processed = process_image(_png(color), max_bytes=_BIG, max_edge_px=_EDGE)
    image = RegistrationImage.from_processed(page.id, processed)
    uow.registration_images.add(image)
    return image


class TestAddRegistrationImage:
    def test_stores_returns_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        image = service.add_registration_image(uow, admin.id, assembly.id, _png())

        assert isinstance(image, RegistrationImage)
        assert uow.registration_images.count_by_page_id(page.id) == 1
        assert uow.committed
        assert page.activity[-1].action == RegistrationPageAction.EDIT
        assert page.activity[-1].text == "Added a registration image"

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        _page(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.add_registration_image(uow, viewer.id, assembly.id, _png())

    def test_no_page_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.add_registration_image(uow, admin.id, assembly.id, _png())

    def test_unknown_user_raises(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)

        with pytest.raises(UserNotFoundError):
            service.add_registration_image(uow, uuid.uuid4(), assembly.id, _png())

    def test_unknown_assembly_raises(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        with pytest.raises(AssemblyNotFoundError):
            service.add_registration_image(uow, admin.id, uuid.uuid4(), _png())

    def test_invalid_image_propagates(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(ImageValidationError):
            service.add_registration_image(uow, admin.id, assembly.id, b"not an image")

    def test_stores_alt_text(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        image = service.add_registration_image(uow, admin.id, assembly.id, _png(), alt="A red square")

        assert image.alt == "A red square"

    def test_dedup_keeps_first_alt(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_image(uow, admin.id, assembly.id, _png(), alt="First caption")
        second = service.add_registration_image(uow, admin.id, assembly.id, _png(), alt="Second caption")

        assert second.alt == "First caption"

    def test_stores_original_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        image = service.add_registration_image(
            uow, admin.id, assembly.id, _png(), alt="A red square", original_filename="red square.png"
        )

        assert image.original_filename == "red square.png"

    def test_sanitises_original_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        image = service.add_registration_image(
            uow, admin.id, assembly.id, _png(), alt="A red square", original_filename="/home/user/red square.png"
        )

        assert image.original_filename == "red square.png"

    def test_dedup_keeps_first_original_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_image(uow, admin.id, assembly.id, _png(), alt="x", original_filename="first.png")
        second = service.add_registration_image(
            uow, admin.id, assembly.id, _png(), alt="x", original_filename="second.png"
        )

        assert second.original_filename == "first.png"

    def test_dedup_returns_existing_without_new_row_or_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        first = service.add_registration_image(uow, admin.id, assembly.id, _png())
        activity_len = len(page.activity)
        second = service.add_registration_image(uow, admin.id, assembly.id, _png())

        assert second.id == first.id
        assert uow.registration_images.count_by_page_id(page.id) == 1
        assert len(page.activity) == activity_len

    def test_quota_at_limit_raises(self, monkeypatch):
        monkeypatch.setenv("MAX_IMAGES_PER_REGISTRATION_PAGE", "1")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_image(uow, admin.id, assembly.id, _png((255, 0, 0)))
        with pytest.raises(ImageQuotaExceeded):
            service.add_registration_image(uow, admin.id, assembly.id, _png((0, 0, 255)))

    def test_dedup_at_limit_still_succeeds(self, monkeypatch):
        monkeypatch.setenv("MAX_IMAGES_PER_REGISTRATION_PAGE", "1")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        first = service.add_registration_image(uow, admin.id, assembly.id, _png())
        again = service.add_registration_image(uow, admin.id, assembly.id, _png())
        assert again.id == first.id
        assert uow.registration_images.count_by_page_id(page.id) == 1


class TestListRegistrationImages:
    def test_lists_only_that_pages_images(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        _stored_image(uow, page, (255, 0, 0))
        _stored_image(uow, page, (0, 255, 0))

        listed = service.list_registration_images(uow, admin.id, assembly.id)
        assert len(listed) == 2

    def test_empty_when_no_page(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        assert service.list_registration_images(uow, admin.id, assembly.id) == []

    def test_permission_denied_for_stranger(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        stranger = User(email=f"x-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(stranger)
        _page(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.list_registration_images(uow, stranger.id, assembly.id)


class TestDeleteRegistrationImage:
    def test_deletes_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        image = _stored_image(uow, page)

        service.delete_registration_image(uow, admin.id, assembly.id, image.id)

        assert uow.registration_images.count_by_page_id(page.id) == 0
        assert page.activity[-1].text == "Deleted a registration image"

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        page = _page(uow, assembly)
        image = _stored_image(uow, page)

        with pytest.raises(InsufficientPermissions):
            service.delete_registration_image(uow, viewer.id, assembly.id, image.id)

    def test_missing_image_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(RegistrationImageNotFoundError):
            service.delete_registration_image(uow, admin.id, assembly.id, uuid.uuid4())


class TestListImageSnippets:
    def test_builds_snippet_per_image_with_builder_url(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        _stored_image(uow, page)

        snippets = service.list_image_snippets(uow, admin.id, assembly.id, lambda img: f"/x/{img.sha256}.png")
        assert len(snippets) == 1
        image, html = snippets[0]
        assert f'src="/x/{image.sha256}.png"' in html
        assert html.startswith("<img ")

    def test_snippet_includes_stored_alt(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)
        service.add_registration_image(uow, admin.id, assembly.id, _png(), alt="A red square")

        snippets = service.list_image_snippets(uow, admin.id, assembly.id, lambda img: f"/x/{img.sha256}.png")
        _, html = snippets[0]
        assert 'alt="A red square"' in html


class TestSetRegistrationImageAlt:
    def test_updates_alt_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        image = _stored_image(uow, page)

        updated = service.set_registration_image_alt(uow, admin.id, assembly.id, image.id, "New caption")

        assert updated.alt == "New caption"
        assert uow.registration_images.get(image.id).alt == "New caption"
        assert page.activity[-1].text == "Updated a registration image caption"
        assert uow.committed

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        page = _page(uow, assembly)
        image = _stored_image(uow, page)

        with pytest.raises(InsufficientPermissions):
            service.set_registration_image_alt(uow, viewer.id, assembly.id, image.id, "New caption")

    def test_missing_image_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(RegistrationImageNotFoundError):
            service.set_registration_image_alt(uow, admin.id, assembly.id, uuid.uuid4(), "New caption")


class TestGetRegistrationImageForServing:
    @pytest.mark.parametrize("status", [RegistrationPageStatus.TEST, RegistrationPageStatus.PUBLISHED])
    def test_serves_for_loadable_statuses(self, status):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="live", status=status)
        image = _stored_image(uow, page)

        served = service.get_registration_image_for_serving(uow, "live", f"{image.sha256}.png")
        assert served is not None
        assert served.id == image.id

    def test_none_when_closed(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="closed", status=RegistrationPageStatus.CLOSED)
        image = _stored_image(uow, page)

        assert service.get_registration_image_for_serving(uow, "closed", f"{image.sha256}.png") is None

    def test_none_for_unknown_slug(self):
        uow = FakeUnitOfWork()
        assert service.get_registration_image_for_serving(uow, "nope", "abc.png") is None

    def test_none_for_unknown_sha(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        _page(uow, assembly, url_slug="live")
        assert service.get_registration_image_for_serving(uow, "live", "deadbeef.png") is None

    def test_handles_missing_extension(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="live")
        image = _stored_image(uow, page)

        served = service.get_registration_image_for_serving(uow, "live", image.sha256)
        assert served is not None
