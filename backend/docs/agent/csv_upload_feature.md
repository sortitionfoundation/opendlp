# CSV Upload Feature Specification

This document captures the implementation plan for adding CSV upload functionality to allow users to upload participant data sets for assembly selection.

## Background

Currently, OpenDLP uses Google Sheets as the data source for assembly participants. The CSV upload feature will provide an alternative method for importing participant data directly into the system.

**Current state:**
- No file uploads exist in the application
- No "Registrant" domain model - participants are rows in external spreadsheets
- CSV handling exists in sortition-algorithms library (`CSVFileDataSource`) for testing
- Celery background tasks are in place for async operations

## Overview

The CSV upload feature will allow assembly organisers to:
1. Upload a CSV file containing participant data
2. Map CSV columns to system fields (name, email, demographics, etc.)
3. Validate the data before import
4. Store the data for use in stratified selection

## Architecture

### Files to Create/Modify

#### 1. Domain Layer (`src/opendlp/domain/`)

**New model in `assembly.py`:**

```python
class AssemblyCSVDataSource:
    data_source_id: uuid.UUID
    assembly_id: uuid.UUID
    file_name: str
    file_path: str  # Relative to config storage directory
    uploaded_by_id: uuid.UUID
    uploaded_at: datetime
    row_count: int
    columns: list[str]  # Column names from CSV
    mapping: dict[str, str]  # CSV column -> system field mapping
    status: DataSourceStatus  # PENDING, VALIDATED, ACTIVE, FAILED
    validation_errors: list[str]
    created_at: datetime

class DataSourceStatus(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    ACTIVE = "active"
    FAILED = "failed"
```

#### 2. Database/ORM (`src/opendlp/adapters/orm.py`)

**New table:**

```python
assembly_csv_data_sources = Table(
    "assembly_csv_data_sources",
    metadata,
    Column("data_source_id", CrossDatabaseUUID(), primary_key=True),
    Column("assembly_id", CrossDatabaseUUID(), ForeignKey("assemblies.id", ondelete="CASCADE")),
    Column("file_name", String(255), nullable=False),
    Column("file_path", Text, nullable=False),
    Column("uploaded_by_id", CrossDatabaseUUID(), ForeignKey("users.id", ondelete="SET NULL")),
    Column("uploaded_at", TZAwareDatetime(), nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("columns", JSON, nullable=False),  # List of column names
    Column("mapping", JSON, nullable=False),  # Mapping config
    Column("status", EnumAsString(DataSourceStatus, 50), nullable=False),
    Column("validation_errors", JSON, nullable=False, default=list),
    Column("created_at", TZAwareDatetime(), nullable=False),
)
```

#### 3. Repository (`src/opendlp/service_layer/repositories.py`)

**New repository:**

```python
class AssemblyCSVDataSourceRepository(AbstractRepository):
    def get(self, data_source_id: uuid.UUID) -> AssemblyCSVDataSource | None: ...
    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> list[AssemblyCSVDataSource]: ...
    def get_active_for_assembly(self, assembly_id: uuid.UUID) -> AssemblyCSVDataSource | None: ...
    def add(self, data_source: AssemblyCSVDataSource) -> None: ...
```

#### 4. Unit of Work (`src/opendlp/service_layer/unit_of_work.py`)

Register the new repository in `SqlAlchemyUnitOfWork`.

#### 5. Service Layer (`src/opendlp/service_layer/`)

**New file `csv_service.py`:**

```python
def upload_csv(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    file: FileStorage,
) -> tuple[AssemblyCSVDataSource, list[str]]:
    """Upload CSV and detect columns. Returns data source and preview rows."""

def validate_csv_mapping(
    uow: AbstractUnitOfWork,
    data_source_id: uuid.UUID,
    column_mapping: dict[str, str],
) -> list[str]:
    """Validate CSV data against mapping. Returns list of errors."""

def activate_csv_data_source(
    uow: AbstractUnitOfWork,
    data_source_id: uuid.UUID,
) -> AssemblyCSVDataSource:
    """Mark CSV data source as active for selection."""
```

#### 6. Forms (`src/opendlp/entrypoints/forms.py`)

**New forms:**

```python
class CSVUploadForm(FlaskForm):
    csv_file = FileField(
        _l("CSV File"),
        validators=[FileRequired(), FileAllowed(['csv'], _l('CSV files only'))],
    )
    skip_header_rows = IntegerField(
        _l("Skip Header Rows"),
        validators=[Optional(), NonNegativeValidator()],
        default=0,
    )

# Column mapping form will be generated dynamically based on CSV columns
```

