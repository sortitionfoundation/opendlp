# Selection with Data in Database: Research Document

**Date:** 2026-03-03

## 1. Executive Summary

This document researches how to implement selection and replacement using targets and respondents stored in the database, rather than Google Sheets. The service layer functions `start_db_select_task` and `generate_selection_csvs` already exist and work. The Celery task `run_select_from_db` and the `OpenDLPDataAdapter` are fully functional. What's missing is the **web layer**: Flask route handlers, templates, and UI for users to trigger DB-based selection, view progress, download results, and run replacements.

## 2. How Google Sheets Selection Works (Reference Implementation)

### 2.1 Architecture Overview

Google Sheets selection uses a 3-step pattern for each operation:

1. **Load/Validate** — Read spreadsheet data and check for errors (optional pre-check step)
2. **Run Selection** — Execute the sortition algorithm
3. **Write Results** — Write selected/remaining tabs back to the spreadsheet

Each step is a Celery background task with progress tracking via `SelectionRunRecord`.

### 2.2 GSheet Selection Routes (in `gsheets.py`)

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/assemblies/<id>/gsheet_select` | GET | `select_assembly_gsheet` | Display selection page (no active task) |
| `/assemblies/<id>/gsheet_select/<run_id>` | GET | `select_assembly_gsheet_with_run` | Display selection page with task status |
| `/assemblies/<id>/gsheet_select/<run_id>/progress` | GET | `gsheet_select_progress` | HTMX polling endpoint (returns progress fragment) |
| `/assemblies/<id>/gsheet_select` | POST | `start_gsheet_select` | Start selection task (form has `test_selection` hidden field) |
| `/assemblies/<id>/gsheet_load` | POST | `start_gsheet_load` | Start validation/check task |
| `/assemblies/<id>/gsheet_select/<run_id>/cancel` | POST | `cancel_gsheet_select` | Cancel a running task |

### 2.3 GSheet Replacement Routes (in `gsheets.py`)

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/assemblies/<id>/gsheet_replace` | GET | `replace_assembly_gsheet` | Display replacement page |
| `/assemblies/<id>/gsheet_replace/<run_id>` | GET | `replace_assembly_gsheet_with_run` | Replacement page with task status |
| `/assemblies/<id>/gsheet_replace/<run_id>/progress` | GET | `gsheet_replace_progress` | HTMX polling for replacement tasks |
| `/assemblies/<id>/gsheet_replace_load` | POST | `start_gsheet_replace_load` | Start replacement data load/validation |
| `/assemblies/<id>/gsheet_replace` | POST | `start_gsheet_replace` | Start replacement selection (with `number_to_select` form field) |
| `/assemblies/<id>/gsheet_replace/<run_id>/cancel` | POST | `cancel_gsheet_replace` | Cancel replacement task |

