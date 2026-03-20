# Editable Targets: Implementation Plan

## Overview

Make the targets page fully editable: users can create categories and values from scratch, edit existing ones, or import via CSV and then refine. Each operation persists immediately via HTMX, with server-side validation and GOV.UK error patterns.

The flex fields (`min_flex`, `max_flex`) are internal — they always use defaults and are never exposed in the UI.

---

## Phase 1: Service Layer

### 1.1 New service functions in `assembly_service.py`

Add these functions after the existing `import_targets_from_csv()` (around line 574):

```python
def update_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str,
    description: str = "",
) -> TargetCategory:
    """Update a target category's name and description."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update target category",
                required_role="assembly-manager, global-organiser or admin",
            )

        category = uow.target_categories.get(category_id)
        if not category or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")

        category.name = name.strip()
        category.description = description.strip()
        category.updated_at = datetime.now(UTC)

        uow.commit()
        return category.create_detached_copy()


def delete_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
) -> None:
    """Delete a target category."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="delete target category",
                required_role="assembly-manager, global-organiser or admin",
            )

        category = uow.target_categories.get(category_id)
        if not category or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")

        uow.target_categories.delete(category)
        uow.commit()


def add_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value: str,
    min_count: int,
    max_count: int,
) -> TargetCategory:
    """Add a value to a target category. Returns the updated category."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="add target value",
                required_role="assembly-manager, global-organiser or admin",
            )

        category = uow.target_categories.get(category_id)
        if not category or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")

        target_val = TargetValue(value=value, min=min_count, max=max_count)
        category.add_value(target_val)

        uow.commit()
        return category.create_detached_copy()


def update_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    value: str,
    min_count: int,
    max_count: int,
) -> TargetCategory:
    """Update a value within a target category. Returns the updated category."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update target value",
                required_role="assembly-manager, global-organiser or admin",
            )

        category = uow.target_categories.get(category_id)
        if not category or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")

        existing = next((v for v in category.values if v.value_id == value_id), None)
        if not existing:
            raise NotFoundError(f"Target value {value_id} not found")

        # Check uniqueness if name changed
        if value != existing.value and any(v.value == value for v in category.values):
            raise ValueError(f"Value '{value}' already exists in category '{category.name}'")

        existing.value = value.strip()
        existing.min = min_count
        existing.max = max_count
        existing._validate()
        category.updated_at = datetime.now(UTC)

        uow.commit()
        return category.create_detached_copy()


def delete_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
) -> TargetCategory:
    """Delete a value from a target category. Returns the updated category."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="delete target value",
                required_role="assembly-manager, global-organiser or admin",
            )

        category = uow.target_categories.get(category_id)
        if not category or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")

        if not category.remove_value(value_id):
            raise NotFoundError(f"Target value {value_id} not found")

        uow.commit()
        return category.create_detached_copy()
```

**Notes:**

- Every function follows the existing permission-check pattern from `create_target_category()`
- Value operations return the whole `TargetCategory` because values are JSON within the category row
- `min_flex`/`max_flex` are never passed — `TargetValue.__init__` defaults them
- The `min`/`max` parameter names in the service layer use `min_count`/`max_count` to avoid shadowing Python builtins

### 1.2 Exports

Add the new functions to the imports in `targets.py` blueprint (and any `__init__.py` if applicable).

---

## Phase 2: Forms

### 2.1 New form classes in `forms.py`

Add after the existing `UploadTargetsCsvForm`:

```python
class AddTargetCategoryForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for adding a new target category."""

    name = StringField(
        _l("Category Name"),
        validators=[DataRequired(), Length(min=1, max=255)],
        description=_l("e.g. Gender, Age, Ethnicity"),
    )


class EditTargetCategoryForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for editing a target category name."""

    name = StringField(
        _l("Category Name"),
        validators=[DataRequired(), Length(min=1, max=255)],
    )


class TargetValueForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for adding or editing a target value."""

    value = StringField(
        _l("Value"),
        validators=[DataRequired(), Length(min=1, max=255)],
        description=_l("e.g. Male, Female, 16-29"),
    )

    min_count = IntegerField(
        _l("Min"),
        validators=[InputRequired(), NonNegativeValidator()],
    )

    max_count = IntegerField(
        _l("Max"),
        validators=[InputRequired(), NonNegativeValidator()],
    )
```

**Note:** `NonNegativeValidator` already exists in `forms.py` (used by `AssemblyForm.number_to_select`). The max >= min validation is handled server-side by `TargetValue.__post_init__`.

---

## Phase 3: Routes

### 3.1 New routes in `targets.py` blueprint

The targets blueprint currently has 2 routes. We add 7 more. Each route:

- Returns an HTML fragment when `HX-Request` header is present (HTMX)
- Returns a redirect to the full page otherwise (progressive enhancement)
- Uses CSRF protection via Flask-WTF

```python
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
from opendlp.translations import gettext as _

from ..forms import AddTargetCategoryForm, EditTargetCategoryForm, TargetValueForm, UploadTargetsCsvForm

targets_bp = Blueprint("targets", __name__)


def _is_htmx() -> bool:
    """Check if the current request is an HTMX request."""
    return request.headers.get("HX-Request") == "true"


def _can_manage(assembly_id: uuid.UUID) -> bool:
    """Check if the current user can manage the assembly. For template use."""
    try:
        uow = bootstrap.bootstrap()
        from opendlp.service_layer.permissions import can_manage_assembly

        with uow:
            user = uow.users.get(current_user.id)
            assembly = uow.assemblies.get(assembly_id)
            if user and assembly:
                return can_manage_assembly(user, assembly)
    except Exception:
        pass
    return False
```

#### 3.1.1 View route (modify existing)

The existing `view_assembly_targets` route needs to pass additional forms and a `can_manage` flag:

```python
@targets_bp.route("/assemblies/<uuid:assembly_id>/targets")
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

        return render_template(
            "targets/view_targets.html",
            assembly=assembly,
            target_categories=target_categories,
            form=upload_form,
            add_category_form=add_category_form,
            value_form=value_form,
            can_manage=can_manage,
            current_tab="targets",
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
```

