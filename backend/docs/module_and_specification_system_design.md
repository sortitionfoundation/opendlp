# Module and Specification System - Design Document

**Status:** Design proposal for team review
**Date:** 2026-01-19
**Purpose:** Technical design for implementing a flexible module and specification system for OpenDLP assemblies

## Overview

Implement a flexible module and specification system for OpenDLP assemblies using **Approach 3: Hybrid Structured Specification**. This approach balances type safety with flexibility, using proper database columns for frequently-accessed fields and JSON for module-specific configuration.

## Architecture Decision: Approach 3 (Hybrid Structured Specification)

### Key Design Principles

1. **Modules are domain concepts** (not database entities)
   - Defined via `ModuleProtocol` with metadata declarations
   - Registered in `ModuleRegistry` at import time
   - Located in `src/opendlp/domain/modules/`
   - Module enablement tracked as JSON array in specification table

2. **Specification is a proper aggregate root** with hybrid storage:
   - **Columns**: Timeline dates, event details (queryable, type-safe)
   - **Separate tables**: Target categories (normalized for reporting)
   - **JSON fields**: Module-specific configs, custom fields

3. **Module families** handle variants:
   - Family constraint: only one module per family (e.g., one invitation type)
   - Registry filtering enables "get all invitation modules"

4. **Permissions** via module metadata:
   - Each module declares `required_global_role`
   - Enable/disable checks permissions automatically

### Terminology

- **Target Categories**: Not just demographics (Gender, Age), but any categorization used for selection targets (e.g., "Attitude to EU: Positive/Neutral/Negative")
- **Registration Page**: Never use "RSVP" - always "registration page/form"
- **Modules**: Code-level domain concepts defining available features
- **Templates**: Preset combinations of modules + default specification values

### Domain Model Structure

```
AssemblySpecification (aggregate root)
  ├── Timeline fields (columns)
  ├── Event details (columns)
  ├── TargetCategory[] (separate table, 1:many)
  │     └── TargetValue[] (separate table, 1:many)
  ├── registration_config (JSON)
  ├── invitation_config (JSON)
  ├── selection_config (JSON)
  ├── confirmation_config (JSON)
  ├── enabled_modules (JSON array)
  └── custom_fields (JSON)

ModuleRegistry (domain service, not persisted)
  └── ModuleProtocol implementations
        ├── metadata (id, name, category, family, permissions)
        ├── validate_specification()
        └── has_data()

TemplateRegistry (domain service, not persisted)
  └── Template definitions
        ├── id, name, description
        ├── enabled_modules list
        └── default_spec_values dict
```

## Database Schema

### New Tables

#### `assembly_specifications`

```sql
CREATE TABLE assembly_specifications (
    specification_id UUID PRIMARY KEY,
    assembly_id UUID NOT NULL UNIQUE REFERENCES assemblies(id) ON DELETE CASCADE,

    -- Timeline (columns for querying/indexing)
    planning_start_date DATE,
    invitation_send_date DATE,
    registration_open_date DATE,
    registration_deadline DATE,
    selection_date DATE,
    confirmation_deadline DATE,
    first_session_date DATE,

    -- Event Details (columns)
    event_location VARCHAR(500) DEFAULT '',
    event_description TEXT DEFAULT '',
    number_of_sessions INTEGER DEFAULT 1,

    -- Module-specific configurations (JSON)
    registration_config JSON DEFAULT '{}',
    invitation_config JSON DEFAULT '{}',
    selection_config JSON DEFAULT '{}',
    confirmation_config JSON DEFAULT '{}',

    -- Module enablement
    enabled_modules JSON DEFAULT '[]',  -- array of module ID strings

    -- Custom fields
    custom_fields JSON DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_spec_assembly_id (assembly_id),
    INDEX idx_spec_selection_date (selection_date),
    INDEX idx_spec_registration_deadline (registration_deadline)
);
```

#### `target_categories`

```sql
CREATE TABLE target_categories (
    category_id UUID PRIMARY KEY,
    specification_id UUID NOT NULL REFERENCES assembly_specifications(specification_id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT '',
    required_on_registration BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_target_cat_spec_id (specification_id),
    INDEX idx_target_cat_sort_order (specification_id, sort_order),
    UNIQUE (specification_id, name)
);
```

**Note on naming:** Called "target_categories" because these categories define selection **targets**, not just demographics. Examples:

- Demographic: Gender, Age, Ethnicity
- Non-demographic: "Attitude to European Union", "Interest in local politics"

#### `target_values`

