# Code review: `793-two-step-fields` vs `main`

Reviewed 2026-09-18 against the checklist in `.claude/skills/sf-code-review`.
Five parallel reviewers (Python/architecture/transactions, tests,
templates/a11y/tokens, i18n/language, JavaScript); findings 1 and 3 were then
re-checked by hand.

**How much to trust this:** apart from three Vitest files and the two unit guard
tests (`test_icons.py`, `test_design_tokens.py`) - all green - no tests were run.
Every runtime claim ("returns a 500", "prompts twice") comes from reading the
code, not from reproducing it. The tests reviewer read the target-sources
blueprint, service and tests in full, but only the diffs and test outlines for
the respondent-field-schema and targets code, so coverage gaps there may have
been missed.

All paths are relative to `backend/`.

## Fix before merge

### 1. `data-confirm` regression on legacy pages (confirmed by hand)

> **Done.** Form-level `data-confirm` is handled on the `submit` event (skipping
> forms that HTMX submits); the click handler matches only
> `button[data-confirm], a[data-confirm]`. Tests added for both paths, the
> `_checklist.html` comment corrected, and `docs/frontend_security.md` updated.
> Still worth a manual browser check after a rebuild: the unlink button inside
> the `hx-post` form at `_checklist.html:140`, and the six legacy form-level
> confirms, which now prompt where on main they never did.

`src/js/init/document-actions.js:33` changed from `e.target.dataset.confirm` to
`e.target.closest("[data-confirm]")`. The motive is sound - a click often lands
on a button's label span - but several legacy templates put `data-confirm` on
the `<form>`, not the button:

- `templates/profile/2fa_settings.html:100`
- `templates/admin/user_view.html:122`
- `templates/profile/view.html:54,88,139`
- `templates/gsheets/manage_tabs.html:71`

On main these forms never prompted at all (the click target was the button,
which has no `data-confirm`), so the change does fix something. But now *any*
click inside the form prompts. The clear victim is `2fa_settings.html:100-117`,
where the form also holds the TOTP code input and its label: clicking into the
code field pops "Are you sure you want to disable two-factor authentication?",
and clicking the label prompts twice (the label click dispatches a synthetic
click on the input).

No other handler covers form-level `data-confirm` - `form-confirm.js` is the
Alpine `$confirm` magic, a separate mechanism. `utilities.js` loads from both
`templates/base.html` and `backoffice/base.html`, so this reaches public and
legacy pages.

Options:

- handle form-level `data-confirm` on the `submit` event, which is what
  `docs/frontend_security.md` actually shows; or
- when the matched element is a `<form>`, confirm only if the click was on a
  submit control.

Also:

- `document-actions.test.js` only covers a button carrying `data-confirm`. Add a
  case for a form carrying it with a non-submit child clicked.
- The comment at `templates/backoffice/target_sources/_checklist.html:77-79`
  ("data-confirm, which reads the click target, sees the button itself") is now
  false.

### 2. Uncaught exceptions that become 500s

`flask_app.py` has handlers for 404, 500, 403, 413 and CSRF only - nothing for
`InsufficientPermissions`, `AssemblyNotFoundError` or `ServiceLayerError`.

- **`target_sources.py:636` (`recompute_view`) and `:694` (`upload_view`)** call
  `_linked_field_id()` *before* their `try`. It runs `target_source_status`,
  which raises `InsufficientPermissions` / `AssemblyNotFoundError`. A read-only
  user or a bad assembly id POSTing to either gets a 500 rather than the
  dashboard redirect. Their `try` blocks (`:640-648`, `:719-722`) also omit
  `NotFoundError`.
- **`configure_view:575`** renders the error modal from inside an `except`
  handler. `_render_setup_modal` -> `_page_context` runs the permission check,
  and `_setup_modal_ctx` raises `NotFoundError` for a foreign category. A
  `ValueError` from `_parse_setup_spec` is raised before any permission check,
  so an unauthorised user posting an invalid form hits `InsufficientPermissions`
  inside the handler. Nothing leaks - the check still runs before anything
  renders - but it is a 500.