### 2.4 GSheet Tab Management Routes

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/assemblies/<id>/gsheet_manage_tabs` | GET | `manage_assembly_gsheet_tabs` | Display tab management page |
| `/assemblies/<id>/gsheet_manage_tabs/<run_id>` | GET | with run status | Show results of list/delete |
| `/assemblies/<id>/gsheet_manage_tabs/<run_id>/progress` | GET | HTMX polling | Progress for tab operations |
| `/assemblies/<id>/gsheet_list_tabs` | POST | list tabs (dry_run=True) | List old output tabs |
| `/assemblies/<id>/gsheet_delete_tabs` | POST | delete tabs (dry_run=False) | Delete old output tabs |

### 2.5 GSheet Run History (in `main.py` and `gsheets.py`)

The "Data & Selection" page (`main.view_assembly_data`) shows:
- GSheet configuration summary and action buttons (Selection, Replacements, Manage Tabs)
- Selection Run History table (paginated) with: Status, Task Type, Started By, Started At, Completed At, Comment, Actions (View link)
- The "View" link uses `gsheets.view_gsheet_run` which routes to the correct task-type-specific page

### 2.6 GSheet Service Layer Functions

Located in `src/opendlp/service_layer/sortition.py`:

- **`start_gsheet_load_task(uow, user_id, assembly_id)`** — Creates `LOAD_GSHEET` task, submits `tasks.load_gsheet` Celery task
- **`start_gsheet_select_task(uow, user_id, assembly_id, test_selection)`** — Creates `SELECT_GSHEET` or `TEST_SELECT_GSHEET` task, submits `tasks.run_select`
- **`start_gsheet_replace_load_task(uow, user_id, assembly_id)`** — Creates `LOAD_REPLACEMENT_GSHEET` task
- **`start_gsheet_replace_task(uow, user_id, assembly_id, number_to_select, test_selection)`** — Creates `SELECT_REPLACEMENT_GSHEET` task, validates number is within min/max
- **`start_gsheet_manage_tabs_task(uow, user_id, assembly_id, dry_run)`** — Creates `LIST_OLD_TABS` or `DELETE_OLD_TABS` task

### 2.7 GSheet Celery Tasks

Located in `src/opendlp/entrypoints/celery/tasks.py`:

- **`load_gsheet`** — Calls `_internal_load_gsheet()` which uses `GSheetDataSource` → returns (success, features, people, already_selected, report)
- **`run_select`** — Calls load → `_internal_run_select()` → `_internal_write_selected()` which writes tabs back to Google Sheets
- **`manage_old_tabs`** — Lists or deletes old output tabs from the spreadsheet

### 2.8 GSheet User Flow

**Initial Selection:**
1. User navigates to Data & Selection page → clicks "Selection"
2. Selection page shows: "Run Selection", "Run Test Selection", "Check Spreadsheet" buttons
3. Clicking any button → POST to handler → creates `SelectionRunRecord` → submits Celery task → redirects to page with `run_id`
4. Page polls `/progress` endpoint every 2s via HTMX
5. On completion, `HX-Refresh: true` header triggers full page reload showing results

**Replacement Selection:**
1. User clicks "Replacements" (which is a POST to `start_gsheet_replace_load`) → load task runs
2. When load completes, progress endpoint redirects (HX-Redirect) to replacement page with `min_select`/`max_select` query params
3. Form appears with number input (validated min/max) → user submits → replacement selection runs
4. Progress polling same pattern as initial selection

### 2.9 GSheet Templates

- `gsheets/select.html` — Selection page with buttons and progress area
- `gsheets/replace.html` — Replacement page with number input form
- `gsheets/manage_tabs.html` — Tab management page
- `gsheets/components/progress.html` — HTMX-polled progress fragment (reused across all three pages)
- `gsheets/components/view_config.html` — GSheet configuration summary
- `gsheets/components/view_config_collapsed.html` — Collapsed version

### 2.10 Key GSheet-Specific Concepts (NOT needed for DB selection)

- Tab management (list/delete old tabs) — only relevant for Google Sheets
- Writing back to spreadsheet — DB selection writes to the `respondents` table instead
- `generate_remaining_tab` setting — DB doesn't need output tabs

### 2.11 Test Selection Behavior (GSheet)

**Test selection DOES write to Google Sheets.** The `test_selection` flag is passed to `run_stratification()` (which may produce a looser/faster result) and causes a log suffix "TEST only, do not use for real selection", but `_internal_write_selected()` is called **unconditionally** at `tasks.py:813` with no guard on `test_selection`. Selected/Remaining tabs are written to the spreadsheet in both test and real modes.

---

## 3. How DB Selection Already Works (Backend)

### 3.1 Service Layer: `start_db_select_task`

**File:** `src/opendlp/service_layer/sortition.py:372-423`

```python
@require_assembly_permission(can_manage_assembly)
def start_db_select_task(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    test_selection: bool = False,
) -> uuid.UUID:
```

**What it does:**
1. Validates assembly exists and `number_to_select > 0`
2. Gets or creates `AssemblyCSV` config (uses defaults if no config exists)
3. Converts to `Settings` object via `csv_config.to_settings()`
4. Creates `SelectionRunRecord` with task type `SELECT_FROM_DB` or `TEST_SELECT_FROM_DB`
5. Stores settings snapshot: `id_column`, `selection_algorithm`, `check_same_address`, `check_same_address_columns`, `columns_to_keep`
6. Submits Celery task `run_select_from_db` with `task_id`, `assembly_id`, `number_people_wanted`, `settings`, `test_selection`
7. Returns `task_id`

**Key difference from GSheet:** No separate `LOAD` step. However, this does NOT mean the data is fully validated. While targets are validated at import, and respondents have basic validation (ID field exists), the sortition-algorithms library's `load_people()` → `read_in_people()` performs additional validation at selection time that is not done at import:

- **Header validation** (`_check_people_head()`): Checks that all feature columns, `columns_to_keep`, and `check_same_address_columns` from settings exist in the respondent data headers
- **Feature value validation** (`People.add()`): Checks each respondent's value for every feature column is in the allowed feature values list. Raises `ParseTableMultiError` for empty values (`empty_value_in_feature`) or invalid values (`value_not_in_feature`)
- **Duplicate detection** (`check_for_duplicate_people()`): Checks for duplicate external IDs with differing data

This means a "Check/Validate Data" step is still valuable for DB selection — it lets users see validation errors before committing to a selection run. Unlike GSheet where data loading is slow (requiring a Celery task), DB loading and validation are both fast, so the check can be a **synchronous web request** — call `load_features()` and `load_people()` directly in the route handler and render any errors inline on the page.

### 3.2 Celery Task: `run_select_from_db`

**File:** `src/opendlp/entrypoints/celery/tasks.py:695-745`

```python
@app.task(bind=True, on_failure=_on_task_failure)
def run_select_from_db(self, task_id, assembly_id, number_people_wanted, settings, test_selection=False, session_factory=None):
```

**Three-step pipeline:**
1. **`_internal_load_db()`** — Opens UoW, creates `OpenDLPDataAdapter`, loads features (target categories) and people (eligible respondents)
2. **`_internal_run_select()`** — Calls `run_stratification()` from sortition-algorithms library
3. **`_internal_write_db_results()`** — Calls `uow.respondents.bulk_mark_as_selected()`, stores `selected_ids` and `remaining_ids` on the run record

### 3.3 Data Adapter: `OpenDLPDataAdapter`

**File:** `src/opendlp/adapters/sortition_data_adapter.py`

Implements `AbstractDataSource` from sortition-algorithms:

- **`read_feature_data()`** — Loads `TargetCategory` objects from DB, converts to CSV-like format: headers `["feature", "value", "min", "max"]` (plus `"min_flex", "max_flex"` if any category uses flex). Each `TargetValue` becomes a row.
- **`read_people_data()`** — Loads eligible respondents (`eligible=True`, `can_attend=True`), converts to CSV-like format: headers `["external_id", <attribute_keys>...]`. Each respondent's attributes dict is flattened to string values.
- **`read_already_selected_data()`** — Returns empty (stub). This will need implementation for DB-based replacements.
- **`write_selected/write_remaining/highlight_dupes`** — Stubs (DB writes happen in `_internal_write_db_results` instead).

### 3.4 Service Layer: `generate_selection_csvs`

**File:** `src/opendlp/service_layer/sortition.py:426-458`

```python
def generate_selection_csvs(uow, assembly_id, task_id) -> tuple[str, str]:
```

**What it does:**
1. Fetches `SelectionRunRecord` by `task_id`
2. Validates `selected_ids` and `remaining_ids` exist
3. Reconstructs `Settings` from `settings_used` JSON (stored at selection time)
4. Creates `OpenDLPDataAdapter` to reload features and people from current DB state
5. Calls `person_list_to_table()` from sortition-algorithms for both selected and remaining IDs
6. Returns tuple of `(selected_csv_string, remaining_csv_string)`

**Purpose:** Generates downloadable CSV files post-selection. The CSVs contain the full person data (not just IDs), formatted by the sortition-algorithms library with the columns defined in settings.

**Important note:** This regenerates from current DB state using the stored settings. If respondent data changes between selection and download, the CSV will reflect the current data (but filtered to the IDs that were selected/remaining at selection time).

### 3.5 What `_internal_write_db_results` Does

**File:** `src/opendlp/entrypoints/celery/tasks.py:637-693`

1. Extracts `selected_ext_ids` from `selected_panels[0]` (first/only panel)
2. Computes `remaining_ext_ids` = all people keys not in selected set
3. Calls `uow.respondents.bulk_mark_as_selected(assembly_id, selected_ext_ids, task_id)` — this SQL UPDATE sets `selection_status=SELECTED`, `selection_run_id=task_id`, `updated_at=now()` for all matching respondents
4. Updates `SelectionRunRecord`: status=COMPLETED, stores `remaining_ids`, sets `completed_at`

### 3.6 AssemblyCSV Configuration

**File:** `src/opendlp/domain/assembly_csv.py`

```python
@dataclass
class AssemblyCSV:
    assembly_id: uuid.UUID
    last_import_filename: str = ""
    last_import_timestamp: datetime | None = None
    id_column: str = "external_id"
    check_same_address: bool = True
    check_same_address_cols: list[str] = field(default_factory=list)
    columns_to_keep: list[str] = field(default_factory=list)
    selection_algorithm: str = "maximin"
