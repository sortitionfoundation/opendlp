"""ABOUTME: Developer tools routes for interactive testing and documentation
ABOUTME: Provides /backoffice/dev/* routes - only registered in non-production environments"""

import uuid
from collections.abc import Callable
from typing import Any

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    get_or_create_csv_config,
    get_or_create_selection_settings,
    import_targets_from_csv,
    update_csv_config,
    update_selection_settings,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.user_service import get_user_assemblies
from opendlp.translations import gettext as _

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
    valid_tabs = ["respondents", "targets", "config", "selection"]
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


# Mapping of service names to their handler functions
_SERVICE_HANDLERS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "import_respondents_from_csv": _handle_import_respondents,
    "import_targets_from_csv": _handle_import_targets,
    "get_or_create_csv_config": _handle_get_csv_config,
    "update_csv_config": _handle_update_csv_config,
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
    valid_tabs = ["dropdown", "form", "ajax", "file-upload", "progress"]
    if active_tab not in valid_tabs:
        active_tab = "dropdown"

    # Get assemblies for live examples
    uow = bootstrap.bootstrap()
    assemblies = get_user_assemblies(uow, current_user.id)

    return render_template("backoffice/patterns.html", assemblies=assemblies, active_tab=active_tab), 200
