"""ABOUTME: Service layer for registration page management and public lookup
ABOUTME: Create/edit/publish the page in the backoffice, and resolve it for the public route"""

import random
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from opendlp.config import get_registration_form_html_max_bytes, get_registration_thank_you_html_max_bytes
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import (
    DEFAULT_THANK_YOU_HTML,
    HtmlSource,
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageSource,
    RegistrationPageStatus,
    RenderContext,
)
from opendlp.domain.registration_page import generate_starter_form_html as _build_starter_html
from opendlp.domain.registration_page import generate_starter_form_html_govuk as _build_starter_html_govuk
from opendlp.domain.users import User

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


def page_for_assembly(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> RegistrationPage | None:
    """The assembly's oldest registration page, or None when it has none."""
    pages = uow.registration_pages.list_by_assembly_id(assembly_id)
    return pages[0] if pages else None


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
    text = re.sub(r"['`]", "", text)
    # Remove any character that isn't alphanumeric or hyphen
    text = re.sub(r"[^a-z0-9-]", "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    return text.strip("-")


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


def _load_manageable_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID
) -> tuple[User, RegistrationPage]:
    """Load a page the user may manage.

    A user who cannot even view the assembly gets the same
    RegistrationPageNotFoundError as an unknown id, so page ids cannot be probed
    to discover which assemblies exist. A user who can view the assembly already
    knows it exists, so they get the more useful InsufficientPermissions.
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    page = uow.registration_pages.get(page_id)
    if page is None:
        raise RegistrationPageNotFoundError(f"Registration page {page_id} not found")
    assembly = uow.assemblies.get(page.assembly_id)
    if assembly is None or not can_view_assembly(user, assembly):
        raise RegistrationPageNotFoundError(f"Registration page {page_id} not found")
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="manage registration page", required_role=_MANAGE_ROLE)
    return user, page


def _load_viewable_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID
) -> tuple[User, RegistrationPage]:
    """Load a page the user may view, or raise as though it did not exist."""
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    page = uow.registration_pages.get(page_id)
    if page is None:
        raise RegistrationPageNotFoundError(f"Registration page {page_id} not found")
    assembly = uow.assemblies.get(page.assembly_id)
    if assembly is None or not can_view_assembly(user, assembly):
        raise RegistrationPageNotFoundError(f"Registration page {page_id} not found")
    return user, page


def _validated_name(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, name: str) -> str:
    """Names label pages in the backoffice, so they must be present and distinct."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("The registration page name is required")
    for existing in uow.registration_pages.list_by_assembly_id(assembly_id):
        if existing.name == cleaned:
            raise ValueError(f"This assembly already has a registration page named '{cleaned}'")
    return cleaned


def create_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    name: str,
    language: str = "",
    source_type: RegistrationPageSource = RegistrationPageSource.HTML,
) -> RegistrationPage:
    """Create a registration page and its HTML source for an assembly."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create registration page", required_role=_MANAGE_ROLE)

        page = RegistrationPage(
            assembly_id=assembly_id,
            source_type=source_type,
            thank_you_html=DEFAULT_THANK_YOU_HTML,
            name=_validated_name(uow, assembly_id, name),
            language=language,
        )
        page.record_create(user.id)
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(RegistrationPageHtml(registration_page_id=page.id))
        uow.commit()
        return page.create_detached_copy()


def _generated_url_slug(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, assembly_title: str, name: str, language: str
) -> str:
    """Build a unique slug from the assembly title plus a suffix identifying the page.

    A language code always earns its place in the URL, and is preferred over the
    page name because _slugify strips non-ASCII - "Cestina" survives, "Čeština"
    becomes "etina". Without a language, an assembly's first page takes the base
    slug bare so a lone page keeps a clean URL; later pages are variants, so
    their name becomes the suffix, which reads far better than the numeric
    fallback. A clash with a different assembly still falls back to the number -
    that assembly's page names mean nothing here.
    """
    base = generate_url_slug_from_name(assembly_title)
    suffix = _slugify(language)
    if not suffix and uow.registration_pages.list_by_assembly_id(assembly_id):
        suffix = _slugify(name)
    if suffix:
        base = f"{base}-{suffix}" if base else suffix
    return generate_unique_url_slug(uow, base)


def create_registration_page_with_slugs(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    name: str,
    language: str = "",
) -> RegistrationPage:
    """Create a registration page with slugs generated from the assembly and page names.

    The url_slug combines the assembly title with a suffix identifying the page,
    then gains a numeric suffix if that is taken. The short_url_slug is a random
    6-digit number.
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create registration page", required_role=_MANAGE_ROLE)
        validated_name = _validated_name(uow, assembly_id, name)

        url_slug = _generated_url_slug(uow, assembly.id, assembly.title, validated_name, language)
        short_url_slug = generate_unique_short_url_slug(uow)

        page = RegistrationPage(
            assembly_id=assembly_id,
            source_type=RegistrationPageSource.HTML,
            thank_you_html=DEFAULT_THANK_YOU_HTML,
            url_slug=url_slug,
            short_url_slug=short_url_slug,
            name=validated_name,
            language=language,
        )
        page.record_create(user.id)
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(RegistrationPageHtml(registration_page_id=page.id))
        uow.commit()
        return page.create_detached_copy()


