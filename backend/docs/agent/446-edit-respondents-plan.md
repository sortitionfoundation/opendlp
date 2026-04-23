# Edit respondents — implementation plan

Adds a web-UI edit path for individual respondents, a typed field schema so the edit form can render appropriate widgets, and the permission model to let confirmation callers (but not read-only users) edit. Also covers selection-status transitions as a paired but independently-deferrable feature.

## Scope

In scope:
- A dedicated edit page per respondent, grouped using the existing `RespondentFieldGroup` schema.
- A `field_type` + `options` addition to `respondent_field_definitions` so the edit form can pick the right widget per field.
- A schema-page UI for organisers to set field types and options.
- A one-click "guess field types from data" action on the schema page.
- A new `edit_respondent` permission function and a new `READ_ONLY` assembly role.
- Selection-status transitions (SELECTED → CONFIRMED, etc.) driven from the view respondent page with a required comment.

Out of scope (for now):
- Editing `is_derived` fields — hidden from the edit form until the derivation feature lands.
- Any registration-facing form work (public form).
- Bulk edit.

## Design decisions (already agreed)

- **Type system**: add `field_type` (enum-as-string: `text`, `longtext`, `bool`, `bool_or_none`, `choice_radio`, `choice_dropdown`, `integer`, `email`) and `options` (nullable JSON, stored as a list of `{value, help_text}` dicts) to `respondent_field_definitions`. Two bool types — strict true/false (`bool`) and nullable true/false/"not set" (`bool_or_none`). Two choice types — radios or dropdown — so organisers can pick presentation explicitly.
- **Fixed fields hardcoded**: `email` → `email`; `eligible`/`can_attend`/`consent`/`stay_on_db` → `bool_or_none` (they are `bool | None` in the domain). Type is locked for fixed fields — the service layer refuses attempts to change it and the schema UI doesn't expose a picker for them.
- **No auto-guess on CSV import.** Types default to `text` when a field is first added to the schema (except the hardcoded fixed fields).
- **Type-guess button** lives on the schema page. One-click write-through. Overwrites **only** fields whose `field_type` is still the default `text` (never overwrites an explicitly-set type). Uses `MAX_DISTINCT_VALUES_FOR_AUTO_ADD` (currently `20` in `service_layer/target_respondent_helpers.py`).
- **Heuristic order** (first match wins):
  1. If field_key matches a `TargetCategory` name (normalised) → choice with those category values as options (empty help_text). Type is `CHOICE_RADIO` if the target category has ≤6 values, else `CHOICE_DROPDOWN`.
  2. All non-empty values parse as bool via `config.to_bool` → `BOOL_OR_NONE` (conservative — preserves the possibility of a blank row; organisers can narrow to `BOOL` by hand).
  3. All non-empty values parse as int → `INTEGER`.
  4. Distinct non-empty value count is `> 0` and `< MAX_DISTINCT_VALUES_FOR_AUTO_ADD` → choice with distinct values as options (sorted alphabetically, empty help_text). Type is `CHOICE_RADIO` if ≤6 distinct values, else `CHOICE_DROPDOWN`.
  5. Otherwise → `TEXT`.
  - `EMAIL` is never guessed — only applied via the hardcoded fixed-field override.
  - `LONGTEXT` is never guessed — organisers opt in manually.
  - `BOOL` (strict) is never guessed — `BOOL_OR_NONE` is always safer as a default.
- **Editable fields on the edit page**:
  - Fixed: `email`, `eligible`, `can_attend`, `consent`, `stay_on_db`.
  - All entries in `respondent.attributes` whose key appears in the field schema and whose field is not derived.
  - **Not editable**: `external_id`, `selection_status` (owned by selection-status sub-feature), `selection_run_id`, `source_type`, `source_reference`, timestamps, `comments`.
  - **Not shown**: derived fields (`is_derived=True`).
  - **Refused entirely if respondent.selection_status is DELETED** (GDPR blanked row — no edit surface).
- **Comment on edit**: required free text, stored as a `RespondentComment` with `action=RespondentAction.EDIT`. No auto-generated diff content appended (PII safety — keeps diff-text out of long-lived storage).
- **Permissions**: a new `can_edit_respondent(user, assembly)` returning True for `ADMIN`, `GLOBAL_ORGANISER`, `ASSEMBLY_MANAGER`, `CONFIRMATION_CALLER`; False for `READ_ONLY` and for users with no assembly role.
- **READ_ONLY role**: new `AssemblyRole.READ_ONLY` that carries `can_view_assembly` = True and nothing else. No live users currently hold `CONFIRMATION_CALLER`, so letting that role silently gain edit rights is acceptable.
- **Boolean UI**: `bool` renders as inline Yes / No radios (required — form validation rejects a missing submission for non-fixed fields; fixed fields use `bool_or_none` so this case only arises for organiser-defined strict-bool attributes). `bool_or_none` renders as inline Yes / No / Not set radios; submitting blank/"Not set" → `None`; existing `None` renders as Not set selected.
- **Choice options carry help text**: each option is `{value, help_text}`. Help text is optional and empty by default; used by CHOICE_RADIO to render a description next to each option, and by CHOICE_DROPDOWN to render a single block below the dropdown listing every option's help text. Needed for cases like an "Education level" field whose values 0–4 each have a definition. Guess-button-generated options start with empty help text; organisers fill it in via the schema page.
- **Selection-status transitions**: per-transition buttons on the view respondent page, each opening a modal overlay with a required comment and a confirm button. Allowed transitions: POOL → SELECTED, SELECTED → CONFIRMED, SELECTED → WITHDRAWN, CONFIRMED → WITHDRAWN. No transitions out of DELETED. POOL-via-batch-reset is unchanged. Manual SELECTED has no associated `selection_run_id` (see Phase 5 note).
- **Tests are part of each phase**, not a trailing phase. Unit + integration tests written as each piece lands.

## Phasing overview

| Phase | Delivers | Depends on | Deferrable? |
|---|---|---|---|
| 1 | Typed field schema (migration + domain + schema-page type editor) | — | No, prerequisite for 2 and 3 |
| 2 | Guess-types button on schema page | Phase 1 | Yes (schema page works without it; organisers set types by hand) |
| 3 | Edit respondent page + `can_edit_respondent` permission | Phase 1 | Yes (but this is the headline feature) |
| 4 | `READ_ONLY` assembly role | — (but naturally paired with Phase 3) | Yes (can ship Phase 3 first with confirmation-caller gaining edit) |
| 5 | Selection-status transition UI | — | Yes (entirely independent) |
| 6 | Relocate `MAX_DISTINCT_VALUES_FOR_AUTO_ADD` | Phase 2 | Yes (cosmetic cleanup) |

**Commit cadence**: at least one commit per phase. Split a phase across multiple commits where it makes sense (e.g. domain + ORM + migration as one commit, service layer as another, blueprint/template as a third, each with their own tests). Keep commits focused and reviewable on their own.

