# Targets and registration questions

How an assembly's targets get their data from its registration questions, what
the system promises about that pairing, and what must stay true for selection
to keep working. This is the high-level view; it names the classes so you can
find the code, and stops there. The reasoning behind each decision is in the
`docs/agent/793-*` folders.

## The problem this solves

Organisers agree targets with a client in target-shaped language: _Gender:
Woman / Man / Other; Age: 16-29 / 30-44 / 45-59 / 60+; Region: North / South_.
The registration page is a means of getting that data. But a page cannot
always ask the target's question directly: nobody answers "which age range are
you in?" reliably, and a region comes from a postcode, not from a dropdown.

So the system separates _what the target needs_ from _what the page asks_, and
records how one becomes the other. The organiser starts from the target and
says where its data will come from; the system creates the registration
question(s) and, where needed, the computation in between.

## The pieces

| Interface word        | Code                                                              | What it is                                                                               |
| --------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| target                | `TargetCategory` (`domain/targets.py`)                            | One thing selection balances on, with a list of values and per-value quotas              |
| value                 | `TargetValue`                                                     | One option within a target, e.g. `Woman`                                                 |
| registration question | `RespondentFieldDefinition` (`domain/respondent_field_schema.py`) | One column of respondent data, with a key, a type, options and where it sits on the page |
| computed question     | a `RespondentFieldDefinition` with `is_derived`                   | A question nobody answers; its value is worked out from another question's answer        |
| source question       | the field named in a computed question's `derived_from`           | The question a computed question reads                                                   |
| lookup table          | `RespondentFieldMappingEntry` rows                                | The postcode-to-value pairs behind a large mapping, stored one row per key               |
| the link              | `RespondentFieldDefinition.target_category_id`                    | Which target a question feeds, explicitly                                                |

A respondent's answers live in `Respondent.attributes`, a JSON dict keyed by
field key. Computed values are written into the same dict, so downstream code
(export, selection, the registrant page) treats them as ordinary columns.

The glossary in [language.md](language.md) fixes the interface words. Note the
split it records: the _interface_ says "question" and "computed question", the
_code_ says field and derived field. Both are correct in their own place.

## How selection pairs a target with data

This is the load-bearing fact, and it is older than everything else here.

Selection hands the sortition library two tables: targets (feature, value,
quotas) and people (one row per respondent, one column per attribute key).
The library pairs a target with a column **by name**, and a target value with a
cell **by string equality**. Nothing in the database enforces that pairing;
it is a coincidence of names that the system arranges and then guards.

Two consequences shape everything below:

- A target `Region` is fed by a column whose key is `Region`. Rename either
  side and the pairing silently breaks.
- A target value `Woman` counts a cell containing `Woman`. A cell containing
  `woman` or `Female` counts for nothing.

Case handling is currently inconsistent: the library's name and value matching
is case-insensitive, while the backoffice target counts compare values
case-sensitively, so `Male` versus `male` selects fine but shows "0
respondents". A later piece of work will make this consistent and update this
document. Until then, the link machinery below assumes verbatim equality,
which is safe under either rule.

The link (`target_category_id`) does not change how selection works. It exists
so the system can _know_ which question feeds which target, and so it can keep
the names and values equal on the organiser's behalf.

## The four ways a target gets its data

On the "Link targets to questions" step (code: `target_sources`) the organiser
picks one method per target. Each method creates or reuses a question and, for
all but the first, a computed question. The feeding question (the one whose
key equals the target name) is the one that carries the link.

| Method                | Question(s) created                                                 | Computation                                            | `DerivationType` |
| --------------------- | ------------------------------------------------------------------- | ------------------------------------------------------ | ---------------- |
| Exact copy            | one choice question whose options are the target's values           | none                                                   | –                |
| Age ranges            | a date-of-birth or year-of-birth question, plus a computed question | age on a fixed date, bucketed into the target's values | `AGE_BRACKET`    |
| Map from more options | a choice question with finer options, plus a computed question      | each option maps to one target value                   | `SMALL_MAPPING`  |
| Map postcode to value | a text question, plus a computed question                           | exact lookup in an uploaded table                      | `LARGE_MAPPING`  |

The source question can be created in the same save or an existing one reused.
Reuse matters: one postcode question typically feeds two targets (region and
deprivation quintile), and one date of birth could feed two bracketings.

Two further answers create nothing:

- **Data comes from the import.** The pool arrived by CSV with a column already
  matching the target name. Detected, not stored: the checklist reports it
  while the column exists.
- **Google Sheets assemblies** have no respondents in the database, so none of
  this applies. The registration set-up steps are replaced by one line saying
  the spreadsheet defines the fields.

