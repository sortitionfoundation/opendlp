# Module and Specification System - Design Document

**Status:** Design proposal for team review
**Date:** 2026-01-19 (Updated: 2026-02-06)
**Purpose:** Technical design for implementing a flexible module and specification system for OpenDLP assemblies

## Overview

Implement a flexible module and specification system for OpenDLP assemblies using a **Hybrid Structured Approach**. This approach balances type safety with flexibility, using proper database columns for frequently-accessed fields, separate tables for module configurations, and JSON for extensibility.

## Architecture Decision: Enhanced Assembly Model + ModuleConfig Table

### Key Design Principles

1. **Assembly is the aggregate root** with enhanced specification fields:
   - Timeline dates, event details, enabled modules tracked directly on Assembly
   - **Columns**: Timeline dates, event details (queryable, type-safe)
   - **Separate tables**: Target categories (normalized for reporting), Module configs (flexible per-module storage)
   - **JSON fields**: enabled_modules list, custom fields for extensibility

2. **Modules are domain concepts** (not database entities):
   - Defined via `ModuleProtocol` with metadata declarations
   - Registered in `ModuleRegistry` at import time
   - Located in `src/opendlp/domain/modules/`
   - Module enablement tracked as JSON array on Assembly

3. **ModuleConfig is a separate entity** for per-module configuration:
   - Each enabled module can have a ModuleConfig record
   - Stores module-specific JSON configuration
   - Queryable: "which assemblies use module X?"
   - No empty/unused config fields on Assembly

4. **Module families** handle variants:
   - Family constraint: only one module per family (e.g., one invitation type)
   - Registry filtering enables "get all invitation modules"

5. **Permissions** via module metadata:
   - Each module declares `required_global_role`
   - Enable/disable checks permissions automatically

### Terminology

- **Target Categories**: Not just demographics (Gender, Age), but any categorization used for selection targets (e.g., "Attitude to EU: Positive/Neutral/Negative")
- **Registration Page**: Never use "RSVP" - always "registration page/form"
- **Modules**: Code-level domain concepts defining available features
- **Templates**: Preset combinations of modules + default specification values

### Domain Model Structure

```
Assembly (aggregate root, enhanced)
  ├── Core identity fields (id, title, question, status)
  ├── Timeline fields (columns)
  │     ├── planning_start_date
  │     ├── invitation_send_date
  │     ├── registration_open_date
  │     ├── registration_deadline
  │     ├── selection_date
  │     ├── confirmation_deadline
  │     └── first_session_date
  ├── Event details (columns)
  │     ├── event_location
  │     ├── event_description
  │     ├── number_of_sessions
  │     └── number_to_select
  ├── Module system (JSON + relationships)
  │     ├── enabled_modules (JSON array)
  │     ├── custom_fields (JSON)
  │     └── ModuleConfig[] (separate table, 1:many)
  ├── TargetCategory[] (separate table, 1:many)
  │     └── TargetValue[] (separate table, 1:many)
  └── Legacy fields (gsheet, created_at, updated_at)

ModuleConfig (entity, owned by Assembly)
  ├── config_id (UUID)
  ├── assembly_id (FK to Assembly)
  ├── module_id (string, e.g., "registration_page")
  ├── config (JSON, module-specific configuration)
  └── created_at, updated_at

TargetCategory (entity, owned by Assembly)
  ├── category_id (UUID)
  ├── assembly_id (FK to Assembly)
  ├── name, description, sort_order
  └── TargetValue[] (1:many)
        ├── value_id (UUID)
        ├── value (string, e.g., "Female", "16-29")
        ├── min, max (required selection targets)
        ├── min_flex, max_flex (flexibility bounds, defaults: 0, -1)
        └── percentage_target, description (optional UI helpers)

ModuleRegistry (domain service, not persisted)
  └── ModuleProtocol implementations
        ├── metadata (id, name, category, family, permissions)
        ├── validate_assembly(assembly) -> list[str]
        └── has_data(assembly_id, uow) -> bool

TemplateRegistry (domain service, not persisted)
  └── Template definitions
        ├── id, name, description
        ├── enabled_modules list
        └── default_field_values dict
```

## Database Schema

### Modified Tables

#### `assemblies` (add new columns)

```sql
-- Add new columns to existing assemblies table
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS planning_start_date DATE;
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS invitation_send_date DATE;
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS registration_open_date DATE;
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS registration_deadline DATE;
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS selection_date DATE;
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS confirmation_deadline DATE;
-- Note: first_assembly_date already exists, may rename to first_session_date
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS event_location VARCHAR(500) DEFAULT '';
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS event_description TEXT DEFAULT '';
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS number_of_sessions INTEGER DEFAULT 1;
-- Note: number_to_select already exists

-- Module system fields
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS enabled_modules JSON DEFAULT '[]';
ALTER TABLE assemblies ADD COLUMN IF NOT EXISTS custom_fields JSON DEFAULT '{}';

-- Create indexes for new date columns
CREATE INDEX IF NOT EXISTS idx_assembly_selection_date ON assemblies(selection_date);
CREATE INDEX IF NOT EXISTS idx_assembly_registration_deadline ON assemblies(registration_deadline);
CREATE INDEX IF NOT EXISTS idx_assembly_first_session ON assemblies(first_assembly_date);
```

### New Tables

#### `module_configs`