---

## Phase 1 — Typed field schema

Add the data model, domain type, ORM mapping, migration, and the schema-page UI for editing type and options. No respondent edit page yet — just making the schema carry type information.

### 1.1 New `FieldType` enum

File: `src/opendlp/domain/respondent_field_schema.py`

Add next to the existing classes:

```python
class FieldType(Enum):
    TEXT = "text"
    LONGTEXT = "longtext"
    BOOL = "bool"                       # strict true/false, must be answered
    BOOL_OR_NONE = "bool_or_none"       # true/false/None (three-state radio)
    CHOICE_RADIO = "choice_radio"       # one of list of options, rendered as radios
    CHOICE_DROPDOWN = "choice_dropdown" # one of list of options, rendered as <select>
    INTEGER = "integer"
    EMAIL = "email"


FIELD_TYPE_LABELS: dict[FieldType, str] = {
    FieldType.TEXT: _l("Text"),
    FieldType.LONGTEXT: _l("Long text"),
    FieldType.BOOL: _l("Yes / No"),
    FieldType.BOOL_OR_NONE: _l("Yes / No / Not set"),
    FieldType.CHOICE_RADIO: _l("Choice (radios)"),
    FieldType.CHOICE_DROPDOWN: _l("Choice (dropdown)"),
    FieldType.INTEGER: _l("Whole number"),
    FieldType.EMAIL: _l("Email"),
}


# Groupings used across the code — import these rather than hard-coding membership.
CHOICE_TYPES: frozenset[FieldType] = frozenset({FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN})
BOOL_TYPES: frozenset[FieldType] = frozenset({FieldType.BOOL, FieldType.BOOL_OR_NONE})


# Hardcoded override: fixed fields always have the type here regardless of DB row.
# The four eligibility/consent flags are typed `bool | None` in the domain, so they
# are BOOL_OR_NONE. Email stays EMAIL.
FIXED_FIELD_TYPES: dict[str, FieldType] = {
    "email": FieldType.EMAIL,
    "eligible": FieldType.BOOL_OR_NONE,
    "can_attend": FieldType.BOOL_OR_NONE,
    "consent": FieldType.BOOL_OR_NONE,
    "stay_on_db": FieldType.BOOL_OR_NONE,
}
```

**On having two bool types.** `BOOL_OR_NONE` exists because the four fixed eligibility/consent flags can legitimately be unset (e.g. a CSV row arrived with a blank). `BOOL` exists for organiser-defined attributes where "not set" doesn't make sense and the form should force an answer. The guess button always picks `BOOL_OR_NONE` when it detects a bool column (conservative — preserves blanks); the organiser can narrow it to `BOOL` manually.

**On having two choice types.** Making presentation an explicit schema choice avoids the magic of "≤N options → radio" heuristics that silently flip when someone adds a 7th option. The guess button uses `CHOICE_RADIO` for ≤6 options and `CHOICE_DROPDOWN` above that, as a sensible default — organisers can switch either direction.

### 1.2 New `ChoiceOption` dataclass

Same file.

A choice option is a `{value, help_text}` pair. Help text is optional, used on the edit form (next to each radio, or as a block under the dropdown) and will also be used by the future registration form.

```python
@dataclass(frozen=True)
class ChoiceOption:
    """One option on a CHOICE_RADIO or CHOICE_DROPDOWN field."""

    value: str
    help_text: str = ""

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("ChoiceOption.value cannot be blank")

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "help_text": self.help_text}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChoiceOption":
        return cls(value=data["value"], help_text=data.get("help_text", ""))
```

### 1.3 Extend `RespondentFieldDefinition`

Same file.

- Add `field_type: FieldType = FieldType.TEXT` and `options: list[ChoiceOption] | None = None` constructor args and attributes.
- On construction: if `field_type in CHOICE_TYPES`, require `options` to be a non-empty list (each `ChoiceOption` validates its own `value`); otherwise `options` must be `None` (reject to keep data tidy).
- Extend `update()` to accept `field_type` and `options` — validating the same invariant and refusing changes when `self.is_fixed` is True (raise `ValueError`).
- Add `effective_field_type` property returning `FIXED_FIELD_TYPES.get(self.field_key, self.field_type)` — everything that picks the widget uses this, so the fixed-field override is applied in one place.
- `create_detached_copy` carries the new fields through (copy the options list).

### 1.4 ORM + migration

File: `src/opendlp/adapters/orm.py` — add two columns to `respondent_field_definitions`:

```python
Column("field_type", EnumAsString(FieldType, 32), nullable=False, default=FieldType.TEXT),
Column("options", JSON, nullable=True),
```

The `options` column stores a list of dicts (`[{"value": ..., "help_text": ...}, ...]`); the imperative mapper is responsible for converting between `list[ChoiceOption]` on the domain object and the JSON shape. Keep the dataclass out of ORM concerns — serialize on the way in, deserialize on load.

Alembic migration (`uv run alembic revision --autogenerate -m "Add field_type and options to respondent_field_definitions"`):

- Add the two columns.
- Backfill: for every existing row, set `field_type = 'text'` and `options = NULL`, then override the five fixed-field keys to their hardcoded types (`email` → `'email'`; `eligible`/`can_attend`/`consent`/`stay_on_db` → `'bool_or_none'`). Simple `UPDATE` keyed on `field_key`.
- Downgrade drops both columns.

### 1.5 Service layer

File: `src/opendlp/service_layer/respondent_field_schema_service.py`

- Extend `update_field()` signature with `field_type: FieldType | None = None` and `options: list[ChoiceOption] | None = None`. Use a sentinel (module-level `_UNSET = object()`) to distinguish "don't change options" from "set to None" — Python's default `None` can't carry that distinction for options.
- Refuse to change `field_type` or `options` on a fixed-field row; raise `FieldDefinitionConflictError` with a translated message.
- Validate `options` for choice fields (non-empty list, values trimmed and deduped by `value`, blank values rejected; help_text preserved as-is including any leading/trailing whitespace the organiser wants).
- `populate_schema_from_headers` / `update_schema_from_headers` / `apply_reconciliation`: when creating new rows, default `field_type=TEXT` and `options=None`, except for rows whose `field_key` is in `IN_SCHEMA_FIXED_FIELDS` — those get their hardcoded type.

### 1.6 Schema page UI

File: `src/opendlp/entrypoints/blueprints/respondent_field_schema.py` and `src/opendlp/entrypoints/templates/backoffice/respondent_field_schema/view.html`

