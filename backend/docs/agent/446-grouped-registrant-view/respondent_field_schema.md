# Respondent Field Schema

**Status:** Design for implementation
**Date:** 2026-04-17
**Branch:** 446-grouped-registrant-view
**Scope:** Per-assembly schema describing respondent fields — their group, display label, and display order. Drives the grouped `view_registrant` page in this phase; will later seed the registration form module.

## Context

### What exists today

- Respondents have a fixed set of database columns (`external_id`, `email`, `selection_status`, `consent`, `stay_on_db`, `eligible`, `can_attend`, `source_type`, `source_reference`, `created_at`, `updated_at`, `selection_run_id`) plus a free-form `attributes: dict[str, Any]` JSON column.
- CSV import populates `attributes` from column headers; column order is lost after import.
- `TargetCategory` matches respondent attribute columns by case-insensitive name. No stored mapping.
- `Assembly.name_fields` is a cached heuristic detecting name columns — a useful precedent.
- `view_registrant` currently renders two hardcoded tables ("Details" and "Attributes") with no grouping.
- GSheet-based assemblies do not store respondents in the database — schema does not apply to them.

### What this adds

A new per-assembly entity, `RespondentFieldDefinition`, stored in its own table, with fixed groups and an explicit display order. Auto-populated on first CSV import using heuristics, reconciled with a confirm-and-apply diff UI on subsequent uploads, editable via a dedicated settings page.

### Decisions locked in from design Q&A

- **Typeless in phase 1.** No `field_type` column. Every field renders as a string.
- **Fixed catalogue of groups** (not per-assembly custom). Expand later if needed.
- **Mix of schema and hardcoded fields.** Some reserved fields (`email`, `eligible`, `can_attend`, `consent`, `stay_on_db`) live in the schema so the organiser can reorder and regroup them; others (`external_id`, `selection_status`, `selection_run_id`, `source_type`, `source_reference`, `created_at`, `updated_at`) are hardcoded blocks rendered above and below the schema-driven section.
- **Reconciliation is explicit.** Re-uploading a CSV with changed columns shows a diff page ("new: X, absent: Y") that the organiser must confirm.
- **Derived-field placeholders ship now, derivation logic does not.** The schema carries `is_derived`, `derived_from`, `derivation_kind` nullable columns; rows marked derived are rendered with a "not yet implemented" badge for now.
- **No `TargetCategory` linkage change.** Targets keep matching by name. A nullable FK to `RespondentFieldDefinition` can be added later without schema churn.
- **Not in scope:** field types, registration form rendering, target linkage, derivation computation, list-view ordering, CSV export ordering, field visibility/hiding.

---

## 1. Domain Layer

### 1.1 Group enum

`src/opendlp/domain/respondent_field_schema.py`

```python
class RespondentFieldGroup(enum.Enum):
    ELIGIBILITY = "eligibility"          # eligible, can_attend
    NAME_AND_CONTACT = "name_and_contact" # first_name, last_name, email, phone_number
    ADDRESS = "address"                   # address_line_*, city, postcode
    ABOUT_YOU = "about_you"               # gender, dob_*, ethnicity, education_level, target-ish attributes
    CONSENT = "consent"                   # consent, stay_on_db
    OTHER = "other"                       # catch-all for unrecognised fields

GROUP_DISPLAY_ORDER: list[RespondentFieldGroup] = [
    RespondentFieldGroup.ELIGIBILITY,
    RespondentFieldGroup.NAME_AND_CONTACT,
    RespondentFieldGroup.ADDRESS,
    RespondentFieldGroup.ABOUT_YOU,
    RespondentFieldGroup.CONSENT,
    RespondentFieldGroup.OTHER,
]

GROUP_LABELS: dict[RespondentFieldGroup, str] = {
    RespondentFieldGroup.ELIGIBILITY: _l("Eligibility"),
    RespondentFieldGroup.NAME_AND_CONTACT: _l("Name and contact"),
    RespondentFieldGroup.ADDRESS: _l("Address"),
    RespondentFieldGroup.ABOUT_YOU: _l("About you"),
    RespondentFieldGroup.CONSENT: _l("Consent"),
    RespondentFieldGroup.OTHER: _l("Other"),
}
```

