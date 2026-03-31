# CSV Upload Implementation Plan

## Overview

Add two new assembly-level tabs — **Targets** and **Respondents** — to the assembly view navigation. Each tab displays a summary of existing data and provides a CSV file upload form to import data.

### Design Decisions

1. **Two new tabs** added to the existing 3-tab service navigation (Details, Data & Selection, Team Members), making 5 tabs total: Details, Targets, Respondents, Data & Selection, Team Members.
2. **Two new blueprints** — `targets_bp` and `respondents_bp` — each owns its own tab and routes. Separate blueprints keep related functionality together as the codebase grows (more views will be added to each in future).
3. **No files saved to disk** — CSV content is read in memory and passed as a string to the service layer (GDPR compliance).
4. **GOV.UK file upload component** — already available in govuk-frontend 5.11.1.
5. **Summary stats displayed on the tab page** — no separate "results" page. After upload, redirect back to the same tab with a flash message showing results.

---

## Part 1: Tab Navigation Changes

### 1.1 Modify `view_assembly_base.html`

**File:** `templates/main/view_assembly_base.html`

Add two new tabs between "Details" and "Data & Selection":

```jinja2
{# Service Navigation for Assembly Sections #}
<nav class="govuk-service-navigation govuk-!-margin-bottom-6"
    aria-label="{{ _('Assembly sections') }}">
    <ul class="govuk-service-navigation__list">
        <li class="govuk-service-navigation__item {% if current_tab == 'details' %}govuk-service-navigation__item--active{% endif %}">
            <a class="govuk-service-navigation__link"
                href="{{ url_for('main.view_assembly', assembly_id=assembly.id) }}">{{ _("Details") }}</a>
        </li>
        <li class="govuk-service-navigation__item {% if current_tab == 'targets' %}govuk-service-navigation__item--active{% endif %}">
            <a class="govuk-service-navigation__link"
                href="{{ url_for('targets.view_assembly_targets', assembly_id=assembly.id) }}">{{ _("Targets") }}</a>
        </li>
        <li class="govuk-service-navigation__item {% if current_tab == 'respondents' %}govuk-service-navigation__item--active{% endif %}">
            <a class="govuk-service-navigation__link"
                href="{{ url_for('respondents.view_assembly_respondents', assembly_id=assembly.id) }}">{{ _("Respondents") }}</a>
        </li>
        <li class="govuk-service-navigation__item {% if current_tab == 'data' %}govuk-service-navigation__item--active{% endif %}">
            <a class="govuk-service-navigation__link"
                href="{{ url_for('main.view_assembly_data', assembly_id=assembly.id) }}">
                {{ _("Data & Selection") }}
            </a>
        </li>
        <li class="govuk-service-navigation__item {% if current_tab == 'members' %}govuk-service-navigation__item--active{% endif %}">
            <a class="govuk-service-navigation__link"
                href="{{ url_for('main.view_assembly_members', assembly_id=assembly.id) }}">
                {{ _("Team Members") }}
            </a>
        </li>
    </ul>
</nav>
```

---

## Part 2: Forms

### 2.1 Add file upload forms to `forms.py`

**File:** `src/opendlp/entrypoints/forms.py`

Add new imports at the top:

```python
from flask_wtf.file import FileField, FileAllowed, FileRequired
```

Add two new form classes:

```python
class UploadRespondentsCsvForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for uploading a CSV file of respondents."""

    csv_file = FileField(
        _l("CSV File"),
        validators=[
            FileRequired(message=_l("Please select a CSV file to upload")),
            FileAllowed(["csv"], message=_l("Only CSV files are allowed")),
        ],
        description=_l("Select a CSV file containing respondent data"),
    )

    replace_existing = BooleanField(
        _l("Replace all existing respondents"),
        description=_l(
            "Warning: this will delete all existing respondents for this assembly before importing. "
            "Leave unchecked to add to existing respondents."
        ),
        default=False,
    )

    id_column = StringField(
        _l("ID Column"),
        validators=[Optional(), Length(max=100)],
        description=_l(
            "Column name containing unique identifiers. "
            "Leave blank to use the assembly default."
        ),
    )


class UploadTargetsCsvForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for uploading a CSV file of target categories."""

    csv_file = FileField(
        _l("CSV File"),
        validators=[
            FileRequired(message=_l("Please select a CSV file to upload")),
            FileAllowed(["csv"], message=_l("Only CSV files are allowed")),
        ],
        description=_l("Select a CSV file containing target categories"),
    )

    replace_existing = BooleanField(
        _l("Replace all existing targets"),
        description=_l(
            "Warning: this will delete all existing target categories for this assembly before importing. "
            "Leave unchecked to add to existing targets."
        ),
        default=False,
    )
```

---

## Part 3: New Blueprints — Routes

Two separate blueprints, one per tab, so related functionality stays together as the codebase grows.

### 3.1 Create `targets.py` blueprint

**File:** `src/opendlp/entrypoints/blueprints/targets.py`

