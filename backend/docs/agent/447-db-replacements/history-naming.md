# Plan: friendlier names in the Selection History list

**Status:** decided, implementation in progress. The questions below are kept
with their answers so the reasoning survives; the steps at the end track the
work.

**Branch:** `447-db-replacements-2`. It touches the run history, the reset,
and the task type labels.

## The idea

Today the history table's "Task Type" column shows the task type label:
"Select from database", "Test select from database", "Select replacements from
database". That says what kind of code ran, not what the run meant to the
organiser. The proposal is to name each run by its place in the story:

| Run                                                          | Name                                        |
| ------------------------------------------------------------ | ------------------------------------------- |
| Most recent test or full selection                           | Initial selection / Test selection          |
| Older full selection                                         | Initial selection (previous)                |
| Older test selection                                         | Test selection (previous)                   |
| Replacement run after the most recent test or full selection | Replacement selection (round X), X from 1   |
| Replacement run older than that                              | Replacement selection (round X, previous)   |
| Failed or cancelled run of any kind                          | Initial selection (failed), and so on       |
| Reset all to pool                                            | Reset all to pool                           |

And a row for each "reset all to pool", so the history reads as a timeline.
By default the list shows only the current era, that is the most recent
initial or test selection and everything after it, with a toggle to show the
whole history.

## What is there today

- **The history table** is `templates/backoffice/assembly_selection.html`, two
  copies (database source around line 180, Google Sheets source around line
  350), fed by `selection_run_records.get_by_assembly_id_paginated`, 15 per
  page, newest first. The legacy page `templates/main/view_assembly_data.html`
  lists the same records.
- **Labels** come from `selection_task_type_labels` in
  `domain/value_objects.py` via `SelectionRunRecord.task_type_verbose`, which
  the modals' "Task:" line also uses.
- **A reset leaves no trace.** `reset_db_selection` calls
  `respondent_service.reset_selection_status`, which runs one bulk UPDATE
  (`reset_all_to_pool`): status back to POOL, `selection_run_id` cleared. No
  run record, no respondent comment, no log line beyond the flash message. The
  only evidence a reset happened is that a later initial selection exists.
- **A respondent remembers which run selected it** (`selection_run_id`), but a
  reset or a manual move back to the pool clears it, so the respondent side
  cannot reconstruct history either.
- **"Since reset" is a guess.** Nothing in the data says a reset happened
  between two initial selections. Today a second initial selection implies one
  (the page hides the run buttons while anyone is held, and the planned
  service guard in [guard-initial-selection-plan.md](guard-initial-selection-plan.md)
  enforces it). The exception is when everyone selected has withdrawn or been
  deleted: held count is zero, a fresh initial selection is allowed, and no
  reset ever happened.
- **Failed and cancelled runs** sit in the same list. A failed or cancelled
  initial selection writes no statuses (`_internal_write_db_results` only runs
  on success), so it does not start a new "era", but it still needs a name.
- **Other readers of the records** that a new task type would touch:
  `get_active_initial_selection_run_id` (looks at the latest record and its
  type), `DB_SELECTION_TASK_TYPES` (download buttons), the monitor
  (Google Sheets types only, unaffected), and the pruning task (monitor
  assembly only).
- **`task_type` is stored as a string** (`EnumAsString`), so a new task type
  needs no migration.

## The model: eras

Every proposed name is "which era is this run in, and what is it within the
era". So the core is one pure function:

1. Take the assembly's runs in `created_at` order.
2. A **completed** initial or test selection starts a new era, and so does a
   reset. (Failed and cancelled ones do not, see Q3.)
3. Within an era, completed replacement runs are numbered 1, 2, 3 in order.
4. The newest era is "current"; completed selection runs in older eras get the
   "(previous)" suffix.

A reset starting an era means that after a reset, before the next initial
selection, the current era holds just the reset row. That is what the
organiser sees by default (Q7), which is right: the slate is clean.

This lives in the service layer as `name_history(summaries)`, returning the
name for every run keyed by task id and the start of the current era. The
page route passes the names to the template alongside the paginated rows.

**It must see the whole history, not the page.** Round numbers and "which era
is current" depend on runs that may be on another page. Options:

- **(a) Load every record for the assembly.** `get_by_assembly_id` exists. The
  records carry `selected_ids`, `remaining_ids`, `log_messages` and the run
  report as JSON, so for a long-lived assembly this is a lot of bytes to name
  15 rows.
- **(b) A lean repository query** returning `(task_id, task_type, status,
  created_at)` for the assembly. One more repository method and fake, but the
  naming function then takes a small tuple type and the cost is flat.

Decision: (b). The first draft recommended (a), but the modal's "Task:" line
needs the name too (Q1), and the modal is re-rendered by HTMX polling every
few seconds while a run is in flight. Loading every record's run report on
each poll is the wrong trade. The lean query is `get_history_summaries` on
the run record repository, returning `RunSummary` objects (a frozen dataclass
in the domain), oldest first.

## Q1. Is this a rename of the Task Type column, or a new column?

- **(a) Replace the label in the column** and rename the header to
  "Selection". The Google Sheets types ("Load from Google Sheets", "List old
  tabs") keep their current labels since the era model only applies to
  selections.
- **(b) Add a "Name" column** and keep "Task Type". More honest, but the table
  already has seven columns and the type label repeats what the name says.

Decision: (a). Also use the name on the modal's "Task:" line so the history
row and the modal agree.

## Q2. What does "(since reset)" say when there was no reset?

The suffix asserts something the data cannot know. Options:

- **(a) Keep "(since reset)"** and accept the edge case where everyone
  withdrew. Rare, and the organiser knows what they did.
- **(b) Make it true**: record the reset (Q5), and only say "(since reset)"
  when a reset record sits between the run and now. A superseded era with no
  reset gets a different word.
- **(c) Pick a word that is true either way**: "(earlier)", "(superseded)",
  "(previous)". For example "Initial selection (previous)",
  "Replacement selection (round 2, previous)". Reads less like a reason and
  more like a position, which is what we actually know.

Decision: (c), with "previous". The reset row (Q5) makes the reason visible in
the timeline without the name having to carry it.

## Q3. Do failed and cancelled runs start eras or take round numbers?

- A failed **initial** selection changed nothing, so it should not start an
  era.
- A failed **replacement** run: does it consume a round number? If yes, the
  organiser sees "round 2 (failed)" then "round 3" and wonders where 2 went.
  If no, two rows both say "round 2", one failed and one completed.

Decision: failed and cancelled runs neither start eras nor take round
numbers. They are named with their status instead: "Initial selection
(failed)", "Replacement selection (cancelled)". They get no "(previous)"
suffix; the status is the more useful word, and the Status column agrees.
Pending and running runs carry the bare name ("Replacement selection") and
get their number once they complete.

## Q4. Do the same rules apply to Google Sheets assemblies?

Google Sheets has no reset and no statuses in our database, but it has the
same shape of history: `SELECT_GSHEET` / `TEST_SELECT_GSHEET` then
`SELECT_REPLACEMENT_GSHEET` rounds. The era model works unchanged, minus the
reset row. `LOAD_GSHEET`, `LOAD_REPLACEMENT_GSHEET` and the tab tasks keep
their labels.

Decision: apply the same naming. The function is type-agnostic once it knows
which types are "initial" and which are "replacement". Note that the existing
`_INITIAL_SELECTION_TASK_TYPES` in `service_layer/sortition.py` is not that
set: it includes `SELECT_REPLACEMENT_FROM_DB` and `LOAD_GSHEET`, because its
job is "which runs swap the buttons for View Running Selection". The naming
gets its own sets.

## Q5. Should a reset appear in the history?

Chewie's suggestion: the reset produces a `SelectionRunRecord` and shows up
like any other row.

**For:** the history becomes a true timeline. The reset gets a who and a when,
which it has nowhere today. The "Reset %(count)s respondents" number goes in
the record's log messages so it is kept.

**Against, or at least to handle:**

- `SelectionRunRecord` is built for background tasks: `celery_task_id`,
  `progress`, `settings_used`, polling. A reset is synchronous. The record is
  created COMPLETED in the same transaction as the bulk update, with an empty
  celery id. Nothing breaks, but it is a slightly odd fit.
- The history row's View link opens the progress modal, which shows a
  task type, status, messages and the Selected section. For a reset there is
  nothing to select and no report. Decision: no View link, the row is the
  record.
- `get_active_initial_selection_run_id` reads the latest record; a reset
  record is finished and not in the initial set, so it returns None, which is
  right. Add the new type to no existing set, and add a test that says so.
- `DB_SELECTION_TASK_TYPES` gates download buttons; a reset is not in it.
- The two legacy pages (`view_assembly_data.html`, the GOV.UK `db_selection`
  templates) list records with `task_type_verbose`, so a reset shows there as
  "Reset all to pool" and needs nothing else.
- Tests that count run records for an assembly after a reset (component and
  BDD) will need one more row.

**Alternative:** record the reset somewhere else, such as an audit comment on
each respondent (`RespondentAction.STATUS_CHANGE`, as the manual path does).
That is the right thing for the respondent's own history and is worth doing
anyway, but it is N rows for one event and still gives the Selection History
nothing to show. The two are not exclusive.

Decision: add `SelectionTaskType.RESET_TO_POOL` (label "Reset all to pool"),
created by `reset_selection_status` in the same unit of work. Keep the
respondent comments as a separate, later change.

## Q6. Wording and glossary

[docs/language.md](../../language.md) has "selection", "test selection" and
"replacement selection" but not "initial selection"; the page already uses
"initial selection" in running text, so add it to the glossary. Table cells
are sentence case: "Initial selection", "Replacement selection (round 2)".

Review item G4 noted that "test selection" confuses users. Decision: there is
no better name yet, so "test selection" stays as it is for this round.

Translatable strings. The base names are one msgid each, and the suffixes
are format strings that take the base name, so a translator can move the
parenthetical or inflect around it:

- `_("Initial selection")`, `_("Test selection")`,
  `_("Replacement selection")`, `_l("Reset all to pool")`
- `_("%(name)s (previous)")`, `_("%(name)s (failed)")`,
  `_("%(name)s (cancelled)")`
- `_("%(name)s (round %(round)s)")`, `_("%(name)s (round %(round)s, previous)")`

## Q7. Hide everything before the current era by default

Chewie's idea: runs before the most recent reset are generally practice runs
and not of interest, so hide them by default behind a toggle.

Decision: yes. The default list shows the current era only: the record that
started it (the most recent completed initial or test selection, or the most
recent reset, whichever is later) and everything after it. A link in the
history card switches between "Show all runs" and "Show current selection
only"; it is only offered when there are older runs to show. The choice is a
query parameter (`history=all`) so pagination links and reloads keep it, and
nothing is stored.

Mechanics: `get_by_assembly_id_paginated` grows an optional `since` datetime
and returns only records created at or after it. The route computes the era
start from the summaries it already loads for naming, and passes `since` only
in the default view. The pagination macro appends `page` to whatever base
URL it is given, so the base URL carries `history=all` when needed.

Consequences: in the default view the "(previous)" suffix never appears, since
older eras are hidden. It still earns its keep in the full view. An assembly
with no completed selection and no reset has no era start, so the default
view shows everything and no toggle.

## Steps

1. [x] Domain: `RESET_TO_POOL` task type and label; `RunSummary` dataclass.
   `reset_selection_status` adds the record with the count in its log
   messages. Repository: `get_history_summaries` on the run record repository
   (SQL and fake), and `since` on `get_by_assembly_id_paginated`. Tests:
   integration test for the service, component test for the route, contract
   tests for both repository changes, unit test that the reset record does
   not count as an active initial selection.
2. [x] Service: `name_history(summaries)` pure function implementing the era
   model with the Q2, Q3 and Q7 decisions. Unit tests cover: single initial
   run; two initial runs; replacement rounds numbering; failed runs not
   numbered; running runs unnamed-but-labelled; Google Sheets types; a reset
   between eras; a reset after the last selection; non-selection types
   untouched; current era start.
3. [ ] Route and templates: `render_selection_page` names all runs for the
   assembly, passes `run_names` keyed by task id, and applies the default
   filter and toggle. The history column uses the name, header renamed to
   "Selection", reset rows have no View link. The modal "Task:" line uses the
   name on both the page and the HTMX fragment routes. Component tests on
   the page; update `tests/bdd/test_selection_history.py` for the header.
4. [ ] Language doc and translations: glossary entry, `just translate-regen`.

## Out of scope, noted

- Respondent-level audit comments for a reset.
- Renaming "test selection".
- Any change to how the Google Sheets replacement tabs are named.