Display labels are lazy-gettext so translations work. Per-assembly label overrides are out of scope for this phase — organisers can reorder and regroup fields but not rename groups.

### 1.2 `RespondentFieldDefinition` entity

`src/opendlp/domain/respondent_field_schema.py`

```python
@dataclass
class RespondentFieldDefinition:
    field_id: uuid.UUID
    assembly_id: uuid.UUID
    field_key: str                        # matches respondent.attributes key OR fixed field name
    label: str                            # display label; defaults to a humanised field_key
    group: RespondentFieldGroup
    sort_order: int                       # position within group; dense integers, re-issued on reorder
    is_fixed: bool                        # True for reserved respondent fields (email, consent, ...)
    is_derived: bool = False              # placeholder for phase 2; always False in phase 1
    derived_from: list[str] | None = None # names of source fields; None unless is_derived
    derivation_kind: str | None = None    # free-form label (e.g. "age_bracket_from_dob"); None unless is_derived
    created_at: datetime
    updated_at: datetime
```

- `field_key` is the **raw attribute key** (preserving case) so it matches `respondent.attributes` lookups exactly; for fixed fields it is the DB column name (`"email"`, `"consent"`, ...).
- UNIQUE constraint on `(assembly_id, field_key)`.
- `is_fixed=True` rows cannot be deleted by the organiser (the underlying DB column always exists) but can be moved to a different group or reordered. Deleting a non-fixed row also does not touch respondent data — the attribute value still exists on each respondent; it's just no longer listed in the detail page.
- `sort_order` is unique within `(assembly_id, group)`. We hand out multiples of 10 on creation (`10, 20, 30, ...`) so drag-and-drop reorder can insert between values before re-issuing.

### 1.3 Fixed field split

Two categories of fixed fields:

**In-schema fixed fields** (rows in `respondent_field_definitions`, `is_fixed=True`, editable group/order):

| Field | Default group |
| --- | --- |
| `email` | name_and_contact |
| `eligible` | eligibility |
| `can_attend` | eligibility |
| `consent` | consent |
| `stay_on_db` | consent |

**Hardcoded blocks** (never in schema, rendered outside the group loop):

| Field | Block | Position |
| --- | --- | --- |
| `selection_status` | status | top (prominent) |
| `selection_run_id` | status | top (only if set) |
| `external_id` | status | top |
| `source_type` | audit | bottom, collapsible |
| `source_reference` | audit | bottom |
| `created_at` | audit | bottom |
| `updated_at` | audit | bottom |

Rationale: the status block surfaces "what matters at a glance" (is this person selected? who are they?); the audit block is provenance data that an organiser rarely needs but wants to find. Neither belongs in the registration form the schema will later seed, so excluding them from the schema is consistent.

### 1.4 `Assembly` model changes

None. The schema is a child aggregate referenced by `assembly_id` FK; no new columns on `assemblies`. Dropping the unused `assemblies.config` column stays part of the separate module-system migration.

---

## 2. Auto-Population Heuristics

Applied on first CSV import (when no schema exists for an assembly) and when new columns appear on re-upload.

### 2.1 Normalisation

`normalise(key: str) -> str` lowercases and strips non-alphanumeric characters. Matches `Assembly.name_fields` semantics exactly (line `domain/assembly.py:104-123`). Both pattern rules and per-key lookups use the normalised form.

### 2.2 Pattern rules

Checked in declaration order; first match wins.