```sql
CREATE TABLE module_configs (
    config_id UUID PRIMARY KEY,
    assembly_id UUID NOT NULL REFERENCES assemblies(id) ON DELETE CASCADE,
    module_id VARCHAR(100) NOT NULL,
    config JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_module_config_assembly_id (assembly_id),
    INDEX idx_module_config_module_id (module_id),
    UNIQUE (assembly_id, module_id)
);
```

**Design notes:**
- One row per enabled module per assembly
- `module_id` is the module identifier (e.g., "registration_page", "invitation_uk_address")
- `config` stores module-specific JSON configuration
- UNIQUE constraint ensures only one config per module per assembly
- Enables queries like "which assemblies use module X?"

#### `target_categories`

```sql
CREATE TABLE target_categories (
    category_id UUID PRIMARY KEY,
    assembly_id UUID NOT NULL REFERENCES assemblies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_target_cat_assembly_id (assembly_id),
    INDEX idx_target_cat_sort_order (assembly_id, sort_order),
    UNIQUE (assembly_id, name)
);
```

**Note on naming:** Called "target_categories" because these categories define selection **targets**, not just demographics. Examples:

- Demographic: Gender, Age, Ethnicity
- Non-demographic: "Attitude to European Union", "Interest in local politics"

**Note on required_on_registration:** All target categories are required on registration, so no boolean field is needed.

#### `target_values`

```sql
CREATE TABLE target_values (
    value_id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES target_categories(category_id) ON DELETE CASCADE,
    value VARCHAR(200) NOT NULL,

    -- Selection targets (matching sortition-algorithms FeatureValueMinMax)
    min INTEGER NOT NULL,
    max INTEGER NOT NULL,
    min_flex INTEGER DEFAULT 0,
    max_flex INTEGER DEFAULT -1,  -- -1 means unset, will be set to safe default

    -- Optional helper fields
    percentage_target DECIMAL(5,2),  -- e.g., 48.5 (percent of wider population)
    description TEXT DEFAULT '',  -- UI help text for non-obvious values

    INDEX idx_target_val_category_id (category_id),
    UNIQUE (category_id, value),

    -- Validation: min <= max
    CHECK (min <= max),
    -- Validation: min_flex <= min
    CHECK (min_flex <= min),
    -- Validation: max_flex >= max OR max_flex = -1 (unset)
    CHECK (max_flex >= max OR max_flex = -1)
);
```

**Field explanations:**
- `min`, `max`: Hard constraints for selection algorithm (must select between min and max of this value)
- `min_flex`, `max_flex`: Soft constraints allowing algorithm flexibility (default: min_flex=0, max_flex=-1 which means "calculate safe default")
- `percentage_target`: Optional guide for UI - percentage of wider population demographics, used to suggest min/max values
- `description`: Optional help text for values that aren't self-explanatory (e.g., "Level 4 and above = Bachelor's degree or higher")

## Implementation Phases

### Phase 1: Enhance Assembly Model & Add Supporting Entities

**Objective:** Extend Assembly domain model with specification fields and create ModuleConfig and TargetCategory entities

#### New Files

1. **`src/opendlp/domain/module_config.py`**
   - `ModuleConfig` class (dataclass or plain class)
   - Fields: config_id, assembly_id, module_id, config (dict), created_at, updated_at
   - Methods:
     - `get_config_value(key, default) -> Any`
     - `update_config(updates: dict) -> None`
     - `validate() -> None`

2. **`src/opendlp/domain/targets.py`**
   - `TargetValue` dataclass:
     - Fields: `value_id`, `value`, `min`, `max`, `min_flex` (default 0), `max_flex` (default -1), `percentage_target` (optional), `description` (default "")
     - Methods:
       - `validate() -> None` - check min <= max, min_flex <= min, etc.
       - `to_feature_value_minmax() -> FeatureValueMinMax` - convert to sortition-algorithms format
       - `from_percentage(percentage, total_to_select) -> tuple[int, int]` - calculate suggested min/max from percentage
   - `TargetCategory` dataclass:
     - Fields: `category_id`, `assembly_id`, `name`, `description`, `values[]`, `sort_order`
     - Note: No `required_on_registration` field (all categories are required)
     - Methods:
       - `validate() -> None` - validate all values
       - `get_value(value_str) -> TargetValue | None`
       - `add_value(value) -> None`
       - `remove_value(value_str) -> None`
       - `to_feature_dict() -> dict[str, FeatureValueMinMax]` - convert to sortition-algorithms format

#### Modified Files

3. **`src/opendlp/domain/assembly.py`**
   - Add new fields to `Assembly.__init__()`:
     - Timeline: planning_start_date, invitation_send_date, registration_open_date, registration_deadline, selection_date, confirmation_deadline
     - Event: event_location, event_description, number_of_sessions
     - Module: enabled_modules (set/list), custom_fields (dict)
   - Add new methods:
     - `enable_module(module_id) -> None`
     - `disable_module(module_id) -> None`
     - `is_module_enabled(module_id) -> bool`
     - `get_enabled_modules() -> list[str]`
     - `update_timeline(**kwargs) -> None`
     - `update_event_details(**kwargs) -> None`
     - `validate_for_modules() -> dict[str, list[str]]`

4. **`src/opendlp/adapters/orm.py`**
   - Add columns to `assemblies` table: timeline dates, event details, enabled_modules, custom_fields
   - Add table definitions: `module_configs`, `target_categories`, `target_values`
   - Use existing patterns: `CrossDatabaseUUID`, `TZAwareDatetime`, `JSON` columns

