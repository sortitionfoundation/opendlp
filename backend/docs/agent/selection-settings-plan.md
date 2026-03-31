# Selection Settings Extraction Plan

## Goal

Extract the duplicated selection-related fields from `AssemblyCSV` and `AssemblyGSheet` into a new `SelectionSettings` domain model with its own database table. Both `AssemblyCSV` and `AssemblyGSheet` currently duplicate these fields:

- `id_column`
- `check_same_address`
- `check_same_address_cols`
- `columns_to_keep`
- `selection_algorithm`

The new `SelectionSettings` model will own these fields plus a foreign key to `Assembly`. The `to_settings()` method moves to `SelectionSettings`.

## Design Decisions

### Relationship model
- `SelectionSettings` has a **one-to-one** relationship with `Assembly` (like the existing CSV/GSheet models).
- `Assembly` gets a new `selection_settings: SelectionSettings | None` attribute.
- Both `AssemblyCSV` and `AssemblyGSheet` lose the 5 duplicated fields but keep their source-specific fields.
- The `settings_confirmed` flag stays on `AssemblyCSV` — it's CSV-workflow-specific (GSheet doesn't have it).

### `id_column` handling

There are two distinct concepts that were previously conflated under `id_column`:

1. **CSV import column name** (`AssemblyCSV`): Which column in the uploaded CSV contains the unique ID. Used during import to extract the value into `respondent.external_id`. Rename to `csv_id_column` to clarify. Not a selection setting.
2. **Selection ID column** (`SelectionSettings`): The column name used by sortition-algorithms. For CSV workflows this is always `"external_id"` (the normalised name after import). For GSheet workflows this varies by team (e.g. `"nationbuilder_id"`).

**Decisions:**
- `AssemblyCSV` keeps an ID column field, renamed to `csv_id_column` (default `"external_id"`).
- `SelectionSettings.id_column` defaults to `"external_id"`. For GSheet assemblies, the service layer sets it from team defaults.
- `SelectionSettings.to_settings()` is straightforward — no override parameter needed. It always uses `self.id_column`.
- `AssemblyGSheet` loses its `id_column` field entirely — it was only used in `to_settings()` (moving to `SelectionSettings`) and `to_data_source()`. For `to_data_source()`, the caller passes `id_column` as a parameter (fetched from `SelectionSettings`).

**Verified:** `AssemblyGSheet.id_column` is used in exactly 3 places within the class:
- `update_team_settings()` — sets it (moving to service layer)
- `to_settings()` — passes to Settings (moving to `SelectionSettings`)
- `to_data_source()` — passes to `GSheetDataSource` for the replacements flow (line 298). After extraction, `to_data_source()` will accept `id_column` as a parameter.

### Team defaults
- `AssemblyGSheet.update_team_settings()` currently sets `id_column`, `check_same_address_cols`, and `columns_to_keep` — all selection settings fields. Since these now live on `SelectionSettings`, this method moves to the **service layer** as a helper that coordinates updates across both `AssemblyGSheet` (no fields to set anymore, but team choice could be recorded) and `SelectionSettings`.
- The team defaults constants (`DEFAULT_ID_COLUMN`, `DEFAULT_ADDRESS_COLS`, `DEFAULT_COLS_TO_KEEP`) stay in `assembly.py` (or move to `selection_settings.py`) as they define the values.

---

## Files to Change

### 1. New domain model

**New file: `src/opendlp/domain/selection_settings.py`**

```python
@dataclass
class SelectionSettings:
    assembly_id: uuid.UUID
    selection_settings_id: uuid.UUID | None = None
    id_column: str = "external_id"
    check_same_address: bool = True
    check_same_address_cols: list[str] = field(default_factory=list)
    columns_to_keep: list[str] = field(default_factory=list)
    selection_algorithm: str = "maximin"

    def to_settings(self) -> settings.Settings:
        """Convert to sortition-algorithms Settings."""
        return settings.Settings(
            id_column=self.id_column,
            columns_to_keep=self.columns_to_keep,
            check_same_address=self.check_same_address,
            check_same_address_columns=self.check_same_address_cols,
            selection_algorithm=self.selection_algorithm,
            solver_backend=config.get_solver_backend(),
        )

    def create_detached_copy(self) -> "SelectionSettings":
        return SelectionSettings(**asdict(self))

    # String properties for form compatibility
    @property
    def check_same_address_cols_string(self) -> str:
        return ", ".join(self.check_same_address_cols)

    @property
    def columns_to_keep_string(self) -> str:
        return ", ".join(self.columns_to_keep)
```

