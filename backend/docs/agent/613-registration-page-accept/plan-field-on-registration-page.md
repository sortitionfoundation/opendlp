# Plan — `FieldOnRegistrationPage` enum on `RespondentFieldDefinition`

**Branch:** `610-registration-page-html`
**Date:** 2026-06-08
**Elaborates:** `docs/agent/613-registration-page-accept/research.md` §6 Q14/Q15
(revised 2026-06-08)
**Status:** Draft plan — ready for review before code lands.

This plan implements the schema change decided in the 613 research doc: replace
the never-built two-bool plan (`is_required` + `for_registration_page`) with a
single enum that records, per respondent field, whether the field appears on the
public registration form and whether it is required there. As part of the same
change, bool fields on the public form move from yes/no **radios** to
**checkboxes**, and the public submission validator becomes enum-driven.

The back-office edit-registrant form is **not** touched — it keeps full
True/False/None handling (see §7).

---

## 1. The enum and its semantics

New enum in `domain/respondent_field_schema.py`, alongside `FieldType`:

```python
class FieldOnRegistrationPage(Enum):
    NO = "no"
    YES_OPTIONAL = "yes_optional"
    YES_REQUIRED = "yes_required"
```

(Lowercase string values to match the existing `FieldType` / `RespondentFieldGroup`
convention, persisted via `EnumAsString`.)

Stored on `RespondentFieldDefinition.on_registration_page`. Meaning:

| Value          | non-bool field                                                  | bool field (BOOL / BOOL_OR_NONE)                                                       |
| -------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `NO`           | not on the form; validator ignores it; column keeps its default | same — not on the form; never produces a value                                         |
| `YES_OPTIONAL` | on the form, may be left blank                                  | **checkbox**, may be left unchecked → `True` if checked, `False` if not (never `None`) |
| `YES_REQUIRED` | on the form, must have a value                                  | **checkbox + `required`**, must be checked → `True`; unchecked is a validation error   |

Invariants (from research §6 Q14):

- A bool field on the form is a checkbox → it can **never** yield `None`.
  `None` survives only for `NO` fields (not collected) and for the back-office /
  CSV / manual-entry paths.
- "Required but either answer is valid" is modelled as `CHOICE_RADIO`, not BOOL.

---

## 2. Files touched (overview)

| Layer      | File                                                     | Change                                                                                                          |
| ---------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Domain     | `domain/respondent_field_schema.py`                      | add enum, constructor param, `update()`, `create_detached_copy()`, seed-default map                             |
| Domain     | `domain/registration_page.py`                            | checkbox renderer; `_render_field`/`generate_starter_form_html` read the enum; drop `required_field_keys` param |
| Adapters   | `adapters/orm.py`                                        | add `on_registration_page` column (`EnumAsString`)                                                              |
| Migration  | `migrations/versions/<new>.py`                           | add column + backfill existing rows                                                                             |
| Service    | `service_layer/registration_submission_service.py`       | enum-driven validation + checkbox bool coercion                                                                 |
| Service    | `service_layer/respondent_field_schema_service.py`       | `add_field` / `update_field` accept the enum; new-field default                                                 |
| Service    | `service_layer/registration_page_service.py`             | drop the `required_field_keys` pass-through                                                                     |
| Entrypoint | `entrypoints/blueprints/respondent_field_schema.py`      | parse + persist the enum from the editor form                                                                   |
| Entrypoint | `entrypoints/blueprints/dev.py`                          | update `generate_starter_form_html` call                                                                        |
| Template   | `templates/backoffice/respondent_field_schema/view.html` | per-field "On registration form" dropdown                                                                       |
| Tests      | unit / contract / integration / bdd / e2e                | new coverage + fix existing radio assertions                                                                    |

The repository (`sql_repository.py`, `repositories.py`, `tests/fakes.py`) needs
**no** change — it round-trips the mapped object generically. `tests/conftest.py`
`_delete_all_test_data` needs **no** change — no new table.

---

## 3. Phase 1 — Domain

