"""ABOUTME: Clones a project (assembly) whose data is held in OpenDLP, for demos and training
ABOUTME: Copies chosen parts - targets, questions, registration pages, respondents, team - under new IDs"""

import dataclasses
import uuid
from dataclasses import dataclass, field

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_asset_urls import rewrite_asset_urls
from opendlp.domain.registration_content_block import RegistrationContentBlock
from opendlp.domain.registration_document import RegistrationDocument
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition, RespondentFieldMappingEntry
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory
from opendlp.domain.users import User
from opendlp.domain.value_objects import RespondentStatus
from opendlp.translations import gettext as _

from .assembly_service import check_title_available, create_assembly, is_title_available
from .exceptions import (
    AssemblyNotFoundError,
    AssemblyTitleTaken,
    CannotCloneGSheetAssembly,
    InsufficientPermissions,
    InvalidCloneOptions,
    UserNotFoundError,
)
from .permissions import can_create_assembly, can_view_assembly
from .registration_page_service import generate_page_url_slug, generate_unique_short_url_slug
from .unit_of_work import AbstractUnitOfWork
from .user_service import assign_assembly_role

MAX_COPY_NUMBER = 9

# A selection is what moves a respondent out of the pool; a clone has no
# selection history, so by default everyone it moved goes back. A test
# submission stays one - putting it in the pool is a deliberate step.
_RESET_STATUS = {
    RespondentStatus.POOL: RespondentStatus.POOL,
    RespondentStatus.SELECTED: RespondentStatus.POOL,
    RespondentStatus.CONFIRMED: RespondentStatus.POOL,
    RespondentStatus.WITHDRAWN: RespondentStatus.POOL,
    RespondentStatus.TEST_SUBMISSION: RespondentStatus.TEST_SUBMISSION,
}


@dataclass(frozen=True)
class CloneOptions:
    title: str = ""
    targets: bool = True
    questions: bool = True
    registration: bool = True
    respondents: bool = False
    preserve_respondent_status: bool = False
    team: bool = False
    confirm_no_personal_data: bool = False


@dataclass(frozen=True)
class CloneResult:
    assembly: Assembly
    registration_pages: list[RegistrationPage]
    counts: dict[str, int] = field(default_factory=dict)


def validate_clone_options(options: CloneOptions) -> None:
    """Raise InvalidCloneOptions if the parts asked for do not fit together."""
    if options.registration and not options.questions:
        raise InvalidCloneOptions(
            _("The registration form needs its questions. Clone the questions too, or leave out the registration form.")
        )
    if options.respondents and not options.questions:
        raise InvalidCloneOptions(_("Respondents need the registration questions. Clone the questions too."))
    if options.respondents and not options.confirm_no_personal_data:
        raise InvalidCloneOptions(
            _(
                "Respondents can only be cloned once you confirm they hold no real personal data, for training or a demo."
            )
        )
    if options.preserve_respondent_status and not options.respondents:
        raise InvalidCloneOptions(_("Keeping respondent statuses only makes sense when cloning respondents."))


def clone_status(status: RespondentStatus, preserve: bool) -> RespondentStatus:
    return status if preserve else _RESET_STATUS[status]


def _load_source(uow: AbstractUnitOfWork, user_id: uuid.UUID, source_assembly_id: uuid.UUID) -> tuple[User, Assembly]:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    source = uow.assemblies.get(source_assembly_id)
    if not source:
        raise AssemblyNotFoundError(f"Assembly {source_assembly_id} not found")
    if not can_create_assembly(user):
        raise InsufficientPermissions(action="clone assembly", required_role="organiser or admin")
    # TODO: revisit once the permissions refactor lands - cloning the team hands
    # out roles on the new project, which may want a manage capability.
    if not can_view_assembly(user, source):
        raise InsufficientPermissions(action="clone assembly", required_role="assembly role or admin")
    if source.gsheet is not None:
        raise CannotCloneGSheetAssembly()
    return user, source


