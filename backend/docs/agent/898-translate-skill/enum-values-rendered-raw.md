# Ticket: enum values rendered raw, so they cannot be translated

Found while fixing the assembly status badge on the backoffice Details tab,
which showed a lowercase English "active" in every language. That one is fixed;
this is the rest of the same defect, written up rather than swept into an
unrelated change.

## The defect

An `Enum` member's `.value` is a database token. Rendering it puts a string on
the page that `pybabel extract` never sees, so no catalogue can carry it and no
translator can find it. The symptom is subtle: the row _label_ is translated
(`{{ _("Status") }}` → "Állapot") and the value beside it is not, so the page
looks half-finished rather than broken, and nothing in `just check` complains.

The fix is a labels dict beside the enum, `_l()` per member, exposed to Jinja —
the pattern `global_role_labels` already establishes in
`src/opendlp/domain/value_objects.py`. Keeping it next to the enum is the point:
a member added later has a visibly missing label, and a member renamed later
cannot leave a stale label stranded in a template.

## What is already fixed

`assembly_status_labels` covers `AssemblyStatus`, and both templates that
rendered it raw now use it:

- `templates/backoffice/assembly_details.html`
- `templates/main/view_assembly_details.html`

Clearing the fuzzy flag on the `Active` msgid also fixed the admin user list,
the invite pages and the profile page, which share that entry — fuzzy entries
are dropped from the `.mo`, since `translate-compile` does not pass
`--use-fuzzy`. Worth remembering: a correct-looking `msgstr` in the catalogue is
not a translation the user will see.

## What is left

### 1. `AssemblyRole` has no short labels

`assembly_role_options` exists but holds the long form descriptions ("Assembly
Manager - Can manage the assembly and add other users"), which is why the
members tables reach for `.value` instead and render `assembly-manager`:

- `templates/main/view_assembly_members.html:21`
- `templates/backoffice/assembly_members.html:63`

Needs an `assembly_role_labels` alongside `global_role_labels`, and the two
tables pointed at it. `user_service.py:1308` uses the long options dict in an
email and is fine as it is.

### 2. `SelectionRunStatus` is translated three times, in three ways

- `templates/main/view_assembly_data.html:67-77` — a five-branch `if` chain
  emitting `_("Pending")`, `_("Running")`, … Correct output, but the mapping
  lives in a template.
- `templates/backoffice/assembly_selection.html:194,367` —
  `{{ run_record.status.value.capitalize() }}`. Untranslated.
- `templates/backoffice/components/modal.html:299` — `status_badge()` renders
  `{{ status | capitalize }}`. Untranslated, and every caller feeds it
  `run_record.status.value`, so the manage-tabs and replacement modals show
  English.

One `selection_run_status_labels` replaces all three.

### 3. The interpolated status in the progress banners

`templates/gsheets/components/progress.html:45,59` and
`templates/db_selection/components/progress.html:45,59`:

```jinja
{{ _('This page will update automatically. Current status: %(status)s', status=run_record.status.value) }}
```

The sentence is translated and the word substituted into it is not, which reads
worse than either alone. Same labels dict fixes it.

### 4. `RespondentStatus` — mostly handled, with two gaps

`table_cell_status` in `templates/backoffice/components/table.html:197` does the
right thing with an `if` chain, so this is the least broken of the set. But:

- `templates/respondents/view_respondents.html:177,186` bypass the macro and
  render `selection_status.value` and `source_type.value` raw — the latter as
  `REGISTRATION_FORM`, shouted at the user in caps.
- The macro's `else` branch falls back to `status_lower|capitalize`, so
  `TEST_SUBMISSION` — added after the chain was written — renders as
  "Test_submission" in English. This is exactly the failure a labels dict beside
  the enum prevents and an `if` chain in a template does not.

`RespondentSourceType` has no labels at all.

### 5. `task_type_verbose` builds an English sentence with string surgery

`src/opendlp/domain/assembly.py:316`:

```python
return self.task_type.value.replace("_", " ").replace("gsheet", "Google Spreadsheet").capitalize()
```

Untranslatable by construction — there is no msgid to translate, and no
word order but English's. It reaches the user in nine places: the run-history
tables in `main/view_assembly_data.html` and `backoffice/assembly_selection.html`,
and the `Task:` line in all five progress modals plus `modal.html:440`.

`SelectionTaskType` has nine members. A `_l()` per member is nine msgids and
deletes the method.

COMMENT: add a section on "stop this happening again" - this might involve updates to docs/translation.md or .claude/skills/sf-code-review/SKILL.md or maybe some other things.

## Suggested order

1 and 2 are self-contained and cover the most-seen pages. 3 falls out of 2 for
free. 5 is mechanical but touches nine templates. 4 is worth doing last, and
worth doing as a labels dict rather than by extending the `if` chain, since the
`TEST_SUBMISSION` gap is the argument against `if` chains.

## Guarding against the next one

Each labels dict should get the parametrised test that
`tests/unit/domain/test_global_roles.py` and now
`tests/unit/domain/test_assembly.py` use — iterate the enum, assert a label
exists. That catches the member-added-later case, which is how
`TEST_SUBMISSION` and `Archived` both slipped through.

It does not catch a template reaching for `.value` in the first place. A lint
step could: `{{ ...value }}` outside an HTML attribute is almost always this
bug. Worth considering for `just check` if a second round of these shows up,
though the false positives (`val.value` on target values, which is user data and
correctly untranslated) mean it needs an allowlist.

## A related thing this turned up

Rendering the details page with `Accept-Language: hu` returns Hungarian body
text inside `<html lang="en">`. If that holds outside the test client it is an
accessibility bug — a screen reader will read Hungarian with English phonemes.
Not verified against a running app, and out of scope here, but someone should
check it.
