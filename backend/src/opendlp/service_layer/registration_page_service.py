"""ABOUTME: Service layer for registration page management and public lookup
ABOUTME: Create/edit/publish the page in the backoffice, and resolve it for the public route"""

import uuid
from dataclasses import dataclass
from enum import Enum

from opendlp.config import get_registration_form_html_max_bytes, get_registration_thank_you_html_max_bytes
from opendlp.domain.registration_page import (
    DEFAULT_THANK_YOU_HTML,
    HtmlSource,
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageSource,
    RegistrationPageStatus,
)
from opendlp.domain.registration_page import generate_starter_form_html as _build_starter_html

from .exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
    SlugError,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly
from .unit_of_work import AbstractUnitOfWork

_MANAGE_ROLE = "assembly-manager, global-organiser or admin"
_VIEW_ROLE = "assembly role or global privileges"


def _load_user_and_assembly(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return user, assembly


def _load_html_source(uow: AbstractUnitOfWork, page: RegistrationPage) -> RegistrationPageHtml:
    source = uow.registration_page_html_sources.get_by_page_id(page.id)
    if source is None:
        raise RegistrationPageNotFoundError(f"Registration page {page.id} has no HTML source")
    return source


def _check_size(html: str, max_bytes: int, label: str) -> None:
    size = len(html.encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"The {label} must be at most {max_bytes} bytes; got {size}")


def create_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    source_type: RegistrationPageSource = RegistrationPageSource.HTML,
) -> RegistrationPage:
    """Create a registration page and its HTML source for an assembly.

    Raises ValueError if the assembly already has a registration page.
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create registration page", required_role=_MANAGE_ROLE)
        if uow.registration_pages.get_by_assembly_id(assembly_id):
            raise ValueError(f"Assembly {assembly_id} already has a registration page")

        page = RegistrationPage(
            assembly_id=assembly_id,
            source_type=source_type,
            thank_you_html=DEFAULT_THANK_YOU_HTML,
        )
        page.record_create(user.id)
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(RegistrationPageHtml(registration_page_id=page.id))
        uow.commit()
        return page.create_detached_copy()


def get_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> RegistrationPage | None:
    """Return the assembly's registration page, or None if it has none."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view registration page", required_role=_VIEW_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        return page.create_detached_copy() if page else None