The rule classes behind the three computations are `AgeBracketRule`,
`SmallMappingRule` and `LargeMappingRule` in `domain/respondent_derivation.py`.
Their parameters live in the field's `derivation_config` JSON; the large
mapping's rows live in their own table because a real table can hold over
200,000 postcodes and must not ride along on every schema read.

## What the checklist can say about a target

`target_source_status` in `service_layer/target_source_service.py` classifies
each target into one `TargetSourceState`:

| State                | Meaning                                                                                                                      |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `LINKED_EXACT`       | a directly answered choice question carries the link                                                                         |
| `LINKED_DERIVED`     | a computed question carries the link; its source is named alongside                                                          |
| `MATCHED_NOT_LINKED` | a question with the same name exists but nothing links them (built before links existed, or unlinked since); offered "adopt" |
| `IMPORT_COVERED`     | no question, but the imported data has a matching column                                                                     |
| `NONE`               | nothing feeds this target                                                                                                    |

A linked target can also be **stale**: the question's options (exact copy) or
the computed question's outputs (mappings) no longer equal the target's
values. Staleness is computed on the fly by comparing values, never stored.
"Re-sync from target" regenerates the options or outputs and recomputes the
pool. Age ranges refuse re-sync because their outputs come from the bracket
configuration, which the organiser edits instead.

The registration hub summarises this as "n of m targets covered, k stale".

## The invariants

These are what keep the pairing intact. Each is enforced somewhere; the point
of listing them is so nobody removes an enforcement without knowing why.

**A linked question's key is the target's name, verbatim.** Not normalised,
not lower-cased. `age_bracket` does not feed a target called `Age Bracket`.
Exact copy uses the name as the key; computed questions are keyed by the
target name; adopting an existing question requires a case-insensitive name
match (the most selection tolerates).

**A linked question's option values are the target's values, verbatim.** The
domain refuses type and option-value changes on a linked question
(`TargetLinkedFieldError`). Label, help text, per-option help text, section,
order, required-or-optional, and radio-versus-dropdown stay editable, because
none of them touch the pairing. The one sanctioned way to change the values is
re-sync, which copies them from the target.

**A computed question's outputs are the target's values, plus the fallback.**
The service refuses a small mapping that maps to a value the target lacks, and
an age rule whose labels are not exactly the target's values. The fallback
(`UNKNOWN` by default) is always added to the options so it round-trips
through the edit form, the export and the target counts. It is meant to read
as "needs attention".

**A computed question's type and options belong to its rule.** Nobody edits
them by hand (`DerivedFieldError`). It is never on the registration page, it
always lives in the `DERIVED` section, and no editing screen lists it: it is
reachable only through the target it feeds. This is why deleting or unlinking
its target deletes it (below).

**A source question cannot be changed underneath its computed question.**
Deleting it, or changing its type, is refused while anything derives from it
(`derivations_depending_on`). Renaming an option on a small-mapping source
renames the mapping key in step; removing an option drops the mapping entry.

**Every target is fed by at most one question.** Linking a question to a
target clears the link from any other question that had it. The reverse does
not hold: one source question can feed several targets, each through its own
computed question. A postcode question feeding both a region target and a
rural/urban target, through two lookup tables, is the case seen in practice,
but any rule type can share a source the same way.

**A source is never itself computed.** One pass, no chains. Intersection
targets (two fields combined) are out of scope for now.

## What happens when things change

**Target values added, renamed or removed.** Allowed. The linked question
becomes stale, the checklist says so, and the organiser re-syncs when ready.
Nothing cascades automatically, because target edits are often exploratory
and the authored registration HTML could not follow anyway.

**Target renamed.** A computed question follows its target: it is re-keyed,
and the values already written on respondents are re-keyed with it. A
directly answered question cannot follow (its key is the input name in the
authored HTML and the column in every export), so the rename is refused with
`TargetLinkedError` until the organiser confirms; the question is then
unlinked and left behind, editable and unlinked.

**Target deleted.** A computed question is deleted with it, along with its
lookup table and the values it wrote. A directly answered question is unlinked
and stays. Both need the organiser's confirmation first. Deleting every target
at once (a targets CSV re-import does this) goes through the same logic, and
questions feeding a target that is about to be recreated under the same name
keep their link.

The original design left a computed question behind as an editable orphan on
delete. The settled intention is what the code does now: delete it, because
no screen could reach an orphaned computed question.

**Unlink.** Same as delete for the question side: a directly answered
question is freed, a computed question is deleted.

**Source question renamed or option-edited.** See the invariants: refused, or
carried through to the mapping.

**Registration questions changed after the page HTML was written.** Nothing
regenerates the authored HTML. The editor shows a staleness warning when any
question was updated after the HTML was last saved, and the organiser pastes a
fresh skeleton. See the external assumptions below.

## When values are computed