### 3.1 `domain/respondent_field_schema.py`

1. Add the `FieldOnRegistrationPage` enum (above `FieldType` or just after it).
2. Add a seed-default map mirroring `FIXED_FIELD_TYPES`:

   ```python
   FIXED_FIELD_ON_REGISTRATION_PAGE: dict[str, FieldOnRegistrationPage] = {
       "email": FieldOnRegistrationPage.YES_REQUIRED,
       "eligible": FieldOnRegistrationPage.YES_REQUIRED,
       "can_attend": FieldOnRegistrationPage.YES_REQUIRED,
       "consent": FieldOnRegistrationPage.YES_REQUIRED,
       "stay_on_db": FieldOnRegistrationPage.YES_OPTIONAL,
   }
   ```

   Note: unlike `effective_field_type`, this is **only a seed default** — the
   stored column is freely editable per field (an assembly may set `can_attend`
   to `NO`). There is no `effective_*` property for it.

3. Constructor: add
   `on_registration_page: FieldOnRegistrationPage = FieldOnRegistrationPage.YES_REQUIRED`.
   - Default `YES_REQUIRED` matches the "almost all fields required" rule and
     preserves today's behaviour (every field is currently rendered and validated
     as required).
   - Add a guard: **if `is_derived` is True, force `on_registration_page = NO`**
     (a computed field is never collected on the form). Coerce silently rather
     than raise — `is_derived` callers don't pass the new arg today. Document the
     coercion with a comment.
   - Store `self.on_registration_page = ...`.

4. `update()`: add an `on_registration_page: FieldOnRegistrationPage | None = None`
   parameter; when not `None`, set it and mark `changed = True`. (Editable on
   fixed fields too — do **not** gate it behind the `is_fixed` check that guards
   `field_type`/`options`.)

5. `create_detached_copy()`: pass `on_registration_page=self.on_registration_page`.

### 3.2 `domain/registration_page.py` — checkbox rendering

1. Add `_render_checkbox`:

   ```python
   def _render_checkbox(field: RespondentFieldDefinition, required_attr: str) -> list[str]:
       key = html_lib.escape(field.field_key, quote=True)
       label = html_lib.escape(field.label)
       checked_expr = _jinja_call("checked", field.field_key, "yes")
       return [
           f'<label><input type="checkbox" id="{key}" name="{key}" value="yes" '
           f'{checked_expr}{required_attr}> {label}</label>',
           _jinja_call("field_errors", field.field_key),
       ]
   ```

   The existing `checked(key, "yes")` helper re-populates the box on a failed-POST
   re-render (checked iff `values[key] == "yes"`), so no new helper is needed.

2. Replace the `required_field_keys` mechanism with the enum. Change
   `_render_field(field)` (drop the second param) to:
   - return `[]` (render nothing) when `field.on_registration_page == NO`;
   - compute `is_required = field.on_registration_page == YES_REQUIRED`,
     `required_attr = " required" if is_required else ""`;
   - route `BOOL_TYPES` → `_render_checkbox(field, required_attr)` (replacing the
     `_render_yes_no_radios` call);
   - keep text/email/number/textarea/choice routing, now driven by the enum's
     `is_required`.

3. **Keep `_render_yes_no_radios`** for now only if something else uses it; the
   Explore map shows it is used solely by `_render_field`, so **remove it** along
   with the radio code path. (If a test references it directly, update the test.)

4. `generate_starter_form_html(fields)`: drop the `required_field_keys`
   parameter; iterate fields and skip `NO` fields (the per-group bucket should
   suppress a group that becomes empty after the `NO` filter — `_group_fields`
   already buckets everything, so filter inside the render loop and keep the
   existing "skip empty bucket" guard, which will now also fire when every field
   in a group is `NO`).

