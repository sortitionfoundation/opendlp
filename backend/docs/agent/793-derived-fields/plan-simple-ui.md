# Fields tab redesign — spike plan for an "OK UI"

**Branch:** `793-derived-fields-ui` (spike). **Scope:** rework the Fields tab so rows are
read-only summaries and all field editing happens in an add/edit modal, including the
first UI for derived fields. Backend (domain/data/service) already landed on
`793-derived-fields` — see [plan.md](plan.md) and [research.md](research.md) §9.

All open questions were reviewed and settled on 2026-09-09; each is recorded inline
as a **Decision**, and collected in §12. §11 is the implementation order.

---

## 1. The brief

- The main page stops being an editor. It keeps: which section (group) a field lives
  in, ordering within a section, adding and deleting fields, and an "Edit" button per
  field. Everything else on a row becomes a read-only summary (options as a one-line
  list, status as tags/chips).
- Add and Edit open a modal, similar to the registration-page dialogs.
- The modal's first choice is field name + type. User-facing types:
  - checkbox
  - free text (single line), with sub-types: text, email, number
  - choice of options (radios or dropdown on the form), then enter the options
  - date
  - derived — choose which **target** it feeds and which **field** it derives from
    (both must already exist), choose the derivation method, enter its config.
- Every field gets optional help text.

## 2. What exists now (the short version)

- The current tab (`templates/backoffice/respondent_field_schema/view.html`, 389
  lines) is entirely inline `<form method="post">` → flash → 302, using the
  `form="edit-field-<id>"` attribute trick to spread one form across table cells.
  There is **no JS component and no JSON layer** for this tab — just the shared
  `$confirm` and scroll-preservation helpers.
- Blueprint `respondent_field_schema.py` has routes for add / update / delete /
  move / option add–update–remove / guess-types / initialise, all calling
  `respondent_field_schema_service`. No derivation routes exist yet.
- The backend surface for derived fields is complete:
  `derivation_service.create_derived_field(...) -> (field, RecomputeReport)`,
  `update_derivation`, `recompute_derived_field`, `upload_large_mapping`,
  plus the rule classes (`AgeBracketRule`, `SmallMappingRule`, `LargeMappingRule`)
  and their `derivation_config` shapes.
- Modal machinery exists twice over:
  - **Alpine + JSON**: `controlled_modal` macro
    (`templates/backoffice/components/modal.html:129`) + flat Alpine slices +
    `lib/json-request.js`, as used by the registration asset dialogs
    (`registration-images.js` is the canonical open/submit/close example).
  - **HTMX fragments**: the `targets` blueprint pattern (form carries both a real
    `action` and `hx-post`; route branches on the `HX-Request` header; validation
    errors come back as a 422 fragment; works with JS off), plus the worked
    `json-to-htmx` spike branch and the
    [htmx-first direction doc](../frontend-architecture/htmx-first.md).
- Targets link to fields by **case-insensitive name match** between
  `TargetCategory.name` and the field's `field_key`
  (`respondent_field_spec_service.build_field_spec`). There is no foreign key.

## 3. Architecture: HTMX fragments, with Alpine only for client-only bits

**Decision (Q1): HTMX-first for this branch.** The modal is a server-rendered
fragment:

- `GET .../fields/new-modal` and `GET .../fields/<id>/edit-modal` return the dialog
  fragment into a `#field-modal-container` div; a plain (non-HTMX) request
  re-renders the whole page with the modal open, so it degrades without JS.
- Submits are real `<form method="post">` with hidden `csrf_token`, enhanced with
  `hx-post`/`hx-target`/`hx-swap`. Success returns the refreshed page section (or a
  redirect for the no-JS path); validation failure returns the modal fragment at
  422 with inline errors and the entered values echoed back.
- Reasons: it matches the htmx-first direction doc and the `json-to-htmx` spike;
  the whole thing is testable in the fast component tier (assert on fragments, no
  browser); and the derived-field form is far too dynamic for comfortable
  CSP-Alpine flat-state modelling. A spike wants the cheap path.
- Alpine stays for two genuinely client-only widgets: the age-bracket **live label
  preview** (research §9 suggests it) and nothing else — the options editor is
  HTMX too (Q7). The preview is a small registered `Alpine.data()` component with
  a vitest test, per `frontend_js_testing.md`.

## 4. The main page redesign

One section per non-empty group, as now, but each row becomes:

