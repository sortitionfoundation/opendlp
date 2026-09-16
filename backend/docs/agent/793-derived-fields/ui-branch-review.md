# Review of `793-derived-fields-ui` against `main`

Reviewed 2026-09-16 with `/sf-code-review`, against [plan-simple-ui.md](plan-simple-ui.md)
(written before the branch) and [ui-notes.md](ui-notes.md). Line numbers refer to the
branch at commit `08a1e17b`.

## Summary

The branch matches the plan closely. All twelve decisions are implemented, all seven
ui-notes are resolved as claimed, and the "left alone" list really is left alone. Config,
build wiring, JSON schemas, fixtures, migrations and the secrets baseline are untouched.
Transaction boundaries, domain purity, structlog usage, PII handling and the uploaded-CSV
retention rule are all clean.

The problems are concentrated in the blueprint's modal error paths and in a few places
where the UI's wholesale submit bypasses cascades the service layer relies on.

## Must-fix

1. **Modal POST error paths can 500.** Every modal POST route re-renders through
   `_schema_page_context`, which calls `get_assembly_with_permissions`, with no handler
   around it. The inner `_try_*` helper catches `InsufficientPermissions` and returns a
   friendly message, then the re-render raises the same exception uncaught. Triggers: a
   user whose assembly role is removed while the modal is open, or an admin POSTing to a
   deleted assembly. The GET modal routes handle this correctly, so it is an omission.
   `respondent_field_schema.py:902` (`add_field_view`) and the same shape in
   `add_derived_field_view`, `update_derivation_view`, `update_field_view`,
   `mapping_upload_view` (via `_fail`) and `_report_response`.

2. **Age prefill rewrites stored config when editing.** `_apply_age_prefills`
   (`respondent_field_schema.py:519`) fires whenever the boundaries string is blank, and
   `_edit_modal_ctx` reaches it through `_build_derived_ctx`. A saved rule with min 16,
   max 100 and no boundaries reopens showing values parsed from the target (e.g. max 40,
   boundaries 25 for a target `16-24, 25-39, 40+`). Pressing Save persists them and
   recomputes the pool. The prefill should only run for a new field.

3. **Renaming an option in the modal silently drops it from small mappings.** The modal
   submits options wholesale (`update_field(options=...)`), so the service sees a rename
   as remove + add and `_drop_small_mapping_keys` deletes the row. Respondents who gave
   the old answer fall to UNKNOWN on the next recompute. The rename cascade in
   `update_choice_option` is no longer reachable from the UI. Either carry option
   identity through the form (a hidden original value per row) or report the dropped
   keys in the response.

4. **New HTMX modals lack the modal accessibility contract.** `_field_modal.html`,
   `_derivation_report_modal.html` and `_mapping_upload_modal.html` hand-roll the
   `dialog-*` markup with no Escape handling, no focus move into the fragment, no focus
   return, no trap. The existing HTMX modal in `respondents/export_modal.html` wraps the
   `modal()` macro (`x-data="modal({ initialOpen: true })"`) and gets all of this free.
   The full-viewport backdrop is also a focusable link named "Close", first in tab order.
   See `docs/agent/component_accessibility.md`, Modal.

5. **Enum labels mapped by `if/elif` chain in a template.** `_editor.html:93-100` maps
   `on_registration_page.value` to three `_()` strings. `docs/translations.md` names this
   as the defect that drops the next enum member. `DerivationType` labels are built in
   the blueprint (`_derivation_type_labels()`) and duplicated in `_build_derived_ctx`.
   Both want a `_l()` labels dict beside the enum in the domain, exposed to Jinja, with
   the parametrised "every member has a label" test that `FIELD_TYPE_LABELS` and
   `GROUP_LABELS` already have.

## Should-fix

6. **"Derived" submitted to the plain add route creates a TEXT field.**
   `_field_type_from_taxonomy` falls through to TEXT for `type_choice == "derived"` and
   `_try_add_field` accepts it. Reachable with JS off (the noscript refresh button is
   optional) or if the HTMX re-render is slow.