> **Authored-HTML / bool-coercion note.** The registration feature is
> branch-only — **no production registration page exists**, so there is no saved
> authored HTML to stay compatible with, and no data-migration concern here. The
> reason the validator (Phase 5) still parses bool values properly rather than
> truthy-testing is that **authored HTML is free-form going forward**: an author
> can write yes/no radios (or `value="no"`) in their own form, and the validator
> must read `"no"` as `False`, not as "non-empty → True". So the rule stands —
> parse `yes/no/true/false/on/1/0`, treat *absent* as the unchecked case — but
> it's a correctness rule for free-form authored markup, not a back-compat
> obligation. If the dual checkbox-or-radio handling gets messy, we are free to
> be strict/checkbox-only (reject unexpected bool values) since nothing in
> production depends on the lenient reading. See §5.

### 3.3 `domain/value_objects.py`

No change — `RespondentStatus.TEST_SUBMISSION` already exists (confirmed in the
research doc and current code). This plan is scoped to the field-schema enum
only.

---

## 4. Phase 2 — Adapters + migration

### 4.1 `adapters/orm.py`

Add to the `respondent_field_definitions` table (after `field_type`):

```python
Column(
    "on_registration_page",
    EnumAsString(FieldOnRegistrationPage, 32),
    nullable=False,
    default=FieldOnRegistrationPage.YES_REQUIRED,
),
```

Import `FieldOnRegistrationPage` alongside the existing `FieldType` /
`RespondentFieldGroup` imports at the top of `orm.py`.

No mapper change in `database.py` (imperative mapping picks the column up
generically, same as `field_type`).

### 4.2 New Alembic migration

Generate with autogenerate, then hand-tune the backfill:

```bash
uv run alembic revision --autogenerate -m "add on_registration_page to respondent field definitions"
```

Parent revision is the current head **`28ad0135cfe8`** (single head, confirmed).
Mirror the `bc31250a8ad0` (field_type) pattern:

```python
def upgrade() -> None:
    op.add_column(
        "respondent_field_definitions",
        sa.Column(
            "on_registration_page",
            sa.String(length=32),
            nullable=False,
            server_default="yes_required",
        ),
    )
    # Backfill existing rows to preserve today's "everything required" behaviour:
    #   derived fields  -> not on the form
    #   stay_on_db      -> optional checkbox
    #   everything else -> required (the column default)
    op.execute(
        "UPDATE respondent_field_definitions SET on_registration_page = 'no' "
        "WHERE is_derived = true"
    )
    op.execute(
        "UPDATE respondent_field_definitions SET on_registration_page = 'yes_optional' "
        "WHERE field_key = 'stay_on_db'"
    )

def downgrade() -> None:
    op.drop_column("respondent_field_definitions", "on_registration_page")
```

Keep `server_default="yes_required"` (matches the field_type migration, which
kept `server_default="text"`). The ORM-level `default` handles ORM inserts;
`server_default` covers raw inserts.

> Existing data exists: the respondent-field-schema feature already ships (the
> grouped view_registrant page uses it), so live assemblies have
> `respondent_field_definitions` rows. The backfill keeps their forms behaving as
> they do today.

---

## 5. Phase 3 — Submission validator (the meaty change)

`service_layer/registration_submission_service.py`.

### 5.1 `_validate_form_data` — skip `NO`, branch on requiredness

```python
for fd in field_definitions:
    if fd.on_registration_page == FieldOnRegistrationPage.NO:
        continue  # not collected on the form
    key = fd.field_key
    value = form_data.get(key, "")
    cleaned_value, error = _validate_field_value(fd, value)
    if error:
        errors.setdefault(key, []).append(error)
    elif cleaned_value is not None:
        cleaned[key] = cleaned_value
    # optional non-bool left blank -> cleaned_value None -> skipped
```

### 5.2 `_validate_field_value` — enum-aware, checkbox bool coercion

Pass requiredness in (derive from the enum) and rewrite the bool branch.

```python
required = fd.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED
str_value = str(value).strip() if value is not None else ""

# bool: checkbox semantics, but also accept legacy yes/no radio values
if fd.effective_field_type in (FieldType.BOOL, FieldType.BOOL_OR_NONE):
    return _coerce_form_bool(str_value, required=required)

# email / choice / integer: validate only when present; required-check when blank
if not str_value:
    if required:
        return None, _("This field is required")
    return None, None          # optional + blank -> stored as nothing
... (existing email / choice / integer / text validation on the non-empty value)
```

