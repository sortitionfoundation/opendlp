# Selection with Data in Database: Implementation Plan

**Date:** 2026-03-03
**Target:** GOV.UK frontend (main blueprint). Backoffice version later.
**Scope:** Initial selection only. Replacement is out of scope (placeholder page).

---

## 1. Overview of Changes

1. Rename "Data & Selection" nav tab to "Selection (GSheet)"
2. Add new "Selection (DB)" nav tab
3. Create new `db_selection` blueprint with routes for:
   - DB selection page (run selection, run test selection, check data)
   - Progress polling via HTMX
   - Cancel task
   - Download selected/remaining CSVs
4. Add status filter to respondents page
5. Extend `view_gsheet_run` to route DB task types
6. Create an AssemblyCSV settings page (needed for `columns_to_keep`, address checking, etc.)

---

## 2. Navigation Change

### 2.1 Update `templates/main/view_assembly_base.html`

Rename "Data & Selection" to "Selection (GSheet)" and add a new "Selection (DB)" tab:

```html
<li
  class="govuk-service-navigation__item {% if current_tab == 'data' %}govuk-service-navigation__item--active{% endif %}"
>
  <a
    class="govuk-service-navigation__link"
    href="{{ url_for('main.view_assembly_data', assembly_id=assembly.id) }}"
  >
    {{ _("Selection (GSheet)") }}
  </a>
</li>
<li
  class="govuk-service-navigation__item {% if current_tab == 'db_selection' %}govuk-service-navigation__item--active{% endif %}"
>
  <a
    class="govuk-service-navigation__link"
    href="{{ url_for('db_selection.view_db_selection', assembly_id=assembly.id) }}"
  >
    {{ _("Selection (DB)") }}
  </a>
</li>
```

---

## 3. New Blueprint: `db_selection`

### 3.1 File: `src/opendlp/entrypoints/blueprints/db_selection.py`

New blueprint for database-based selection routes.

#### Route Table

| Route                                                    | Method | Handler                      | Purpose                         |
| -------------------------------------------------------- | ------ | ---------------------------- | ------------------------------- |
| `/assemblies/<id>/db_select`                             | GET    | `view_db_selection`          | Display selection page          |
| `/assemblies/<id>/db_select/<run_id>`                    | GET    | `view_db_selection_with_run` | Selection page with task status |
| `/assemblies/<id>/db_select/check`                       | POST   | `check_db_data`              | Synchronous data validation     |
| `/assemblies/<id>/db_select/run`                         | POST   | `start_db_selection`         | Start selection (real or test)  |
| `/assemblies/<id>/db_select/<run_id>/progress`           | GET    | `db_selection_progress`      | HTMX polling endpoint           |
| `/assemblies/<id>/db_select/<run_id>/cancel`             | POST   | `cancel_db_selection`        | Cancel running task             |
| `/assemblies/<id>/db_select/<run_id>/download/selected`  | GET    | `download_selected_csv`      | Download selected CSV           |
| `/assemblies/<id>/db_select/<run_id>/download/remaining` | GET    | `download_remaining_csv`     | Download remaining CSV          |
| `/assemblies/<id>/db_select/settings`                    | GET    | `view_db_selection_settings` | View/edit AssemblyCSV settings  |
| `/assemblies/<id>/db_select/settings`                    | POST   | `save_db_selection_settings` | Save AssemblyCSV settings       |
| `/assemblies/<id>/db_replace`                            | GET    | `view_db_replacement`        | Placeholder replacement page    |

#### 3.2 Route Implementation: Skeleton

```python
"""ABOUTME: Database selection routes for running sortition on DB-stored data
ABOUTME: Handles selection, validation, progress tracking and CSV downloads"""

import uuid

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from sortition_algorithms import adapters
from sortition_algorithms.errors import SortitionBaseError

from opendlp import bootstrap
from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.value_objects import SelectionTaskType
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.service_layer.assembly_service import (
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_or_create_csv_config,
    update_csv_config,
)
from opendlp.service_layer.error_translation import translate_sortition_error_to_html
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.service_layer.report_translation import translate_run_report_to_html
from opendlp.service_layer.sortition import (
    cancel_task,
    check_and_update_task_health,
    generate_selection_csvs,
    get_selection_run_status,
    start_db_select_task,
)
from opendlp.translations import gettext as _

from ..forms import DbSelectionSettingsForm

db_selection_bp = Blueprint("db_selection", __name__)
```

#### 3.3 View Selection Page (GET, no run)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display database selection page."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
```

#### 3.4 View Selection Page with Run Status (GET with run_id)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Display database selection page with task status."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
            result = get_selection_run_status(uow, run_id)

        if result.run_record and result.run_record.assembly_id != assembly_id:
            flash(_("Invalid task ID for this assembly"), "error")
            return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            run_record=result.run_record,
            run_report=result.run_report,
            translated_report_html=translate_run_report_to_html(result.run_report),
            run_id=run_id,
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
```

#### 3.5 Check Data (POST, synchronous)

This is the key difference from GSheet — no Celery task needed. We call `load_features()` and `load_people()` directly. Errors from the sortition-algorithms library are caught and displayed inline.

The business logic lives in a service layer function (`check_db_selection_data` in `sortition.py`); the route is a thin wrapper.

#### Service layer function (add to `src/opendlp/service_layer/sortition.py`)