- In `update_field_view`, accept `field_type` and `options` form fields. Parse options from a repeating group of rows (one `{value, help_text}` pair per row) — not a single textarea, so help text can contain any characters without escaping rules. Call the extended service with `list[ChoiceOption]`.
- In the template: add a "Type" column to the schema table showing the effective type. For non-fixed rows, the edit form gains a `<select>` of `FieldType` and a dynamic options editor (repeating rows of `value` input + `help_text` input, plus Add/Remove buttons). Shown only when `field_type in CHOICE_TYPES` — Alpine `x-show` on a flat property, per `templates/backoffice/patterns.html` constraints.
- Fixed rows render the type as read-only text.
- The options editor needs basic Alpine behaviour (add row / remove row). Keep handlers argument-free per the CSP rules in `patterns.html` — use array indices tracked by Alpine state, not inline string arguments.

### 1.7 Tests

- **Domain unit tests** (`tests/unit/domain/test_respondent_field_schema.py`):
  - `FieldType` round-trips via `update()`.
  - Each choice type requires a non-empty options list.
  - Non-choice types reject non-None options.
  - `ChoiceOption` rejects blank values; help_text defaults to empty; `to_dict`/`from_dict` round-trip.
  - `is_fixed=True` blocks type and options change.
  - `effective_field_type` overrides for known fixed keys (including `bool_or_none` for the four flag fields).
  - `BOOL_TYPES` / `CHOICE_TYPES` groupings match expectation.
- **Service tests**: `update_field` happy paths per field_type (including transitions bool ↔ bool_or_none and choice_radio ↔ choice_dropdown); conflict error on fixed rows; `_UNSET` sentinel behaviour (options preserved when not passed, cleared when explicitly `None`); `populate_schema_from_headers` defaults for fixed vs. non-fixed.
- **ORM round-trip test**: save + reload a definition with choice options (including a row with non-empty help_text) and confirm both value and help_text survive the JSON shape.
- **Migration test**: an existing schema row migrates to `text` for generic rows and to the hardcoded type (`bool_or_none` / `email`) for fixed rows — if we have a migration test harness, otherwise verified by fixture plus a spot check.
- **Blueprint test**: schema page submission round-trips type and option list with help text; options editor renders correctly for each choice type.

---

## Phase 2 — Guess field types from data

One-click button on the schema page that sets `field_type` (and `options`) on every field still at the default `text`. Never overwrites an explicitly-set type.

### 2.1 Service: `guess_field_types`

New function in `src/opendlp/service_layer/respondent_field_schema_service.py`:

```python
def guess_field_types(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> dict[str, FieldType]:
    """Overwrite field_type for every non-fixed, non-derived, text-typed field
    based on the current respondent attribute distribution. Returns a mapping
    of field_key -> new FieldType for rows that were changed."""
```

- Permission: `can_manage_assembly` (same as other schema edits).
- Pulls the target category names for the assembly (`uow.target_categories.get_by_assembly_id`) so the first heuristic step can match.
- For each schema row where `is_fixed=False`, `is_derived=False`, `field_type=TEXT`:
  1. If `field_key` (via a case-insensitive / normalised match) equals a target category name → choice with options from that category's `TargetValue` list (help_text empty). Pick `CHOICE_RADIO` if ≤6 options, else `CHOICE_DROPDOWN`.
  2. Else pull `uow.respondents.get_attribute_value_counts(assembly_id, field_key)`. If no data for this key, skip (leave as text).
  3. Walk the heuristic ladder: bool → `BOOL_OR_NONE` (all values parse via `config.to_bool`); integer → `INTEGER`; choice → `CHOICE_RADIO`/`CHOICE_DROPDOWN` (distinct count `0 < n < MAX_DISTINCT_VALUES_FOR_AUTO_ADD`, picked by ≤6 rule); otherwise no change.
  - When choice wins, options are built from sorted distinct values stripped of whitespace, each wrapped as `ChoiceOption(value=..., help_text="")`.
- Commits in one transaction.
- Small internal helpers: `_is_all_bool(values)`, `_is_all_int(values)` — both filter out blank/None before testing; an all-blank attribute leaves type as text. A helper `_choice_type_for(n_options: int) -> FieldType` keeps the ≤6 rule in one place for reuse by the guess button and any future auto-pickers.

### 2.2 Blueprint + template

Same files as Phase 1's schema UI.

- `POST /assembly/<assembly_id>/respondent-schema/guess-types`: calls the service, flashes a summary (e.g. `_("Guessed types for %(count)d fields.", count=len(changed))`), redirects back to the schema page.
- Button rendered on the schema page when:
  - Respondent data exists for the assembly (`uow.respondents.count_non_pool` or a cheaper "any row" check — add a repo method if needed), **and**
  - At least one schema row is non-fixed, non-derived, and at `field_type=TEXT`.
- Button copy: `_("Guess field types from data")` with a short helper line clarifying that only untouched fields are overwritten.

### 2.3 Tests

- **Service unit tests** (new file `tests/unit/service_layer/test_guess_field_types.py`) exercising each heuristic branch with small fixtures:
  - all `"true"`/`"false"` → `BOOL_OR_NONE` (never `BOOL`)
  - all integer strings → `INTEGER`
  - 3 distinct strings → `CHOICE_RADIO` with those 3 options (help_text empty)
  - 10 distinct strings → `CHOICE_DROPDOWN` with those 10 options
  - 50 distinct strings → left as `TEXT`
  - mixed blanks + bools → `BOOL_OR_NONE`
  - matches target category name (5 values) → `CHOICE_RADIO` from target values (even if attribute data has other distinct values)
  - matches target category name (8 values) → `CHOICE_DROPDOWN`
  - fixed / derived / already-typed rows untouched
- **Integration test**: upload a CSV, call guess-types, assert schema rows updated and fixed rows untouched.
- **Blueprint test**: button is present when conditions met, absent otherwise; POST round-trips flash message.

---

## Phase 3 — Edit respondent page

The headline feature. Dedicated page, grouped stacked form, required comment.

### 3.1 New permission

File: `src/opendlp/service_layer/permissions.py`

```python
def can_edit_respondent(user: User, assembly: Assembly) -> bool:
    """Who can edit respondent attributes via the backoffice edit page."""
    if user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
        return True
    for role in user.assembly_roles:
        if role.assembly_id == assembly.id and role.role in (
            AssemblyRole.ASSEMBLY_MANAGER,
            AssemblyRole.CONFIRMATION_CALLER,
            # READ_ONLY (Phase 4) excluded by omission.
        ):
            return True
    return False
```

### 3.2 Domain method

File: `src/opendlp/domain/respondents.py`

Add a single domain method that does the state change and appends the required comment as one atomic step:

```python
def apply_edit(
    self,
    *,
    author_id: uuid.UUID,
    comment: str,
    email: str | None = None,
    eligible: bool | None = ...,
    can_attend: bool | None = ...,
    consent: bool | None = ...,
    stay_on_db: bool | None = ...,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Apply an edit from the backoffice. `comment` is required; raises on DELETED."""
```