New helper `_coerce_form_bool(str_value, *, required)`:

```python
truthy = {"yes", "true", "on", "1"}
falsy = {"no", "false", "0"}
v = str_value.lower()
if v in truthy:
    return True, None
if v in falsy:
    return False, None
if v == "":                        # checkbox unchecked OR radio not picked
    if required:
        return None, _("Please tick this box to continue")
    return False, None             # optional bool -> False, never None
return None, _("Please select a valid option")
```

Key points:

- A required checkbox left unchecked → key absent → `""` → error. ✔
- An optional checkbox unchecked → `False` (GDPR-safe for `stay_on_db`). ✔
- A free-form authored radio answering "no" → `False` (not `True`). ✔ (this is
  why we parse the value rather than test truthiness — see the note in §3.2)
- Never returns `None` for an on-form bool. ✔

### 5.3 Required non-bool blank

Current code rejects every blank field. New code rejects a blank only when
`YES_REQUIRED`; a blank `YES_OPTIONAL` field validates to "nothing" and is left
out of `cleaned` (so its `Respondent` column keeps the default — `""` for email,
`None` for the fixed bools, absent from `attributes`).

### 5.4 No change needed in `_create_and_save_respondent`

It already pops the fixed keys with sensible defaults (`email` → `""`, bools →
`None`) and routes the rest to `attributes`. A `NO` / optional-blank field simply
isn't in `cleaned_data`, so the default applies.

### 5.5 i18n

The new/blank messages must use `_()` (the file currently returns bare strings
like `"This field is required"`; check whether the validators in
`domain/validators.py` are already gettext'd and match that style — keep
consistent, prefer wrapping the user-facing strings). Run `just translate-regen`
after.

---

## 6. Phase 4 — Schema-editor service + UI

### 6.1 `service_layer/respondent_field_schema_service.py`

- `add_field(...)`: accept `on_registration_page: FieldOnRegistrationPage =
FieldOnRegistrationPage.YES_REQUIRED` and pass it to the constructor. (Derived
  fields created here, if any, will be coerced to `NO` by the constructor guard.)
- `update_field(...)`: accept `on_registration_page:
FieldOnRegistrationPage | None = None` and forward to `field.update(...)`.
- `_build_fixed_rows(...)`: set each fixed row's `on_registration_page` from
  `FIXED_FIELD_ON_REGISTRATION_PAGE` (so a freshly-seeded schema gets
  `stay_on_db = YES_OPTIONAL`, the rest `YES_REQUIRED`).
- `populate_schema_from_headers` / heuristics: custom fields inherit the
  constructor default `YES_REQUIRED`; derived fields → `NO` via the guard.
  (See §9 — Q1 for whether CSV-seeded fields should default to `NO` instead.)

### 6.2 `entrypoints/blueprints/respondent_field_schema.py`

- Add `_parse_on_registration_page(raw: str) -> FieldOnRegistrationPage`
  (mirroring `_parse_field_type` / `_parse_group`; fall back to a sensible
  default on bad input).
- In `update_field_view`, read the new form value and pass
  `on_registration_page=...` into the `update_field` service call.

### 6.3 `templates/backoffice/respondent_field_schema/view.html`

- Add an "On registration form" `<select>` column to each field row with the
  three options (gettext'd labels: _("Not shown") / _("Optional") /
  _("Required") — confirmed copy, §9 Q2), pre-selected from
  `field.on_registration_page`.
- Shown for **all** fields including fixed ones (unlike the Field Type column,
  which is disabled for fixed fields).
- The select must post within the same per-row form the Save button submits, so
  `update_field_view` receives it.
- Accessibility: the select needs an associated label (visually-hidden per-row
  label or an `aria-label` referencing the field), per the component
  accessibility guide.

### 6.4 `service_layer/registration_page_service.py` + `dev.py`