- **`resync_view:617`** does not catch the `ValueError` that `rule_from_field`
  can raise for a config that no longer parses (`_stale_for_derived` in the same
  service acknowledges that it can).
- **`targets_legacy.py:277,324`** - `update_target_category` and
  `delete_target_category` now raise `TargetLinkedError` for a linked category.
  `edit_category` catches `(ValueError, NotFoundError, InsufficientPermissions)`
  and `remove_category` catches `(NotFoundError, InsufficientPermissions)`, so
  it escapes both. The legacy UI is still registered and has no way to force
  the change. `FieldDefinitionConflictError` from `rename_derived_field` escapes
  `edit_category` the same way.
- **`targets.py:492-505` (`save_all`)** has no clause for the curated
  `FieldDefinitionConflictError` ("A question named ... already exists") raised
  during a forced rename. It falls into the blanket `except Exception`: the user
  sees the generic "An error occurred" and the event is logged as unexpected
  with a traceback. The rollback is still correct.

### 3. Two paths bypass the linked-target guard (confirmed by hand)

`update_target_category` / `delete_target_category` refuse a linked category,
but two bulk paths call `uow.target_categories.delete_all_for_assembly` with no
guard:

- `target_service.delete_targets_for_assembly` (`target_service.py:682`)
- `target_csv_import.import_targets_from_csv` with `replace_existing`
  (`target_csv_import.py:180`)