- `...` sentinel so callers can distinguish "leave alone" from "set to None" (since None is a real value for the three-state bools).
- Refuses when `self.selection_status == RespondentStatus.DELETED` (raise `ValueError`).
- Requires non-empty `comment` (raise `ValueError`).
- Validates attribute keys using the existing `validate_no_field_name_collisions`.
- Records an `EDIT` comment using `add_comment(..., action=RespondentAction.EDIT)`.
- Touches `updated_at` only if something changed; if no changes and no comment-only edits, raise `ValueError("No changes submitted")` (form layer translates).

### 3.3 Service function

File: `src/opendlp/service_layer/respondent_service.py`

```python
def update_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    comment: str,
    *,
    email: str | None = None,
    eligible: bool | None = ...,
    can_attend: bool | None = ...,
    consent: bool | None = ...,
    stay_on_db: bool | None = ...,
    attributes: dict[str, Any] | None = None,
) -> None:
```

- Permission check via `can_edit_respondent`.
- Loads the respondent, asserts matching assembly.
- Calls `respondent.apply_edit(...)`, commits.
- `RespondentNotFoundError` on missing.

### 3.4 Form class

File: `src/opendlp/entrypoints/forms.py`

The edit form is dynamic — its fields depend on the schema. Two realistic approaches:

- **Construct a Flask-WTF form class per request** using `type()` to generate a subclass and setting fields from the schema. Pros: re-uses form infra and validators. Cons: dynamic class generation is a bit magic.
- **Hand-rolled dict-style form validation** in the service/view layer. Pros: simple. Cons: gives up Flask-WTF niceties (CSRF, errors, repopulation on POST).

Decision: **use Flask-WTF with dynamic form construction**. Helper in `forms.py`:

```python
def build_edit_respondent_form(
    schema: list[RespondentFieldDefinition],
    current_values: dict[str, Any],
) -> FlaskForm:
    """Return a Flask-WTF form instance with one field per schema entry plus a
    required comment field. Field type is looked up via effective_field_type."""
```

- `TEXT` → `StringField` with `Optional()` (email is also optional — blank allowed).
- `LONGTEXT` → `TextAreaField`.
- `INTEGER` → `IntegerField` with `Optional()` — submits blank → `None`.
- `BOOL` → `RadioField` with choices `[("true", _("Yes")), ("false", _("No"))]` and `DataRequired()`. No "Not set" — strict bool must be answered.
- `BOOL_OR_NONE` → `RadioField` with choices `[("true", _("Yes")), ("false", _("No")), ("", _("Not set"))]`; coerce `""` / missing → `None` in the view.
- `CHOICE_RADIO` → `RadioField` over `[(opt.value, opt.value) for opt in options]`. Per-option help_text rendered next to each radio (requires macro support — see 3.6). Optional unless the schema says otherwise (no "required choice" flag in Phase 3).
- `CHOICE_DROPDOWN` → `SelectField` over the same options, with an empty first choice labelled *"— none —"*. Per-option help_text rendered as a help block beneath the dropdown, listing each option and its description (only shown when any option has non-empty help_text).
- `EMAIL` → `StringField` with existing `DomainEmailValidator()` and `Optional()`.
- Comment → `TextAreaField` with `DataRequired()`.

**Choice-value drift handling.** If the respondent's current value for a choice field isn't in the schema's options list, the form builder merges the current value in as an extra option (so the user can keep it or change it), **and** the edit page flashes a warning at render time: `_("The current value for '%(field)s' is not in the options list: %(value)s.", ...)`. This surfaces schema-vs-data drift instead of hiding it.

### 3.5 Blueprint routes

File: `src/opendlp/entrypoints/blueprints/respondents.py`

```
GET  /assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/edit  → edit_respondent
POST /assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/edit  → edit_respondent
```

- GET: renders form populated from current respondent values.
- POST: validates, calls `update_respondent`. On validation error re-renders the form with errors. On success, flashes `_("Respondent updated.")` and redirects back to the view respondent page.
- Permission enforced twice: blueprint calls `can_edit_respondent` for the 403 path; service layer re-checks.
- Refuses (404 / redirect with flash) if respondent is DELETED.

### 3.6 Template

New file: `src/opendlp/entrypoints/templates/backoffice/assembly_edit_respondent.html`

- Layout mirrors `assembly_view_respondent.html` section-by-section but renders inputs instead of read-only values.
- One `<h2>` per `RespondentFieldGroup` in `GROUP_DISPLAY_ORDER`, skipping empty groups.
- Uses existing macros from `components/input.html` (`input`, `textarea`, `select`, `radio_group`).
- Bool radios in a single row — pass an `inline=True` flag to `radio_group`. Check the macro when implementing; if it doesn't already support inline rendering, extend it (small CSS/flex tweak).
- Choice radios with per-option help text — the existing `radio_group` macro accepts choices as `[(value, label)]` pairs. Extend it to also accept `[(value, label, help_text)]` triples, or accept an `option_help` dict parallel to choices. Pick whichever is lighter for the current macro shape. Help text renders immediately below each option's label.
- Choice dropdowns with help text — render the `<select>` as usual, then when any option has non-empty help_text render a `<dl>` or bulleted list below the control naming each option and its help text.
- Comment field at the bottom, inside its own section `<h2>{{ _("Change note") }}</h2>` with a helper line: *"Required. Describe why you're making this change."*
- Submit + Cancel buttons. Cancel returns to the view respondent page.

### 3.7 Edit links on list + view pages

Add `{% if can_edit %}...{% endif %}` edit links to:
- `templates/backoffice/assembly_respondents.html` — a per-row "Edit" link in the respondents table.
- `templates/backoffice/assembly_view_respondent.html` — an "Edit" button near the header.

Route handlers that render those pages compute `can_edit` via `can_edit_respondent` and pass it to the template. Links are hidden when `respondent.selection_status == DELETED`.

### 3.8 Tests

- **Domain**: `apply_edit` happy path; refuses blank comment; refuses on DELETED status; leaves untouched fields alone when the sentinel is used; validates attribute keys.
- **Form builder**: one test per `FieldType` asserting the right WTForms field class, validator set, and choice shape. Specifically:
  - `BOOL` renders two choices and requires a value.
  - `BOOL_OR_NONE` renders three choices including `("", _("Not set"))` and coerces blank/missing to `None`.
  - `CHOICE_RADIO` / `CHOICE_DROPDOWN` render all options; per-option help_text is reachable by the template.
  - Drift case: current value not in options is merged into the choices and the blueprint flashes a warning.
- **Service**: `update_respondent` round-trips through repo; permission test table (admin/global-organiser/assembly-manager/confirmation-caller all pass; no-role and future read-only fail); raises `RespondentNotFoundError` for mismatched assembly.
- **Blueprint**: GET renders expected form fields based on schema; POST with valid data redirects and shows the flash; POST with blank comment rerenders with error; 403 for unauthorised user; drift flash appears on GET when current value is out of options.
- **BDD / end-to-end**: a simple scenario that loads the edit page, edits a field + fills a comment, submits, and confirms the change shows on the view page and a new EDIT comment appears. (Optional — weigh against existing BDD coverage patterns.)