def get_registration_page_with_source(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> tuple[RegistrationPage, HtmlSource] | None:
    """Return the page and its active HTML source, or None if the page is not created."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view registration page", required_role=_VIEW_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            return None
        source = _load_html_source(uow, page)
        return page.create_detached_copy(), source.create_detached_copy()


def _describe_slug_change(field: str, before: str, after: str) -> str:
    if after == "":
        return f"Cleared {field} (was '{before}')"
    if before == "":
        return f"Set {field} to '{after}'"
    return f"Changed {field} from '{before}' to '{after}'"


def update_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    url_slug: str | None = None,
    short_url_slug: str | None = None,
) -> RegistrationPage:
    """Update the page's URL slugs. Raises if a slug is taken or the page has been published."""
    url_slug = url_slug.strip() if url_slug is not None else None
    short_url_slug = short_url_slug.strip() if short_url_slug is not None else None
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="update registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        if url_slug:
            clash = uow.registration_pages.get_by_url_slug(url_slug)
            if clash and clash.id != page.id:
                raise SlugError(
                    field="url_slug",
                    reason="taken",
                    message=f"The slug '{url_slug}' is already in use by another registration page",
                )
        if short_url_slug:
            clash = uow.registration_pages.get_by_short_url_slug(short_url_slug)
            if clash and clash.id != page.id:
                raise SlugError(
                    field="short_url_slug",
                    reason="taken",
                    message=f"The slug '{short_url_slug}' is already in use by another registration page",
                )

        before_url = page.url_slug
        before_short = page.short_url_slug
        page.update_slugs(url_slug=url_slug, short_url_slug=short_url_slug)

        changes: list[str] = []
        if url_slug is not None and page.url_slug != before_url:
            changes.append(_describe_slug_change("url_slug", before_url, page.url_slug))
        if short_url_slug is not None and page.short_url_slug != before_short:
            changes.append(_describe_slug_change("short_url_slug", before_short, page.short_url_slug))
        if changes:
            page.record_edit(user.id, "; ".join(changes))

        uow.commit()
        return page.create_detached_copy()


def update_thank_you_html(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, thank_you_html: str
) -> RegistrationPage:
    """Update the page's thank-you HTML. Raises ValueError if it exceeds the size limit."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="update registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        _check_size(thank_you_html, get_registration_thank_you_html_max_bytes(), "thank-you HTML")
        if page.thank_you_html != thank_you_html:
            page.update_thank_you_html(thank_you_html)
            page.record_edit(user.id, "Updated thank-you HTML")
        uow.commit()
        return page.create_detached_copy()


def update_registration_page_html(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, form_html: str
) -> RegistrationPageHtml:
    """Update the page's form HTML. Raises ValueError if it exceeds the size limit."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="update registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        _check_size(form_html, get_registration_form_html_max_bytes(), "form HTML")
        source = _load_html_source(uow, page)
        if source.form_html != form_html:
            source.update_html(form_html)
            page.record_edit(user.id, "Updated form HTML")
        uow.commit()
        return source.create_detached_copy()


def publish_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Publish the page. Raises RegistrationPageNotReady if it is not ready."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="publish registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        page.publish(_load_html_source(uow, page), author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def unpublish_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Move the page back to draft. Used for 'I made a mistake, want to fix and republish'."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="unpublish registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        page.unpublish(author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def close_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Close the page (registration period over)."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="close registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        page.close(author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def reopen_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Reopen a closed page. Runs the same readiness check as publish."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="reopen registration page", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        page.reopen(_load_html_source(uow, page), author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def regenerate_preview_token(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> RegistrationPage:
    """Rotate the page's preview token."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="regenerate preview token", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        page.regenerate_preview_token(author_id=user.id)
        uow.commit()
        return page.create_detached_copy()


def find_registration_page_by_url_slug(uow: AbstractUnitOfWork, url_slug: str) -> RegistrationPage | None:
    """Public lookup for the canonical /register/<url_slug> route. No auth."""
    with uow:
        page = uow.registration_pages.get_by_url_slug(url_slug)
        return page.create_detached_copy() if page else None


def find_registration_page_by_short_url_slug(uow: AbstractUnitOfWork, short_url_slug: str) -> RegistrationPage | None:
    """Public lookup for the /r/<short_url_slug> route. No auth."""
    with uow:
        page = uow.registration_pages.get_by_short_url_slug(short_url_slug)
        return page.create_detached_copy() if page else None


class RegistrationPageVisibilityState(Enum):
    """Public-route response classification.

    LIVE        — render the form (status PUBLISHED).
    PREVIEW     — render the form with a preview banner (DRAFT or CLOSED + valid token).
    CLOSED      — 302 to /registration-closed.
    NOT_FOUND   — 404 (page absent, or DRAFT without a valid preview token).
    """

    LIVE = "LIVE"
    PREVIEW = "PREVIEW"
    CLOSED = "CLOSED"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class RegistrationPageVisibility:
    """The outcome of resolving whether a page should be shown to a public visitor."""

    page: RegistrationPage | None
    state: RegistrationPageVisibilityState

    @property
    def is_visible(self) -> bool:
        return self.state in (RegistrationPageVisibilityState.LIVE, RegistrationPageVisibilityState.PREVIEW)

    @property
    def is_preview(self) -> bool:
        return self.state == RegistrationPageVisibilityState.PREVIEW


def resolve_visibility(page: RegistrationPage | None, preview_token: str = "") -> RegistrationPageVisibility:
    """Pure decision: which public-route response does this page deserve?"""
    if page is None:
        return RegistrationPageVisibility(page=None, state=RegistrationPageVisibilityState.NOT_FOUND)
    if page.status == RegistrationPageStatus.PUBLISHED:
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.LIVE)
    if preview_token and preview_token == page.preview_token:
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.PREVIEW)
    if page.status == RegistrationPageStatus.CLOSED:
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.CLOSED)
    return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.NOT_FOUND)


def get_page_and_source_for_render(uow: AbstractUnitOfWork, page: RegistrationPage) -> HtmlSource:
    """Load the active HTML source for a page that has already been resolved as visible."""
    with uow:
        return _load_html_source(uow, page).create_detached_copy()


def render_thank_you_html(page: RegistrationPage) -> str:
    """Return the thank-you HTML. Verbatim in v1 - a seam for later substitution."""
    return page.thank_you_html


def generate_starter_form_html(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> str:
    """Generate an unstyled starter HTML form from the assembly's respondent field schema."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="generate starter HTML", required_role=_MANAGE_ROLE)
        fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
        return _build_starter_html(list(fields))