5. **`src/opendlp/adapters/database.py`**
   - Update `Assembly` mapping to include new columns
   - Add imperative mappings for new entities in `start_mappers()`:
     - `ModuleConfig` mapping
     - `TargetCategory` mapping
     - `TargetValue` mapping
   - Add relationships:
     - `Assembly.module_configs` (one-to-many, cascade delete)
     - `Assembly.target_categories` (one-to-many, cascade delete)
     - `TargetCategory.values` (one-to-many, cascade delete)

6. **`src/opendlp/service_layer/repositories.py`**
   - Add `ModuleConfigRepository` abstract interface
   - Optionally add `TargetCategoryRepository` (could query via Assembly)

7. **`src/opendlp/adapters/sql_repository.py`**
   - Implement `SqlAlchemyModuleConfigRepository`
   - Methods: `add()`, `get(config_id)`, `get_by_assembly_and_module()`, `list_by_assembly()`, `delete()`
   - Update `SqlAlchemyAssemblyRepository` if needed for eager loading

8. **Migration: `migrations/versions/XXXX_add_module_system.py`**
   - Add new columns to `assemblies` table
   - Create three new tables: `module_configs`, `target_categories`, `target_values`
   - Data migration: initialize enabled_modules and custom_fields to empty for existing assemblies

#### Service Layer

9. **`src/opendlp/service_layer/assembly_service.py`** (modify existing)
   - Extend `update_assembly()` to handle new fields
   - Add module management methods:
     - `enable_module(uow, user_id, assembly_id, module_id, config) -> Assembly`
     - `disable_module(uow, user_id, assembly_id, module_id) -> Assembly`
     - `update_module_config(uow, user_id, assembly_id, module_id, config_updates) -> ModuleConfig`
     - `get_module_config(uow, user_id, assembly_id, module_id) -> ModuleConfig | None`
     - `validate_assembly_for_modules(uow, user_id, assembly_id) -> dict[str, list[str]]`
   - Add target category management methods:
     - `add_target_category(uow, user_id, assembly_id, category) -> TargetCategory`
     - `update_target_category(uow, user_id, assembly_id, category_id, updates) -> TargetCategory`
     - `delete_target_category(uow, user_id, assembly_id, category_id) -> None`
     - `import_targets_from_csv(uow, user_id, assembly_id, csv_file) -> list[TargetCategory]`
       - Parse CSV using `sortition_algorithms.features.read_in_features()`
       - Convert FeatureCollection to TargetCategory/TargetValue domain models
       - If registrations exist, validate that category/value names match exactly (only min/max/flex can change)
       - Create or update target categories and values
     - `export_targets_to_csv(uow, user_id, assembly_id) -> str` (optional, for round-trip)
   - Add sortition-algorithms integration:
     - `get_feature_collection(uow, user_id, assembly_id) -> FeatureCollection`
       - Convert assembly's target categories to sortition-algorithms format
       - Apply `set_default_max_flex()` to unset max_flex values
       - Validate with `check_min_max()` against `assembly.number_to_select`
   - All methods check `can_manage_assembly` permission

### Phase 2: Module System Foundation

**Objective:** Create module registry and protocol as domain concepts

#### New Files

10. **`src/opendlp/domain/modules/__init__.py`**
    - Package initialization
    - Import all module implementations to trigger registration

11. **`src/opendlp/domain/modules/base.py`**
    - `ModuleCategory` enum (ASSEMBLY, INVITATION, REGISTRATION, SELECTION, CONFIRMATION, etc.)
    - `ModuleMetadata` dataclass:
      - `id: str` (unique identifier like "invitation_uk_address")
      - `name: str` (display name)
      - `category: ModuleCategory`
      - `description: str`
      - `required_assembly_fields: list[str]` (e.g., ["registration_deadline", "first_session_date"])
      - `optional_assembly_fields: list[str]`
      - `suggested_modules: list[str]` (soft dependencies)
      - `required_global_role: GlobalRole | None`
      - `requires_payment: bool`
      - `stores_data: bool`
      - `family: str | None` (for grouping related modules, e.g., "invitation")
    - `ModuleProtocol` (Protocol class):
      - `metadata -> ModuleMetadata` (property)
      - `validate_assembly(assembly, module_config) -> list[str]`
      - `has_data(assembly_id, uow) -> bool`

12. **`src/opendlp/domain/modules/registry.py`**
    - `ModuleRegistry` class (class methods only, no instances)
    - `register(module) -> None`
    - `get(module_id) -> ModuleProtocol | None`
    - `all() -> dict[str, ModuleProtocol]`
    - `by_category(category) -> dict[str, ModuleProtocol]`
    - `by_family(family) -> dict[str, ModuleProtocol]`

#### Service Layer Additions

(Already added to assembly_service in Phase 1)

### Phase 3: Initial Module Implementations

**Objective:** Implement 2-3 concrete modules to prove the system works

#### Example Modules

13. **`src/opendlp/domain/modules/assembly_module.py`**
    - Always-enabled mandatory module
    - Validates core assembly fields
    - `ModuleMetadata`:
      - id: "assembly"
      - category: ASSEMBLY
      - required_assembly_fields: ["first_session_date", "event_location"]
      - stores_data: False