```python
"""ABOUTME: Target category routes for viewing and importing selection targets
ABOUTME: Handles CSV upload and display of target categories for assemblies"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    import_targets_from_csv,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.translations import gettext as _

from ..forms import UploadTargetsCsvForm

targets_bp = Blueprint("targets", __name__)


@targets_bp.route("/assemblies/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View target categories and upload form."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            target_categories = uow.target_categories.get_by_assembly_id(assembly_id)
            targets = [tc.create_detached_copy() for tc in target_categories]

        form = UploadTargetsCsvForm()

        return render_template(
            "targets/view_targets.html",
            assembly=assembly,
            target_categories=targets,
            form=form,
            current_tab="targets",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View targets error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        return render_template("errors/500.html"), 500


@targets_bp.route("/assemblies/<uuid:assembly_id>/targets/upload", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Process target categories CSV upload."""
    form = UploadTargetsCsvForm()
    try:
        if not form.validate_on_submit():
            # Re-render the targets page with form errors
            uow = bootstrap.bootstrap()
            with uow:
                assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
                target_categories = uow.target_categories.get_by_assembly_id(assembly_id)
                targets = [tc.create_detached_copy() for tc in target_categories]
            return render_template(
                "targets/view_targets.html",
                assembly=assembly,
                target_categories=targets,
                form=form,
                current_tab="targets",
            ), 200

        # Read CSV content from uploaded file
        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")  # utf-8-sig handles BOM
        filename = csv_file.filename or "unknown.csv"

        uow = bootstrap.bootstrap()
        categories = import_targets_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=form.replace_existing.data or False,
        )

        total_values = sum(len(c.values) for c in categories)
        flash(
            _("Successfully imported %(cats)s target categories with %(vals)s values from %(file)s",
              cats=len(categories), vals=total_values, file=filename),
            "success",
        )
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid targets CSV for assembly {assembly_id}: {e}")
        flash(_("CSV import failed: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except UnicodeDecodeError:
        flash(_("Could not read CSV file. Please ensure it is UTF-8 encoded."), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Upload targets error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred during import"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
```

### 3.2 Create `respondents.py` blueprint

**File:** `src/opendlp/entrypoints/blueprints/respondents.py`

```python
"""ABOUTME: Respondent routes for viewing and importing assembly participants
ABOUTME: Handles CSV upload, summary display, and paginated listing of respondents"""

import uuid
from datetime import UTC, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    update_csv_config,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.translations import gettext as _

from ..forms import UploadRespondentsCsvForm

respondents_bp = Blueprint("respondents", __name__)


@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View respondents summary and upload form."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 50

        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            # Get counts — avoid loading all respondent objects
            all_respondents = uow.respondents.get_by_assembly_id(assembly_id)
            total_count = len(all_respondents)
            available_count = uow.respondents.count_available_for_selection(assembly_id)

            # Paginate for display
            start = (page - 1) * per_page
            end = start + per_page
            respondents_page = [r.create_detached_copy() for r in all_respondents[start:end]]

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        form = UploadRespondentsCsvForm()

        # Pre-fill id_column from assembly CSV config
        if assembly.csv and not form.id_column.data:
            form.id_column.data = assembly.csv.id_column

        return render_template(
            "respondents/view_respondents.html",
            assembly=assembly,
            respondents=respondents_page,
            total_count=total_count,
            available_count=available_count,
            form=form,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            current_tab="respondents",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"View respondents error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        return render_template("errors/500.html"), 500


@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents/upload", methods=["POST"])
@login_required
def upload_respondents_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Process respondents CSV upload."""
    form = UploadRespondentsCsvForm()
    try:
        if not form.validate_on_submit():
            # Re-render the respondents page with form errors
            uow = bootstrap.bootstrap()
            with uow:
                assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            return render_template(
                "respondents/view_respondents.html",
                assembly=assembly,
                respondents=[],
                total_count=0,
                available_count=0,
                form=form,
                page=1,
                per_page=50,
                total_pages=1,
                current_tab="respondents",
            ), 200

        # Read CSV content from uploaded file
        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")
        filename = csv_file.filename or "unknown.csv"

        # Use id_column from form if provided, else None (service layer uses assembly default)
        id_column = form.id_column.data.strip() if form.id_column.data else None

        uow = bootstrap.bootstrap()
        respondents, errors = import_respondents_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=form.replace_existing.data or False,
            id_column=id_column if id_column else None,
        )

        # Update CSV config with import metadata
        uow2 = bootstrap.bootstrap()
        update_csv_config(
            uow=uow2,
            user_id=current_user.id,
            assembly_id=assembly_id,
            last_import_filename=filename,
            last_import_timestamp=datetime.now(UTC),
        )

        # Build flash message
        msg = _("Successfully imported %(count)s respondents from %(file)s",
                count=len(respondents), file=filename)
        flash(msg, "success")

        if errors:
            error_summary = "; ".join(errors[:10])
            if len(errors) > 10:
                error_summary += _(" ... and %(more)s more", more=len(errors) - 10)
            flash(
                _("%(count)s rows were skipped: %(errors)s", count=len(errors), errors=error_summary),
                "warning",
            )

        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid respondents CSV for assembly {assembly_id}: {e}")
        flash(_("CSV import failed: %(error)s", error=str(e)), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import respondents"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except UnicodeDecodeError:
        flash(_("Could not read CSV file. Please ensure it is UTF-8 encoded."), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Upload respondents error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred during import"), "error")
        return redirect(url_for("respondents.view_assembly_respondents", assembly_id=assembly_id))
```

### 3.3 Register both blueprints

**File:** `src/opendlp/entrypoints/flask_app.py` — add to `register_blueprints()`:

```python
from .blueprints.targets import targets_bp
from .blueprints.respondents import respondents_bp

# ... existing registrations ...
app.register_blueprint(targets_bp)
app.register_blueprint(respondents_bp)
```