```

This mirrors `AssemblyGSheet`'s selection settings but without Google Sheets-specific fields (URL, tab names, etc.). The `to_settings()` method converts to `sortition_algorithms.settings.Settings`.

**Current behavior in `start_db_select_task`:** If `assembly.csv` is None, a default `AssemblyCSV(assembly_id=assembly_id)` is created in-memory (not persisted) to get default settings. This means DB selection can work even without explicit CSV configuration.

---

## 4. What Already Exists for DB Selection vs What's Missing

### 4.1 Already Done (Backend)

| Component | Status | Location |
|-----------|--------|----------|
| `SelectionRunRecord` domain model | ✅ | `domain/assembly.py` |
| `SelectionTaskType.SELECT_FROM_DB` | ✅ | `domain/value_objects.py` |
| `SelectionTaskType.TEST_SELECT_FROM_DB` | ✅ | `domain/value_objects.py` |
| `OpenDLPDataAdapter` | ✅ | `adapters/sortition_data_adapter.py` |
| `start_db_select_task()` | ✅ | `service_layer/sortition.py` |
| `generate_selection_csvs()` | ✅ | `service_layer/sortition.py` |
| `run_select_from_db` Celery task | ✅ | `entrypoints/celery/tasks.py` |
| `_internal_load_db()` | ✅ | `entrypoints/celery/tasks.py` |
| `_internal_write_db_results()` | ✅ | `entrypoints/celery/tasks.py` |
| `_process_celery_final_result` handles `SELECT_FROM_DB` | ✅ | `service_layer/sortition.py` |
| `get_selection_run_status()` | ✅ | `service_layer/sortition.py` |
| `cancel_task()` | ✅ | `service_layer/sortition.py` |
| `check_and_update_task_health()` | ✅ | `service_layer/sortition.py` |
| `bulk_mark_as_selected()` repository method | ✅ | `adapters/sql_repository.py` |
| Target categories CRUD | ✅ | Domain + Repository + Service |
| Respondents CRUD | ✅ | Domain + Repository + Service |
| CSV upload for targets and respondents | ✅ | Pages exist for importing data |

### 4.2 Missing (Web Layer and Supporting Code for DB Selection)

| Component | Status | Notes |
|-----------|--------|-------|
| AssemblyCSV create/edit form class | ❌ | No `AssemblyCSVForm` — only `UploadRespondentsCsvForm` exists (covers `id_column` only) |
| AssemblyCSV create/edit route handlers | ❌ | No routes to create/edit full CSV config (algorithm, address cols, columns_to_keep) |
| AssemblyCSV create/edit templates | ❌ | No template for standalone CSV configuration |
| DB data validation route handler | ❌ | No "Check Data" endpoint; can be synchronous (DB load + validation is fast) — call `load_features()`/`load_people()` directly and render errors inline |
| DB selection page route handler | ❌ | No Flask route to display DB selection UI |
| DB selection start route handler | ❌ | No route to POST and trigger `start_db_select_task` |
| DB selection progress route handler | ❌ | No HTMX polling endpoint for DB selection |
| DB selection cancel route handler | ❌ | No cancel endpoint for DB selection tasks |
| DB selection template | ❌ | No Jinja template for DB selection UI |
| DB selection progress template | ❌ | Could reuse `gsheets/components/progress.html` pattern |
| CSV download route for results | ❌ | No endpoint to call `generate_selection_csvs()` and serve files |
| `view_gsheet_run` routing for DB tasks | ❌ | The `view_gsheet_run` handler doesn't route `SELECT_FROM_DB`/`TEST_SELECT_FROM_DB` task types |
| DB replacement selection | ❌ | No `start_db_replace_task` service function |
| DB replacement target adjustment logic | ❌ | No code to reduce target min/max by count of currently selected people per value |
| DB replacement routes and templates | ❌ | No web layer for DB-based replacements |
| `read_already_selected_data()` in adapter | ❌ | Currently a stub returning empty — needed for replacements |

---

## 5. Existing Web Pages and UI Surfaces

### 5.1 GOV.UK Frontend (main blueprint)

The main frontend uses GOV.UK Design System styling.

**Data & Selection page** (`/assemblies/<id>/data`, template: `main/view_assembly_data.html`):
- Shows GSheet config summary (if configured)
- Action buttons: Selection, Replacements, Manage Generated Tabs
- Selection Run History table (all task types, paginated)
- Currently only has buttons for GSheet operations

### 5.2 Backoffice Frontend (backoffice blueprint)

The backoffice uses a custom design system (Tailwind-based).

**Assembly Data page** (`/backoffice/assembly/<id>/data`, template: `backoffice/assembly_data.html`):
- Has tabs: Details, Data, Selection, Team Members
- "Selection" tab currently links to `#` (not implemented)
- Data Source selector dropdown: "Google Spreadsheet" or "CSV file"
- When "CSV file" selected: shows placeholder "Upload a CSV file to import participant data." with TODO comment
- When "Google Spreadsheet" selected: shows full GSheet config form (create/edit/view/delete)

