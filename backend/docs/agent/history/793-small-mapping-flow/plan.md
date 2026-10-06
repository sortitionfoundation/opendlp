# Small-mapping set-up flow — implementation plan

**Status:** Implemented — all chunks landed on `793-small-mapping-flow` (2026-09-22)
**Date:** 2026-09-22
**Branch:** `793-small-mapping-flow` (off `main`, which now carries both
`793-two-step-fields` and `793-large-mapping-flow`)

## 0. What this is, and where we start from

Today the "Map from more options" (`SMALL_MAPPING`) method in the target data
sources set-up modal can only **reuse** an existing choice question. If none
exists the modal says "add the more detailed question on the registration
questions step first, then come back", and the save path refuses a `create`
source with the same message (`_parse_setup_spec`). That was a deliberate
shortcut in `793-two-step-fields` (plan §3, implementation note), and it is
the one method where step 1 sends the organiser to step 2 and back.

The goal: from the same modal, name the new registration question, type its
answer options, map each option to a target value, and save — one dialog,
one transaction, exactly as the other three methods already create their
source question.

### The good news: the service layer already does this

`configure_target_source` with a `SmallMappingSpec` whose `SourceFieldSpec`
carries `field_key`, a choice `field_type` and `options` already creates the
choice question, creates the computed question, links it and recomputes.
`tests/unit/test_target_source_service.py` has a test for exactly that
(`TestConfigureSmallMapping`, the create-with-options case around line 330).
`_resolve_source_field` validates the created field the same way it validates
a reused one.

So this is almost entirely a **blueprint + template** change in
`entrypoints/blueprints/target_sources.py` and
`templates/backoffice/target_sources/_setup_modal.html`, plus tests. The one
service-layer touch is trivial (§3.3).

### What the modal has to grow

1. The **create / reuse choice** for this method, as the other methods have
   it (`source_mode` radio when there are candidates; straight to "create"
   when there are none).
2. A **name and label** for the new question — the existing `new_field_key`
   / `new_field_label` inputs.
3. An **option editor** — rows the organiser types answer values into, with
   add-another and remove, round-tripping through the server the way the
   registration questions modal's option editor does (`form_action`
   `add_option` / `remove_option_<i>`).
4. The **mapping** — each row's target-value select. In create mode this sits
   on the same row as the option's value input, so "type the answers" and
   "map them" are one table rather than two steps.

---

## 1. Proposed dialog, create mode

```
How is the data collected?      [ Map from more options ▾ ]
  Ask with more detailed answers and map each one to a target value
Target values: Younger, Older

Which question collects the source value?
  ( ) Use an existing question   (•) Create a new question      ← only when candidates exist

New question name        Label on the registration page (optional)
[ age_band           ]   [ Which age group are you in?          ]

Answers, and the target value each one counts as
  Answer                       Counts as
  [ 16-29        ]   →   [ Younger        ▾ ]   (Remove)
  [ 30-44        ]   →   [ Older          ▾ ]   (Remove)
  [              ]   →   [ (fall back to UNKNOWN) ▾ ]   (Remove)
  [ Add another answer ]

This will add 'age_band' to your registration page.

                                     [ Cancel ]  [ Save ]
```

Reuse mode is unchanged: the existing question select, then the mapping
table with the question's options as fixed labels (today's markup).

Notes on the shape:

- **One table, not two phases.** The alternative — type the options, refresh,
  then map — is what a textarea-of-options would force. The row-per-option
  editor with the select on the same row avoids it and matches the
  questions modal's option rows, which organisers have already seen.
