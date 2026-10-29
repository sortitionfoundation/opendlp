# 1072 — Replace fixed sections with headings and text in the question list

Status: agreed; being implemented. All questions settled over two rounds
of review; round 2 chose B for Q1, dropped headings from the CSV seed (Q2) and
dropped tag rejection on save (Q4). Phases are ticked below as they land.

## The goal

The registration questions step (`/project/<id>/respondent-schema`) today shows
six fixed sections (Eligibility, Name and contact, Address, About you, Consent,
Other), each with its own "Add a question" button. We agreed to drop the fixed
sections. Instead the step shows **one ordered list** in which an organiser can
place, between any two questions, a **heading and/or some text**, and move it
like a question.

## What exists today

The sections are not just a display grouping on this one page. They are the
`RespondentFieldGroup` enum, stored on every question as `field_group`, and the
whole system orders questions as "group in `GROUP_DISPLAY_ORDER`, then
`sort_order` within the group". Sort orders are only unique _within_ a group.

Where the group is used:

| Where                                                                                    | What it does with the group                                                                                                                                        |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `domain/respondent_field_schema.py`                                                      | `RespondentFieldGroup`, `GROUP_DISPLAY_ORDER`, `GROUP_LABELS`                                                                                                      |
| `adapters/orm.py`, `sql_repository.py` `list_by_assembly`                                | `field_group` column; sorts by group index, then `sort_order`                                                                                                      |
| `blueprints/respondent_field_schema.py`                                                  | one card per group; Section dropdown in the dialog; `move_field` swaps within the group; `reorder_group`                                                           |
| `_editor.html`                                                                           | the section cards, the per-section "Add a question" button                                                                                                         |
| `service_layer/respondent_field_schema_service.py`                                       | `get_schema_grouped`, `reorder_group`, per-group "next sort order" when seeding from CSV, adding a field, and the CSV diff                                         |
| `respondent_field_schema_heuristics.py` `classify_field_key`                             | guesses a group from a CSV header ("postcode" → Address) when seeding                                                                                              |
| `target_source_service.py`, `derivation_service.py`                                      | pick a group, and the next sort order in that group, for questions they create; derived fields always go in `DERIVED`                                              |
| `domain/registration_page.py` `generate_starter_form_html[_govuk]`                       | writes an `<h2>` per non-empty group into the starter form HTML                                                                                                    |
| `blueprints/respondents.py`                                                              | the view-respondent and edit-respondent pages show the respondent's answers in group sections; the CSV upload diff page lists the guessed group of each new column |
| `respondent_field_spec_service.py`, `schemas/json_api/respondent-field-spec.schema.json` | `"group"` in every field of the hidden JSON spec, whose order is documented as `GROUP_DISPLAY_ORDER` then `sort_order`                                             |
| `respondent_export_service.py` (via `list_by_assembly`)                                  | the column order of the CSV export                                                                                                                                 |
| `blueprints/dev.py`, `templates/backoffice/service_docs/_fields.html`                    | dev endpoint and service docs mention groups                                                                                                                       |

### The public form doesn't read the schema

The public registration page is **authored HTML** (`RegistrationPageHtml.form_html`)
that the system never rewrites. The schema reaches it only when an organiser
fills an empty form with the generated starter HTML
(`fill_empty_registration_form_html`). "Render the page from the schema" is
agreed direction, not done (see `docs/targets-and-registration-questions.md`).

So a heading added on this step reaches:

1. the starter form HTML — **in scope for this work** (P5);
2. the view- and edit-respondent pages (Q7);
3. the schema-rendered form, when we build it.

The "questions changed since the form was saved" warning
(`backoffice_registration.py:303`) is what tells an organiser their HTML is
behind; Q9 makes headings and text feed it.

### Q0. Before or after the schema-rendered form? — decided

**Build this first.** Until the form is generated automatically, the way to get
a page's form in line with the questions is manual: on the form step, Edit,
clear the HTML, save, then "Fill with accessible HTML" (the fill buttons appear
only once the form is empty). Automating that step comes soon after this work,
as its own piece.

## Decisions

### Q1. How do we store a heading/text block? — decided: B

**A separate table, `registration_content_blocks`, sharing the questions'
ordering scale.** Columns: `id`, `assembly_id`, `sort_order`, `heading`,
`body_html`, `created_at`, `updated_at`. `sort_order` on both tables is on
**one per-assembly scale**, so the list the step shows is the two merged by
`sort_order`. A new service function (`get_form_items(uow, user_id,
assembly_id)` or similar) does the merge, and a new `reorder_form_items(...
ordered: list[tuple[kind, id]])` renumbers both tables in one transaction,
requiring the complete set (as `reorder_group` does today, so a stale browser
is rejected rather than half-applied). Nothing that reads only questions
changes.