14. **`src/opendlp/domain/modules/registration/registration_page_module.py`**
    - Registration page module
    - `ModuleMetadata`:
      - id: "registration_page"
      - category: REGISTRATION
      - required_assembly_fields: ["registration_deadline"]
      - stores_data: True (checks if any registrants exist)
    - `validate_assembly()`: Check module config has required fields, verify target_categories exist
    - `has_data()`: Query if registrants exist for assembly

15. **`src/opendlp/domain/modules/selection/participants_module.py`**
    - Selection & replacement module
    - `ModuleMetadata`:
      - id: "selection_participants"
      - category: SELECTION
      - required_assembly_fields: ["selection_date"]
      - suggested_modules: ["registration_page"]
      - stores_data: True (checks if selection runs exist)
    - `validate_assembly()`: Check module config for algorithm/data_source, verify target_categories exist
    - `has_data()`: Query if SelectionRunRecord exists

### Phase 4: Assembly Creation Integration & Templates

**Objective:** Update assembly creation workflow to support templates and module initialization

#### Modified Files

16. **`src/opendlp/service_layer/assembly_service.py`** (already modified in Phase 1)
    - Modify `create_assembly()`:
      - Initialize new fields: enabled_modules = ["assembly"], custom_fields = {}
      - Optionally apply template (if template_id provided)
    - Add `apply_template(uow, user_id, assembly_id, template_id) -> Assembly`
      - Enables template's modules
      - Creates ModuleConfig records for each module
      - Sets assembly timeline/event fields from template defaults

#### Template System (New Package)

17. **`src/opendlp/domain/templates/__init__.py`** (new package)
    - Template definitions as domain concepts (Python dicts or dataclasses)
    - Example templates:
      - "UK Standard": Enable invitation_uk + registration_page + selection + confirmation
      - "Selection Only (CSV)": Enable selection only
      - "Australia Standard": Enable invitation_australia + registration_page + selection

18. **`src/opendlp/domain/templates/registry.py`**
    - `TemplateRegistry` similar to ModuleRegistry
    - `Template` dataclass:
      - `id: str`
      - `name: str`
      - `description: str`
      - `enabled_modules: list[str]`
      - `module_configs: dict[str, dict]` (module_id -> config dict)
      - `assembly_field_defaults: dict[str, Any]` (e.g., number_of_sessions: 3)
    - Methods: `get()`, `all()`, `apply_to_assembly(assembly, module_configs)`

### Phase 5: UI/Entrypoints

**Objective:** Create web interface for managing assembly timeline, modules, and target categories

#### Modified/New Routes

19. **`src/opendlp/entrypoints/blueprints/assemblies.py`** (modify existing)
    - Extend existing assembly edit page to include timeline and event details
    - Add new routes:
      - `GET /assemblies/<id>/timeline` - View/edit timeline dates and event details
      - `POST /assemblies/<id>/timeline` - Update timeline/event fields
      - `GET /assemblies/<id>/modules` - Manage enabled modules
      - `POST /assemblies/<id>/modules/enable` - Enable a module (creates ModuleConfig)
      - `POST /assemblies/<id>/modules/disable` - Disable a module (deletes ModuleConfig)
      - `GET /assemblies/<id>/modules/<module_id>/config` - View/edit module config
      - `POST /assemblies/<id>/modules/<module_id>/config` - Update module config
      - `GET /assemblies/<id>/targets` - Manage target categories (with import/export)
      - `POST /assemblies/<id>/targets/categories` - Add/update category
      - `DELETE /assemblies/<id>/targets/categories/<category_id>` - Delete category
      - `POST /assemblies/<id>/targets/import` - Import targets from CSV
        - If registrations exist, validate category/value names match
        - Show preview before confirming import
      - `GET /assemblies/<id>/targets/export` - Export targets to CSV (optional)
    - All routes require `@require_assembly_management` decorator
    - Add template selection to creation wizard

20. **`src/opendlp/entrypoints/forms.py`**
    - Add forms:
      - `AssemblyTimelineForm` (timeline date fields)
      - `AssemblyEventDetailsForm` (location, description, number_of_sessions)
      - `TargetCategoryForm` (name, description, sort_order)
      - `TargetValueForm` (value, min, max, min_flex, max_flex, percentage_target, description)
        - Note: Initially hide min_flex/max_flex in UI, show only min/max
        - Percentage field can auto-calculate suggested min/max
      - `ModuleConfigForm` (base class, subclassed per module for module-specific fields)
      - `TargetImportForm` (CSV file upload with validation preview)

21. **Templates** (new files)
    - `templates/assembly/timeline.html` - Timeline and event details edit page
    - `templates/assembly/modules.html` - Module management page
    - `templates/assembly/module_config.html` - Module-specific config page
    - `templates/assembly/targets.html` - Target categories management page

#### Assembly Creation Wizard Enhancement

22. **Creation wizard flow:**
    - Step 1: Basic details (title, question) - existing
    - Step 2: Template selection (new) - optional, can skip
    - Step 3: Module selection (new) - shows enabled modules from template, can customize
    - Step 4: Review and create

### Phase 6: Permissions Enhancement

**Objective:** Integrate module permissions with existing system

#### Modified Files

23. **`src/opendlp/domain/value_objects.py`**
    - No changes needed (existing GlobalRole sufficient)