On Postgres the FK's `ON DELETE SET NULL` (`adapters/orm.py:638`) nulls the link
and leaves a derived field with no target - the state commit 98ea3e4e ("never
leave a computed question behind with no target") set out to prevent. The fake
repository leaves a dangling ID instead, so the two backends diverge.

No test covers the column at database level: `TestTargetLinkedGuardWrites`
(`tests/integration/test_target_service.py:1472+`) asserts only on in-session
objects after `flush()`, never commits and reloads, and never checks `SET NULL`.
`tests/integration/test_create_assembly_persistence.py:120` is the pattern to
copy.

### 4. Authorisation is not tested

- `tests/component/test_backoffice_target_sources.py` uses `logged_in_admin`
  throughout. All nine routes have `except InsufficientPermissions` /
  `except NotFoundError` redirect branches that nothing exercises - which is how
  finding 2's first bullet went unnoticed.
- At unit level, `TestPermissions`
  (`tests/unit/test_target_source_service.py:675-691`) covers only
  `configure_target_source` and `target_source_status`. `adopt_field`,
  `resync_from_target` and `unlink` have no permission test.
- No test creates a second assembly. The guards exist and look right
  (`field.assembly_id != assembly_id` in `_resolve_source_field`,
  `_configure_exact_copy`, `adopt_field`; `category.assembly_id != assembly_id`
  in `_get_category`, `unlink`), but the only "wrong ID" tests use a random
  `uuid4()`. Deleting the `assembly_id` half of any guard would break no test.

This is the masking problem the TODO in `docs/testing.md` warns about.

## Medium

### Python / architecture

- **`str(e)` reaches the page.** `target_sources.py:575,600,618,645,720` flash or
  render `str(e)` for `FieldDefinitionNotFoundError`, which does not mix in
  `CuratedMessage`. Its messages are untranslated f-strings with internal UUIDs
  ("Field {id} not found in assembly {id}"). `:470`'s
  `uuid.UUID(values["reuse_field_id"])` lets "badly formed hexadecimal UUID
  string" through to the modal via `:575`; `:575` also surfaces bare domain
  `ValueError`s (`domain/respondent_field_schema.py:364,366,396,400`). These are
  HTML responses, so the JSON rule is not broken, but it is the same class of
  leak. `adopt_view:600` shows the right shape - it swaps `ValueError` for a
  wrapped string. The pattern exists on main; the branch widens it.
- **Several `with uow:` blocks per request**, against "exactly one context
  around the work of that request" in `docs/architecture.md`:
  - `setup_modal` opens three (`:551` status, `:289` `_setup_modal_ctx`, `:196`
    `_page_context`);
  - `configure_view` opens two on success and three on the error path;
  - `recompute_view` / `upload_view` resolve `field_id` in one transaction and
    write in another - a time-of-check/time-of-use gap;
  - `_schema_page_context` already opened two and now does more in each;
    `_edit_modal_ctx` adds a third via `_linked_target_name`.
  The reads can disagree: a checklist rendered from a later snapshot than the
  modal.
- **`_setup_modal_ctx` (`target_sources.py:288-297`) reads repositories directly
  with no permission check of its own.** Safe today only because every caller
  then calls `_page_context`; a future caller that skips it is an IDOR. It also
  holds business logic (candidate computation, `_exact_reuse_candidates`,
  staleness, prefills) that belongs in `target_source_service`.
  `_linked_target_name` (`respondent_field_schema.py:477-484`) is the same
  pattern, smaller.

### i18n / language

- **Enum `.value` in a user message.** `target_source_service.py:285`:
  `_l("A '%(type)s' field cannot feed this kind of derivation",
  type=spec.field_type.value)` - the user sees "A 'choice_radio' field...". Use
  `FIELD_TYPE_LABELS[spec.field_type]`.
- **`.value` as a template fallback, and a second labels dict.**
  `_checklist.html:34`:
  `method_labels.get(status.field.derivation_type.value, status.field.derivation_type.value)`
  - a future `DerivationType` member falls through to the raw token.
  `method_labels` comes from `_method_options()` (`target_sources.py:79-84`), a
  blueprint-local dict keyed by `.value`; `docs/translations.md` asks for the
  dict to live beside the enum. One enum now has two sets of English:

  | `DerivationType` | domain `DERIVATION_TYPE_LABELS` | blueprint `_method_options()` |
  | --- | --- | --- |
  | `AGE_BRACKET` | Age brackets | Age ranges |
  | `SMALL_MAPPING` | Map choices | Map more options to fewer |
  | `LARGE_MAPPING` | Lookup table | Map postcode to value |

  The fields editor (`_editor.html:136`) shows the domain set and the checklist
  shows the blueprint set, for the same field.
- **`FieldType` has the same split.** `respondent_field_schema.py:186-213`: the
  type dropdown offers "Radio" / "Dropdown"; the table column shows
  "Choice (radios)" / "Choice (dropdown)" from `FIELD_TYPE_LABELS`.
- **"registration form"** in new strings; the glossary says "registration page":
  `_checklist.html:31`, `_setup_modal.html:130,150`, `registration/_hub.html:47`,
  `target_sources/view.html:54`. (`_setup_modal.html:142` "Label on the form
  (optional)" is borderline.)
- **Remove vs delete.** The guide says Delete destroys data.
  `_checklist.html:121,123,142` ("Remove the computed question ...? Its answers
  ... are deleted", button "Remove computed question") and `target_sources.py:740`
  ("Computed question removed") destroy answers and the lookup table, so should
  say Delete. `targets_force_unlink_confirm.html:41` gets it right.
  `respondent_field_schema_service.py:695` ("rename or remove it first") has the
  same issue.
- **"Computed question" is not in `docs/language.md`**, and the branch's own
  addition to the guide says "a derived field computed from a question". The UI
  now mixes "computed question" (checklist, confirm page), the "Derived" tag and
  "Derived from %(source)s" (`_editor.html:135,237`), and "is derived" in service
  errors. Pick one and record it in the glossary.

### Templates / accessibility

- **Row-actions menu is not a full APG menu button**
  (`_checklist.html:79-141`, `_editor.html:126-190`,
  `src/js/components/row-actions-menu.js`). Present: `aria-haspopup="menu"`, bound
  `aria-expanded`, `aria-controls`, `role="menu"`/`menuitem`, `role="none"` on
  wrapper forms, click-outside, Escape closes and returns focus and is stopped
  from reaching `dialog-escape.js`. Missing: focus into the menu on open,
  ArrowUp/Down/Home/End, roving tabindex (every item is a Tab stop), closing when
  focus tabs out, focus management after click-outside. This matches
  `dropdown_button.html`, but `component_accessibility.md` requires arrow keys and
  roving tabindex for menus and asks for deviations to be documented with a
  rationale; the template comments only say "same behaviour as dropdown_button".
  `role="menu"` tells screen-reader users arrow keys work. Either add the key
  handling (with tests) or drop the menu roles.
- **`_editor.html:180`** - the Remove form inside `role="menu"` is missing
  `role="none"`. Siblings at `:143,154,165` have it, and the comment at `:140`
  explains why it is needed.
- **HTMX fragment dialogs do not manage focus** (`_setup_modal.html`,
  `_upload_modal.html`, `_field_modal.html`, `_step_dialog.html`). The ARIA is
  right and Escape works, but:
  - nothing moves focus into the dialog after the `hx-get` swap (the only
    `htmx:afterSwap` listener, in `progress-modals.js`, serves progress modals);
  - the step dialog behind a fragment modal is not inert, so Tab reaches the
    checklist underneath (`page_takeover`'s `inert` covers header/main/footer
    only);
  - focus does not return to the row's button on close - the OOB swap replaces
    the whole list;
  - every `hx-trigger="change"` refresh in `_setup_modal.html:11` re-swaps the
    modal and drops focus from the control just changed. Keyboard users lose
    their place on each choice - the most user-visible of these;
  - the first focusable element is the full-screen backdrop
    `<a aria-label="Close">` (`_step_dialog.html:20-22`), so screen readers
    announce two "Close" links.
- **`dialog-escape.js:13-22`** - the window-level Escape handler never checks
  `event.defaultPrevented` or `event.isComposing`; the only opt-out is
  `stopPropagation`. Components listening with `@keydown.escape.window`
  (`dropdown_button.html:47`, `account_menu.html:35`, the Alpine modals in
  `modal.html`) cannot stop it, so one Escape would close them *and* navigate
  away from the step. None sits inside a step dialog today - latent. A stray
  Escape also discards unsaved input in the setup and field modals; same as a
  backdrop click, so a design choice, but Escape is pressed by accident far more
  often. Native `<dialog>` is not involved; HTMX-swapped content is handled
  correctly (the query runs at keypress time); "last in the DOM is topmost" holds
  today and `_step_dialog.html:11-13` documents the assumption.
- **Hand-rolled markup where components exist.**
  - `_setup_modal.html:12-23`, `_upload_modal.html:9-20`, `_field_modal.html`
    and `_step_dialog.html` write `.dialog-header/body/footer` by hand;
    `components/modal.html` provides `dialog_header`, `dialog_body`,
    `dialog_footer`.
  - Error banners are raw divs (`_setup_modal.html:33-38`,
    `_upload_modal.html:30-35`) with no `role="alert"`/`aria-live` and nothing
    tying the error to the input; `alert(variant="error")` exists.
  - `registration/_step_form.html:22-29` hand-rolls a warning banner in a file
    that already imports `alert`.
  - Info cards at `target_sources/view.html:37-49` and
    `respondent_field_schema/view.html:38-44` are hand-rolled.
  - The "✕" close link and error div already exist on main in `_field_modal.html`,
    so the branch copies rather than invents them.
- **Text glyphs instead of icon macros.** `✕` at `_setup_modal.html:22`,
  `_upload_modal.html:19`, `_field_modal.html:45` (`_step_dialog.html:32`
  correctly uses `dialog_close_icon()`); `✓`/`✗` at `_checklist.html:31-43`, read
  out as "check mark" / "ballot x". `test_icons.py` cannot catch these - they are
  not `<svg>`.
- **`_field_modal.html:99`** - `govuk-tag govuk-tag--green` has no styling in the
  backoffice (`backoffice/base.html` loads only the Tailwind `main.css` and the
  tokens; `.govuk-tag` lives in `src/scss/application.scss`). The "Feeds target"
  tag renders as plain bold text. Main used `govuk-tag--grey` in the same spot,
  so the habit is inherited, but the line is new.

### Tests

- **Untested error branches in `target_sources.py`:**
  - `adopt_view` with a malformed/missing `field_id`, and with a name-mismatch
    conflict;
  - `resync_view` error flash (age-bracket refusal, no linked field);
  - `recompute_view` / `upload_view` with nothing linked;
  - `_upload_modal_response` when the linked field is not derived;
  - `upload_view` on `UnicodeDecodeError`, on the 422 conflict, and with
    `allow_new_outputs=1` (grep for `UTF-8` / `allow_new_outputs` in the component
    tests finds nothing);
  - `setup_modal` with an unknown category;
  - `unlink_view` deleting a derived field ("Computed question removed") - BDD
    only;
  - `_parse_setup_spec` for a small mapping with no source selected.
- **`test_unknown_category_404s_politely`**
  (`test_backoffice_target_sources.py:676`) asserts only `status_code == 302`. A
  successful unlink and a permission-denied response also return 302, and the
  name says 404. Assert the redirect location and/or the flash.
- **Service-layer unit gaps in `target_source_service.py`:**
  `_configure_exact_copy` refusing a derived field; `_resolve_source_field` with
  an empty key or a non-existent reuse ID; `_stale_for_derived` when the config
  no longer parses; `_relink` via `adopt_field`; `rename_derived_field` keeping a
  custom label.
- **`delete_derived_field` / `rename_derived_field` reassign
  `respondent.attributes`** "so the JSON column change is detected" - SQLAlchemy
  behaviour tested only over the fake store. `docs/testing.md` puts that in an
  integration test.
- **No `tests/e2e/` smoke test for any target-sources route**; `docs/testing.md`
  asks for a Postgres happy path per route. BDD partly compensates.
- **`_setup_summary` (`backoffice_registration.py`)** - the gsheet branch
  returning `None` and the `targets_stale` count are untested.
- **JS:** `row-actions-menu.test.js` stubs `$refs` and the event, so the real
  claim - Escape in an open menu does not reach `dialog-escape` - is never
  exercised end to end; a jsdom test wiring both would pin it.
  `dialog-escape.test.js` has no case showing a `div.dialog-backdrop--clickable`
  (the Alpine modals) is ignored.

## Rewords - your call

The Hungarian catalogue has no fuzzy entries, so each of these is now an
untranslated new msgid.

| Old | New |
| --- | --- |
| "Yes / No", "Yes / No / Not set" | "Checkbox" (both), plus "Checkbox (can be left unanswered)" |
| "Add a field" | "Add a question" |
| "Field added" / "updated" / "removed" | "Question added" / "updated" / "removed" |
| "Field" (table header) | "Question" |
| "Guess field types from data" | "Guess question types from data" |
| "Guessed types for %(count)d fields" | "Guessed types for %(count)d questions" |
| "No fields were guessed - ..." | "No question types were guessed - ..." |
| "Only fields still set to Text will be updated; explicitly-typed fields are left alone." | "Only questions still set to Text ...; explicitly-typed questions are left alone." |
| "Schema initialised with %(count)d fixed fields" | "... %(count)d built-in questions" |
| "Fixed fields keep their built-in type." | "This is a built-in question, so its type can't be changed." |
| "No schema has been set up ... reserved fixed fields only (...)" | "... built-in questions only (...)" |
| "Remove this field from the schema? Respondent data keeps its values..." | "Remove this question? Respondent data keeps its values..." |
| "Help text" | "Help text (optional)" |
| "Optional hint shown beneath the field on the registration page." | "Shown beneath the question on the registration page." |
| "Radio buttons" | "Radio" |
| "Registration" (h2) | "Registration page" |
| "This assembly has no registration pages yet. Create one to start..." | "No registration page created yet" + "Use the button above to create one." |

Dropped with no successor: "Fields" (tab), "Fixed" (tag), "Summary", "Order",
"Move", "Section for %(key)s", "Kind of text", "Shown on the form as", "On the
registration page", "Derived (computed from another field)", "Create targets
first to add a derived field - it feeds one."

Nearly all follow from the deliberate field -> question move, which I would
accept. Two look incidental and could be reverted to save retranslation:
**"Help text" -> "Help text (optional)"** and **"Radio buttons" -> "Radio"**.

## Low

- `assert` used for control flow in `target_source_service.py`
  (`assert created is not None`, `assert linked.derivation_type is not None`,
  `assert linked.derivation_config is not None`) - stripped under `python -O`.
- A blueprint imports another blueprint: `target_sources.py` and
  `respondent_field_schema.py` import `registration_hub_context` from
  `backoffice_registration.py`; `target_sources.py` imports `parse_age_rule`,
  `parse_small_mapping_rule`, `age_prefill_from_target` from
  `respondent_field_schema.py`. Better in a non-blueprint module.
- `delete_derived_field` / `rename_derived_field` load every respondent of the
  assembly to rewrite one JSON key, inside the `save_all` / unlink request
  transaction. Slow on large pools.
- `TargetLinkedError` is correctly uncurated (the route renders `blocks`, never
  the message). `LinkedFieldBlock.action` is a bare `"rename"`/`"delete"` string
  where an Enum would be tidier.
- `tests/fixtures/json_api/respondent-field-spec.json` - every record has
  `"feeds_target": null`, so the JS/contract side never sees the string case.
- Double quotes around placeholders where the guide asks for single:
  `_checklist.html:31,33,39`, `_setup_modal.html:130,150`,
  `targets_force_unlink_confirm.html:30,32,40`. `_checklist.html:121-126` uses
  single, so the file disagrees with itself.
- `target_source_service.py:190` - "before wiring a data source" is code jargon;
  "setting up a data source" matches the screen.
- Field and question mixed within one flow: `_checklist.html:48`,
  `_field_modal.html:103`, `respondent_field_schema_service.py:351`,
  `target_sources.py:674` next to `:638`. ("Field '%(key)s' ..." service errors are
  defensible - they name a field key.)
- "Choose one" (`_field_modal.html:16`), "Select one" (`_setup_modal.html:40`)
  and "Choose a question..." are separate msgids for one idea.
- "%(count)s lookup rows" (`_checklist.html:36`) has no plural handling and sits
  beside the existing "%(count)d lookup rows" - two msgids differing only in
  format. "%(count)s questions on the registration form" also lacks plurals.
- `target_sources.py:102-104` defaults new field keys to "Postcode",
  "year_of_birth", "date_of_birth"; they become labels via `humanise_field_key`,
  so are English in every language. Probably accepted as data.
- Static inline styles, which `frontend_security.md` discourages: widths at
  `_setup_modal.html:177-194`, `min-width: 12rem` on the menus and mapping rows,
  `list-style: none; padding: 0;` at `_checklist.html:20`, `<col style>` at
  `_editor.html:41-45`. (`style="color: var(--...)"` is house style - not flagged.)
- `_editor.html:61-66` - the question name cell is a `<td>`; `<th scope="row">`
  would give row context. The hand-rolled `.question-table` is otherwise
  justified by the Figma design and structurally correct.
- `main.css` `.row-link-host { position: relative }` on a `<tr>` - older Safari
  ignores it, so the `::after` overlay can escape the row. Needs a quick Safari
  check.
- `components/registration_page_list.html:228` - the illustration `<img>` has no
  `v=static_hashes(...)` cache-buster; the SVG is a 66KB unoptimised Figma export
  and contains a layer id `20365528_SEO_Services_6_` that looks like a
  stock-asset identifier. **Worth confirming the licence.**
- `_setup_modal.html:161-164` passes user-written target values to
  `ageBracketPreview` via `data-target-values='{{ ...|tojson }}'` rather than a
  JSON script block. Safe as written (single-quoted, `tojson` escapes `'`,
  commented), and copied from `_derived_panel.html:71-73` on main.
- `_editor.html:185` - `@submit.prevent="$confirm('{{ _("...") }}', $el)"` is the
  established `$confirm` pattern and was on main; known weakness that a
  translation containing an apostrophe breaks the expression. The same file uses
  `data-confirm` elsewhere, which does not have the problem.
- `pie_chart_card.html:11-24` references `--color-data-*` primitives directly. A
  semantic `--color-chart-series-N` layer would be purer; with one consumer, not
  worth blocking on.
- Test brittleness: BDD steps match literal English ("2 fell back to UNKNOWN",
  "Break the links and save"); many component-test `"..." not in body` negatives
  pass silently if wording changes (`test_backoffice_target_sources.py:172,206,225,358-360`);
  `see_warning_toast` asserts the inline style contains `--color-warning-100`.
- `tests/e2e/test_backoffice_respondent_field_schema.py:48-49` - positive
  `b"Fixed" in body` became negative `b">Fixed<" not in body`. Justified product
  change, and other positive assertions keep the test from being vacuous.
- Not this branch (raise an issue): `docs/frontend_build.md`'s entry-point table
  omits `backoffice/js/pie-chart`, which came in from main.

## Clean

- **Config/build:** no changes to `config.py`, `env.example`,
  `docs/configuration.md`, `esbuild.config.mjs`, `package.json`, the justfile or
  either conftest. No new table, so the conftest delete lists need no change.
- **JS:** nothing hand-written under `static/`; `row-actions-menu.js` is imported
  by `backoffice/alpine-components.js` and `dialog-escape.js` by `utilities.js`,
  both entry points; no CDN references; new Alpine code is CSP-compliant (named
  `Alpine.data()` components, zero-arg handlers, simple ternaries, no `x-model`);
  no user-facing strings added in JS; no hand-typed API literals in tests.
- **Templates:** the one `caller()` (`_step_dialog.html:36`) is directly in the
  macro body; no inline `<svg>`; `icon_arrow_forward` is a proper Lucide glyph
  with `aria-hidden` and a showcase entry; no per-call-site stroke-width; every
  `var(--...)` is defined; `test_icons.py` and `test_design_tokens.py` untouched;
  the `--color-data-*` scale belongs in `primitive.css`. Icon-only buttons all
  have contextual `aria_label`s; unlabelled selects carry `aria-label`; fieldsets
  and legends used; removing the stale static `aria-checked` from the switch in
  `input.html` is correct.
- **JSON API:** no `str(e)` in any JSON body; the field-spec route, schema and
  fixture agree (`feeds_target` added, required, `string|null`; `SPEC_VERSION` 5
  in service, fixture and `docs/respondent_field_spec.md`).
- **Transactions:** no `render_template`, gspread or SMTP inside a `with uow:`;
  no new `except Exception`; no `commit_and_reset()`; no broad suppress inside a
  block (`contextlib.suppress(ServiceLayerError)` in `_page_context` is narrow
  and follows precedent). `_guard_linked_categories` breaks links before
  validation, but `TargetsNotSaved` is raised inside the block, so it all rolls
  back.
- **Layering:** domain stays plain Python; no Flask in the service layer; the new
  ORM column is a plain UUID FK with no relationship.
- **Auth/CSRF:** every new route has `@login_required`; every service entry point
  asks `can_manage_assembly` / `can_view_assembly` (a capability, not a role);
  every URL/form id is checked against `assembly_id`; all seven POST forms and
  the force-unlink page carry `csrf_token`.
- **Personal data:** structlog only, no PII logged; the uploaded CSV (a postcode
  lookup table, not respondent data) is held in memory only; nothing touches
  cookies, sessions or analytics.
- **i18n mechanics:** `_()`/`_l()` used correctly (module-level dicts use `_l()`,
  request-time dicts use `_()`); no literal-beside-lookup, f-string or `.format()`
  inside `_()`; no lone `%`; placeholders well-formed; glossary terms (Google
  Sheets, spreadsheet, target, respondent), British spelling and "no we" all
  hold. The `docs/language.md` additions match the strings used, apart from
  "computed question".
- **Tests:** tiers are right (unit over `FakeUnitOfWork`, component over
  `FakeStore`, BDD via feature files); no `skip`, `xfail`, `sleep` or mocks
  added; `TargetLinkedError` went on the UNCURATED list (the safe side);
  `test_accessibility.py`'s selector change is a legitimate tightening; the
  deleted BDD scenario is replaced by one in `target-data-sources.feature`.

## Suggested order

1. Finding 1 - it affects live pages the branch never meant to touch.
2. Finding 3 - it undermines the invariant the branch's last commit was written
   to protect.
3. Finding 2 - the 500s.
4. Finding 4 - the tests that would have caught part of 2.

One thing to push back on in advance: if the APG menu gap is waved through
because `dropdown_button` does it too, that makes two components announcing
arrow-key behaviour they do not have.
