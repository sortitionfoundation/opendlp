# CSV Upload Web Pages — Research Document

## Goal

Add web pages to upload CSV files for **targets** and **respondents** to an assembly. The service layer, domain models, and database persistence already exist. This document captures everything needed to build the web layer.

---

## 1. Existing Service Layer Functions

### 1.1 `import_respondents_from_csv()`

**File:** `src/opendlp/service_layer/respondent_service.py:64-169`

```python
def import_respondents_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,           # Raw CSV as a string
    replace_existing: bool = False,
    id_column: str | None = None,
) -> tuple[list[Respondent], list[str]]:
```

**Behaviour:**
- Validates user exists, assembly exists, and user has `can_manage_assembly` permission
- If `assembly.csv` config is None, auto-creates a default `AssemblyCSV` with `id_column="external_id"`
- Uses `id_column` parameter if provided, otherwise falls back to `assembly.csv.id_column`
- Parses CSV with `csv.DictReader`
- **Requires** the `id_column` to be present in CSV headers; raises `InvalidSelection` if missing
- Skips rows with empty external_id (soft error)
- Skips duplicates within the CSV (soft error)
- Skips duplicates already in database (soft error)
- Extracts special columns: `consent`, `eligible`, `can_attend` (parsed as booleans), `email`
- All other columns become `Respondent.attributes` dict entries
- Uses `bulk_add()` for performance
- **Returns:** `(list[Respondent], list[str] errors)` — soft error model, partial imports succeed

**Exceptions (hard errors):**
- `UserNotFoundError`
- `AssemblyNotFoundError`
- `InsufficientPermissions`
- `InvalidSelection` — when CSV lacks the required id_column

### 1.2 `import_targets_from_csv()`

**File:** `src/opendlp/service_layer/assembly_service.py:501-574`

```python
def import_targets_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,           # Raw CSV as a string
    replace_existing: bool = False,
) -> list[TargetCategory]:
```

**Behaviour:**
- Same permission checks as respondents
- Uses `sortition_algorithms.features.read_in_features()` for parsing and validation
- **Required CSV columns:** `feature`, `value`, `min`, `max`
- **Optional CSV columns:** `min_flex`, `max_flex`
- Validates constraints (min ≤ max, etc.) via the sortition-algorithms library
- Converts parsed features into `TargetCategory` + `TargetValue` domain objects
- **Returns:** `list[TargetCategory]` — hard error model, raises on any validation failure

**Exceptions (hard errors):**
- `UserNotFoundError`
- `AssemblyNotFoundError`
- `InsufficientPermissions`
- `InvalidSelection` — for empty CSV, malformed CSV, or validation failures

### 1.3 Key Difference in Error Handling

| Aspect | Respondents | Targets |
|--------|-------------|---------|
| Error model | Soft — collects errors, returns partial results | Hard — raises on any error |
| Return type | `(list[Respondent], list[str])` | `list[TargetCategory]` |
| Replace strategy | Delete each individually | `delete_all_for_assembly()` |
| Bulk insert | `bulk_add()` | Individual `add()` per category |

Both functions take `csv_content: str`, so the web layer needs to read the uploaded file and decode it to a string before calling these functions.

---

## 2. Domain Models

### 2.1 Respondent (`domain/respondents.py`)

Key fields:
- `id: uuid.UUID` (auto-generated)
- `assembly_id: uuid.UUID`
- `external_id: str` (unique per assembly)
- `selection_status: RespondentStatus` (defaults to POOL)
- `consent: bool | None`, `eligible: bool | None`, `can_attend: bool | None`
- `email: str` (default "")
- `source_type: RespondentSourceType` (set to `CSV_IMPORT`)
- `source_reference: str` (e.g. "CSV import by user {user_id}")
- `attributes: dict[str, Any]` (flexible JSON storage for all other columns)

### 2.2 TargetCategory + TargetValue (`domain/targets.py`)

**TargetCategory:**
- `id: uuid.UUID`, `assembly_id: uuid.UUID`
- `name: str` (feature name, e.g. "Gender")
- `sort_order: int`
- `values: list[TargetValue]`

**TargetValue (dataclass):**
- `value: str`, `min: int`, `max: int`
- `min_flex: int = 0`, `max_flex: int = MAX_FLEX_UNSET`

### 2.3 AssemblyCSV (`domain/assembly_csv.py`)

Configuration for CSV imports:
- `assembly_id: uuid.UUID`
- `id_column: str = "external_id"` — the column name used as external_id
- `last_import_filename: str` — tracks what was last imported
- `last_import_timestamp: datetime | None`
- `check_same_address: bool`, `check_same_address_cols: list[str]`
- `columns_to_keep: list[str]`
- `selection_algorithm: str = "maximin"`