24. **Module metadata** (in each module implementation)
    - Set `required_global_role` appropriately:
      - `invitation_uk_address`: `GlobalRole.ADMIN` (requires payment)
      - `invitation_database`: `GlobalRole.ADMIN` (privacy concerns)
      - Most others: `GlobalRole.GLOBAL_ORGANISER` or None

25. **Service layer** (already handled in Phase 1)
    - `enable_module()` in assembly_service checks `module.metadata.required_global_role`
    - Raises PermissionError if user lacks required role

## Critical Files to Create/Modify

### New Files (16 files)

1. `src/opendlp/domain/module_config.py` - ModuleConfig domain entity
2. `src/opendlp/domain/targets.py` - TargetCategory and TargetValue entities
3. `src/opendlp/domain/modules/__init__.py` - Module package
4. `src/opendlp/domain/modules/base.py` - Module protocol and metadata
5. `src/opendlp/domain/modules/registry.py` - Module registry
6. `src/opendlp/domain/modules/assembly_module.py` - Mandatory core module
7. `src/opendlp/domain/modules/registration/__init__.py`
8. `src/opendlp/domain/modules/registration/registration_page_module.py` - Registration module
9. `src/opendlp/domain/modules/selection/__init__.py`
10. `src/opendlp/domain/modules/selection/participants_module.py` - Selection module
11. `src/opendlp/domain/templates/__init__.py` - Template package
12. `src/opendlp/domain/templates/registry.py` - Template registry
13. `templates/assembly/timeline.html` - Timeline/event details UI
14. `templates/assembly/modules.html` - Module management UI
15. `templates/assembly/targets.html` - Target categories UI
16. `migrations/versions/XXXX_add_module_system.py` - Database migration

### Modified Files (8 files)

1. `src/opendlp/domain/assembly.py` - Add timeline, event, module fields and methods
2. `src/opendlp/adapters/orm.py` - Add columns to assemblies table, add module_configs/target tables
3. `src/opendlp/adapters/database.py` - Update Assembly mapping, add ModuleConfig/TargetCategory mappings
4. `src/opendlp/service_layer/repositories.py` - Add ModuleConfigRepository interface
5. `src/opendlp/adapters/sql_repository.py` - Implement ModuleConfigRepository
6. `src/opendlp/service_layer/assembly_service.py` - Add module/target/timeline management methods
7. `src/opendlp/entrypoints/forms.py` - Add timeline/module/target forms
8. `src/opendlp/entrypoints/blueprints/assemblies.py` - Add new routes, enhance creation wizard

## Data Migration Strategy

1. **Add new columns** to assemblies table with NULL/default values:
   - Timeline fields: `planning_start_date`, `invitation_send_date`, `registration_open_date`, `registration_deadline`, `selection_date`, `confirmation_deadline`
   - Event fields: `event_location`, `event_description`, `number_of_sessions`
   - Module fields: `enabled_modules`, `custom_fields`

2. **Initialize module system fields** for all existing assemblies:
   - Set `enabled_modules = '["assembly"]'` (enable core module)
   - Set `custom_fields = '{}'`

3. **Create new tables**:
   - `module_configs` (config_id, assembly_id, module_id, config, timestamps)
   - `target_categories` (category_id, assembly_id, name, description, sort_order, timestamps)
   - `target_values` (value_id, category_id, value, min, max, min_flex, max_flex, percentage_target, description)

4. **Migrate existing target data** (if any exists in current system):
   - If current system has selection targets elsewhere, migrate to new tables
   - Convert old format to new min/max/min_flex/max_flex fields
   - Set sensible defaults: `min_flex=0`, `max_flex=-1`

5. **Optional field renames**:
   - Consider renaming `first_assembly_date` → `first_session_date` for clarity
   - `number_to_select` remains on Assembly (already there)

6. **Gradual enhancement**: Users fill in timeline dates, event details, configure modules, and import/create targets over time

## Testing Strategy

### Unit Tests

- `tests/unit/test_assembly.py` - Extended Assembly domain model logic (timeline, modules)
- `tests/unit/test_module_config.py` - ModuleConfig entity logic
- `tests/unit/test_targets.py` - TargetCategory/TargetValue validation
- `tests/unit/test_module_registry.py` - Module registration and lookup
- `tests/unit/test_assembly_module.py` - Core module validation logic

### Integration Tests

- `tests/integration/test_assembly_service.py` - Extended service layer operations (modules, timeline, targets)
- `tests/integration/test_module_config_repository.py` - ModuleConfig persistence
- `tests/integration/test_module_enablement.py` - Enable/disable module flows
- `tests/integration/test_target_categories.py` - Target category CRUD operations

### End-to-End Tests (Playwright)

- Create assembly → select template → customize modules → edit timeline
- Add target categories and values
- Enable/disable modules with permission checks
- Update module configurations
- Validate assembly for enabled modules (show validation errors)

## Verification Steps

1. **Database Schema:**

   ```bash
   # Check assemblies table has new columns
   just psql -c "\d assemblies"
   # Check new tables created
   just psql -c "\d module_configs"
   just psql -c "\d target_categories"
   just psql -c "\d target_values"
   ```

2. **Module Registry:**

   ```python
   # In Flask shell (just flask-shell)
   from opendlp.domain.modules.registry import ModuleRegistry
   print(ModuleRegistry.all())
   print(ModuleRegistry.by_category(ModuleCategory.REGISTRATION))
   ```