#### 3.1.2 Add category

```python
@targets_bp.route("/assemblies/<uuid:assembly_id>/targets/categories", methods=["POST"])
@login_required
def add_category(assembly_id: uuid.UUID) -> ResponseReturnValue:
    form = AddTargetCategoryForm()
    try:
        if not form.validate_on_submit():
            # Return the form fragment with errors for HTMX
            if _is_htmx():
                return render_template(
                    "targets/components/add_category_form.html",
                    assembly_id=assembly_id,
                    add_category_form=form,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        # Get current count for sort_order
        uow2 = bootstrap.bootstrap()
        existing = get_targets_for_assembly(uow2, current_user.id, assembly_id)
        sort_order = len(existing)

        category = create_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            name=form.name.data,
            sort_order=sort_order,
        )

        if _is_htmx():
            # Return the new category block + a fresh empty add-category form
            value_form = TargetValueForm()
            add_category_form = AddTargetCategoryForm()
            return render_template(
                "targets/components/add_category_response.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                add_category_form=add_category_form,
                can_manage=True,
            )

        flash(_("Category '%(name)s' added", name=category.name), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.name.errors.append(str(e))
            return render_template(
                "targets/components/add_category_form.html",
                assembly_id=assembly_id,
                add_category_form=form,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

#### 3.1.3 Update category name

```python
@targets_bp.route(
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
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
        category = update_target_category(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            category_id=category_id,
            name=form.name.data,
        )

        if _is_htmx():
            value_form = TargetValueForm()
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
            )

        flash(_("Category renamed to '%(name)s'", name=category.name), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.name.errors.append(str(e))
            return render_template(
                "targets/components/category_name_edit.html",
                assembly_id=assembly_id,
                category_id=category_id,
                edit_category_form=form,
                editing=True,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

#### 3.1.4 Delete category

```python
@targets_bp.route(
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
            # Return empty string — HTMX outerHTML swap removes the element
            return ""

        flash(_("Category deleted"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

#### 3.1.5 Add value

```python
@targets_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values",
    methods=["POST"],
)
@login_required
def add_value(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
            if _is_htmx():
                # Re-fetch the category to render the full block with errors
                uow = bootstrap.bootstrap()
                categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
                category = next((c for c in categories if c.id == category_id), None)
                if not category:
                    return "", 404
                return render_template(
                    "targets/components/category_block.html",
                    assembly_id=assembly_id,
                    category=category,
                    value_form=form,
                    show_add_value=True,
                    can_manage=True,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
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
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
            )

        flash(_("Value '%(value)s' added", value=form.value.data), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except ValueError as e:
        if _is_htmx():
            form.value.errors.append(str(e))
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                show_add_value=True,
                can_manage=True,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

#### 3.1.6 Update value

```python
@targets_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>",
    methods=["POST"],
)
@login_required
def edit_value(
    assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID
) -> ResponseReturnValue:
    form = TargetValueForm()
    try:
        if not form.validate_on_submit():
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
                    value_form=form,
                    editing_value_id=value_id,
                    can_manage=True,
                ), 422
            flash(_("Please correct the errors below"), "error")
            return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

        uow = bootstrap.bootstrap()
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
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
            )

        flash(_("Value updated"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (ValueError, NotFoundError, InsufficientPermissions) as e:
        if _is_htmx():
            form.value.errors.append(str(e))
            uow = bootstrap.bootstrap()
            categories = get_targets_for_assembly(uow, current_user.id, assembly_id)
            category = next((c for c in categories if c.id == category_id), None)
            if not category:
                return "", 404
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=form,
                editing_value_id=value_id,
                can_manage=True,
            ), 422
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

#### 3.1.7 Delete value

```python
@targets_bp.route(
    "/assemblies/<uuid:assembly_id>/targets/categories/<uuid:category_id>/values/<uuid:value_id>/delete",
    methods=["POST"],
)
@login_required
def remove_value(
    assembly_id: uuid.UUID, category_id: uuid.UUID, value_id: uuid.UUID
) -> ResponseReturnValue:
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
            return render_template(
                "targets/components/category_block.html",
                assembly_id=assembly_id,
                category=category,
                value_form=value_form,
                can_manage=True,
            )

        flash(_("Value deleted"), "success")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

### 3.2 HTMX 422 handling

HTMX by default does not swap content on 4xx responses. We need to configure it to swap on 422 so validation errors display. Add this to `static/js/htmx-422-swap.js`:

```javascript
// ABOUTME: Configures HTMX to swap content on 422 responses for inline validation errors
// ABOUTME: Without this, HTMX ignores 4xx responses and validation error markup is not displayed

document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("htmx:beforeSwap", function (evt) {
        if (evt.detail.xhr.status === 422) {
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
        }
    });
});
```

Then include it in `base.html` after the HTMX script tag:

```html
<script nonce="{{ csp_nonce }}"
        src="{{ url_for('static', filename='js/htmx-422-swap.js', v=static_hashes('js/htmx-422-swap.js')) }}"></script>
```

This keeps it globally available (any page using HTMX + server validation benefits) and avoids inline scripts.

---

## Phase 4: Templates

### 4.1 Template file structure

```
templates/targets/
    view_targets.html                          -- Full page (modified)
    components/
        category_block.html                    -- Single category: header + values table
        add_category_form.html                 -- "Add category" form (HTMX swap target)
        add_category_response.html             -- New category block + fresh add form (HTMX response)
        category_name_edit.html                -- Inline category name edit form
```

### 4.2 `view_targets.html` (rewrite)

```html
{% extends "main/view_assembly_base.html" %} {% block assembly_breadcrumbs %}
<li class="govuk-breadcrumbs__list-item">{{ _("Targets") }}</li>
{% endblock %} {% block assembly_content %}
<h2 class="govuk-heading-l">{{ _("Target Categories") }}</h2>

{% if target_categories %}
<p class="govuk-body">
  {{ _("%(count)s categories defined.", count=target_categories|length) }}
</p>
{% else %}
<p class="govuk-body">{{ _("No target categories defined yet.") }}</p>
{% endif %} {# ── Category Blocks ─────────────────────────────────── #}
<div id="target-categories">
  {% for category in target_categories %} {% include
  "targets/components/category_block.html" %} {% endfor %}
</div>

{# ── Add Category Form ────────────────────────────────── #} {% if can_manage
%} {% include "targets/components/add_category_form.html" %} {% endif %} {# ──
CSV Import (collapsible) ─────────────────────────── #}
<hr
  class="govuk-section-break govuk-section-break--l govuk-section-break--visible"
/>
<details class="govuk-details">
  <summary class="govuk-details__summary">
    <span class="govuk-details__summary-text">{{ _("Import from CSV") }}</span>
  </summary>
  <div class="govuk-details__text">
    <p class="govuk-body">
      {{ _("Upload a CSV file with columns: feature, value, min, max.") }}
    </p>
    {% if target_categories %}
    <div class="govuk-warning-text">
      <span class="govuk-warning-text__icon" aria-hidden="true">!</span>
      <strong class="govuk-warning-text__text">
        <span class="govuk-visually-hidden">{{ _("Warning") }}</span>
        {{ _("Uploading a CSV will replace all existing target categories.") }}
      </strong>
    </div>
    {% endif %}
    <form
      method="post"
      action="{{ url_for('targets.upload_targets_csv', assembly_id=assembly.id) }}"
      enctype="multipart/form-data"
      novalidate
    >
      {{ form.hidden_tag() }}
      <div
        class="govuk-form-group {% if form.csv_file.errors %}govuk-form-group--error{% endif %}"
      >
        <label class="govuk-label" for="{{ form.csv_file.id }}"
          >{{ form.csv_file.label.text }}</label
        >
        {% if form.csv_file.errors %}
        <p class="govuk-error-message">
          <span class="govuk-visually-hidden">Error:</span>
          {{ form.csv_file.errors[0] }}
        </p>
        {% endif %} {{ form.csv_file(class="govuk-file-upload") }}
      </div>
      <button
        type="submit"
        class="govuk-button govuk-button--secondary"
        data-module="govuk-button"
      >
        {{ _("Upload CSV") }}
      </button>
    </form>
  </div>
</details>
{% endblock %}
```

**Key changes from current template:**

- CSV upload moved into a collapsible `<details>` element (secondary action)
- Category blocks are separate `{% include %}` components
- Add-category form is always visible at the bottom for managers
- `can_manage` flag controls whether edit/delete controls appear

### 4.3 `components/category_block.html`

This is the core component — the HTMX swap target for all value operations within a category.

```html
{# HTMX swap target for category-level operations #}
<div class="govuk-!-margin-bottom-6" id="category-{{ category.id }}">
  {# ── Category Header ──────────────────────────────── #}
  <div class="govuk-!-margin-bottom-2" x-data="{ editing: false }">
    <div x-show="!editing">
      <h3
        class="govuk-heading-m govuk-!-margin-bottom-1"
        style="display: inline;"
      >
        {{ category.name }}
      </h3>
      {% if can_manage %}
      <button
        type="button"
        class="govuk-link govuk-!-margin-left-2"
        @click="editing = true"
      >
        {{ _("Rename") }}
      </button>
      <form
        method="post"
        action="{{ url_for('targets.remove_category', assembly_id=assembly_id, category_id=category.id) }}"
        style="display: inline;"
        hx-post="{{ url_for('targets.remove_category', assembly_id=assembly_id, category_id=category.id) }}"
        hx-target="#category-{{ category.id }}"
        hx-swap="outerHTML"
      >
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
        <button
          type="submit"
          class="govuk-link govuk-!-margin-left-2"
          style="color: #d4351c;"
          data-confirm="{{ _('Are you sure you want to delete the category \&quot;%(name)s\&quot; and all its values?', name=category.name) }}"
        >
          {{ _("Delete") }}
        </button>
      </form>
      {% endif %}
    </div>

    {# ── Inline Rename Form ───────────────────────── #}
    <div x-show="editing" x-cloak>
      <form
        method="post"
        action="{{ url_for('targets.edit_category', assembly_id=assembly_id, category_id=category.id) }}"
        hx-post="{{ url_for('targets.edit_category', assembly_id=assembly_id, category_id=category.id) }}"
        hx-target="#category-{{ category.id }}"
        hx-swap="outerHTML"
        class="govuk-!-margin-bottom-2"
      >
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
        <div class="govuk-form-group" style="display: inline-block;">
          <input
            class="govuk-input govuk-input--width-20"
            type="text"
            name="name"
            value="{{ category.name }}"
            required
          />
        </div>
        <button
          type="submit"
          class="govuk-button govuk-button--secondary govuk-!-margin-bottom-0"
        >
          {{ _("Save") }}
        </button>
        <button
          type="button"
          class="govuk-link govuk-!-margin-left-2"
          @click="editing = false"
        >
          {{ _("Cancel") }}
        </button>
      </form>
    </div>
  </div>

  {# ── Values Table ─────────────────────────────────── #} {% if
  category.values %}
  <table class="govuk-table">
    <thead class="govuk-table__head">
      <tr class="govuk-table__row">
        <th scope="col" class="govuk-table__header">{{ _("Value") }}</th>
        <th
          scope="col"
          class="govuk-table__header govuk-table__header--numeric"
        >
          {{ _("Min") }}
        </th>
        <th
          scope="col"
          class="govuk-table__header govuk-table__header--numeric"
        >
          {{ _("Max") }}
        </th>
        {% if can_manage %}
        <th scope="col" class="govuk-table__header">{{ _("Actions") }}</th>
        {% endif %}
      </tr>
    </thead>
    <tbody class="govuk-table__body">
      {% for val in category.values %}
      <tr
        class="govuk-table__row"
        x-data="{ editing: {{ 'true' if editing_value_id is defined and editing_value_id == val.value_id else 'false' }} }"
      >
        {# ── Display Mode ─── #}
        <template x-if="!editing">
          <td class="govuk-table__cell">{{ val.value }}</td>
        </template>
        <template x-if="!editing">
          <td class="govuk-table__cell govuk-table__cell--numeric">
            {{ val.min }}
          </td>
        </template>
        <template x-if="!editing">
          <td class="govuk-table__cell govuk-table__cell--numeric">
            {{ val.max }}
          </td>
        </template>
        <template x-if="!editing">
          {% if can_manage %}
          <td class="govuk-table__cell">
            <button type="button" class="govuk-link" @click="editing = true">
              {{ _("Edit") }}
            </button>
            <form
              method="post"
              action="{{ url_for('targets.remove_value', assembly_id=assembly_id, category_id=category.id, value_id=val.value_id) }}"
              style="display: inline;"
              hx-post="{{ url_for('targets.remove_value', assembly_id=assembly_id, category_id=category.id, value_id=val.value_id) }}"
              hx-target="#category-{{ category.id }}"
              hx-swap="outerHTML"
            >
              <input
                type="hidden"
                name="csrf_token"
                value="{{ csrf_token() }}"
              />
              <button
                type="submit"
                class="govuk-link govuk-!-margin-left-2"
                style="color: #d4351c;"
                data-confirm="{{ _('Delete value \&quot;%(value)s\&quot;?', value=val.value) }}"
              >
                {{ _("Delete") }}
              </button>
            </form>
          </td>
          {% endif %}
        </template>

        {# ── Edit Mode ────── #}
        <template x-if="editing">
          <td colspan="{{ 4 if can_manage else 3 }}" class="govuk-table__cell">
            <form
              method="post"
              action="{{ url_for('targets.edit_value', assembly_id=assembly_id, category_id=category.id, value_id=val.value_id) }}"
              hx-post="{{ url_for('targets.edit_value', assembly_id=assembly_id, category_id=category.id, value_id=val.value_id) }}"
              hx-target="#category-{{ category.id }}"
              hx-swap="outerHTML"
              class="govuk-!-margin-bottom-0"
            >
              <input
                type="hidden"
                name="csrf_token"
                value="{{ csrf_token() }}"
              />
              {% if value_form and editing_value_id is defined and
              editing_value_id == val.value_id %} {# Show server-side validation
              errors #} {% set vf = value_form %} {% else %} {% set vf = None %}
              {% endif %}
              <div
                style="display: flex; gap: 0.5em; align-items: flex-start; flex-wrap: wrap;"
              >
                <div
                  class="govuk-form-group govuk-!-margin-bottom-0 {% if vf and vf.value.errors %}govuk-form-group--error{% endif %}"
                >
                  <label
                    class="govuk-visually-hidden"
                    for="edit-value-{{ val.value_id }}"
                    >{{ _("Value") }}</label
                  >
                  {% if vf and vf.value.errors %}
                  <p class="govuk-error-message govuk-!-margin-bottom-0">
                    {{ vf.value.errors[0] }}
                  </p>
                  {% endif %}
                  <input
                    class="govuk-input govuk-input--width-10"
                    type="text"
                    name="value"
                    id="edit-value-{{ val.value_id }}"
                    value="{{ vf.value.data if vf and vf.value.data else val.value }}"
                    required
                  />
                </div>
                <div
                  class="govuk-form-group govuk-!-margin-bottom-0 {% if vf and vf.min_count.errors %}govuk-form-group--error{% endif %}"
                >
                  <label
                    class="govuk-visually-hidden"
                    for="edit-min-{{ val.value_id }}"
                    >{{ _("Min") }}</label
                  >
                  {% if vf and vf.min_count.errors %}
                  <p class="govuk-error-message govuk-!-margin-bottom-0">
                    {{ vf.min_count.errors[0] }}
                  </p>
                  {% endif %}
                  <input
                    class="govuk-input govuk-input--width-4"
                    type="number"
                    name="min_count"
                    id="edit-min-{{ val.value_id }}"
                    value="{{ vf.min_count.data if vf and vf.min_count.data is not none else val.min }}"
                    min="0"
                    required
                  />
                </div>
                <div
                  class="govuk-form-group govuk-!-margin-bottom-0 {% if vf and vf.max_count.errors %}govuk-form-group--error{% endif %}"
                >
                  <label
                    class="govuk-visually-hidden"
                    for="edit-max-{{ val.value_id }}"
                    >{{ _("Max") }}</label
                  >
                  {% if vf and vf.max_count.errors %}
                  <p class="govuk-error-message govuk-!-margin-bottom-0">
                    {{ vf.max_count.errors[0] }}
                  </p>
                  {% endif %}
                  <input
                    class="govuk-input govuk-input--width-4"
                    type="number"
                    name="max_count"
                    id="edit-max-{{ val.value_id }}"
                    value="{{ vf.max_count.data if vf and vf.max_count.data is not none else val.max }}"
                    min="0"
                    required
                  />
                </div>
                <button
                  type="submit"
                  class="govuk-button govuk-button--secondary govuk-!-margin-bottom-0"
                >
                  {{ _("Save") }}
                </button>
                <button
                  type="button"
                  class="govuk-link"
                  @click="editing = false"
                >
                  {{ _("Cancel") }}
                </button>
              </div>
            </form>
          </td>
        </template>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="govuk-body govuk-!-margin-bottom-2">
    {{ _("No values defined.") }}
  </p>
  {% endif %} {# ── Add Value Form ───────────────────────────────── #} {% if
  can_manage %}
  <div
    x-data="{ adding: {{ 'true' if show_add_value is defined and show_add_value else 'false' }} }"
  >
    <button
      type="button"
      class="govuk-button govuk-button--secondary"
      x-show="!adding"
      @click="adding = true"
    >
      {{ _("Add value") }}
    </button>

    <div x-show="adding" x-cloak>
      <form
        method="post"
        action="{{ url_for('targets.add_value', assembly_id=assembly_id, category_id=category.id) }}"
        hx-post="{{ url_for('targets.add_value', assembly_id=assembly_id, category_id=category.id) }}"
        hx-target="#category-{{ category.id }}"
        hx-swap="outerHTML"
      >
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
        {% if show_add_value is defined and show_add_value and value_form %} {%
        set af = value_form %} {% else %} {% set af = None %} {% endif %}
        <div
          style="display: flex; gap: 0.5em; align-items: flex-start; flex-wrap: wrap;"
        >
          <div
            class="govuk-form-group govuk-!-margin-bottom-0 {% if af and af.value.errors %}govuk-form-group--error{% endif %}"
          >
            <label class="govuk-label" for="add-value-{{ category.id }}"
              >{{ _("Value") }}</label
            >
            {% if af and af.value.errors %}
            <p class="govuk-error-message govuk-!-margin-bottom-0">
              {{ af.value.errors[0] }}
            </p>
            {% endif %}
            <input
              class="govuk-input govuk-input--width-10"
              type="text"
              name="value"
              id="add-value-{{ category.id }}"
              value="{{ af.value.data if af and af.value.data else '' }}"
              placeholder="{{ _('e.g. Male') }}"
              required
            />
          </div>
          <div
            class="govuk-form-group govuk-!-margin-bottom-0 {% if af and af.min_count.errors %}govuk-form-group--error{% endif %}"
          >
            <label class="govuk-label" for="add-min-{{ category.id }}"
              >{{ _("Min") }}</label
            >
            {% if af and af.min_count.errors %}
            <p class="govuk-error-message govuk-!-margin-bottom-0">
              {{ af.min_count.errors[0] }}
            </p>
            {% endif %}
            <input
              class="govuk-input govuk-input--width-4"
              type="number"
              name="min_count"
              id="add-min-{{ category.id }}"
              value="{{ af.min_count.data if af and af.min_count.data is not none else '' }}"
              min="0"
              required
            />
          </div>
          <div
            class="govuk-form-group govuk-!-margin-bottom-0 {% if af and af.max_count.errors %}govuk-form-group--error{% endif %}"
          >
            <label class="govuk-label" for="add-max-{{ category.id }}"
              >{{ _("Max") }}</label
            >
            {% if af and af.max_count.errors %}
            <p class="govuk-error-message govuk-!-margin-bottom-0">
              {{ af.max_count.errors[0] }}
            </p>
            {% endif %}
            <input
              class="govuk-input govuk-input--width-4"
              type="number"
              name="max_count"
              id="add-max-{{ category.id }}"
              value="{{ af.max_count.data if af and af.max_count.data is not none else '' }}"
              min="0"
              required
            />
          </div>
          <div
            style="display: flex; gap: 0.5em; align-items: flex-end; padding-top: 1.8em;"
          >
            <button type="submit" class="govuk-button govuk-!-margin-bottom-0">
              {{ _("Add") }}
            </button>
            <button type="button" class="govuk-link" @click="adding = false">
              {{ _("Cancel") }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
  {% endif %}
</div>
```

**How it works:**

- The entire `<div id="category-{{ category.id }}">` is the HTMX swap target
- Value add/edit/delete routes return this fragment, replacing the whole category block
- Alpine.js manages the toggle between display/edit mode (client-side only, no server round-trip for toggling)
- Forms have both `action` (no-JS fallback) and `hx-post` (HTMX enhancement)
- `data-confirm` on delete buttons uses the existing utility.js confirmation pattern
- `x-cloak` hides edit forms until Alpine initializes

### 4.4 `components/add_category_form.html`

```html
<div id="add-category-form">
  <form
    method="post"
    action="{{ url_for('targets.add_category', assembly_id=assembly_id) }}"
    hx-post="{{ url_for('targets.add_category', assembly_id=assembly_id) }}"
    hx-target="#add-category-form"
    hx-swap="outerHTML"
    class="govuk-!-margin-top-4"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <div
      style="display: flex; gap: 0.5em; align-items: flex-end; flex-wrap: wrap;"
    >
      <div
        class="govuk-form-group govuk-!-margin-bottom-0 {% if add_category_form.name.errors %}govuk-form-group--error{% endif %}"
      >
        <label class="govuk-label" for="new-category-name"
          >{{ _("New category name") }}</label
        >
        {% if add_category_form.name.errors %}
        <p class="govuk-error-message govuk-!-margin-bottom-0">
          {{ add_category_form.name.errors[0] }}
        </p>
        {% endif %}
        <input
          class="govuk-input govuk-input--width-20"
          type="text"
          name="name"
          id="new-category-name"
          value="{{ add_category_form.name.data or '' }}"
          placeholder="{{ _('e.g. Gender') }}"
          required
        />
      </div>
      <button
        type="submit"
        class="govuk-button govuk-!-margin-bottom-0"
        data-module="govuk-button"
      >
        {{ _("Add category") }}
      </button>
    </div>
  </form>
</div>
```

**HTMX swap behaviour:**

- On success, the server returns `add_category_response.html` which contains the new category block followed by a fresh add-category form (both wrapped to replace `#add-category-form`)
- On validation error (422), returns this same template with errors shown

### 4.5 `components/add_category_response.html`

This is the HTMX response when a category is successfully added. It replaces the `#add-category-form` div with the new category block + a fresh form:

```html
{# Returned by HTMX after successful category creation #} {# Replaces
#add-category-form via outerHTML swap #}
<div id="new-category-wrapper">
  {% include "targets/components/category_block.html" %}
</div>
<div id="add-category-form">
  {% include "targets/components/add_category_form_inner.html" %}
</div>
```

Wait — HTMX `outerHTML` swap replaces a single element. Since we need to insert both a new category block AND a fresh add form, we have a couple of options:

**Better approach:** Use `hx-target="#target-categories"` with `hx-swap="beforeend"` to append the new category block into the categories container, and separately reset the form. But this requires the add form to be inside the categories container, or use out-of-band swaps.

**Simplest approach:** Wrap the categories list AND the add form together in a container, and swap the whole thing. But this re-renders all categories on every add.

**Recommended approach: HTMX out-of-band (OOB) swaps:**

The add-category form targets itself (`#add-category-form`) and the response includes an OOB swap for the new category block:

```html
{# Primary swap: replaces #add-category-form with a fresh empty form #} {%
include "targets/components/add_category_form.html" %} {# OOB swap: appends the
new category block before #add-category-form #}
<div hx-swap-oob="beforebegin:#add-category-form">
  {% include "targets/components/category_block.html" %}
</div>
```

This way:

1. The main swap replaces the form with a clean version (clearing the input)
2. The OOB swap inserts the new category block just above the form
3. Existing category blocks are untouched

Update the route to render this combined response template.

### 4.6 `components/category_name_edit.html`

Only needed if the rename form errors need to be returned as a standalone fragment. In practice, the `category_block.html` already contains the rename form, so the `edit_category` route can just return `category_block.html`. This file is not strictly needed — remove it from the route and use `category_block.html` with an `editing_name=True` flag instead if error display is needed.

---

## Phase 5: Alpine Component (optional)

The current approach uses simple `x-data="{ editing: false }"` inline state, which is CSP-safe. No new Alpine.data() component registration is needed unless we want shared behaviour.

If we want to add a reusable component later (e.g. for keyboard shortcuts, undo), register it in `static/js/alpine-components.js`:

```javascript
document.addEventListener("alpine:init", () => {
  Alpine.data("targetValueRow", () => ({
    editing: false,
    startEdit() {
      this.editing = true;
    },
    cancelEdit() {
      this.editing = false;
    },
  }));
});
```

For now, inline `x-data` is sufficient and simpler.

---

## Phase 6: Testing

### 6.1 Unit tests (`tests/unit/test_targets.py`)

Add tests for new domain behaviours. Most domain logic is already tested; the main new thing is the update-in-place pattern:

```python
def test_update_target_value_in_place():
    """Verify that updating a value's fields and re-validating works."""
    cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
    val = TargetValue(value="Male", min=5, max=10)
    cat.add_value(val)

    # Simulate what update_target_value service does
    val.value = "Male (updated)"
    val.min = 6
    val.max = 12
    val._validate()

    assert val.value == "Male (updated)"
    assert val.min == 6
    assert val.max == 12
    # Flex fields unchanged
    assert val.min_flex == 0
    assert val.max_flex == MAX_FLEX_UNSET


def test_update_target_value_invalid_min_max():
    """Verify validation catches bad min/max on update."""
    val = TargetValue(value="Male", min=5, max=10)
    val.min = 15  # now min > max
    with pytest.raises(ValueError, match="max must be >= min"):
        val._validate()
```

### 6.2 Integration tests (`tests/integration/test_assembly_service_targets.py`)

Add tests for each new service function:

```python
class TestUpdateTargetCategory:
    def test_update_category_name(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        updated = update_target_category(
            uow_factory(), organiser.id, assembly.id, category.id, name="Sex"
        )
        assert updated.name == "Sex"

    def test_update_nonexistent_category_raises(self, uow, assembly, organiser):
        with pytest.raises(NotFoundError):
            update_target_category(
                uow_factory(), organiser.id, assembly.id, uuid.uuid4(), name="Nope"
            )

    def test_update_category_wrong_assembly_raises(self, uow, assembly, other_assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        with pytest.raises(NotFoundError):
            update_target_category(
                uow_factory(), organiser.id, other_assembly.id, category.id, name="Nope"
            )

    def test_update_category_insufficient_permissions(self, uow, assembly, viewer):
        category = create_target_category(uow_factory(), admin.id, assembly.id, "Gender")
        with pytest.raises(InsufficientPermissions):
            update_target_category(uow_factory(), viewer.id, assembly.id, category.id, name="X")


class TestDeleteTargetCategory:
    def test_delete_category(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        delete_target_category(uow_factory(), organiser.id, assembly.id, category.id)
        cats = get_targets_for_assembly(uow_factory(), organiser.id, assembly.id)
        assert len(cats) == 0

    def test_delete_nonexistent_raises(self, uow, assembly, organiser):
        with pytest.raises(NotFoundError):
            delete_target_category(uow_factory(), organiser.id, assembly.id, uuid.uuid4())


class TestAddTargetValue:
    def test_add_value_to_category(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        updated = add_target_value(
            uow_factory(), organiser.id, assembly.id, category.id, "Male", 5, 10
        )
        assert len(updated.values) == 1
        assert updated.values[0].value == "Male"
        assert updated.values[0].min == 5
        assert updated.values[0].max == 10
        assert updated.values[0].min_flex == 0
        assert updated.values[0].max_flex == MAX_FLEX_UNSET

    def test_add_duplicate_value_raises(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 5, 10)
        with pytest.raises(ValueError, match="already exists"):
            add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 3, 7)

    def test_add_value_invalid_min_max_raises(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        with pytest.raises(ValueError):
            add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 10, 5)


class TestUpdateTargetValue:
    def test_update_value(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        cat = add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        updated = update_target_value(
            uow_factory(), organiser.id, assembly.id, category.id, value_id, "Female", 6, 12
        )
        assert updated.values[0].value == "Female"
        assert updated.values[0].min == 6
        assert updated.values[0].max == 12

    def test_update_to_duplicate_name_raises(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        cat = add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 5, 10)
        cat = add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Female", 5, 10)
        value_id = cat.values[1].value_id
        with pytest.raises(ValueError, match="already exists"):
            update_target_value(
                uow_factory(), organiser.id, assembly.id, category.id, value_id, "Male", 5, 10
            )


class TestDeleteTargetValue:
    def test_delete_value(self, uow, assembly, organiser):
        category = create_target_category(uow_factory(), organiser.id, assembly.id, "Gender")
        cat = add_target_value(uow_factory(), organiser.id, assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        updated = delete_target_value(
            uow_factory(), organiser.id, assembly.id, category.id, value_id
        )
        assert len(updated.values) == 0
```

### 6.3 Route tests (`tests/integration/test_targets_routes.py`)

Test each new endpoint:

```python
def test_add_category_requires_login(client, assembly):
    response = client.post(f"/assemblies/{assembly.id}/targets/categories")
    assert response.status_code == 302  # redirect to login

def test_add_category_creates_category(auth_client, assembly):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories",
        data={"name": "Gender", "csrf_token": get_csrf(auth_client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Gender" in response.data

def test_delete_category(auth_client, assembly, category):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories/{category.id}/delete",
        data={"csrf_token": get_csrf(auth_client)},
        follow_redirects=True,
    )
    assert response.status_code == 200

def test_add_value_to_category(auth_client, assembly, category):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories/{category.id}/values",
        data={"value": "Male", "min_count": "5", "max_count": "10", "csrf_token": get_csrf(auth_client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Male" in response.data

def test_add_value_invalid_min_max(auth_client, assembly, category):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories/{category.id}/values",
        data={"value": "Male", "min_count": "10", "max_count": "5", "csrf_token": get_csrf(auth_client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    # Error should be shown

def test_htmx_add_category_returns_fragment(auth_client, assembly):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories",
        data={"name": "Gender", "csrf_token": get_csrf(auth_client)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert b"Gender" in response.data
    assert b"<!DOCTYPE" not in response.data  # Verify it's a fragment

def test_htmx_delete_category_returns_empty(auth_client, assembly, category):
    response = auth_client.post(
        f"/assemblies/{assembly.id}/targets/categories/{category.id}/delete",
        data={"csrf_token": get_csrf(auth_client)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.data == b""
```

### 6.4 E2E tests (`tests/e2e/test_targets_pages.py`)

Add to existing E2E tests:

```python
def test_add_category_from_empty(logged_in_page, assembly):
    """Can add a category when no targets exist."""
    page = logged_in_page
    page.goto(f"/assemblies/{assembly.id}/targets")
    page.fill("#new-category-name", "Gender")
    page.click("button:text('Add category')")
    expect(page.locator("text=Gender")).to_be_visible()

def test_add_value_to_category(logged_in_page, assembly_with_category):
    """Can add a value to an existing category."""
    page = logged_in_page
    page.goto(f"/assemblies/{assembly_with_category.id}/targets")
    page.click("button:text('Add value')")
    page.fill("[name=value]", "Male")
    page.fill("[name=min_count]", "5")
    page.fill("[name=max_count]", "10")
    page.click("button:text('Add')")
    expect(page.locator("text=Male")).to_be_visible()

def test_edit_value_inline(logged_in_page, assembly_with_targets):
    """Can edit a value inline."""
    page = logged_in_page
    page.goto(f"/assemblies/{assembly_with_targets.id}/targets")
    page.click("button:text('Edit')")
    page.fill("[name=value]", "Female")
    page.click("button:text('Save')")
    expect(page.locator("text=Female")).to_be_visible()

def test_delete_category_with_confirmation(logged_in_page, assembly_with_targets):
    """Delete category shows confirmation and removes it."""
    page = logged_in_page
    page.goto(f"/assemblies/{assembly_with_targets.id}/targets")
    page.on("dialog", lambda dialog: dialog.accept())
    page.click("button:text('Delete')")
    # Category should be gone
    expect(page.locator("#target-categories")).not_to_contain_text("Gender")

def test_csv_import_still_works(logged_in_page, assembly):
    """CSV import remains functional within the collapsible section."""
    page = logged_in_page
    page.goto(f"/assemblies/{assembly.id}/targets")
    page.click("text=Import from CSV")
    # Upload form should be visible
    expect(page.locator("button:text('Upload CSV')")).to_be_visible()
```

---

## Implementation Order

1. **Service layer** — new functions in `assembly_service.py` (no UI dependency)
2. **Forms** — new WTForm classes in `forms.py`
3. **Routes** — new endpoints in `targets.py` blueprint, modify existing view route
4. **Templates** — create component templates, rewrite `view_targets.html`
5. **HTMX 422 handler** — add the `beforeSwap` event listener
6. **Tests** — unit, integration, route, and E2E tests throughout

Each phase can be developed and tested independently. The CSV upload path is preserved unchanged.

---

## Design Decisions Summary

| Decision                | Choice                      | Rationale                                                 |
| ----------------------- | --------------------------- | --------------------------------------------------------- |
| Save strategy           | Immediate (per-action)      | Matches project patterns; no lost work; server validation |
| HTMX swap target        | Category block              | Values are JSON in category row; atomic unit              |
| Flex fields             | Hidden, use defaults        | Not user-facing; `min_flex=0`, `max_flex=MAX_FLEX_UNSET`  |
| Progressive enhancement | Yes                         | Forms work without JS; HTMX enhances                      |
| Alpine usage            | Inline `x-data` only        | Simple state (editing toggle); CSP-safe                   |
| Delete confirmation     | `data-confirm` pattern      | Existing utility.js pattern                               |
| Error display           | GOV.UK error messages + 422 | Consistent with codebase; HTMX-compatible                 |
| CSV upload              | Kept, moved to collapsible  | Power-user alternative; not the primary path              |
| New Alpine components   | None needed                 | Inline state is sufficient                                |
| DB migration            | None needed                 | Schema unchanged; values are JSON                         |

---

## Todo List

### Phase 1: Service Layer

- [x] 1.1 Add `update_target_category()` to `assembly_service.py` — rename/update description of an existing category
- [x] 1.2 Add `delete_target_category()` to `assembly_service.py` — delete a single category by ID (with assembly ownership check)
- [x] 1.3 Add `add_target_value()` to `assembly_service.py` — add a value (name, min, max) to an existing category; flex fields use defaults
- [x] 1.4 Add `update_target_value()` to `assembly_service.py` — update a value's name/min/max within a category; validate uniqueness on name change
- [x] 1.5 Add `delete_target_value()` to `assembly_service.py` — remove a value from a category by value_id
- [x] 1.6 Write unit tests for in-place value update and re-validation (`tests/unit/test_targets.py`)
- [x] 1.7 Write integration tests for `update_target_category` — happy path, not-found, wrong assembly, insufficient permissions (`tests/integration/test_assembly_service_targets.py`)
- [x] 1.8 Write integration tests for `delete_target_category` — happy path, not-found (`tests/integration/test_assembly_service_targets.py`)
- [x] 1.9 Write integration tests for `add_target_value` — happy path, duplicate value, invalid min/max (`tests/integration/test_assembly_service_targets.py`)
- [x] 1.10 Write integration tests for `update_target_value` — happy path, rename to duplicate, not-found (`tests/integration/test_assembly_service_targets.py`)
- [x] 1.11 Write integration tests for `delete_target_value` — happy path, not-found (`tests/integration/test_assembly_service_targets.py`)
- [x] 1.12 Run `just test` and `just check` — all existing and new tests pass, no type errors

### Phase 2: Forms

- [x] 2.1 Add `AddTargetCategoryForm` to `forms.py` — StringField for name with DataRequired + Length validators
- [x] 2.2 Add `EditTargetCategoryForm` to `forms.py` — StringField for name with DataRequired + Length validators
- [x] 2.3 Add `TargetValueForm` to `forms.py` — StringField for value, IntegerField for min_count and max_count with InputRequired + NonNegativeValidator
- [x] 2.4 Run `just check` — type checking passes with new forms

### Phase 3: Routes

- [x] 3.1 Add `_is_htmx()` helper to `targets.py` — checks `HX-Request` header
- [x] 3.2 Add `_can_manage()` helper to `targets.py` — checks if current user can manage the assembly (for template context)
- [x] 3.3 Modify existing `view_assembly_targets` route — pass `add_category_form`, `value_form`, and `can_manage` to template
- [x] 3.4 Add `add_category` route (POST) — creates category, returns HTMX fragment (OOB swap) or redirects
- [x] 3.5 Add `edit_category` route (POST) — updates category name, returns category_block fragment or redirects
- [x] 3.6 Add `remove_category` route (POST) — deletes category, returns empty string for HTMX or redirects
- [x] 3.7 Add `add_value` route (POST) — adds value to category, returns category_block fragment or redirects
- [x] 3.8 Add `edit_value` route (POST) — updates value, returns category_block fragment or redirects
- [x] 3.9 Add `remove_value` route (POST) — deletes value, returns category_block fragment or redirects
- [x] 3.10 Update imports at top of `targets.py` — import new service functions and form classes
- [x] 3.11 Write route tests for login-required on all new endpoints (`tests/integration/test_targets_routes.py`)
- [x] 3.12 Write route tests for add/delete category — both regular and HTMX (HX-Request header) variants
- [x] 3.13 Write route tests for add/edit/delete value — both regular and HTMX variants
- [x] 3.14 Write route tests for validation error cases — invalid form data returns 422 with HTMX, redirect without
- [x] 3.15 Run `just test` and `just check` — all tests pass

### Phase 4: Templates

- [x] 4.1 Create `templates/targets/components/` directory
- [x] 4.2 Create `templates/targets/components/category_block.html` — single category with header (name, rename, delete), values table (display + inline edit), add-value form
- [x] 4.3 Create `templates/targets/components/add_category_form.html` — add-category form with HTMX post targeting itself
- [x] 4.4 Create `templates/targets/components/add_category_response.html` — OOB swap response: fresh add-category form (primary swap) + new category block (OOB beforebegin)
- [x] 4.5 Rewrite `templates/targets/view_targets.html` — include category blocks in a loop, include add-category form, move CSV upload into `<details>` collapsible
- [x] 4.6 Verify all templates use `{{ csrf_token() }}` for manual forms and `{{ form.hidden_tag() }}` for WTForms
- [x] 4.7 Verify all translatable strings are wrapped in `{{ _() }}` or `_l()`
- [x] 4.8 Verify Alpine.js usage is CSP-safe — only simple expressions in `x-data`, `x-show`, `@click`; no arrow functions or template literals
- [x] 4.9 Verify `data-confirm` pattern works with `utilities.js` for delete buttons
- [x] 4.10 Manual smoke test — load the page, check that categories display correctly for both managers and viewers

### Phase 5: HTMX 422 Handler

- [x] 5.1 Create `static/js/htmx-422-swap.js` — listen for `htmx:beforeSwap`, allow swap on 422 responses
- [x] 5.2 Add ABOUTME comment header to the new file
- [x] 5.3 Add `<script>` tag to `base.html` after the HTMX script tag — load `htmx-422-swap.js` with `nonce` and `static_hashes` cache busting
- [x] 5.4 Manual smoke test — submit an invalid form via HTMX, confirm validation errors appear inline

### Phase 6: E2E Tests

- [x] 6.1 Add `assembly_with_category` fixture if not already present — assembly with one empty target category
- [x] 6.2 Add `assembly_with_targets` fixture if not already present — assembly with categories and values
- [x] 6.3 Write E2E test: add category from empty state
- [x] 6.4 Write E2E test: add value to an existing category
- [x] 6.5 Write E2E test: edit a value inline (click Edit, change fields, Save)
- [x] 6.6 Write E2E test: delete a category with confirmation dialog
- [x] 6.7 Write E2E test: delete a value with confirmation dialog
- [x] 6.8 Write E2E test: rename a category inline
- [x] 6.9 Write E2E test: validation error on add value (min > max) shows error inline
- [x] 6.10 Write E2E test: CSV import still works within collapsible section
- [x] 6.11 Write E2E test: viewer (non-manager) sees targets but no edit/delete controls
- [x] 6.12 Run full test suite: `just test` and `just check` — everything green

### Phase 7: Translation & Cleanup

- [x] 7.1 Run `just translate-regen` to pick up new translatable strings
- [x] 7.2 Review all new flash messages and form labels for i18n completeness
- [x] 7.3 Keep `components/category_name_edit.html` — used by edit_category error handler for inline validation
- [x] 7.4 Final `just test` and `just check` — confirm clean pass
- [ ] 7.5 Commit