`SORT_ORDER_STEP` (10) gaps, the whole list renumbered on every reorder, and
equal values tie-broken deterministically (questions before blocks, then id).

Rejected:

- **A row in `respondent_field_definitions` with a `kind` column.** Every one
  of the dozen or so service modules calling `list_by_assembly` (export, spec,
  targets, submission validation, the email field lookup, derivations…) would
  have to learn to skip rows that aren't questions, and a row would need a fake
  `field_key` for the unique index. A missed filter puts a "heading" column in
  someone's CSV export.
- **An explicit layout list** (a JSON array of item ids on the assembly). It
  duplicates the ordering `sort_order` already holds.
- **Three tables: fields, blocks, and a `form_layout` table** holding the order,
  with a foreign key to a field or a block, and no row for off-form fields.
  Fields would still need an order of their own for the CSV export, the JSON
  spec and the respondent pages — two orderings that can disagree — and turning
  "on the registration page" off and on would delete and re-invent a field's
  position. Its one real advantage, a different layout per registration page,
  isn't wanted: every page of a project shares one order.

### Q2. What happens to `field_group`? — decided

Ordering becomes one flat list per assembly, and the group has no remaining
job: `DERIVED` is already said by `is_derived`.

1. **Migration** (data + schema), per assembly:
   - for each group except `DERIVED`, in `GROUP_DISPLAY_ORDER`, insert a
     heading block with the group's English label ("Eligibility", "Name and
     contact"…) **only when at least one non-derived question is in that
     group**, so an empty group — "Other", most often — never leaves a heading
     stranded after the last question. Existing projects look as they do now,
     but the headings are editable, movable and deletable;
   - renumber all questions and blocks globally in the old display order;
   - derived fields keep a `sort_order`, after everything else, and are never
     shown in the step's list (they aren't today either).
2. **Code** stops reading `field_group` everywhere (table above).
3. **A later migration drops the column**, once nothing reads it — a separate
   PR, so a rollback of the first doesn't need the data back.

The migration writes the labels as English literals, not `_()`; they are
organiser-editable text from then on, like question labels, and in the same
language whatever the registration page's language.

**Where new questions go** when they don't come from an "add" button:

- _CSV seed and later CSV uploads_ (the upload diff): new columns are appended
  at the end in CSV column order, and **no headings are created**. A guessed
  heading would often be wrong, and a CSV usually already has similar columns
  next to each other. The diff page stops showing a guessed group per column.
- _Target sources step_ (creating a question for a target): appended at the end.
- _Derived fields:_ not in the list; appended at the end.

So nothing needs `classify_field_key` once `field_group` is gone. Until the
column is dropped (P8) it is `NOT NULL`, so new rows keep getting a guessed
group from it — purely so the column has a value, and so a rollback of this
work still shows sensible sections. P8 deletes the heuristics module along
with the column.

### Q3. One element type or two? — decided

**One type, "heading and text": an optional plain-text heading plus an
optional rich-text body, at least one of them filled in.** The heading is
structural (stored on its own, rendered as `<h2>`), the common case is one
item, and a heading-only or text-only block is one field left blank. In the
list it shows the heading prominently, or the first line of the text in a
quieter style when there is no heading.

The heading is always `<h2>`; the rich-text body may contain `<h3>` for
sub-points.

Rejected: rich text only (nothing structural knows where the headings are, so
the respondent pages couldn't split at them), and two separate types (the
common heading-plus-sentence case becomes two items to keep together).

### Q4. Plain fields or rich text for the body? — decided

**A plain-text heading `<input>` and a rich-text body** using the existing
Tiptap editor (`src/js/backoffice/rich-editor.js`) with a reduced toolbar:

- **in:** paragraph, h3, bold, italic, left/centre/right alignment, bulleted
  and numbered lists, link, undo/redo;
- **out:** images, tables, h1, and h2 (the block's own heading is the h2, per
  Q3).

The auto-reply email already mounts the editor "with less in it", so a reduced
toolbar is a solved problem. The HTML view stays available as it is elsewhere.

Wiring notes for implementation:

- `html-editor.js` mounts the editor on any `textarea[data-rich-editor]` added
  later (MutationObserver), so it mounts inside the HTMX-loaded dialog with no
  new wiring, and destroys it when the textarea leaves the DOM.
- The **link** dialog is answered by Alpine handlers on
  `assembly_registration.html` (`@rich-editor-link-request.document`) and
  markup in `registration/_modals.html`. The questions step is a different
  page, so it needs the link dialog included, or the link button does nothing.
- **The body accepts any HTML on save.** Only the toolbar is reduced: someone
  writing in the HTML view knows what they are doing, and the alternative is
  that they hand-maintain the same thing in the full form HTML instead. So no
  server-side tag rejection.
- Configure the editor as the auto-reply email does, with the existing
  `createSchemaExtensions({ images: false, tables: false })` flags. A body
  whose HTML has a table or image then opens in HTML mode with the usual
  notice and loses nothing — the behaviour the auto-reply already documents
  and tests. h1 and h2 are left out of the toolbar only; the schema keeps
  them, so a body with one still opens visually.

How a block gets onto a page:

- The heading as `<h2>`, escaped with `_literal_html_text`, which also
  neutralises `{` `}` so it can't open a Jinja tag.
- The body with braces escaped the same way: **no template variables in
  blocks** for now. A block that rendered differently in the starter HTML and
  in a future schema-rendered form would be a trap.
- Under the GOV.UK style the body goes through `apply_default_govuk_classes`,
  as the intro does; the heading gets `class="govuk-heading-l"`, matching the
  section headings the GOV.UK starter writes today.

### Q5. What do the add buttons say, and where do they go? — decided

- **Two buttons, "Add a question" and "Add a heading or text"**, at the foot of
  the list. New items go at the end.
- **"Add a question below" and "Add a heading or text below"** in each row's ⋮
  menu, for putting something in place first time.

"Add a heading or text" is the working wording; user testing may change it.

### Q6. Drag-and-drop? — decided

**Sortable.js** (npm, bundled by esbuild), as HTMX's own sortable example uses.
It's a new dependency, approved here. MIT, no dependencies of its own, handles
touch, autoscroll and drop placeholders, and uses no `eval`, so it is CSP-safe;
it is wired from an Alpine component registered in JS, as the CSP build
requires.

On drop, the component posts the complete new order to `reorder_form_items`
and swaps in the returned `#schema-editor` fragment, as the modal saves already
do. A rejected order (the list changed underneath) re-renders the current list
with a message.

The ⋮ menu gains **"Move to top" and "Move to bottom"** alongside "Move up" and
"Move down". These land with the flat list (P4), not with drag-and-drop.

Accessibility: drag-and-drop is never the only way (WCAG 2.2 SC 2.5.7,
Dragging Movements). The ⋮ menu's move commands are the keyboard and
screen-reader route; the drag handle is `aria-hidden`. After any move, focus
returns to the moved row's menu button, and a live region announces "Moved to
position 4 of 22".

### Q7. The view- and edit-respondent pages — decided

**Split at heading blocks.** Each block with a heading starts a section titled
with that heading; the body text isn't shown (it's addressed to the respondent,
not the person viewing their record). Questions before the first heading go in
an untitled section, and derived fields keep a "Computed" section at the end.
With the migration's headings, existing projects look the same as today.

### Q8. The JSON field spec and the CSV export — decided

- The hidden JSON spec (`respondent-schema.json`) **drops `"group"`** outright.
  Update the JSON Schema, re-record the fixture (`UPDATE_API_FIXTURES=1`), and
  update `docs/respondent_field_spec.md`; its documented order becomes "form
  order". Blocks don't belong in it: it describes CSV columns.
- The test-data generator lives outside this repo and only Doctor Chewie uses
  it, so it gets updated rather than the spec keeping a deprecated field.
- The CSV export's column order follows `list_by_assembly`, so it becomes the
  form order.

### Q9. Keeping the "questions changed" warning honest — decided

An assembly-level "questions last changed" timestamp, touched by every add,
edit, move and delete of a question or a block, and the warning compares
`form_updated_at` against it instead of scanning fields' `updated_at`. That
covers blocks without the warning learning about a second table, and fixes the
existing gap where deleting a question never raises the warning.

Implementation detail to settle in P3: the timestamp is a column on
`assemblies`, touched by one helper that every schema-writing service function
calls — including the CSV seed, upload diff, target sources step and
derivations, which write fields today without going through
`respondent_field_schema_service`.

## Out of scope