---

## Part 4: Templates

### 4.1 Targets Tab — `templates/targets/view_targets.html`

```jinja2
{% extends "main/view_assembly_base.html" %}
{% block assembly_breadcrumbs %}<li class="govuk-breadcrumbs__list-item">{{ _("Targets") }}</li>{% endblock %}
{% block assembly_content %}
    {# ── Upload Form ────────────────────────────────────────── #}
    <h2 class="govuk-heading-m">{{ _("Import Target Categories from CSV") }}</h2>
    <p class="govuk-body">
        {{ _("Upload a CSV file with columns: feature, value, min, max (and optionally min_flex, max_flex).") }}
    </p>

    {% if form.errors %}
        <div class="govuk-error-summary" data-module="govuk-error-summary">
            <div role="alert">
                <h2 class="govuk-error-summary__title">{{ _("There is a problem") }}</h2>
                <div class="govuk-error-summary__body">
                    <ul class="govuk-list govuk-error-summary__list">
                        {% for field_name, errors in form.errors.items() %}
                            {% for error in errors %}
                                <li><a href="#{{ form[field_name].id }}">{{ error }}</a></li>
                            {% endfor %}
                        {% endfor %}
                    </ul>
                </div>
            </div>
        </div>
    {% endif %}

    <form method="post"
        action="{{ url_for('targets.upload_targets_csv', assembly_id=assembly.id) }}"
        enctype="multipart/form-data"
        novalidate>
        {{ form.hidden_tag() }}

        <div class="govuk-form-group {% if form.csv_file.errors %}govuk-form-group--error{% endif %}">
            <label class="govuk-label govuk-label--s" for="{{ form.csv_file.id }}">
                {{ form.csv_file.label.text }}
            </label>
            {% if form.csv_file.description %}
                <div class="govuk-hint">{{ form.csv_file.description }}</div>
            {% endif %}
            {% if form.csv_file.errors %}
                <p class="govuk-error-message">
                    <span class="govuk-visually-hidden">Error:</span>
                    {{ form.csv_file.errors[0] }}
                </p>
            {% endif %}
            {{ form.csv_file(class="govuk-file-upload" + (" govuk-file-upload--error" if form.csv_file.errors else "")) }}
        </div>

        <div class="govuk-checkboxes govuk-!-margin-bottom-4" data-module="govuk-checkboxes">
            <div class="govuk-checkboxes__item">
                {{ form.replace_existing(class="govuk-checkboxes__input") }}
                <label class="govuk-label govuk-checkboxes__label"
                    for="{{ form.replace_existing.id }}">{{ form.replace_existing.label.text }}</label>
                {% if form.replace_existing.description %}
                    <div class="govuk-hint govuk-checkboxes__hint">{{ form.replace_existing.description }}</div>
                {% endif %}
            </div>
        </div>

        <div class="govuk-button-group">
            <button type="submit" class="govuk-button" data-module="govuk-button">
                {{ _("Upload CSV") }}
            </button>
        </div>
    </form>

    {# ── Current Targets ────────────────────────────────────── #}
    <hr class="govuk-section-break govuk-section-break--l govuk-section-break--visible">
    <h2 class="govuk-heading-m">{{ _("Current Target Categories") }}</h2>

    {% if target_categories %}
        <p class="govuk-body">
            {{ _("%(count)s categories defined.", count=target_categories|length) }}
        </p>
        {% for category in target_categories %}
            <h3 class="govuk-heading-s govuk-!-margin-bottom-2">{{ category.name }}</h3>
            <table class="govuk-table govuk-!-margin-bottom-6">
                <thead class="govuk-table__head">
                    <tr class="govuk-table__row">
                        <th scope="col" class="govuk-table__header">{{ _("Value") }}</th>
                        <th scope="col" class="govuk-table__header govuk-table__header--numeric">{{ _("Min") }}</th>
                        <th scope="col" class="govuk-table__header govuk-table__header--numeric">{{ _("Max") }}</th>
                        <th scope="col" class="govuk-table__header govuk-table__header--numeric">{{ _("Min Flex") }}</th>
                        <th scope="col" class="govuk-table__header govuk-table__header--numeric">{{ _("Max Flex") }}</th>
                    </tr>
                </thead>
                <tbody class="govuk-table__body">
                    {% for val in category.values %}
                        <tr class="govuk-table__row">
                            <td class="govuk-table__cell">{{ val.value }}</td>
                            <td class="govuk-table__cell govuk-table__cell--numeric">{{ val.min }}</td>
                            <td class="govuk-table__cell govuk-table__cell--numeric">{{ val.max }}</td>
                            <td class="govuk-table__cell govuk-table__cell--numeric">{{ val.min_flex }}</td>
                            <td class="govuk-table__cell govuk-table__cell--numeric">
                                {% if val.max_flex == 0 %}auto{% else %}{{ val.max_flex }}{% endif %}
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% endfor %}
    {% else %}
        <p class="govuk-body">{{ _("No target categories defined yet. Upload a CSV file to get started.") }}</p>
    {% endif %}
{% endblock %}
```

### 4.2 Respondents Tab — `templates/respondents/view_respondents.html`