---

## Phase 4 — `READ_ONLY` assembly role

Add a view-only assembly role so organisers can grant dashboard access without write rights.

### 4.1 Enum + translations

File: `src/opendlp/domain/value_objects.py`

```python
class AssemblyRole(Enum):
    ASSEMBLY_MANAGER = "assembly-manager"
    CONFIRMATION_CALLER = "confirmation-caller"
    READ_ONLY = "read-only"
```

Extend `ASSEMBLY_ROLE_DESCRIPTIONS`:

```python
AssemblyRole.READ_ONLY.name: _l("Read Only - Can view the assembly but cannot make changes"),
```

Run `just translate-regen` after string additions.

### 4.2 ORM / migration

The role column uses `EnumAsString` with a string length of 50, so **no migration is required** for the enum change itself. Existing rows don't need rewriting. No empty/no-op migration — repo practice is to skip those.

### 4.3 Permission functions

File: `src/opendlp/service_layer/permissions.py`

- `can_view_assembly` already returns True for any role on the assembly — READ_ONLY inherits view access automatically. Add a test that confirms this.
- `can_manage_assembly` — no change (only matches `ASSEMBLY_MANAGER`).
- `can_call_confirmations` — no change.
- `can_edit_respondent` (from Phase 3) — no change; READ_ONLY is excluded by omission. Add an explicit test.

### 4.4 Admin UI for assigning the role

Find the page where assembly roles are assigned (likely in the users / admin blueprint — a quick search for `AssemblyRole.ASSEMBLY_MANAGER` in templates will pinpoint it). Add `READ_ONLY` to the role-picker options. Translate the description label.

### 4.5 Tests

- Permission unit tests: matrix over (role → `can_*` function) confirming READ_ONLY behaviour.
- Service tests: a user with only READ_ONLY on an assembly can call `get_respondent` / `get_respondents_for_assembly_paginated` but cannot call `update_respondent` / `delete_respondent` / `add_respondent_comment`.
- Blueprint test: the role-picker in the admin UI includes the new option.

---

## Phase 5 — Selection-status transitions

Per-transition buttons on the view respondent page, modal with required comment, service-level state change. Entirely independent of Phases 1–4.

### 5.1 Allowed transitions

Single source of truth in `src/opendlp/domain/value_objects.py`:

```python
ALLOWED_SELECTION_STATUS_TRANSITIONS: dict[RespondentStatus, list[RespondentStatus]] = {
    RespondentStatus.POOL: [RespondentStatus.SELECTED],
    RespondentStatus.SELECTED: [RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
    RespondentStatus.CONFIRMED: [RespondentStatus.WITHDRAWN],
    RespondentStatus.WITHDRAWN: [],
    RespondentStatus.DELETED: [],
    RespondentStatus.PARTICIPATED: [],
}
```

### 5.2 Domain method

File: `src/opendlp/domain/respondents.py`

```python
def apply_status_transition(
    self,
    *,
    new_status: RespondentStatus,
    author_id: uuid.UUID,
    comment: str,
) -> None:
    """Transition selection_status, refusing illegal moves. Appends an EDIT comment
    prefixed with 'Status: OLD → NEW. ' followed by the user's reason."""
```

- Refuses if `new_status` not in `ALLOWED_SELECTION_STATUS_TRANSITIONS[self.selection_status]`.
- Refuses on blank comment.
- For POOL → SELECTED: sets `selection_run_id = None` (manual override has no run). Flag in code comment.
- For WITHDRAWN from SELECTED or CONFIRMED: keeps `selection_run_id` as-is so the audit trail of which run they were selected in is preserved.
- Always touches `updated_at`.
- Records a comment with `action=RespondentAction.EDIT` and text `f"Status: {old.value} → {new.value}. {user_comment}"`.

Note on an existing mismatch: the current `Respondent.mark_as_selected` requires a `selection_run_id`, but manual overrides have none. `apply_status_transition` is the new canonical path for UI-driven changes; `mark_as_selected` stays as the algorithmic path.

### 5.3 Service + blueprint