- Rendering the public form from the schema, and automating "clear and refill"
  (Q0) — next, as separate work.
- Translating blocks for registration pages in other languages (question
  labels have the same limitation today).
- Images and tables in blocks.
- Multi-page forms.

**In scope**, to be explicit: the starter form generators
(`generate_starter_form_html` and `generate_starter_form_html_govuk`) write the
blocks in place and stop writing the old group headings.

## Personal data

Blocks hold organiser-written text about the form, never respondent data, so
nothing changes for erasure.

## Phases

- [x] P1. Domain: `RegistrationContentBlock` (heading, body HTML, sort order),
  validation (at least one of heading/body), the merged form-item ordering, unit tests.
- [x] P2. ORM table, Alembic migration creating it, the data migration from groups
  to heading blocks (non-empty groups only) and global renumbering, the
  "questions last changed" column; add the table to `_delete_all_test_data()`
  and the BDD `delete_all_except_standard_users()`. Migration tests.
- [x] P3. Service layer: `get_form_items`, `reorder_form_items`, add/update/delete
  block; every "next sort order in group" becomes "next on the whole list";
  CSV seed and uploads append in column order with no headings; the "questions last
  changed" helper called from every schema write; stop reading `field_group`.
  Integration tests.
- [x] P4. The step: one list, rows for both kinds, the block dialog with the
  reduced rich editor and the link dialog, the two add buttons and the "add
  below" menu entries, move up/down/top/bottom across the whole list, the
  Section dropdown removed from the question dialog. Load the `ui-components`
  skill first. E2E tests.
- [x] P5. Consumers: **starter form generators** (blocks in place, no group
  headings), respondent view/edit pages split at headings, the CSV upload diff
  page without groups, JSON spec and fixture, the changed-since warning, dev
  endpoint, service docs.
- [x] P6. Drag-and-drop with Sortable.js. Vitest for the component; BDD scenarios
  for drag and for the keyboard route.
- [ ] P7. Docs (`targets-and-registration-questions.md` "Sections are a fixed
  enum", `respondent_field_spec.md`, the field-schema design note, a short
  note on the manual clear-and-refill), translation catalogues.
- [ ] P8. Separate PR: drop `field_group`, `RespondentFieldGroup`,
  `GROUP_DISPLAY_ORDER`, `GROUP_LABELS`, `reorder_group`, `get_schema_grouped`,
  and the heuristics module (`classify_field_key`).

## Where the implementation differs from the plan

- `reorder_group` went in P3, not P8: it renumbered one group 10, 20, 30…,
  which on the single scale would have collided with the rest of the list.
  `move_form_item` (up, down, top, bottom) and `reorder_form_items` replace it.
- `list_by_assembly` orders by `sort_order` with **derived fields last**, so
  the CSV export keeps computed columns at the end as the Derived section did.
- A new schema, and a CSV seed, put the built-in questions eligible,
  can attend and email first and consent and stay on database last. A built-in
  column the CSV has stays where the CSV has it.
- "Questions last changed" is recorded for writes to questions and blocks,
  including the target sources step creating a question or resyncing its
  options, but not for changes to derived fields: they are never on a form.
- The link dialog moved out of `registration/_modals.html` into
  `components/rich_editor_link_modal.html`, so the questions step can include
  it. There it sits inside the heading/text dialog fragment, hosted by a small
  `richEditorLinkHost` Alpine component, because the fragment host's siblings
  go inert while a dialog is open.
- The compact toolbar is a `compact` option on the existing editor macros
  (`rich_editor_compact` on `textarea`), not a separate toolbar.
- The respondent pages put the questions before the first heading under
  "Answers", and computed questions under "Computed questions"
  (`sections_at_headings`). A heading with no question after it, and text
  without a heading, start no section.
- The JSON field spec dropped `group` as version 6 of the spec.
- The dev blueprint's `add_field` handler still takes a `group`: it writes the
  column that P8 drops, so it changes with P8.
- Dragging posts a `reorder-form` that sits outside the table: a form cannot
  wrap rows that hold forms of their own, so each row's hidden `item` input
  joins it through the `form` attribute. A refused order comes back as a 422,
  the status the page's HTMX set-up swaps in.
- After a move from the row menu the page says "Moved to position 4 of 22" (a
  flash message) and focus returns to that row's menu button through
  `#focus=`. After a drag, the step's live region says "Order saved".
- Sortable.js is bundled into `alpine-components.js`, so every backoffice page
  carries it.
