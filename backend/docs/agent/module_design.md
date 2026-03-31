# Module System Design

**Status:** Design for implementation - implementation is delayed until after the registration page is done
**Date:** 2026-03-30
**Scope:** Module system foundation and UI (Phase B + C from original planning)

## Context

### Already Implemented

- **Target Categories & Values** — full stack (domain, ORM, repos, services, routes, UI, tests)
- **Respondents** — full stack (domain, ORM, repos, services, routes, UI, tests)
- **Assembly tabs UI** — Details, Data, Targets, Respondents, Selection, Team Members
- **CSV import/export** for both targets and respondents
- **Selection integration** with sortition-algorithms via both GSheet and CSV data sources

### Deferred (Not In Scope)

- **Assembly specification fields** (timeline dates, event details) — to be added later
- **Template system** (predefined assembly configurations) — to be added later
- **Data tab refactoring** into a module — to be done later

### Design Decisions Already Made

- **Targets and Respondents** are core infrastructure, always available to every assembly. Modules that need them (e.g. selection, registration) just use them — they are not themselves modules.
- **Permissions**: assembly organiser role required to enable/disable any module. No per-module role requirements.
- **No family constraints**: the "one module per family" concept is dropped. Can be revisited if needed.
- **Disable behaviour**: warn and require confirmation when a module has data, then disable while preserving the data. Module can be re-enabled.
- **Respondent data is shared** across multiple modules (registration, selection, confirmation) — disabling one module does not affect respondent data used by others.
- **Module routes** go in a new blueprint.
- **Existing `config` JSON column** on assemblies is unused and should be dropped via migration.

---

## 1. Domain Layer

### 1.1 Module Definitions

#### `src/opendlp/domain/modules/base.py`

```python
class ModuleCategory(enum.Enum):
    ASSEMBLY = "assembly"
    LOCATION = "location"
    INVITATION = "invitation"
    REGISTRATION = "registration"
    SELECTION = "selection"
    CONFIRMATION = "confirmation"

@dataclass
class ModuleMetadata:
    id: str                              # e.g. "registration_page"
    name: str                            # human-readable display name
    category: ModuleCategory
    description: str
    required_assembly_fields: list[str]  # assembly fields that must be set for this module
    optional_assembly_fields: list[str]  # assembly fields that this module can use if set

class ModuleProtocol(Protocol):
    @property
    def metadata(self) -> ModuleMetadata: ...
    def validate_assembly(self, assembly: Assembly, module_config: ModuleConfig | None) -> list[str]: ...
    def has_data(self, assembly_id: UUID, uow: UnitOfWork) -> bool: ...
```

`ModuleMetadata` is deliberately lean. Fields like `required_global_role`, `requires_payment`, `stores_data`, `family`, and `suggested_modules` are omitted (YAGNI). They can be added when a concrete use case arrives.

### 1.2 Module Registry

#### `src/opendlp/domain/modules/registry.py`

```python
class ModuleRegistry:
    """Class-level registry. Modules register at import time."""
    @classmethod
    def register(cls, module: ModuleProtocol) -> None: ...
    @classmethod
    def get(cls, module_id: str) -> ModuleProtocol | None: ...
    @classmethod
    def all(cls) -> dict[str, ModuleProtocol]: ...
    @classmethod
    def by_category(cls, category: ModuleCategory) -> dict[str, ModuleProtocol]: ...
```

### 1.3 Module `__init__.py`

`src/opendlp/domain/modules/__init__.py` imports all module implementations to trigger registration.

### 1.4 Initial Module Implementations

Three modules to prove the system, all in `src/opendlp/domain/modules/`:

1. **`assembly_module.py`** — always-enabled core module, validates basic assembly fields (title, question)
2. **`registration_page_module.py`** — registration page feature, requires `registration_deadline` (once that field exists)
3. **`selection_module.py`** — selection feature, requires `number_to_select`

---

## 2. ModuleConfig Entity

### `src/opendlp/domain/module_config.py`

```python
class ModuleConfig:
    config_id: UUID
    assembly_id: UUID
    module_id: str          # e.g. "registration_page"
    config: dict[str, Any]  # module-specific JSON configuration
    created_at: datetime
    updated_at: datetime
```

One row per enabled module per assembly. UNIQUE constraint on `(assembly_id, module_id)`.

---

## 3. Assembly Model Changes

Add to `Assembly`:

- `enabled_modules: list[str]` — JSON array column, e.g. `["assembly", "selection"]`
- `custom_fields: dict[str, Any]` — JSON column for extensibility
- Methods: `enable_module(module_id)`, `disable_module(module_id)`, `is_module_enabled(module_id)`, `get_enabled_modules()`

---

## 4. ORM Changes

### New table: `module_configs`

```sql
CREATE TABLE module_configs (
    config_id UUID PRIMARY KEY,
    assembly_id UUID NOT NULL REFERENCES assemblies(id) ON DELETE CASCADE,
    module_id VARCHAR(100) NOT NULL,
    config JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (assembly_id, module_id)
);
CREATE INDEX ix_module_configs_assembly_id ON module_configs (assembly_id);
```

### Changes to `assemblies` table

```sql
ALTER TABLE assemblies DROP COLUMN config;
ALTER TABLE assemblies ADD COLUMN enabled_modules JSON DEFAULT '[]';
ALTER TABLE assemblies ADD COLUMN custom_fields JSON DEFAULT '{}';
```

---

## 5. Migration

Single migration that:

1. Drops the unused `config` column from `assemblies`
2. Adds `enabled_modules` (JSON, default `'[]'`) to `assemblies`
3. Adds `custom_fields` (JSON, default `'{}'`) to `assemblies`
4. Creates the `module_configs` table
5. Backfills: sets `enabled_modules = '["assembly", "selection"]'` for all existing assemblies (every assembly in the database currently uses selection)

---

## 6. Repository

### Abstract interface in `repositories.py`

```python
class ModuleConfigRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, config: ModuleConfig) -> ModuleConfig: ...
    @abc.abstractmethod
    def get(self, config_id: UUID) -> ModuleConfig | None: ...
    @abc.abstractmethod
    def get_by_assembly_and_module(self, assembly_id: UUID, module_id: str) -> ModuleConfig | None: ...
    @abc.abstractmethod
    def list_by_assembly(self, assembly_id: UUID) -> list[ModuleConfig]: ...
    @abc.abstractmethod
    def delete(self, config_id: UUID) -> None: ...
```

### SQL implementation in `sql_repository.py`

`SqlAlchemyModuleConfigRepository` implementing the above.

---

## 7. Service Layer

New service file `src/opendlp/service_layer/module_service.py`:

- `enable_module(uow, user_id, assembly_id, module_id, config=None)` — checks user is assembly organiser, enables on assembly, creates ModuleConfig if config provided
- `disable_module(uow, user_id, assembly_id, module_id)` — checks permissions, calls `has_data()` and returns warning info if data exists (caller handles confirmation), removes ModuleConfig, disables on assembly
- `update_module_config(uow, user_id, assembly_id, module_id, config_updates)`
- `get_module_config(uow, assembly_id, module_id) -> ModuleConfig | None`
- `get_available_modules(assembly_id) -> list[ModuleMetadata]` — all registered modules with enabled status
- `validate_assembly_modules(uow, assembly_id) -> dict[str, list[str]]` — runs all enabled module validators, returns module_id -> list of validation errors

---

## 8. Routes and UI

### New blueprint: `src/opendlp/entrypoints/blueprints/modules.py`

Routes:

- `GET /assemblies/<id>/modules` — view enabled/available modules grouped by category
- `POST /assemblies/<id>/modules/<module_id>/enable` — enable a module
- `POST /assemblies/<id>/modules/<module_id>/disable` — disable a module (with confirmation if has_data)
- `GET /assemblies/<id>/modules/<module_id>/config` — edit module config form
- `POST /assemblies/<id>/modules/<module_id>/config` — update module config

### Assembly tabs

Add a "Modules" tab to the assembly tab bar.

### Templates

- `templates/backoffice/modules/view_modules.html` — list of all modules by category, toggles for enable/disable
- `templates/backoffice/modules/module_config.html` — config editing form (if module has configurable options)

---

## 9. Files to Create or Modify

### New files

| File                                                     | Purpose                                        |
| -------------------------------------------------------- | ---------------------------------------------- |
| `src/opendlp/domain/modules/__init__.py`                 | Module package init, imports implementations   |
| `src/opendlp/domain/modules/base.py`                     | ModuleCategory, ModuleMetadata, ModuleProtocol |
| `src/opendlp/domain/modules/registry.py`                 | ModuleRegistry                                 |
| `src/opendlp/domain/modules/assembly_module.py`          | Core assembly module                           |
| `src/opendlp/domain/modules/registration_page_module.py` | Registration page module                       |
| `src/opendlp/domain/modules/selection_module.py`         | Selection module                               |
| `src/opendlp/domain/module_config.py`                    | ModuleConfig entity                            |
| `src/opendlp/service_layer/module_service.py`            | Module service functions                       |
| `src/opendlp/entrypoints/blueprints/modules.py`          | Module routes blueprint                        |
| `templates/backoffice/modules/view_modules.html`         | Module management page                         |
| `templates/backoffice/modules/module_config.html`        | Module config edit page                        |
| `migrations/versions/XXXX_add_module_system.py`          | Migration                                      |

