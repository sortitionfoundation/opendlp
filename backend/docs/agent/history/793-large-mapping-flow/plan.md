# Large-mapping set-up flow — implementation plan

**Status:** Implemented — all chunks landed on `793-large-mapping-flow` (2026-09-18)
**Date:** 2026-09-18
**Branch:** `793-large-mapping-flow` (off `793-two-step-fields`)

## 0. Scope and shape

Two pieces of refinement after `793-two-step-fields`:

1. **Chunk A:** the step-1 set-up modal for a "Map postcode to value"
   (`LARGE_MAPPING`) target turns into a two-step modal. Step 1 is the form
   as it is now. **Save** keeps the modal open and moves to step 2, which is
   the lookup-table upload. Uploading straight away is the normal path.
   Putting it off is allowed but takes a deliberate choice.
2. **Chunk B:** retire the derived-field UI in the registration questions
   editor (`respondent_field_schema` blueprint). That editor can no longer
   create or show derived fields, so its derived paths are dead code, and
   one of them still tells people to "upload the CSV from its row on the
   Fields tab", a row that is never shown.

The two chunks are independent and could land in either order. A goes first
because it is the feature.

### Decisions (agreed 2026-09-18)

1. **Nothing blocks selection yet, so the warning text must not say it
   does.** An empty lookup table sends every respondent to the fallback
   value, and selection then runs against quotas it cannot meet. The copy
   says exactly that. Actually blocking selection when a large mapping has
   no rows is a separate issue (see §4). It belongs in selection readiness,
   not in this modal.
2. **Step 1 commits.** Save runs `configure_target_source` exactly as it
   does today, and step 2 is the existing target-sources upload endpoint with
   a different footer. We rejected carrying step 1's values through as
   hidden inputs so that both steps commit in one transaction: re-rendering
   after a CSV error gets complicated, and it would change
   `configure_target_source`, for little gain.
3. **The ✕ and the backdrop stay in step 2.** A dialog must always be
   escapable. Closing step 2 amounts to "upload later" without the warning,
   which leaves the same state as today, and the checklist row still shows
   the "Upload table" button. The checkbox is a speed bump, not a gate.
4. **Step 2 only appears when the table is empty.** That covers a new
   field, or re-editing a field whose upload was put off. When the table
   already has rows, Save closes the modal as it does now, and the table is
   replaced through "Re-upload table" in the row menu.
5. **When Save leads to step 2, step 1's recompute report is not shown.**
   With an empty table the report can only say "everyone fell back", which
   is noise. The combined upload and recompute report after step 2 is the
   one that counts.
6. **"Upload later" gives a warning toast, not a success toast**, and the
   step-2 dialog says "Step 2 of 2".
7. **Scope:** only the target data sources modal. The registration
   questions editor stops dealing with derived fields altogether (Chunk B).

---

## 1. Chunk A — two-step set-up modal for a lookup-table target ✅ done

Notes from implementing it:

- The CSP Alpine build accepts a data-only inline `x-data` object (as the
  dashboard export modal already does), so the checkbox → "Upload later"
  toggle is `x-data="{ deferred: false }"` on the form, not a new component.
- "Step 2 of 2" has an id and is part of the dialog's `aria-labelledby`,
  so screen readers hear it with the title.
- The set-up modal's large-mapping hint now reads the linked field's row
  count too, which is how it knows to say saving keeps the existing table.

Files: `entrypoints/blueprints/target_sources.py`,
`templates/backoffice/target_sources/_setup_modal.html`,
`templates/backoffice/target_sources/_upload_modal.html`,
`templates/backoffice/target_sources/_checklist.html`,
`tests/component/test_backoffice_target_sources.py`, BDD.

### 1.1 Step 1 → step 2 (`configure_view`)

1. After `configure_target_source` succeeds, check whether the linked field
   (`fields[-1]`) is `LARGE_MAPPING` and
   `uow.respondent_field_mapping_entries.count_for_field(...) == 0`. Do the
   check inside the same `with uow:` block. Reading a repository from the
   entrypoint follows the existing precedent in
   `respondent_field_schema._schema_page_context`. If that feels wrong in
   review, a `mapping_row_count(uow, user_id, assembly_id, field_id)`
   service helper is the alternative.