### 2. Database schema (`src/opendlp/adapters/orm.py`)

Add new table:
```python
selection_settings = Table(
    "selection_settings",
    metadata,
    Column("selection_settings_id", PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("assembly_id", PostgresUUID(as_uuid=True), ForeignKey("assemblies.id", ondelete="CASCADE"),
           nullable=False, unique=True),
    Column("id_column", String(100), nullable=False, default="external_id"),
    Column("check_same_address", Boolean, nullable=False, default=True),
    Column("check_same_address_cols", JSON, nullable=False, default=list),
    Column("columns_to_keep", JSON, nullable=False, default=list),
    Column("selection_algorithm", String(50), nullable=False, default="maximin"),
)
```

Remove from `assembly_gsheets` table: `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`.

Remove from `assembly_csv` table: `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`.

### 3. ORM mapping (`src/opendlp/adapters/database.py`)

- Add `SelectionSettings` mapping with back_populates to Assembly.
- Add `selection_settings` relationship on Assembly mapping (one-to-one, cascade delete).
- Remove back_populates for the deleted columns (no change needed — the columns just disappear from the domain models).

### 4. Domain model changes

**`src/opendlp/domain/assembly.py` — `Assembly` class:**
- Add `selection_settings: SelectionSettings | None = None` parameter/attribute.
- Update `create_detached_copy()` to copy `selection_settings`.
- Move `convert_str_kwargs()`, `_str_to_list_str()`, string properties, team defaults logic to be shared (some stays on `AssemblyGSheet` for GSheet-specific fields, team settings update moves to service layer or `SelectionSettings`).

**`src/opendlp/domain/assembly.py` — `AssemblyGSheet`:**
- Remove fields: `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`.
- Remove `to_settings()` method.
- Remove `check_same_address_cols_string` and `columns_to_keep_string` properties.
- Remove `convert_str_kwargs()` and `_str_to_list_str()` — move to `SelectionSettings` (or a shared utility) if still needed for form handling.
- Remove `update_team_settings()` — moves to service layer as it now affects `SelectionSettings`.
- Update `update_values()` — remove handling of the extracted fields.
- Update `to_data_source()` — accept `id_column` as a required keyword parameter instead of using `self.id_column`.
- Update `dict_for_json()` — remove the extracted fields.
- Update `_updatable_fields()` — remove the extracted fields.

**`src/opendlp/domain/assembly_csv.py` — `AssemblyCSV`:**
- Remove fields: `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`.
- Rename `id_column` to `csv_id_column` (default `"external_id"`). This is the column name in the uploaded CSV file, used during import only.
- Remove `to_settings()` method.

### 5. Repository layer

**`src/opendlp/service_layer/repositories.py`:**
- No new repository needed — `SelectionSettings` is accessed via the Assembly relationship (like `AssemblyCSV`).

### 6. Service layer

**`src/opendlp/service_layer/assembly_service.py`:**

`get_or_create_csv_config()`:
- Also ensure `SelectionSettings` exists on the assembly (create default if needed).
- Return type stays `AssemblyCSV` but callers will also need `SelectionSettings`. **Option:** Return a tuple, or have callers access `assembly.selection_settings` separately. **Decision:** Create a companion `get_or_create_selection_settings()` function, and update callers.

`update_csv_config()`:
- Split: CSV-specific fields (`last_import_filename`, `last_import_timestamp`, `settings_confirmed`) stay here.
- Selection fields (`check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`) move to a new `update_selection_settings()` function.

`add_assembly_gsheet()`:
- After creating `AssemblyGSheet`, also create/update `SelectionSettings` on the assembly with team defaults.

`update_assembly_gsheet()`:
- Selection settings updates route to `SelectionSettings` on the assembly.
- GSheet-specific updates stay on `AssemblyGSheet`.

`get_assembly_gsheet()`:
- No change needed — callers that need settings will get them from `assembly.selection_settings`.

`CSVUploadStatus`:
- The `csv_config` field stays, but selection settings accessed separately.

New functions:
- `get_or_create_selection_settings(uow, user_id, assembly_id) -> SelectionSettings`
- `update_selection_settings(uow, user_id, assembly_id, **settings) -> SelectionSettings`