| Column | Content |
|---|---|
| Field | **Label** (bold) with `field_key` in `<code>` beneath; help text as a grey line below if set |
| Summary | Type label + read-only detail: for choice fields a one-line option list ("Male, Female, Non-binary, Prefer not to say"); for derived fields "Derived from `year_of_birth` · Age brackets" plus the option list |
| Tags | chips: `Fixed`, `Derived`, `Required` / `Optional` / `Not on form` |
| Section | the group `<select>` — the one bit of inline editing we keep |
| Order | ↑ / ↓ buttons, unchanged |
| Actions | **Edit** (opens modal) · **Remove** (existing `$confirm` POST; hidden for fixed fields) |

- The gsheet-source read-only branch and the "initialise empty schema" branch stay
  exactly as they are.
- Long option lists truncate ("… and 12 more") — the modal shows them all.
- Derived rows additionally get a **Recompute** action, and large-mapping rows an
  **Upload lookup table** action (§7). Row actions beyond Edit/Remove can sit in a
  small overflow area; for the spike, plain inline links/buttons are fine.

**Decision (Q2): the section select auto-submits on `change`** (`hx-post` with
`hx-trigger="change"`). The form keeps a small "Move" submit button as the no-JS
path (the `targets` blueprint convention: real `action` + `hx-*` enhancement).

**Decision (Q3): `on_registration_page` moves into the modal** and appears as a
chip on the row (derived fields show a fixed "Not on form" chip).

The "Guess field types" button stays on the main page (it is a bulk action, not a
per-field edit).

## 5. The add/edit modal — ordinary fields

Built from `controlled_modal`'s CSS atoms (`dialog-*` classes) but rendered as an
HTMX fragment like the `json-to-htmx` branch (backdrop + X are real links to the
close URL; `role="dialog"`, `aria-modal`, `aria-labelledby`, Escape via a tiny
shared behaviour or the existing macro classes).

Form contents, top to bottom:

1. **Label** (text input, required). **Field key**: on *add*, auto-generated from
   the label with `normalise_field_key`, shown as a live-updating grey hint with a
   "change" disclosure to override; on *edit*, shown read-only (there is no rename
   path in the service layer, and building one is out of scope).
   **Decision (Q4): yes** — auto-generate with override on add.
2. **Type** — a radio group of the user-facing taxonomy:

   | User choice | Sub-choice | `FieldType` |
   |---|---|---|
   | Checkbox | — | `BOOL` |
   | Free text | Text / Email / Number | `TEXT` / `EMAIL` / `INTEGER` |
   | Choice of options | Radios / Dropdown | `CHOICE_RADIO` / `CHOICE_DROPDOWN` |
   | Date | — | `DATE` |
   | Derived | (see §6) | `CHOICE_RADIO` + `is_derived` |

   **Decision (Q5/Q6): `LONGTEXT` and `BOOL_OR_NONE` are excluded from the
   picker.** `LONGTEXT` has no current use case; `BOOL_OR_NONE` only arises from
   CSV import, which the spike doesn't need to solve. When *editing* a field that
   already has one of these types (from an imported schema), it is shown as the
   selected — still selectable — value, so editing doesn't force a type change.
   "Checkbox" means `BOOL`.
3. **Choice options editor** (shown when type = choice): one row per option —
   value + optional per-option help text + remove; "Add another option" appends a
   row. Server enforces ≥1 option and the small-mapping rename/drop cascade.
   **Decision (Q7): HTMX "add another" round-trip** that re-renders the form
   fragment preserving entered values (GOV.UK add-another pattern, zero new JS).
   The existing "seed `option_1`" hack in the add route disappears — the modal
   submits real options with the field in one POST, so `add_field(options=[...])`
   gets used properly.
4. **Help text** (optional textarea) — new, see §8.
5. **On the registration form** — Required / Optional / Not shown radios (hidden
   for derived).
6. Footer: Cancel / **Save**. On success: close modal, refresh the schema section,
   toast/flash. On conflict (`FieldDefinitionConflictError` — e.g. changing the type
   of a derivation source, fixed-field edits): 422 fragment with the `_l()` message
   shown inline. `FieldDefinitionNotFoundError` messages are internal — render a
   generic "not found" message, never `str(exc)`.

Edit-mode differences: type radios disabled for fixed fields (effective type shown
with the "Fixed" explanation); the whole type/options block replaced by the
derivation panel for derived fields (§6).

## 6. The add/edit modal — derived fields

Choosing **Derived** swaps in this panel (HTMX fragment refresh on selection, since
the panel needs server data: targets, candidate sources):

