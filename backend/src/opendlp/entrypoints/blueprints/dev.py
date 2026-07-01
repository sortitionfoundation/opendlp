"""ABOUTME: Developer tools routes for interactive testing and documentation
ABOUTME: Provides /backoffice/dev/* routes - only registered in non-production environments"""

import base64
import binascii
import uuid
from collections.abc import Callable
from typing import Any, cast

import structlog
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.registration_image import IMAGE_FILE_EXTENSION, ImageValidationError, RegistrationImage
from opendlp.domain.registration_page import RegistrationPageHtml
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldGroup,
)
from opendlp.domain.validators import SlugError
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import (
    create_assembly,
    get_assembly_with_permissions,
    get_or_create_csv_config,
    get_or_create_selection_settings,
    import_targets_from_csv,
    update_assembly,
    update_csv_config,
    update_selection_settings,
)
from opendlp.service_layer.email_template_service import (
    assign_auto_reply_template,
    auto_reply_readiness_problems,
    create_email_template,
    delete_email_template,
    get_email_template,
    list_email_templates,
    update_email_template,
)
from opendlp.service_layer.exceptions import (
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    ImageQuotaExceeded,
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.registration_image_service import (
    add_registration_image,
    delete_registration_image,
    get_registration_image_for_serving,
    list_image_snippets,
    list_registration_images,
    set_registration_image_alt,
)
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page,
    generate_starter_form_html,
    get_registration_page_with_source,
    publish_registration_page,
    reopen_registration_page,
    unpublish_registration_page,
    update_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.registration_submission_service import (
    submit_registration_by_assembly_id,
)
from opendlp.service_layer.respondent_field_schema_service import (
    FieldDefinitionConflictError,
    add_field,
)
from opendlp.service_layer.respondent_service import (
    get_respondents_for_assembly,
    import_respondents_from_csv,
    reset_selection_status,
)
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _


def _is_safe_redirect_url(url: str) -> bool:
    """Check if a URL is safe for redirection (internal only).

    Prevents open redirect attacks by only allowing relative URLs.
    """
    # Only allow relative URLs that start with / but not // (protocol-relative)
    return url.startswith("/") and not url.startswith("//")


dev_bp = Blueprint("dev", __name__)

logger = structlog.get_logger(__name__)


# =============================================================================
# Developer Tools Dashboard (Admin-only)
# =============================================================================


@dev_bp.route("/dev")
@login_required
def dev_dashboard() -> ResponseReturnValue:
    """Developer tools dashboard.

    Admin-only page that links to all developer tools.
    This blueprint is only registered in non-production environments.
    """
    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    return render_template("backoffice/dev_dashboard.html"), 200


# =============================================================================
# Service Layer Documentation (Admin-only developer tools)
# =============================================================================


@dev_bp.route("/dev/service-docs")
@login_required
def service_docs() -> ResponseReturnValue:
    """Interactive service layer documentation page for CSV upload services.

    Admin-only page that provides interactive testing of service layer functions.
    This blueprint is only registered in non-production environments.
    """
    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    # Get active tab from query parameter, default to 'respondents'
    active_tab = request.args.get("tab", "respondents")
    valid_tabs = [
        "respondents",
        "targets",
        "config",
        "selection",
        "assembly",
        "registration",
        "fields",
        "images",
        "emails",
    ]
    if active_tab not in valid_tabs:
        active_tab = "respondents"

    # Get all assemblies for the dropdown (admin can see all via get_user_assemblies)
    uow = bootstrap.get_flask_uow()
    assemblies = get_user_assemblies(uow, current_user.id)

    return render_template("backoffice/service_docs.html", assemblies=assemblies, active_tab=active_tab), 200


@dev_bp.route("/dev/service-docs/execute", methods=["POST"])
@login_required
def service_docs_execute() -> ResponseReturnValue:
    """Execute a service layer function for testing.

    Accepts JSON with service name and parameters, returns JSON result.
    This blueprint is only registered in non-production environments.
    """
    if not has_global_admin(current_user):
        return jsonify({"status": "error", "error": "Unauthorized", "error_type": "InsufficientPermissions"}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "error": "No JSON data provided", "error_type": "ValidationError"}), 400

        service_name = data.get("service")
        params = data.get("params", {})

        result = _execute_service(service_name, params)
        return jsonify(result), 200

    except Exception as e:
        logger.exception("Service docs execute error", error=str(e))
        return jsonify({
            "status": "error",
            "error": "An internal error occurred while executing the service.",
            "error_type": "InternalError",
        }), 500