- `_build_starter_html` (in `registration_page_service.py`) currently calls
  `generate_starter_form_html(list(fields))` with no `required_field_keys` — it
  needs **no change** beyond confirming the dropped parameter.
- `dev.py` line ~592–600 and `backoffice_registration.py` line ~241 call the
  domain `generate_starter_form_html`; update any that pass `required_field_keys`
  (none should, but confirm) and ensure they still compile after the signature
  change.

---

## 7. Phase 5 — Confirm the back-office edit form is untouched

No code change. Add/keep a test that pins the separation:

- `edit_respondent_form.py` keeps `_bool_or_none_choices()` (Yes / No / Not set)
  and `radio_or_none_to_bool()` — bool fields there remain three-state.
- The new enum does **not** influence the edit form: a field can be `NO` on the
  registration form yet still editable (and `None`-able) in the back office.
- Document this explicitly in the test name, e.g.
  `test_edit_respondent_form_bool_is_three_state_regardless_of_on_registration_page`.

---

## 8. Test inventory

This is the **master catalogue** of tests the change needs. It is *not* a
separate end-of-project phase: the §12 execution checklist distributes every
item below into the phase that owns it, written **red-first** (failing test
before the implementation that makes it pass).

Run with `CI=true` (per repo convention) and `just check` before commit.

**Unit — domain (`tests/unit/test_respondent_field_schema.py`):**

- enum values / string round-trip
- constructor default `YES_REQUIRED`; `is_derived=True` forces `NO`
- `update(on_registration_page=...)` works on fixed and non-fixed fields
- `create_detached_copy()` carries the value
- `FIXED_FIELD_ON_REGISTRATION_PAGE` seed values

**Unit — starter generator (`tests/unit/` for `registration_page`):**

- bool field renders a `checkbox` (not radios) with `value="yes"` + `checked()`
- `YES_REQUIRED` bool gets the `required` attribute; `YES_OPTIONAL` does not
- `NO` fields are omitted entirely; a group with only `NO` fields renders no `<h2>`
- non-bool `YES_REQUIRED`/`YES_OPTIONAL` `required` attribute behaviour
- **fix existing tests** that assert yes/no radio markup in starter output

**Unit — validator (`tests/unit/` for `registration_submission_service`):**

- required checkbox unchecked (key absent) → error
- optional checkbox unchecked → `False`
- checkbox checked (`"yes"`) → `True`
- free-form authored radio `"no"` → `False` (value is parsed, not truthy-tested)
- `NO` field present in POST → ignored, not stored
- optional non-bool blank → accepted, not stored; required non-bool blank → error
- required choice unselected (`""`) → error (research §5 Q9 / §9 Q4)

**Contract (`tests/contract/test_respondent_field_definition_repo.py`):**

- add/get round-trips `on_registration_page` for each enum value

**Integration (`tests/integration/`):**

- `submit_registration` end-to-end with a schema mixing all three enum values
  (TEST → TEST_SUBMISSION, PUBLISHED → POOL) — asserts the created `Respondent`
  has the right `eligible`/`consent`/`stay_on_db`/`attributes`
- schema-service `add_field`/`update_field` persist the enum

**BDD / e2e:**

- backoffice schema editor: set a field to each value, save, reload, assert
  persisted (`tests/e2e/test_backoffice_respondent_field_schema.py`)
- existing registration-submission BDD scenarios still pass with checkbox markup

**Migration:**

- if there is a migration test harness, assert upgrade backfills
  derived→`no`, `stay_on_db`→`yes_optional`, else→`yes_required`; assert
  downgrade drops the column.

---

## 9. Decisions (resolved 2026-06-08)

1. **CSV-seeded field default → `YES_REQUIRED`.**
   `populate_schema_from_headers` creates custom fields from an uploaded
   respondent CSV. They inherit the constructor default `YES_REQUIRED`
   (consistent, and preserves current behaviour). Trade-off accepted: imported
   columns auto-appear on a generated starter form; an admin can set any to `NO`
   in the schema editor. No special-case `NO` in that service path.