### 5.3 Where DB Selection UI Should Live

There are two possible locations:

**Option A: GOV.UK frontend (main blueprint)**
- Extend `view_assembly_data.html` to show DB selection buttons alongside GSheet buttons
- Create a new `db_select.html` template similar to `gsheets/select.html`

**Option B: Backoffice frontend (backoffice blueprint)**
- Implement the "Selection" tab that's currently a `#` link
- Use the backoffice design system components

**Option C: Both**
- The two frontends seem to coexist (main for GOV.UK, backoffice for new design)
- The selection-tab-spec.md doc suggests backoffice is the target for new features

---

## 6. Detailed Component Analysis

### 6.1 The Progress Polling Pattern

Both frontends use the same pattern:

1. User action triggers POST → creates task → redirect to page with `run_id`
2. Page includes progress fragment with `hx-get="...progress_url..." hx-trigger="every 2s" hx-swap="outerHTML"`
3. Progress endpoint returns updated fragment showing current log messages and status
4. When `run_record.has_finished`: GSheet version sets `HX-Refresh: true` header for full page reload

The progress template (`gsheets/components/progress.html`) is already somewhat generic — it checks `run_record.status` and `run_record.task_type` to show appropriate messages. The main GSheet-specific part is the success message linking to the spreadsheet.