def duplicate_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    source_page_id: uuid.UUID,
    *,
    name: str,
    language: str = "",
) -> RegistrationPage:
    """Copy a page's content into a fresh TEST page with its own slugs.

    The auto-reply email template is deep-copied rather than shared, so editing
    one variant's auto-reply can never rewrite another's.
    """
    with uow:
        user, source = _load_manageable_page(uow, user_id, source_page_id)
        assembly = uow.assemblies.get(source.assembly_id)
        if assembly is None:
            raise AssemblyNotFoundError(f"Assembly {source.assembly_id} not found")
        validated_name = _validated_name(uow, source.assembly_id, name)

        page = RegistrationPage(
            assembly_id=source.assembly_id,
            source_type=source.source_type,
            thank_you_html=source.thank_you_html,
            url_slug=_generated_url_slug(uow, assembly.id, assembly.title, validated_name, language),
            short_url_slug=generate_unique_short_url_slug(uow),
            name=validated_name,
            language=language,
            auto_reply_email_template_id=_copy_auto_reply_template(uow, source, validated_name),
        )
        page.record_create(user.id)
        page.activity[-1] = replace(page.activity[-1], text=f"Registration page copied from '{source.name}'")
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(
            RegistrationPageHtml(
                registration_page_id=page.id,
                form_html=_load_html_source(uow, source).form_html,
            )
        )
        uow.commit()
        return page.create_detached_copy()


def _copy_auto_reply_template(uow: AbstractUnitOfWork, source: RegistrationPage, page_name: str) -> uuid.UUID | None:
    """Give the copy its own template row, so the two never share mutable content."""
    if source.auto_reply_email_template_id is None:
        return None
    original = uow.email_templates.get(source.auto_reply_email_template_id)
    if original is None:
        return None
    copy = EmailTemplate(
        assembly_id=original.assembly_id,
        name=f"{original.name} ({page_name})",
        subject=original.subject,
        body_html=original.body_html,
    )
    uow.email_templates.add(copy)
    return copy.id


def delete_registration_page(uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID) -> None:
    """Delete a page that was never published and has no registrations.

    A published page keeps its row so the slugs on invites and QR codes still
    resolve; close it instead. A page in TEST can still have collected test
    submissions, which are equally worth keeping the row for.
    """
    with uow:
        _user, page = _load_manageable_page(uow, user_id, page_id)
        if not page.can_be_deleted():
            raise ValueError("A registration page that has been published cannot be deleted; close it instead")
        if uow.respondents.count_by_registration_page(page.assembly_id).get(page.id):
            raise ValueError("This registration page has registrations, so it cannot be deleted")

        source = uow.registration_page_html_sources.get_by_page_id(page.id)
        if source is not None:
            uow.registration_page_html_sources.delete(source)
        uow.registration_pages.delete(page)
        uow.commit()