Every path that writes a respondent runs `apply_derivations` from
`service_layer/derivation_service.py` before saving: registration submission,
CSV import, manual entry, and edit. Saving a rule (create, edit, re-sync,
lookup upload) recomputes the whole pool synchronously and returns a
`RecomputeReport` saying how many changed and how many fell back.

Precedence when a value is already present, for instance on a re-import of an
edited export: a real computed value always wins; when the computation can
only offer the fallback and a value was supplied, the supplied value survives
on import and manual write, and is overwritten on recompute and edit.

Age is worked out on a **fixed date** stored in the rule, pre-filled from the
assembly's first date. Never "today": a relative date would move people
between brackets each time the pool was recomputed. A year-of-birth source
assumes a 1 January birthday, and the set-up screen says so. Year of birth is
the recommended source for data-minimisation reasons; full date of birth is
the opt-up.

Postcode lookup is **exact match** after normalisation (upper-case, all
whitespace removed) on both upload and lookup. No prefix or outcode matching.
A non-match is meaningful: with an invite-list table it means the respondent
is outside the invited area, moved, or mistyped.

Deleted respondents are skipped by recompute. Recomputing records no comment
on the respondent. A completed selection run is not reproducible after a
recompute, since runs snapshot targets but not attributes.

The report carries the number of completed selection runs, and the "Link
targets to questions" step turns it into a warning wherever a recompute is
reported: as a warning toast after a save, re-sync or recompute, and as a
banner in the report dialog after a lookup-table upload. The warning is
skipped when the pool is empty, because then nothing was recomputed. It
warns only; it never blocks.

## External assumptions

Things outside the code that the design leans on. If one stops being true,
revisit the decision it supports.

- **Lookup tables are invite lists at full-postcode granularity**, consumed
  today by spreadsheet `vlookup`. That is why matching is exact and the row
  cap is 500,000 (a real Scotland table had 220,000 rows). If tables at
  outcode or district level appear, prefix matching is the parked answer and
  needs no migration.
- **The eligibility checkbox does the real age gating.** The registration
  page states the minimum age and the date; the age bracket is a data-quality
  backstop, not the gate. That is what makes the 1 January assumption
  tolerable.
- **The registration page is authored HTML that the system never rewrites.**
  Server-side validation follows the schema regardless of the HTML, so adding
  a required question without editing the HTML makes every submission fail.
  Rendering the page from the schema is agreed direction, not done.
- **All live assemblies are still on Google Sheets** at the time of writing, so
  the target-source flow is expected to be used on new assemblies with no
  respondents yet. The "fresh source, everyone fell back" report is therefore
  rare, and the dry-run preview was parked.
- **Sections are a fixed enum** (`RespondentFieldGroup`), shared with the
  backoffice registrant page. Free-form sections are deferred.
- **Google Sheets assemblies never get computed questions.** If a Google
  Sheets user needs a derived column, they compute it with a formula in the
  spreadsheet, not inside OpenDLP. The UI says so.
- **"Data comes from the import" is a valid, lasting way to feed a target**,
  not just a way to quieten the checklist. It is the route to derivations
  OpenDLP does not support: export the pool, compute the extra column
  elsewhere, re-import. A possible future flow automates that round trip
  through Google Sheets, exporting to one tab and reading back from a second
  whose columns hold formulas. Expect this to be supported for the long term.

## Known gaps

- Selection is **not blocked** when a lookup-table target has an empty table;
  everyone falls back and the quotas cannot be met. The copy states the
  consequence; a readiness check is a separate issue.
- Field keys are used **as typed** on the set-up screen (`Postcode` keeps its
  capital) while the questions screen normalises them. A single consistent
  normalisation pass across every entry point is planned, not piecemeal.
- The respondent field spec endpoint exposes the link as `feeds_target`; see
  [respondent_field_spec.md](respondent_field_spec.md). Changing the shape of
  any of this means updating that schema and fixture too.

## Where to look

- `domain/respondent_field_schema.py`: the field, its lock errors, `DerivationType`
- `domain/respondent_derivation.py`: the three rules, label parsing, key normalisation
- `domain/targets.py`: `TargetCategory`, `TargetValue`
- `service_layer/target_source_service.py`: configure, status, adopt, re-sync, unlink
- `service_layer/derivation_service.py`: computing, recompute, lookup upload, source protection queries
- `service_layer/target_service.py`: the rename and delete guards, `TargetLinkedError`
- `service_layer/respondent_field_schema_service.py`: field edits and what they refuse
- `entrypoints/blueprints/target_sources.py`: the "Link targets to questions" step
- `adapters/sortition_data_adapter.py`: how targets and respondents reach the library
- `docs/agent/793-derived-fields/`, `793-two-step-fields/`, `793-large-mapping-flow/`,
  `793-small-mapping-flow/`, `793-registration-tweaks/`: the research and decisions