def _handle_import_respondents(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle import_respondents_from_csv service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    csv_content = params["csv_content"]
    replace_existing = params.get("replace_existing", False)
    id_column = params.get("id_column") or None

    with uow:
        try:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=replace_existing,
                id_column=id_column,
            )
            return {
                "status": "success",
                "imported_count": len(respondents),
                "errors": errors,
                "id_column_used": resolved_id_column,
                "sample_respondents": [
                    {
                        "external_id": r.external_id,
                        "attributes": r.attributes,
                        "email": r.email,
                        "consent": r.consent,
                        "eligible": r.eligible,
                        "can_attend": r.can_attend,
                    }
                    for r in respondents[:5]  # Show first 5 as sample
                ],
            }
        except InvalidSelection as e:
            return {"status": "error", "error": str(e), "error_type": "InvalidSelection"}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_reset_selection_status(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle reset_selection_status service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            count = reset_selection_status(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "respondents_reset": count,
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_get_respondents(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_respondents_for_assembly service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    status_str = params.get("status")
    status = RespondentStatus(status_str) if status_str else None

    with uow:
        try:
            respondents = get_respondents_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                status=status,
            )
            return {
                "status": "success",
                "total_count": len(respondents),
                "respondents": [
                    {
                        "external_id": r.external_id,
                        "attributes": r.attributes,
                        "selection_status": r.selection_status.value if r.selection_status else None,
                        "email": r.email,
                        "consent": r.consent,
                        "eligible": r.eligible,
                        "can_attend": r.can_attend,
                    }
                    for r in respondents[:20]  # Show first 20 as sample
                ],
                "showing": min(20, len(respondents)),
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_import_targets(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle import_targets_from_csv service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    csv_content = params["csv_content"]
    replace_existing = params.get("replace_existing", True)

    with uow:
        try:
            categories = import_targets_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=replace_existing,
            )
            return {
                "status": "success",
                "categories_count": len(categories),
                "total_values_count": sum(len(c.values) for c in categories),
                "categories": [
                    {
                        "name": c.name,
                        "values": [
                            {
                                "value": v.value,
                                "min": v.min,
                                "max": v.max,
                                "min_flex": v.min_flex,
                                "max_flex": v.max_flex,
                            }
                            for v in c.values
                        ],
                    }
                    for c in categories
                ],
            }
        except InvalidSelection as e:
            return {"status": "error", "error": str(e), "error_type": "InvalidSelection"}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_get_csv_config(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_or_create_csv_config service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            csv_config = get_or_create_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            sel_settings = get_or_create_selection_settings(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "config": {
                    "assembly_csv_id": str(csv_config.assembly_csv_id) if csv_config.assembly_csv_id else None,
                    "assembly_id": str(csv_config.assembly_id),
                    "csv_id_column": csv_config.csv_id_column,
                    "id_column": sel_settings.id_column,
                    "check_same_address": sel_settings.check_same_address,
                    "check_same_address_cols": sel_settings.check_same_address_cols,
                    "columns_to_keep": sel_settings.columns_to_keep,
                    "selection_algorithm": sel_settings.selection_algorithm,
                    "settings_confirmed": csv_config.settings_confirmed,
                    "last_import_filename": csv_config.last_import_filename,
                    "last_import_timestamp": csv_config.last_import_timestamp.isoformat()
                    if csv_config.last_import_timestamp
                    else None,
                    "created_at": csv_config.created_at.isoformat() if csv_config.created_at else None,
                    "updated_at": csv_config.updated_at.isoformat() if csv_config.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_csv_config(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_csv_config service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    settings = {k: v for k, v in params.items() if k not in ("assembly_id",)}

    with uow:
        try:
            # Split settings into CSV-specific and selection settings
            selection_fields = {
                "id_column",
                "check_same_address",
                "check_same_address_cols",
                "columns_to_keep",
                "selection_algorithm",
            }
            sel_kwargs = {k: v for k, v in settings.items() if k in selection_fields}
            csv_kwargs = {k: v for k, v in settings.items() if k not in selection_fields}

            csv_config = update_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                **csv_kwargs,
            )
            if sel_kwargs:
                uow2 = bootstrap.get_flask_uow()
                sel_settings = update_selection_settings(
                    uow=uow2,
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                    **sel_kwargs,
                )
            else:
                sel_settings = get_or_create_selection_settings(
                    uow=bootstrap.get_flask_uow(),
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                )
            return {
                "status": "success",
                "config": {
                    "assembly_csv_id": str(csv_config.assembly_csv_id) if csv_config.assembly_csv_id else None,
                    "assembly_id": str(csv_config.assembly_id),
                    "csv_id_column": csv_config.csv_id_column,
                    "id_column": sel_settings.id_column,
                    "check_same_address": sel_settings.check_same_address,
                    "check_same_address_cols": sel_settings.check_same_address_cols,
                    "columns_to_keep": sel_settings.columns_to_keep,
                    "selection_algorithm": sel_settings.selection_algorithm,
                    "settings_confirmed": csv_config.settings_confirmed,
                    "updated_at": csv_config.updated_at.isoformat() if csv_config.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_create_assembly(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle create_assembly service call."""
    title = params["title"]
    question = params.get("question", "")
    number_to_select = params.get("number_to_select", 0)

    with uow:
        try:
            assembly = create_assembly(
                uow=uow,
                created_by_user_id=current_user.id,
                title=title,
                question=question,
                number_to_select=int(number_to_select) if number_to_select else 0,
            )
            return {
                "status": "success",
                "assembly": {
                    "id": str(assembly.id),
                    "title": assembly.title,
                    "question": assembly.question,
                    "number_to_select": assembly.number_to_select,
                    "created_at": assembly.created_at.isoformat() if assembly.created_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}


def _handle_get_assembly(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_assembly_with_permissions service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            assembly = get_assembly_with_permissions(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "assembly": {
                    "id": str(assembly.id),
                    "title": assembly.title,
                    "question": assembly.question,
                    "number_to_select": assembly.number_to_select,
                    "first_assembly_date": assembly.first_assembly_date.isoformat()
                    if assembly.first_assembly_date
                    else None,
                    "created_at": assembly.created_at.isoformat() if assembly.created_at else None,
                    "updated_at": assembly.updated_at.isoformat() if assembly.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_assembly(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_assembly service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    updates = {k: v for k, v in params.items() if k != "assembly_id" and v}

    with uow:
        try:
            assembly = update_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                **updates,
            )
            return {
                "status": "success",
                "assembly": {
                    "id": str(assembly.id),
                    "title": assembly.title,
                    "question": assembly.question,
                    "number_to_select": assembly.number_to_select,
                    "updated_at": assembly.updated_at.isoformat() if assembly.updated_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_create_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle create_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            reg_page = create_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "assembly_id": str(reg_page.assembly_id),
                    "url_slug": reg_page.url_slug,
                    "short_url_slug": reg_page.short_url_slug,
                    "status": reg_page.status.value if reg_page.status else None,
                    "created_at": reg_page.created_at.isoformat() if reg_page.created_at else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except ValueError as e:
            return {"status": "error", "error": str(e), "error_type": "ValueError"}


def _handle_get_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_registration_page_with_source service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            result = get_registration_page_with_source(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            if result is None:
                return {
                    "status": "success",
                    "registration_page": None,
                    "html_source": None,
                }
            reg_page, html_source = result
            # Cast to RegistrationPageHtml since HtmlSource protocol doesn't expose id/form_html
            html = cast(RegistrationPageHtml, html_source)
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "assembly_id": str(reg_page.assembly_id),
                    "url_slug": reg_page.url_slug,
                    "short_url_slug": reg_page.short_url_slug,
                    "status": reg_page.status.value if reg_page.status else None,
                    "created_at": reg_page.created_at.isoformat() if reg_page.created_at else None,
                },
                "html_source": {
                    "id": str(html.id),
                    "form_html_preview": html.form_html[:200] + "..." if len(html.form_html) > 200 else html.form_html,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    url_slug = params.get("url_slug")
    short_url_slug = params.get("short_url_slug")

    with uow:
        try:
            reg_page = update_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                url_slug=url_slug,
                short_url_slug=short_url_slug,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "url_slug": reg_page.url_slug,
                    "short_url_slug": reg_page.short_url_slug,
                    "updated_at": reg_page.updated_at.isoformat() if reg_page.updated_at else None,
                },
            }
        except SlugError as e:
            return {"status": "error", "error": str(e), "error_type": "SlugError", "field": e.field}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_generate_starter_html(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle generate_starter_form_html service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            html = generate_starter_form_html(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "html": html,
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_registration_page_html(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_registration_page_html service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    form_html = params.get("form_html", "")

    with uow:
        try:
            html_source = update_registration_page_html(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                form_html=form_html,
            )
            return {
                "status": "success",
                "html_source": {
                    "id": str(html_source.id),
                    "form_html_preview": html_source.form_html[:200] + "..."
                    if len(html_source.form_html) > 200
                    else html_source.form_html,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except ValueError as e:
            return {"status": "error", "error": str(e), "error_type": "ValueError"}


def _handle_publish_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle publish_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            reg_page = publish_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "status": reg_page.status.value if reg_page.status else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except Exception as e:
            # Catch RegistrationPageNotReady or other validation errors
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}


def _handle_unpublish_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle unpublish_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            reg_page = unpublish_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "status": reg_page.status.value if reg_page.status else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except Exception as e:
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}


def _handle_close_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle close_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            reg_page = close_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "status": reg_page.status.value if reg_page.status else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except Exception as e:
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}


def _handle_reopen_registration_page(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle reopen_registration_page service call."""
    assembly_id = uuid.UUID(params["assembly_id"])

    with uow:
        try:
            reg_page = reopen_registration_page(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )
            return {
                "status": "success",
                "registration_page": {
                    "id": str(reg_page.id),
                    "status": reg_page.status.value if reg_page.status else None,
                },
            }
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}
        except Exception as e:
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}


def _handle_submit_registration(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle submit_registration_by_assembly_id service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    form_data = params.get("form_data", {})
    is_test = params.get("is_test", False)

    with uow:
        try:
            result = submit_registration_by_assembly_id(
                uow=uow,
                assembly_id=assembly_id,
                form_data=form_data,
                is_test=is_test,
            )
            return {
                "status": "success" if result.is_valid else "validation_error",
                "respondent": {
                    "id": str(result.respondent.id),
                    "external_id": result.respondent.external_id,
                    "selection_status": result.respondent.selection_status.value,
                    "attributes": result.respondent.attributes,
                }
                if result.respondent
                else None,
                "is_test": result.is_test,
                "field_errors": result.field_errors,
                "form_errors": result.form_errors,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}


def _handle_add_field(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle add_field service call for creating a new field definition."""
    assembly_id = uuid.UUID(params["assembly_id"])
    field_key = params.get("field_key", "")
    label = params.get("label") or None
    group_str = params.get("group", "GENERAL")
    field_type_str = params.get("field_type", "TEXT")
    options_raw = params.get("options")  # List of option values (strings) or None

    # Parse group enum
    try:
        group = RespondentFieldGroup(group_str)
    except ValueError:
        return {
            "status": "error",
            "error": f"Invalid group: {group_str}. Valid values: {[g.value for g in RespondentFieldGroup]}",
            "error_type": "ValidationError",
        }

    # Parse field_type enum
    try:
        field_type = FieldType(field_type_str)
    except ValueError:
        return {
            "status": "error",
            "error": f"Invalid field_type: {field_type_str}. Valid values: {[ft.value for ft in FieldType]}",
            "error_type": "ValidationError",
        }

    # Parse options if provided (for choice fields)
    options = None
    if options_raw:
        if isinstance(options_raw, list):
            options = [ChoiceOption(value=str(v)) for v in options_raw]
        else:
            return {
                "status": "error",
                "error": "options must be a list of strings",
                "error_type": "ValidationError",
            }

    with uow:
        try:
            field = add_field(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                field_key=field_key,
                label=label,
                group=group,
                field_type=field_type,
                options=options,
            )
            return {
                "status": "success",
                "field": {
                    "id": str(field.id),
                    "field_key": field.field_key,
                    "label": field.label,
                    "group": field.group.value,
                    "field_type": field.field_type.value,
                    "sort_order": field.sort_order,
                    "options": [{"value": o.value, "help_text": o.help_text} for o in (field.options or [])],
                },
            }
        except FieldDefinitionConflictError as e:
            return {"status": "error", "error": str(e), "error_type": "FieldDefinitionConflictError"}
        except InsufficientPermissions as e:
            return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
        except NotFoundError as e:
            return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _serialise_image(image: RegistrationImage) -> dict[str, Any]:
    return {
        "id": str(image.id),
        "registration_page_id": str(image.registration_page_id),
        "byte_size": image.byte_size,
        "width": image.width,
        "height": image.height,
        "sha256": image.sha256,
        "alt": image.alt,
        "created_by": str(image.created_by) if image.created_by else None,
        "created_at": image.created_at.isoformat() if image.created_at else None,
        "file_name": f"{image.sha256}.{IMAGE_FILE_EXTENSION}",
        "original_filename": image.original_filename,
    }


def _handle_add_registration_image(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle add_registration_image service call.

    The image bytes are expected as a base64-encoded string under ``image_base64``
    (a ``data:`` URL prefix is stripped if present).
    """
    assembly_id = uuid.UUID(params["assembly_id"])
    alt = params.get("alt", "")
    original_filename = params.get("original_filename", "")
    raw_b64 = params.get("image_base64", "")
    if "," in raw_b64 and raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        raw_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError):
        return {"status": "error", "error": "image_base64 is not valid base64", "error_type": "ValidationError"}
    if not raw_bytes:
        return {"status": "error", "error": "image_base64 is empty", "error_type": "ValidationError"}

    try:
        image = add_registration_image(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            raw=raw_bytes,
            alt=alt,
            original_filename=original_filename,
        )
        return {"status": "success", "image": _serialise_image(image)}
    except ImageValidationError as e:
        return {"status": "error", "error": e.message, "error_type": "ImageValidationError", "reason": e.reason}
    except ImageQuotaExceeded as e:
        return {"status": "error", "error": str(e), "error_type": "ImageQuotaExceeded"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_list_registration_images(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle list_registration_images service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    try:
        images = list_registration_images(uow=uow, user_id=current_user.id, assembly_id=assembly_id)
        return {
            "status": "success",
            "total_count": len(images),
            "images": [_serialise_image(image) for image in images],
        }
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_delete_registration_image(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle delete_registration_image service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    image_id = uuid.UUID(params["image_id"])
    try:
        delete_registration_image(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            image_id=image_id,
        )
        return {"status": "success", "deleted_image_id": str(image_id)}
    except RegistrationImageNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "RegistrationImageNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_set_registration_image_alt(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle set_registration_image_alt service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    image_id = uuid.UUID(params["image_id"])
    alt = params.get("alt", "")
    try:
        image = set_registration_image_alt(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            image_id=image_id,
            alt=alt,
        )
        return {"status": "success", "image": _serialise_image(image)}
    except RegistrationImageNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "RegistrationImageNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_list_image_snippets(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle list_image_snippets service call.

    Uses the same URL builder as the public registration route so the snippets
    show the URL the public page would render.
    """
    assembly_id = uuid.UUID(params["assembly_id"])

    page_repo_uow = bootstrap.get_flask_uow()
    with page_repo_uow:
        page = page_repo_uow.registration_pages.get_by_assembly_id(assembly_id)
    url_slug = page.url_slug if page else ""

    def url_for_image(image: RegistrationImage) -> str:
        if url_slug:
            return url_for(
                "registration.serve_registration_image",
                url_slug=url_slug,
                image_name=f"{image.sha256}.{IMAGE_FILE_EXTENSION}",
            )
        return f"<no-slug>/{image.sha256}.{IMAGE_FILE_EXTENSION}"

    try:
        pairs = list_image_snippets(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            url_for_image=url_for_image,
        )
        return {
            "status": "success",
            "total_count": len(pairs),
            "snippets": [{"image": _serialise_image(image), "html": html_snippet} for image, html_snippet in pairs],
        }
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_get_registration_image_for_serving(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_registration_image_for_serving service call.

    Bytes are not returned in the JSON response - we report metadata and whether
    the lookup succeeded. Use the public /register/<slug>/assets/<image_name>
    route to actually fetch the image.
    """
    url_slug = params.get("url_slug", "")
    image_name = params.get("image_name", "")
    image = get_registration_image_for_serving(uow, url_slug, image_name)
    if image is None:
        return {"status": "success", "found": False, "image": None}
    return {"status": "success", "found": True, "image": _serialise_image(image)}


def _serialise_email_template(template: Any) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "assembly_id": str(template.assembly_id),
        "name": template.name,
        "subject": template.subject,
        "body_html_preview": template.body_html[:300] + "..." if len(template.body_html) > 300 else template.body_html,
        "body_html_bytes": len(template.body_html.encode("utf-8")),
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def _handle_create_email_template(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle create_email_template service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    name = params.get("name", "")
    subject = params.get("subject", "")
    body_html = params.get("body_html", "")
    try:
        template = create_email_template(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            name=name,
            subject=subject,
            body_html=body_html,
        )
        return {"status": "success", "template": _serialise_email_template(template)}
    except EmailTemplateInvalid as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateInvalid", "problems": e.problems}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_list_email_templates(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle list_email_templates service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    try:
        templates = list_email_templates(uow=uow, user_id=current_user.id, assembly_id=assembly_id)
        return {
            "status": "success",
            "total_count": len(templates),
            "templates": [_serialise_email_template(t) for t in templates],
        }
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_get_email_template(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle get_email_template service call."""
    template_id = uuid.UUID(params["template_id"])
    try:
        template = get_email_template(uow=uow, user_id=current_user.id, template_id=template_id)
        return {"status": "success", "template": _serialise_email_template(template)}
    except EmailTemplateNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_update_email_template(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_email_template service call."""
    template_id = uuid.UUID(params["template_id"])
    try:
        template = update_email_template(
            uow=uow,
            user_id=current_user.id,
            template_id=template_id,
            name=params.get("name"),
            subject=params.get("subject"),
            body_html=params.get("body_html"),
        )
        return {"status": "success", "template": _serialise_email_template(template)}
    except EmailTemplateInvalid as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateInvalid", "problems": e.problems}
    except EmailTemplateNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_delete_email_template(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle delete_email_template service call."""
    template_id = uuid.UUID(params["template_id"])
    try:
        delete_email_template(uow=uow, user_id=current_user.id, template_id=template_id)
        return {"status": "success", "deleted_template_id": str(template_id)}
    except EmailTemplateNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_assign_auto_reply_template(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle assign_auto_reply_template service call. Pass empty/null template_id to clear."""
    assembly_id = uuid.UUID(params["assembly_id"])
    template_id_raw = params.get("template_id")
    template_id = uuid.UUID(template_id_raw) if template_id_raw else None
    try:
        assign_auto_reply_template(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            template_id=template_id,
        )
        return {
            "status": "success",
            "assembly_id": str(assembly_id),
            "auto_reply_email_template_id": str(template_id) if template_id else None,
        }
    except EmailTemplateNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "EmailTemplateNotFoundError"}
    except RegistrationPageNotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "RegistrationPageNotFoundError"}
    except InsufficientPermissions as e:
        return {"status": "error", "error": str(e), "error_type": "InsufficientPermissions"}
    except NotFoundError as e:
        return {"status": "error", "error": str(e), "error_type": "NotFoundError"}


def _handle_auto_reply_readiness_problems(uow: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle auto_reply_readiness_problems service call."""
    assembly_id = uuid.UUID(params["assembly_id"])
    problems = auto_reply_readiness_problems(uow=uow, assembly_id=assembly_id)
    return {
        "status": "success",
        "problem_count": len(problems),
        "problems": [{"severity": p.severity.value, "message": p.message} for p in problems],
    }


# Mapping of service names to their handler functions
_SERVICE_HANDLERS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "import_respondents_from_csv": _handle_import_respondents,
    "reset_selection_status": _handle_reset_selection_status,
    "get_respondents_for_assembly": _handle_get_respondents,
    "import_targets_from_csv": _handle_import_targets,
    "get_or_create_csv_config": _handle_get_csv_config,
    "update_csv_config": _handle_update_csv_config,
    "create_assembly": _handle_create_assembly,
    "get_assembly_with_permissions": _handle_get_assembly,
    "update_assembly": _handle_update_assembly,
    "create_registration_page": _handle_create_registration_page,
    "get_registration_page_with_source": _handle_get_registration_page,
    "update_registration_page": _handle_update_registration_page,
    "update_registration_page_html": _handle_update_registration_page_html,
    "generate_starter_form_html": _handle_generate_starter_html,
    "publish_registration_page": _handle_publish_registration_page,
    "unpublish_registration_page": _handle_unpublish_registration_page,
    "close_registration_page": _handle_close_registration_page,
    "reopen_registration_page": _handle_reopen_registration_page,
    "submit_registration": _handle_submit_registration,
    "add_field": _handle_add_field,
    "add_registration_image": _handle_add_registration_image,
    "list_registration_images": _handle_list_registration_images,
    "delete_registration_image": _handle_delete_registration_image,
    "set_registration_image_alt": _handle_set_registration_image_alt,
    "list_image_snippets": _handle_list_image_snippets,
    "get_registration_image_for_serving": _handle_get_registration_image_for_serving,
    "create_email_template": _handle_create_email_template,
    "list_email_templates": _handle_list_email_templates,
    "get_email_template": _handle_get_email_template,
    "update_email_template": _handle_update_email_template,
    "delete_email_template": _handle_delete_email_template,
    "assign_auto_reply_template": _handle_assign_auto_reply_template,
    "auto_reply_readiness_problems": _handle_auto_reply_readiness_problems,
}


def _execute_service(service_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a service layer function and return the result as JSON-serializable dict."""
    handler = _SERVICE_HANDLERS.get(service_name)
    if handler is None:
        return {"status": "error", "error": f"Unknown service: {service_name}", "error_type": "ValidationError"}

    uow = bootstrap.get_flask_uow()
    return handler(uow, params)


# =============================================================================
# Frontend Patterns Documentation (Admin-only developer tools)
# =============================================================================


@dev_bp.route("/dev/patterns")
@login_required
def patterns() -> ResponseReturnValue:
    """Interactive frontend patterns documentation page.

    Admin-only page that documents Alpine.js patterns, form handling,
    and other frontend patterns used in the backoffice.
    This blueprint is only registered in non-production environments.
    """
    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    # Get active tab from query parameter, default to 'dropdown'
    active_tab = request.args.get("tab", "dropdown")
    valid_tabs = ["dropdown", "form", "ajax", "file-upload", "progress", "pagination", "scroll", "floating-alerts"]
    if active_tab not in valid_tabs:
        active_tab = "dropdown"

    # Get assemblies for live examples
    uow = bootstrap.get_flask_uow()
    assemblies = get_user_assemblies(uow, current_user.id)

    return render_template("backoffice/patterns.html", assemblies=assemblies, active_tab=active_tab), 200


@dev_bp.route("/dev/flash-test", methods=["POST"])
@login_required
def flash_test() -> ResponseReturnValue:
    """Trigger flash messages for testing floating alerts.

    Admin-only endpoint that creates flash messages of different types.
    This blueprint is only registered in non-production environments.
    """
    if not has_global_admin(current_user):
        flash(_("You don't have permission to access developer tools"), "error")
        return redirect(url_for("backoffice.dashboard"))

    flash_type = request.form.get("type", "info")
    message = request.form.get("message", "")

    if not message:
        messages = {
            "success": _("Success! Your changes have been saved."),
            "warning": _("Warning: Please review the data before continuing."),
            "error": _("Error: Something went wrong. Please try again."),
            "info": _("Info: A new feature is available."),
        }
        message = messages.get(flash_type, messages["info"])

    flash(message, flash_type)

    default_url = url_for("dev.patterns", tab="floating-alerts")
    return_url = request.form.get("return_url", default_url)
    # Validate return_url to prevent open redirect attacks
    if not _is_safe_redirect_url(return_url):
        return_url = default_url
    return redirect(return_url)