```python
HEURISTIC_RULES: list[tuple[RespondentFieldGroup, set[str], list[str]]] = [
    # (group, exact-normalised matches, substring patterns)
    (RespondentFieldGroup.ELIGIBILITY,
     {"eligible", "canattend", "available"},
     []),
    (RespondentFieldGroup.NAME_AND_CONTACT,
     {"firstname", "givenname", "forename", "lastname", "surname", "familyname",
      "fullname", "name", "email", "emailaddress", "phone", "phonenumber",
      "mobile", "mobilenumber", "tel", "telephone", "contactnumber",
      "countrycode", "externalid"},
     []),
    (RespondentFieldGroup.ADDRESS,
     {"address", "addressline1", "addressline2", "addressline3", "street",
      "streetaddress", "city", "town", "county", "region", "state", "postcode",
      "zip", "zipcode", "postalcode", "country"},
     ["addressline", "addrline"]),
    (RespondentFieldGroup.CONSENT,
     {"consent", "consenttocontact", "stayondb", "stayonlist",
      "marketingconsent", "futurecontact"},
     []),
    (RespondentFieldGroup.ABOUT_YOU,
     {"gender", "sex", "age", "agebracket", "agerange", "dob", "dateofbirth",
      "dobday", "dobmonth", "dobyear", "yearofbirth", "birthyear", "ethnicity",
      "race", "disability", "disabilitystatus", "education", "educationlevel",
      "qualification", "income", "incomebracket", "occupation", "employment",
      "employmentstatus"},
     ["opinion", "attitude"]),  # "opinion_about_climate" -> about_you
]
```

Any column matching a **`TargetCategory.name` already defined on the assembly** (case-insensitive) goes straight to `ABOUT_YOU` regardless of pattern rules — target-relevant fields are the canonical "about you" content. This rule runs before the pattern list.

Everything unmatched → `RespondentFieldGroup.OTHER`.

### 2.3 Default label

Default label is a humanised form of `field_key` (underscore → space, title-case), e.g. `first_name` → "First name", `dob_day` → "Dob day". Organiser can override.

### 2.4 Default `sort_order`

Within each group, preserve CSV header order. The `import_respondents_from_csv` service will need to pass the ordered header list into schema population (currently CSV reader fieldnames order is used implicitly — we need to make it explicit).

Fixed fields are seeded in a predictable order (e.g. eligibility: `eligible`, `can_attend`; consent: `consent`, `stay_on_db`) rather than CSV order, because they may not even be columns in the uploaded CSV.

---

## 3. ORM and Migration

### 3.1 New table

```sql
CREATE TABLE respondent_field_definitions (
    field_id UUID PRIMARY KEY,
    assembly_id UUID NOT NULL REFERENCES assemblies(id) ON DELETE CASCADE,
    field_key VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    field_group VARCHAR(50) NOT NULL,
    sort_order INTEGER NOT NULL,
    is_fixed BOOLEAN NOT NULL DEFAULT FALSE,
    is_derived BOOLEAN NOT NULL DEFAULT FALSE,
    derived_from JSON DEFAULT NULL,
    derivation_kind VARCHAR(100) DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (assembly_id, field_key),
    UNIQUE (assembly_id, field_group, sort_order)
);
CREATE INDEX ix_respondent_field_definitions_assembly
  ON respondent_field_definitions (assembly_id);
```

`field_group` stored as string (the enum `value`), not as a PostgreSQL enum type, so adding groups later is a data-only migration rather than an `ALTER TYPE`.

### 3.2 Backfill

The migration backfills a schema for every existing assembly that has respondents:

1. For each `Assembly` with `COUNT(respondents) > 0`, examine the first respondent's attributes to get the CSV column order (best available — dicts preserve insertion order).
2. Run the heuristic rules over the keys.
3. Insert fixed rows (`email`, `eligible`, `can_attend`, `consent`, `stay_on_db`) in their default groups.
4. Insert one row per attribute key.

Assemblies with zero respondents get no schema rows — the schema is created lazily on first CSV upload or via the "initialise schema" UI button (for registration-form-first workflows).

### 3.3 Test-data cleanup

Add `respondent_field_definitions` DELETE to `_delete_all_test_data()` in `tests/conftest.py` and `delete_all_except_standard_users()` in `tests/bdd/conftest.py` — **before** the `assemblies` DELETE (child table) and after any table with an FK to assemblies that hasn't already been deleted.

---

## 4. Reconciliation on Re-Upload

### 4.1 Flow change