2. **Editor dropdown labels → _("Not shown") / _("Optional") / _("Required").**

3. **Required-checkbox error copy → one generic message** for now
   (_("Please tick this box to continue")). Per-field custom error text is out of
   scope here (the schema has no per-field error-text column) but is noted as a
   **future consideration** — a later story may add a per-field error-message
   column, at which point the validator would prefer it and fall back to this
   generic string.

---

## 10. Commit sequencing

Per the repo convention (docs separate from code), and to keep review tractable:

1. _(done)_ docs commit — research-doc revision.
2. domain + ORM + migration (enum, column, backfill) — one commit.
3. validator + starter-generator (checkbox + enum-driven) — one commit.
4. schema-editor service + blueprint + template — one commit.
5. tests can ride with each functional commit, or land as a final commit if that
   reads more cleanly; translations regen (`just translate-regen`) in the commit
   that introduces the new strings.

Each commit must pass `just check` and `CI=true just test`.

---

## 11. References

- `docs/agent/613-registration-page-accept/research.md` §6 Q14/Q15
- `src/opendlp/domain/respondent_field_schema.py` (enum, constructor,
  `FIXED_FIELD_TYPES`, `IN_SCHEMA_FIXED_FIELDS`)
- `src/opendlp/domain/registration_page.py` (`_render_field`,
  `_render_yes_no_radios`, `generate_starter_form_html`, `checked` helper)
- `src/opendlp/service_layer/registration_submission_service.py` (validator)
- `src/opendlp/service_layer/respondent_field_schema_service.py`
  (`add_field`, `update_field`, `_build_fixed_rows`)
- `src/opendlp/adapters/orm.py` (`EnumAsString`, table at lines 535–563)
- `migrations/versions/bc31250a8ad0_add_field_type_and_options_to_.py`
  (pattern to mirror); current head `28ad0135cfe8`
- `src/opendlp/entrypoints/blueprints/respondent_field_schema.py`,
  `templates/backoffice/respondent_field_schema/view.html` (editor UI)
- `src/opendlp/entrypoints/edit_respondent_form.py` (back-office form — NOT
  changed)

---

## 12. Execution checklist (red/green TDD)

Work top to bottom. Each phase is a **red → green → verify** cycle: write the
listed tests first and watch them fail (red), implement the minimum to make them
pass (green), then run the gate (`CI=true just test` + `just check`) before
moving on. Tick boxes as you go. Each phase maps to a commit in §10.

The §8 inventory is the source for the test tasks below; nothing in §8 is
deferred to "the end".

### Phase 1 — Domain: enum + `RespondentFieldDefinition`

Pure domain, no DB needed. (Plan §3.1.)

**Red — `tests/unit/test_respondent_field_schema.py`:**

- [ ] `FieldOnRegistrationPage` exists with members `NO` / `YES_OPTIONAL` /
      `YES_REQUIRED` and string values `"no"` / `"yes_optional"` / `"yes_required"`.
- [ ] constructor defaults `on_registration_page` to `YES_REQUIRED` when omitted.
- [ ] constructor with `is_derived=True` forces `on_registration_page = NO`
      (even if a non-`NO` value is passed).
- [ ] `update(on_registration_page=...)` sets the value and touches `updated_at`,
      on both a fixed and a non-fixed field; `update()` with it omitted leaves it
      unchanged.
- [ ] `create_detached_copy()` carries `on_registration_page` through.
- [ ] `FIXED_FIELD_ON_REGISTRATION_PAGE` maps email/eligible/can_attend/consent →
      `YES_REQUIRED` and stay_on_db → `YES_OPTIONAL`.

**Green — `src/opendlp/domain/respondent_field_schema.py`:**

- [ ] add the `FieldOnRegistrationPage` enum.
- [ ] add the `FIXED_FIELD_ON_REGISTRATION_PAGE` seed-default map.
- [ ] add the constructor param (default `YES_REQUIRED`) + the `is_derived → NO`
      guard with an explanatory comment; store the attribute.
