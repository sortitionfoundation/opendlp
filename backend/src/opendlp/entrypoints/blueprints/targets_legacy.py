"""ABOUTME: Targets blueprint for viewing and editing target categories and values
ABOUTME: Provides routes for assembly-level target category management with HTMX support"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    add_target_value,
    create_target_category,
    delete_target_category,
    delete_target_value,
    get_assembly_with_permissions,
    get_targets_for_assembly,
    import_targets_from_csv,
    update_target_category,
    update_target_value,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.respondent_service import (
    get_respondent_attribute_columns,
    get_respondent_attribute_value_counts,
)
from opendlp.service_layer.target_checking import check_targets_detailed
from opendlp.translations import gettext as _

from ..forms import AddTargetCategoryForm, EditTargetCategoryForm, TargetValueForm, UploadTargetsCsvForm

targets_legacy_bp = Blueprint("targets_legacy", __name__)

MAX_DISTINCT_VALUES_FOR_AUTO_ADD = 20


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
        pass
    return False


def _get_respondent_counts_for_category(
    assembly_id: uuid.UUID,
    category_name: str,
    attribute_columns: list[str],
) -> dict[str, int] | None:
    """Get respondent value counts for a category if its name matches a respondent attribute column.

    Uses case-insensitive matching. Returns None if no matching column found.
    """
    columns_lower = {col.lower(): col for col in attribute_columns}
    matched_col = columns_lower.get(category_name.lower())
    if matched_col is None:
        return None
    uow = bootstrap.bootstrap()
    with uow:
        return get_respondent_attribute_value_counts(uow, assembly_id, matched_col)


def _get_respondent_attribute_columns(assembly_id: uuid.UUID) -> list[str]:
    """Get respondent attribute columns for an assembly."""
    uow = bootstrap.bootstrap()
    with uow:
        return get_respondent_attribute_columns(uow, assembly_id)


def _get_column_distinct_counts(
    assembly_id: uuid.UUID,
    attribute_columns: list[str],
) -> dict[str, int]:
    """Get the number of distinct values for each respondent attribute column."""
    counts: dict[str, int] = {}
    uow = bootstrap.bootstrap()
    with uow:
        for col in attribute_columns:
            value_counts = get_respondent_attribute_value_counts(uow, assembly_id, col)
            counts[col] = len(value_counts)
    return counts


def _build_respondent_counts(
    assembly_id: uuid.UUID,
    target_categories: list,
    attribute_columns: list[str],
) -> dict[str, dict[str, int]]:
    """Build respondent value counts for each target category that matches a respondent attribute."""
    respondent_counts: dict[str, dict[str, int]] = {}
    for category in target_categories:
        counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
        if counts is not None:
            respondent_counts[category.name] = counts
    return respondent_counts


@targets_legacy_bp.route("/assemblies/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow2 = bootstrap.bootstrap()
        target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

        upload_form = UploadTargetsCsvForm()
        add_category_form = AddTargetCategoryForm()
        value_form = TargetValueForm()
        can_manage = _can_manage(assembly_id)

        attribute_columns = _get_respondent_attribute_columns(assembly_id)
        respondent_counts = _build_respondent_counts(assembly_id, target_categories, attribute_columns)

        # Get the id_column to exclude from the respondent columns list
        id_column = ""
        if assembly.csv is not None:
            id_column = assembly.csv.csv_id_column

        column_distinct_counts = _get_column_distinct_counts(assembly_id, attribute_columns)

        return render_template(
            "targets/view_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            form=upload_form,
            add_category_form=add_category_form,
            value_form=value_form,
            can_manage=can_manage,
            current_tab="targets",
            respondent_attribute_columns=attribute_columns,
            all_respondent_counts=respondent_counts,
            id_column=id_column,
            column_distinct_counts=column_distinct_counts,
        )

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error viewing targets for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred"), "error")
        return redirect(url_for("main.dashboard"))


@targets_legacy_bp.route("/assemblies/<uuid:assembly_id>/targets/upload", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        form = UploadTargetsCsvForm()

        if not form.validate_on_submit():
            uow = bootstrap.bootstrap()
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            uow2 = bootstrap.bootstrap()
            target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

            return render_template(
                "targets/view_targets.html",
                assembly=assembly,
                assembly_id=assembly_id,
                target_categories=target_categories,
                form=form,
                add_category_form=AddTargetCategoryForm(),
                value_form=TargetValueForm(),
                can_manage=_can_manage(assembly_id),
                current_tab="targets",
            ), 200

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

        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid targets CSV for assembly {assembly_id}: {e}")
        flash(_("CSV import failed: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import targets"), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
    except UnicodeDecodeError:
        flash(_("Could not read CSV file. Please ensure it is UTF-8 encoded."), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Upload targets error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred during import"), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route("/assemblies/<uuid:assembly_id>/targets/categories", methods=["POST"])
@login_required
def add_category(assembly_id: uuid.UUID) -> ResponseReturnValue:
    form = AddTargetCategoryForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                return render_template(
                    "targets/components/add_category_form.html",
                    assembly_id=assembly_id,
                    add_category_form=form,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        uow2 = bootstrap.bootstrap()
        existing = get_targets_for_assembly(uow2, current_user.id, assembly_id)
        sort_order = len(existing)
        assert form.name.data is not None

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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/add_category_response.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                add_category_form=add_category_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(_("Category '%(name)s' added", name=category.name), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.name.errors.append(str(e))  # type: ignore[attr-defined]
            return render_template(
                "targets/components/add_category_form.html",
                assembly_id=assembly_id,
                add_category_form=form,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>",
    methods=["POST"],
)
@login_required
def edit_category(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    form = EditTargetCategoryForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                return render_template(
                    "targets/components/category_name_edit.html",
                    assembly_id=assembly_id,
                    category_id=category_id,
                    edit_category_form=form,
                    editing=True,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(_("Category renamed to '%(name)s'", name=category.name), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.name.errors.append(str(e))  # type: ignore[attr-defined]
            return render_template(
                "targets/components/category_name_edit.html",
                assembly_id=assembly_id,
                category_id=category_id,
                edit_category_form=form,
                editing=True,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/delete",
    methods=["POST"],
)
@login_required
def remove_category(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        delete_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
        )

        if _is_htmx():
            return ""

        flash(_("Category deleted"), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values",
    methods=["POST"],
)
@login_required
def add_value(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                attribute_columns = _get_respondent_attribute_columns(assembly_id)
                counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
                return render_template(
                    "targets/components/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=form,
                    show_add_value=True,
                    can_manage=True,
                    respondent_counts=counts,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(_("Value '%(value)s' added", value=form.value.data), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.value.errors.append(str(e))  # type: ignore[attr-defined]
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                show_add_value=True,
                can_manage=True,
                respondent_counts=counts,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>",
    methods=["POST"],
)
@login_required
def edit_value(assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID) -> ResponseReturnValue:
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                attribute_columns = _get_respondent_attribute_columns(assembly_id)
                counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
                return render_template(
                    "targets/components/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=form,
                    editing_value_id=value_id,
                    can_manage=True,
                    respondent_counts=counts,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(_("Value updated"), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.value.errors.append(str(e))  # type: ignore[attr-defined]
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                editing_value_id=value_id,
                can_manage=True,
                respondent_counts=counts,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>/delete",
    methods=["POST"],
)
@login_required
def remove_value(assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID) -> ResponseReturnValue:
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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(_("Value deleted"), "success")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/add-missing",
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
                    "targets/components/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=TargetValueForm(),
                    can_manage=True,
                )
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

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
            attribute_columns = _get_respondent_attribute_columns(assembly_id)
            counts = _get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
                respondent_counts=counts,
            )

        flash(
            _("Added %(count)s values", count=len(missing_values)),
            "success",
        )
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/add-from-columns",
    methods=["POST"],
)
@login_required
def add_categories_from_columns(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Bulk-create target categories from selected respondent attribute columns."""
    try:
        selected_columns = request.form.getlist("columns")
        if not selected_columns:
            flash(_("No columns selected"), "warning")
            return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        existing = get_targets_for_assembly(uow, current_user.id, assembly_id)
        sort_order = len(existing)

        # Compute distinct value counts to decide whether to auto-add values
        attribute_columns = _get_respondent_attribute_columns(assembly_id)
        column_distinct_counts = _get_column_distinct_counts(assembly_id, attribute_columns)

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

        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))


@targets_legacy_bp.route("/assemblies/<uuid:assembly_id>/targets/check", methods=["POST"])
@login_required
def check_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
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

        attribute_columns = _get_respondent_attribute_columns(assembly_id)
        respondent_counts = _build_respondent_counts(assembly_id, target_categories, attribute_columns)

        id_column = ""
        if assembly.csv is not None:
            id_column = assembly.csv.csv_id_column

        column_distinct_counts = _get_column_distinct_counts(assembly_id, attribute_columns)

        return render_template(
            "targets/view_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            form=upload_form,
            add_category_form=add_category_form,
            value_form=value_form,
            can_manage=can_manage,
            current_tab="targets",
            respondent_attribute_columns=attribute_columns,
            all_respondent_counts=respondent_counts,
            id_column=id_column,
            column_distinct_counts=column_distinct_counts,
            check_result=check_result,
        ), 200

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error checking targets for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred while checking targets"), "error")
        return redirect(url_for("targets_legacy.view_assembly_targets", assembly_id=assembly_id))
