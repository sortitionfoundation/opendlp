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

## Suggested order

1 and 2 are self-contained and cover the most-seen pages. 3 falls out of 2 for
free. 5 is mechanical but touches nine templates. 4 is worth doing last, and
worth doing as a labels dict rather than by extending the `if` chain, since the
`TEST_SUBMISSION` gap is the argument against `if` chains.

## Stopping this happening again

This defect gets past everything we have. `just check` is silent, `just
translate-check` is silent — its whole subject is the catalogue, and the defect
is that the string never reaches the catalogue — and the page looks translated
because the label beside the value is. Nothing but a person noticing "active"
in a Hungarian table found it, and only after the string had been on the page
for the life of the feature.

So the guards have to be added deliberately. Three are in place; the fourth is
the only one that would actually make it impossible, and it is not written.

### In place: the convention is written down where people look

- `docs/translations.md` has **Enum values are not translatable strings** — the
  wrong version, the labels dict, `_l()` over `_()`, the parametrised test, and
  why an `if`/`elif` chain in a template is the same defect one step on. That is
  the canonical statement; everything else points at it.
- `AGENTS.md` (which `CLAUDE.md` symlinks to) gains a third bullet beside the
  two existing msgid traps, framed as the worse case because it produces no
  msgid at all. Agents read that file and rarely reach `docs/translations.md`
  unaided, so the rule has to exist in both.

### In place: review asks the question

`.claude/skills/sf-code-review/SKILL.md` gains a bullet next to the other i18n
checks. It names the three shapes seen in this codebase
(`{{ x.status.value }}`, `{{ x.role.value }}`, `{{ x.status.value.capitalize() }}`),
says what the fix is, and — as important — says which `.value` uses are fine, so
the reviewer does not flag every `{% if status.value == 'failed' %}` in the
tree. Realistically this is the guard that will catch the next one, because it
is the only one that runs against a diff before it lands.

### In place: a test per labels dict

`tests/unit/domain/test_global_roles.py` and `tests/unit/domain/test_assembly.py`
parametrise over the enum and assert a label exists. Three lines each, and it
turns "a member added later is a `KeyError` in production" into "a member added
later fails CI". Both `Archived` and `TEST_SUBMISSION` are members-added-later,
so this is not a hypothetical failure mode — it is the one that actually
happened, twice.

It only guards enums that already have a labels dict. It cannot say anything
about an enum that has none, which is every enum in §1-5 above.

### Not written: the check that would close it

A template-side check in `just check`, alongside `scripts/check_uow_convention.py`.
The rule is nearly clean: a `.value` in a Jinja **output** expression (`{{ ... }}`)
is this bug; a `.value` in a condition, a `data-` attribute or an
`<option value="...">` is not.

The wrinkle is that `.value` is not exclusively an enum accessor here. Three
uses in templates are correct today and would all trip a naive check:

- `TargetValue.value` — a category value the person configuring the assembly
  typed ("Man", "18-24"). Rendered by `{{ val.value }}` in both
  `targets/components/category_block.html` and its backoffice twin. User data,
  and translating it would be a bug.
- `ChoiceOption.value` (`domain/respondent_field_schema.py:151`) — same story,
  rendered by `{{ opt.value }}` in `backoffice/assembly_edit_respondent.html:102`.
- `{{ vf.value.errors[0] }}` in `targets/components/category_block.html:138` —
  a WTForms field that happens to be *named* `value`. The output is `.errors[0]`;
  the `.value` is the field lookup. Nothing to do with either of the above, and
  a substring match cannot tell.

So a checker needs an allowlist, and `tests/unit/test_icons.py` is the precedent
for how that goes: useful, and something a later change quietly pads.

Two ways to make it honest:

1. Resolve the type. The templates render from known routes with known context;
   a checker that imports the domain and asks whether the attribute is an `Enum`
   member needs no allowlist at all. Considerably more work, and it cannot type
   a `{% macro %}` parameter, which is exactly where `status_badge` and
   `table_cell_status` live.
2. Narrow the rule instead of the allowlist. Every true positive so far ends in
   a status or a role, and none of the three false positives does. Measured:

   ```bash
   grep -rnE '\{\{[^}]*\.(status|role)\.value|\{\{[^}]*_status\.value' templates/
   ```

   returns 16 lines — 14 of them the defects in §2, §3 and §4, and the other
   two `data-status="{{ ... }}"` attributes, which the "output, not attribute"
   half of the rule already excludes. No allowlist, and nothing to pad.

   It is a heuristic: it would miss an enum attribute named something else, and
   it wants re-running after the fixes land to confirm it goes quiet. But a
   guard that catches the common shape and stays silent otherwise is worth more
   than a thorough one that gets padded until it catches nothing.

Worth doing when the §1-5 fixes land, not before: written now it would fail on
every one of them, and a check that ships red gets suppressed rather than
obeyed.

## A related thing this turned up

Rendering the details page with `Accept-Language: hu` returns Hungarian body
text inside `<html lang="en">`. If that holds outside the test client it is an
accessibility bug — a screen reader will read Hungarian with English phonemes.
Not verified against a running app, and out of scope here, but someone should
check it.