```sql
CREATE TABLE target_values (
    value_id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES target_categories(category_id) ON DELETE CASCADE,
    value VARCHAR(200) NOT NULL,
    target_count INTEGER DEFAULT 0,
    minimum_count INTEGER DEFAULT 0,

    INDEX idx_target_val_category_id (category_id),
    UNIQUE (category_id, value)
);
```

## Implementation Phases

### Phase 1: Core Specification Domain & Database

**Objective:** Create the specification entity and persistence layer

#### New Files

1. **`src/opendlp/domain/assembly_specification.py`**
   - `AssemblySpecification` class (dataclass or plain class)
   - Fields: timeline dates, event details, config dicts, enabled_modules set, custom_fields
   - Methods:
     - `enable_module(module_id, user) -> None`
     - `disable_module(module_id, uow) -> None`
     - `is_module_enabled(module_id) -> bool`
     - `get_registration_config(key, default) -> Any`
     - `update_registration_config(updates) -> None`
     - Similar accessors for other config dicts
     - `validate_for_modules() -> dict[str, list[str]]`
     - `add_target_category(category) -> None`
     - `get_target_category(category_id) -> TargetCategory | None`
     - `remove_target_category(category_id) -> None`

2. **`src/opendlp/domain/targets.py`**
   - `TargetValue` dataclass (value, target_count, minimum_count)
   - `TargetCategory` dataclass (category_id, name, description, values[], required, sort_order)
   - Methods on `TargetCategory`:
     - `validate() -> None`
     - `get_value(value_str) -> TargetValue | None`
     - `add_value(value) -> None`

#### Modified Files

3. **`src/opendlp/adapters/orm.py`**
   - Add table definitions: `assembly_specifications`, `target_categories`, `target_values`
   - Use existing patterns: `CrossDatabaseUUID`, `TZAwareDatetime`, `JSON` columns

4. **`src/opendlp/adapters/database.py`**
   - Add imperative mappings for new entities in `start_mappers()`
   - Relationship: `AssemblySpecification.target_categories` (one-to-many, cascade delete)
   - Relationship: `TargetCategory.values` (one-to-many, cascade delete)

5. **`src/opendlp/service_layer/repositories.py`**
   - Add `AssemblySpecificationRepository` abstract interface
   - Add `TargetCategoryRepository` abstract interface (optional, could query via spec)

6. **`src/opendlp/adapters/sql_repository.py`**
   - Implement `SqlAlchemyAssemblySpecificationRepository`
   - Methods: `add()`, `get(spec_id)`, `get_by_assembly_id()`, `delete()`

7. **Migration: `migrations/versions/XXXX_add_assembly_specifications.py`**
   - Create three new tables
   - Data migration: create empty specification for each existing assembly

#### Service Layer

8. **`src/opendlp/service_layer/specification_service.py`** (new file)
   - `create_specification(uow, user_id, assembly_id, **kwargs) -> AssemblySpecification`
   - `get_specification(uow, user_id, assembly_id) -> AssemblySpecification`
   - `update_specification(uow, user_id, assembly_id, updates) -> AssemblySpecification`
   - `add_target_category(uow, user_id, assembly_id, category) -> TargetCategory`
   - `update_target_category(uow, user_id, assembly_id, category_id, updates) -> TargetCategory`
   - `delete_target_category(uow, user_id, assembly_id, category_id) -> None`
   - All methods check `can_manage_assembly` permission

### Phase 2: Module System Foundation

**Objective:** Create module registry and protocol as domain concepts

#### New Files

9. **`src/opendlp/domain/modules/__init__.py`**
   - Package initialization
   - Import all module implementations to trigger registration

10. **`src/opendlp/domain/modules/base.py`**
    - `ModuleCategory` enum (SPECIFICATION, INVITATION, REGISTRATION, SELECTION, etc.)
    - `ModuleMetadata` dataclass:
      - `id: str` (unique identifier like "invitation_uk_address")
      - `name: str` (display name)
      - `category: ModuleCategory`
      - `description: str`
      - `required_spec_fields: list[str]`
      - `optional_spec_fields: list[str]`
      - `suggested_modules: list[str]` (soft dependencies)
      - `required_global_role: GlobalRole | None`
      - `requires_payment: bool`
      - `stores_data: bool`
      - `family: str | None` (for grouping related modules)
    - `ModuleProtocol` (Protocol class):
      - `metadata -> ModuleMetadata` (property)
      - `validate_specification(spec) -> list[str]`
      - `has_data(assembly_id, uow) -> bool`