7. **Duplicate option values accepted.** `_submitted_options` does not dedupe; two `Male`
   rows save, then collide as hidden `map_source` keys in the mapping table and emit
   duplicate radios in the starter HTML.
8. **As-of year has no sanity range.** `parse_age_rule` accepts year `99`, stores
   `0099-05-13`, and every respondent becomes UNKNOWN. `validate_date_field` in
   `domain/validators.py` already has the year check.
9. **Untranslated domain `ValueError` text shown to users.** `_try_update_field` returns
   `str(e)` for messages like "options must be None for non-choice field types". New on
   this branch (`main` did not catch `ValueError` there). Translate at source as
   `respondent_derivation.py` now does, or map to a generic `_()` message.
10. **Editing a small mapping after the target was renamed shrinks its options.**
    `_try_update_derivation` looks the target up by `field.field_key`; if missing,
    `output_values=None` and the options are rebuilt from mapped values only.
11. **CSRF token in GET query strings.** `hx-include="closest form"` on the refresh
    `hx-get` (`_field_modal.html:10`, `_derived_panel.html:7`) sends the token and the
    whole form in the URL. Fix with `hx-params="not csrf_token"`.
12. **Up to five `with uow:` blocks per modal request** (`_matching_choice_target`,
    `_assembly_has_targets`, `_build_derived_ctx`, `_schema_page_context` twice). The
    convention is one per request. Pre-existing pattern (`view_schema` had two on
    `main`), but the branch multiplies it. Suggested shape: the route opens the uow and
    the context builders take it.
13. **Business logic in the blueprint.** `age_prefill_from_target` is the inverse of
    `AgeBracketRule.bracket_labels()` and will drift if they live in different layers.
    The case-insensitive target-name join and "field key is the target name verbatim"
    rule are domain rules duplicated from the field-spec service.
14. **Row cap checked after parsing the whole upload** into memory. `itertools.islice`
    would make the cap cheap. Related: recompute and a 220k-row upload run synchronously
    inside a request against a 60 second gunicorn timeout. The plan accepted "several
    seconds"; worth a doc line or a row-count guard before the pool grows.
15. **Wording.** New strings say "form" (`Not on form`, `Shown on the form as`) where
    the glossary says "registration page"; the radio legend on the same screen already
    says "On the registration page". The "Remove" button deletes the definition while
    the new derived-panel copy says "delete this field and create it again" (pre-existing
    wording, but the branch now contradicts itself). Hand-built plurals:
    `%(count)d lookup rows`, `%(count)d completed selection run(s)`; use `ngettext`.
    Trailing full stops on two single-sentence upload errors. Two rewords discarded
    Hungarian translations for marginal gain: "On registration page" gained an article,
    "Field Type" became "Type".
16. **Hand-rolled components.** Error/warning banners where `alert()` exists; raw `✕`
    glyph where `dialog_close_icon()` exists; static `style=` widths and `display: none`
    where Tailwind classes exist (`docs/frontend_security.md`, Styling).
17. **JS preview diverges from the server.** `age-bracket-preview.js` shows nothing when
    min/max are blank while `parse_age_rule` defaults them to 16/100; JS accepts
    `min_age = 0` while `AgeBracketRule` rejects it. Neither corrupts data.

## Nits

- `_l()` used for a runtime-built label at `respondent_field_schema.py:346`; the file's
  convention is `_()` inside functions.
- `help_text` is stripped on create but not on update.
- `_derivation_report_modal.html:71` hardcodes `limit=20` instead of `UNMATCHED_SAMPLE_SIZE`;
  line 60 hardcodes "UNKNOWN" in a msgid while sibling strings pass `%(fallback)s`.
- Double quotes round placeholders in `_field_modal.html:178,186`; `docs/language.md`
  says single quotes.
- `<th>` without `scope="col"` in `_editor.html:41-46`.
- Prefill also overwrites user-typed min/max in *new* mode when boundaries are blank and
  the source select changes.
- `create_derived_field` duplicate check is exact-match while the target join is
  case-insensitive, so `Gender` + existing `gender` yields two fields matching one target.