---

## 3. Assembly Web Page Architecture

### 3.1 Template Inheritance

```
base.html                              ← Global layout (GOV.UK Frontend, HTMX, Alpine.js)
└── main/view_assembly_base.html       ← Assembly wrapper with 3-tab service navigation
    ├── main/view_assembly_details.html     (tab: "details")
    ├── main/view_assembly_data.html        (tab: "data")
    └── main/view_assembly_members.html     (tab: "members")
```

`view_assembly_base.html` provides:
- Breadcrumbs (with `{% block assembly_breadcrumbs %}` for child extension)
- Assembly title heading
- **3-tab service navigation** controlled by `current_tab` template variable
- `{% block assembly_content %}` for page-specific content
- "Back to Dashboard" footer button

### 3.2 Tab Navigation Structure

| Tab | URL Pattern | Route Function | Blueprint |
|-----|-------------|----------------|-----------|
| Details | `/assemblies/<uuid:assembly_id>` | `main.view_assembly` | `main_bp` |
| Data & Selection | `/assemblies/<uuid:assembly_id>/data` | `main.view_assembly_data` | `main_bp` |
| Team Members | `/assemblies/<uuid:assembly_id>/members` | `main.view_assembly_members` | `main_bp` |

The active tab is set by passing `current_tab="details"|"data"|"members"` to the template.

### 3.3 The "Data & Selection" Tab (Where CSV Upload Should Integrate)

**File:** `templates/main/view_assembly_data.html`

Current content:
1. **Google Spreadsheet section** — Configure/Edit buttons, Selection, Replacements, Manage Generated Tabs
2. **Configuration details** — includes `gsheets/components/view_config.html`
3. **Selection Run History** — paginated table of past runs

The CSV upload pages should be accessible from this tab (or from a sub-page linked from it), since this is where data management lives.

### 3.4 Sub-Pages (Linked from Data & Selection Tab)

Sub-pages for gsheets extend `view_assembly_base.html` and add their own breadcrumbs:

```
Dashboard → Assembly: [Title] → Data & Selection → [Sub-page Name]
```

Example breadcrumb pattern from `gsheets/create_config.html`:
```jinja2
{% block assembly_breadcrumbs %}
    <li class="govuk-breadcrumbs__list-item">
        <a class="govuk-breadcrumbs__link"
            href="{{ url_for('main.view_assembly_data', assembly_id=assembly.id) }}">Data & Selection</a>
    </li>
    <li class="govuk-breadcrumbs__list-item">Configure Google Spreadsheet</li>
{% endblock %}
```

---

## 4. Route & Blueprint Patterns

### 4.1 Blueprint Registration

**File:** `src/opendlp/entrypoints/flask_app.py:83-99`

Blueprints are registered in `register_blueprints()`:
```python
app.register_blueprint(main_bp)          # no prefix
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(gsheets_bp)       # no prefix
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(profile_bp)       # no prefix
app.register_blueprint(health_bp)        # no prefix
app.register_blueprint(backoffice_bp, url_prefix="/backoffice")
```

The gsheets blueprint has no URL prefix — its routes start with `/assemblies/<uuid:assembly_id>/gsheet*`.

### 4.2 Standard Route Pattern

Every assembly route follows this pattern:

```python
@blueprint.route("/assemblies/<uuid:assembly_id>/something", methods=["GET", "POST"])
@login_required
def route_name(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            # ... business logic ...

        return render_template("template.html", assembly=assembly, current_tab="data"), 200

    except NotFoundError as e:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        flash(_("You don't have permission..."), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error: {e}")
        return render_template("errors/500.html"), 500
```

### 4.3 Permission Model

**Service layer permission check** (inside the CSV import functions):
- `can_manage_assembly(user, assembly)` — requires ADMIN, GLOBAL_ORGANISER, or ASSEMBLY_MANAGER

**Route-level decorators** available (from `entrypoints/decorators.py`):
- `@login_required` — basic auth (Flask-Login)
- `@require_assembly_management` — checks `can_manage_assembly` at the route level
- `@require_assembly_view` — checks `can_view_assembly`

The gsheets blueprint uses `@require_assembly_management` on some routes. The main blueprint does permission checking inside the route function via `get_assembly_with_permissions()`.

Either approach works. The service layer functions also check permissions internally (belt-and-suspenders).

---

## 5. Form Handling Patterns

### 5.1 Flask-WTF Forms

**File:** `src/opendlp/entrypoints/forms.py`

All forms extend `FlaskForm` with CSRF protection enabled (`WTF_CSRF_ENABLED = True` in config).