### 6.2 Data Flow: GSheet vs DB Selection Comparison

| Step | GSheet Selection | DB Selection |
|------|-----------------|--------------|
| **Configure** | Create `AssemblyGSheet` (URL, tabs, columns) | `AssemblyCSV` created automatically or via settings |
| **Validate** | `start_gsheet_load_task` → Celery task (loading from sheets is slow) | Synchronous request — call `load_features()`/`load_people()` directly (DB load + validation both fast), render errors inline |
| **Run** | `start_gsheet_select_task` → `run_select` Celery task | `start_db_select_task` → `run_select_from_db` Celery task |
| **Load data** | `GSheetDataSource.read_*()` reads from Google API | `OpenDLPDataAdapter.read_*()` reads from DB |
| **Algorithm** | `run_stratification()` — identical | `run_stratification()` — identical |
| **Write results** | Write selected/remaining tabs to spreadsheet | `bulk_mark_as_selected()` + store IDs on record |
| **View results** | Link to spreadsheet tabs | Download CSVs via `generate_selection_csvs()` |
| **Test mode** | `test_selection=True` — still writes selected/remaining tabs to spreadsheet (same as real) | `test_selection=True` — still marks respondents as SELECTED in DB (same as real) |

### 6.3 Test Selection Behavior

Both GSheet and DB selection behave identically with `test_selection=True`: results are written unconditionally.

- **GSheet:** `run_select` (tasks.py:769-825) calls `_internal_write_selected()` at line 813 with no guard on `test_selection`. Selected/Remaining tabs are always written to the spreadsheet.
- **DB:** `run_select_from_db` (tasks.py:695-745) calls `_internal_write_db_results()` at line 736 with no guard on `test_selection`. Respondents are always marked as SELECTED in the database.

The `test_selection` flag is passed to `run_stratification()` from the sortition-algorithms library (which may produce different algorithmic behavior) and causes a log message suffix "TEST only, do not use for real selection", but it does not prevent writing results in either case.

### 6.4 CSV Download Mechanism