```jinja2
{% extends "main/view_assembly_base.html" %}
{% block assembly_breadcrumbs %}<li class="govuk-breadcrumbs__list-item">{{ _("Respondents") }}</li>{% endblock %}
{% block assembly_content %}
    {# ── Upload Form ────────────────────────────────────────── #}
    <h2 class="govuk-heading-m">{{ _("Import Respondents from CSV") }}</h2>
    <p class="govuk-body">
        {{ _("Upload a CSV file with a unique ID column and any additional attribute columns.") }}
    </p>

    {% if form.errors %}
        <div class="govuk-error-summary" data-module="govuk-error-summary">
            <div role="alert">
                <h2 class="govuk-error-summary__title">{{ _("There is a problem") }}</h2>
                <div class="govuk-error-summary__body">
                    <ul class="govuk-list govuk-error-summary__list">
                        {% for field_name, errors in form.errors.items() %}
                            {% for error in errors %}
                                <li><a href="#{{ form[field_name].id }}">{{ error }}</a></li>
                            {% endfor %}
                        {% endfor %}
                    </ul>
                </div>
            </div>
        </div>
    {% endif %}

    <form method="post"
        action="{{ url_for('respondents.upload_respondents_csv', assembly_id=assembly.id) }}"
        enctype="multipart/form-data"
        novalidate>
        {{ form.hidden_tag() }}

        <div class="govuk-form-group {% if form.csv_file.errors %}govuk-form-group--error{% endif %}">
            <label class="govuk-label govuk-label--s" for="{{ form.csv_file.id }}">
                {{ form.csv_file.label.text }}
            </label>
            {% if form.csv_file.description %}
                <div class="govuk-hint">{{ form.csv_file.description }}</div>
            {% endif %}
            {% if form.csv_file.errors %}
                <p class="govuk-error-message">
                    <span class="govuk-visually-hidden">Error:</span>
                    {{ form.csv_file.errors[0] }}
                </p>
            {% endif %}
            {{ form.csv_file(class="govuk-file-upload" + (" govuk-file-upload--error" if form.csv_file.errors else "")) }}
        </div>

        <div class="govuk-form-group {% if form.id_column.errors %}govuk-form-group--error{% endif %}">
            <label class="govuk-label govuk-label--s" for="{{ form.id_column.id }}">
                {{ form.id_column.label.text }}
            </label>
            {% if form.id_column.description %}
                <div class="govuk-hint">{{ form.id_column.description }}</div>
            {% endif %}
            {% if form.id_column.errors %}
                <p class="govuk-error-message">
                    <span class="govuk-visually-hidden">Error:</span>
                    {{ form.id_column.errors[0] }}
                </p>
            {% endif %}
            {{ form.id_column(class="govuk-input govuk-!-width-one-third" + (" govuk-input--error" if form.id_column.errors else "")) }}
        </div>

        <div class="govuk-checkboxes govuk-!-margin-bottom-4" data-module="govuk-checkboxes">
            <div class="govuk-checkboxes__item">
                {{ form.replace_existing(class="govuk-checkboxes__input") }}
                <label class="govuk-label govuk-checkboxes__label"
                    for="{{ form.replace_existing.id }}">{{ form.replace_existing.label.text }}</label>
                {% if form.replace_existing.description %}
                    <div class="govuk-hint govuk-checkboxes__hint">{{ form.replace_existing.description }}</div>
                {% endif %}
            </div>
        </div>

        <div class="govuk-button-group">
            <button type="submit" class="govuk-button" data-module="govuk-button">
                {{ _("Upload CSV") }}
            </button>
        </div>
    </form>

    {# ── Summary Stats ──────────────────────────────────────── #}
    <hr class="govuk-section-break govuk-section-break--l govuk-section-break--visible">
    <h2 class="govuk-heading-m">{{ _("Current Respondents") }}</h2>

    {% if assembly.csv and assembly.csv.last_import_filename %}
        <dl class="govuk-summary-list govuk-!-margin-bottom-6">
            <div class="govuk-summary-list__row">
                <dt class="govuk-summary-list__key">{{ _("Last import file") }}</dt>
                <dd class="govuk-summary-list__value">{{ assembly.csv.last_import_filename }}</dd>
            </div>
            <div class="govuk-summary-list__row">
                <dt class="govuk-summary-list__key">{{ _("Last import date") }}</dt>
                <dd class="govuk-summary-list__value">
                    {% if assembly.csv.last_import_timestamp %}
                        {{ assembly.csv.last_import_timestamp.strftime("%d %B %Y at %H:%M") }}
                    {% else %}
                        <span class="govuk-hint">{{ _("N/A") }}</span>
                    {% endif %}
                </dd>
            </div>
            <div class="govuk-summary-list__row">
                <dt class="govuk-summary-list__key">{{ _("ID column") }}</dt>
                <dd class="govuk-summary-list__value">{{ assembly.csv.id_column }}</dd>
            </div>
        </dl>
    {% endif %}

    {% if total_count > 0 %}
        <dl class="govuk-summary-list govuk-!-margin-bottom-6">
            <div class="govuk-summary-list__row">
                <dt class="govuk-summary-list__key">{{ _("Total respondents") }}</dt>
                <dd class="govuk-summary-list__value">{{ total_count }}</dd>
            </div>
            <div class="govuk-summary-list__row">
                <dt class="govuk-summary-list__key">{{ _("Available for selection") }}</dt>
                <dd class="govuk-summary-list__value">{{ available_count }}</dd>
            </div>
        </dl>

        {# ── Respondent Table ──────────────────────────────── #}
        <p class="govuk-body">
            {{ _("Showing %(start)s to %(end)s of %(total)s respondents",
                start=(page - 1) * per_page + 1,
                end=((page - 1) * per_page + respondents|length),
                total=total_count) }}
        </p>

        <table class="govuk-table">
            <thead class="govuk-table__head">
                <tr class="govuk-table__row">
                    <th scope="col" class="govuk-table__header">{{ _("External ID") }}</th>
                    <th scope="col" class="govuk-table__header">{{ _("Email") }}</th>
                    <th scope="col" class="govuk-table__header">{{ _("Status") }}</th>
                    <th scope="col" class="govuk-table__header">{{ _("Consent") }}</th>
                    <th scope="col" class="govuk-table__header">{{ _("Eligible") }}</th>
                    <th scope="col" class="govuk-table__header">{{ _("Source") }}</th>
                </tr>
            </thead>
            <tbody class="govuk-table__body">
                {% for respondent in respondents %}
                    <tr class="govuk-table__row">
                        <td class="govuk-table__cell">{{ respondent.external_id }}</td>
                        <td class="govuk-table__cell">{{ respondent.email or "-" }}</td>
                        <td class="govuk-table__cell">
                            <strong class="govuk-tag govuk-tag--{% if respondent.selection_status.value == 'POOL' %}grey{% elif respondent.selection_status.value == 'SELECTED' %}blue{% elif respondent.selection_status.value == 'CONFIRMED' %}green{% else %}yellow{% endif %}">
                                {{ respondent.selection_status.value }}
                            </strong>
                        </td>
                        <td class="govuk-table__cell">
                            {% if respondent.consent is none %}-{% elif respondent.consent %}Yes{% else %}No{% endif %}
                        </td>
                        <td class="govuk-table__cell">
                            {% if respondent.eligible is none %}-{% elif respondent.eligible %}Yes{% else %}No{% endif %}
                        </td>
                        <td class="govuk-table__cell">{{ respondent.source_type.value }}</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>

        {# ── Pagination ────────────────────────────────────── #}
        {% if total_pages > 1 %}
            <nav class="govuk-pagination" role="navigation" aria-label="Pagination">
                {% if page > 1 %}
                    <div class="govuk-pagination__prev">
                        <a class="govuk-link govuk-pagination__link"
                            href="{{ url_for('respondents.view_assembly_respondents', assembly_id=assembly.id, page=page-1) }}"
                            rel="prev">
                            <svg class="govuk-pagination__icon govuk-pagination__icon--prev"
                                xmlns="http://www.w3.org/2000/svg" height="13" width="15"
                                aria-hidden="true" focusable="false" viewBox="0 0 15 13">
                                <path d="m6.5938-0.0078125-6.7266 6.7266 6.7441 6.4062 1.377-1.449-4.1856-3.9768h12.896v-2h-12.984l4.2931-4.293-1.414-1.414z"></path>
                            </svg>
                            <span class="govuk-pagination__link-title">{{ _("Previous") }}</span>
                        </a>
                    </div>
                {% endif %}
                <ul class="govuk-pagination__list">
                    {% for p in range(1, total_pages + 1) %}
                        {% if p == page %}
                            <li class="govuk-pagination__item govuk-pagination__item--current">
                                <a class="govuk-link govuk-pagination__link" href="#"
                                    aria-label="Page {{ p }}" aria-current="page">{{ p }}</a>
                            </li>
                        {% elif (p == 1) or (p == total_pages) or (p >= page - 2 and p <= page + 2) %}
                            <li class="govuk-pagination__item">
                                <a class="govuk-link govuk-pagination__link"
                                    href="{{ url_for('respondents.view_assembly_respondents', assembly_id=assembly.id, page=p) }}"
                                    aria-label="Page {{ p }}">{{ p }}</a>
                            </li>
                        {% elif (p == page - 3) or (p == page + 3) %}
                            <li class="govuk-pagination__item govuk-pagination__item--ellipses">&ctdot;</li>
                        {% endif %}
                    {% endfor %}
                </ul>
                {% if page < total_pages %}
                    <div class="govuk-pagination__next">
                        <a class="govuk-link govuk-pagination__link"
                            href="{{ url_for('respondents.view_assembly_respondents', assembly_id=assembly.id, page=page+1) }}"
                            rel="next">
                            <span class="govuk-pagination__link-title">{{ _("Next") }}</span>
                            <svg class="govuk-pagination__icon govuk-pagination__icon--next"
                                xmlns="http://www.w3.org/2000/svg" height="13" width="15"
                                aria-hidden="true" focusable="false" viewBox="0 0 15 13">
                                <path d="m8.107-0.0078125-1.4136 1.414 4.2926 4.293h-12.986v2h12.896l-4.1855 3.9766 1.377 1.4492 6.7441-6.4062-6.7246-6.7266z"></path>
                            </svg>
                        </a>
                    </div>
                {% endif %}
            </nav>
        {% endif %}
    {% else %}
        <p class="govuk-body">{{ _("No respondents imported yet. Upload a CSV file to get started.") }}</p>
    {% endif %}
{% endblock %}
```