def count_respondents_to_clone(uow: AbstractUnitOfWork, user_id: uuid.UUID, source_assembly_id: uuid.UUID) -> int:
    """How many respondents a clone with respondents would copy - every one but the DELETED.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _load_source(uow, user_id, source_assembly_id)
    return uow.respondents.count_by_assembly_id(source_assembly_id)


def choose_clone_title(uow: AbstractUnitOfWork, user_id: uuid.UUID, source_title: str, requested: str) -> str:
    """The requested title if the title rule allows it, else the first free "<source> (copy N)".

    Raises AssemblyTitleTaken when the requested title is taken, or no copy title is free.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if requested.strip():
        check_title_available(uow, user_id, requested)
        return requested.strip()
    candidates = [f"{source_title} (copy)"] + [f"{source_title} (copy {n})" for n in range(2, MAX_COPY_NUMBER + 1)]
    for candidate in candidates:
        if is_title_available(uow, user_id, candidate):
            return candidate
    raise AssemblyTitleTaken(candidates[-1])


def clone_assembly(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, source_assembly_id: uuid.UUID, options: CloneOptions
) -> CloneResult:
    """Copy a project held in OpenDLP, and the parts of it that `options` ask for, under new IDs.

    Selection history, email send records, the Google Sheet export, reply-to
    settings, respondent comments and DELETED respondents are never copied.
    Registration pages start in TEST with fresh slugs.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    validate_clone_options(options)
    user, source = _load_source(uow, user_id, source_assembly_id)
    title = choose_clone_title(uow, user_id, source.title, options.title)

    created = create_assembly(
        uow,
        title=title,
        created_by_user_id=user.id,
        question=source.question,
        first_assembly_date=source.first_assembly_date,
        number_to_select=source.number_to_select,
    )
    clone = uow.assemblies.get(created.id)
    assert clone is not None
    clone.questions_updated_at = source.questions_updated_at
    _clone_settings(source, clone)
    uow.flush()

    counts: dict[str, int] = {}
    category_ids = _clone_targets(uow, source, clone) if options.targets else {}
    counts["targets"] = len(category_ids)

    clone_derived = options.targets and options.questions
    source_fields = uow.respondent_field_definitions.list_by_assembly(source.id)
    if options.questions:
        counts["questions"], counts["derived_fields"] = _clone_questions(
            uow, source_fields, clone, category_ids, clone_derived
        )
        counts["content_blocks"] = _clone_content_blocks(uow, source, clone)

    pages: list[RegistrationPage] = []
    page_ids: dict[uuid.UUID, uuid.UUID] = {}
    if options.registration:
        pages, page_ids, registration_counts = _clone_registration(uow, user, source, clone)
        counts.update(registration_counts)

    if options.respondents:
        stripped_keys = set() if clone_derived else {f.field_key for f in source_fields if f.is_derived}
        counts["respondents"] = _clone_respondents(
            uow, source, clone, page_ids, stripped_keys, options.preserve_respondent_status
        )

    if options.team:
        counts["team_members"] = _clone_team(uow, user, source, clone)

    return CloneResult(
        assembly=clone.create_detached_copy(),
        registration_pages=[page.create_detached_copy() for page in pages],
        counts=counts,
    )


def _clone_settings(source: Assembly, clone: Assembly) -> None:
    if source.selection_settings is not None:
        clone.selection_settings = dataclasses.replace(
            source.selection_settings,
            assembly_id=clone.id,
            selection_settings_id=None,
            check_same_address_cols=list(source.selection_settings.check_same_address_cols),
            columns_to_keep=list(source.selection_settings.columns_to_keep),
        )
    if source.csv is not None:
        clone.csv = AssemblyCSV(
            assembly_id=clone.id,
            csv_id_column=source.csv.csv_id_column,
            settings_confirmed=source.csv.settings_confirmed,
        )


def _clone_targets(uow: AbstractUnitOfWork, source: Assembly, clone: Assembly) -> dict[uuid.UUID, uuid.UUID]:
    category_ids: dict[uuid.UUID, uuid.UUID] = {}
    for category in uow.target_categories.get_by_assembly_id(source.id):
        copied = TargetCategory(
            assembly_id=clone.id,
            name=category.name,
            sort_order=category.sort_order,
            values=[dataclasses.replace(value) for value in category.values],
            comment=category.comment,
            source_url=category.source_url,
        )
        uow.target_categories.add(copied)
        category_ids[category.id] = copied.id
    return category_ids


def _clone_questions(
    uow: AbstractUnitOfWork,
    source_fields: list[RespondentFieldDefinition],
    clone: Assembly,
    category_ids: dict[uuid.UUID, uuid.UUID],
    clone_derived: bool,
) -> tuple[int, int]:
    """Copy the field definitions; derived ones, and their lookup rows, only when `clone_derived`."""
    copies: list[RespondentFieldDefinition] = []
    field_ids: dict[uuid.UUID, uuid.UUID] = {}
    for source_field in source_fields:
        if source_field.is_derived and not clone_derived:
            continue
        copied = RespondentFieldDefinition(
            assembly_id=clone.id,
            field_key=source_field.field_key,
            label=source_field.label,
            group=source_field.group,
            sort_order=source_field.sort_order,
            is_fixed=source_field.is_fixed,
            is_derived=source_field.is_derived,
            derived_from=source_field.derived_from,
            derivation_type=source_field.derivation_type,
            derivation_config=source_field.derivation_config,
            field_type=source_field.field_type,
            options=source_field.options,
            on_registration_page=source_field.on_registration_page,
            help_text=source_field.help_text,
            target_category_id=category_ids.get(source_field.target_category_id)
            if source_field.target_category_id
            else None,
        )
        copies.append(copied)
        field_ids[source_field.id] = copied.id
    uow.respondent_field_definitions.bulk_add(copies)
    uow.flush()

    for source_field in source_fields:
        if source_field.is_derived and source_field.id in field_ids:
            entries = uow.respondent_field_mapping_entries.list_for_field(source_field.id)
            uow.respondent_field_mapping_entries.bulk_add([
                RespondentFieldMappingEntry(
                    field_id=field_ids[source_field.id], lookup_key=entry.lookup_key, output_value=entry.output_value
                )
                for entry in entries
            ])

    derived_count = sum(1 for f in copies if f.is_derived)
    return len(copies) - derived_count, derived_count


def _clone_content_blocks(uow: AbstractUnitOfWork, source: Assembly, clone: Assembly) -> int:
    blocks = uow.registration_content_blocks.list_by_assembly(source.id)
    for block in blocks:
        uow.registration_content_blocks.add(
            RegistrationContentBlock(
                assembly_id=clone.id, sort_order=block.sort_order, heading=block.heading, body_html=block.body_html
            )
        )
    return len(blocks)


def _clone_registration(
    uow: AbstractUnitOfWork, user: User, source: Assembly, clone: Assembly
) -> tuple[list[RegistrationPage], dict[uuid.UUID, uuid.UUID], dict[str, int]]:
    """Copy the images, documents, email templates and pages, pointing the copied HTML at the copies."""
    image_ids: dict[uuid.UUID, uuid.UUID] = {}
    images = uow.registration_images.list_by_assembly_id(source.id)
    for image in images:
        copied_image = RegistrationImage(
            assembly_id=clone.id,
            byte_size=image.byte_size,
            width=image.width,
            height=image.height,
            sha256=image.sha256,
            data=image.data,
            alt=image.alt,
            original_filename=image.original_filename,
            created_by=user.id,
        )
        uow.registration_images.add(copied_image)
        image_ids[image.id] = copied_image.id

    documents = uow.registration_documents.list_by_assembly_id(source.id)
    for document in documents:
        uow.registration_documents.add(
            RegistrationDocument(
                assembly_id=clone.id,
                byte_size=document.byte_size,
                sha256=document.sha256,
                data=document.data,
                original_filename=document.original_filename,
                label=document.label,
                created_by=user.id,
            )
        )

    source_pages = uow.registration_pages.list_by_assembly_id(source.id)
    pages: list[RegistrationPage] = []
    page_ids: dict[uuid.UUID, uuid.UUID] = {}
    url_slugs: dict[str, str] = {}
    for source_page in source_pages:
        page = RegistrationPage(
            assembly_id=clone.id,
            url_slug=generate_page_url_slug(uow, clone.id, clone.title, source_page.name, source_page.language),
            short_url_slug=generate_unique_short_url_slug(uow),
            source_type=source_page.source_type,
            thank_you_html=source_page.thank_you_html,
            thank_you_use_default=source_page.thank_you_use_default,
            name=source_page.name,
            language=source_page.language,
        )
        page.record_clone(user.id, source.title)
        uow.registration_pages.add(page)
        uow.flush()
        pages.append(page)
        page_ids[source_page.id] = page.id
        if source_page.url_slug:
            url_slugs[source_page.url_slug] = page.url_slug

    template_ids: dict[uuid.UUID, uuid.UUID] = {}
    templates = uow.email_templates.list_by_assembly(source.id)
    for template in templates:
        copied_template = EmailTemplate(
            assembly_id=clone.id,
            name=template.name,
            subject=template.subject,
            body_html=rewrite_asset_urls(template.body_html, image_ids, url_slugs),
        )
        uow.email_templates.add(copied_template)
        template_ids[template.id] = copied_template.id

    for source_page, page in zip(source_pages, pages, strict=True):
        page.thank_you_html = rewrite_asset_urls(page.thank_you_html, image_ids, url_slugs)
        if source_page.auto_reply_email_template_id:
            page.auto_reply_email_template_id = template_ids.get(source_page.auto_reply_email_template_id)
        source_html = uow.registration_page_html_sources.get_by_page_id(source_page.id)
        if source_html is not None:
            uow.registration_page_html_sources.add(
                RegistrationPageHtml(
                    registration_page_id=page.id,
                    form_html=rewrite_asset_urls(source_html.form_html, image_ids, url_slugs),
                    intro_html=rewrite_asset_urls(source_html.intro_html, image_ids, url_slugs),
                    content_style=source_html.content_style,
                    form_updated_at=source_html.form_updated_at,
                )
            )

    counts = {
        "registration_pages": len(pages),
        "images": len(images),
        "documents": len(documents),
        "email_templates": len(templates),
    }
    return pages, page_ids, counts


def _clone_respondents(
    uow: AbstractUnitOfWork,
    source: Assembly,
    clone: Assembly,
    page_ids: dict[uuid.UUID, uuid.UUID],
    stripped_keys: set[str],
    preserve_status: bool,
) -> int:
    copies = [
        Respondent(
            assembly_id=clone.id,
            external_id=respondent.external_id,
            selection_status=clone_status(respondent.selection_status, preserve_status),
            consent=respondent.consent,
            stay_on_db=respondent.stay_on_db,
            eligible=respondent.eligible,
            can_attend=respondent.can_attend,
            email=respondent.email,
            source_type=respondent.source_type,
            registration_page_id=page_ids.get(respondent.registration_page_id)
            if respondent.registration_page_id
            else None,
            attributes={k: v for k, v in respondent.attributes.items() if k not in stripped_keys},
        )
        for respondent in uow.respondents.get_by_assembly_id(source.id)
    ]
    uow.flush()
    uow.respondents.bulk_add(copies)
    return len(copies)


def _clone_team(uow: AbstractUnitOfWork, user: User, source: Assembly, clone: Assembly) -> int:
    count = 0
    for role in list(uow.user_assembly_roles.get_roles_for_assembly(source.id)):
        if role.user_id == user.id:
            continue
        assign_assembly_role(uow, role.user_id, clone.id, role.role)
        count += 1
    return count