3. **Create Assembly with Modules:**

   ```python
   # Via service layer
   from opendlp.service_layer import assembly_service
   # Create assembly
   assembly = assembly_service.create_assembly(uow, user_id, title="Test")
   # Check default module enabled
   assert assembly.is_module_enabled("assembly")
   assert assembly.enabled_modules == ["assembly"]
   ```

4. **Module Enablement:**

   ```python
   # Enable registration module
   config = {"welcome_text": "Please register"}
   assembly = assembly_service.enable_module(
       uow, user_id, assembly.id, "registration_page", config
   )
   assert assembly.is_module_enabled("registration_page")

   # Check ModuleConfig created
   module_config = assembly_service.get_module_config(
       uow, user_id, assembly.id, "registration_page"
   )
   assert module_config.config["welcome_text"] == "Please register"
   ```

5. **Target Categories Management:**

   ```python
   # Add target category manually
   from opendlp.domain.targets import TargetCategory, TargetValue
   import uuid
   gender = TargetCategory(
       category_id=uuid.uuid4(),
       assembly_id=assembly.id,
       name="Gender",
       description="",
       sort_order=0,
       values=[
           TargetValue(
               value_id=uuid.uuid4(),
               value="Male",
               min=10,
               max=15,
               min_flex=0,
               max_flex=-1,  # will be set to safe default
               percentage_target=48.5,
               description=""
           ),
           TargetValue(
               value_id=uuid.uuid4(),
               value="Female",
               min=10,
               max=15,
               min_flex=0,
               max_flex=-1,
               percentage_target=51.5,
               description=""
           ),
       ]
   )
   assembly_service.add_target_category(uow, user_id, assembly.id, gender)
   ```

6. **Import Target Categories from CSV:**

   ```python
   # Import from CSV (uses sortition-algorithms parser)
   csv_content = """feature,value,min,max,min_flex,max_flex
   Gender,Male,10,15,0,15
   Gender,Female,10,15,0,15
   Age,16-29,5,8,0,8
   Age,30-44,5,8,0,8
   Age,45-59,5,7,0,7
   Age,60+,5,7,0,7
   """
   categories = assembly_service.import_targets_from_csv(
       uow, user_id, assembly.id, csv_content
   )
   assert len(categories) == 2  # Gender and Age
   ```

7. **Convert to FeatureCollection:**

   ```python
   # Get FeatureCollection for sortition-algorithms
   from sortition_algorithms.features import FeatureCollection
   fc = assembly_service.get_feature_collection(uow, user_id, assembly.id)

   # Should be nested dict: feature_name -> value_name -> FeatureValueMinMax
   assert "Gender" in fc
   assert "Male" in fc["Gender"]
   assert fc["Gender"]["Male"].min == 10
   assert fc["Gender"]["Male"].max == 15
   ```

8. **Run Tests:**

   ```bash
   just test  # All tests including new ones
   just check  # Linting and type checking
   ```

9. **Test UI Flow:**
   - Create new assembly via web interface
   - Select "UK Standard" template
   - Verify modules are pre-enabled
   - Navigate to timeline page
   - Fill in timeline dates and event details
   - Navigate to targets page
   - Either: Add Gender category with values manually, OR
   - Import targets from CSV file
   - Verify percentage_target calculates suggested min/max
   - Navigate to modules page
   - Enable/configure additional modules
   - Try to enable a module requiring admin (should fail if not admin)

## Integration with Sortition-Algorithms Library

### Field Mapping

OpenDLP's target categories/values map directly to sortition-algorithms' FeatureCollection:

| OpenDLP Domain Model | Sortition-Algorithms | Notes |
|---------------------|---------------------|-------|
| `TargetCategory.name` | Feature name (dict key) | e.g., "Gender", "Age" |
| `TargetValue.value` | Feature value (dict key) | e.g., "Male", "16-29" |
| `TargetValue.min` | `FeatureValueMinMax.min` | Hard lower bound |
| `TargetValue.max` | `FeatureValueMinMax.max` | Hard upper bound |
| `TargetValue.min_flex` | `FeatureValueMinMax.min_flex` | Soft lower bound (default: 0) |
| `TargetValue.max_flex` | `FeatureValueMinMax.max_flex` | Soft upper bound (default: -1 = unset) |

**Additional OpenDLP fields** (not in sortition-algorithms):
- `TargetValue.percentage_target` - Optional UI helper for suggesting min/max
- `TargetValue.description` - Optional help text for UI

### CSV Import Process

1. **Parse CSV** using `sortition_algorithms.features.read_in_features()`:
   ```python
   from sortition_algorithms.features import read_in_features
   import csv

   with open(csv_file) as f:
       reader = csv.DictReader(f)
       headers = reader.fieldnames
       rows = list(reader)

   feature_collection, feature_col_name, value_col_name = read_in_features(
       headers, rows, number_to_select=assembly.number_to_select
   )
   ```

2. **Convert FeatureCollection to domain models**:
   ```python
   from sortition_algorithms.features import iterate_feature_collection

   categories = {}
   for feature_name, value_name, fv_minmax in iterate_feature_collection(feature_collection):
       if feature_name not in categories:
           categories[feature_name] = TargetCategory(
               category_id=uuid.uuid4(),
               assembly_id=assembly.id,
               name=feature_name,
               description="",
               sort_order=len(categories),
               values=[]
           )

       target_value = TargetValue(
           value_id=uuid.uuid4(),
           value=value_name,
           min=fv_minmax.min,
           max=fv_minmax.max,
           min_flex=fv_minmax.min_flex,
           max_flex=fv_minmax.max_flex,
           percentage_target=None,  # not in CSV
           description=""
       )
       categories[feature_name].values.append(target_value)
   ```