```python
@dataclass
class CheckDataResult:
    """Result of validating targets and respondents against selection settings."""

    success: bool
    errors: list[str]
    features_report_html: str
    people_report_html: str
    num_features: int
    num_people: int


@require_assembly_permission(can_manage_assembly)
def check_db_selection_data(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> CheckDataResult:
    """Synchronously validate targets and respondents against selection settings.

    Loads features and people via the sortition-algorithms library to trigger
    all consistency checks. Returns a result dataclass with validation outcome.
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    csv_config = assembly.csv if assembly.csv is not None else AssemblyCSV(assembly_id=assembly_id)
    settings_obj = csv_config.to_settings()

    data_source = OpenDLPDataAdapter(uow, assembly_id)
    select_data = adapters.SelectionData(data_source)

    check_errors: list[str] = []
    features = None
    people = None
    features_report_html = ""
    people_report_html = ""

    # Step 1: Load and validate features (target categories)
    try:
        features, f_report = select_data.load_features()
        features_report_html = translate_run_report_to_html(f_report)
    except SortitionBaseError as e:
        check_errors.append(translate_sortition_error_to_html(e))

    # Step 2: Load and validate people (respondents) against features
    if features is not None:
        try:
            people, p_report = select_data.load_people(settings_obj, features)
            people_report_html = translate_run_report_to_html(p_report)
        except SortitionBaseError as e:
            check_errors.append(translate_sortition_error_to_html(e))

    return CheckDataResult(
        success=not check_errors,
        errors=check_errors,
        features_report_html=features_report_html,
        people_report_html=people_report_html,
        num_features=len(features) if features else 0,
        num_people=people.count if people else 0,
    )
```

#### Route handler (thin wrapper)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/check", methods=["POST"])
@login_required
@require_assembly_management
def check_db_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Synchronously validate targets and respondents against selection settings."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        check_result = check_db_selection_data(uow=uow, user_id=current_user.id, assembly_id=assembly_id)

        return render_template(
            "db_selection/select.html",
            assembly=assembly,
            csv_config=csv_config,
            current_tab="db_selection",
            check_result={
                "success": check_result.success,
                "errors": check_result.errors,
                "features_report_html": check_result.features_report_html,
                "people_report_html": check_result.people_report_html,
                "num_features": check_result.num_features,
                "num_people": check_result.num_people,
            },
        ), 200
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Check data error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred while checking data"), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
```

#### 3.6 Start Selection (POST)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/run", methods=["POST"])
@login_required
@require_assembly_management
def start_db_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start a database selection task (real or test)."""
    test_selection = request.form.get("test_selection") == "1"
    try:
        uow = bootstrap.bootstrap()
        with uow:
            task_id = start_db_select_task(uow, current_user.id, assembly_id, test_selection=test_selection)

        return redirect(url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=task_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid selection for assembly {assembly_id}: {e}")
        flash(_("Could not start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        current_app.logger.warning(f"Failed to start db select for assembly {assembly_id}: {e}")
        flash(_("Failed to start selection task: %(error)s", error=str(e)), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id}: {e}")
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error starting db select for assembly {assembly_id}: {e}")
        flash(_("An unexpected error occurred while starting the selection task"), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
```

#### 3.7 Progress Polling (GET, HTMX fragment)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/progress", methods=["GET"])
@login_required
@require_assembly_management
def db_selection_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return progress fragment for HTMX polling."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            check_and_update_task_health(uow, run_id)
            result = get_selection_run_status(uow, run_id)

        if not result.run_record:
            return "", 404
        if result.run_record.assembly_id != assembly_id:
            return "", 404

        response = current_app.make_response((
            render_template(
                "db_selection/components/progress.html",
                assembly=assembly,
                run_record=result.run_record,
                translated_report_html=translate_run_report_to_html(result.run_report),
                run_id=run_id,
                progress_url=url_for(
                    "db_selection.db_selection_progress", assembly_id=assembly_id, run_id=run_id
                ),
            ),
            200,
        ))
        if result.run_record.has_finished:
            response.headers["HX-Refresh"] = "true"
        return response
    except (NotFoundError, InsufficientPermissions):
        return "", 404
    except Exception as e:
        current_app.logger.error(f"Progress polling error for assembly {assembly_id}: {e}")
        return "", 500
```

#### 3.8 Cancel (POST)

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_db_selection(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running database selection task."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            cancel_task(uow, current_user.id, assembly_id, run_id)
        flash(_("Task has been cancelled"), "success")
        return redirect(
            url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except NotFoundError as e:
        current_app.logger.warning(f"Task {run_id} not found for cancellation: {e}")
        flash(_("Task not found"), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        current_app.logger.warning(f"Cannot cancel task {run_id}: {e}")
        flash(str(e), "error")
        return redirect(
            url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions to cancel task {run_id}: {e}")
        flash(_("You don't have permission to cancel this task"), "error")
        return redirect(url_for("main.dashboard"))
```

#### 3.9 CSV Downloads

```python
@db_selection_bp.route(
    "/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/selected", methods=["GET"]
)
@login_required
@require_assembly_management
def download_selected_csv(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Download CSV of selected respondents from a completed selection run."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            get_assembly_with_permissions(uow, assembly_id, current_user.id)
            selected_csv, _remaining_csv = generate_selection_csvs(uow, assembly_id, run_id)

        return Response(
            selected_csv,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=selected-{run_id}.csv"},
        )
    except NotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(
            url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route(
    "/assemblies/<uuid:assembly_id>/db_select/<uuid:run_id>/download/remaining", methods=["GET"]
)
@login_required
@require_assembly_management
def download_remaining_csv(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Download CSV of remaining respondents from a completed selection run."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            get_assembly_with_permissions(uow, assembly_id, current_user.id)
            _selected_csv, remaining_csv = generate_selection_csvs(uow, assembly_id, run_id)

        return Response(
            remaining_csv,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=remaining-{run_id}.csv"},
        )
    except NotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))
    except InvalidSelection as e:
        flash(str(e), "error")
        return redirect(
            url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
        )
    except InsufficientPermissions:
        flash(_("You don't have permission to download this data"), "error")
        return redirect(url_for("main.dashboard"))
```