1. **Target it feeds** — select over the assembly's `TargetCategory` names
   (`target_service.get_targets_for_assembly`). Choosing one fixes:
   `field_key` = normalised category name (that's how the name-match linkage works),
   `label` = category name, and the **output values** = the target's value names.
   If the assembly has no targets, the Derived option is disabled with a hint
   ("Create targets first").
   **Decision (Q8): the target is mandatory and owns key/label/outputs.** A
   target-less derived field can come after the spike.
2. **Derivation method** — radios with hint text:
   - **Age brackets** — from a date of birth or year of birth
   - **Map choices** — map each answer of an existing choice field to a target value
   - **Lookup table** — upload a CSV mapping (e.g. postcode → region)
3. **Source field** — select filtered by the chosen method's compatibility table
   (age → `DATE`/`INTEGER`; map choices → choice fields; lookup → `TEXT`), matching
   `derivation_service._COMPATIBLE_SOURCE_TYPES`. Empty → inline "no compatible
   field exists yet" hint. (The table is private today; §9 notes the small public
   helper this needs.)
4. **Method config:**
   - **Age brackets**: as-of date (GOV.UK three-part date input, pre-filled from
     `Assembly.first_assembly_date` when set, required — never "today"); min age
     (default 16), max age (default 100); boundaries entered as a comma-separated
     list ("25, 40, 60"); a live preview of the generated labels
     (`under-16, 16-24, 25-39, … 100+, UNKNOWN`) via a small Alpine component
     mirroring `AgeBracketRule.bracket_labels()`. When the source is a
     year-of-birth (`INTEGER`) field, the 1 January assumption is stated on the
     panel (research §9 constraint 3), and the copy leads with year-of-birth as the
     data-minimising choice (constraint 4).
     **Decision (Q9): always show the target's values next to the preview and
     warn on mismatch, never block.** Additionally, attempt to pre-fill the
     boundaries by parsing the target's value names (e.g. "16-24" style ranges);
     if the parse fails, leave the boundaries blank for the user to fill in.
     Mismatched outputs aren't invalid — they just count as unmatched at
     selection time.
   - **Map choices**: a static table — one row per option of the source choice
     field, each with a select of the target's values plus "(fall back to
     UNKNOWN)". Builds `SmallMappingRule.mapping`. Renames/removals of source
     options later are already cascaded by the service.
   - **Lookup table**: creation declares the outputs (from the target) and saves
     the field with an **empty** mapping table; the row then shows "0 rows —
     upload a lookup table". Fallback is fixed at `UNKNOWN` (settled in research
     review).
     **Decision (Q10): the upload is a separate row action (§7), not a step
     inside the create modal** — `upload_large_mapping` needs the field to exist,
     uploads can be 220k rows / several seconds, and a separate upload dialog
     with its own report display is simpler than a wizard.
