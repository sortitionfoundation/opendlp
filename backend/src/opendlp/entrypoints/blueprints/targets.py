"""ABOUTME: Backoffice routes for CRUD operations on assembly targets
ABOUTME: Provides target viewing, editing, CSV upload, and deletion under /backoffice/assembly/*/targets"""

import uuid

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    add_target_value,
    create_target_category,
    delete_target_category,
    delete_target_value,
    delete_targets_for_assembly,
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
    get_targets_for_assembly,
    import_targets_from_csv,
    update_target_category,
    update_target_value,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.respondent_service import get_respondent_attribute_value_counts
from opendlp.service_layer.target_checking import check_targets_detailed
from opendlp.service_layer.target_respondent_helpers import (
    MAX_DISTINCT_VALUES_FOR_AUTO_ADD,
    build_respondent_counts,
    build_selected_counts,
    get_assembly_respondent_attribute_columns,
    get_column_distinct_counts,
    get_respondent_counts_for_category,
    get_selected_counts_for_category,
)
from opendlp.translations import gettext as _

from ..forms import AddTargetCategoryForm, EditTargetCategoryForm, TargetValueForm, UploadTargetsCsvForm

targets_bp = Blueprint("targets", __name__)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _can_manage(assembly_id: uuid.UUID) -> bool:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            user = uow.users.get(current_user.id)
            assembly = uow.assemblies.get(assembly_id)
            if user and assembly:
                return can_manage_assembly(user, assembly)
    except Exception:  # noqa: S110
        # Permission check failure treated as no permission
        pass
    return False