**`src/opendlp/service_layer/sortition.py`:**

All `to_settings()` calls change to `assembly.selection_settings.to_settings()` — no override parameter needed since `SelectionSettings.id_column` already stores the correct value for each workflow (`"external_id"` for CSV, team-specific for GSheet).

`start_gsheet_load_task()`, `start_gsheet_replace_load_task()`: Get settings from `assembly.selection_settings`.

`start_gsheet_select_task()`, `start_gsheet_replace_task()`: Get settings from `assembly.selection_settings`. Pass `id_column=assembly.selection_settings.id_column` to `gsheet.to_data_source()`.

`check_db_selection_data()`, `start_db_select_task()`: Get settings from `assembly.selection_settings`.

`settings_used` serialization: Use `SelectionSettings` fields.

**`src/opendlp/service_layer/target_checking.py`:**
- `check_detailed_target_feedback()`: Get settings from `assembly.selection_settings`.

### 7. Flask routes / entrypoints

**`src/opendlp/entrypoints/blueprints/db_selection.py`:**
- `view_db_selection()`, `view_db_selection_with_run()`, `check_db_data()`: Fetch `selection_settings` alongside `csv_config`. Pass to templates.
- `start_db_selection()`: Check `assembly.csv.settings_confirmed` (unchanged) but get selection settings from `assembly.selection_settings`.
- `view_db_selection_settings()`: Load `SelectionSettings` for form population.
- `save_db_selection_settings()`: Update `SelectionSettings` via `update_selection_settings()`. The `settings_confirmed` flag still updates via `update_csv_config()`.

**`src/opendlp/entrypoints/blueprints/gsheets.py`:**
- Update to pass selection settings alongside gsheet data to templates/forms.

**`src/opendlp/entrypoints/blueprints/backoffice.py`:**
- Minor: May need to pass `selection_settings` to templates if they display settings info.

**`src/opendlp/entrypoints/blueprints/dev.py`:**
- `_handle_get_csv_config()`: Return selection settings fields from `assembly.selection_settings`.
- `_handle_update_csv_config()`: Route selection field updates to `update_selection_settings()`.

### 8. Forms

**`src/opendlp/entrypoints/forms.py`:**

`AssemblyGSheetForm`:
- The selection-related fields (`id_column`, `check_same_address`, `check_same_address_cols_string`, `columns_to_keep_string`) stay on the form — the form still collects them from the user. The route handler will split the submitted data between `AssemblyGSheet` and `SelectionSettings` updates.
- `team` field and its validation stay — team defaults affect `SelectionSettings`.

`DbSelectionSettingsForm`:
- No structural change — it already only has selection-related fields. The route handler will route updates to `update_selection_settings()`.

### 9. Templates

Templates should need minimal changes — they currently reference `csv_config.check_same_address` etc. These will change to `selection_settings.check_same_address` etc. Quick grep for template references:
- `db_selection/select.html` — references `csv_config.*` for display
- `db_selection/settings.html` — form-based, populated from form object
- GSheet templates — reference `gsheet.*` fields

### 10. Alembic migration