Pattern for GET+POST routes:
```python
form = MyForm()
if form.validate_on_submit():
    # Process the form data
    # On success: redirect with flash message
    # On error: flash error and fall through to render
return render_template("template.html", form=form), 200
```

### 5.2 File Upload — No Existing Pattern

There are **no existing file upload forms** in the codebase. No `FileField` from `wtforms` or `flask_wtf.file` is currently imported or used. This will be a first.

For file upload, we need:
- `from flask_wtf.file import FileField, FileAllowed, FileRequired`
- `enctype="multipart/form-data"` on the `<form>` tag
- Reading the file: `file = form.csv_file.data` → `file.read().decode("utf-8")` to get `csv_content: str`
- Flask's `MAX_CONTENT_LENGTH` config to limit upload size (not currently set — should be added)

### 5.3 CSRF Protection

Two patterns used:
1. **Flask-WTF forms:** `{{ form.hidden_tag() }}` in the template (includes CSRF token)
2. **Manual forms:** `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />`

### 5.4 Error Display Pattern

GOV.UK error summary at top of form:
```jinja2
{% if form.errors %}
    <div class="govuk-error-summary" data-module="govuk-error-summary">
        <div role="alert">
            <h2 class="govuk-error-summary__title">There is a problem</h2>
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
```

Plus per-field error messages:
```jinja2
{% if form.field_name.errors %}
    <p class="govuk-error-message">
        <span class="govuk-visually-hidden">Error:</span>
        {{ form.field_name.errors[0] }}
    </p>
{% endif %}
```

---

## 6. Frontend Technologies

### 6.1 GOV.UK Design System