3. **Validation when re-importing** (if registrations exist):
   - Existing category/value names must match exactly
   - Only `min`, `max`, `min_flex`, `max_flex` can change
   - Raise error if new categories/values introduced or existing ones removed

### Export to FeatureCollection

When running selection, convert domain models back to FeatureCollection:

```python
def get_feature_collection(assembly: Assembly) -> FeatureCollection:
    from sortition_algorithms.features import FeatureCollection, set_default_max_flex, check_min_max
    from requests.structures import CaseInsensitiveDict

    fc: FeatureCollection = CaseInsensitiveDict()

    for category in assembly.target_categories:
        fc[category.name] = CaseInsensitiveDict()
        for value in category.values:
            fc[category.name][value.value] = value.to_feature_value_minmax()

    # Set default max_flex for unset values (-1)
    set_default_max_flex(fc)

    # Validate consistency
    check_min_max(fc, number_to_select=assembly.number_to_select)

    return fc
```

## Open Questions / Future Considerations

1. **Module Lifecycle Hooks**: Should modules have `on_enable()` / `on_disable()` hooks for setup/cleanup?

2. **Module Dependencies**: Current design uses "suggested modules" (warnings only). Do we need hard dependencies later?

3. **Assembly Versioning**: Should we version assemblies for audit trail? Or is `updated_at` sufficient?

4. **Module Data Auditing**: `has_data()` is binary. Should we track data counts for better UX?

5. **Target Category Presets**: Should we ship with preset categories (Gender, Age, etc.) or require manual creation?
   - Could provide "common templates" that include standard UK/AU/EU demographic categories

6. **Translation of Module Metadata**: Module names/descriptions should be translatable - integrate with existing i18n system.

7. **Module Deprecation**: How to handle deprecating old modules while keeping data accessible?

8. **Template Customization**: Should users be able to save their own custom templates, or only use predefined ones?

9. **Assembly Import/Export**: Should full assembly configurations (timeline, targets, modules) be exportable for backup/sharing?

10. **Target Value Constraints Validation**: When a user changes target min/max values, should we:
    - Immediately validate against existing registrations?
    - Show warnings if targets are unachievable with current pool?
    - Auto-suggest adjustments based on registration demographics?

11. **Percentage Target Calculation**: When using `percentage_target`, should the system:
    - Auto-update min/max when `number_to_select` changes?
    - Lock min/max once manually edited (ignore percentage)?
    - Show both percentage and absolute in UI?