2. If it is, respond with step 2 rather than `_saved_response`:
   - **HTMX:** render `_upload_modal.html` with `setup_step=True` into
     `#ts-modal-container`, **plus the checklist fragment out of band**. The
     row behind the modal has just changed (unconfigured → linked, 0 rows),
     and if the user closes step 2 with ✕ it must already be correct.
   - **No JS:** redirect to `upload_modal`'s URL with `?step=setup`, which
     already renders the full page with the modal open via `_render_page`.
     Flash nothing. Step 2 itself is the next thing to do.
3. Otherwise (any other method, or a table that already has rows):
   `_saved_response` as today.

### 1.2 Step 2 (`_upload_modal.html` in setup-step mode)

The upload modal gets a `setup_step` flag in `modal_ctx`, read by
`_upload_modal_response` from `request.args.get("step")` or a hidden form
input, so that a CSV error re-renders step 2 and not the plain upload
dialog.

When `setup_step` is set:

- A "Step 2 of 2" caption above the title (its own msgid; the title
  msgid stays as it is).
- The body starts with a line saying the data source is saved, so it is
  clear step 1 is not lost if they stop here.
- The body keeps the existing CSV explanation, file input and "Allow new
  output values" checkbox.
- A new **defer** checkbox (`defer_upload`), with this text:
  *"I don't have the lookup table yet and will upload it later. Until it is
  uploaded, everyone's answers fall back to '%(fallback)s' and the targets
  can't be met."* Pass `fallback` from the field's derivation config via
  `LargeMappingRule`, the same way `_setup_modal_ctx` gets it now.
- Footer: **no Cancel**. **Upload** is the primary button and comes first
  in the DOM, so pressing Enter in the form uploads. **Upload later** is a
  secondary submit button with `name="form_action" value="defer"` and
  `formnovalidate`, because the file input is `required`. It is shown with
  `x-show` on a flat `x-model` property bound to the checkbox and hidden
  with `x-cloak`. That is CSP-safe, and follows the rules in
  `templates/backoffice/patterns.html`. Without JS it stays hidden, and
  no-JS users defer by following the ✕ link, which is acceptable under
  decision 3.
- Check the dialog against `docs/agent/component_accessibility.md`: the
  checkbox is labelled, and the button that appears must not steal focus.

When `setup_step` is not set, the modal is unchanged. It is the
"Upload table" / "Re-upload table" dialog from the checklist row.

### 1.3 The defer action (`upload_view`)

- `form_action == "defer"` **and** `defer_upload == "1"`: upload nothing,
  close the modal, refresh the checklist, and show a **warning** toast:
  *"Data source saved. Until the lookup table is uploaded, everyone's
  %(key)s will be '%(fallback)s'."* Reuse `_toast_response` with the
  `"warning"` category, and check that the toast component renders it.
- `form_action == "defer"` without the checkbox (a hand-crafted post, or the
  button reached some other way) re-renders step 2 with an error. The server
  does not rely on the button being hidden.
- Otherwise the path is unchanged: upload, recompute, then the combined
  report modal via `_report_response`.

### 1.4 Copy changes

- `_setup_modal.html` large-mapping hint: replace "The lookup table starts
  empty — upload its CSV from this target's row afterwards. …" with
  something like *"After saving you'll upload the lookup table: a CSV
  pairing each %(source)s value with a target value. Values with no table
  entry fall back to %(fallback)s."* When the field already has rows, say
  that saving keeps the existing table.
- `_checklist.html`: when a large mapping has 0 rows, show the consequence
  next to the row's "0 lookup rows", in the error colour. This is the
  one-line version of the defer-checkbox warning. It takes over from the
  "0 rows — upload a lookup table" cue that Chunk B removes from the
  registration questions editor.
- Check each new string against `docs/language.md`: "lookup table",
  "target", "respondent".

### 1.5 Tests

