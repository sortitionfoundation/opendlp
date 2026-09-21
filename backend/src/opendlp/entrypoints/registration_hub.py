"""ABOUTME: The registration hub's context - its set-up steps and its list of registration pages
ABOUTME: Shared by the hub view and the set-up step views that paint the hub behind their takeover dialog"""

import uuid
from typing import Any

from flask import url_for
from flask_login import current_user

from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import FieldOnRegistrationPage
from opendlp.entrypoints.blueprints.registration import registration_url, short_url
from opendlp.service_layer.qr_codes import generate_qr_code_base64
from opendlp.service_layer.registration_page_service import deletable_registration_page_ids, list_registration_pages
from opendlp.service_layer.target_source_service import TargetSourceState, target_source_status
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


def editor_url(assembly_id: uuid.UUID, url_slug: str, **kwargs: Any) -> str:
    return url_for(
        "backoffice_registration.view_registration_page", assembly_id=assembly_id, url_slug=url_slug, **kwargs
    )


def _page_row(page: RegistrationPage, assembly_id: uuid.UUID, deletable_ids: set[uuid.UUID]) -> dict[str, Any]:
    """One row of the registration pages list.

    A page created outside the backoffice can lack a slug; it has no public URL
    and cannot be opened here until one is set, so it renders without links. The
    QR code encodes the short URL, matching the editor's sharing panel, so it
    only exists once a short slug does.
    """
    page_short_url = short_url(page.short_url_slug) if page.short_url_slug else ""
    return {
        "page": page,
        "editor_url": editor_url(assembly_id, page.url_slug) if page.url_slug else "",
        "close_url": url_for(
            "backoffice_registration.save_assembly_registration",
            assembly_id=assembly_id,
            url_slug=page.url_slug,
        )
        if page.url_slug and page.status == RegistrationPageStatus.PUBLISHED
        else "",
        "delete_url": url_for(
            "backoffice_registration.delete_assembly_registration_page",
            assembly_id=assembly_id,
            url_slug=page.url_slug,
        )
        if page.url_slug and page.id in deletable_ids
        else "",
        "registration_url": registration_url(page.url_slug) if page.url_slug else "",
        "short_url": page_short_url,
        "qr_code_data_url": generate_qr_code_base64(page_short_url) if page_short_url else "",
        "qr_code_url": url_for(
            "backoffice_registration.download_registration_qr_code",
            assembly_id=assembly_id,
            url_slug=page.url_slug,
        )
        if page_short_url and page.url_slug
        else "",
        "published_at": page.last_published_at(),
    }


def registration_page_rows(
    pages: list[RegistrationPage], assembly_id: uuid.UUID, deletable_ids: set[uuid.UUID]
) -> list[dict[str, Any]]:
    """Rows for the registration pages list — also rendered behind the editor's modal."""
    return [_page_row(page, assembly_id, deletable_ids) for page in pages]


def _setup_summary(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, data_source: str, gsheet: Any
) -> dict[str, Any] | None:
    """Status lines for the registration set-up task list, or None for gsheet assemblies.

    A gsheet assembly's fields are its spreadsheet columns, so the two field
    set-up steps don't apply and the template shows a one-liner instead.
    """
    if data_source == "gsheet" and gsheet:
        return None
    statuses = target_source_status(uow, current_user.id, assembly_id)
    fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    on_form = sum(1 for f in fields if not f.is_derived and f.on_registration_page != FieldOnRegistrationPage.NO)
    return {
        "targets_total": len(statuses),
        "targets_covered": sum(1 for s in statuses if s.state != TargetSourceState.NONE),
        "targets_stale": sum(1 for s in statuses if s.stale),
        "fields_on_form": on_form,
    }


def registration_hub_context(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, data_source: str, gsheet: Any
) -> dict[str, Any]:
    """What the registration hub template needs: the set-up steps and the pages list.

    Shared with the set-up step views, which paint the hub behind their takeover dialog.
    """
    pages = list_registration_pages(uow, current_user.id, assembly_id)
    deletable_ids = deletable_registration_page_ids(uow, current_user.id, assembly_id)
    return {
        "page_rows": registration_page_rows(pages, assembly_id, deletable_ids),
        "setup_summary": _setup_summary(uow, assembly_id, data_source, gsheet),
    }