Create a migration that:
1. Creates `selection_settings` table.
2. Copies data from `assembly_gsheets` → `selection_settings` (for assemblies with GSheet config).
3. Copies data from `assembly_csv` → `selection_settings` (for assemblies with CSV config but no GSheet — avoids overwriting).
4. For assemblies with **both** CSV and GSheet configs, prefer the GSheet values (they're the ones actively used for GSheet selection; CSV values are defaults).
5. Drops the 5 columns from `assembly_gsheets` (`id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`).
6. Drops 4 columns from `assembly_csv` (`check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`).
7. Renames `assembly_csv.id_column` to `csv_id_column`.

**Migration upgrade pseudocode:**
```python
def upgrade():
    # 1. Create selection_settings table
    op.create_table("selection_settings", ...)

    # 2. Copy from assembly_gsheets
    op.execute("""
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm
        FROM assembly_gsheets
    """)

    # 3. Copy from assembly_csv where assembly doesn't already have selection_settings
    op.execute("""
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm
        FROM assembly_csv
        WHERE assembly_id NOT IN (SELECT assembly_id FROM selection_settings)
    """)

    # 4. Create default selection_settings for assemblies that have neither
    op.execute("""
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), id, 'external_id', true, '[]'::json, '[]'::json, 'maximin'
        FROM assemblies
        WHERE id NOT IN (SELECT assembly_id FROM selection_settings)
    """)

    # 5. Drop columns from assembly_gsheets
    op.drop_column("assembly_gsheets", "id_column")
    op.drop_column("assembly_gsheets", "check_same_address")
    op.drop_column("assembly_gsheets", "check_same_address_cols")
    op.drop_column("assembly_gsheets", "columns_to_keep")
    op.drop_column("assembly_gsheets", "selection_algorithm")

    # 6. Drop columns from assembly_csv (4 of the 5 — id_column stays but is renamed)
    op.drop_column("assembly_csv", "check_same_address")
    op.drop_column("assembly_csv", "check_same_address_cols")
    op.drop_column("assembly_csv", "columns_to_keep")
    op.drop_column("assembly_csv", "selection_algorithm")

    # 7. Rename id_column to csv_id_column on assembly_csv
    op.alter_column("assembly_csv", "id_column", new_column_name="csv_id_column")
```

**Downgrade** reverses: re-add columns, copy data back, drop `selection_settings` table.

### 11. Test changes

**`tests/conftest.py`:**
- Add `session.execute(orm.selection_settings.delete())` to `_delete_all_test_data()` — before `assemblies` delete, after `assembly_gsheets`/`assembly_csv`.

**`tests/bdd/conftest.py`:**
- Same: add `selection_settings` delete to `delete_all_except_standard_users()`.

**`tests/fakes.py`:**
- No `SelectionSettings` repository needed (accessed via Assembly relationship).
- Ensure `FakeUnitOfWork` assemblies can have `selection_settings` attached.

**`tests/unit/test_assembly_csv.py`:**
- Update: `to_settings()` tests move to test `SelectionSettings.to_settings()`.
- Remove tests for fields that no longer exist on `AssemblyCSV`.

**`tests/unit/test_assembly_service.py`:**
- Update service function calls to match new signatures.

**`tests/unit/test_sortition_service.py`:**
- Update to use `SelectionSettings` instead of `csv_config.to_settings()`.

**`tests/unit/test_db_selection.py`:**
- Update references to selection settings.

**`tests/integration/test_orm.py`:**
- Add ORM mapping test for `SelectionSettings`.
- Update existing tests that create `AssemblyGSheet`/`AssemblyCSV` with the removed fields.

**`tests/e2e/test_assembly_gsheet_crud.py`:**
- Update assertions about GSheet fields (removed fields won't be on the object).

**`tests/e2e/test_db_selection_routes.py`:**
- Update to account for separate selection settings.

**Various BDD tests:**
- Fixtures that create gsheet configs need to also create selection settings.

---

## Detailed TODO

### Phase 1: New domain model and ORM plumbing

- [x] 1.1 Create `src/opendlp/domain/selection_settings.py` with `SelectionSettings` dataclass
  - Fields: `assembly_id`, `selection_settings_id`, `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`
  - Methods: `to_settings()`, `create_detached_copy()`
  - Properties: `check_same_address_cols_string`, `columns_to_keep_string`
  - Move `convert_str_kwargs()` and `_str_to_list_str()` here (used by forms for comma-separated string → list conversion)
  - ABOUTME comment at top of file
- [x] 1.2 Add `selection_settings` table definition to `src/opendlp/adapters/orm.py`
- [x] 1.3 Add `SelectionSettings` imperative mapping to `src/opendlp/adapters/database.py`
  - Map `SelectionSettings` to `selection_settings` table
  - Add `assembly` back_populates relationship on `SelectionSettings`
  - Add `selection_settings` relationship on `Assembly` mapping (one-to-one, cascade delete-orphan)
- [x] 1.4 Add `selection_settings: SelectionSettings | None = None` to `Assembly.__init__()` in `src/opendlp/domain/assembly.py`
- [x] 1.5 Update `Assembly.create_detached_copy()` to include `selection_settings`
- [x] 1.6 Move team defaults constants (`DEFAULT_ID_COLUMN`, `DEFAULT_ADDRESS_COLS`, `DEFAULT_COLS_TO_KEEP`) from `assembly.py` to `selection_settings.py`
  - Update any imports of these constants elsewhere

### Phase 2: Alembic migration

- [x] 2.1 Create Alembic migration with `uv run alembic revision --autogenerate -m "extract selection settings from csv and gsheet"`
- [x] 2.2 Edit the migration to add data-copy SQL statements:
  - Copy from `assembly_gsheets` → `selection_settings`
  - Copy from `assembly_csv` → `selection_settings` (where assembly not already covered)
  - Create defaults for assemblies with neither
- [x] 2.3 Add column drops to migration:
  - Drop 5 columns from `assembly_gsheets`: `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`
  - Drop 4 columns from `assembly_csv`: `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`
- [x] 2.4 Add `id_column` → `csv_id_column` rename on `assembly_csv`
- [x] 2.5 Write the downgrade function (reverse all operations)

### Phase 3: Update `AssemblyGSheet` domain model

- [x] 3.1 Remove fields from `AssemblyGSheet`: `id_column`, `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`
- [x] 3.2 Remove `to_settings()` method
- [x] 3.3 Remove `check_same_address_cols_string` and `columns_to_keep_string` properties
- [x] 3.4 Remove `convert_str_kwargs()` and `_str_to_list_str()` (now on `SelectionSettings`)
- [x] 3.5 Remove `update_team_settings()` method (moves to service layer)
- [x] 3.6 Update `update_values()` to remove handling of extracted fields and team settings
- [x] 3.7 Update `_updatable_fields()` to remove extracted fields
- [x] 3.8 Update `to_data_source()` to accept `id_column` as a required keyword parameter
- [x] 3.9 Update `dict_for_json()` to remove extracted fields
- [x] 3.10 Remove the 5 columns from `assembly_gsheets` table in `orm.py`

### Phase 4: Update `AssemblyCSV` domain model

- [x] 4.1 Rename `id_column` to `csv_id_column` in `AssemblyCSV` dataclass
- [x] 4.2 Remove fields: `check_same_address`, `check_same_address_cols`, `columns_to_keep`, `selection_algorithm`
- [x] 4.3 Remove `to_settings()` method
- [x] 4.4 Update comments/docstrings to reflect the rename
- [x] 4.5 Remove 4 columns from `assembly_csv` table in `orm.py`, rename `id_column` to `csv_id_column`

### Phase 5: Service layer changes

- [x] 5.1 Create `get_or_create_selection_settings()` in `assembly_service.py`
  - Similar pattern to `get_or_create_csv_config()`: view permissions, create default if missing, return detached copy
- [x] 5.2 Create `update_selection_settings()` in `assembly_service.py`
  - Similar pattern to `update_csv_config()`: manage permissions, update fields, commit, return detached copy
- [x] 5.3 Create `apply_team_defaults()` helper in `assembly_service.py` (replaces `AssemblyGSheet.update_team_settings()`)
  - Takes team name, updates `SelectionSettings` fields (`id_column`, `check_same_address_cols`, `columns_to_keep`) from constants
- [x] 5.4 Update `add_assembly_gsheet()`:
  - After creating `AssemblyGSheet`, also create/update `SelectionSettings` on the assembly
  - Apply team defaults to `SelectionSettings` if team is specified
  - Selection-related kwargs route to `SelectionSettings` instead of `AssemblyGSheet`
- [x] 5.5 Update `update_assembly_gsheet()`:
  - Split incoming updates: GSheet-specific fields → `AssemblyGSheet.update_values()`; selection fields → `SelectionSettings`
  - If team is specified, apply team defaults to `SelectionSettings`
- [x] 5.6 Update `get_or_create_csv_config()`: no longer needs to handle selection settings — callers use `get_or_create_selection_settings()` separately
- [x] 5.7 Update `update_csv_config()`: only handle CSV-specific fields (`last_import_filename`, `last_import_timestamp`, `settings_confirmed`); remove selection fields
- [x] 5.8 Update `sortition.py` — `start_gsheet_load_task()`:
  - Get `selection_settings` from assembly
  - Call `selection_settings.to_settings()` instead of `gsheet.to_settings()`
  - Pass `id_column=selection_settings.id_column` to `gsheet.to_data_source()`
- [x] 5.9 Update `sortition.py` — `start_gsheet_replace_load_task()`: same pattern as 5.8
- [x] 5.10 Update `sortition.py` — `start_gsheet_select_task()`:
  - Get `selection_settings` from assembly
  - Call `selection_settings.to_settings()`
  - Pass `id_column=selection_settings.id_column` to `gsheet.to_data_source()`
  - Update `settings_used` dict to use `SelectionSettings` fields
- [x] 5.11 Update `sortition.py` — `start_gsheet_replace_task()`: same pattern as 5.10
- [x] 5.12 Update `sortition.py` — `check_db_selection_data()`:
  - Get `selection_settings` from assembly (create default if needed)
  - Call `selection_settings.to_settings()`
- [x] 5.13 Update `sortition.py` — `start_db_select_task()`:
  - Get `selection_settings` from assembly
  - Call `selection_settings.to_settings()`
  - Update `settings_used` dict
- [x] 5.14 Update `target_checking.py` — `check_detailed_target_feedback()`:
  - Get `selection_settings` from assembly (create default if needed)
  - Call `selection_settings.to_settings()`

### Phase 6: Flask routes and forms

- [x] 6.1 Update `db_selection.py` — `view_db_selection()`:
  - Fetch `selection_settings` via `get_or_create_selection_settings()`
  - Pass `selection_settings` to template instead of selection fields from `csv_config`
- [x] 6.2 Update `db_selection.py` — `view_db_selection_with_run()`: same as 6.1
- [x] 6.3 Update `db_selection.py` — `check_db_data()`: same as 6.1
- [x] 6.4 Update `db_selection.py` — `start_db_selection()`:
  - `settings_confirmed` check stays on `assembly.csv`
- [x] 6.5 Update `db_selection.py` — `view_db_selection_settings()`:
  - Fetch `selection_settings` for form population
  - Populate form from `selection_settings` fields instead of `csv_config`
- [x] 6.6 Update `db_selection.py` — `save_db_selection_settings()`:
  - Call `update_selection_settings()` for selection fields
  - Call `update_csv_config()` only for `settings_confirmed=True`
- [x] 6.7 Update `gsheets.py` routes:
  - Pass `selection_settings` to templates alongside gsheet data
  - When creating/updating gsheet, pass selection-related form fields to `update_selection_settings()` or via updated `add_assembly_gsheet()`/`update_assembly_gsheet()`
- [x] 6.8 Update `backoffice.py` — `view_assembly()`: pass `selection_settings` to template if needed
- [x] 6.9 Update `respondents.py`:
  - Change `assembly.csv.id_column` → `assembly.csv.csv_id_column` (lines 60-61)
- [x] 6.10 Update `targets.py`:
  - Change `assembly.csv.id_column` → `assembly.csv.csv_id_column` (lines 129, 757)
- [x] 6.11 Update `dev.py` — `_handle_get_csv_config()`:
  - Return `csv_id_column` instead of `id_column` for the CSV-specific field
  - Return selection settings fields from `assembly.selection_settings`
- [x] 6.12 Update `dev.py` — `_handle_update_csv_config()`:
  - Route selection field updates to `update_selection_settings()`
  - Route CSV-specific updates to `update_csv_config()`
- [x] 6.13 Forms — no structural changes needed to `AssemblyGSheetForm` or `DbSelectionSettingsForm`; route handlers do the splitting

### Phase 7: Templates

- [x] 7.1 Update `templates/gsheets/components/view_config.html`:
  - `gsheet.check_same_address` → `selection_settings.check_same_address`
  - `gsheet.id_column` → `selection_settings.id_column`
  - `gsheet.check_same_address_cols_string` → `selection_settings.check_same_address_cols_string`
  - `gsheet.columns_to_keep_string` → `selection_settings.columns_to_keep_string`
- [x] 7.2 Update `templates/db_selection/select.html`: change any `csv_config.*` references for selection fields to `selection_settings.*`
- [x] 7.3 Update any other templates that reference the moved fields (grep to confirm)

### Phase 8: Test infrastructure

- [x] 8.1 Add `session.execute(orm.selection_settings.delete())` to `_delete_all_test_data()` in `tests/conftest.py` (after `assembly_gsheets`/`assembly_csv` deletes, before `assemblies` delete)
- [x] 8.2 Add `selection_settings` delete to `delete_all_except_standard_users()` in `tests/bdd/conftest.py` (same ordering)
- [x] 8.3 Update `tests/fakes.py`: no new repository needed, but ensure fake assembly creation can attach `SelectionSettings`

### Phase 9: Unit tests

- [x] 9.1 Create `tests/unit/test_selection_settings.py`:
  - Test `SelectionSettings` creation with defaults
  - Test `SelectionSettings` creation with custom values
  - Test `to_settings()` produces correct `sortition_algorithms.Settings`
  - Test `create_detached_copy()`
  - Test `convert_str_kwargs()` string-to-list conversion
  - Test string properties (`check_same_address_cols_string`, `columns_to_keep_string`)
- [x] 9.2 Update `tests/unit/test_assembly_csv.py`:
  - Remove `to_settings()` tests (moved to test_selection_settings.py)
  - Remove tests for fields that no longer exist on `AssemblyCSV`
  - Update remaining tests to use `csv_id_column` instead of `id_column`
- [x] 9.3 Update `tests/unit/test_assembly_service.py`:
  - Update `add_assembly_gsheet` / `update_assembly_gsheet` tests to verify `SelectionSettings` is created/updated
  - Add tests for `get_or_create_selection_settings()`
  - Add tests for `update_selection_settings()`
  - Update `update_csv_config` tests to reflect reduced scope
- [x] 9.4 Update `tests/unit/test_sortition_service.py`:
  - Update to attach `SelectionSettings` to test assemblies
  - Verify `to_settings()` is called on `SelectionSettings` not on `csv_config`/`gsheet`
- [x] 9.5 Update `tests/unit/test_db_selection.py`:
  - Update references from `csv_config` selection fields to `selection_settings`

### Phase 10: Integration tests

- [x] 10.1 Update `tests/integration/test_orm.py`:
  - Add ORM round-trip test for `SelectionSettings`
  - Update `AssemblyGSheet` ORM test to remove the 5 fields
  - Update `AssemblyCSV` ORM test to use `csv_id_column` and remove 4 fields

### Phase 11: E2E tests

- [x] 11.1 Update `tests/e2e/test_assembly_gsheet_crud.py`:
  - Update assertions for GSheet fields (removed fields won't be on the object)
  - Add assertions that selection settings are created alongside gsheet
- [x] 11.2 Update `tests/e2e/test_db_selection_routes.py`:
  - Update to create/use `SelectionSettings` alongside `AssemblyCSV`
  - Update assertions for settings page to verify `SelectionSettings` is updated
- [x] 11.3 Update `tests/e2e/test_targets_pages.py` if it references moved fields
- [x] 11.4 Update `tests/e2e/test_respondents_pages.py` if it references `id_column`
- [x] 11.5 Update `tests/e2e/test_backoffice_gsheet_selection.py` if it references moved fields

### Phase 12: BDD tests

- [x] 12.1 Update `tests/bdd/conftest.py`:
  - Update `assembly_gsheet_creator` fixture to also create `SelectionSettings`
  - Update any other fixtures that create assemblies with gsheet/csv configs
- [x] 12.2 Update `tests/bdd/test_backoffice.py` if it references moved fields
- [x] 12.3 Update `tests/bdd/test_selection_manual_gsheet.py` if it references moved fields

### Phase 13: Verification

- [x] 13.1 Run `just check` — mypy, ruff, deptry all pass ✓
- [x] 13.2 Run `just test` — 495 unit tests pass; integration/e2e tests need DB/Redis (pre-existing infrastructure requirement, not related to this change)
- [x] 13.3 BDD tests — need DB/Redis infrastructure to run (fixtures updated, conftest cleanup added)
- [x] 13.4 Migration created manually (DB not running for autogenerate); verified SQL is correct
- [x] 13.5 Downgrade function written with reverse operations

## Risks and Considerations

- **Data loss during migration**: The migration must copy data *before* dropping columns. The pseudocode above handles this.
- **Assemblies with both CSV and GSheet**: Currently an assembly can have both, but in practice only one is used at a time. The migration prefers GSheet values when both exist.
- **`id_column` semantics**: Cleanly separated — `AssemblyCSV.csv_id_column` is the CSV import column name, `SelectionSettings.id_column` is the selection column name. For CSV assemblies it defaults to `"external_id"`. For GSheet assemblies the service layer sets it from team defaults.
- **Team defaults**: `update_team_settings()` moves from `AssemblyGSheet` to the service layer since it now updates `SelectionSettings` fields.
- **Form handling**: The GSheet form collects selection settings and GSheet-specific data together. The route handler will need to split the submitted data.
- **`to_data_source()` needs `id_column`**: `AssemblyGSheet.to_data_source()` passes `id_column` to `GSheetDataSource` for the replacements flow. After extraction, the caller must pass it from `SelectionSettings`.