def list_registration_pages(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[RegistrationPage]:
    """Return every registration page for an assembly, oldest first."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view registration pages", required_role=_VIEW_ROLE)
        return [page.create_detached_copy() for page in uow.registration_pages.list_by_assembly_id(assembly_id)]


def get_registration_page(uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID) -> RegistrationPage:
    """Return one registration page by its id."""
    with uow:
        _user, page = _load_viewable_page(uow, user_id, page_id)
        return page.create_detached_copy()


def get_registration_page_with_source(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID
) -> tuple[RegistrationPage, HtmlSource]:
    """Return one page and its active HTML source."""
    with uow:
        _user, page = _load_viewable_page(uow, user_id, page_id)
        source = _load_html_source(uow, page)
        return page.create_detached_copy(), source.create_detached_copy()


def _describe_slug_change(field: str, before: str, after: str) -> str:
    if after == "":
        return f"Cleared {field} (was '{before}')"
    if before == "":
        return f"Set {field} to '{after}'"
    return f"Changed {field} from '{before}' to '{after}'"


def _raise_if_slug_taken(
    uow: AbstractUnitOfWork,
    page_id: uuid.UUID,
    *,
    url_slug: str | None,
    short_url_slug: str | None,
) -> None:
    if url_slug:
        clash = uow.registration_pages.get_by_url_slug(url_slug)
        if clash and clash.id != page_id:
            raise SlugError(
                field="url_slug",
                reason="taken",
                message=f"The slug '{url_slug}' is already in use by another registration page",
            )
    if short_url_slug:
        clash = uow.registration_pages.get_by_short_url_slug(short_url_slug)
        if clash and clash.id != page_id:
            raise SlugError(
                field="short_url_slug",
                reason="taken",
                message=f"The slug '{short_url_slug}' is already in use by another registration page",
            )


def update_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    page_id: uuid.UUID,
    *,
    url_slug: str | None = None,
    short_url_slug: str | None = None,
) -> RegistrationPage:
    """Update the page's URL slugs. Raises if a slug is taken or the page has been published."""
    url_slug = url_slug.strip() if url_slug is not None else None
    short_url_slug = short_url_slug.strip() if short_url_slug is not None else None
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)

        _raise_if_slug_taken(uow, page.id, url_slug=url_slug, short_url_slug=short_url_slug)

        # Treat "value matches what's already stored" as a no-op so that callers
        # who resubmit the current slugs alongside other edits don't get an error
        # when slugs are frozen.
        url_slug_changed = url_slug is not None and url_slug != page.url_slug
        short_changed = short_url_slug is not None and short_url_slug != page.short_url_slug
        if url_slug_changed or short_changed:
            before_url = page.url_slug
            before_short = page.short_url_slug
            page.update_slugs(
                url_slug=url_slug if url_slug_changed else None,
                short_url_slug=short_url_slug if short_changed else None,
            )

            changes: list[str] = []
            if url_slug_changed:
                changes.append(_describe_slug_change("url_slug", before_url, page.url_slug))
            if short_changed:
                changes.append(_describe_slug_change("short_url_slug", before_short, page.short_url_slug))
            if changes:
                page.record_edit(user.id, "; ".join(changes))

        uow.commit()
        return page.create_detached_copy()


