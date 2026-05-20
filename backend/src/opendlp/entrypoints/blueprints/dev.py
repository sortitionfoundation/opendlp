"""ABOUTME: Developer tools routes for interactive testing and documentation
ABOUTME: Provides /backoffice/dev/* routes - only registered in non-production environments"""

import uuid
from collections.abc import Callable
from typing import Any

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
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
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page,
    generate_starter_form_html,
    get_registration_page_with_source,
    publish_registration_page,
    reopen_registration_page,
    unpublish_registration_page,
    update_registration_page,
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
    valid_tabs = ["respondents", "targets", "config", "selection", "assembly", "registration"]
    if active_tab not in valid_tabs:
        active_tab = "respondents"

    # Get all assemblies for the dropdown (admin can see all via get_user_assemblies)
    uow = bootstrap.bootstrap()
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
        current_app.logger.error(f"Service docs execute error: {e}")
        current_app.logger.exception("Full traceback:")
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
                uow2 = bootstrap.bootstrap()
                sel_settings = update_selection_settings(
                    uow=uow2,
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                    **sel_kwargs,
                )
            else:
                sel_settings = get_or_create_selection_settings(
                    uow=bootstrap.bootstrap(),
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
                user_id=current_user.id,
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
                    "preview_token": reg_page.preview_token,
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
                    "id": str(html_source.id),
                    "html_content_preview": html_source.html_content[:200] + "..."
                    if len(html_source.html_content) > 200
                    else html_source.html_content,
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
    "generate_starter_form_html": _handle_generate_starter_html,
    "publish_registration_page": _handle_publish_registration_page,
    "unpublish_registration_page": _handle_unpublish_registration_page,
    "close_registration_page": _handle_close_registration_page,
    "reopen_registration_page": _handle_reopen_registration_page,
}


def _execute_service(service_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a service layer function and return the result as JSON-serializable dict."""
    handler = _SERVICE_HANDLERS.get(service_name)
    if handler is None:
        return {"status": "error", "error": f"Unknown service: {service_name}", "error_type": "ValidationError"}

    uow = bootstrap.bootstrap()
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
    uow = bootstrap.bootstrap()
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