---

## Part 5: Configuration Change

### 5.1 Add `MAX_CONTENT_LENGTH` to Flask config

**File:** `src/opendlp/config.py` — add to `FlaskBaseConfig.__init__()`:

```python
# File upload limits (10 MB)
self.MAX_CONTENT_LENGTH = 10 * 1024 * 1024
```

This causes Flask to reject uploads larger than 10 MB with a 413 error before our code runs. We should also add a handler for this in the error handlers. In `flask_app.py`, the existing error handler registration should catch `RequestEntityTooLarge` via the general HTTPException handler, but it's worth verifying.

---

## Part 6: Service Layer — Track Upload Metadata

The `import_respondents_from_csv` function does NOT currently update `last_import_filename` or `last_import_timestamp` on the `AssemblyCSV` config. The route handles this by calling `update_csv_config()` after a successful import. This keeps the service layer function pure (it doesn't know about filenames).

For targets, there is no `AssemblyCSV` config tracking. Targets are a simpler model — the data itself (categories + values) is the record. No separate metadata tracking is needed for the first version.

---

## Part 7: Performance Consideration

**Important:** `get_assembly_with_permissions()` calls `assembly.create_detached_copy()` which eagerly copies ALL respondents and target_categories. For the new tabs:

- **Targets tab:** Uses `uow.target_categories.get_by_assembly_id()` directly — the assembly's `target_categories` from `get_assembly_with_permissions` are not used for display. This is fine since target categories are typically small (< 50 rows).
- **Respondents tab:** Uses `uow.respondents.get_by_assembly_id()` directly and paginates in Python. For a future optimization, a `get_by_assembly_id_paginated()` repository method with SQL-level LIMIT/OFFSET would be better, but in-Python slicing works for an initial implementation.

If assemblies with thousands of respondents become common, two improvements should be made:

1. Add a `count_by_assembly_id()` method to the respondent repository (SQL COUNT instead of loading all objects).
2. Add `get_by_assembly_id_paginated(assembly_id, page, per_page)` to the respondent repository.
3. Stop calling `get_assembly_with_permissions()` and instead just get the assembly without the eager copy of respondents (or make `create_detached_copy` not copy respondents).

For now, the approach works and matches existing patterns (e.g. `view_assembly_data` also loads via `get_assembly_with_permissions`).

---

## Part 8: File Inventory

### New Files

| File                                                | Purpose                                               |
| --------------------------------------------------- | ----------------------------------------------------- |
| `src/opendlp/entrypoints/blueprints/targets.py`     | Targets blueprint: view + CSV upload (2 routes)       |
| `src/opendlp/entrypoints/blueprints/respondents.py` | Respondents blueprint: view + CSV upload (2 routes)   |
| `templates/targets/view_targets.html`                | Targets tab: upload form + current targets display    |
| `templates/respondents/view_respondents.html`        | Respondents tab: upload form + stats + paginated table|

### Modified Files

| File                                     | Change                                                                     |
| ---------------------------------------- | -------------------------------------------------------------------------- |
| `src/opendlp/entrypoints/flask_app.py`   | Register `targets_bp` and `respondents_bp` blueprints                      |
| `src/opendlp/entrypoints/forms.py`       | Add `FileField` import, `UploadRespondentsCsvForm`, `UploadTargetsCsvForm` |
| `templates/main/view_assembly_base.html` | Add Targets and Respondents tabs to service navigation                     |
| `src/opendlp/config.py`                  | Add `MAX_CONTENT_LENGTH = 10 * 1024 * 1024`                               |

### Test Files to Create

| File                                             | Purpose                                                                                  |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| `tests/e2e/test_targets_pages.py`                | Flask test client tests for targets tab: GET render, POST upload, error cases            |
| `tests/e2e/test_respondents_pages.py`            | Flask test client tests for respondents tab: GET render, POST upload, error cases        |
| `tests/integration/test_targets_routes.py`       | Route-level tests: permission checks, form validation, redirect behaviour                |
| `tests/integration/test_respondents_routes.py`   | Route-level tests: permission checks, form validation, redirect behaviour                |
| `tests/unit/test_csv_upload_forms.py`            | Unit tests for form validation (file type, required fields)                              |

---

## Part 9: Implementation Order

1. **Forms** — `UploadRespondentsCsvForm` and `UploadTargetsCsvForm` in `forms.py`
2. **Config** — Add `MAX_CONTENT_LENGTH` to `config.py`
3. **Targets blueprint** — Create `targets.py` with view + upload routes
4. **Respondents blueprint** — Create `respondents.py` with view + upload routes
5. **Register** — Add both blueprint registrations in `flask_app.py`
6. **Templates** — Create `templates/targets/` and `templates/respondents/` directories and templates
7. **Tab navigation** — Modify `view_assembly_base.html` to add the two new tabs
8. **Tests** — Write tests for routes, forms, and end-to-end flows (split by blueprint)
9. **Translations** — Run `just translate-regen` to pick up new translatable strings
10. **Quality** — Run `just check` and `just test` to verify everything passes

---

## Part 10: Example CSV Files for Testing

### `test_targets.csv`

```csv
feature,value,min,max,min_flex,max_flex
Gender,Male,8,12,0,0
Gender,Female,8,12,0,0
Gender,Non-binary,1,3,0,0
Age,18-35,5,10,0,0
Age,36-55,5,10,0,0
Age,56+,3,8,0,0
```

### `test_respondents.csv`

```csv
external_id,email,name,age,gender,consent,eligible
R001,alice@example.com,Alice Smith,34,Female,true,true
R002,bob@example.com,Bob Jones,45,Male,true,true
R003,carol@example.com,Carol White,28,Non-binary,true,true
R004,dave@example.com,Dave Brown,62,Male,true,false
R005,,Eve Black,19,Female,false,true
```

---

## Part 11: Detailed TODO List

### Phase 1: Foundation (forms + config)

- [x] **1.1** Add `FileField`, `FileAllowed`, `FileRequired` imports to `src/opendlp/entrypoints/forms.py`
- [x] **1.2** Add `UploadTargetsCsvForm` class to `forms.py` (fields: `csv_file`, `replace_existing`)
- [x] **1.3** Add `UploadRespondentsCsvForm` class to `forms.py` (fields: `csv_file`, `replace_existing`, `id_column`)
- [x] **1.4** Add `MAX_CONTENT_LENGTH = 10 * 1024 * 1024` to `FlaskBaseConfig.__init__()` in `src/opendlp/config.py`
- [x] **1.5** Verify the existing error handlers in `flask_app.py` handle 413 `RequestEntityTooLarge` (from the general `HTTPException` handler) — added a specific 413 handler and template

### Phase 2: Targets blueprint

- [x] **2.1** Create `src/opendlp/entrypoints/blueprints/targets.py` with ABOUTME comment
- [x] **2.2** Define `targets_bp = Blueprint("targets", __name__)`
- [x] **2.3** Implement `view_assembly_targets` GET route (`/assemblies/<uuid:assembly_id>/targets`)
  - [x] Call `get_assembly_with_permissions` for auth
  - [x] Query `uow.target_categories.get_by_assembly_id()` for display data
  - [x] Create `UploadTargetsCsvForm` instance
  - [x] Render `targets/view_targets.html` with `current_tab="targets"`
  - [x] Handle `NotFoundError`, `InsufficientPermissions`, generic `Exception`
- [x] **2.4** Implement `upload_targets_csv` POST route (`/assemblies/<uuid:assembly_id>/targets/upload`)
  - [x] Validate form; on failure re-render the view with errors
  - [x] Read uploaded file with `utf-8-sig` decoding
  - [x] Call `import_targets_from_csv` service function
  - [x] Flash success message with category/value counts and filename
  - [x] Redirect back to `targets.view_assembly_targets`
  - [x] Handle `InvalidSelection`, `NotFoundError`, `InsufficientPermissions`, `UnicodeDecodeError`, generic `Exception`
- [x] **2.5** Register `targets_bp` in `register_blueprints()` in `src/opendlp/entrypoints/flask_app.py`

### Phase 3: Respondents blueprint

- [x] **3.1** Create `src/opendlp/entrypoints/blueprints/respondents.py` with ABOUTME comment
- [x] **3.2** Define `respondents_bp = Blueprint("respondents", __name__)`
- [x] **3.3** Implement `view_assembly_respondents` GET route (`/assemblies/<uuid:assembly_id>/respondents`)
  - [x] Call `get_assembly_with_permissions` for auth
  - [x] Query `uow.respondents.get_by_assembly_id()` for full list
  - [x] Call `uow.respondents.count_available_for_selection()` for summary stat
  - [x] Paginate respondent list in Python (page/per_page from query string)
  - [x] Create `UploadRespondentsCsvForm` and pre-fill `id_column` from `assembly.csv`
  - [x] Render `respondents/view_respondents.html` with `current_tab="respondents"`
  - [x] Pass context: `assembly`, `respondents`, `total_count`, `available_count`, `form`, `page`, `per_page`, `total_pages`
  - [x] Handle `NotFoundError`, `InsufficientPermissions`, generic `Exception`
- [x] **3.4** Implement `upload_respondents_csv` POST route (`/assemblies/<uuid:assembly_id>/respondents/upload`)
  - [x] Validate form; on failure re-render the view with errors
  - [x] Read uploaded file with `utf-8-sig` decoding
  - [x] Extract `id_column` from form (strip, or None if blank)
  - [x] Call `import_respondents_from_csv` service function
  - [x] Call `update_csv_config` to record `last_import_filename` and `last_import_timestamp`
  - [x] Flash success message with imported count and filename
  - [x] If soft errors returned, flash warning with first 10 errors summarised
  - [x] Redirect back to `respondents.view_assembly_respondents`
  - [x] Handle `InvalidSelection`, `NotFoundError`, `InsufficientPermissions`, `UnicodeDecodeError`, generic `Exception`
- [x] **3.5** Register `respondents_bp` in `register_blueprints()` in `src/opendlp/entrypoints/flask_app.py`

### Phase 4: Templates

- [x] **4.1** Create `templates/targets/` directory
- [x] **4.2** Create `templates/targets/view_targets.html`
  - [x] Extend `main/view_assembly_base.html`
  - [x] Add breadcrumb: "Targets"
  - [x] GOV.UK error summary block for form errors
  - [x] Upload form with `enctype="multipart/form-data"`, action pointing to `targets.upload_targets_csv`
  - [x] `{{ form.hidden_tag() }}` for CSRF
  - [x] File upload field using `govuk-file-upload` class
  - [x] "Replace all existing targets" checkbox using `govuk-checkboxes`
  - [x] Submit button
  - [x] Horizontal rule separator
  - [x] "Current Target Categories" section heading with count
  - [x] Loop over `target_categories`: heading per category, table per category with columns Value/Min/Max/Min Flex/Max Flex
  - [x] Empty state message when no categories exist
- [x] **4.3** Create `templates/respondents/` directory
- [x] **4.4** Create `templates/respondents/view_respondents.html`
  - [x] Extend `main/view_assembly_base.html`
  - [x] Add breadcrumb: "Respondents"
  - [x] GOV.UK error summary block for form errors
  - [x] Upload form with `enctype="multipart/form-data"`, action pointing to `respondents.upload_respondents_csv`
  - [x] `{{ form.hidden_tag() }}` for CSRF
  - [x] File upload field using `govuk-file-upload` class
  - [x] ID column text field using `govuk-input govuk-!-width-one-third`
  - [x] "Replace all existing respondents" checkbox using `govuk-checkboxes`
  - [x] Submit button
  - [x] Horizontal rule separator
  - [x] Import metadata summary list (last import file, date, ID column) — conditional on `assembly.csv` existing
  - [x] Stats summary list (total respondents, available for selection) — conditional on `total_count > 0`
  - [x] "Showing X to Y of Z respondents" text
  - [x] Respondent table with columns: External ID, Email, Status (with coloured `govuk-tag`), Consent, Eligible, Source
  - [x] GOV.UK pagination component (Previous/Next, page numbers with ellipsis)
  - [x] Empty state message when no respondents exist

### Phase 5: Tab navigation

- [x] **5.1** Edit `templates/main/view_assembly_base.html` — add Targets tab `<li>` between Details and Data & Selection
  - [x] Link to `targets.view_assembly_targets`
  - [x] Active class conditional on `current_tab == 'targets'`
- [x] **5.2** Edit `templates/main/view_assembly_base.html` — add Respondents tab `<li>` between Targets and Data & Selection
  - [x] Link to `respondents.view_assembly_respondents`
  - [x] Active class conditional on `current_tab == 'respondents'`

### Phase 6: Tests — targets

- [x] **6.1** Create `tests/e2e/test_targets_pages.py`
  - [x] Test: GET targets page renders successfully (200, contains "Targets" heading)
  - [x] Test: GET targets page shows empty state when no targets exist
  - [x] Test: GET targets page shows existing target categories in tables
  - [x] Test: POST upload with valid CSV creates target categories, redirects with success flash
  - [x] Test: POST upload with replace_existing=True deletes old targets first
  - [x] Test: POST upload with invalid CSV (e.g. min > max) shows error flash
  - [x] Test: POST upload with no file shows form validation error
  - [x] Test: POST upload with non-CSV file shows form validation error
  - [x] Test: GET targets page requires login (redirects to login)
  - [x] Test: GET targets page with non-existent assembly_id shows error
- [x] **6.2** Create `tests/integration/test_targets_routes.py`
  - [x] Test: blueprint registered
  - [x] Test: route requires login
  - [x] Test: upload route requires login
  - [x] Test: invalid assembly_id returns 404

### Phase 7: Tests — respondents

- [x] **7.1** Create `tests/e2e/test_respondents_pages.py`
  - [x] Test: GET respondents page renders successfully (200, contains "Respondents" heading)
  - [x] Test: GET respondents page shows empty state when no respondents exist
  - [x] Test: GET respondents page shows summary stats (total count, available count)
  - [x] Test: GET respondents page shows import metadata when CSV config exists
  - [x] Test: GET respondents page shows paginated respondent table
  - [x] Test: GET respondents page pagination (page=2 works)
  - [x] Test: POST upload with valid CSV creates respondents, redirects with success flash
  - [x] Test: POST upload with replace_existing=True deletes old respondents first
  - [x] Test: POST upload with CSV missing id_column shows error flash
  - [x] Test: POST upload with duplicate rows shows warning flash with skipped count
  - [x] Test: POST upload updates `last_import_filename` and `last_import_timestamp` on AssemblyCSV
  - [x] Test: POST upload with no file shows form validation error
  - [x] Test: POST upload with custom id_column override works
  - [x] Test: GET respondents page pre-fills id_column from assembly CSV config
  - [x] Test: GET respondents page requires login
- [x] **7.2** Create `tests/integration/test_respondents_routes.py`
  - [x] Test: blueprint registered
  - [x] Test: route requires login
  - [x] Test: upload route requires login
  - [x] Test: invalid assembly_id returns 404

### Phase 8: Tests — forms

- [x] **8.1** Create `tests/unit/test_csv_upload_forms.py`
  - [x] Test: `UploadTargetsCsvForm` requires csv_file (validation fails without it)
  - [x] Test: `UploadTargetsCsvForm` rejects non-CSV file extension
  - [x] Test: `UploadTargetsCsvForm` accepts valid CSV file
  - [x] Test: `UploadTargetsCsvForm` replace_existing defaults to False
  - [x] Test: `UploadRespondentsCsvForm` requires csv_file
  - [x] Test: `UploadRespondentsCsvForm` rejects non-CSV file extension
  - [x] Test: `UploadRespondentsCsvForm` accepts valid CSV file
  - [x] Test: `UploadRespondentsCsvForm` id_column is optional (blank is valid)
  - [x] Test: `UploadRespondentsCsvForm` id_column respects max length 100

### Phase 9: Translations and quality

- [x] **9.1** Run `just translate-regen` to extract new translatable strings
- [x] **9.2** Run `just check` (mypy, deptry, linting) — all pass
- [x] **9.3** Run `just test` — all 1255 tests pass, 90.03% coverage
- [ ] **9.4** Manual smoke test: start app with `just run`, navigate to an assembly, verify both new tabs render and uploads work