- Hardcoded English `Day`/`Month`/`Year` in the generated public registration form
  (`registration_page.py:515,617`). Follows existing precedent (`Please select...`)
  because the sandboxed environment has no `_`; a known gap, not fixable in isolation.
- Server data reaches the preview via `data-target-values='{{ ... | tojson }}'`. Safely
  escaped, but a third route beside the two `docs/frontend_build.md` sanctions.

## Test gaps

No test was lost; the six removed inline-editor tests each have a replacement.

- `tests/component/test_backoffice_respondent_field_schema.py:513` is tautological: the
  second disjunct passes whenever any radio on the page is checked.
- Nothing renders the `completed_selection_runs > 0` warning or the `unmatched_sample`
  list in the report modal, though `FakeSelectionRunRecordRepository` supports seeding.
- No modal-path 422 test for `FieldDefinitionConflictError` on edit
  (`test_relabel_a_source_field_via_the_modal` asserts only the absence of the message).
- No permission-denied test on any new route. A parametrised test with a read-only user
  would have caught must-fix 1.
- The plain, no-JS branches of the report and mapping modals (`view.html` `mode="report"`
  and `mode="mapping"`) are rendered by no test.
- e2e is short of the "one Postgres smoke per route" rule for `derivation`, `recompute`
  and `mapping-modal`.
- Map-choices rows rendering is untested (only the finished POST is).
- Edit-mode guards asserted only via POST, not render (fixed field shows "Fixed" with no
  type radios; derived field has no type radios).
- Field-key override on add and server-side `mismatch_labels` untested.
- `age-bracket-preview.test.js` lacks boundary-at-min, boundary-at-max, max <= min and
  zero-age cases.
- Minor: `value="16"` asserted against the whole fragment (collides with a day input on
  the 16th); `assert "disabled" in body` unanchored; `_base()` duplicated in four classes.

## Deviations from the plan to confirm as deliberate

- **Q8:** the derived field key is the target name verbatim, not `normalise_field_key`.
  The BDD scenario asserts a key `"age bracket"` with a space.
- **Q4:** the key override is a `<details>` disclosure, not a live-updating grey hint.
- HTMX success paths return no flash/toast. The report routes (`add-derived`,
  `derivation`, `mapping-upload`, `recompute`) respond to a non-HTMX POST with a 200 page
  rather than a redirect, so a browser refresh re-runs the recompute.
- "Copy options from target" was added and is not in the plan.
- "Derived option disabled with hint" is implemented as omitted from the picker plus a
  hint.

## Checked and clean

- No `with uow:` wraps `render_template`; the upload is read and decoded outside the
  block. No `except Exception`, no new `contextlib.suppress`, no `commit_and_reset()`.
- Every `str(e)` in a response body is on `FieldDefinitionConflictError` (`CuratedMessage`)
  or a `_()`-translated `ValueError` from `parse_derivation_rule`, except should-fix 9.
  `FieldDefinitionNotFoundError` is mapped to a generic message.
- Domain files import nothing from Flask/SQLAlchemy. `_()` in `AgeBracketRule.__post_init__`
  is correct (evaluated at raise time, matching `domain/validators.py`).
- Uploaded CSV never persisted; `unmatched_sample` rendered only, not logged or stored.
- All `var(--...)` tokens exist; no inline `<svg>`; no JS under `static/`; no inline
  `<script>`; no CDN scripts; `ageBracketPreview` is registered and bundled via the
  existing entry point; CSP-Alpine expressions are compliant.
- Every form carries `method="post"` + `action` + `csrf_token` plus `hx-*`; 422 fragments
  swap via `htmx-422-swap.js`; the section select has the no-JS Move button.
- No `Enum.value` rendered as output; no lone `%`; placeholders well-formed.
- `.secrets.baseline` needs no change; no migrations; no conftest delete-list updates.
- Tier placement per `docs/testing.md` is right throughout; no `print`, `sleep` or
  hand-typed API payloads.

## Suggested cut before merge

Must-fix 1, 2 and 3 are real data or availability bugs. 4 and 5 are documented house
rules. Add the permission-denied test that would have caught 1.