#### 7. Blueprint (`src/opendlp/entrypoints/blueprints/`)

**New file `csv_upload.py`:**

```python
csv_bp = Blueprint("csv_upload", __name__)

@csv_bp.route("/assemblies/<uuid:assembly_id>/csv/upload", methods=["GET", "POST"])
@login_required
def upload_csv(assembly_id: uuid.UUID):
    """Step 1: Upload CSV file and detect columns."""

@csv_bp.route("/assemblies/<uuid:assembly_id>/csv/<uuid:data_source_id>/map", methods=["GET", "POST"])
@login_required
def map_columns(assembly_id: uuid.UUID, data_source_id: uuid.UUID):
    """Step 2: Map CSV columns to system fields."""

@csv_bp.route("/assemblies/<uuid:assembly_id>/csv/<uuid:data_source_id>/validate", methods=["POST"])
@login_required
def validate_and_activate(assembly_id: uuid.UUID, data_source_id: uuid.UUID):
    """Step 3: Validate and activate the data source."""

@csv_bp.route("/assemblies/<uuid:assembly_id>/csv/<uuid:task_id>/progress")
@login_required
def upload_progress(assembly_id: uuid.UUID, task_id: uuid.UUID):
    """HTMX endpoint for progress polling."""
```

#### 8. Celery Tasks (`src/opendlp/entrypoints/celery/tasks.py`)

**New task:**

```python
@app.task(bind=True, on_failure=_on_task_failure)
def process_csv_validation_task(
    self,
    data_source_id: uuid.UUID,
    column_mapping: dict[str, str],
) -> None:
    """Async task to validate large CSV files."""
```

#### 9. Templates (`templates/`)

**New templates:**

- `templates/csv_upload/upload.html` - File upload form
- `templates/csv_upload/map_columns.html` - Column mapping UI with data preview
- `templates/csv_upload/progress.html` - HTMX progress fragment
- `templates/csv_upload/success.html` - Confirmation page

## User Flow

```
1. Organiser navigates to Assembly -> Data Sources
2. Clicks "Upload CSV"
3. Selects CSV file, optionally sets skip rows
4. System parses CSV, detects columns, shows preview (first 5 rows)
5. Organiser maps CSV columns to system fields:
   - Required: unique_id (or auto-generate)
   - Optional: first_name, last_name, email, phone, address, etc.
   - Demographics for stratification (age, gender, location, etc.)
6. System validates data:
   - Required fields present
   - Email format (if mapped)
   - No duplicate IDs
   - Data type validation
7. If valid, data source becomes ACTIVE
8. Can now run selection using this data source
```

## File Storage

- Store uploaded files in configurable directory (env var: `CSV_UPLOAD_DIR`)
- Path pattern: `{CSV_UPLOAD_DIR}/{assembly_id}/{data_source_id}/{secure_filename}`
- Use `werkzeug.utils.secure_filename()` for safety
- Consider cleanup job for orphaned files

## Validation Rules

```python
REQUIRED_VALIDATIONS = [
    "unique_id_present_or_generated",
    "no_duplicate_ids",
    "minimum_row_count",
]

OPTIONAL_VALIDATIONS = [
    "email_format",
    "phone_format",
    "date_format",
    "enum_values",  # For demographic categories
]
```

## Integration with Selection

The CSV data source should implement the same interface as GSheet data source:

```python
class CSVAssemblyDataSource:
    """Adapter that implements AbstractDataSource for CSV uploads."""

    def get_registrants(self) -> list[dict]: ...
    def get_targets(self) -> list[dict]: ...
    def write_selected(self, selected: list[dict]) -> None: ...
    def write_remaining(self, remaining: list[dict]) -> None: ...
```

## Database Migration

Create Alembic migration for the new table:

```bash
uv run alembic revision --autogenerate -m "add_assembly_csv_data_sources_table"
```

## Testing Strategy

1. **Unit tests:** CSV parsing, validation logic, column mapping
2. **Integration tests:** Full upload flow with test database
3. **E2E tests:** Playwright tests for UI flow

## Internationalization

All user-facing strings must use:
- `_()` for immediate translation
- `_l()` for lazy translation in forms/exceptions

## Security Considerations

- Validate file size limits (configurable max)
- Sanitize filenames with `secure_filename()`
- Validate CSV structure before processing
- Check user permissions for assembly access
- Store files outside web root

## Configuration

New environment variables:

```bash
# Directory for CSV uploads (default: instance/uploads)
CSV_UPLOAD_DIR=/path/to/uploads

# Maximum file size in MB (default: 10)
CSV_MAX_FILE_SIZE_MB=10

# Maximum rows per CSV (default: 100000)
CSV_MAX_ROWS=100000
```

## Implementation Iterations

Each iteration is small and independently testable.

### Iteration 1: Add "Upload CSV" Button (UI Only)
**Goal:** Add a visible button on the Data & Selection page that links to a placeholder page.

**Files to modify:**
- `templates/main/view_assembly_data.html` - Add button next to "Configure Google Spreadsheet"

**Files to create:**
- `templates/csv_upload/upload.html` - Simple placeholder page
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - New blueprint with single route

**Test:** Navigate to `/assemblies/<id>/data`, see "Upload CSV" button, click it, see placeholder page.

---

### Iteration 2: Basic File Upload Form
**Goal:** Create a working file upload form that accepts a CSV file and shows its filename.

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Handle POST, read file
- `templates/csv_upload/upload.html` - Add actual form with file input
- `src/opendlp/entrypoints/forms.py` - Add `CSVUploadForm`

**Test:** Upload a CSV file, see confirmation that file was received (flash message with filename).

---

### Iteration 3: CSV Parsing and Column Detection
**Goal:** Parse uploaded CSV and display detected columns with preview rows.

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Parse CSV, detect columns

**Files to create:**
- `templates/csv_upload/preview.html` - Show columns and first 5 rows

**Test:** Upload CSV, see table with column headers and preview of data.

---

### Iteration 4: Domain Model and Database
**Goal:** Create the domain model and database table to persist CSV uploads.

**Files to create:**
- `src/opendlp/domain/csv_data_source.py` - Domain model and enum

**Files to modify:**
- `src/opendlp/adapters/orm.py` - Add table definition and mapping
- Create Alembic migration

**Test:** Run migration, verify table exists in database with `just psql`.

---

### Iteration 5: Repository and Persistence
**Goal:** Save CSV metadata to database after upload.

**Files to create:**
- `src/opendlp/adapters/csv_repository.py` - SQLAlchemy repository

**Files to modify:**
- `src/opendlp/service_layer/unit_of_work.py` - Register repository
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Save to DB after upload

**Test:** Upload CSV, check database has record with correct metadata.

---

### Iteration 6: File Storage
**Goal:** Save uploaded CSV file to disk with secure naming.

**Files to modify:**
- `src/opendlp/config.py` - Add `CSV_UPLOAD_DIR` config
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Save file to disk

**Test:** Upload CSV, verify file exists in configured directory.

---

### Iteration 7: Column Mapping UI
**Goal:** Create UI to map CSV columns to system fields.

**Files to create:**
- `templates/csv_upload/map_columns.html` - Mapping form with dropdowns

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Add mapping route

**Test:** After upload, see mapping page with dropdowns to assign each CSV column.

---

### Iteration 8: Save Mapping and Validate
**Goal:** Save column mapping and run basic validation.

**Files to create:**
- `src/opendlp/service_layer/csv_service.py` - Validation logic

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/csv_upload.py` - Process mapping, validate

**Test:** Submit mapping, see validation results (success or error list).

---

### Iteration 9: List CSV Data Sources
**Goal:** Show uploaded CSVs on the Data & Selection page.

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/main.py` - Fetch CSV data sources
- `templates/main/view_assembly_data.html` - Add CSV section

**Test:** After uploading CSV, see it listed on the Data & Selection page.

---

### Iteration 10: Selection Integration
**Goal:** Allow running selection against CSV data source.

**Files to create:**
- `src/opendlp/adapters/csv_data_source_adapter.py` - Implements selection interface

**Files to modify:**
- Selection flow to accept CSV as data source

**Test:** Run selection using uploaded CSV data.

---

## Current Progress

| Iteration | Status | Date |
|-----------|--------|------|
| 1. Add "Upload CSV" Button | Complete | 2025-01-22 |
| 2. Basic File Upload Form | Complete | 2025-01-22 |
| 3. CSV Parsing and Preview | Not Started | - |
| 4. Domain Model and Database | Not Started | - |
| 5. Repository and Persistence | Not Started | - |
| 6. File Storage | Not Started | - |
| 7. Column Mapping UI | Not Started | - |
| 8. Save Mapping and Validate | Not Started | - |
| 9. List CSV Data Sources | Not Started | - |
| 10. Selection Integration | Not Started | - |

---

*Document created: 2025-01-22*
*Status: Specification - Not yet implemented*