`generate_selection_csvs()` returns two CSV strings. The calling code needs to:
1. Accept the two strings
2. Package them as downloadable files (e.g., `Response` with `Content-Disposition: attachment`)
3. Following GDPR requirements (from CLAUDE.md): files should not be stored long-term — serve directly from memory or use a short-lived cache

### 6.5 Replacement Selection for DB

For GSheet replacement, the flow is:
1. Load replacement data from specific tabs (Remaining, Replacement Categories, Selected)
2. The "already selected" data is read from a dedicated tab
3. Number to select is user-input (validated against min/max from features)
4. Algorithm excludes already-selected people

For DB replacement, the equivalent would be:
1. Load remaining respondents (status=POOL, eligible=True, can_attend=True) — same as initial selection
2. Load already-selected respondents (status=SELECTED or CONFIRMED) — currently the `read_already_selected_data()` stub
3. **Reuse the same target categories**, but with min and max for each value **reduced by the count of currently selected people with that value**. For example, if the Gender/Female target is min=20, max=30 and 25 females are currently selected, the replacement target would be min=0, max=5 (i.e. `max(0, original_min - selected_count)` and `max(0, original_max - selected_count)`)
4. User inputs number to select
5. Algorithm runs with `already_selected` parameter populated and adjusted targets

**Key missing pieces:**
- `OpenDLPDataAdapter.read_already_selected_data()` needs to be implemented to return respondents with `selection_status` in (SELECTED, CONFIRMED)
- Logic to compute adjusted replacement targets from the base targets and current selection counts per value

---

## 7. Settings and Configuration

### 7.1 Settings That Matter for DB Selection

The `AssemblyCSV.to_settings()` produces:

```python
Settings(
    id_column="external_id",        # Always "external_id" for DB data
    selection_algorithm="maximin",   # Configurable
    check_same_address=True,         # Configurable
    check_same_address_columns=[],   # Configurable - which respondent attributes are address columns
    columns_to_keep=[],              # Configurable - extra columns in CSV output
)
```

### 7.2 How Respondent Attributes Map to Selection

The sortition algorithm needs respondent attributes to match target category names. For example:
- If a `TargetCategory` is named "Gender" with values "Male"/"Female"
- Then respondents must have `attributes["Gender"]` matching one of those values
- The `OpenDLPDataAdapter.read_people_data()` flattens `respondent.attributes` dict into column headers

### 7.3 Settings Configuration UI

For GSheet, settings are configured as part of the GSheet config (team presets, custom columns, etc.).

For DB selection, settings come from the `AssemblyCSV` object. Currently there is **no dedicated page to create or edit `AssemblyCSV` configuration**. The existing state is:

- **Service layer exists:** `get_or_create_csv_config()` and `update_csv_config()` in `assembly_service.py`
- **Respondent upload form** touches `id_column` only (via `UploadRespondentsCsvForm`)
- **No form class** for editing the full config (`selection_algorithm`, `check_same_address_cols`, `columns_to_keep`)
- **No template** for a standalone CSV configuration page

Pages will need to be added to create and edit the `AssemblyCSV` object, covering at minimum:
- `selection_algorithm` (currently defaults to "maximin")
- `check_same_address` and `check_same_address_cols` (address deduplication settings)
- `columns_to_keep` (which columns appear in CSV output)

The `id_column` for DB is always "external_id" since that's what `OpenDLPDataAdapter` uses.

---

## 8. Two UI Systems

### 8.1 GOV.UK Frontend (main blueprint)

**Templates:** `templates/main/` and `templates/gsheets/`
**Design:** GOV.UK Design System classes (`govuk-*`)
**Features:** Selection with GSheets, run history, progress polling
**Base template:** `main/view_assembly_base.html`

### 8.2 Backoffice Frontend (backoffice blueprint)

**Templates:** `templates/backoffice/`
**Design:** Custom Tailwind-based design system with component macros
**Features:** Assembly CRUD, GSheet config, data source selection
**Base template:** `backoffice/base_page.html`
**Components:** `button`, `input`, `checkbox`, `radio_group`, `tabs`, `card`, `alert`

### 8.3 How They Relate

Both frontends serve the same data/assemblies. The backoffice appears to be a redesign/replacement of the GOV.UK frontend, but both are active:
- Main blueprint mounts at `/assemblies/<id>/...`
- Backoffice blueprint mounts at `/backoffice/assembly/<id>/...`
- The backoffice "Selection" tab is listed but links to `#` (not yet implemented)
- The selection-tab-spec.md document plans backoffice routes under `/backoffice/assembly/<id>/selection/...`