- **Component** (`test_backoffice_target_sources.py`):
  - configuring a new large mapping returns step 2, with the out-of-band
    checklist and no recompute toast
  - re-configuring one that has rows closes the modal (existing behaviour)
  - re-configuring one with 0 rows returns step 2
  - no-JS configure redirects to `?step=setup`, and that GET renders step 2
  - defer with the checkbox gives a warning toast and 0 rows
  - defer without the checkbox gives 422 and step 2 again
  - a bad CSV in step 2 re-renders step 2, not the plain dialog
  - a good CSV in step 2 gives the report modal
  - the plain upload dialog has no step caption, no defer checkbox and
    still has Cancel
- **BDD:** one scenario for configure → upload straight away → row shows N
  lookup rows, and one for configure → tick defer → Upload later → row
  shows the warning and the "Upload table" button. Put them next to the
  existing target-sources scenarios.
- No JS unit test is needed unless the checkbox → button toggle gets its
  own Alpine component. Plain `x-model`/`x-show` doesn't need one.

---

## 2. Chunk B — retire the derived-field UI from the registration questions editor ✅ done

Notes from implementing it:

- Deleting the `type_choice == "derived"` guard in `_try_add_field` would
  have let an unrecognised type fall through to a text question, so it
  became a general check: any `type_choice` the modal does not offer gets
  "Choose a question type".
- `edit_field_modal` for a derived field answers HTMX with an `HX-Redirect`
  header (a plain redirect would load the whole page into the modal
  container) and a plain request with a 302, both with an info flash.
- The `report` mode of the registration questions page went too — only the
  retired routes produced it. `_derivation_report_modal.html` now requires
  `close_url`, which the target sources step always passes.
- `parse_derivation_rule` had no caller left and was deleted with its test.
  The parser unit tests moved to `tests/unit/test_target_source_parsers.py`;
  `test_field_schema_modal_parsers.py` keeps the option-value check.
- The two Postgres round trips in the old e2e file (age bracket; lookup
  table upload) were ported to `tests/e2e/test_backoffice_target_sources.py`
  rather than dropped, and the upload behaviours only tested on the old
  route (first-row warning, empty file, row cap, new output values) were
  ported to the target sources component tests.
- Left alone: `DERIVATION_TYPE_LABELS` and its `derivation_type_labels`
  Jinja global no longer have a template using them. They follow the
  enum-labels convention and have their own unit tests, so removing them
  is a separate decision.

### 2.1 Why it is unreachable

- The new-field modal offers no Derived type (`_question_type_choices`,
  with a comment at `_new_modal_ctx` saying so).
- The editor leaves out the DERIVED group (`_schema_page_context`, and
  `group_choices` also excludes it).
- Every derived field lives in the DERIVED group:
  - `create_derived_field` defaults to it, and `target_source_service`
    never passes a group.
  - `update_derivation_view` doesn't touch the group, and `move_field` only
    moves a field within its group.
  - The `#291` UI already on `main` had no group control on derived fields.
- So no derived field's row, edit link, "Recompute" or "Upload lookup
  table" item is ever rendered, and the `type_choice == "derived"` branches
  can only be reached by a hand-crafted request.

✅ **Guard done** — `update_field` raises `FieldDefinitionConflictError` for a
group change on a derived field.

The only way left to move a derived field out of DERIVED is a hand-crafted
POST to `update_field_view` with a `group`. Close it in the same chunk.
Either `update_field` in the service layer rejects a group change on a
derived field, or `update_field_view` ignores `group` for one. The service
layer is the better place. Then the retirement rests on an enforced rule
rather than on nobody having done it.

### 2.2 What goes

In the `respondent_field_schema` blueprint:

- **Routes:** `add_derived_field_view` (`/fields/add-derived`),
  `update_derivation_view` (`/fields/<id>/derivation`),
  `mapping_upload_modal` (`/fields/<id>/mapping-modal`),
  `mapping_upload_view` (`/fields/<id>/mapping-upload`), `recompute_view`
  (`/fields/<id>/recompute`).