#### 3.10 Selection Settings Page

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["GET"])
@login_required
@require_assembly_management
def view_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """View/edit AssemblyCSV selection settings."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

        form = DbSelectionSettingsForm(obj=csv_config)
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))


@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/settings", methods=["POST"])
@login_required
@require_assembly_management
def save_db_selection_settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save AssemblyCSV selection settings."""
    try:
        form = DbSelectionSettingsForm()
        if form.validate_on_submit():
            uow = bootstrap.bootstrap()
            update_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                selection_algorithm="maximin",
                check_same_address=form.check_same_address.data or False,
                check_same_address_cols=_parse_comma_list(form.check_same_address_cols_string.data),
                columns_to_keep=_parse_comma_list(form.columns_to_keep_string.data),
            )
            flash(_("Selection settings saved"), "success")
            return redirect(url_for("db_selection.view_db_selection", assembly_id=assembly_id))

        # Re-render with validation errors
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
        return render_template(
            "db_selection/settings.html",
            assembly=assembly,
            csv_config=csv_config,
            form=form,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("main.dashboard"))


def _parse_comma_list(value: str | None) -> list[str]:
    """Parse a comma-separated string into a list of stripped, non-empty strings."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
```

#### 3.11 Replacement Placeholder

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_replace", methods=["GET"])
@login_required
@require_assembly_management
def view_db_replacement(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Placeholder replacement page — not yet implemented."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        return render_template(
            "db_selection/replace.html",
            assembly=assembly,
            current_tab="db_selection",
        ), 200
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
```

---

## 4. Form: `DbSelectionSettingsForm`

### 4.1 Add to `src/opendlp/entrypoints/forms.py`

The selection algorithm is hardcoded to "maximin" and not exposed to the user. The `save_db_selection_settings` route always passes `selection_algorithm="maximin"` to `update_csv_config`.

```python
class DbSelectionSettingsForm(FlaskForm):
    """Form for editing AssemblyCSV selection settings."""

    check_same_address = BooleanField(
        _l("Check Same Address"),
        default=True,
        description=_l("Prevent selecting multiple participants from the same address"),
    )

    check_same_address_cols_string = StringField(
        _l("Address Columns"),
        validators=[Optional(), Length(max=500)],
        description=_l("Comma-separated respondent attribute names used for address matching"),
    )

    columns_to_keep_string = StringField(
        _l("Columns to Keep"),
        validators=[Optional(), Length(max=1000)],
        description=_l("Comma-separated respondent attribute names to include in CSV output"),
    )
```

---

## 5. Templates

### 5.1 `templates/db_selection/select.html`

Main DB selection page. Shows:

- Selection info (number to select)
- Action buttons (Run Selection, Run Test Selection, Check Data)
- Link to settings page
- Link to replacement page (placeholder)
- Check result (if just ran a check)
- Progress/results (if a task is running or completed)
- Download links (if completed)

```html
{% extends "main/view_assembly_base.html" %} {% block title %}{{ _("Selection
(DB)") }} - {{ assembly.title }} - OpenDLP{% endblock %} {% block
assembly_breadcrumbs %}
<li class="govuk-breadcrumbs__list-item">{{ _("Selection (DB)") }}</li>
{% endblock %} {% block assembly_content %}
<h2 class="govuk-heading-m">{{ _("Selection") }}</h2>
<p class="govuk-body">
  {{ _("Run the democratic lottery selection for this assembly using data stored
  in the database.") }}
</p>
<p class="govuk-body">
  {{ _('Selection will be for <b>%(number_to_select)s people</b>.',
  number_to_select=assembly.number_to_select) }} {% if not run_record or
  run_record.has_finished %}
  <a href="{{ url_for('main.edit_assembly', assembly_id=assembly.id) }}"
    >{{ _("Edit the number.") }}</a
  >
  {% endif %}
</p>

{# ── Action Buttons ─────────────────────────────────────── #}
<div class="govuk-button-group govuk-button-group-mixed govuk-!-margin-top-6">
  {% if not run_record or run_record.has_finished %}
  <form
    action="{{ url_for('db_selection.start_db_selection', assembly_id=assembly.id) }}"
    method="post"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <input type="hidden" name="test_selection" value="0" />
    <button type="submit" class="govuk-button">{{ _("Run Selection") }}</button>
  </form>
  <form
    action="{{ url_for('db_selection.start_db_selection', assembly_id=assembly.id) }}"
    method="post"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <input type="hidden" name="test_selection" value="1" />
    <button type="submit" class="govuk-button govuk-button--secondary">
      {{ _("Run Test Selection") }}
    </button>
  </form>
  <form
    action="{{ url_for('db_selection.check_db_data', assembly_id=assembly.id) }}"
    method="post"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <button type="submit" class="govuk-button govuk-button--secondary">
      {{ _("Check Targets & Respondents") }}
    </button>
  </form>
  {% else %}
  <button class="govuk-button" disabled>
    {% if run_record.task_type.value == "select_from_db" %} {{ _("Running
    Selection") }} {% elif run_record.task_type.value == "test_select_from_db"
    %} {{ _("Running Test Selection") }} {% else %} {{ _("Task in Progress...")
    }} {% endif %}
  </button>
  <form
    method="POST"
    action="{{ url_for('db_selection.cancel_db_selection', assembly_id=assembly.id, run_id=run_record.task_id) }}"
    style="display: inline;"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <button
      class="govuk-button govuk-button--warning"
      type="submit"
      data-module="govuk-button"
      data-confirm="{{ _('Are you sure you want to cancel this task?') }}"
    >
      {{ _("Cancel") }}
    </button>
  </form>
  {% endif %}
</div>

{# ── Links ──────────────────────────────────────────────── #}
<div class="govuk-!-margin-bottom-6">
  <a
    href="{{ url_for('db_selection.view_db_selection_settings', assembly_id=assembly.id) }}"
    class="govuk-link"
    >{{ _("Selection Settings") }}</a
  >
  &nbsp;|&nbsp;
  <a
    href="{{ url_for('db_selection.view_db_replacement', assembly_id=assembly.id) }}"
    class="govuk-link"
    >{{ _("Replacements") }}</a
  >
</div>

<hr
  class="govuk-section-break govuk-section-break--l govuk-section-break--visible"
/>

{# ── Check Result (synchronous) ─────────────────────────── #} {% if
check_result is defined and check_result %} {% if check_result.success %}
<div
  class="govuk-notification-banner govuk-notification-banner--success"
  role="alert"
>
  <div class="govuk-notification-banner__header">
    <h2 class="govuk-notification-banner__title">
      {{ _("Data Check Passed") }}
    </h2>
  </div>
  <div class="govuk-notification-banner__content">
    <p class="govuk-body">
      {{ _("Found %(num_features)s target categories and %(num_people)s eligible
      respondents. Data is ready for selection.",
      num_features=check_result.num_features,
      num_people=check_result.num_people) }}
    </p>
  </div>
</div>
{% else %}
<div class="govuk-error-summary" role="alert" tabindex="-1">
  <h2 class="govuk-error-summary__title">{{ _("Data Check Failed") }}</h2>
  <div class="govuk-error-summary__body">
    <ul class="govuk-list govuk-error-summary__list">
      {% for error_html in check_result.errors %}
      <li>{{ error_html | safe }}</li>
      {% endfor %}
    </ul>
  </div>
</div>
{% endif %} {% if check_result.features_report_html or
check_result.people_report_html %}
<details class="govuk-details">
  <summary class="govuk-details__summary">
    <span class="govuk-details__summary-text"
      >{{ _("Validation Details") }}</span
    >
  </summary>
  <div class="govuk-details__text">
    {{ check_result.features_report_html | safe }} {{
    check_result.people_report_html | safe }}
  </div>
</details>
{% endif %} {% endif %} {# ── Download Links (completed run)
─────────────────────── #} {% if run_record and run_record.is_completed and
run_record.selected_ids %}
<div
  class="govuk-notification-banner govuk-notification-banner--success"
  role="alert"
>
  <div class="govuk-notification-banner__header">
    <h2 class="govuk-notification-banner__title">
      {{ _("Selection Complete") }}
    </h2>
  </div>
  <div class="govuk-notification-banner__content">
    <p class="govuk-body">{{ _("Download the results as CSV files:") }}</p>
    <ul class="govuk-list">
      <li>
        <a
          class="govuk-link"
          href="{{ url_for('db_selection.download_selected_csv', assembly_id=assembly.id, run_id=run_record.task_id) }}"
        >
          {{ _("Download Selected") }}
        </a>
      </li>
      <li>
        <a
          class="govuk-link"
          href="{{ url_for('db_selection.download_remaining_csv', assembly_id=assembly.id, run_id=run_record.task_id) }}"
        >
          {{ _("Download Remaining") }}
        </a>
      </li>
    </ul>
  </div>
</div>
{% endif %} {# ── Progress (running task) ─────────────────────────────── #}
<div class="govuk-!-margin-bottom-6">
  {% include "db_selection/components/progress.html" %}
</div>
{% endblock %}
```

### 5.2 `templates/db_selection/components/progress.html`

Follows the same HTMX pattern as the GSheet progress component. Adapted to remove GSheet-specific references.

```html
{# ABOUTME: Progress fragment for DB selection tasks with HTMX polling ABOUTME:
Shows task status, log messages, and report for database selection runs #} {% if
run_record %}
<div
  id="progress-section"
  data-status="{{ run_record.status.value }}"
  data-task-type="{{ run_record.task_type.value }}"
  {%
  if
  not
  run_record.has_finished
  %}
  hx-get="{{ progress_url if progress_url is defined else url_for('db_selection.db_selection_progress', assembly_id=assembly.id, run_id=run_id) }}"
  hx-trigger="every 2s"
  hx-swap="outerHTML"
  {%
  endif
  %}
>
  {% if run_record.has_finished %}
  <details class="govuk-details">
    <summary class="govuk-details__summary">
      <span class="govuk-details__summary-text"
        >{{ _("Full Run Report") }}</span
      >
    </summary>
    <div class="govuk-details__text">
      {% if run_record.log_messages %} {% for message in run_record.log_messages
      %}
      <p class="govuk-body-s">{{ message }}</p>
      {% endfor %} {% endif %}
      <p class="govuk-body-s">{{ translated_report_html | safe }}</p>
      <p class="govuk-body-s">
        {{ _("Started At") }}: {{ run_record.created_at.strftime("%Y-%m-%d
        %H:%M:%S") if run_record.created_at }}
      </p>
      <p class="govuk-body-s">
        {{ _("Completed At") }}: {{ run_record.completed_at.strftime("%Y-%m-%d
        %H:%M:%S") if run_record.completed_at }}
      </p>
    </div>
  </details>
  {% endif %} {% if run_record.is_running and run_record.log_messages %}
  <h4 class="govuk-heading-s">{{ _("Progress Messages") }}</h4>
  <div class="govuk-inset-text">
    {% for message in run_record.log_messages %}
    <p class="govuk-body-s">{{ message }}</p>
    {% endfor %}
  </div>
  {% endif %} {% if run_record.is_pending %}
  <div class="govuk-notification-banner" role="region">
    <div class="govuk-notification-banner__header">
      <h2 class="govuk-notification-banner__title">
        {{ _("Task is Pending") }}
      </h2>
    </div>
    <div class="govuk-notification-banner__content">
      <p class="govuk-notification-banner__heading">
        {{ _("This page will update automatically.") }}
      </p>
    </div>
  </div>
  {% elif run_record.is_running %}
  <div class="govuk-notification-banner" role="region">
    <div class="govuk-notification-banner__header">
      <h2 class="govuk-notification-banner__title">
        {{ _("Task in Progress") }}
      </h2>
    </div>
    <div class="govuk-notification-banner__content">
      <p class="govuk-notification-banner__heading">
        {{ _("This page will update automatically.") }}
      </p>
    </div>
  </div>
  {% elif run_record.is_failed %}
  <h4 class="govuk-heading-s">{{ _("Error Details") }}</h4>
  <div class="govuk-error-summary" role="alert" tabindex="-1">
    <div class="govuk-error-summary__body">
      <ul class="govuk-list govuk-error-summary__list">
        <li>{{ run_record.error_message | safe }}</li>
      </ul>
    </div>
  </div>
  {% elif run_record.is_cancelled %}
  <div class="govuk-warning-text">
    <span class="govuk-warning-text__icon" aria-hidden="true">!</span>
    <strong class="govuk-warning-text__text">
      <span class="govuk-visually-hidden">{{ _("Warning") }}</span>
      {{ _("Task Cancelled") }}
    </strong>
  </div>
  {% if run_record.error_message %}
  <p class="govuk-body-s">{{ run_record.error_message }}</p>
  {% endif %} {% endif %}
</div>
{% endif %}
```

### 5.3 `templates/db_selection/settings.html`

```html
{% extends "main/view_assembly_base.html" %} {% block title %}{{ _("Selection
Settings") }} - {{ assembly.title }} - OpenDLP{% endblock %} {% block
assembly_breadcrumbs %}
<li class="govuk-breadcrumbs__list-item">
  <a
    class="govuk-breadcrumbs__link"
    href="{{ url_for('db_selection.view_db_selection', assembly_id=assembly.id) }}"
    >{{ _("Selection (DB)") }}</a
  >
</li>
<li class="govuk-breadcrumbs__list-item">{{ _("Settings") }}</li>
{% endblock %} {% block assembly_content %}
<h2 class="govuk-heading-m">{{ _("Selection Settings") }}</h2>
<p class="govuk-body">
  {{ _("Configure how the selection runs for this assembly.") }}
</p>

<form
  method="post"
  action="{{ url_for('db_selection.save_db_selection_settings', assembly_id=assembly.id) }}"
  novalidate
>
  {{ form.hidden_tag() }}

  <div
    class="govuk-checkboxes govuk-!-margin-bottom-4"
    data-module="govuk-checkboxes"
  >
    <div class="govuk-checkboxes__item">
      {{ form.check_same_address(class="govuk-checkboxes__input") }}
      <label
        class="govuk-label govuk-checkboxes__label"
        for="{{ form.check_same_address.id }}"
        >{{ form.check_same_address.label.text }}</label
      >
      <div class="govuk-hint govuk-checkboxes__hint">
        {{ form.check_same_address.description }}
      </div>
    </div>
  </div>

  <div class="govuk-form-group">
    <label
      class="govuk-label govuk-label--s"
      for="{{ form.check_same_address_cols_string.id }}"
    >
      {{ form.check_same_address_cols_string.label.text }}
    </label>
    <div class="govuk-hint">
      {{ form.check_same_address_cols_string.description }}
    </div>
    {{ form.check_same_address_cols_string(class="govuk-input") }}
  </div>

  <div class="govuk-form-group">
    <label
      class="govuk-label govuk-label--s"
      for="{{ form.columns_to_keep_string.id }}"
    >
      {{ form.columns_to_keep_string.label.text }}
    </label>
    <div class="govuk-hint">{{ form.columns_to_keep_string.description }}</div>
    {{ form.columns_to_keep_string(class="govuk-input") }}
  </div>

  <div class="govuk-button-group">
    <button type="submit" class="govuk-button">{{ _("Save Settings") }}</button>
    <a
      href="{{ url_for('db_selection.view_db_selection', assembly_id=assembly.id) }}"
      class="govuk-link"
      >{{ _("Cancel") }}</a
    >
  </div>
</form>
{% endblock %}
```

### 5.4 `templates/db_selection/replace.html`

```html
{% extends "main/view_assembly_base.html" %} {% block title %}{{ _("Replacements
(DB)") }} - {{ assembly.title }} - OpenDLP{% endblock %} {% block
assembly_breadcrumbs %}
<li class="govuk-breadcrumbs__list-item">
  <a
    class="govuk-breadcrumbs__link"
    href="{{ url_for('db_selection.view_db_selection', assembly_id=assembly.id) }}"
    >{{ _("Selection (DB)") }}</a
  >
</li>
<li class="govuk-breadcrumbs__list-item">{{ _("Replacements") }}</li>
{% endblock %} {% block assembly_content %}
<h2 class="govuk-heading-m">{{ _("Replacement Selection") }}</h2>
<p class="govuk-body">
  {{ _("Replacement selection from database data is not yet available. This
  feature is coming soon.") }}
</p>
<a
  href="{{ url_for('db_selection.view_db_selection', assembly_id=assembly.id) }}"
  class="govuk-link"
  >{{ _("Back to Selection") }}</a
>
{% endblock %}
```

---

## 6. Register the Blueprint

### 6.1 Find and update the Flask app factory

In the app factory (likely `src/opendlp/entrypoints/flask_app.py` or similar), register the new blueprint:

```python
from opendlp.entrypoints.blueprints.db_selection import db_selection_bp
app.register_blueprint(db_selection_bp)
```

---

## 7. Respondents Page: Show Selection Status Filter

### 7.1 Update `respondents.py` route handler

Add a `status` query parameter to the respondents view. The repository method `get_by_assembly_id` already accepts a `status` filter.

```python
@respondents_bp.route("/assemblies/<uuid:assembly_id>/respondents")
@login_required
def view_assembly_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        # Parse status filter from query params
        status_filter_str = request.args.get("status", "")
        status_filter = None
        if status_filter_str:
            try:
                status_filter = RespondentStatus(status_filter_str)
            except ValueError:
                status_filter = None

        uow2 = bootstrap.bootstrap()
        with uow2:
            all_respondents = uow2.respondents.get_by_assembly_id(
                assembly_id, status=status_filter
            )
            total_count = len(all_respondents)
            available_count = uow2.respondents.count_available_for_selection(assembly_id)

            page = request.args.get("page", 1, type=int)
            # ... pagination logic unchanged ...
            respondents = [r.create_detached_copy() for r in all_respondents[start:end]]

        form = UploadRespondentsCsvForm()
        if assembly.csv and assembly.csv.id_column:
            form.id_column.data = assembly.csv.id_column

        return render_template(
            "respondents/view_respondents.html",
            assembly=assembly,
            respondents=respondents,
            total_count=total_count,
            available_count=available_count,
            form=form,
            page=page,
            per_page=PER_PAGE,
            total_pages=total_pages,
            current_tab="respondents",
            status_filter=status_filter_str,
        )
    # ... error handling unchanged ...
```

### 7.2 Update `templates/respondents/view_respondents.html`

Add a status filter dropdown above the respondent table:

```html
{# ── Status Filter ──────────────────────────────────────── #} {% if
total_count > 0 %}
<div class="govuk-form-group govuk-!-margin-bottom-4">
  <label class="govuk-label govuk-label--s" for="status-filter"
    >{{ _("Filter by status") }}</label
  >
  <select
    class="govuk-select"
    id="status-filter"
    onchange="window.location.href='{{ url_for('respondents.view_assembly_respondents', assembly_id=assembly.id) }}' + (this.value ? '?status=' + this.value : '')"
  >
    <option value="" {% if not status_filter %}selected{% endif %}>
      {{ _("All statuses") }}
    </option>
    <option value="POOL" {% if status_filter="" ="POOL" %}selected{% endif %}>
      {{ _("Pool") }}
    </option>
    <option
      value="SELECTED"
      {%
      if
      status_filter=""
      ="SELECTED"
      %}selected{%
      endif
      %}
    >
      {{ _("Selected") }}
    </option>
    <option
      value="CONFIRMED"
      {%
      if
      status_filter=""
      ="CONFIRMED"
      %}selected{%
      endif
      %}
    >
      {{ _("Confirmed") }}
    </option>
    <option
      value="WITHDRAWN"
      {%
      if
      status_filter=""
      ="WITHDRAWN"
      %}selected{%
      endif
      %}
    >
      {{ _("Withdrawn") }}
    </option>
  </select>
</div>
{% endif %}
```

---

## 8. Extend `view_gsheet_run` Router

### 8.1 Update `gsheets.py` view_gsheet_run

Add handling for `SELECT_FROM_DB` and `TEST_SELECT_FROM_DB` task types. In `gsheets.py:1023-1041`:

```python
        if task_type in (
            SelectionTaskType.LOAD_GSHEET,
            SelectionTaskType.SELECT_GSHEET,
            SelectionTaskType.TEST_SELECT_GSHEET,
        ):
            return redirect(url_for("gsheets.select_assembly_gsheet_with_run", assembly_id=assembly_id, run_id=run_id))
        elif task_type in (
            SelectionTaskType.LOAD_REPLACEMENT_GSHEET,
            SelectionTaskType.SELECT_REPLACEMENT_GSHEET,
        ):
            return redirect(url_for("gsheets.replace_assembly_gsheet_with_run", assembly_id=assembly_id, run_id=run_id))
        elif task_type in (SelectionTaskType.LIST_OLD_TABS, SelectionTaskType.DELETE_OLD_TABS):
            return redirect(
                url_for("gsheets.manage_assembly_gsheet_tabs_with_run", assembly_id=assembly_id, run_id=run_id)
            )
        # ── NEW: Route DB selection task types ──
        elif task_type in (SelectionTaskType.SELECT_FROM_DB, SelectionTaskType.TEST_SELECT_FROM_DB):
            return redirect(
                url_for("db_selection.view_db_selection_with_run", assembly_id=assembly_id, run_id=run_id)
            )
        else:
            current_app.logger.error(f"Unknown task type {task_type} for run {run_id}")
            flash(_("Unknown task type"), "error")
            return redirect(url_for("main.view_assembly_data", assembly_id=assembly_id))
```

---

## 9. Run History

The run history table on `main/view_assembly_data.html` already shows all task types from `SelectionRunRecord`. The "View" link uses `view_gsheet_run`, which we updated above. No change needed to the run history table itself — DB selection runs will appear there automatically since they create `SelectionRunRecord` entries with `SELECT_FROM_DB`/`TEST_SELECT_FROM_DB` task types.

---

## 10. File Summary

### New Files

| File                                                 | Purpose                                    |
| ---------------------------------------------------- | ------------------------------------------ |
| `src/opendlp/entrypoints/blueprints/db_selection.py` | New blueprint with all DB selection routes |
| `templates/db_selection/select.html`                 | Main DB selection page                     |
| `templates/db_selection/components/progress.html`    | HTMX progress polling fragment             |
| `templates/db_selection/settings.html`               | AssemblyCSV settings edit page             |
| `templates/db_selection/replace.html`                | Replacement placeholder page               |

### Modified Files

| File                                                | Change                                                                     |
| --------------------------------------------------- | -------------------------------------------------------------------------- |
| `templates/main/view_assembly_base.html`            | Rename "Data & Selection" → "Selection (GSheet)", add "Selection (DB)" tab |
| `src/opendlp/entrypoints/forms.py`                  | Add `DbSelectionSettingsForm`                                              |
| `src/opendlp/entrypoints/blueprints/gsheets.py`     | Add `SELECT_FROM_DB`/`TEST_SELECT_FROM_DB` handling to `view_gsheet_run`   |
| `src/opendlp/entrypoints/blueprints/respondents.py` | Add `status` query param filtering                                         |
| `templates/respondents/view_respondents.html`       | Add status filter dropdown                                                 |
| Flask app factory                                   | Register `db_selection_bp` blueprint                                       |

---

## 11. Testing Plan

### Unit Tests

- `check_db_data` returns success when features and people are valid
- `check_db_data` returns error HTML when features have problems
- `check_db_data` returns error HTML when respondents don't match features
- `start_db_selection` calls `start_db_select_task` with correct `test_selection` flag
- `download_selected_csv` returns CSV with correct Content-Disposition header
- `download_remaining_csv` returns CSV with correct Content-Disposition header
- `_parse_comma_list` handles empty strings, whitespace, trailing commas
- `DbSelectionSettingsForm` validates correctly

### Integration Tests

- Full flow: upload targets CSV → upload respondents CSV → check data → run selection → download CSVs
- Check data with mismatched respondent attributes shows correct errors
- Progress polling returns correct status updates
- Cancel stops running task
- Settings page saves and loads correctly
- Respondents page filters by status

### E2E Tests

- Selection page loads for assembly with targets and respondents
- Run Selection creates task and redirects to progress page
- Progress auto-refreshes and shows completion
- Download links work after completion
- Check Data shows success/error inline
- Settings page edits and saves
- Respondents page shows "Selected" filter after selection run
- View link in run history correctly routes DB selection runs

---

## 12. Implementation Todo List

### Phase 1: Service Layer ✅

The service layer has no UI dependencies and can be built and tested first.

- [x] 1.1 Add `CheckDataResult` dataclass to `src/opendlp/service_layer/sortition.py`
- [x] 1.2 Add `check_db_selection_data()` function to `src/opendlp/service_layer/sortition.py` (uses `OpenDLPDataAdapter`, `SelectionData`, `load_features()`, `load_people()`, catches `SortitionBaseError`, returns `CheckDataResult`)
- [x] 1.3 Add necessary imports to `sortition.py` (`translate_sortition_error_to_html`, `translate_run_report_to_html`, `AssemblyCSV`)

### Phase 2: Form ✅

- [x] 2.1 Add `DbSelectionSettingsForm` to `src/opendlp/entrypoints/forms.py` (fields: `check_same_address`, `check_same_address_cols_string`, `columns_to_keep_string` — no `selection_algorithm` field)

### Phase 3: Blueprint — Routes ✅

Create the blueprint file and implement all routes. Routes can be built incrementally but the file must be created first.

- [x] 3.1 Create `src/opendlp/entrypoints/blueprints/db_selection.py` with imports, blueprint declaration, and ABOUTME comment
- [x] 3.2 Implement `view_db_selection` (GET — main selection page without a run)
- [x] 3.3 Implement `view_db_selection_with_run` (GET — selection page with run status)
- [x] 3.4 Implement `check_db_data` (POST — thin wrapper calling `check_db_selection_data` service function)
- [x] 3.5 Implement `start_db_selection` (POST — calls `start_db_select_task`, redirects to run view)
- [x] 3.6 Implement `db_selection_progress` (GET — HTMX polling fragment, sends `HX-Refresh: true` on completion)
- [x] 3.7 Implement `cancel_db_selection` (POST — calls `cancel_task`)
- [x] 3.8 Implement `download_selected_csv` (GET — calls `generate_selection_csvs`, returns CSV response)
- [x] 3.9 Implement `download_remaining_csv` (GET — calls `generate_selection_csvs`, returns CSV response)
- [x] 3.10 Implement `view_db_selection_settings` (GET — loads `AssemblyCSV`, populates `DbSelectionSettingsForm`)
- [x] 3.11 Implement `save_db_selection_settings` (POST — validates form, calls `update_csv_config` with `selection_algorithm="maximin"`)
- [x] 3.12 Implement `_parse_comma_list` helper
- [x] 3.13 Implement `view_db_replacement` (GET — placeholder page)

### Phase 4: Templates ✅

Templates depend on the blueprint routes existing (for `url_for` references).

- [x] 4.1 Create `templates/db_selection/` directory
- [x] 4.2 Create `templates/db_selection/select.html` — extends `view_assembly_base.html`, shows action buttons, check result area, progress include, download links
- [x] 4.3 Create `templates/db_selection/components/` directory
- [x] 4.4 Create `templates/db_selection/components/progress.html` — HTMX fragment with `hx-get` every 2s, status display (pending/running/completed/failed/cancelled)
- [x] 4.5 Create `templates/db_selection/settings.html` — form for `check_same_address`, address columns, columns to keep
- [x] 4.6 Create `templates/db_selection/replace.html` — placeholder "coming soon" page

### Phase 5: Existing File Modifications ✅

These integrate the new feature into the existing application.

- [x] 5.1 Update `templates/main/view_assembly_base.html` — rename "Data & Selection" tab to "Selection (GSheet)", add "Selection (DB)" tab with `current_tab == 'db_selection'` activation
- [x] 5.2 Register `db_selection_bp` in the Flask app factory
- [x] 5.3 Extend `view_gsheet_run` in `src/opendlp/entrypoints/blueprints/gsheets.py` — add `elif` branch routing `SELECT_FROM_DB` and `TEST_SELECT_FROM_DB` to `db_selection.view_db_selection_with_run`
- [x] 5.4 Update `view_assembly_respondents` in `src/opendlp/entrypoints/blueprints/respondents.py` — add `status` query parameter, parse to `RespondentStatus`, pass to `get_by_assembly_id()`, pass `status_filter` to template
- [x] 5.5 Update `templates/respondents/view_respondents.html` — add status filter `<select>` dropdown above the respondent table

### Phase 6: Translations ✅

- [x] 6.1 Run `just translate-regen` to pick up all new `_()` and `_l()` strings

### Phase 7: Quality Checks ✅

- [x] 7.1 Run `just check` — fix any mypy, ruff, or deptry issues (only pre-existing typos error in Hungarian translation remains)
- [x] 7.2 Run `just test` — ensure existing tests still pass

### Phase 8: Unit Tests ✅

- [x] 8.1 Test `check_db_selection_data` returns success when features and people are valid
- [x] 8.2 Test `check_db_selection_data` returns error HTML when features have problems
- [x] 8.3 Test `check_db_selection_data` returns error HTML when respondents don't match features
- [x] 8.4 Test `_parse_comma_list` handles empty strings, whitespace, trailing commas
- [x] 8.5 Test `DbSelectionSettingsForm` validates correctly (valid data, missing optional fields)
- [x] 8.6 Test `check_db_data` route returns 200 with check result in template context
- [x] 8.7 Test `start_db_selection` route calls `start_db_select_task` with correct `test_selection` flag
- [x] 8.8 Test `download_selected_csv` returns CSV with correct `Content-Disposition` header
- [x] 8.9 Test `download_remaining_csv` returns CSV with correct `Content-Disposition` header

### Phase 9: Integration Tests ✅

Tests written as e2e tests using the real postgres test database.

- [x] 9.1 Full selection flow: start selection creates run record, verify task type
- [x] 9.2 Check data with success and failure results shown correctly
- [x] 9.3 Progress polling returns correct HTMX fragments for each task state
- [x] 9.4 Cancel stops a running task and updates status
- [x] 9.5 Settings page saves and loads `check_same_address`, address columns, columns to keep
- [x] 9.6 Respondents page filters by status correctly (all, POOL, SELECTED, CONFIRMED, WITHDRAWN)
- [x] 9.7 `view_gsheet_run` correctly redirects DB task types to DB selection page

### Phase 10: E2E Tests ✅

- [x] 10.1 Selection page loads for assembly with targets and respondents
- [x] 10.2 "Run Selection" creates task and redirects to progress page
- [x] 10.3 Progress polling shows running/completed states and HX-Refresh header
- [x] 10.4 Download routes return CSV with correct headers (mocked `generate_selection_csvs`)
- [x] 10.5 "Check Targets & Respondents" shows success/error inline
- [x] 10.6 Settings page allows editing and saving
- [x] 10.7 Respondents page shows "Selected" filter option after selection run
- [x] 10.8 Run history "View" link routes DB selection runs correctly

### Phase 11: Final Checks ✅

- [x] 11.1 Run `just check` — all checks pass (only pre-existing typos error in Hungarian translation)
- [x] 11.2 Run `just test` — 1329 tests pass, 90.00% coverage
- [ ] 11.3 Manual smoke test: create assembly, upload targets CSV, upload respondents CSV, check data, run test selection, verify respondents page, download CSVs

### Dependency Graph

```
Phase 1 (service layer) ──┐
Phase 2 (form)           ──┼── Phase 3 (routes) ── Phase 4 (templates) ──┐
                           │                                              │
                           └── Phase 5 (existing file mods) ─────────────┤
                                                                          │
                               Phase 6 (translations) ◄──────────────────┤
                               Phase 7 (quality checks) ◄───────────────┤
                               Phase 8 (unit tests) ◄───────────────────┤
                               Phase 9 (integration tests) ◄────────────┤
                               Phase 10 (e2e tests) ◄───────────────────┤
                               Phase 11 (final checks) ◄────────────────┘
```

Phases 1 and 2 are independent of each other and can be done in parallel. Phase 3 depends on both. Phase 4 depends on Phase 3. Phase 5 can be done in parallel with Phases 3-4 (the nav tab and app factory changes don't depend on the routes existing). Phases 6-11 happen after all code is written.