def rename_registration_page(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    page_id: uuid.UUID,
    *,
    name: str | None = None,
    language: str | None = None,
) -> RegistrationPage:
    """Update the page's backoffice label and language."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)
        changes: list[str] = []
        if name is not None and name.strip() != page.name:
            cleaned = name.strip()
            if not cleaned:
                raise ValueError("The registration page name is required")
            for existing in uow.registration_pages.list_by_assembly_id(page.assembly_id):
                if existing.id != page.id and existing.name == cleaned:
                    raise ValueError(f"This assembly already has a registration page named '{cleaned}'")
            changes.append(f"Renamed from '{page.name}' to '{cleaned}'")
            page.rename(cleaned)
        if language is not None and language.strip() != page.language:
            changes.append(f"Set language to '{language.strip()}'")
            page.set_language(language)
        if changes:
            page.record_edit(user.id, "; ".join(changes))
        uow.commit()
        return page.create_detached_copy()


def set_auto_reply_template(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, template_id: uuid.UUID | None
) -> RegistrationPage:
    """Assign (or clear, with None) the page's auto-reply email template."""
    with uow:
        _user, page = _load_manageable_page(uow, user_id, page_id)
        page.set_auto_reply_template(template_id)
        uow.commit()
        return page.create_detached_copy()


def update_thank_you_html(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, thank_you_html: str
) -> RegistrationPage:
    """Update the page's thank-you HTML. Raises ValueError if it exceeds the size limit."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)

        _check_size(thank_you_html, get_registration_thank_you_html_max_bytes(), "thank-you HTML")
        if page.thank_you_html != thank_you_html:
            page.update_thank_you_html(thank_you_html)
            page.record_edit(user.id, "Updated thank-you HTML")
        uow.commit()
        return page.create_detached_copy()


def update_registration_page_html(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, form_html: str
) -> RegistrationPageHtml:
    """Update the page's form HTML. Raises ValueError if it exceeds the size limit."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)

        _check_size(form_html, get_registration_form_html_max_bytes(), "form HTML")
        source = _load_html_source(uow, page)
        if source.form_html != form_html:
            source.update_html(form_html)
            page.record_edit(user.id, "Updated form HTML")
        uow.commit()
        return source.create_detached_copy()