- **Version:** GOV.UK Frontend 5.11.1
- **CSS:** Compiled from SCSS via `just build-css`
- **Components:** `govuk-button`, `govuk-form-group`, `govuk-input`, `govuk-error-summary`, `govuk-table`, `govuk-tag`, `govuk-breadcrumbs`, `govuk-service-navigation`, etc.
- **File upload component:** GOV.UK has a [file upload component](https://design-system.service.gov.uk/components/file-upload/) that uses `govuk-file-upload` class

### 6.2 JavaScript Libraries (from base.html)

- **HTMX 2.0.7** — for dynamic HTML updates without full page reloads
- **Alpine.js 3.15.8** (CSP-compatible build) — for lightweight component interactivity
- **GOV.UK Frontend JS** — for component initialization (`initAll()`)

### 6.3 CSP Requirements

- All `<script>` tags need `nonce="{{ csp_nonce }}"`
- No inline event handlers (`onclick`, `onsubmit`, etc.)
- No `eval()` or `Function()` constructors
- Alpine.js uses CSP-compatible build only (no arrow functions, template literals)
- See `docs/frontend_security.md` for full guidelines

### 6.4 i18n Requirements

All user-facing strings must be wrapped:
- Python: `from opendlp.translations import gettext as _, lazy_gettext as _l`
- Templates: `{{ _("Text to translate") }}`
- Form labels: `_l("Label Text")` (lazy)

---

## 7. CSV Format Expectations

### 7.1 Respondents CSV

**Required column:** Configurable via `id_column` (default: `"external_id"`)

**Special columns (optional):**
| Column | Type | Notes |
|--------|------|-------|
| `consent` | Boolean | "true"/"false" (case-insensitive) |
| `eligible` | Boolean | "true"/"false" (case-insensitive) |
| `can_attend` | Boolean | "true"/"false" (case-insensitive) |
| `email` | String | Extracted to `respondent.email` |

**All other columns** are stored as key-value pairs in `respondent.attributes`.

**Example:**
```csv
external_id,name,email,age,gender,consent,eligible
R001,Alice Smith,alice@example.com,34,Female,true,true
R002,Bob Jones,bob@example.com,45,Male,true,true
```

### 7.2 Targets CSV

**Required columns:** `feature`, `value`, `min`, `max`

**Optional columns:** `min_flex`, `max_flex`

**Example:**
```csv
feature,value,min,max,min_flex,max_flex
Gender,Male,8,12,0,0
Gender,Female,8,12,0,0
Age,18-35,5,10,0,0
Age,36-55,5,10,0,0
Age,56+,3,8,0,0
```

---

## 8. Existing Tests for CSV Import

### 8.1 Respondent Import Tests

**File:** `tests/integration/test_respondent_service.py`
- `test_import_valid_csv` — basic import
- `test_import_csv_without_external_id_column` — error handling
- `test_import_skips_duplicates` — within-CSV duplicates
- `test_import_skips_empty_external_id` — empty ID validation
- `test_import_with_replace_existing` — replacement workflow
- `test_import_with_nullable_boolean_fields` — None when absent
- `test_import_with_boolean_fields` — boolean parsing
- `test_import_without_permission` — permission enforcement

### 8.2 Target Import Tests

**File:** `tests/integration/test_assembly_service_targets.py`
- `test_import_valid_csv` — basic import with feature/value/min/max
- `test_import_csv_with_minimal_columns` — min/max defaults
- `test_import_invalid_csv_raises_error` — validation
- `test_import_with_replace_existing` — replacement
- `test_import_without_permission` — permission enforcement

### 8.3 CSV Config Tests

**File:** `tests/integration/test_csv_import_with_config.py`
- Tests for default/custom/override id_column
- Tests for auto-creation of config
- Tests for config updates

---

## 9. Implementation Considerations

### 9.1 Where to Put the Routes

**Option A: New blueprint** (e.g. `csv_bp`) — similar to `gsheets_bp`, registered without prefix

**Option B: Add to `main_bp`** — since main already handles all assembly view routes

**Option C: Add to `gsheets_bp`** — doesn't make sense since CSV is separate from Google Sheets

Recommendation: **Option A (new blueprint)** keeps things modular and mirrors the gsheets pattern, OR **Option B** if we want to keep it simple with fewer files.

### 9.2 URL Structure

Following the existing pattern:
- `GET /assemblies/<uuid:assembly_id>/csv/upload-respondents` — show upload form
- `POST /assemblies/<uuid:assembly_id>/csv/upload-respondents` — process upload
- `GET /assemblies/<uuid:assembly_id>/csv/upload-targets` — show upload form
- `POST /assemblies/<uuid:assembly_id>/csv/upload-targets` — process upload

### 9.3 Template Structure

```
templates/csv/
    upload_respondents.html  ← extends view_assembly_base.html
    upload_targets.html      ← extends view_assembly_base.html
```

Both should set `current_tab="data"` to keep the Data & Selection tab highlighted.

### 9.4 Entry Points from the Data & Selection Page

The `view_assembly_data.html` template needs buttons/links to the CSV upload pages. These could sit alongside the Google Spreadsheet buttons, perhaps in a separate "CSV Import" section:

```
+------------------------------------------+
| Google Spreadsheet                       |
|   [Configure] [Selection] [Replacements] |
|                                          |
| CSV Import                               |
|   [Upload Respondents] [Upload Targets]  |
+------------------------------------------+
```

### 9.5 File Upload Security

- Set `MAX_CONTENT_LENGTH` in Flask config (e.g. 10MB) to prevent oversized uploads
- Validate file extension (`.csv` only)
- Read file as text, decode UTF-8, pass as string to service layer
- Do NOT store the file on disk (GDPR — see CLAUDE.md)
- Process entirely in memory
- The file content should be read, processed, and discarded in the same request

### 9.6 User Feedback After Upload

**For respondents** (soft error model):
- Flash success message with count of imported respondents
- If there are errors/skipped rows, display them as a warning list
- Consider showing a summary table or redirect to a respondent list view

**For targets** (hard error model):
- Flash success message with count of imported categories
- On error, flash the error message and re-render the form
- Consider showing a preview of imported targets

### 9.7 Replace Existing Checkbox

Both service functions support `replace_existing: bool`. The upload forms should include a checkbox:
- "Replace all existing respondents" / "Replace all existing target categories"
- Default: unchecked (append mode)
- Should have a warning/hint text about the destructive nature

### 9.8 ID Column Configuration (Respondents Only)

The respondent import allows specifying an `id_column`. Options:
- Use the assembly's CSV config default (auto-created if needed)
- Allow override via a text field on the upload form
- Pre-populate with the assembly's current `csv.id_column` value

---

## 10. Summary of Files to Create/Modify

### New Files
1. `src/opendlp/entrypoints/blueprints/csv_upload.py` — routes (or add to `main.py`)
2. `src/opendlp/entrypoints/forms.py` — add `UploadRespondentsCsvForm` and `UploadTargetsCsvForm`
3. `templates/csv/upload_respondents.html` — respondents upload page
4. `templates/csv/upload_targets.html` — targets upload page

### Modified Files
1. `src/opendlp/entrypoints/flask_app.py` — register new blueprint (if using Option A)
2. `templates/main/view_assembly_data.html` — add CSV upload buttons/links
3. `src/opendlp/config.py` — add `MAX_CONTENT_LENGTH` for file upload limits

### Test Files
1. `tests/e2e/test_csv_upload.py` — end-to-end tests using Flask test client
2. `tests/integration/test_csv_upload_routes.py` — route-level integration tests