11. **`src/opendlp/domain/modules/registry.py`**
    - `ModuleRegistry` class (class methods only, no instances)
    - `register(module) -> None`
    - `get(module_id) -> ModuleProtocol | None`
    - `all() -> dict[str, ModuleProtocol]`
    - `by_category(category) -> dict[str, ModuleProtocol]`
    - `by_family(family) -> dict[str, ModuleProtocol]`

#### Service Layer Additions

12. **`src/opendlp/service_layer/specification_service.py`** (modify)
    - Add methods:
      - `enable_module(uow, user_id, assembly_id, module_id) -> AssemblySpecification`
      - `disable_module(uow, user_id, assembly_id, module_id) -> AssemblySpecification`
      - `get_enabled_modules(uow, user_id, assembly_id) -> list[str]`
      - `validate_specification_for_modules(uow, user_id, assembly_id) -> dict[str, list[str]]`

### Phase 3: Initial Module Implementations

**Objective:** Implement 2-3 concrete modules to prove the system works

#### Example Modules

13. **`src/opendlp/domain/modules/specification_module.py`**
    - Always-enabled mandatory module
    - Validates core specification fields
    - `ModuleMetadata`:
      - id: "specification"
      - category: SPECIFICATION
      - required_spec_fields: ["first_session_date"]
      - stores_data: False

14. **`src/opendlp/domain/modules/registration/registration_page_module.py`**
    - Registration page module
    - `ModuleMetadata`:
      - id: "registration_page"
      - category: REGISTRATION
      - required_spec_fields: ["registration_deadline", "target_categories"]
      - stores_data: True (checks if any registrants exist)
    - `validate_specification()`: Check registration_config has required fields
    - `has_data()`: Query if registrants exist for assembly

15. **`src/opendlp/domain/modules/selection/participants_module.py`**
    - Selection & replacement module
    - `ModuleMetadata`:
      - id: "selection_participants"
      - category: SELECTION
      - required_spec_fields: ["selection_date", "target_categories"]
      - optional_spec_fields: ["selection_config.algorithm", "selection_config.data_source"]
      - suggested_modules: ["registration_page"]
      - stores_data: True (checks if selection runs exist)
    - `validate_specification()`: Check selection_config and target categories
    - `has_data()`: Query if SelectionRunRecord exists

### Phase 4: Assembly Creation Integration

**Objective:** Update assembly creation workflow to include specification and modules

#### Modified Files

16. **`src/opendlp/service_layer/assembly_service.py`**
    - Modify `create_assembly()`:
      - After creating Assembly, create default AssemblySpecification
      - Enable "specification" module by default
      - Optionally apply template (if template_id provided)
    - Add `apply_template(uow, user_id, assembly_id, template_id) -> AssemblySpecification`

17. **`src/opendlp/domain/assembly.py`** (optional modification)
    - Consider adding `specification` property to Assembly (lazy-loaded relationship)
    - Or keep specification accessed via separate service calls

#### Template System

18. **`src/opendlp/domain/templates/__init__.py`** (new package)
    - Template definitions as domain concepts (Python dicts or dataclasses)
    - Example templates:
      - "UK Standard": Enable invitation_uk + registration_page + selection + confirmation
      - "Selection Only (CSV)": Enable selection only, set data_source = csv
      - "Australia Standard": Enable invitation_australia + registration_page + selection

19. **`src/opendlp/domain/templates/registry.py`**
    - `TemplateRegistry` similar to ModuleRegistry
    - `Template` dataclass:
      - `id: str`
      - `name: str`
      - `description: str`
      - `enabled_modules: list[str]`
      - `default_spec_values: dict[str, Any]`
    - Methods: `get()`, `all()`, `apply_to_specification()`

### Phase 5: UI/Entrypoints

**Objective:** Create web interface for managing modules and specification

#### New Routes/Templates

20. **`src/opendlp/entrypoints/blueprints/assembly_spec.py`** (new blueprint)
    - Routes:
      - `GET /assemblies/<id>/specification` - View/edit specification
      - `POST /assemblies/<id>/specification` - Update specification fields
      - `GET /assemblies/<id>/modules` - Manage enabled modules
      - `POST /assemblies/<id>/modules/enable` - Enable a module
      - `POST /assemblies/<id>/modules/disable` - Disable a module
      - `GET /assemblies/<id>/targets` - Manage target categories
      - `POST /assemblies/<id>/targets/categories` - Add/update category
      - `DELETE /assemblies/<id>/targets/categories/<category_id>` - Delete category
    - All routes require `@require_assembly_management` decorator

21. **`src/opendlp/entrypoints/forms.py`**
    - Add forms:
      - `AssemblySpecificationForm` (timeline fields, event details)
      - `TargetCategoryForm` (name, description, required)
      - `TargetValueForm` (value, target_count, minimum_count)
      - `ModuleConfigForm` (dynamic based on module)