def _get_assembly_context(assembly_id: uuid.UUID) -> dict:
    """Get common assembly context needed for the targets page layout (tabs, data source)."""
    gsheet = None
    try:
        uow_gsheet = bootstrap.bootstrap()
        gsheet = get_assembly_gsheet(uow_gsheet, assembly_id, current_user.id)
    except Exception:  # noqa: S110
        pass  # No gsheet config exists - expected for new assemblies

    csv_status: CSVUploadStatus | None = None
    try:
        uow_csv = bootstrap.bootstrap()
        csv_status = get_csv_upload_status(uow_csv, current_user.id, assembly_id)
    except Exception:  # noqa: S110
        pass  # No CSV data - expected for new assemblies

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    return {
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


@targets_bp.route("/assembly/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly targets page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow2 = bootstrap.bootstrap()
        target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

        upload_form = UploadTargetsCsvForm()
        add_category_form = AddTargetCategoryForm()
        value_form = TargetValueForm()
        can_manage = _can_manage(assembly_id)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        respondent_counts = build_respondent_counts(assembly_id, target_categories, attribute_columns)
        selected_counts = build_selected_counts(assembly_id, target_categories, attribute_columns)
        has_selected = any(selected_counts.values())

        # Get the id_column to exclude from the respondent columns list
        id_column = ""
        if assembly.csv is not None:
            id_column = assembly.csv.csv_id_column

        column_distinct_counts = get_column_distinct_counts(assembly_id, attribute_columns)

        context = _get_assembly_context(assembly_id)

        return render_template(
            "backoffice/assembly_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            form=upload_form,
            add_category_form=add_category_form,
            value_form=value_form,
            can_manage=can_manage,
            respondent_attribute_columns=attribute_columns,
            all_respondent_counts=respondent_counts,
            all_selected_counts=selected_counts,
            has_selected=has_selected,
            id_column=id_column,
            column_distinct_counts=column_distinct_counts,
            **context,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View assembly targets error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while loading assembly targets"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _render_targets_upload_page(assembly_id: uuid.UUID, form: UploadTargetsCsvForm) -> ResponseReturnValue:
    """Re-render the targets page so the user sees their upload error inline."""
    uow = bootstrap.bootstrap()
    assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

    uow2 = bootstrap.bootstrap()
    target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

    context = _get_assembly_context(assembly_id)

    return render_template(
        "backoffice/assembly_targets.html",
        assembly=assembly,
        assembly_id=assembly_id,
        target_categories=target_categories,
        form=form,
        add_category_form=AddTargetCategoryForm(),
        value_form=TargetValueForm(),
        can_manage=_can_manage(assembly_id),
        **context,
    ), 200


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/upload", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Upload targets CSV file for an assembly."""
    form = UploadTargetsCsvForm()
    try:
        if not form.validate_on_submit():
            return _render_targets_upload_page(assembly_id, form)

        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")
        filename = csv_file.filename or "unknown.csv"

        uow = bootstrap.bootstrap()
        categories = import_targets_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=True,
        )

        total_values = sum(len(c.values) for c in categories)
        flash(
            _(
                "Successfully imported %(cats)s categories with %(vals)s values from %(file)s",
                cats=len(categories),
                vals=total_values,
                file=filename,
            ),
            "success",
        )

        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid targets CSV for assembly {assembly_id}: {e}")
        form.csv_file.errors.append(_("CSV import failed: %(error)s", error=str(e)))
        return _render_targets_upload_page(assembly_id, form)
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except UnicodeDecodeError:
        form.csv_file.errors.append(_("Could not read CSV file. Please ensure it is UTF-8 encoded."))
        return _render_targets_upload_page(assembly_id, form)
    except Exception as e:
        current_app.logger.error(f"Upload targets error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        form.csv_file.errors.append(_("An unexpected error occurred during import"))
        return _render_targets_upload_page(assembly_id, form)


@targets_bp.route("/assembly/<uuid:assembly_id>/data/delete-targets", methods=["POST"])
@login_required
def delete_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete all targets for an assembly."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            count = delete_targets_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
            )

        flash(_("Targets deleted: %(count)d categories removed", count=count), "success")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

    except InsufficientPermissions as e:
        current_app.logger.warning(
            f"Insufficient permissions to delete targets for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("You don't have permission to delete targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for targets deletion: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Delete targets error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An error occurred while deleting targets"), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/categories", methods=["POST"])
@login_required
def add_category(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a target category to an assembly."""
    form = AddTargetCategoryForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                return render_template(
                    "backoffice/targets/add_category_form.html",
                    assembly_id=assembly_id,
                    add_category_form=form,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        uow2 = bootstrap.bootstrap()
        existing = get_targets_for_assembly(uow2, current_user.id, assembly_id)
        sort_order = len(existing)
        assert form.name.data is not None  # this is basically a type hint

        category = create_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            name=form.name.data,
            sort_order=sort_order,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            add_category_form = AddTargetCategoryForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            response = make_response(
                render_template(
                    "backoffice/targets/add_category_response.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=value_form,
                    add_category_form=add_category_form,
                    can_manage=True,
                    respondent_counts=counts,
                    selected_counts=sel_counts,
                    has_selected=bool(sel_counts),
                )
            )
            response.headers["HX-Trigger"] = "categoriesChanged"
            return response

        flash(_("Category '%(name)s' added", name=category.name), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.name.errors.append(str(e))  # type: ignore[attr-defined]
            return render_template(
                "backoffice/targets/add_category_form.html",
                assembly_id=assembly_id,
                add_category_form=form,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>",
    methods=["POST"],
)
@login_required
def edit_category(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Rename a target category."""
    form = EditTargetCategoryForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                return render_template(
                    "backoffice/targets/category_name_edit.html",
                    assembly_id=assembly_id,
                    category_id=category_id,
                    edit_category_form=form,
                    editing=True,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        assert form.name.data is not None
        category = update_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
            name=form.name.data,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            )

        flash(_("Category renamed to '%(name)s'", name=category.name), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.name.errors.append(str(e))  # type: ignore[attr-defined]
            return render_template(
                "backoffice/targets/category_name_edit.html",
                assembly_id=assembly_id,
                category_id=category_id,
                edit_category_form=form,
                editing=True,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>/delete",
    methods=["POST"],
)
@login_required
def remove_category(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a target category and all its values."""
    try:
        uow = bootstrap.bootstrap()
        delete_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
        )

        if _is_htmx():
            response = make_response("")
            response.headers["HX-Trigger"] = "categoriesChanged"
            return response

        flash(_("Category deleted"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values",
    methods=["POST"],
)
@login_required
def add_value(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Add a value to a target category."""
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
                counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
                sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
                return render_template(
                    "backoffice/targets/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=form,
                    show_add_value=True,
                    can_manage=True,
                    respondent_counts=counts,
                    selected_counts=sel_counts,
                    has_selected=bool(sel_counts),
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        assert form.value.data is not None
        assert form.min_count.data is not None
        assert form.max_count.data is not None
        category = add_target_value(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
            value=form.value.data,
            min_count=form.min_count.data,
            max_count=form.max_count.data,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            )

        flash(_("Value '%(value)s' added", value=form.value.data), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.value.errors.append(str(e))  # type: ignore[attr-defined]
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                show_add_value=True,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>",
    methods=["POST"],
)
@login_required
def edit_value(assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID) -> ResponseReturnValue:
    """Edit an existing target value."""
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
                counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
                sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
                return render_template(
                    "backoffice/targets/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=form,
                    editing_value_id=value_id,
                    can_manage=True,
                    respondent_counts=counts,
                    selected_counts=sel_counts,
                    has_selected=bool(sel_counts),
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        assert form.value.data is not None
        assert form.min_count.data is not None
        assert form.max_count.data is not None
        category = update_target_value(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
            value_id=value_id,
            value=form.value.data,
            min_count=form.min_count.data,
            max_count=form.max_count.data,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            )

        flash(_("Value updated"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.value.errors.append(str(e))  # type: ignore[attr-defined]
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                editing_value_id=value_id,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>/delete",
    methods=["POST"],
)
@login_required
def remove_value(assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a target value from a category."""
    try:
        uow = bootstrap.bootstrap()
        category = delete_target_value(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
            value_id=value_id,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            )

        flash(_("Value deleted"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/add-missing",
    methods=["POST"],
)
@login_required
def add_missing_values(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Bulk-add missing respondent values to a target category with min=0, max=0."""
    try:
        missing_values = request.form.getlist("missing_values")
        if not missing_values:
            flash(_("No values to add"), "warning")
            if _is_htmx():
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                return render_template(
                    "backoffice/targets/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=TargetValueForm(),
                    can_manage=True,
                )
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        category = None
        for value_name in missing_values:
            uow = bootstrap.bootstrap()
            category = add_target_value(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                category_id=category_id,
                value=value_name,
                min_count=0,
                max_count=0,
            )

        if _is_htmx() and category is not None:
            value_form = TargetValueForm()
            attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
            counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            sel_counts = get_selected_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "backoffice/targets/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
                selected_counts=sel_counts,
                has_selected=bool(sel_counts),
            )

        flash(
            _("Added %(count)s values", count=len(missing_values)),
            "success",
        )
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/respondent-columns",
)
@login_required
def respondent_columns(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Render the respondent data columns section (HTMX partial)."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow2 = bootstrap.bootstrap()
        target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        column_distinct_counts = get_column_distinct_counts(assembly_id, attribute_columns)

        id_column = ""
        if assembly.csv is not None:
            id_column = assembly.csv.csv_id_column

        return render_template(
            "backoffice/targets/respondent_columns.html",
            assembly_id=assembly_id,
            target_categories=target_categories,
            can_manage=_can_manage(assembly_id),
            respondent_attribute_columns=attribute_columns,
            column_distinct_counts=column_distinct_counts,
            id_column=id_column,
        )

    except (NotFoundError, InsufficientPermissions):
        return ""


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/add-from-columns",
    methods=["POST"],
)
@login_required
def add_categories_from_columns(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Bulk-create target categories from selected respondent attribute columns."""
    try:
        selected_columns = request.form.getlist("columns")
        if not selected_columns:
            flash(_("No columns selected"), "warning")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        existing = get_targets_for_assembly(uow, current_user.id, assembly_id)
        sort_order = len(existing)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        column_distinct_counts = get_column_distinct_counts(assembly_id, attribute_columns)

        created = []
        values_added_count = 0
        for column_name in selected_columns:
            try:
                uow = bootstrap.bootstrap()
                category = create_target_category(
                    uow=uow,
                    user_id=current_user.id,
                    assembly_id=assembly_id,
                    name=column_name,
                    sort_order=sort_order,
                )
                created.append(column_name)
                sort_order += 1

                # Auto-add all distinct values for low-cardinality columns
                distinct_count = column_distinct_counts.get(column_name, 0)
                if distinct_count > 0 and distinct_count < MAX_DISTINCT_VALUES_FOR_AUTO_ADD:
                    uow2 = bootstrap.bootstrap()
                    with uow2:
                        value_counts = get_respondent_attribute_value_counts(uow2, assembly_id, column_name)
                    for value_name in sorted(value_counts.keys()):
                        uow3 = bootstrap.bootstrap()
                        add_target_value(
                            uow=uow3,
                            user_id=current_user.id,
                            assembly_id=assembly_id,
                            category_id=category.id,
                            value=value_name,
                            min_count=0,
                            max_count=0,
                        )
                        values_added_count += 1
            except ValueError:
                # Category with this name may already exist; skip it
                continue

        if created:
            if values_added_count > 0:
                flash(
                    _(
                        "Created %(count)s categories with %(values)s values: %(names)s",
                        count=len(created),
                        values=values_added_count,
                        names=", ".join(created),
                    ),
                    "success",
                )
            else:
                flash(
                    _("Created %(count)s categories: %(names)s", count=len(created), names=", ".join(created)),
                    "success",
                )
        else:
            flash(_("No new categories were created"), "warning")

        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/check", methods=["GET"])
@login_required
def check_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Run detailed target validation and display results."""
    try:
        uow = bootstrap.bootstrap()
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow2 = bootstrap.bootstrap()
        with uow2:
            check_result = check_targets_detailed(uow2, current_user.id, assembly_id)

        uow3 = bootstrap.bootstrap()
        target_categories = get_targets_for_assembly(uow3, current_user.id, assembly_id)

        upload_form = UploadTargetsCsvForm()
        add_category_form = AddTargetCategoryForm()
        value_form = TargetValueForm()
        can_manage = _can_manage(assembly_id)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        respondent_counts = build_respondent_counts(assembly_id, target_categories, attribute_columns)
        selected_counts = build_selected_counts(assembly_id, target_categories, attribute_columns)
        has_selected = any(selected_counts.values())

        id_column = ""
        if assembly.csv is not None:
            id_column = assembly.csv.csv_id_column

        column_distinct_counts = get_column_distinct_counts(assembly_id, attribute_columns)

        context = _get_assembly_context(assembly_id)

        return render_template(
            "backoffice/assembly_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            form=upload_form,
            add_category_form=add_category_form,
            value_form=value_form,
            can_manage=can_manage,
            respondent_attribute_columns=attribute_columns,
            all_respondent_counts=respondent_counts,
            all_selected_counts=selected_counts,
            has_selected=has_selected,
            id_column=id_column,
            column_distinct_counts=column_distinct_counts,
            check_result=check_result,
            **context,
        ), 200

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error checking targets for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full stacktrace:")
        flash(_("An unexpected error occurred while checking targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