- [ ] extend `update()` with the optional param.
- [ ] extend `create_detached_copy()`.

**Verify:**

- [ ] `CI=true uv run pytest tests/unit/test_respondent_field_schema.py` green.
- [ ] `just check` (mypy/ruff) clean for the edited file.

### Phase 2 — Persistence: ORM column + migration

(Plan §4.)

**Red — `tests/contract/test_respondent_field_definition_repo.py`:**

- [ ] add/get round-trips `on_registration_page` for each of the three enum
      values (fails first because the ORM column doesn't exist yet).

**Green:**

- [ ] add the `on_registration_page` `EnumAsString(FieldOnRegistrationPage, 32)`
      column to `adapters/orm.py` (import the enum there) with
      `nullable=False, default=FieldOnRegistrationPage.YES_REQUIRED`.
- [ ] confirm the contract/integration test DB picks the column up (metadata
      `create_all` vs migrations — check `tests/conftest.py`; if it builds from
      metadata, the ORM column is enough for tests).
- [ ] generate the migration:
      `uv run alembic revision --autogenerate -m "add on_registration_page to respondent field definitions"`
      (parent = head `28ad0135cfe8`).
- [ ] hand-edit the migration to the §4.2 shape: `add_column` with
      `server_default="yes_required"`, then backfill `derived → 'no'` and
      `stay_on_db → 'yes_optional'`; `downgrade` drops the column.

**Red/Green — migration test (if a harness exists; see `tests/` for existing
migration tests):**

- [ ] upgrade backfills derived→`no`, stay_on_db→`yes_optional`, else→
      `yes_required`; downgrade drops the column.

**Verify:**

- [ ] `uv run alembic upgrade head` then `uv run alembic downgrade -1` then
      `upgrade head` all succeed on a scratch DB.
- [ ] `uv run alembic revision --autogenerate` shows **no** further diff
      (column matches the ORM).
- [ ] contract tests green; `just check` clean.

### Phase 3 — Submission validator

Depends on Phase 1 (domain attr) for unit tests; Phase 2 for integration.
(Plan §5.)

**Red — `tests/unit/` for `registration_submission_service`:**

- [ ] `NO` field present in the POST body → ignored, not in `cleaned`, no error.
- [ ] required (`YES_REQUIRED`) checkbox unchecked (key absent / `""`) → error.
- [ ] optional (`YES_OPTIONAL`) checkbox unchecked → `False` (never `None`).
- [ ] checkbox checked (`"yes"`) → `True`.
- [ ] free-form authored radio `"no"` → `False` (value parsed, not truthy-tested).
- [ ] unexpected bool value (e.g. `"maybe"`) → error.
- [ ] optional non-bool blank → accepted, not stored; required non-bool blank →
      error.
- [ ] required choice unselected (`""`) → error.

**Green — `service_layer/registration_submission_service.py`:**

- [ ] add `_coerce_form_bool(str_value, *, required)`.
- [ ] rewrite `_validate_field_value` to be enum-aware (requiredness from the
      enum; bool branch via `_coerce_form_bool`; blank handling for non-bool).
- [ ] update `_validate_form_data` to skip `NO` fields and only store
      non-`None` cleaned values.
- [ ] gettext-wrap the new user-facing messages.

**Red/Green — `tests/integration/`:**

- [ ] `submit_registration` end-to-end against a schema mixing all three enum
      values: PUBLISHED → `POOL`, TEST → `TEST_SUBMISSION`; assert the created
      `Respondent` has correct `eligible`/`consent`/`stay_on_db`/`attributes`
      and that `NO`/optional-blank fields keep their defaults.

**Verify:**

- [ ] validator unit + integration tests green.
- [ ] `just translate-regen` run; `just check` clean.

### Phase 4 — Starter generator: checkbox + enum-driven

(Plan §3.2; depends on Phase 1.)

**Red — `tests/unit/` for `registration_page` (starter generator):**

- [ ] bool field renders an `<input type="checkbox" ... value="yes">` with the
      `checked('key','yes')` helper, **not** yes/no radios.
- [ ] `YES_REQUIRED` bool checkbox carries the `required` attribute;
      `YES_OPTIONAL` does not.
- [ ] `NO` fields are omitted entirely; a group whose every field is `NO`
      renders no `<h2>`.
- [ ] non-bool `YES_REQUIRED` gets `required`; `YES_OPTIONAL` does not (incl. the
      dropdown "— Please choose —" only on optional).
- [ ] **update existing tests** that assert yes/no radio markup → expect checkbox
      markup (these go red on the change; fix them as part of this phase).

**Green — `src/opendlp/domain/registration_page.py`:**

- [ ] add `_render_checkbox`.
- [ ] change `_render_field` to drop the `required_field_keys` param, read
      `field.on_registration_page`, skip `NO`, route bools to `_render_checkbox`.
- [ ] change `generate_starter_form_html` to drop the `required_field_keys` param
      and skip `NO` fields.
- [ ] remove `_render_yes_no_radios` (no remaining callers).

**Green — callers of the changed signatures:**

- [ ] `service_layer/registration_page_service.py` `_build_starter_html` —
      confirm/adjust the call.
- [ ] `entrypoints/blueprints/dev.py` and
      `entrypoints/blueprints/backoffice_registration.py` — update the
      `generate_starter_form_html` calls.

**Verify:**

- [ ] starter-generator unit tests green; existing registration-submission BDD
      scenarios still pass with checkbox markup.
- [ ] `just check` clean.

### Phase 5 — Schema-editor: service + blueprint + template

(Plan §6.)

**Red:**

- [ ] `tests/integration/` — `add_field` defaults a new custom field to
      `YES_REQUIRED` and persists an explicit value; `update_field` updates
      `on_registration_page` (incl. on a fixed field).
- [ ] `tests/integration/` — a freshly-seeded schema via `_build_fixed_rows`
      gives stay_on_db `YES_OPTIONAL` and the other fixed fields `YES_REQUIRED`.
- [ ] blueprint test — `_parse_on_registration_page` parses the three values and
      falls back safely on bad input; `update_field_view` forwards the value.
- [ ] `tests/e2e/test_backoffice_respondent_field_schema.py` — set a field to each
      value in the editor, save, reload, assert persisted and pre-selected.

**Green:**

- [ ] `service_layer/respondent_field_schema_service.py` — `add_field` +
      `update_field` params; `_build_fixed_rows` uses
      `FIXED_FIELD_ON_REGISTRATION_PAGE`.
- [ ] `entrypoints/blueprints/respondent_field_schema.py` —
      `_parse_on_registration_page` + wire into `update_field_view`.
- [ ] `templates/backoffice/respondent_field_schema/view.html` — per-row
      "On registration form" `<select>` (labels _("Not shown") / _("Optional") /
      _("Required")), shown for all fields incl. fixed, posting in the row's Save
      form, with an accessible label.

**Verify:**

- [ ] `just translate-regen`; integration + e2e green (`CI=true`).
- [ ] manual/Playwright sanity of the editor dropdown if useful.
- [ ] `just check` clean.

### Phase 6 — Back-office isolation pin

No production code change. (Plan §7.)

- [ ] **Red/Green** — add
      `test_edit_respondent_form_bool_is_three_state_regardless_of_on_registration_page`
      asserting `edit_respondent_form` bool fields keep Yes/No/Not-set choices
      and `radio_or_none_to_bool` behaviour even when the field is `NO` on the
      registration form.
- [ ] **Verify** — test green; no diff to `edit_respondent_form.py`.

### Phase 7 — Final verification

- [ ] full suite: `CI=true just test` green (including BDD).
- [ ] `just check` clean (mypy, ruff, `deptry src`).
- [ ] `uv run alembic upgrade head` clean; autogenerate shows no diff.
- [ ] `just translate-regen` leaves no uncommitted churn beyond the intended new
      strings.
- [ ] re-read the diff against this plan; note any deviations back into the doc.
