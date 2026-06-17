"""ABOUTME: Service layer for registration image upload, listing, deletion and serving
ABOUTME: Validates and stores images, builds <img> snippets, resolves images for the public route"""

import uuid
from collections.abc import Callable

from opendlp.config import (
    get_max_image_upload_bytes,
    get_max_images_per_registration_page,
    get_registration_image_max_edge_px,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_image import (
    RegistrationImage,
    generate_image_html,
    sanitise_original_filename,
)
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.users import User

from .exceptions import (
    AssemblyNotFoundError,
    ImageQuotaExceeded,
    InsufficientPermissions,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from .image_processing import process_image
from .permissions import can_manage_assembly, can_view_assembly
from .unit_of_work import AbstractUnitOfWork

_MANAGE_ROLE = "assembly-manager, global-organiser or admin"
_VIEW_ROLE = "assembly role or global privileges"


def _load_user_and_assembly(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> tuple[User, Assembly]:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return user, assembly


def _load_page(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> RegistrationPage:
    page = uow.registration_pages.get_by_assembly_id(assembly_id)
    if not page:
        raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")
    return page


def add_registration_image(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    raw: bytes,
    alt: str = "",
    original_filename: str = "",
) -> RegistrationImage:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="add registration image", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)

        processed = process_image(
            raw,
            max_bytes=get_max_image_upload_bytes(),
            max_edge_px=get_registration_image_max_edge_px(),
        )
        # Content-addressed dedup: identical bytes on a page collapse to one row.
        # The first upload's alt text and original filename are kept; change the alt
        # via set_registration_image_alt.
        existing = uow.registration_images.get_by_page_and_sha(page.id, processed.sha256)
        if existing is not None:
            return existing.create_detached_copy()

        limit = get_max_images_per_registration_page()
        if uow.registration_images.count_by_page_id(page.id) >= limit:
            raise ImageQuotaExceeded(limit)

        image = RegistrationImage.from_processed(
            page.id,
            processed,
            created_by=user.id,
            alt=alt,
            original_filename=sanitise_original_filename(original_filename),
        )
        uow.registration_images.add(image)
        page.record_edit(user.id, "Added a registration image")
        uow.commit()
        return image.create_detached_copy()


def list_registration_images(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[RegistrationImage]:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view registration images", required_role=_VIEW_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            return []
        return [image.create_detached_copy() for image in uow.registration_images.list_by_page_id(page.id)]


def delete_registration_image(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, image_id: uuid.UUID
) -> None:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="delete registration image", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)
        image = uow.registration_images.get(image_id)
        if image is None or image.registration_page_id != page.id:
            raise RegistrationImageNotFoundError(f"Image {image_id} not found for this registration page")
        uow.registration_images.delete(image)
        page.record_edit(user.id, "Deleted a registration image")
        uow.commit()


def set_registration_image_alt(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, image_id: uuid.UUID, alt: str
) -> RegistrationImage:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="edit registration image", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)
        image: RegistrationImage | None = uow.registration_images.get(image_id)
        if image is None or image.registration_page_id != page.id:
            raise RegistrationImageNotFoundError(f"Image {image_id} not found for this registration page")
        image.alt = alt
        page.record_edit(user.id, "Updated a registration image caption")
        uow.commit()
        return image.create_detached_copy()


def list_image_snippets(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    url_for_image: Callable[[RegistrationImage], str],
) -> list[tuple[RegistrationImage, str]]:
    images = list_registration_images(uow, user_id, assembly_id)
    return [(image, generate_image_html(url_for_image(image), alt=image.alt)) for image in images]


def get_registration_image_for_serving(
    uow: AbstractUnitOfWork, url_slug: str, image_name: str
) -> RegistrationImage | None:
    sha256 = image_name.rsplit(".", 1)[0]
    with uow:
        page = uow.registration_pages.get_by_url_slug(url_slug)
        if page is None or not page.is_publicly_loadable():
            return None
        image = uow.registration_images.get_by_page_and_sha(page.id, sha256)
        return image.create_detached_copy() if image else None