---

## 9. Run History and the `view_gsheet_run` Router

### 9.1 Current Behavior

The `view_gsheet_run` route (`gsheets.py:997-1057`) maps task types to view endpoints:

| Task Type | Redirects To |
|-----------|--------------|
| `LOAD_GSHEET`, `SELECT_GSHEET`, `TEST_SELECT_GSHEET` | `gsheets.select_assembly_gsheet_with_run` |
| `LOAD_REPLACEMENT_GSHEET`, `SELECT_REPLACEMENT_GSHEET` | `gsheets.replace_assembly_gsheet_with_run` |
| `LIST_OLD_TABS`, `DELETE_OLD_TABS` | `gsheets.manage_assembly_gsheet_tabs_with_run` |
| `SELECT_FROM_DB`, `TEST_SELECT_FROM_DB` | **Not handled** — falls through to "Unknown task type" |

### 9.2 What Needs to Change

The `view_gsheet_run` (or a generic `view_run`) needs to route `SELECT_FROM_DB` and `TEST_SELECT_FROM_DB` to the new DB selection view page. This also affects the run history table on the Data & Selection page, where clicking "View" on a DB selection run currently goes nowhere useful.

---

## 10. Key Architectural Patterns to Follow

### 10.1 Route Handler Pattern

Every GSheet operation follows this consistent pattern:

```python
# Display page (GET, no run)
@bp.route("/<id>/select", methods=["GET"])
def view_select(id):
    assembly = get_assembly(...)
    return render_template("select.html", assembly=assembly)

# Display page with run status (GET, with run_id)
@bp.route("/<id>/select/<run_id>", methods=["GET"])
def view_select_with_run(id, run_id):
    assembly = get_assembly(...)
    result = get_selection_run_status(uow, run_id)
    return render_template("select.html", assembly=assembly, run_record=result.run_record, ...)

# Start task (POST)
@bp.route("/<id>/select", methods=["POST"])
def start_select(id):
    task_id = start_select_task(uow, user_id, id, ...)
    return redirect(url_for("view_select_with_run", id=id, run_id=task_id))

# Progress polling (GET, returns fragment)
@bp.route("/<id>/select/<run_id>/progress", methods=["GET"])
def select_progress(id, run_id):
    check_and_update_task_health(uow, run_id)
    result = get_selection_run_status(uow, run_id)
    response = render_template("progress.html", ...)
    if result.run_record.has_finished:
        response.headers["HX-Refresh"] = "true"
    return response

# Cancel task (POST)
@bp.route("/<id>/select/<run_id>/cancel", methods=["POST"])
def cancel_select(id, run_id):
    cancel_task(uow, user_id, id, run_id)
    return redirect(url_for("view_select_with_run", ...))
```

### 10.2 HTMX Progress Fragment Pattern

The progress template fragment:
- Has `hx-get` and `hx-trigger="every 2s"` when task is not finished
- Shows different content based on status: pending, running, completed, failed, cancelled
- When finished, the progress endpoint sets `HX-Refresh: true` to reload the full page

### 10.3 Permission Pattern

All routes use:
- `@login_required` decorator
- `@require_assembly_management` decorator (checks user can manage the assembly)
- Service functions use `@require_assembly_permission(can_manage_assembly)` decorator

---

## 11. Summary: What Needs to Be Built

### 11.1 AssemblyCSV Configuration Pages (Prerequisite)