- **Helpers** only these use, for example `_build_derived_ctx`, the
  derived try-add and try-update helpers, and the derived keys in the modal
  values (`derivation_method`, `source_key`, `map_source` / `map_target`,
  age fields). Confirm each one with a grep before deleting.
- **`_schema_page_context`:** `large_mapping_fields` and
  `mapping_row_counts`.
- **`_new_modal_ctx` / `_edit_modal_ctx`:** the `is_derived` / `derived`
  keys and the `type_choice == "derived"` branches in
  `_required_switch_label`, `_question_type_value` and `_try_add_field`.
- **`edit_field_modal` for a derived field:** it no longer renders the
  derived panel. It redirects to the target data sources page with a flash
  (*"Computed questions are set up on the target data sources step"*), so
  an old bookmark lands somewhere useful rather than on a 404.

Templates:

- delete `respondent_field_schema/_derived_panel.html` and
  `_mapping_upload_modal.html`
- `_field_modal.html`: remove the `is_derived_flow` logic and both derived
  panel includes
- `_editor.html`: remove the large-mapping row count, the "Derived" tag,
  and the Recompute and "Upload lookup table" menu items
- `view.html`: remove the mapping-modal include and its `modal_ctx` mode

### 2.3 What stays

- `_derivation_report_modal.html`: `target_sources` renders it too. It can
  stay where it is, or move to `target_sources/` in a separate tidy-up.
- `age_prefill_from_target`, `parse_age_rule` and
  `parse_small_mapping_rule`, which `target_sources.py` imports from this
  blueprint. Once the rest is gone, move them into `target_sources.py`,
  since that is their only caller. That is a straight move with no logic
  change.
- Every service-layer function (`create_derived_field`,
  `update_derivation`, `upload_large_mapping`, `recompute_derived_field`),
  because the target sources step uses them.
- The DERIVED group display on the backoffice registrant detail page, and
  the field-spec JSON.

### 2.4 Tests and docs

✅ Done. The explainers under `docs/explainers/` still describe older designs;
their `ABOUT.md` says they are not maintained, so they were left as they
are. `docs/respondent_field_spec.md` and `docs/language.md` describe derived
fields as data, not the editor, and needed no change.

- Delete the component and e2e tests for the retired routes: about 21 hits
  in `tests/component/test_backoffice_respondent_field_schema.py` (for
  example `test_derived_panel_lists_targets_and_filters_sources_by_method`)
  and 5 in `tests/e2e/test_backoffice_respondent_field_schema.py`. Before
  deleting each one, check that the behaviour it covers is also tested
  through `target_sources`. Where it isn't (a CSV error case, say), port the
  test rather than dropping it.
- Add tests:
  - `edit_field_modal` for a derived field redirects to target sources
  - the old derived routes return 404 (or a redirect)
  - the service layer rejects a group change on a derived field
- `just translate-regen` drops the retired msgids. `just translate-check`
  must pass.
- Search `docs/` (for example `docs/explainers/fields-and-targets.html`,
  `docs/respondent_field_spec.md`, `docs/language.md`) for anything
  describing derived fields on the Fields tab or registration questions
  editor, and fix it. Add a pointer from
  `docs/agent/793-derived-fields/plan-simple-ui.md` to this plan.

---

## 3. Suggested commit sequence ✅ done

Each lands green on its own:

1. `feat(ui)`: two-step set-up modal for lookup-table targets (Chunk A,
   tests included)
2. `fix(services)`: keep derived fields in the DERIVED group (§2.1 guard,
   with its test)
3. `refactor(ui)`: retire the derived-field UI from the registration
   questions editor (Chunk B, including the test deletions and ports)
4. `i18n`: regenerate catalogues
5. `docs`: explainer and plan pointers

Run `just check` and `just test` before each commit.

## 4. Follow-up issue (not in this branch)

**Block selection when a lookup-table target has an empty table.** Today
selection runs, with every respondent on the fallback value. The check fits
the selection readiness checks. Until it exists, the copy in Chunk A only
states the consequence and does not claim selection is blocked.