- Service: `transition_respondent_status(uow, user_id, assembly_id, respondent_id, new_status, comment)` — permission is transition-specific:
  - `POOL → SELECTED`: `can_manage_assembly` (manual override of the selection algorithm; not something callers should do).
  - `SELECTED → CONFIRMED`, `SELECTED → WITHDRAWN`, `CONFIRMED → WITHDRAWN`: `can_call_confirmations` (this is the caller's core job; assembly managers and global roles are covered too since they satisfy `can_call_confirmations`).
  - Centralise this in a helper `_required_permission_for(old, new)` so the mapping is one table, not scattered if/else.
- Blueprint: `POST /assembly/<uuid:assembly_id>/respondents/<uuid:respondent_id>/transition-status` with `new_status` and `comment` form fields.
- On view respondent page: render one button per allowed transition (zero buttons if the list is empty). Each button has `x-data` to toggle a modal overlay (Alpine pattern per `templates/backoffice/patterns.html`) containing:
  - A short warning line summarising the change (e.g. *"This will mark the respondent as CONFIRMED. The change is logged with your comment."*).
  - A required `<textarea>` for the comment.
  - Cancel / Confirm buttons.
- Form POSTs to the transition route; response flashes and redirects back to the view page.

### 5.4 Tests

- **Domain**: allowed-transition matrix — for each (from, to) pair, either succeeds or raises; blank comment always raises; comment text includes the prefix.
- **Service**: permission enforcement; respondent not-found handling; commit happens.
- **Blueprint**: button visibility matches allowed transitions; POST with valid data transitions and flashes; POST with illegal transition returns a flash error; POST with blank comment is rejected.

---

## Phase 6 — Relocate `MAX_DISTINCT_VALUES_FOR_AUTO_ADD`

Small cleanup. The constant currently lives in `src/opendlp/service_layer/target_respondent_helpers.py` and is used by target code. Phase 2 adds a second independent consumer; time to move it somewhere neutral.

- New home: `src/opendlp/service_layer/constants.py` (or a similarly-named shared module if one already exists — quick check first).
- Update all imports (`target_respondent_helpers.py`, `assembly_service.py`, `entrypoints/blueprints/targets.py`, `entrypoints/blueprints/targets_legacy.py`, the Phase 2 new consumer, `tests/integration/test_targets_respondent_data.py`).
- Leave a re-export in the old location if removing it creates churn, or update the test import — whichever is cheaper.
- No behaviour change; tests stay green.

---

## Open questions to resolve before/during implementation

1. **Flask-WTF dynamic form class vs. per-request construction** — decide in Phase 3.1 during spike.
2. **Admin UI for READ_ONLY role assignment** — find the exact template/route and confirm the picker surface.
3. **Schema-page options editor shape** — repeating `{value, help_text}` input rows is the current plan. If that turns out to be fiddly under the CSP-safe Alpine rules, fall back to a structured table layout (one row per option) rendered server-side, with add/remove as form submissions rather than Alpine. Decide during Phase 1.6 implementation.

## Translation regeneration

Each phase that adds user-facing strings ends with `just translate-regen` plus a check that the `.po` files compile. Phases 1, 3, 4, 5 all add strings.

---

## TDD todo list

Each task follows red/green: write the failing test first, run it to confirm it fails for the intended reason, then write the minimum code to make it pass, then refactor. Where a task says "add test for X", the implementation task right after it is what drives the test from red to green. Do not write multiple tests in a row without implementing in between — that breaks the rhythm and makes it easy to write a test that passes accidentally.

Run `just test` after every green step and `just check` before every commit.

### Phase 1 — Typed field schema

**1.1 · `FieldType` enum** (target commit at end of 1.1–1.2)

- [x] Write failing domain test `test_field_type_enum_values` asserting all 8 values exist with the expected string values.
- [x] Add `FieldType` enum to `src/opendlp/domain/respondent_field_schema.py`; confirm test green.
- [x] Write failing test `test_field_type_labels_cover_every_value` asserting `FIELD_TYPE_LABELS` has one entry per enum value.
- [x] Add `FIELD_TYPE_LABELS` dict; confirm test green.
- [x] Write failing test `test_bool_types_and_choice_types_groupings` asserting `BOOL_TYPES == {BOOL, BOOL_OR_NONE}` and `CHOICE_TYPES == {CHOICE_RADIO, CHOICE_DROPDOWN}`.
- [x] Add `BOOL_TYPES` and `CHOICE_TYPES` frozensets; confirm test green.
- [x] Write failing test `test_fixed_field_types_overrides` covering each of the five fixed keys.
- [x] Add `FIXED_FIELD_TYPES` dict; confirm test green.

**1.2 · `ChoiceOption` dataclass**

- [x] Write failing test `test_choice_option_requires_non_blank_value`.
- [x] Write failing test `test_choice_option_defaults_help_text_to_empty`.
- [x] Write failing test `test_choice_option_to_dict_round_trip` (dict → ChoiceOption → dict).
- [x] Implement `ChoiceOption` frozen dataclass with `__post_init__` validation and `to_dict`/`from_dict`; confirm all three tests green.
- [x] **Commit**: "Add FieldType and ChoiceOption to respondent field schema domain".

**1.3 · Extend `RespondentFieldDefinition`** (target commit at end of 1.3–1.4)

- [x] Write failing test `test_definition_defaults_to_text_type`.
- [x] Write failing test `test_definition_rejects_choice_without_options`.
- [x] Write failing test `test_definition_rejects_options_on_non_choice_type`.
- [x] Write failing test `test_definition_accepts_choice_radio_with_options`.
- [x] Write failing test `test_definition_accepts_choice_dropdown_with_options`.
- [x] Extend constructor to accept `field_type` and `options`, validate invariant; confirm tests green.
- [x] Write failing test `test_update_refuses_type_change_on_fixed_row`.
- [x] Write failing test `test_update_changes_type_and_options_together_for_non_fixed_row`.
- [x] Write failing test `test_update_clears_options_when_switching_away_from_choice` (explicit `None`).
- [x] Extend `update()` to accept `field_type` and `options` with `_UNSET` sentinel; add fixed-row guard; confirm tests green.
- [x] Write failing test `test_effective_field_type_uses_override_for_fixed_keys_even_if_db_row_disagrees`.
- [x] Add `effective_field_type` property; confirm green.
- [x] Write failing test `test_create_detached_copy_preserves_field_type_and_options`.
- [x] Update `create_detached_copy`; confirm green.

**1.4 · ORM + migration**

- [x] Write failing integration test `test_field_definition_round_trip_with_choice_options_and_help_text` (save then reload through SQLAlchemy).
- [x] Add `field_type` and `options` columns to `respondent_field_definitions` in `src/opendlp/adapters/orm.py`.
- [x] Add the mapper-side serialization for options (`list[ChoiceOption]` ↔ `list[dict]`).
- [x] Run `uv run alembic revision --autogenerate -m "Add field_type and options to respondent_field_definitions"`; review and tidy the generated migration.
- [x] Add a deterministic backfill to the migration: default everything to `'text'`/`NULL`, then UPDATE fixed-field keys to their hardcoded types.
- [x] Run migration against a local DB with pre-existing schema rows; inspect the result manually.
- [x] Confirm the integration test is green.
- [x] **Commit**: "Add field_type and options columns to respondent field definitions".

**1.5 · Service layer** (target commit at end of 1.5)

- [x] Write failing test `test_update_field_accepts_field_type_and_options`.
- [x] Write failing test `test_update_field_refuses_type_change_on_fixed_row` raising `FieldDefinitionConflictError`.
- [x] Write failing test `test_update_field_unset_sentinel_preserves_existing_options_when_type_unchanged`.
- [x] Write failing test `test_update_field_explicit_none_clears_options_when_switching_to_text`.
- [x] Extend `update_field` signature with `field_type` and `options`, use `_UNSET` sentinel, add fixed-row guard; confirm tests green.
- [x] Write failing test `test_populate_schema_from_headers_sets_hardcoded_types_for_fixed_keys`.
- [x] Write failing test `test_populate_schema_from_headers_defaults_new_rows_to_text`.
- [x] Update `populate_schema_from_headers` / `apply_reconciliation` to apply the defaults; confirm green.
- [x] **Commit**: "Let update_field set field_type and options with fixed-row guard".

**1.6 · Schema page UI** (target commit at end of 1.6)

- [x] Write failing blueprint test `test_schema_page_renders_type_column`.
- [x] Write failing blueprint test `test_schema_page_post_accepts_field_type_and_options_with_help_text`.
- [x] Write failing blueprint test `test_schema_page_options_editor_hidden_for_fixed_rows`.
- [x] Extend `update_field_view` route to parse `field_type` and the repeating options rows; call the extended service.
- [x] Update the schema page template (`respondent_field_schema/view.html`): add the Type column, the type `<select>`, and a server-rendered options editor (add/remove forms per option). No Alpine needed for this shape.
- [x] Took the structured server-rendered fallback from open question 3 — no Alpine for this UI — each add/remove is its own POST.
- [ ] Manually verify the page in a browser (use rodney per CLAUDE.md guidance).
- [x] Confirm blueprint tests green.
- [x] **Commit**: "Add type/options editor to respondent schema page".

**1.7 · Translations + closeout**

- [x] Run `just translate-regen`; commit regenerated `.po` files.
- [x] Run `just check` and `just test`; fix anything that surfaces.
- [x] **Commit** (if not already included above): "Regenerate translations for respondent field schema types".

### Phase 2 — Guess field types from data

**2.1 · Service function** (target commit at end of 2.1)

- [x] Write failing test `test_guess_types_promotes_bool_column_to_bool_or_none`.
- [x] Write failing test `test_guess_types_promotes_integer_column`.
- [x] Write failing test `test_guess_types_promotes_small_distinct_column_to_choice_radio` (3 distinct values).
- [x] Write failing test `test_guess_types_promotes_mid_distinct_column_to_choice_dropdown` (10 distinct values).
- [x] Write failing test `test_guess_types_leaves_large_distinct_column_as_text` (50 distinct values).
- [x] Write failing test `test_guess_types_uses_target_category_values_when_field_key_matches`.
- [x] Write failing test `test_guess_types_skips_already_typed_rows`.
- [x] Write failing test `test_guess_types_skips_fixed_rows`.
- [x] Write failing test `test_guess_types_permission_gated_by_can_manage_assembly`.
- [x] Implement `guess_field_types` service function (with `_is_all_bool`, `_is_all_int`, `_choice_type_for` helpers); confirm all guess tests green.

**2.2 · Blueprint + template**

- [x] Write failing blueprint test `test_schema_page_shows_guess_button_when_conditions_met`.
- [x] Write failing blueprint test `test_schema_page_hides_guess_button_when_no_respondents`.
- [x] Write failing blueprint test `test_schema_page_hides_guess_button_when_no_untouched_fields`.
- [x] Write failing blueprint test `test_guess_types_post_flashes_summary_and_redirects`.
- [x] Add a `POST /assembly/<uuid:assembly_id>/respondent-schema/guess-types` route.
- [x] Extend the schema page template with the conditional button + helper text.
- [x] Confirm blueprint tests green.

**2.3 · Closeout**

- [x] Run `just translate-regen`.
- [x] Run `just check` and `just test`.
- [x] **Commit**: "Add guess-types button to respondent schema page".

### Phase 3 — Edit respondent page

**3.1 · Permission function** (target commit at end of 3.1)

- [x] Write failing test `test_can_edit_respondent_allows_admin`.
- [x] Write failing test `test_can_edit_respondent_allows_global_organiser`.
- [x] Write failing test `test_can_edit_respondent_allows_assembly_manager`.
- [x] Write failing test `test_can_edit_respondent_allows_confirmation_caller`.
- [x] Write failing test `test_can_edit_respondent_denies_user_without_role`.
- [x] (READ_ONLY denial test deferred to Phase 4 where the role exists.)
- [x] Implement `can_edit_respondent` in `permissions.py`; confirm tests green.
- [x] **Commit**: "Add can_edit_respondent permission".

**3.2 · Domain method** (target commit at end of 3.2)

- [x] Write failing test `test_apply_edit_requires_non_blank_comment`.
- [x] Write failing test `test_apply_edit_refuses_on_deleted_status`.
- [x] Write failing test `test_apply_edit_updates_email_and_flags_when_passed`.
- [x] Write failing test `test_apply_edit_leaves_unpassed_flags_alone_via_sentinel` (distinguishes "leave alone" from "set to None").
- [x] Write failing test `test_apply_edit_sets_flag_to_none_when_explicit_none_passed`.
- [x] Write failing test `test_apply_edit_merges_attributes_and_validates_keys`.
- [x] Write failing test `test_apply_edit_raises_when_no_field_changed_but_comment_supplied`.
- [x] Write failing test `test_apply_edit_appends_edit_comment`.
- [x] Implement `Respondent.apply_edit(...)`; confirm tests green.
- [x] **Commit**: "Add Respondent.apply_edit domain method".

**3.3 · Service function** (target commit at end of 3.3)

- [x] Write failing test `test_update_respondent_round_trips_through_repo`.
- [x] Write failing test `test_update_respondent_raises_for_mismatched_assembly`.
- [x] Write failing test `test_update_respondent_refuses_when_permission_denied`.
- [x] Write failing test `test_update_respondent_refuses_on_deleted_status`.
- [x] Implement `update_respondent` service function; confirm tests green.
- [x] **Commit**: "Add update_respondent service function".

**3.4 · Form builder** (target commit at end of 3.4)

- [x] Write failing test `test_build_form_text_renders_string_field`.
- [x] Write failing test `test_build_form_longtext_renders_textarea`.
- [x] Write failing test `test_build_form_integer_renders_integer_field_optional`.
- [x] Write failing test `test_build_form_bool_renders_two_radios_required`.
- [x] Write failing test `test_build_form_bool_or_none_renders_three_radios_with_not_set`.
- [x] Write failing test `test_build_form_choice_radio_renders_radio_field_with_options`.
- [x] Write failing test `test_build_form_choice_dropdown_renders_select_field_with_empty_first_option`.
- [x] Write failing test `test_build_form_choice_help_text_reachable_on_field`.
- [x] Write failing test `test_build_form_email_renders_string_field_with_domain_email_validator`.
- [x] Write failing test `test_build_form_comment_field_is_required`.
- [x] Write failing test `test_build_form_merges_drifted_value_into_choices` (current value not in options list appears as an extra choice).
- [x] Implement `build_edit_respondent_form` (new module `entrypoints/edit_respondent_form.py`); confirm tests green.
- [x] **Commit**: "Add edit respondent form builder".

**3.5 · Macro adaptations** (commit either here or folded into 3.6)

- [ ] Inspect `components/input.html` `radio_group` macro.
- [ ] Write failing template/integration test `test_radio_group_renders_inline_when_inline_flag_set`.
- [ ] Extend the macro to support `inline=True`; confirm test green.
- [ ] Write failing template test `test_radio_group_renders_per_option_help_text`.
- [ ] Extend the macro to accept per-option help text; confirm test green.
- [ ] Write failing template test `test_select_with_help_text_renders_description_block`.
- [ ] Extend `select` macro (or add a sibling helper) for the post-dropdown help block; confirm green.

**3.6 · Blueprint + template + edit links** (target commit at end of 3.6–3.7)

- [ ] Write failing blueprint test `test_edit_respondent_get_renders_form_grouped_by_schema`.
- [ ] Write failing blueprint test `test_edit_respondent_post_valid_data_redirects_and_flashes_success`.
- [ ] Write failing blueprint test `test_edit_respondent_post_blank_comment_rerenders_with_error`.
- [ ] Write failing blueprint test `test_edit_respondent_403_for_unauthorised_user`.
- [ ] Write failing blueprint test `test_edit_respondent_flashes_warning_when_current_value_not_in_options`.
- [ ] Write failing blueprint test `test_edit_respondent_refused_for_deleted_respondent`.
- [ ] Implement `GET` and `POST /assembly/<id>/respondents/<id>/edit` routes.
- [ ] Create `assembly_edit_respondent.html` template; section per `RespondentFieldGroup`, widgets driven by `effective_field_type`.
- [ ] Manually verify in a browser (golden path + drift warning + DELETED refusal).
- [ ] Confirm blueprint tests green.

**3.7 · Edit links on list + view pages**

- [ ] Write failing blueprint test `test_respondents_list_shows_edit_link_for_editable_respondents`.
- [ ] Write failing blueprint test `test_respondents_list_hides_edit_link_for_deleted_respondents`.
- [ ] Write failing blueprint test `test_view_respondent_shows_edit_button_for_editable_respondents`.
- [ ] Pass `can_edit` into both templates; render the link conditionally.
- [ ] Confirm tests green.
- [ ] **Commit**: "Add edit respondent page and entry links".

**3.8 · Closeout**

- [ ] (Optional) BDD scenario for the edit flow end-to-end.
- [ ] Run `just translate-regen`.
- [ ] Run `just check` and `just test`.
- [ ] **Commit**: "Regenerate translations for edit respondent".

### Phase 4 — `READ_ONLY` assembly role

**4.1 · Enum + translations** (target commit at end of 4.1–4.3)

- [ ] Write failing test `test_assembly_role_read_only_value`.
- [ ] Write failing test `test_assembly_role_descriptions_cover_every_role`.
- [ ] Add `AssemblyRole.READ_ONLY` and extend `ASSEMBLY_ROLE_DESCRIPTIONS`; confirm tests green.

**4.2 · Permission behaviour**

- [ ] Write failing test `test_can_view_assembly_allows_read_only`.
- [ ] Write failing test `test_can_manage_assembly_denies_read_only`.
- [ ] Write failing test `test_can_call_confirmations_denies_read_only`.
- [ ] Write failing test `test_can_edit_respondent_denies_read_only` (the deferred case from 3.1).
- [ ] Confirm the existing permission functions already produce the right answers; add explicit READ_ONLY arms or inline comments where clarity helps.

**4.3 · Service-layer integration**

- [ ] Write failing integration test: a READ_ONLY user can `get_respondent` but `update_respondent` / `delete_respondent` / `add_respondent_comment` all raise `InsufficientPermissions`.
- [ ] Confirm test green (no code change expected beyond 4.1–4.2).
- [ ] **Commit**: "Add READ_ONLY assembly role".

**4.4 · Admin UI**

- [ ] Find the role-picker template/route (grep for `AssemblyRole.ASSEMBLY_MANAGER` in templates/blueprints).
- [ ] Write failing blueprint test `test_role_picker_includes_read_only_option`.
- [ ] Add READ_ONLY to the picker; confirm test green.
- [ ] Manually assign the role to a test user and verify the effect in a browser session.
- [ ] **Commit**: "Offer READ_ONLY in the assembly role picker".

**4.5 · Closeout**

- [ ] Run `just translate-regen`.
- [ ] Run `just check` and `just test`.
- [ ] **Commit**: "Regenerate translations for READ_ONLY role".

### Phase 5 — Selection-status transitions

**5.1 · Allowed transitions table** (target commit at end of 5.1–5.2)

- [ ] Write failing test `test_allowed_transitions_matches_agreed_matrix` asserting the exact dict shape.
- [ ] Add `ALLOWED_SELECTION_STATUS_TRANSITIONS` to `value_objects.py`; confirm test green.

**5.2 · Domain method**

- [ ] Write failing test `test_apply_status_transition_allows_every_listed_pair` (parametrised over the matrix).
- [ ] Write failing test `test_apply_status_transition_refuses_every_non_listed_pair`.
- [ ] Write failing test `test_apply_status_transition_requires_non_blank_comment`.
- [ ] Write failing test `test_apply_status_transition_prepends_status_line_to_comment`.
- [ ] Write failing test `test_apply_status_transition_clears_selection_run_id_on_manual_select`.
- [ ] Write failing test `test_apply_status_transition_preserves_selection_run_id_on_withdrawal`.
- [ ] Write failing test `test_apply_status_transition_appends_edit_comment`.
- [ ] Implement `Respondent.apply_status_transition(...)`; confirm tests green.
- [ ] **Commit**: "Add Respondent.apply_status_transition".

**5.3 · Service + permissions** (target commit at end of 5.3)

- [ ] Write failing test `test_transition_permission_helper_maps_transitions_to_permission_function`.
- [ ] Write failing test `test_pool_to_selected_requires_can_manage_assembly`.
- [ ] Write failing test `test_selected_to_confirmed_allowed_for_confirmation_caller`.
- [ ] Write failing test `test_selected_to_withdrawn_allowed_for_confirmation_caller`.
- [ ] Write failing test `test_confirmed_to_withdrawn_allowed_for_confirmation_caller`.
- [ ] Write failing test `test_transition_respondent_status_round_trips_through_repo`.
- [ ] Write failing test `test_transition_respondent_status_refuses_illegal_move` with a clear error.
- [ ] Implement `_required_permission_for(old, new)` helper and `transition_respondent_status` service function; confirm tests green.
- [ ] **Commit**: "Add transition_respondent_status service".

**5.4 · Blueprint + template**

- [ ] Write failing blueprint test `test_view_respondent_shows_buttons_for_every_allowed_transition`.
- [ ] Write failing blueprint test `test_view_respondent_shows_no_transition_buttons_for_terminal_states` (WITHDRAWN, DELETED, PARTICIPATED).
- [ ] Write failing blueprint test `test_transition_post_valid_data_flashes_and_redirects`.
- [ ] Write failing blueprint test `test_transition_post_blank_comment_rejected`.
- [ ] Write failing blueprint test `test_transition_post_illegal_move_rejected`.
- [ ] Write failing blueprint test `test_transition_post_respects_transition_specific_permission` (a caller can confirm but cannot pool→select).
- [ ] Implement the route `POST /assembly/<id>/respondents/<id>/transition-status`.
- [ ] Add the transition button + modal UX to `assembly_view_respondent.html` (Alpine `x-data` on flat properties, CSP-safe).
- [ ] Manually verify each allowed transition in a browser.
- [ ] Confirm blueprint tests green.

**5.5 · Closeout**

- [ ] Run `just translate-regen`.
- [ ] Run `just check` and `just test`.
- [ ] **Commit**: "Add selection-status transition UI".

### Phase 6 — Relocate `MAX_DISTINCT_VALUES_FOR_AUTO_ADD`

- [ ] Decide the new module (`src/opendlp/service_layer/constants.py` unless a more appropriate existing one surfaces).
- [ ] Move the constant; leave a deprecated re-export in `target_respondent_helpers.py` only if removing it creates import churn across tests.
- [ ] Update imports in `target_respondent_helpers.py`, `assembly_service.py`, `entrypoints/blueprints/targets.py`, `entrypoints/blueprints/targets_legacy.py`, the new Phase 2 consumer, and `tests/integration/test_targets_respondent_data.py`.
- [ ] Run `just check` and `just test` — no new tests needed; existing coverage catches regressions.
- [ ] **Commit**: "Relocate MAX_DISTINCT_VALUES_FOR_AUTO_ADD to shared constants module".