Create and edit pages for the `AssemblyCSV` object:
1. **Form class** — New `AssemblyCSVForm` (or create/edit variants) with fields for `selection_algorithm`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`
2. **Route handlers** — Create and edit routes for AssemblyCSV
3. **Templates** — Configuration form and view templates
4. **Service layer** — `get_or_create_csv_config()` and `update_csv_config()` already exist

### 11.2 For Initial DB Selection

1. **Route handlers** — New blueprint or extend existing one with:
   - Display DB selection page (GET)
   - Display with run status (GET with run_id)
   - Start DB selection (POST) — calls `start_db_select_task`
   - Validate DB data (POST, synchronous) — call `load_features()` and `load_people()` from sortition-algorithms directly in the request handler, render any validation errors inline on the page. No Celery task needed since both DB loading and validation are fast
   - Progress polling (GET, HTMX fragment)
   - Cancel (POST)
   - Download CSVs (GET) — calls `generate_selection_csvs` and serves as file download

2. **Templates** — New or adapted:
   - DB selection page (similar to `gsheets/select.html` but without GSheet-specific elements)
   - Progress fragment (can likely reuse pattern from `gsheets/components/progress.html`)
   - The success state should show download links instead of spreadsheet links

3. **Run history integration** — Update `view_gsheet_run` (or create generic router) to handle `SELECT_FROM_DB` and `TEST_SELECT_FROM_DB`

### 11.3 For DB Replacement Selection (Additional)

1. **Service layer** — New `start_db_replace_task` function (similar to `start_gsheet_replace_task`)
2. **Target adjustment logic** — Compute replacement targets from base targets by reducing min/max values by the count of currently selected people per value
3. **Data adapter** — Implement `read_already_selected_data()` in `OpenDLPDataAdapter` to return respondents with `selection_status` in (SELECTED, CONFIRMED)
4. **Celery task** — New or modified task for DB replacement
5. **Route handlers** — Replacement page, start, progress, cancel
6. **Templates** — Replacement page with number input form

---

## Appendix A: File Reference

| File | Purpose |
|------|---------|
| `src/opendlp/service_layer/sortition.py` | All selection service functions |
| `src/opendlp/entrypoints/celery/tasks.py` | Celery task definitions |
| `src/opendlp/adapters/sortition_data_adapter.py` | `OpenDLPDataAdapter` — DB data source |
| `src/opendlp/adapters/sortition_algorithms.py` | `CSVGSheetDataSource` hybrid adapter |
| `src/opendlp/domain/assembly.py` | `SelectionRunRecord`, `AssemblyGSheet` |
| `src/opendlp/domain/assembly_csv.py` | `AssemblyCSV` configuration |
| `src/opendlp/domain/targets.py` | `TargetCategory`, `TargetValue` |
| `src/opendlp/domain/respondents.py` | `Respondent` domain model |
| `src/opendlp/domain/value_objects.py` | Enums: `SelectionRunStatus`, `SelectionTaskType`, `RespondentStatus` |
| `src/opendlp/adapters/orm.py` | SQLAlchemy table definitions |
| `src/opendlp/adapters/sql_repository.py` | Repository implementations |
| `src/opendlp/service_layer/repositories.py` | Repository interfaces |
| `src/opendlp/entrypoints/blueprints/gsheets.py` | GSheet web routes (1057 lines) |
| `src/opendlp/entrypoints/blueprints/main.py` | Main blueprint routes |
| `src/opendlp/entrypoints/blueprints/backoffice.py` | Backoffice blueprint routes |
| `templates/main/view_assembly_data.html` | GOV.UK Data & Selection page |
| `templates/backoffice/assembly_data.html` | Backoffice assembly data page |
| `templates/gsheets/select.html` | GSheet selection page |
| `templates/gsheets/replace.html` | GSheet replacement page |
| `templates/gsheets/manage_tabs.html` | GSheet tab management page |
| `templates/gsheets/components/progress.html` | HTMX progress fragment |
| `docs/agent/selection-tab-spec.md` | Backoffice selection tab specification |

## Appendix B: Enum Values

### SelectionTaskType

```
LOAD_GSHEET              = "load_gsheet"
SELECT_GSHEET            = "select_gsheet"
TEST_SELECT_GSHEET       = "test_select_gsheet"
LOAD_REPLACEMENT_GSHEET  = "load_replacement_gsheet"
SELECT_REPLACEMENT_GSHEET = "select_replacement_gsheet"
LIST_OLD_TABS            = "list_old_tabs"
DELETE_OLD_TABS          = "delete_old_tabs"
SELECT_FROM_DB           = "select_from_db"
TEST_SELECT_FROM_DB      = "test_select_from_db"
```

### SelectionRunStatus

```
PENDING   = "pending"
RUNNING   = "running"
COMPLETED = "completed"
FAILED    = "failed"
CANCELLED = "cancelled"
```

### RespondentStatus

```
POOL        — In selection pool
SELECTED    — Selected in a run
CONFIRMED   — Confirmed participation
WITHDRAWN   — Withdrew after selection
PARTICIPATED — Actually participated
EXCLUDED    — Excluded from selection
```