- **Add/remove round-trip through the server** (`hx-post` with the clicked
  button's `form_action`), no client-side row cloning. That is the pattern
  `_field_modal.html` uses, it is CSP-safe, and it works without JS because
  the buttons are ordinary submit buttons.
- **Blank rows are dropped on save**, as `_submitted_options` does. A row
  with a value but no target counts as "fall back", which is today's
  behaviour for a reused question.
- **Radio vs dropdown** is chosen automatically by option count, as the
  exact-copy method does (`_choice_type_for`: six or fewer is radio). The
  organiser can change it afterwards on the registration questions step,
  since the *source* question is not target-linked and stays fully editable
  there.

---

## 2. Decisions (agreed 2026-09-22)

Each was put to Chewie with a recommendation; every recommendation was
accepted. The rejected alternatives stay here so nobody re-proposes them.

### D1. The option rows start as one more blank row than the target has values

- **(a) Agreed: one more blank row than the target has values.** "More
  options than the target" means at least N+1, and it saves a click or two
  without pretending to know the answers. Two-value target → three rows.
- (b) A fixed three blank rows.
- (c) Pre-fill the rows with the target's own values, each mapped to itself,
  for the organiser to add to. Tempting for the "target plus a finer split"
  case, but the common case (age bands finer than the target's) makes them
  delete every row first. I'd not.

### D2. No per-option help text in the modal

The questions modal has a help-text input per option. **Agreed: no.**
The set-up modal stays about the mapping; help text is a presentation detail
the organiser edits on step 2, and the modal already says so ("you can edit
parts of it in the registration questions step"). It is a one-line addition
later if it turns out to be missed.

### D3. Edit mode does not edit the source question's options

Today "Edit" on a small-mapping row opens the modal in reuse mode, with the
source question's current options as the rows. **Agreed: leave that as it
is.** Editing option values belongs to the questions modal, which already
carries renames and removals through to the mapping (`option_original`,
`_rename_small_mapping_keys`, `_drop_small_mapping_keys`). Adding option
editing to the set-up modal's edit mode would mean re-implementing that
rename/remove bookkeeping here. What *does* change on edit: the organiser can
switch to "Create a new question" if they want a different source, exactly as
the other methods allow.

### D4. An unmapped answer is allowed, with a warning line

Today a reused question's row may be left on "(fall back to UNKNOWN)". For a
question being created in the same breath, an unmapped answer is more likely
an oversight. **Agreed: keep allowing it, but say so** — a
secondary-text line under the table: "Answers left as 'fall back' don't count
towards any target value." No blocking, no extra state. Blocking is easy to
add later; un-blocking is a rewording plus a translation churn.

### D5. No default name; the name is required

Large mapping defaults to "Postcode", age brackets to `date_of_birth`. There
is no equivalent here. **Agreed: no default; the name is required**, with
the existing "Enter a name for the new registration question" error. The
label defaults to the humanised key as elsewhere.

### D6. The rows are "answers", not "options"

The modal already says "Map each answer to a target value"; the questions
modal says "Options". **Agreed: "answer"** in this dialog throughout
("Add another answer", column heading "Answer"), because here the organiser
is thinking about what the page asks (glossary: say "question" where the
reader is thinking about what the page asks).

---

## 3. Implementation ✅ done

Notes from implementing it:

- `parse_answer_options` in `derivation_form_parser.py` turns the typed
  `map_source` rows into the new question's options (blank rows dropped,
  repeats refused by name). The blueprint's `_parse_source_spec` calls it
  for the small-mapping method and sets `field_type` with `choice_type_for`.
- `_setup_modal_response` is the general "re-open with these values" helper;
  `_setup_error_response` wraps it with an error and 422. A `form_action`
  other than `save` in `configure_view` is a row round trip and saves nothing.
- `_map_rows` builds the table for either mode. In create mode with nothing
  typed it pads to D1's row count; removing every row therefore re-pads,
  which is harmless.
- The service refuses a `SmallMappingRule` whose outputs are not all target
  values (`_require_mapping_outputs_are_target_values`), for both modes.
- The template renders the mapping as a `<table>` with `scope="col"`
  headings; the create-mode row is a labelled text input, the select, and a
  labelled Remove button. The hidden default submitter from
  `_field_modal.html` is copied so Enter saves. Column headings use
  `text-label-md` (`text-label-sm` does not exist in the design system).
- No focus work was needed: `fragment-dialog-focus.js` already puts focus
  back on the control that had it, by id, after a re-render, and the row
  inputs have stable ids.
- The Hungarian catalogue regeneration also picked up a stale `signup`
  msgid from an earlier branch; it is untranslated and harmless.

### 3.1 Form values (`target_sources.py`) ✅

- `_setup_values_from_request` already reads `map_source` and `map_target`
  as lists. **Keep those names in create mode too**: the create-mode row's
  value input is `name="map_source"` (a text input instead of the hidden
  input reuse mode renders). Then `parse_small_mapping_rule` needs no change
  and the two modes post the same shape. The option list for the new
  question is simply the non-blank `map_source` values, in order.
- `_setup_modal_ctx`'s `map_rows` grows a create-mode branch: rows are the
  submitted `map_source`/`map_target` pairs (zip_longest, fill ""), padded to
  the D1 starting count when nothing has been typed yet.
- Mapping values submitted but not among the target's values (a hand-edited
  form, or a target whose values changed under a stale dialog) are **silent
  today**: `output_options` builds the computed question's options from the
  target's values, so the stray value is stored in the mapping but is not an
  option, and respondents who give that answer get a value the target does
  not count. The parser cannot check it (it runs before the route's `uow`
  opens, so it has no target), so add the check in the service layer:
  `_configure_derivation` raises `FieldDefinitionConflictError` for a
  `SmallMappingRule` whose mapping values are not all target values —
  "'%(value)s' is not one of the target's values". `configure_view` already
  shows that exception's `user_msg()` in the modal. It closes the gap for
  both create and reuse mode, and the §4 note about stray *keys* stays a
  separate, lower-value follow-up.

### 3.2 Round trips (`configure_view`) ✅

- Read `form_action = request.form.get("form_action", "save")`.
- If it is not `"save"`: apply `add_option` (append a blank pair) or
  `remove_option_<i>` (pop that index from both lists, ignoring a bad index)
  to `values`, then re-render the modal with **200** and no error. This
  needs a `_setup_modal_response(assembly_id, category_id, values, error="",
  status=200)` — `_setup_error_response` is that function with `error` and
  422 baked in, so generalise it and keep the name for the error call or
  replace both call sites. Its docstring's point (the block is fresh because
  the save's has rolled back — here, because there was no save) still holds.
- The `dirty` hidden input rides through as it does on the refresh GET, so
  the leave guard keeps working across a round trip.
- Without JS the same buttons post the same form and get the full page with
  the modal open via `_render_setup_modal`. Nothing extra to do.

### 3.3 Spec building (`_parse_source_spec`, `_parse_setup_spec`) ✅

- Drop the `source_mode != "reuse"` refusal in `_parse_setup_spec` for
  `SMALL_MAPPING`.
- In `_parse_source_spec`, when the method is `SMALL_MAPPING` and the mode is
  `create`: build `options` from the non-blank, stripped `map_source` values
  as `ChoiceOption`s; refuse an empty list ("Enter at least one answer") and
  a repeat (reuse `duplicate_option_value` — it lives in the
  `respondent_field_schema` blueprint; move it to
  `domain/respondent_field_schema.py` next to `normalise_field_key`, since it
  is pure and now has two blueprint callers); set
  `field_type=choice_type_for(len(options))`.
- **Service touch (agreed):** rename `_choice_type_for` in
  `target_source_service.py` to `choice_type_for` and export it, so the
  blueprint and the exact-copy path agree on the radio/dropdown threshold.
  The blueprint sets `field_type` explicitly in the spec. (Rejected: leaving
  `field_type` unset and having `_resolve_source_field` choose when
  `options` is given — implicit, for no saving.)

- The key is used as typed, not normalised through `normalise_field_key`,
  to match how this modal already treats `new_field_key` for the other
  methods ("Postcode" keeps its capital). **Agreed to leave as is:** Chewie
  wants to revisit key normalisation later, in one consistent step across
  every place a key is entered, not piecemeal here. Listed in §4.

### 3.4 Template (`_setup_modal.html`) ✅

- Remove the small-mapping-only branch (the forced `source_mode=reuse` hidden
  input and the "add it on the registration questions step first" copy).
  Small mapping then falls into the general `{% elif values["method"] %}`
  branches: the create/reuse radio when there are candidates, or the
  "nothing to reuse" path when there are none — with the difference that
  the no-candidates path for this method **shows the create form** (name,
  label, option table) rather than only the sentence, because there is
  something to fill in.
- Restructure the mapping fieldset into a small table (`<table>` with
  `scope="col"` headings "Answer" / "Counts as"; or keep the flex rows with
  a visually-hidden heading — table is the accessible choice for two related
  columns). In reuse mode the first cell is the fixed value plus the hidden
  `map_source`; in create mode it is a text input (`aria-label` "Answer
  %(n)d") plus the Remove button at the row end, and "Add another answer"
  below. Both are `type="submit"` buttons with `name="form_action"`.
- Enter in a text input must **save**, not remove a row: the Save button is
  the first submit button in the form's DOM order? It is not — the footer
  comes last. `_field_modal.html` solves this with a hidden default submit
  button placed first in the form (see its comment near line 67); do the
  same here.
- `refresh_attrs` (`hx-get` on change) on the method/source-mode/reuse
  selects already carries the whole form, so typed rows survive a mode
  switch. The target-value selects must **not** carry `refresh_attrs` —
  changing a mapping is not a reason to re-render.
- D4's fall-back line under the table; the "This will add '%(name)s' to your
  registration page." preview already exists for the create branch.
- Accessibility check against `docs/agent/component_accessibility.md`: each
  row's inputs labelled, the Remove buttons `aria-label`led with the row
  number, focus after a round trip lands somewhere sensible (the fragment
  dialog focus code in `src/js/init/fragment-dialog-focus.js` restores by
  identity — give the added row's input a stable id so "Add another answer"
  can move focus there; check what the questions modal does and copy it).

### 3.5 Copy ✅

New msgids, checked against `docs/language.md`:

- "Answers, and the target value each one counts as" (legend)
- "Answer", "Counts as" (column headings)
- "Add another answer", "Remove answer %(n)d"
- "Enter at least one answer"
- "Answer values must be different: '%(value)s' appears more than once"
  (mirror of the questions modal's option message, reworded for "answer")
- "Answers left as 'fall back' don't count towards any target value." (D4)

Removed: "Choose the choice question to map from — add it on the
registration questions step first" and "No choice question exists yet — add
the more detailed question on the registration questions step first, then
come back." Run `just translate-regen` and `just translate-check`.

The "Map from more options" method help text stays as it is.

### 3.6 Tests ✅

- **Unit** (`tests/unit/test_target_source_parsers.py`): options from
  `map_source` in create mode — blank rows dropped, whitespace stripped,
  duplicate refused, empty refused, radio/dropdown threshold.
- **Unit** for `duplicate_option_value` moves with the function.
- **Component** (`test_backoffice_target_sources.py`,
  `TestConfigureSmallMapping`):
  - with no choice question in the assembly, choosing the method shows the
    create form with the D1 starting rows and no "come back later" copy
  - with a candidate, the create/reuse radio appears and reuse still works
    (existing test)
  - saving in create mode creates a choice question with the typed options
    in order, a linked computed question, and the mapping; recompute toast
    when respondents exist
  - `add_option` and `remove_option_<i>` round-trip with 200, keep typed
    values, and save nothing
  - a bad remove index is ignored
  - blank name → 422 with the name error; empty options → 422; duplicate →
    422; each re-renders the modal with the typed rows intact
  - no-JS: the round-trip buttons return the full page with the modal open
  - the fixed-row markup in reuse mode is unchanged (hidden `map_source`)
- **e2e** (`tests/e2e/test_backoffice_target_sources.py`): one Postgres
  round trip — create via the modal, then a respondent recompute, following
  `TestConfigureAgeBrackets.test_age_bracket_round_trip`.
- **BDD** (`features/target-data-sources.feature`,
  `tests/bdd/test_target_sources.py`): one scenario — set up "Age group" by
  mapping from a new question, typing two answers and mapping them, then the
  row says "Computed from '…' — Map from more options" and the registration
  questions step lists the new question. Add a second scenario only if the
  add/remove round trip needs Playwright to prove focus handling.
- No JS unit test unless a new Alpine component appears; none is planned.

### 3.7 Docs ✅

- `docs/agent/793-two-step-fields/plan.md` §3 implementation note ("the
  small-mapping method reuses an existing choice field only"): add a pointer
  to this plan.
- `docs/agent/793-derived-fields/plan-simple-ui.md` if it still describes
  the small-mapping constraint; grep for "registration questions step first".
- Memory note update at the end.

### 3.8 Commit sequence ✅

Each lands green (`just check`, `just test-nobdd`, then
`just test-bdd-headless`):

1. `refactor`: move `duplicate_option_value` to the domain; export
   `choice_type_for` — pure moves with their tests
2. `feat(ui)`: create the source question and its answers from the
   small-mapping set-up modal (parsers, round trips, template, component
   and unit tests)
3. `test`: e2e round trip and BDD scenario
4. `i18n`: regenerate catalogues
5. `docs`: plan pointers

---

## 4. Out of scope, noted for later

- **Field-key normalisation** across every place a key is typed (this modal,
  the questions modal's `normalise_field_key` path, imports). Chewie's call:
  one consistent change later, so this branch keeps the as-typed behaviour.

- **Option editing in the set-up modal's edit mode** (D3) — if wanted, it is
  the `option_original` rename/remove bookkeeping from the questions modal,
  moved into or shared with this one.
- **The two mapping-table layouts drifting**: after this change the set-up
  modal and the questions modal each have an option-row editor with the same
  add/remove round trip but different columns. A shared macro is possible
  but they differ enough (help text vs. target select) that I'd wait for a
  third caller.
- **`SmallMappingRule` does not check that mapping keys are among the source's
  options.** Create mode guarantees it by construction and reuse mode by
  the fixed rows, so only a hand-crafted post can produce a stray key. A
  service-layer check would close it; it is not needed for this feature.