### Modified files

| File                                                 | Change                                                 |
| ---------------------------------------------------- | ------------------------------------------------------ |
| `src/opendlp/domain/assembly.py`                     | Add `enabled_modules`, `custom_fields`, module methods |
| `src/opendlp/adapters/orm.py`                        | Add `module_configs` table, modify `assemblies` table  |
| `src/opendlp/adapters/database.py`                   | Add ModuleConfig mapping                               |
| `src/opendlp/service_layer/repositories.py`          | Add ModuleConfigRepository ABC                         |
| `src/opendlp/adapters/sql_repository.py`             | Add SqlAlchemyModuleConfigRepository                   |
| `src/opendlp/service_layer/unit_of_work.py`          | Add module_configs repo to UoW                         |
| `src/opendlp/entrypoints/blueprints/__init__.py`     | Register modules blueprint                             |
| `templates/backoffice/components/assembly_tabs.html` | Add Modules tab                                        |
| `tests/conftest.py`                                  | Add module_configs DELETE to `_delete_all_test_data()` |

---

## 10. Testing Strategy

### Unit Tests

- ModuleMetadata and ModuleCategory
- ModuleRegistry: register, get, all, by_category
- ModuleConfig entity
- Assembly module methods (enable, disable, is_enabled)
- Each module implementation: validate_assembly, has_data
- Module service logic (permission checks, enable/disable flows)

### Contract Tests

- ModuleConfigRepository CRUD operations

### Integration Tests

- Module enable/disable through service layer with UoW
- ModuleConfig persistence and retrieval
- Module validation against assembly state
- Disable-with-data warning flow

### E2E Tests

- View modules page for an assembly
- Enable and disable modules via UI
- Confirm disable when module has data
- Edit module configuration

---

## 11. Questions

### Q1: Where should the Modules tab go in the tab order?

Current order: Details, Data, Targets, Respondents, Selection, Team Members.

Options:

- (a) After Details: Details, **Modules**, Data, Targets, ...
- (b) After Team Members: ..., Team Members, **Modules**
- (c) Before Team Members: ..., Selection, **Modules**, Team Members
- (d) Other

**Answer:**

### Q2: Should `registration_page_module` validate `registration_deadline` now?

The `registration_deadline` field doesn't exist on Assembly yet (it's in the deferred spec fields phase). Should the registration module:

- (a) Have an empty `required_assembly_fields` for now and add `registration_deadline` when the field is created
- (b) Include `registration_deadline` in its requirements, which will cause validation warnings until the field exists
- (c) Skip the registration module entirely and only implement `assembly` + `selection` for now

**Answer:**

### Q3: What should `assembly_module.validate_assembly()` check?

The core assembly module validates basic fields. Which fields should be required?

- `title` (currently always required at creation)
- `question` (currently optional)
- `first_assembly_date` (currently optional)
- `number_to_select` (currently optional, but required by selection)
- Others?

**Answer:**

### Q4: Should the Modules tab be visible to all assembly roles?

Assembly organisers can enable/disable modules. Should confirmation-callers and other assembly roles:

- (a) See the Modules tab as read-only (can view but not toggle)
- (b) Not see the Modules tab at all
- (c) Something else

**Answer:**

### Q5: How should `has_data()` work for shared data?

Respondent data is shared across registration, selection, and confirmation modules. When the user tries to disable the registration module and respondents exist:

- (a) `has_data()` returns true — warn that respondent data exists (even though other modules use it too)
- (b) `has_data()` returns false — because the data isn't exclusively owned by registration
- (c) Show a more nuanced message like "Respondent data will be preserved and remains available to other modules"

**Answer:**

### Q6: Should `custom_fields` be added now?

The `custom_fields` JSON column on assemblies is for future extensibility. Since the spec fields phase is deferred, should we:

- (a) Add it now anyway as part of the migration (it's just a JSON column with default `'{}'`)
- (b) Defer it until we have a concrete use case

**Answer:**