def publish_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Publish the page. Raises RegistrationPageNotReady if it is not ready."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)
        page.publish(_load_html_source(uow, page), author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def unpublish_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Move the page back to draft. Used for 'I made a mistake, want to fix and republish'."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)
        page.unpublish(author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def close_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Close the page (registration period over)."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)
        page.close(author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


def reopen_registration_page(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, page_id: uuid.UUID, text: str = ""
) -> RegistrationPage:
    """Reopen a closed page. Runs the same readiness check as publish."""
    with uow:
        user, page = _load_manageable_page(uow, user_id, page_id)
        page.reopen(_load_html_source(uow, page), author_id=user.id, text=text)
        uow.commit()
        return page.create_detached_copy()


class BulkStatusOutcome(Enum):
    """What a bulk status change did to one page.

    MOVED transitioned. SKIPPED was already in the target state, or was not in a
    state the transition applies from. FAILED tried and was refused, carrying the
    readiness problems that explain why.
    """

    MOVED = "MOVED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BulkStatusResult:
    """One page's outcome from a bulk status change.

    ``page_name`` travels with the result so callers can name the pages that did
    not move without a second lookup.
    """

    page_id: uuid.UUID
    page_name: str
    outcome: BulkStatusOutcome
    problems: list[str] = field(default_factory=list)


_BULK_TEXT = "Changed as part of a bulk status update"


def _bulk_publish_one(uow: AbstractUnitOfWork, page: RegistrationPage, user_id: uuid.UUID) -> BulkStatusResult:
    if page.status is RegistrationPageStatus.PUBLISHED:
        return BulkStatusResult(page.id, page.name, BulkStatusOutcome.SKIPPED)
    source = _load_html_source(uow, page)
    problems = page.readiness_problems(source)
    if problems:
        return BulkStatusResult(page.id, page.name, BulkStatusOutcome.FAILED, problems)
    if page.status is RegistrationPageStatus.CLOSED:
        page.reopen(source, author_id=user_id, text=_BULK_TEXT)
    else:
        page.publish(source, author_id=user_id, text=_BULK_TEXT)
    return BulkStatusResult(page.id, page.name, BulkStatusOutcome.MOVED)


def _bulk_unpublish_one(_uow: AbstractUnitOfWork, page: RegistrationPage, user_id: uuid.UUID) -> BulkStatusResult:
    if page.status is not RegistrationPageStatus.PUBLISHED:
        return BulkStatusResult(page.id, page.name, BulkStatusOutcome.SKIPPED)
    page.unpublish(author_id=user_id, text=_BULK_TEXT)
    return BulkStatusResult(page.id, page.name, BulkStatusOutcome.MOVED)


def _bulk_close_one(_uow: AbstractUnitOfWork, page: RegistrationPage, user_id: uuid.UUID) -> BulkStatusResult:
    if page.status is not RegistrationPageStatus.PUBLISHED:
        return BulkStatusResult(page.id, page.name, BulkStatusOutcome.SKIPPED)
    page.close(author_id=user_id, text=_BULK_TEXT)
    return BulkStatusResult(page.id, page.name, BulkStatusOutcome.MOVED)


def _bulk_status_change(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    action: str,
    transition: Callable[[AbstractUnitOfWork, RegistrationPage, uuid.UUID], BulkStatusResult],
) -> list[BulkStatusResult]:
    """Apply a transition to every page of an assembly, best effort.

    Pages that cannot make the transition are reported rather than raised, so one
    unfinished page never stops its siblings moving. Whatever moved is committed.
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action=action, required_role=_MANAGE_ROLE)

        results = [transition(uow, page, user.id) for page in uow.registration_pages.list_by_assembly_id(assembly_id)]
        uow.commit()
        return results


def publish_all_registration_pages(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[BulkStatusResult]:
    """Publish every page of an assembly that is ready to go live."""
    return _bulk_status_change(uow, user_id, assembly_id, "publish registration pages", _bulk_publish_one)


def unpublish_all_registration_pages(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[BulkStatusResult]:
    """Return every published page of an assembly to TEST."""
    return _bulk_status_change(uow, user_id, assembly_id, "unpublish registration pages", _bulk_unpublish_one)


def close_all_registration_pages(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[BulkStatusResult]:
    """Close every published page of an assembly."""
    return _bulk_status_change(uow, user_id, assembly_id, "close registration pages", _bulk_close_one)


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


def render_registration_form(
    uow: AbstractUnitOfWork,
    page: RegistrationPage,
    csrf_form_element: str,
    form_action: str,
    values: dict[str, str] | None = None,
    errors: dict[str, list[str]] | None = None,
    form_level_errors: list[str] | None = None,
) -> str:
    """Render the public form HTML for a page already resolved as visible.

    Loads the active HTML source and the assembly in a single transaction and
    renders the author HTML against a RenderContext. Keeping the render inside
    the ``with uow:`` block means a failed render (the sandbox raises on bad
    author HTML) still rolls back and closes the session rather than leaking an
    open transaction.

    The request CSP nonce is deliberately absent from the RenderContext: author
    HTML must not be able to reference ``{{ csp_nonce }}`` to whitelist its own
    inline JavaScript past the Content-Security-Policy.
    """
    with uow:
        source = _load_html_source(uow, page)
        assembly = uow.assemblies.get(page.assembly_id)
        ctx = RenderContext(
            csrf_form_element=csrf_form_element,
            form_action=form_action,
            assembly_title=assembly.title if assembly else "",
            assembly_question=assembly.question if assembly else "",
            values=values or {},
            errors=errors or {},
            form_level_errors=form_level_errors or [],
        )
        return source.render(ctx)


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


@dataclass(frozen=True)
class StarterFormHtmlVariants:
    plain: str
    govuk: str


def generate_starter_form_html_variants(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> StarterFormHtmlVariants:
    """Generate both the unstyled and GOV.UK-styled starter HTML forms from the assembly's respondent field schema."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="generate starter HTML", required_role=_MANAGE_ROLE)
        fields = list(uow.respondent_field_definitions.list_by_assembly(assembly_id))
        return StarterFormHtmlVariants(plain=_build_starter_html(fields), govuk=_build_starter_html_govuk(fields))