Currently `/assembly/<id>/data/upload-respondents` POSTs a CSV and immediately replaces all respondents (`respondents.py:38-98`). The new flow inserts a confirmation step when a schema already exists.

```
POST /upload-respondents  →
  if no existing schema OR diff is empty:
    proceed as today, auto-populate schema afterwards
  else:
    stash CSV in server-side session/tempfile
    redirect to diff page
GET  /upload-respondents/confirm-diff  →
  show: new columns (group assignments), absent columns (kept in schema),
        unchanged columns, destructive warning
POST /upload-respondents/confirm-diff  →
  apply import + schema reconciliation
  OR cancel (discard stashed CSV)
```

### 4.2 Diff categories

Given `existing_schema_keys` and `new_csv_headers` (both excluding the id column and the schema's in-schema fixed fields):

- **Unchanged** — key in both. Keep schema row as-is.
- **New** — key in CSV only. Insert schema row (heuristic group, default label, appended sort_order).
- **Absent** — key in schema only. Keep schema row; no respondent will have data for it. Flag in UI with "No data in latest upload" — but don't delete, because (a) a typo fix in the next upload shouldn't lose the grouping, (b) organiser may have renamed in the CSV and wants to rename the schema row to match.

Organiser gets an inline option on the diff page: "rename `email_addr` → `email`" (merges absent+new with matching humanised labels). Phase 1 implementation can skip the rename UI and just add + flag-absent; we note this as a follow-up enhancement.

### 4.3 CSV stash and size limit

Use the existing Redis session backing (flask-session). Store the CSV contents under a one-shot key `csv_import_pending:{user_id}:{assembly_id}` with a 30-minute TTL. Clear on confirm or cancel.

To keep the stash bounded (and to avoid any risk of hitting Redis' 512MB value ceiling) the upload handler enforces a configurable maximum size. Real respondent CSVs in production sit comfortably under 2MB, so the default leaves generous headroom:

- New env var **`MAX_CSV_UPLOAD_MB`**, parsed in `src/opendlp/config.py`.
  - **Default:** `50` (50MB).
  - **Hard ceiling:** `500`. Values above this are clamped to 500 and a warning is logged at startup.
  - **Minimum:** `1` (reject anything less — clamped up with a warning).
- Add an example line to `env.example`: `MAX_CSV_UPLOAD_MB=50`.
- Enforcement point: the upload route in `entrypoints/blueprints/respondents.py`. If the uploaded file exceeds the limit, return a GOV.UK error page ("CSV is larger than N MB — the limit is configurable via `MAX_CSV_UPLOAD_MB`") without stashing anything. A service-layer assert on `len(csv_content)` provides belt-and-braces for other callers.
- Flask's `MAX_CONTENT_LENGTH` should be set from the same config so oversize requests are rejected at the WSGI layer before we allocate memory.

### 4.4 Edge cases

- **No existing schema** → auto-populate silently, no diff page. This matches the first-upload-ever experience.
- **Schema exists but all columns match** → no diff page (nothing to confirm).
- **id column changed** → surface prominently in the diff page ("ID column changed from `X` to `Y`"). This is already user-selectable at upload time; we just echo it back.

---

## 5. Repository Layer

### 5.1 Abstract interface (`service_layer/repositories.py`)

```python
class RespondentFieldDefinitionRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, field: RespondentFieldDefinition) -> RespondentFieldDefinition: ...
    @abc.abstractmethod
    def add_many(self, fields: list[RespondentFieldDefinition]) -> list[RespondentFieldDefinition]: ...
    @abc.abstractmethod
    def get(self, field_id: UUID) -> RespondentFieldDefinition | None: ...
    @abc.abstractmethod
    def get_by_key(self, assembly_id: UUID, field_key: str) -> RespondentFieldDefinition | None: ...
    @abc.abstractmethod
    def list_by_assembly(self, assembly_id: UUID) -> list[RespondentFieldDefinition]:
        """Returns rows ordered by GROUP_DISPLAY_ORDER then sort_order."""
    @abc.abstractmethod
    def delete(self, field_id: UUID) -> None: ...
    @abc.abstractmethod
    def delete_all_for_assembly(self, assembly_id: UUID) -> int: ...
```

### 5.2 SQL implementation

`SqlAlchemyRespondentFieldDefinitionRepository` in `adapters/sql_repository.py`. Uses ORM table column references per the mypy-compatibility rule in CLAUDE.md.

`list_by_assembly` does the ordering in Python against `GROUP_DISPLAY_ORDER` rather than in SQL, because the display order is a fixed Python list (simpler than a CASE statement and identical cost at our scale).

### 5.3 Fake implementation

Add `FakeRespondentFieldDefinitionRepository` to `tests/fakes.py` alongside the other fakes. Must mirror `SqlAlchemyRespondentFieldDefinitionRepository` behaviour: enforce the `(assembly_id, field_key)` uniqueness, enforce `(assembly_id, field_group, sort_order)` uniqueness, and return `list_by_assembly` results ordered by `GROUP_DISPLAY_ORDER` then `sort_order`. Add the fake to `FakeUnitOfWork` so service-layer tests can use it without hitting the database.

### 5.4 UnitOfWork

Add `respondent_field_definitions: RespondentFieldDefinitionRepository` to `AbstractUnitOfWork` and `SqlAlchemyUnitOfWork`.

---

## 6. Service Layer

New file `src/opendlp/service_layer/respondent_field_schema_service.py`.

### 6.1 Read functions

- `get_schema(uow, assembly_id) -> list[RespondentFieldDefinition]` — ordered list.
- `get_schema_grouped(uow, assembly_id) -> dict[RespondentFieldGroup, list[RespondentFieldDefinition]]` — view-friendly map with all groups present (including empty ones).

### 6.2 Population functions

- `populate_schema_from_headers(uow, user_id, assembly_id, headers: list[str], id_column: str) -> None` — creates fixed rows + one row per header (excluding id_column), applies heuristics, asserts no pre-existing schema.
- `reconcile_schema_with_headers(uow, user_id, assembly_id, headers: list[str], id_column: str) -> ReconciliationDiff` — returns diff dataclass without committing.
- `apply_reconciliation(uow, user_id, assembly_id, diff: ReconciliationDiff) -> None` — inserts new rows, optionally renames (phase-2), commits.

`ReconciliationDiff` dataclass:

```python
@dataclass
class ReconciliationDiff:
    assembly_id: UUID
    unchanged: list[str]
    new_keys: list[tuple[str, RespondentFieldGroup]]  # key + heuristic-suggested group
    absent_keys: list[str]
    id_column_changed: tuple[str, str] | None  # (old, new) or None
```

### 6.3 Edit functions

- `update_field(uow, user_id, assembly_id, field_id, label=None, group=None) -> RespondentFieldDefinition`
- `reorder_group(uow, user_id, assembly_id, group, ordered_field_ids: list[UUID]) -> None` — re-issues sort_orders in multiples of 10.
- `move_field_to_group(uow, user_id, assembly_id, field_id, new_group, position: int | None) -> None` — appends if position is None.
- `delete_field(uow, user_id, assembly_id, field_id) -> None` — rejects fixed fields.
- `initialise_empty_schema(uow, user_id, assembly_id) -> None` — creates just the fixed-field rows (for registration-form-first assemblies with no CSV yet).

All edit functions require `can_manage_assembly(user_id, assembly_id)`.

### 6.4 Integration with existing services

`respondent_service.import_respondents_from_csv` must be updated to:

1. Extract the header list from the CSV reader and pass to the schema service.
2. Call `populate_schema_from_headers` if no schema exists, or expect reconciliation to already be applied.
3. Stop swallowing header order — the current implementation relies on dict iteration; we'll pass the fieldnames list explicitly.

The upload route (`entrypoints/blueprints/respondents.py:38`) splits into upload-begin and upload-confirm handlers.

---

## 7. Routes and UI

### 7.1 Schema management blueprint

Add routes to the existing backoffice blueprint (or a new `respondent_field_schema` blueprint if it grows — start inside backoffice). Prefix: `/backoffice/assembly/<id>/respondent-schema`.

- `GET  /` — view the schema grouped, with per-field "edit label", drag handles per group.
- `POST /fields/<field_id>/edit` — update label/group (HTMX partial).
- `POST /groups/<group>/reorder` — bulk sort_order update (HTMX).
- `POST /fields/<field_id>/delete` — delete a non-fixed field (with confirm).
- `POST /initialise` — one-click init for registration-form-first assemblies.

### 7.2 Navigation

Schema editing is a secondary action from the existing Respondents tab (a "Manage field layout" link near the CSV upload form), not a new top-level tab. Keeps the tab bar short and matches where organisers already think about respondent data.

### 7.3 Templates

- `templates/backoffice/respondent_field_schema/view.html` — main page, grouped list with drag-and-drop per group (Alpine.js with `x-model` patterns per existing interactive-patterns guide).
- `templates/backoffice/respondent_field_schema/_field_row.html` — HTMX partial for a single field row.
- `templates/backoffice/respondent_field_schema/_group.html` — partial for a group section.

### 7.4 `view_registrant` template changes

`templates/backoffice/assembly_view_respondent.html` is rewritten to three sections:

1. **Status block** (hardcoded, top): `external_id` (prominent), `selection_status` (as a GOV.UK tag with status-dependent colour), `selection_run_id` only if present.
2. **Schema-driven middle**: loop `GROUP_DISPLAY_ORDER`, for each group that has fields, render a labelled table (reusing the existing `<dl>` pattern) with rows ordered by `sort_order`. Value lookup:
   - Fixed field (`is_fixed=True`): read from the respondent's DB column (`respondent.email`, `respondent.consent`, ...). Booleans render "Yes / No / —".
   - Non-fixed field: read from `respondent.attributes[field_key]`, fall back to "—".
   - Derived field (`is_derived=True`): render with a "Derivation not yet implemented" muted badge and no value.
3. **Audit block** (hardcoded, bottom, inside a GOV.UK `<details>` element titled "Record metadata"): `source_type`, `source_reference`, `created_at`, `updated_at`.

If no schema exists for the assembly (which should only happen for gsheet-backed assemblies or pre-migration edge cases), the template falls back to a single "Attributes" table iterating `respondent.attributes` — preserving today's behaviour as a safety net.

---

## 8. Files to Create or Modify

### 8.1 New files

| File | Purpose |
| --- | --- |
| `src/opendlp/domain/respondent_field_schema.py` | `RespondentFieldGroup`, `GROUP_DISPLAY_ORDER`, `RespondentFieldDefinition` |
| `src/opendlp/service_layer/respondent_field_schema_service.py` | Population, reconciliation, edit service functions |
| `src/opendlp/service_layer/respondent_field_schema_heuristics.py` | Normalisation + pattern rules (isolated so tests stay tight) |
| `migrations/versions/XXXX_add_respondent_field_definitions.py` | Alembic migration + data backfill |
| `templates/backoffice/respondent_field_schema/view.html` | Schema management page |
| `templates/backoffice/respondent_field_schema/_field_row.html` | Field row partial |
| `templates/backoffice/respondent_field_schema/_group.html` | Group section partial |
| `templates/backoffice/respondents/_upload_diff.html` | CSV re-upload diff confirmation page |

### 8.2 Modified files

| File | Change |
| --- | --- |
| `src/opendlp/adapters/orm.py` | Add `respondent_field_definitions` table |
| `src/opendlp/adapters/database.py` | Register `RespondentFieldDefinition` imperative mapping |
| `src/opendlp/adapters/sql_repository.py` | `SqlAlchemyRespondentFieldDefinitionRepository` |
| `src/opendlp/service_layer/repositories.py` | Abstract interface |
| `src/opendlp/service_layer/unit_of_work.py` | Add repo to UoW |
| `src/opendlp/service_layer/respondent_service.py` | Pass headers into schema service; two-phase upload on reconcile |
| `src/opendlp/entrypoints/blueprints/respondents.py` | Split upload into upload + confirm-diff routes; enforce `MAX_CSV_UPLOAD_MB` |
| `src/opendlp/entrypoints/blueprints/backoffice.py` | Add schema-management routes (or new blueprint if cleaner) |
| `src/opendlp/config.py` | Parse `MAX_CSV_UPLOAD_MB` env var (default 50, min 1, max 500); wire to Flask `MAX_CONTENT_LENGTH` |
| `env.example` | Add `MAX_CSV_UPLOAD_MB=50` example |
| `templates/backoffice/assembly_view_respondent.html` | Rewrite to schema-driven rendering |
| `templates/backoffice/assembly_data.html` | Add "Manage field layout" link |
| `tests/fakes.py` | Add `FakeRespondentFieldDefinitionRepository`; wire into `FakeUnitOfWork` |
| `tests/conftest.py` | Add DELETE to `_delete_all_test_data()` |
| `tests/bdd/conftest.py` | Add DELETE to `delete_all_except_standard_users()` |

---

## 9. Testing Strategy

### 9.1 Unit tests

- `RespondentFieldDefinition` construction / invariants.
- Heuristic rules: a table-driven test that asserts a broad set of real-world header names land in the expected groups. Include mixed-case, underscore, hyphen, space-separated, and non-English variants for the i18n-aware cases we care about.
- Normalisation matches `Assembly.name_fields` semantics (regression guard).
- `ReconciliationDiff` categorisation given various (old_schema, new_headers) pairs.
- `TargetCategory.name` match routing to `ABOUT_YOU` overrides pattern rules.

### 9.2 Contract tests

- `RespondentFieldDefinitionRepository` CRUD, unique-constraint behaviour, `list_by_assembly` ordering.

### 9.3 Integration tests

- Fresh CSV upload populates schema correctly for a realistic respondent CSV.
- Re-upload with identical headers produces an empty diff and skips the confirmation page.
- Re-upload with added columns inserts new schema rows in heuristic groups.
- Re-upload with removed columns keeps schema rows present but marked absent.
- Editing labels and moving fields between groups persists and re-orders.
- Attempting to delete a fixed field fails with a service-layer exception.
- Non-organiser users cannot edit the schema.

### 9.4 BDD / e2e tests

- Organiser uploads CSV, sees grouped detail page for a respondent.
- Organiser reorders a field within a group and sees the new order on the detail page.
- Organiser re-uploads CSV with a new column, confirms the diff, and sees the new field on the detail page.
- Organiser re-uploads CSV with a removed column, confirms the diff, and sees the "no data" flag.

---

## 10. Implementation Order

1. Domain + heuristics + unit tests (no persistence).
2. ORM + migration + contract tests for the repo.
3. Service layer: populate + read functions, integration tests against a fresh CSV.
4. Rewrite `view_registrant` template — this is the visible payoff and validates the schema is enough.
5. Reconciliation service + diff page + integration tests.
6. Schema management UI (edit label, move, reorder, delete, initialise-empty).
7. BDD coverage for the full cycle.

Shipping 1–4 would already deliver the grouped registrant view on the next CSV import; 5–7 round out the editable-schema story. If time pressure hits, 1–4 is a valid intermediate release.

---

## 11. Resolved follow-ups

All design questions raised during planning have been resolved:

- **Rename UX on the diff page:** out of scope for phase 1. The diff page adds new fields and flags absent ones; no inline "rename absent → new" merge UI.
- **`external_id` placement:** confirmed as a hardcoded top-block field. Not editable or movable in phase 1.
- **Registration-form-first seeding:** the `initialise_empty_schema` button (fixed-field rows only) is phase-1 scope. A per-field "add custom field" UI is deferred to a later phase.
- **i18n of labels:** group labels use lazy-gettext; organiser-edited field labels are stored verbatim (consistent with `TargetCategory.name`).
- **Future `registration_page` module linkage:** when the module lands, it should read `RespondentFieldDefinition` as its field catalogue. A forward reference has been added to `docs/agent/module_design.md` so this is not forgotten.