22. **Templates**
    - `templates/assembly/specification.html` - Main specification edit page
    - `templates/assembly/modules.html` - Module management page
    - `templates/assembly/targets.html` - Target categories management page

#### Assembly Creation Wizard Enhancement

23. **Modify `src/opendlp/entrypoints/blueprints/assemblies.py`**
    - Add template selection step to creation wizard
    - After assembly created, redirect to module selection page
    - Allow module changes before "finalizing" assembly

### Phase 6: Permissions Enhancement

**Objective:** Integrate module permissions with existing system

#### Modified Files

24. **`src/opendlp/domain/value_objects.py`**
    - No changes needed (existing GlobalRole sufficient)

25. **Module metadata** (in each module implementation)
    - Set `required_global_role` appropriately:
      - `invitation_uk_address`: `GlobalRole.ADMIN` (requires payment)
      - `invitation_database`: `GlobalRole.ADMIN` (privacy concerns)
      - Most others: `GlobalRole.GLOBAL_ORGANISER` or None

26. **Service layer** (already handled in Phase 2)
    - `enable_module()` checks `module.metadata.required_global_role`

## Critical Files to Create/Modify

### New Files (18 files)

1. `src/opendlp/domain/assembly_specification.py` - Core domain entity
2. `src/opendlp/domain/targets.py` - Target categories domain entities
3. `src/opendlp/domain/modules/__init__.py` - Module package
4. `src/opendlp/domain/modules/base.py` - Module protocol and metadata
5. `src/opendlp/domain/modules/registry.py` - Module registry
6. `src/opendlp/domain/modules/specification_module.py` - Mandatory module
7. `src/opendlp/domain/modules/registration/__init__.py`
8. `src/opendlp/domain/modules/registration/registration_page_module.py` - Registration module
9. `src/opendlp/domain/modules/selection/__init__.py`
10. `src/opendlp/domain/modules/selection/participants_module.py` - Selection module
11. `src/opendlp/service_layer/specification_service.py` - Specification services
12. `src/opendlp/domain/templates/__init__.py` - Template package
13. `src/opendlp/domain/templates/registry.py` - Template registry
14. `src/opendlp/entrypoints/blueprints/assembly_spec.py` - Specification blueprint
15. `templates/assembly/specification.html` - Specification UI
16. `templates/assembly/modules.html` - Module management UI
17. `templates/assembly/targets.html` - Target categories UI
18. `migrations/versions/XXXX_add_assembly_specifications.py` - Database migration

### Modified Files (7 files)

1. `src/opendlp/adapters/orm.py` - Add table definitions
2. `src/opendlp/adapters/database.py` - Add imperative mappings
3. `src/opendlp/service_layer/repositories.py` - Add repository interfaces
4. `src/opendlp/adapters/sql_repository.py` - Implement repositories
5. `src/opendlp/service_layer/assembly_service.py` - Integrate specification creation
6. `src/opendlp/entrypoints/forms.py` - Add specification/target forms
7. `src/opendlp/entrypoints/blueprints/assemblies.py` - Enhance creation wizard

## Data Migration Strategy

1. **Initial migration** creates empty specifications for all existing assemblies
2. **Backfill basic data** from existing Assembly fields:
   - Copy `first_assembly_date` to `first_session_date`
   - Copy `number_to_select` to target counts (if target categories exist)
3. **Gradual enhancement**: Users fill in detailed specification over time

## Testing Strategy

### Unit Tests

- `tests/unit/test_assembly_specification.py` - Domain model logic
- `tests/unit/test_targets.py` - Category/value validation
- `tests/unit/test_module_registry.py` - Module registration and lookup
- `tests/unit/test_specification_module.py` - Module validation logic

### Integration Tests

- `tests/integration/test_specification_service.py` - Service layer operations
- `tests/integration/test_specification_repository.py` - Database persistence
- `tests/integration/test_module_enablement.py` - Enable/disable flows

### End-to-End Tests (Playwright)

- Create assembly → select template → customize modules → edit specification
- Add target categories and values
- Enable/disable modules with permission checks
- Validate specification for enabled modules

## Verification Steps

