# Derived Fields — Implementation Plan (domain, data, service layers)

**Status:** Reviewed — all judgement calls confirmed, ready to implement
**Date:** 2026-09-08
**Issue:** 793
**Companion:** [research.md](research.md) holds the reasoning and decisions; this file holds the concrete build order for the current chunk.

**Scope of this chunk:** domain models, data model + migration, and the service layer. Flask blueprints, templates, JS, starter-HTML rendering and BDD tests are **out of scope** — they come in a later chunk. The one apparent exception is the respondent-field-spec JSON Schema and its recorded fixture, which must move in step with the data model or the component tests fail (§0.1).

---

## 0. What changed in the code since the research

Verified against the working tree on 2026-09-08 (branch `793-derived-fields`, on top of main merge `83a10622`).

### 0.1 The field-spec endpoint now serialises the derivation columns

`service_layer/respondent_field_spec_service.py` (landed 2026-08-25, after the research) serialises `is_derived`, `derived_from` and `derivation_kind` at lines 65-67, and its JSON Schema (`src/opendlp/schemas/json_api/respondent-field-spec.schema.json`) lists all three as `required` with `additionalProperties: false`, plus **closed enums** for `field_type` (lines ~152-165) and `group` (~115-125). Consequences for this chunk:

- Renaming `derivation_kind` → `derivation_type` and adding `derivation_config` changes that response shape. Per the JSON API conventions this means updating the service, the schema, and re-recording `tests/fixtures/json_api/respondent-field-spec.json` with `UPDATE_API_FIXTURES=1 uv run pytest` — one deliberate re-record, diff read.
- Adding `FieldType.DATE` and `RespondentFieldGroup.DERIVED` extends both closed enums in the schema.
- The endpoint is hidden/undocumented-for-humans, so a breaking shape change is acceptable now in a way it will not be later — a reason to do the rename in this chunk, not defer it.

### 0.2 Other drift and corrections

- **Line numbers** in research §1 have been corrected in place (2026-09-08 re-check).
- **`src/js/components/service-docs/fields.js` does not enumerate field types** (research assumed it did) — no JS change needed for `FieldType.DATE`. `templates/backoffice/service_docs/_fields.html` does enumerate types (3 places) and groups (2 places), but that is template work → later chunk.
- **Validators live in `domain/validators.py`**, not the service layer. `validate_integer` returns `tuple[int | None, str | None]` (typed value, not string); `validate_email_field` returns `tuple[str | None, str | None]`. `validate_date_field` should follow the local convention: `tuple[str | None, str | None]` returning the cleaned ISO string, since attributes store strings.
- **`_ensure_manage_permission` is module-private** to `respondent_field_schema_service.py` — it is not a shared pattern. Other services inline `can_manage_assembly` checks. See §4 for what the new service does.
- **A contract test for the field-definitions repository already exists** (`tests/contract/test_respondent_field_definition_repo.py`, fixture in `tests/contract/conftest.py:469-477`). New derivation columns get cases added there; the new mapping-entries repository gets its own file modelled on it, plus a `Fake*` in `tests/fakes.py` and a backend fixture in `tests/contract/conftest.py`.
- **`RespondentFieldDefinition.update()` does not re-apply the `is_derived ⇒ on_registration_page = NO` invariant** — it will happily set `on_registration_page` on a derived field. Fix in step 1.
- **`add_field` has no derivation parameters** — there is currently no service-layer path that can create a derived field. `create_derived_field` (step 4) is that path; `add_field` stays derivation-free.
- **`create_respondent` does not commit** (its entrypoint does); `_create_and_save_respondent` commits itself. Derivation must run before `uow.respondents.add(...)` in both, so this asymmetry does not matter, but tests should not assume a commit inside `create_respondent`.
- **Migration head is `aedb402e99ad`** (`record_who_created_an_assembly`); the new migration chains from it. Note the head moved on 2026-09-04 (`a225ee09` rebased branch migrations), so run `uv run alembic heads` before generating.
- **`list_by_assembly` sorts in Python** by `GROUP_DISPLAY_ORDER` then `sort_order` then `field_key` (`adapters/sql_repository.py:1504-1518`) — the new `DERIVED` group sorts last for free once appended to `GROUP_DISPLAY_ORDER`.
- **`create_detached_copy()` routes through `__init__`**, so it must pass the new `derivation_type` / `derivation_config` through, and note that a derived field is re-normalised to `on_registration_page = NO` by the constructor.
- **`normalise_field_name` (`domain/respondents.py:56`) lowercases and strips non-alphanumerics** — right for CSV header matching, wrong for postcode keys. Large-mapping lookup keys get their own normaliser (§2, step 2).

