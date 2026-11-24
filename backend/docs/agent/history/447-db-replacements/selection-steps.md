# Plan: the Selection tab as two numbered steps

**Status:** implemented on `447-db-replacements-2`, 2026-10-05.
**Figma:** [full panel](https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=5628-13006)
and [partly filled panel](https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=5689-13386).

## What the design says

The Initial Selection and Replacement Selection cards become two rows in a
vertical numbered list, joined by a connector, like the set-up steps on the
Registration tab. Each row has the step number, a title and a one-line
description, and its actions right-aligned. The Initial selection row also
carries a status panel: "Number to select" and "Selected or confirmed", green
with a tick when every place is filled and amber with a warning when it is not.

The brief that came with the links:

- **Google Sheets** assemblies keep "Check Spreadsheet". OpenDLP cannot read the
  spreadsheet's state quickly, so the organiser can start an initial, test or
  replacement selection whenever they like and OpenDLP does what it is told.
- **CSV / database** assemblies never show "Check Data": the check happens
  implicitly where it is needed. The Figma still shows the button; it is being
  removed there.
  - An initial or test selection can run only when nobody is selected or
    confirmed.
  - While anyone is selected, "Reset selected people" is available.
  - A replacement selection can run only when some people are selected or
    confirmed, but fewer than the number to select.

## Decisions

**D1. Counts are of people holding a place.** Every rule above is on the
selected-plus-confirmed count (`count_held_respondents`), not on the count
outside the pool. Withdrawn people and test submissions do not block an
initial selection. This is the same call as the planned service-layer guard
([guard-initial-selection-plan.md](guard-initial-selection-plan.md)); the page
and the guard now agree. The non-pool count is no longer read by the page.

**D2. The status panel has three looks, not two.** Figma shows full (green)
and partly filled (amber). Before any selection, when nobody holds a place,
the panel is neutral: the same subtle box the old card used, with no icon.
Amber-with-a-warning for "nobody selected yet" would nag before anything has
gone wrong.

**D3. "Number to select" keeps its Edit link,** in the status panel. Figma
does not show it, but the edit dialog exists and the BDD scenario "User can
edit number to select from selection tab" uses it.

**D4. Existing labels keep their msgids.** "Initial Selection", "Replacement
Selection", "Run Selection", "Run Test Selection", "Reset Selected People" and
"View Running Selection" are already translated. Figma writes them in sentence
case; rewording them would discard the translations for a change of case, which
`docs/language.md` says not to do in passing. The case sweep is a job of its own.

**D5. The replacement button says "Select replacements".** Figma's "Run
replacement" is a prefix of the dialog's "Run Replacement Selection", and
Playwright's role lookup matches names by substring, so the two would collide
in the BDD steps once the dialog is open. "Select replacements" follows the
glossary (the process selects replacements; the people are the replacements)
and does not collide. It replaces "Go to Replacement Selection" on both the
database and the Google Sheets rows.

**D6. A disabled replacement button says why.** The row's second line explains
the state (run the initial selection first; every place is filled; wait for
the running selection) and is linked to the button with `aria-describedby`.
The three sentences already exist as msgids.

**D7. Reset is hidden while a run is active.** The brief says reset is always
possible while anyone is selected. While an initial or replacement selection
is writing statuses, a reset would race it, so the row shows only "View
Running Selection" until the run finishes. Flagged for Hamish.

**D8. The `check_db_data` route stays.** The legacy page still posts to the
legacy copy, and the backoffice route has tests. Only the button goes. Running
the check implicitly before a selection is separate work.

## What changed

- `static/backoffice/src/main.css`: `.selection-step`, a static row next to
  `.setup-step`, which is a whole-row link.
- `templates/backoffice/components/selection_steps.html`: the two rows, with
  the database and Google Sheets branches inside.
- `templates/backoffice/assembly_selection.html`: both source branches include
  the partial in place of the two cards.
- `entrypoints/blueprints/gsheets.py::render_selection_page`:
  `replacement_enabled` uses the held count against `number_to_select`; the
  non-pool count is gone.
- Tests: component tests for each state of the two rows; BDD steps click the
  new button name.
