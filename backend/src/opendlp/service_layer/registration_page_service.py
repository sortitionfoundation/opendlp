"""ABOUTME: Service layer for registration page management and public lookup
ABOUTME: Create/edit/publish the page in the backoffice, and resolve it for the public route"""

import random
import re
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


# --- Slug generation utilities ---


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug: lowercase, hyphens, no special chars."""
    # Lowercase and replace spaces/underscores with hyphens
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    # Remove apostrophes and similar characters completely
    text = re.sub(r"[''`]", "", text)
    # Remove any character that isn't alphanumeric or hyphen
    text = re.sub(r"[^a-z0-9-]", "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    return text


def generate_url_slug_from_name(name: str, max_length: int = 25) -> str:
    """Generate a URL slug from assembly name.

    Takes first N words that fit within max_length characters.
    Returns empty string if name produces no valid slug chars.
    """
    slug = _slugify(name)
    if not slug:
        return ""

    # Split into words by hyphen
    words = slug.split("-")
    result_words: list[str] = []
    current_length = 0

    for word in words:
        # Account for hyphen separator (except first word)
        separator_len = 1 if result_words else 0
        new_length = current_length + separator_len + len(word)

        if new_length > max_length:
            # If we have no words yet and first word is too long, truncate it
            if not result_words:
                result_words.append(word[:max_length])
            break

        result_words.append(word)
        current_length = new_length

    return "-".join(result_words)


def generate_unique_url_slug(uow: AbstractUnitOfWork, base_slug: str) -> str:
    """Ensure slug is unique, appending -2, -3, etc. if needed.

    If base_slug is empty, generates a random fallback slug.
    """
    if not base_slug:
        base_slug = f"assembly-{random.randint(100000, 999999)}"  # noqa: S311

    # Check if base slug is available
    if uow.registration_pages.get_by_url_slug(base_slug) is None:
        return base_slug

    # Try with numeric suffix
    for i in range(2, 100):
        candidate = f"{base_slug}-{i}"
        if uow.registration_pages.get_by_url_slug(candidate) is None:
            return candidate

    # Fallback: append random suffix
    return f"{base_slug}-{random.randint(1000, 9999)}"  # noqa: S311


def generate_short_url_slug() -> str:
    """Generate a random 6-digit numeric string."""
    return str(random.randint(100000, 999999))  # noqa: S311


def generate_unique_short_url_slug(uow: AbstractUnitOfWork, max_attempts: int = 10) -> str:
    """Generate unique 6-digit short slug, retrying on collision."""
    for _ in range(max_attempts):
        candidate = generate_short_url_slug()
        if uow.registration_pages.get_by_short_url_slug(candidate) is None:
            return candidate

    # Very unlikely to reach here, but handle it
    raise ValueError("Failed to generate unique short URL slug after multiple attempts")


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


def create_registration_page_with_slugs(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> RegistrationPage:
    """Create a registration page with auto-generated slugs from the assembly name.

    The url_slug is generated from the assembly title (first N words, max 25 chars).
    The short_url_slug is a random 6-digit number.
    Both are ensured to be unique.

    Raises ValueError if the assembly already has a registration page.
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create registration page", required_role=_MANAGE_ROLE)
        if uow.registration_pages.get_by_assembly_id(assembly_id):
            raise ValueError(f"Assembly {assembly_id} already has a registration page")

        # Generate unique slugs
        base_slug = generate_url_slug_from_name(assembly.title)
        url_slug = generate_unique_url_slug(uow, base_slug)
        short_url_slug = generate_unique_short_url_slug(uow)

        page = RegistrationPage(
            assembly_id=assembly_id,
            source_type=RegistrationPageSource.HTML,
            thank_you_html=DEFAULT_THANK_YOU_HTML,
            url_slug=url_slug,
            short_url_slug=short_url_slug,
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

    LIVE        — render the form (status PUBLISHED); submissions go to the pool.
    TEST        — render the form with a test-page banner (status TEST);
                  submissions are recorded as test submissions.
    CLOSED      — 302 to /registration-closed.
    NOT_FOUND   — 404 (page absent).
    """

    LIVE = "LIVE"
    TEST = "TEST"
    CLOSED = "CLOSED"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class RegistrationPageVisibility:
    """The outcome of resolving whether a page should be shown to a public visitor."""

    page: RegistrationPage | None
    state: RegistrationPageVisibilityState

    @property
    def is_visible(self) -> bool:
        return self.state in (RegistrationPageVisibilityState.LIVE, RegistrationPageVisibilityState.TEST)

    @property
    def is_test(self) -> bool:
        return self.state == RegistrationPageVisibilityState.TEST


def resolve_visibility(page: RegistrationPage | None) -> RegistrationPageVisibility:
    """Pure decision: which public-route response does this page deserve?"""
    if page is None:
        return RegistrationPageVisibility(page=None, state=RegistrationPageVisibilityState.NOT_FOUND)
    if not page.url_slug:
        # A page with no canonical slug cannot be rendered at /register/<slug>;
        # treat it as not found regardless of status (a freshly created page is
        # TEST with an empty slug until a manager sets one).
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.NOT_FOUND)
    if page.status == RegistrationPageStatus.PUBLISHED:
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.LIVE)
    if page.status == RegistrationPageStatus.TEST:
        return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.TEST)
    return RegistrationPageVisibility(page=page, state=RegistrationPageVisibilityState.CLOSED)


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