1. **Database Schema:**

   ```bash
   # Check tables created
   just psql -c "\d assembly_specifications"
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

3. **Create Assembly with Specification:**

   ```python
   # Via service layer
   from opendlp.service_layer import assembly_service, specification_service
   # Create assembly
   assembly = assembly_service.create_assembly(uow, user_id, title="Test")
   # Get its specification
   spec = specification_service.get_specification(uow, user_id, assembly.id)
   assert spec.assembly_id == assembly.id
   ```

4. **Module Enablement:**

   ```python
   # Enable registration module
   spec = specification_service.enable_module(uow, user_id, assembly.id, "registration_page")
   assert spec.is_module_enabled("registration_page")
   ```

5. **Target Categories Management:**

   ```python
   # Add target category
   from opendlp.domain.targets import TargetCategory, TargetValue
   gender = TargetCategory(
       category_id=uuid.uuid4(),
       name="Gender",
       values=[
           TargetValue("Male", target_count=15),
           TargetValue("Female", target_count=15),
       ]
   )
   specification_service.add_target_category(uow, user_id, assembly.id, gender)
   ```

6. **Run Tests:**

   ```bash
   just test  # All tests including new ones
   just check  # Linting and type checking
   ```

7. **Test UI Flow:**
   - Create new assembly via web interface
   - Select "UK Standard" template
   - Verify modules are pre-enabled
   - Navigate to specification page
   - Fill in timeline dates
   - Navigate to targets page
   - Add Gender category with values
   - Navigate to modules page
   - Try to enable a module requiring admin (should fail if not admin)

## Open Questions / Future Considerations

1. **Module Lifecycle Hooks**: Should modules have `on_enable()` / `on_disable()` hooks for setup/cleanup?

2. **Module Dependencies**: Current design uses "suggested modules" (warnings only). Do we need hard dependencies later?

3. **Specification Versioning**: Should we version specifications for audit trail? Or is `updated_at` sufficient?

4. **Module Data Auditing**: `has_data()` is binary. Should we track data counts for better UX?

5. **Target Category Presets**: Should we ship with preset categories (Gender, Age, etc.) or require manual creation?

6. **Translation of Module Metadata**: Module names/descriptions should be translatable - integrate with existing i18n system.

7. **Module Deprecation**: How to handle deprecating old modules while keeping data accessible?

8. **Template Customization**: Should users be able to save their own custom templates, or only use predefined ones?

9. **Specification Import/Export**: Should specifications be exportable for backup/sharing between assemblies?

## Design Rationale

### Why "Target Categories" instead of "Demographics"?

The original planning document used "Demographics" but the actual use case is broader. Target categories include:

- Traditional demographics: Gender, Age, Ethnicity, Location
- Attitudinal: "What is your attitude to the European Union?"
- Behavioral: "Have you participated in local politics?"
- Knowledge-based: "How familiar are you with climate policy?"

All of these are used to define **selection targets** for the sortition algorithm. The term "target categories" is more accurate and extensible.

### Why Modules in Domain Layer?

Modules define **what features are available** and **what they require** - this is domain knowledge, not infrastructure. The module system encapsulates:

- Business rules about module compatibility (families)
- Validation logic for specifications
- Permission requirements

These are all domain concerns, so modules belong in `src/opendlp/domain/modules/`.

Similarly, templates are **preset configurations** that represent common assembly patterns - also domain knowledge.

### Why Hybrid Storage (Columns + JSON)?

- **Columns for timeline dates**: Enable date-range queries, sorting, indexing
- **Columns for event details**: Frequently displayed, good to have type-safe
- **Separate tables for targets**: Normalized design enables:
  - Rich reporting queries (JOIN on registrant responses)
  - Proper foreign key constraints
  - Easy addition of metadata per category
- **JSON for module configs**: Each module has different config needs, JSON provides flexibility without constant migrations
- **JSON for custom fields**: Client-specific needs without schema changes

This balances **queryability** (columns/tables) with **flexibility** (JSON) and **type safety** (domain validation).

## Success Criteria

✅ Assembly creation wizard includes template selection
✅ Specification page shows timeline, event details, custom fields
✅ Target categories page supports add/edit/delete categories and values
✅ Modules page shows available modules with enable/disable actions
✅ Permission checks prevent unauthorized module enablement
✅ Cannot disable modules that have created data
✅ Module validation errors shown when specification incomplete
✅ All tests pass (unit, integration, e2e)
✅ Type checking passes (mypy)
✅ Documentation updated in CLAUDE.md

## Next Steps for Team Review

1. **Review terminology**: Do "target categories" and "modules" resonate?
2. **Database schema**: Are we happy with the hybrid approach?
3. **Module location**: Agree that modules/templates are domain concepts?
4. **Permissions model**: Is per-module `required_global_role` sufficient?
5. **Template system**: What predefined templates do we need?
6. **Open questions**: Which should we answer before implementation?

## Timeline Estimate

**Note**: No time estimates provided per project guidelines. This is a sequenced breakdown of work phases to be estimated by the team.