12. **CSV Import Conflicts**: If CSV import fails validation (names don't match), should we:
    - Show detailed diff of what changed
    - Offer to create a new assembly instead
    - Allow "force import" that deletes all registrations?

13. **Flex Values in UI**: Should `min_flex` and `max_flex` be:
    - Hidden permanently (too complex for users)?
    - Available as "Advanced" toggle?
    - Shown with clear explanations/defaults?

## Design Rationale

### Why Extend Assembly Instead of Separate Specification?

**Decision:** Add specification fields directly to the Assembly model rather than creating a separate AssemblySpecification entity.

**Rationale:**
- **One-to-one relationship**: Every assembly has exactly one "specification" - they're conceptually the same thing
- **Simpler model**: Avoids forced joins and split-brain issues (where does `number_to_select` live?)
- **Already had overlap**: Assembly already contained `first_assembly_date` and `number_to_select` which are specification details
- **User mental model**: Users think "I'm configuring the assembly" not "I'm configuring the assembly's specification"
- **Less infrastructure**: One aggregate root, one repository, one service, simpler queries

The specification fields ARE the assembly configuration - no need to separate them.

### Why Separate ModuleConfig Table?

**Decision:** Store module configurations in a separate `module_configs` table rather than fixed JSON columns on Assembly.

**Rationale:**
- **True extensibility**: Can add new modules without any schema changes
- **No wasted space**: Only create ModuleConfig rows for enabled modules
- **Queryability**: Can answer "which assemblies use module X?" with a direct query
- **Module independence**: Each module's config is a proper entity with its own lifecycle
- **Aligns with philosophy**: Modules are meant to be pluggable - their config storage should be too

Fixed columns like `registration_config` would work but create tension: modules are supposed to be extensible, but their storage wouldn't be.

### Why "Target Categories" instead of "Demographics"?

The term "Demographics" is too narrow. Target categories include:

- Traditional demographics: Gender, Age, Ethnicity, Location
- Attitudinal: "What is your attitude to the European Union?"
- Behavioral: "Have you participated in local politics?"
- Knowledge-based: "How familiar are you with climate policy?"

All of these are used to define **selection targets** for the sortition algorithm. "Target categories" is more accurate and extensible.

### Why Modules in Domain Layer?

Modules define **what features are available** and **what they require** - this is domain knowledge, not infrastructure. The module system encapsulates:

- Business rules about module compatibility (families)
- Validation logic for assemblies
- Permission requirements

These are all domain concerns, so modules belong in `src/opendlp/domain/modules/`.

Similarly, templates are **preset configurations** that represent common assembly patterns - also domain knowledge.

### Why Hybrid Storage (Columns + Tables + JSON)?

- **Columns for timeline dates**: Enable date-range queries, sorting, indexing (e.g., "assemblies with selection_date next week")
- **Columns for event details**: Frequently displayed, good to have type-safe and queryable
- **Separate table for module configs**: True extensibility - add modules without schema changes
- **Separate tables for targets**: Normalized design enables:
  - Rich reporting queries (JOIN on registrant responses)
  - Proper foreign key constraints
  - Easy addition of metadata per category
- **JSON for enabled_modules**: Simple list, no need for separate table
- **JSON for custom_fields**: Client-specific needs without schema changes

This balances **queryability** (columns/tables) with **flexibility** (JSON) and **extensibility** (ModuleConfig table).

## Success Criteria

✅ Assembly creation wizard includes template selection
✅ Assembly timeline page shows timeline dates and event details
✅ Target categories page supports add/edit/delete categories and values
✅ Modules page shows available modules with enable/disable actions
✅ Module config pages allow configuring enabled modules
✅ Permission checks prevent unauthorized module enablement
✅ Cannot disable modules that have created data
✅ Module validation errors shown when assembly configuration incomplete
✅ ModuleConfig stored separately per module, queryable by module_id
✅ All tests pass (unit, integration, e2e)
✅ Type checking passes (mypy)
✅ Documentation updated in CLAUDE.md

## Next Steps for Team Review

1. **Review architectural changes**:
   - Assembly as single aggregate root (no separate Specification entity)
   - ModuleConfig as separate table (not fixed JSON columns)
2. **Review terminology**: Do "target categories" and "modules" resonate?
3. **Database schema**: Are we happy with the hybrid approach (columns + ModuleConfig table)?
4. **Module location**: Agree that modules/templates are domain concepts?
5. **Permissions model**: Is per-module `required_global_role` sufficient?
6. **Template system**: What predefined templates do we need?
7. **Open questions**: Which should we answer before implementation?

## Timeline Estimate

**Note**: No time estimates provided per project guidelines. This is a sequenced breakdown of work phases to be estimated by the team.

## Architectural Changes from Original Design

**Date of revision:** 2026-02-06

This document was revised based on architectural review. Key changes:

### Change 1: Merged Specification into Assembly

**Original design:** Separate `AssemblySpecification` entity with 1:1 relationship to Assembly

**New design:** Assembly extended with specification fields directly

**Rationale:**
- Eliminates forced join for 1:1 relationship
- Simpler mental model (specification IS the assembly configuration)
- Assembly already contained specification-like fields (`first_assembly_date`, `number_to_select`)
- Reduces infrastructure complexity (one aggregate root, one repository, one service)

**Impact:**
- Fewer files to create (no `assembly_specification.py`, no `specification_service.py`)
- `target_categories` references `assemblies.id` instead of `specification_id`
- All specification operations go through `assembly_service`

### Change 2: ModuleConfig as Separate Table

**Original design:** Fixed JSON columns on AssemblySpecification: `registration_config`, `invitation_config`, `selection_config`, `confirmation_config`

**New design:** Separate `module_configs` table with rows per enabled module

**Rationale:**
- True extensibility - new modules require no schema changes
- No empty/unused JSON columns for disabled modules
- Queryable: "which assemblies use module X?" is a simple query
- Module-specific configs are independent entities with their own lifecycle
- Aligns with "modules are pluggable" philosophy

**Impact:**
- New `ModuleConfig` entity and repository
- Can query assemblies by module usage
- Module configs created/deleted when modules enabled/disabled
- More normalized design

### Summary of Architectural Benefits

1. **Simpler domain model**: One aggregate root (Assembly) instead of two
2. **More extensible**: ModuleConfig table supports unlimited modules without schema changes
3. **More queryable**: Can query assemblies by module usage, timeline dates
4. **Less coupling**: Module configs are independent, not baked into fixed columns
5. **Clearer ownership**: Assembly owns everything (timeline, modules, targets)

### Change 3: Enhanced Target Values with Sortition-Algorithms Integration

**Date of addition:** 2026-02-06

**Design decisions for target categories and values:**

1. **Field naming matches sortition-algorithms**:
   - Use `min`, `max`, `min_flex`, `max_flex` directly (not `target_count`/`minimum_count`)
   - Enables seamless conversion to/from FeatureCollection
   - Reduces mapping complexity and potential errors

2. **CSV import using sortition-algorithms parser**:
   - Use `read_in_features()` from sortition-algorithms library
   - Validates min/max consistency, checks against number_to_select
   - Re-import allowed, but category/value names must match if registrations exist

3. **Optional helper fields** (not in sortition-algorithms):
   - `percentage_target`: Stores demographic percentage, suggests min/max values
   - `description`: Help text for non-obvious values (e.g., "Level 4 = Bachelor's degree+")

4. **Removed required_on_registration field**:
   - All target categories are required on registration
   - No need for per-category flag

5. **Flex values hidden initially**:
   - `min_flex` defaults to 0, `max_flex` defaults to -1 (unset, calculated later)
   - Not shown in UI initially (advanced feature for later)
   - `set_default_max_flex()` calculates safe default before running selection

**Benefits:**
- Direct integration with proven sortition-algorithms library
- CSV import/export for bulk target management
- Percentage helpers make target-setting more intuitive
- Field constraints enforced at database level (CHECK constraints)