---

## 1. Step 1 — Data model and migration ✅ DONE

All domain + adapters + tests; no behaviour yet.

### 1.1 `RespondentFieldDefinition` changes (`domain/respondent_field_schema.py`)

- New `DerivationType(Enum)`: `AGE_BRACKET`, `SMALL_MAPPING`, `LARGE_MAPPING` (values `"age_bracket"` etc.). `INTERSECTION` deliberately absent.
- Replace `derivation_kind: str` with:
  - `derivation_type: DerivationType | None` — `None` when not derived. (Deviation from the research's `default ""` sketch: `EnumAsString` round-trips enum members, and an empty string is not a member; a nullable column with `None` matches how `derived_from` already models "not derived". The house prefer-empty-string rule is about *string* arguments; this is an enum.)
  - `derivation_config: dict[str, Any] | None` — parameters only, never source keys, never output values.
- `__init__` validation additions: `is_derived` ⇒ `derivation_type` and `derivation_config` both present; not-`is_derived` ⇒ both absent (mirrors the existing `derived_from` check at lines 199-200).
- New `DerivedFieldError(ValueError)` sibling of `FixedFieldError`. `update()` raises it when `field_type`/`options` are passed for a derived field (options are owned by the derivation, research §2.7), and re-applies the `on_registration_page = NO` invariant so the constructor-only gap closes.
- `create_detached_copy()` carries the two new attributes (copy `derivation_config` as a new dict).
- New `RespondentFieldGroup.DERIVED`; `GROUP_DISPLAY_ORDER` gets it **after `OTHER`** (last); `GROUP_LABELS[DERIVED] = _l("Derived")`.
- A unit test that `classify_field_key` (`service_layer/respondent_field_schema_heuristics.py:117`) never returns `DERIVED` for any header.

### 1.2 New mapping-entries table and domain object

- Domain: `RespondentFieldMappingEntry` in `domain/respondent_field_schema.py` (or the new derivation module, see step 2) — plain class with `id: UUID`, `field_id: UUID`, `lookup_key: str`, `output_value: str`. Not frozen-dataclass-in-JSON like `ChoiceOption`: these are table rows, so they follow the ordinary imperatively-mapped-entity pattern.
- ORM (`adapters/orm.py`): table `respondent_field_mapping_entries` per research §2.4 — UUID PK, `field_id` FK → `respondent_field_definitions.id` ON DELETE CASCADE, `lookup_key` String(255) NOT NULL, `output_value` String(255) NOT NULL, unique index on `(field_id, lookup_key)`. `map_imperatively` alongside the others.
- `respondent_field_definitions` ORM: drop `derivation_kind`, add `derivation_type` (`EnumAsString(DerivationType, 32)`, nullable) and `derivation_config` (JSON, nullable).

### 1.3 Repository, UoW, cleanup, fixtures

- `service_layer/repositories.py`: abstract `RespondentFieldMappingEntryRepository` — `add`, `bulk_add`, `get_many(field_id, lookup_keys) -> list[RespondentFieldMappingEntry]` (the batch lookup, research §4.2), `count_for_field`, `list_for_field` (paged or capped — needed later by the UI, cheap now), `delete_all_for_field`.
- `adapters/sql_repository.py`: `SqlAlchemyRespondentFieldMappingEntryRepository`; `get_many` uses `WHERE field_id = :f AND lookup_key = ANY(:keys)`.
- `tests/fakes.py`: `FakeRespondentFieldMappingEntryRepository`.
- `service_layer/unit_of_work.py`: all five touch-points — SQL-class import, `TYPE_CHECKING` import, the class-level annotation on `AbstractUnitOfWork` (load-bearing: `_close_repositories` iterates `__annotations__`), and instantiation in `SqlAlchemyUnitOfWork.__enter__`. Property name: `uow.respondent_field_mapping_entries`.
- `tests/conftest.py::_delete_all_test_data`: DELETE `respondent_field_mapping_entries` **before** `respondent_field_definitions` (insert above line ~400). Same in `tests/bdd/conftest.py::delete_all_except_standard_users` (~line 573).
- Contract tests: new `tests/contract/test_respondent_field_mapping_entry_repo.py` + backend fixture in `tests/contract/conftest.py`, modelled on the field-definition one. Extend `test_respondent_field_definition_repo.py` for round-tripping `derivation_type`/`derivation_config`.

### 1.4 Migration and field-spec update

- One Alembic revision from `aedb402e99ad`: drop `derivation_kind`, add the two columns, create the new table. Plain drop-and-add — nothing has ever written `derivation_kind` outside tests (research §10). `uv run alembic revision --autogenerate`, then hand-check (autogenerate may fumble the `EnumAsString` type).
- Field-spec: update `respondent_field_spec_service.py` serialisation (`derivation_type` as its value-string-or-null, `derivation_config` as-is), the JSON Schema (rename + `derivation_config`; extend `group` enum with `derived`; `field_type` enum gains `date` in step 3 — fold into the same edit if steps land together), re-record the fixture, read the diff.

---

## 2. Step 2 — Rule classes: `domain/respondent_derivation.py` ✅ DONE

New module, pure domain, exhaustively unit-tested, no DB/Flask anywhere.

- `AgeBracketRule` (frozen dataclass): `as_of_date: date` (required), `min_age: int = 16`, `max_age: int = 100`, `boundaries: tuple[int, ...] = ()`, `fallback: str = "UNKNOWN"`. `__post_init__` validates `min_age > 0`, `min_age < max_age`, boundaries sorted/unique/strictly between. Methods: `bracket_labels()`, `eligibility_sentence()` (i18n via `_l`/`_` with `min_age` and `as_of_date` parameters), `derive_from_date(born: date)`, `derive_from_year(year: int)` (1 January assumption; out-of-sane-range years → fallback).
- `SmallMappingRule` (frozen dataclass): `mapping: Mapping[str, str]`, `fallback: str = "UNKNOWN"`, `derive(value) -> str`.
- `LargeMappingRule` (frozen dataclass): `fallback: str = "UNKNOWN"`, `derive(value, lookup: Callable[[str], str | None]) -> str` — normalises the input then calls the injected lookup.
- Serialisation: each rule gets `to_config()` / `from_config(dict)` (mirrors the `ChoiceOption.to_dict/from_dict` house pattern), and a module-level `rule_from_field(derivation_type, derivation_config)` factory used by the service dispatch. Unknown/missing config keys raise `ValueError` with `_l()` messages.
- `normalise_lookup_key(value: str) -> str`: uppercase, strip **all** whitespace. Applied on mapping upload and on lookup — the single highest-risk detail per research §5.3, so it gets its own test battery (mixed case, internal/edge whitespace, non-breaking spaces, tabs).
- `output_options(rule) -> list[ChoiceOption]` helper — bracket labels + fallback for age; declared outputs + fallback for mappings (mapping output declaration lives in the service call, see step 4) — so "fallback is always in `options`" (research §4.5) is enforced in one place.

---

## 3. Step 3 — `FieldType.DATE`, domain + service slice only ✅ DONE

Independently useful; deferrable behind steps 2/4 if we want year-of-birth brackets shipping first (research §13).

- `FieldType.DATE` + `FIELD_TYPE_LABELS[DATE] = _l("Date")`.
- `domain/validators.py::validate_date_field(str_value) -> tuple[str | None, str | None]`: accepts ISO `YYYY-MM-DD` and `dd/mm/yyyy`, returns canonical ISO string; rejects impossible dates, future dates, age > 120.
- Registration path: a `DATE` branch in `registration_submission_service._validate_field_value`, plus the three-part `-day`/`-month`/`-year` assembly in `_validate_form_data` with fallback to a single bare-key value (research §3.3 item 3); errors attach to the bare key.
- Import path: lenient parse via the same validator; a failed parse leaves the raw string in `attributes` and lets the derivation fall back (precedence rules, step 5) — the import does not fail on a bad date.
- Field-spec schema: add `date` to the `field_type` enum (same re-record as §1.4).
- **Deferred to the UI chunk:** starter-HTML `DATE` rendering in both generators, the edit-form date control, the view macro branch, `_fields.html` enumerations, `guess_field_types` left alone by decision (research §3.3 item 5).

---

## 4. Step 4 — `service_layer/derivation_service.py`

The surface from research §8, adjusted to what the code actually offers:

```python
create_derived_field(uow, user_id, assembly_id, field_key, label, source_field_key, rule,
                     output_values=None)                          -> tuple[RespondentFieldDefinition, RecomputeReport]
update_derivation(uow, user_id, assembly_id, field_id, rule, output_values=None)
                                                                  -> tuple[RespondentFieldDefinition, RecomputeReport]
upload_large_mapping(uow, user_id, assembly_id, field_id, csv_content) -> MappingUploadReport
recompute_derived_field(uow, user_id, assembly_id, field_id)      -> RecomputeReport
derivations_depending_on(uow, assembly_id, field_key)             -> list[RespondentFieldDefinition]
load_mapping_lookups(uow, field_defs)                             -> dict[uuid.UUID, Callable[[str], str | None]]
derived_value_for(field_def, rule, source_def, source_value, lookup=None) -> str   # pure dispatch
apply_derivations(respondent, field_defs, lookups)                -> DerivationOutcome  # in-memory, mutates attributes
```

Details:

- **Permissions:** inline `can_manage_assembly` checks like `respondent_service` does (do **not** import the schema service's private helper; promoting it to a shared module is a separate cleanup, not this task).
- **`create_derived_field`** builds the `RespondentFieldDefinition` with `group=DERIVED` (caller-overridable), `field_type=CHOICE_RADIO`, `options=output_options(rule)`, `is_derived=True`, `derived_from=[source_field_key]`, the matching `derivation_type` and `rule.to_config()`. Config-time validation: source field exists, source is not itself derived (research §4.4), source `field_type` is compatible with the rule (`DATE`/`INTEGER` for age; `CHOICE_*` for small mapping; `TEXT` for large mapping), `field_key` unique. `output_values` is required for mapping rules (they declare their outputs), forbidden for age (labels are generated).
- **`update_derivation`** regenerates `options` from the new rule, updates `derivation_config`, keeps `derived_from`.
- **Both trigger a synchronous recompute** and return its report (research §6). Recompute: iterate the pool via the respondents repository (existing listing method; batched if one exists), skip `RespondentStatus.DELETED`, no comments written, count `total` / `changed` / `fell_back`, sample of unmatched inputs. `RecomputeReport` and `MappingUploadReport` are frozen dataclasses in the service module.
- **Selection-run warning** (research §6): the report carries `completed_selection_runs: int` so the (future) UI can warn; the service does not block.
- **`upload_large_mapping`**: parse CSV in memory, match headers via `normalise_field_name` against source/derived field keys with positional fallback + warning, normalise keys via `normalise_lookup_key`, detect duplicate keys, validate outputs against `options` (report unknown outputs with counts — the "add vs reject" choice is a UI concern later; the service takes an `allow_new_outputs: bool`), row cap 500,000, replace-all as delete-then-`bulk_add`. The uploaded file is never persisted (GDPR rule).
- **`apply_derivations`** implements precedence (c) from research §4.3: source usable → derive; else supplied value present → keep; else fallback. Returns a small `DerivationOutcome` (which fields were overwritten vs kept) so the import path can add its notes to `errors`.
- **`derived_value_for`** is the pure `match derivation_type` dispatch; for age it reads the *source* field's `field_type` to pick `derive_from_date` vs `derive_from_year`.

## 5. Step 5 — Wire the four write paths

| Path | Change |
| --- | --- |
| `registration_submission_service._create_and_save_respondent` | accept the already-loaded `field_definitions` from both callers (`submit_registration:233`, `submit_registration_by_assembly_id:295`); build lookups; `apply_derivations` on the attributes before constructing the `Respondent` |
| `respondent_service.create_respondent` | load schema, build lookups, apply before `uow.respondents.add` |
| `respondent_service.import_respondents_from_rows` | load schema + `load_mapping_lookups` **once before the row loop**; for large mappings prefetch the batch's distinct source values via `get_many` and close over an in-memory dict; pass into `respondent_from_row` as optional args (stays pure, no `uow`); append overwrite notes to `errors` |
| `respondent_service.update_respondent` | after `apply_edit`, before commit |

## 6. Step 6 — Source-field protection (`respondent_field_schema_service.py`)

Per research §7, each mutator calls `derivations_depending_on` first:

- `delete_field` on a source → raise `FieldDefinitionConflictError` ("X is used to derive Y").
- `update_field` changing a source's `field_type` → same.
- `update_choice_option` on a small-mapping source → rename the mapping key in the dependent field's `derivation_config` in step.
- `remove_choice_option` on a small-mapping source → drop the mapping entry (value now falls back); the report/return notes it.
- `update_field` on a derived field's own `field_type`/`options` → blocked via `DerivedFieldError` (domain, step 1.1), translated to `FieldDefinitionConflictError` like `FixedFieldError` is at line 325.

## 7. Step 7 — Tests

Unit, contract and integration land with their steps (listed above); the full matrix is research §11. Explicitly **in** this chunk: all unit tests for rules/normalisation/dispatch/date-validation, contract tests for the new repository, integration tests for the four write paths, recompute idempotence, import precedence, source-field protection, and the batch-lookup-not-N-queries check. Explicitly **out** (UI chunk): BDD scenarios — they need the config pages that don't exist yet.

Housekeeping per house rules: `just check` + targeted test runs before each commit; regenerate translations after new `_l()` strings; regenerate `../.secrets.baseline` if test edits shift flagged line numbers.

## 8. Suggested commit sequence

1. Step 1 (data model, migration, repos, fixtures, field-spec re-record)
2. Step 2 (rule classes)
3. Step 3 (DATE slice) — could swap with 4/5 if year-of-birth-first is preferred
4. Step 4 (derivation service) + Step 6 (protection) — 6 depends on 4's `derivations_depending_on`
5. Step 5 (write-path wiring)

---

## 9. Judgement calls — all confirmed in review (2026-09-08)

1. **`derivation_type` is a nullable enum column (`None` when not derived)**, not `default ""` as the research sketched — `EnumAsString` can't round-trip `""`. Confirmed.
2. **The field-spec breaking change ships in this chunk** (§0.1) — the endpoint is young and hidden, so now is the cheap time. Confirmed.
3. **Derived fields default to `CHOICE_RADIO`** — changed from the draft's `CHOICE_DROPDOWN` in review. Radios are the house preference between the two choice types, and later editors tend to copy whatever the default is, so the default should be the preferred one.
4. **`create_derived_field`/`update_derivation` return the recompute report** rather than a separate preview/apply dance — matches the parked-dry-run decision. Confirmed.
5. **Permission checks are inlined** rather than reusing the schema service's private `_ensure_manage_permission`. Confirmed.
6. **Row cap 500,000** (up from the research's 250k) given the real 220k Scotland table. Confirmed.
7. **DATE registration-form parsing is service-layer and included**; all DATE *rendering* is deferred to the UI chunk. Confirmed.