5. **Save** calls `create_derived_field` / `update_derivation`, which recomputes the
   whole pool synchronously.
   **Decision (Q11): the modal shows the recompute report** rather than closing
   silently: total / changed / fell back to UNKNOWN, the `unmatched_sample` list
   (up to 20) for mapping rules, and a prominent warning when
   `completed_selection_runs > 0` ("this assembly has completed selections;
   recomputing changes the pool under them" — research §6). One "Done" button
   closes and refreshes.

Editing a derived field reopens the same panel with method + config populated.
Changing the **source** or the **target** of an existing derivation is out of scope
for the spike (the service's `update_derivation` only changes rule + outputs) —
delete and recreate instead; the modal says so. Method *config* edits (boundaries,
mapping, as-of date) are in scope.

## 7. Mapping upload dialog + recompute action

- **Upload lookup table** (large-mapping rows): small modal — file input, an
  "allow new output values" checkbox (maps to `allow_new_outputs`), Upload. Route
  calls `upload_large_mapping` then `recompute_derived_field`, and the modal shows
  the combined report: row count, duplicate keys, unknown outputs,
  `used_positional_headers` notice, then the recompute counts. Errors
  (empty file, > 500k rows, unknown outputs without the checkbox) are 422
  fragments with the `_l()` conflict message.
- **Recompute** (any derived row): POST → report shown the same way. Useful after
  editing source data or uploading a new table.

## 8. Backend addition: field-level `help_text`

There is currently no per-field help text (only per-choice-option). Needed:

- `RespondentFieldDefinition`: `help_text: str = ""` constructor param + `update()`
  support (plain mutable text — not derivation-owned, editable on derived fields
  too).
- ORM: `help_text` Text column, `server_default=""`; Alembic migration.
- `add_field` / `update_field` gain a `help_text` kwarg (empty-string default per
  house style).
- Field-spec JSON: add `help_text` to the field payload → `spec_version` 3→4,
  update schema, re-record fixture (`UPDATE_API_FIXTURES=1`), update
  `docs/respondent_field_spec.md`.
- **Decision (Q12): the registration starter-HTML generators emit `help_text` as a
  GOV.UK hint**, in both generators, with tests.

This slice is pure domain/data/service work, so it goes **first** in the
implementation order (§11) — it touches none of the templates the later steps
rewrite.

## 9. Routes (HTMX shape)

Extending `respondent_field_schema.py` (all under the existing prefix):

| Route | Method | Does |
|---|---|---|
| `fields/new-modal` | GET | add-field modal fragment (`?type=` re-renders on type change) |
| `fields/<id>/edit-modal` | GET | edit modal fragment |
| `fields/add` | POST | extended: options list, `help_text`; HTMX branch |
| `fields/<id>/update` | POST | extended likewise; keeps serving the row's group select |
| `fields/add-derived` | POST | `create_derived_field`; returns report fragment |
| `fields/<id>/derivation` | POST | `update_derivation`; returns report fragment |
| `fields/<id>/mapping-modal` | GET | upload dialog fragment |
| `fields/<id>/mapping-upload` | POST | `upload_large_mapping` + recompute; report fragment |
| `fields/<id>/recompute` | POST | `recompute_derived_field`; report fragment |

Existing move/delete/option routes stay (option routes may become unused by the UI
once the modal submits options wholesale — leave them; the service functions are
still the cascade owners). Every POST keeps the non-HTMX flash+redirect branch.

Parsing derivation config from the form lives in the blueprint (like the existing
`_parse_*` helpers): boundaries string → sorted ints, date parts → ISO, mapping
table rows → dict; `ValueError` from rule construction → 422 with the message.

The source-field select needs the method→compatible-types table, which is private
(`derivation_service._COMPATIBLE_SOURCE_TYPES`). Add a small public helper in
`derivation_service` (e.g. `compatible_source_fields(field_defs, derivation_type)`)
rather than importing the private table from the blueprint.

## 10. Testing

Tests per tier:

- **component** — the main tier: every fragment route (renders, validates, 422s,
  conflict messages, HTMX-vs-plain branches); extend
  `tests/component/test_backoffice_respondent_field_schema.py`. Note that many
  existing component and e2e tests assert on the *inline* editor (type selects in
  rows, option sub-row forms, the seed-`option_1` behaviour) — steps 2–3 rework
  those alongside the templates rather than keeping them limping.
- **integration** — only the new `help_text` service paths; the derivation
  services are already covered from the backend chunk.
- **e2e** — a handful of real-Postgres round-trips: add via modal, create a
  derived field, upload a mapping.
- **unit** — domain `help_text`, the blueprint config parsers (boundaries,
  date parts, mapping rows).
- **vitest** — the age-preview Alpine component.
- **BDD** — extend `features/respondent-field-schema.feature`: add a field
  through the modal; create an age-bracket derived field and see the recompute
  report; derived row is read-only. The existing "move a field up" scenario
  stays valid.
- Field-spec fixture re-recorded at v4.

## 11. Implementation order

Each step ends green (`just check` + relevant test suites) and committed.
Run `just translate-regen` in any step that adds user-facing strings.
Regenerate `../.secrets.baseline` if test edits shift flagged line numbers.

### Step 1 — `help_text` backend slice ✅ DONE

Domain/data/service only; no template changes (per review: migration work first).

1. Domain: `help_text: str = ""` on `RespondentFieldDefinition.__init__` and
   `update()`; unit tests.
2. ORM column (`Text`, `server_default=""`) + Alembic autogenerate migration
   (hand-check the generated file); round-trip upgrade/downgrade.
3. Service: `help_text` kwarg on `add_field` / `update_field`; integration tests.
4. Field-spec v4: serialise `help_text`, bump `SPEC_VERSION`, update the JSON
   Schema, re-record the fixture, update `docs/respondent_field_spec.md`.
5. Starter HTML: emit the hint in both generators (GOV.UK hint pattern), with
   tests.

Commit: `feat(793): add field-level help text`

### Step 2 — main page becomes read-only rows ✅ DONE (landed with step 3 in one commit)

1. Rewrite the editor branch of `view.html`: summary rows per §4 (label + key +
   help text, type/options summary with truncation, chips), section select with
   `hx-trigger="change"` auto-submit plus the no-JS "Move" button, ↑/↓ and Remove
   unchanged. The `#field-modal-container` div lands here, empty. Edit buttons
   arrive with their routes in step 3.
2. The old inline add-field form is replaced by a single "Add a field" button
   (dead until step 3 — acceptable mid-branch, but steps 2 and 3 should merge to
   `main` together).
3. Rework the component/e2e/BDD assertions that relied on inline selects and
   option sub-rows; keep the group-move and delete tests.

Commit: `refactor(793): read-only field rows on the Fields tab`

### Step 3 — add/edit modal for ordinary fields ✅ DONE

1. Fragment templates: modal shell (from the `dialog-*` atoms, `json-to-htmx`
   style), form partial, options add-another partial.
2. Routes: `GET fields/new-modal` (with `?type=` re-render) and
   `GET fields/<id>/edit-modal`; full-page fallback renders `view.html` with the
   modal open.
3. Extend `POST fields/add` / `fields/<id>/update`: type taxonomy parsing
   (checkbox/free-text subtypes/choice/date), wholesale options list,
   `help_text`, `on_registration_page`, auto-generated field key with override;
   HTMX branch returns refreshed content or a 422 modal fragment; drop the
   seed-`option_1` hack.
4. Edit-mode guards: fixed fields (type disabled), excluded legacy types shown
   but not forced away (Q5), conflict errors inline.
5. Component tests for every branch; a couple of e2e round-trips.

Commit: `feat(793): add and edit fields in a modal`

### Step 4 — derived-field flow ✅ DONE (create + edit landed in one commit)

1. Public helper for source compatibility in `derivation_service` (§9); unit
   test.
2. Derived panel fragments: target select (disabled state when no targets),
   method radios, filtered source select, per-method config partials.
3. Age config: three-part date input (pre-fill `first_assembly_date`), min/max,
   boundaries input, boundary pre-fill parsed from target values (blank on
   parse failure), mismatch warning panel, 1-January copy for `INTEGER` sources;
   the live-preview Alpine component + vitest.
4. Map-choices config: source-option → target-value table.
5. Lookup-table config: outputs from target, creates with an empty mapping
   table.
6. Routes: `POST fields/add-derived`, `POST fields/<id>/derivation`; blueprint
   parsers for boundaries/date/mapping; recompute-report fragment (shared with
   step 5) including the completed-selections warning.
7. Component tests per method + parser unit tests + one e2e create.

Commits: `feat(793): create derived fields from the modal` then
`feat(793): edit derivation config` (split if the step runs long).

### Step 5 — lookup-table upload and recompute actions ✅ DONE

1. `GET fields/<id>/mapping-modal` + `POST fields/<id>/mapping-upload`
   (upload then recompute, combined report) + `POST fields/<id>/recompute`.
2. Row actions: "Upload lookup table" (large-mapping rows, with the
   "0 rows" nudge), "Recompute" (all derived rows).
3. Component tests for the error catalogue (empty file, row cap, unknown
   outputs vs `allow_new_outputs`); e2e upload round-trip.

Commit: `feat(793): lookup table upload and recompute from the Fields tab`

### Step 6 — BDD, translations, polish ✅ DONE

All six steps are implemented and committed on `793-derived-fields-ui`
(2026-09-09). One pre-existing BDD failure is unrelated to this work:
`tests/bdd/test_replacement_selection.py::test_replacement_modal_shows_loading_state`
fails identically on the pre-spike commit `df2c6271` (spinner-visibility race).

1. BDD scenarios per §10; update `delete_all_except_standard_users()` only if
   new tables appeared (none expected).
2. `just translate-regen` sweep; chip/summary styling pass; check the patterns
   page needs no update (the modal is a fragment, not a new Alpine pattern).
3. Full `just test` + `just check` run.

Commit: `test(793): BDD coverage for the fields modal and derived fields`

## 12. Decisions collected (settled 2026-09-09)

| # | Question | Decision |
|---|---|---|
| Q1 | HTMX fragments vs Alpine+JSON for the modal | HTMX for this branch |
| Q2 | Section select saving | auto-submit on change, Move button as no-JS path |
| Q3 | Move `on_registration_page` into the modal | yes |
| Q4 | Auto-generate field key from label on add, with override | yes |
| Q5 | `LONGTEXT` / `BOOL_OR_NONE` | excluded from the spike picker; shown when editing an existing field of that type |
| Q6 | "Checkbox" maps to | `BOOL` |
| Q7 | Options editor mechanics | HTMX add-another round-trip |
| Q8 | Target mandatory for derived fields; owns key/label/outputs | yes |
| Q9 | Age labels vs target values | always warn on mismatch; attempt boundary pre-fill from target values, blank if unparsable |
| Q10 | Large-mapping upload placement | separate row-action dialog |
| Q11 | Recompute report display | in-modal before closing |
| Q12 | Starter HTML renders `help_text` as GOV.UK hint | yes |
