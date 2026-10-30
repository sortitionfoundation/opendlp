# The registration questions list

The registration questions step (`/project/<id>/respondent-schema`) is one
ordered list. It holds the questions and, wherever the organiser puts them,
**headings and text**. There are no fixed sections. This page says how the
list is stored and ordered, where new items go, and what reads it. It is for
developers.

The design and its decisions are in
[docs/agent/1072-edit-sections/plan.md](agent/1072-edit-sections/plan.md).

## What is on the list

- **Questions** are `RespondentFieldDefinition` rows
  (`domain/respondent_field_schema.py`), as they always were.
- **Headings and text** are `RegistrationContentBlock` rows
  (`domain/registration_content_block.py`, table `registration_content_blocks`).
  A block has a plain-text `heading`, an HTML `body_html`, or both; one with
  neither is refused (`ContentBlockInvalidError`). The interface calls a block
  "a heading or text".
- **Computed questions** (derived fields) are never on the list. They are
  managed on the "Link targets to questions" step.

## How it is ordered

Questions and blocks share **one `sort_order` scale per assembly**.
`form_items(fields, blocks)` merges them into the list the step shows, leaving
out derived fields; equal sort orders put the question first. Every reorder
renumbers the whole list 10, 20, 30… (`renumber` in
`service_layer/form_order.py`).

`RespondentFieldDefinitionRepository.list_by_assembly` orders fields by
`sort_order` with **derived fields last** (`field_list_order`), so the CSV
export keeps computed columns at the end. A derived field's `sort_order` only
orders it among the other derived fields.

The `field_group` column still exists, and new rows still get a guessed group
so that it has a value, but nothing orders or displays by it.

### Changing the order

- `move_form_item` moves one item up, down, to the top or to the bottom. The
  row's "More actions" menu uses it; afterwards the page says "Moved to
  position 4 of 22" and focus returns to that row's menu button.
- `reorder_form_items` takes the whole list in its new order and refuses one
  that does not name every item exactly once, so a page that missed someone
  else's change cannot half-apply its order. Dragging a row by its handle
  posts it (`components/sortable-rows.js`, using Sortable.js). The handle is
  hidden from assistive technology: the menu's move commands are the keyboard
  and screen reader route.

## Where new items go

| How it arrives                                | Where it goes                                                   |
| --------------------------------------------- | --------------------------------------------------------------- |
| "Add a question" / "Add a heading or text"    | The end of the list                                             |
| "Add a question below" / "… heading or text below" in a row's menu | Straight after that row                     |
| A new schema ("Initialise empty schema")      | Eligible, can attend, email, consent, stay on database          |
| The first CSV upload                          | Eligible, can attend and email; the CSV's columns in CSV order; consent and stay on database. A built-in column the CSV has stays where the CSV has it. No headings are added |
| A later CSV upload                            | New columns at the end, in CSV order                            |
| A question made on the target sources step    | The end of the list                                             |

## What reads the list

- **The starter form HTML** (`generate_starter_form_html[_govuk]` in
  `domain/registration_page.py`) writes the questions and blocks in list
  order. A heading is an `<h2>` (`govuk-heading-l` in the GOV.UK style); the
  text follows, with the intro's default GOV.UK classes in that style. Braces
  in both are escaped, so a block can never open a template tag: blocks carry
  no variables.
- **The respondent view and edit pages** split the fields into sections at
  each block with a heading (`sections_at_headings`). Fields before the first
  heading go under "Answers"; computed questions come last under "Computed
  questions". Text without a heading starts no section.
- **The JSON field spec** lists fields only, in list order; see
  [respondent_field_spec.md](respondent_field_spec.md).

## When the form is behind the list

The registration page's form is authored HTML that the system never rewrites,
so a change to the list does not reach a page whose form already has HTML.
`Assembly.questions_updated_at` records when the questions or the blocks last
changed - every add, edit, move and delete, including a deletion, which leaves
no row behind to compare. The form step warns when that is later than the
form HTML's `form_updated_at`.

Until the form is generated from the list automatically, the way to bring it
up to date is by hand: on the form step, Edit, clear the HTML, save, then
"Fill with accessible HTML".

## The editor for a block's text

The text is edited in the visual editor used for the intro, with a shorter
toolbar (`rich_editor_compact`): text, heading 3, bold, italic, alignment,
lists, link, undo and redo. Images and tables are not offered, and a body
holding one opens in HTML mode, but whatever is written in the HTML view is
kept. See [registration-intro-editor.md](registration-intro-editor.md).

The link dialog lives inside the block's dialog, hosted by the
`richEditorLinkHost` Alpine component, because a fragment dialog's host makes
its siblings inert while it is open.
