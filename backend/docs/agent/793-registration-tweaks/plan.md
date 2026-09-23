# Age range set-up: making the modal readable

Plan for reworking the age-range (`DerivationType.AGE_BRACKET`) part of the
"Set up / Edit the question for …" modal, reached from **Link targets to
questions** (`/backoffice/assembly/<id>/target-sources`). It also covers
tighter validation of `FieldType.DATE` answers on registration pages.

Status: **agreed, not yet implemented**. Decisions from review are in §8.

---

## 1. What the code does today

Files involved:

| Concern | File |
|---|---|
| Modal template | `templates/backoffice/target_sources/_setup_modal.html` |
| Modal context, prefill, parsing glue | `src/opendlp/entrypoints/blueprints/target_sources.py` (`_setup_modal_ctx`, `_apply_age_prefills`, `_seed_from_derivation`, `_setup_values_from_request`) |
| Form → rule | `src/opendlp/entrypoints/derivation_form_parser.py` (`parse_age_rule`, `age_prefill_from_target`) |
| The rule | `src/opendlp/domain/respondent_derivation.py` (`AgeBracketRule`, `age_brackets_from_labels`, `MAX_SANE_AGE = 120`) |
| Live preview | `src/js/components/age-bracket-preview.js` (+ `.test.js`) |
| Stale check | `src/opendlp/service_layer/target_source_service.py` (`_stale_for_derived`) |
| DATE answer validation | `src/opendlp/domain/validators.py` (`validate_date_field`, `_MAX_DATE_FIELD_AGE_YEARS = 120`) |

### How an age rule works now

`AgeBracketRule(as_of_date, min_age=16, max_age=100, boundaries=(…))`
**generates its own labels**: `under-16`, `16-24`, …, `100+`. Those labels
become the derived question's options, and the derived values are those
labels.

The selection compares respondent values with target values as **exact
strings**. So the only way an age rule feeds a target is if the target's values
happen to be spelt exactly `under-16`, `16-24`, `100+`. Consequences:

- A target of `16-29, 30-44, 45-59, 60+` can **never** be fed without mismatch:
  the rule always emits a `100+` label and an `under-16` label as well, and
  `_stale_for_derived` compares the output set with the target's value set, so
  the link shows as stale.
- `age_brackets_from_labels` only recognises the exact `under-N`, `N-M`, `N+`
  shapes. `16 - 29`, `16–29` (en dash), `16 to 29`, `60 or over` all fail, and
  the inputs fall back to 16 / 100 / blank.
- `min_age <= 0` is rejected ("must be greater than zero"), so a `0-15` bracket
  is impossible.

**This is the key finding, and it changes the scope of the brief.** Relaxing the
parser is not enough by itself: even if we understand that `60 or higher` means
"60 and over", the rule would still emit the string `60+`, which doesn't equal
`60 or higher`, so nobody would be counted. The rule has to emit **the target's
own value strings**. That means changing what the rule stores (§3).

### Other things I found

- `MAX_SANE_AGE = 120` already sends impossible ages (a typo'd 1880) to
  `UNKNOWN` during derivation. `validate_date_field` already refuses a DATE
  answer more than 120 years ago, or in the future. So the "100+ as a bad-data
  check" is **already handled in two places**, and dropping `max_age` loses
  nothing.
- `AgeBracketRule.eligibility_sentence()` has no callers. It gets deleted.
- The year-of-birth caveat ("assume a 1 January birthday…") only shows when an
  *existing* integer question is picked. It doesn't show when you create a new
  question with "Year of birth" selected. That's a small bug, and the regrouping
  fixes it (§2).
- The target values are printed twice in age mode: "Target values: …" at the
  top and "The target expects: …" lower down.
- `info_icon` shows its text only as a `title` tooltip plus `sr-only` text. It
  isn't focusable, so keyboard-only and touch users can't read it. That's being
  worked around here (§5), and the component fix is logged in
  `docs/agent/793-two-step-fields/future-work.md`.
- A year-of-birth answer (`FieldType.INTEGER`) gets **no** range check at all on
  submission. `validate_integer` accepts 1880, or 3025. Fixed in §6.

---

## 2. Grouping the form

The grouping applies to **all four methods** (exact copy, age ranges, map more
options to fewer, map postcode to value). Each group is a `<fieldset>` with a
`<legend>` heading. Groups are separated by the divider the codebase already
uses (`border-top: 1px solid var(--color-borders-dividers)` with `pt-4`, as in
`assembly_details.html`), not cards. The modal panel is already a card, and the
fieldsets give screen readers the grouping for free.

1. **How is the data collected?** The method select, its help line, and the
   target values. The target values are printed once only, here.
2. **Which question collects the source value?** Reuse/create radios, then the
   existing-question dropdown **or** name + label (+ date/year radios for age).
   For age, the year-of-birth caveat moves here and shows whenever the source is
   a year, whether reused or new.
3. **Method-specific detail**, only where the method has any:
   - age ranges: **Age ranges**, the target-value matching (§3/§4)
   - map more options to fewer: the existing answer → target value table
   - map postcode to value: the existing upload block
   - exact copy: no third group
4. **Respondent age calculated on**: age only, last (§5).

Within each group the existing markup and behaviour stay as they are. For the
three non-age methods, the change is moving blocks into fieldsets and adding
dividers, nothing else.

Rough layout, with brackets auto-matched and a date already known:

```
┌ Set up the question for Age ─────────────────────────────── ✕ ┐
│ How is the data collected?                                    │
│ [ Age ranges                                  ▾]              │
│ Ask for a date or year of birth and compute the age range     │
│ Target values: 16-29, 30-44, 45-59, 60+                       │
│ ───────────────────────────────────────────────────────────── │
│ Which question collects the source value?                     │
│ ( ) Use an existing question  (•) Create a new question       │
│ New question name [date_of_birth]  Label (optional) [      ]  │
│ What is asked for?  (•) Date of birth  ( ) Year of birth      │
│ ───────────────────────────────────────────────────────────── │
│ Age ranges                                                    │
│ Each target value is matched to these ages:          [Edit]   │
│   16-29 ........... 16 to 29                                  │
│   30-44 ........... 30 to 44                                  │
│   45-59 ........... 45 to 59                                  │
│   60+ ............. 60 and over                               │
│ Anyone younger than 16 counts as UNKNOWN.                     │
│ ───────────────────────────────────────────────────────────── │
│ Respondent age calculated on 12 March 2027 (i)  [Change]      │
├───────────────────────────────────────────────────────────────┤
│                                          [Cancel]  [Save]     │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. The rule model: one "from" age per target value

Replace `min_age` / `max_age` / `boundaries` with an ordered list of brackets.
Each bracket is a **target value** plus the **age it starts at**:

```python
@dataclass(frozen=True)
class AgeBracket:
    from_age: int   # >= 0
    label: str      # a target value, verbatim

@dataclass(frozen=True)
class AgeBracketRule:
    as_of_date: date
    brackets: tuple[AgeBracket, ...]   # sorted by from_age, unique from_ages, >= 1
    fallback: str = DEFAULT_FALLBACK
```

Derivation: ages below the lowest `from_age` give the fallback. Otherwise the
age gets the bracket with the highest `from_age` <= age. The top bracket is
always open-ended. `MAX_SANE_AGE` still sends ages over 120, and negative ages,
to the fallback.

Why this shape:

- **Outputs are target values by construction.** The mismatch warning, the
  `under-N` / `N+` synthesis and the "these brackets don't match the target"
  paragraph all go away. `output_options` returns the labels.
- **Gaps and overlaps can't be stored.** Each bracket runs up to the next one's
  start.
- **Zero is allowed** (`from_age >= 0`), which covers `0-15`.
- **No maximum.**
- **It handles labels no parser will ever understand.** A target of `Young
  people / Adults / Older people` can still be set up by typing three numbers.
- The "minimum age" is simply the lowest `from_age`. With an `under-X` / `0-Y`
  bottom bracket, that's 0, so everyone young gets that bracket.

Stored config: `{"as_of_date": "...", "brackets": [{"from_age": 16, "label":
"16-29"}, ...], "fallback": "UNKNOWN"}`. The respondent-field-spec JSON schema
already types `derivation_config` as a free-form object, so the API fixture
doesn't change shape.

### Existing configs: delete them with a data migration

Nothing live uses age ranges, only demo assemblies. So there's **no legacy
reader**: `from_config` understands the new shape only. A data migration
deletes every existing age-range derived field instead, and the demo assemblies
get set up again through the modal.

I checked that this leaves nothing broken. The migration does in SQL what
`target_source_service.unlink` already does to a derived field (via
`respondent_field_schema_service.delete_derived_field`), and that's a state the
app already produces and handles:

- **The field row.** `DELETE FROM respondent_field_definitions WHERE
  derivation_type = 'age_bracket'`. `respondent_field_mapping_entries` cascades,
  though age fields have none.
- **The values it wrote.** Each respondent in that assembly loses the
  `attributes[<field_key>]` it holds. This uses the same `json_each` /
  `json_object_agg` rewrite as `_REMOVE_ATTRIBUTE` in `sql_repository.py`
  (`attributes` is `JSON`, not `JSONB`, so there's no `-` operator). Without
  this, a stale column would linger in the respondent export.
- **The target.** The category the field fed loses its only linked field, so
  **Link targets to questions** shows it as "not set up". That's the ordinary
  state before anyone links it.
- **The source question** (`date_of_birth` / `year_of_birth`) stays. It's a
  normal question on the registration page. Re-running set-up can reuse it, so
  existing answers aren't lost.
- **Nothing else refers to a derived field.** A derived field can never be the
  source of another (`compatible_source_fields` excludes derived fields), and
  derived fields are never on a registration form (`registration_hub.py` counts
  only non-derived fields).
- Setting up the field again derives values for existing respondents, as it
  does for any new link.

The downgrade is a no-op, since deleted config can't be restored. That's
acceptable for demo data. The migration is made with
`uv run alembic revision -m "delete age range derived fields"`. It's a data-only
migration, so it isn't autogenerated.

---

## 4. Matching target values to ages automatically

The parser produces a `from_age` for each target value. It lives in the domain
beside the rule, and replaces `age_brackets_from_labels`.

### Rules

Count the whole numbers (`\d+`) in each label:

| Numbers in label | Meaning | Examples |
|---|---|---|
| 2 | a range `a`–`b` | `16-29`, `16 - 29`, `16–29`, `16—29`, `16 to 29`, `16 bis 29`, `16-29 év`, `Aged 16 to 29` |
| 1 | an open end; which end is decided by **position** | `under 16`, `under-16`, `<16`, `60+`, `>59`, `60 or higher`, `over 59` |
| 0 or 3+ | not an age, so no auto-match | `Prefer not to say` |

Counting numbers, not "starts and ends with digits", so `16-29 years` and
`Aged 16 to 29` are accepted too. It needs no list of separators (`-`, `–`,
`—`, `to`, `bis`, `a`, `és`…), so other languages come free.

**Position, not keywords, for one-number labels.** After sorting the ranges:

- A one-number label whose number is <= the lowest range's start is the
  **bottom** bracket: `from_age = 0`. So `under 16` or `<16` next to `16-29` → 0.
- A one-number label whose number is the highest range's end or end + 1 is the
  **top** bracket: `from_age = highest end + 1`. So `60+`, `60 or higher`,
  `over 59` and `>59` all become 60 when the highest range is `45-59`.

That handles `>59` without trying to read `>`. There's no English keyword
list, so it works in Hungarian too.

- A range starting at 0 (`0-15`) is just a bracket from 0.
- The **highest** range is always treated as open-ended. `60-99` and `60-100`
  become "60 and over".
- The ranges must be **contiguous** (each start = previous end + 1). A gap
  (`16-29`, `31-44`) or an overlap is not auto-matched. Silently putting 30-year-olds
  into `16-29` would be wrong.

We don't try to settle every case. Where position can't decide (e.g. only
`under 30` and `30+`, with no range to anchor them), there's no auto-match, and
the organiser types two numbers.

### When auto-matching fails

The form opens in the editable table (below), pre-filled with whatever *could*
be parsed, with one line saying why. Messages are kept modest. Give a specific
reason for the two cases the contiguity check spots directly:

- a gap: "The target values leave out age 30" (or "ages 30 to 34")
- an overlap: "Age 30 is in more than one target value"

For everything else (no numbers, too many numbers, a one-number label that
can't be placed), use one generic line: "Could not work out age ranges from the
target values. Enter the age each one starts at, or change the target values
to look like 16-29, 30-44, 45-59, 60+."

### Minimum age and "younger than that"

- If the target has a bottom bracket (`under 16`, `0-15`), people younger than
  16 get that bracket's value, so they're counted as under-16s.
- If it doesn't, people younger than the lowest range get `UNKNOWN`. Agreed:
  the registration eligibility question should stop under-age registrations
  anyway, so sharing a bucket with bad data is acceptable.

Both fall out of the model with no special case.

### What the organiser sees

- **Matched:** the summary table in §2 (target value → "16 to 29" / "60 and
  over") and an **Edit** button. Edit reveals the editable table in place (an
  Alpine toggle, with no server round trip).
- **Editing / not matched:** one row per target value, with a **From age**
  number input and a computed "to" column that updates as you type:

  ```
  Target value   From age   Ages
  16-29          [16 ]      16 to 29
  30-44          [30 ]      30 to 44
  45-59          [45 ]      45 to 59
  60+            [60 ]      60 and over
  Anyone younger than 16 counts as UNKNOWN.
  ```

  Validation: **every target value needs a from age**, whole numbers >= 0, no
  two the same. Requiring every row keeps `_stale_for_derived` unchanged
  (outputs == target values).

- **Across HTMX re-renders** (e.g. flipping date/year of birth), the Edit toggle
  isn't kept. The server re-decides: summary if every row is valid, table
  otherwise. So an organiser who opened Edit, changed nothing and flipped the
  radio sees the summary again. That's fine.

**JS.** `age-bracket-preview.js` mirrors `bracket_labels()`, which goes away. It
is **rewritten** (agreed) as a component that computes the "to" column and the
"younger than" line from the from-age inputs, and owns the Edit toggle. It's
about the same size as the current one, and its vitest file is rewritten with
it.

---

## 5. "Respondent age calculated on"

- Moves to the bottom, as group 4 with a divider above it.
- Renamed **Respondent age calculated on**. That's a new msgid, so the old
  string's translations are dropped. That's fine: it's a real rewording.
- **Value known** (saved, or seeded from the first assembly date, and valid):
  one line of text, `Respondent age calculated on 12 March 2027 (i) [Change]`.
  The date is formatted with `flask_babel.format_date(…, "long")`, as
  `date_text` does. **Change** is a `<button type="button">` whose accessible
  name says what changes ("Change the date respondent age is calculated on",
  the GOV.UK summary-list pattern). It reveals the three inputs and moves focus
  to Day.
- The three inputs are always in the form, hidden with `x-show` while in text
  mode, so their values still submit. No duplicate hidden inputs.
- **No value, or an invalid one** (including after a failed save): the server
  renders the inputs straight away, with `DD` / `MM` / `YYYY` placeholders to
  match the starter registration form (commit `c2de4167`).
- Help text: "Usually the first assembly date. Ages are worked out on this one
  date, so they don't change while registration is open." Where it shows:
  - **Text mode:** in the `info_icon` beside the date.
  - **Inputs showing:** as a normal visible hint under the legend, tied to the
    inputs with `aria-describedby`. No icon.

  That way keyboard and touch users can read it whenever they can act on it.
  The proper `info_icon` fix (a focusable toggletip) is written up in
  `docs/agent/793-two-step-fields/future-work.md`.
- The "as-of year must be within a year of today" check **stays**. It catches
  the silent typo that would put everyone in `UNKNOWN`.

---

## 6. Validating DATE and year-of-birth answers on registration pages

### DATE answers

`validate_date_field` already rejects dates in the future ("Date cannot be in
the future") and more than 120 years ago ("Please check the year"). **Keep the
rolling 120 years.** It's stricter than "year <= current year" at the top end,
slightly stricter than a fixed 1900 at the bottom, and never needs revisiting.

**Improve the message.** "Please check the year" doesn't say what's wrong.
GOV.UK's date-input guidance names the limit: "[Date of birth] must be the same
as or after 1 January 1906". The validator doesn't know the question's label,
and threading it through isn't worth it here. So use generic wording that names
the limit, with the date computed and formatted for the locale: "The date must
be on or after %(date)s". The future-date message stays "Date cannot be in the
future", which already says what's wrong.

### Year-of-birth (INTEGER) answers

**Add a range check for integer answers to a question that is the source of an
age rule**: the year must be between (this year − 120) and this year, with the
message "The year must be between %(earliest)s and %(latest)s".

Implementation: the submission service (`registration_submission_service.py`,
`_validate_field_value`) already has the assembly's field definitions to hand.
It works out the set of field keys named in `derived_from` by an `AGE_BRACKET`
field, and applies the check to INTEGER answers for those keys. The limits live
beside `_MAX_DATE_FIELD_AGE_YEARS` so DATE and year share one number. Ordinary
integer questions (number of children, say) are unaffected.

### Client-side JS

**Not doing it.** GOV.UK Frontend has no client-side validation, and the Design
System's advice is to validate on the server. The registration form is
organiser-editable HTML, so any script would have to guess which inputs are
dates. The form already round-trips on submit and shows the server's message by
the field.

---

## 7. Implementation outline

TDD, in this order:

1. **Domain:** `AgeBracket`, the reworked `AgeBracketRule` (validation,
   derivation, `to_config` / `from_config`), and the label parser replacing
   `age_brackets_from_labels`, returning either the brackets or a failure
   reason (gap / overlap / generic). Delete `eligibility_sentence` and
   `bracket_labels`. Unit tests: every label variant in the §4 table, en/em
   dashes, `bis` / `év` suffixes, gaps, overlaps, 0-starting ranges, `>59`,
   ambiguous single-number pairs, and derivation at every boundary, including
   ages 0, over 120 and negative.
2. **Data migration:** delete age-range derived fields and the respondent
   attributes they wrote (§3). Test: a migration test, or a component test that
   runs the migration's SQL against a seeded assembly, checking the field and
   attribute are gone, and that the source question and target category
   survive. Check what `tests/` already does for data migrations before
   choosing.
3. **Form parser:** `parse_age_rule` reads a `bracket_label` list and a parallel
   `bracket_from` list, like `map_source` / `map_target`. Tests in
   `tests/unit/test_target_source_parsers.py`.
4. **Blueprint:** `_setup_values_from_request`, `_seed_from_derivation`,
   `_apply_age_prefills` and `_setup_modal_ctx` produce bracket rows, the
   matched/editing flag, the failure reason and the as-of display flag. Drop
   `preview_labels` / `mismatch_labels`, and the `min_age` / `max_age` /
   `boundaries` keys.
5. **Template:** the four groups for all methods, the summary/table toggle, the
   as-of text mode and the hint/icon split. Component tests in
   `tests/component/test_backoffice_target_sources.py` for: fieldsets present
   for each method, auto-matched summary, unmatched table with reason, text vs
   inputs for as-of, error re-render opening the inputs, and the year-of-birth
   caveat showing for a new year-of-birth question.
6. **JS:** the rewritten preview component and its vitest tests.
7. **Registration validation:** the DATE message, and the year range check for
   age-rule sources. Tests in the validator unit tests and
   `test_registration_submission_service.py` (an INTEGER field feeding an age
   rule is range-checked; an unrelated INTEGER field isn't).
8. **BDD / e2e:** update `tests/bdd/test_target_sources.py` and
   `tests/e2e/test_backoffice_target_sources.py` for the new flow. Add one BDD
   scenario: a target of `16-29, 30-44, 45-59, 60+` auto-matches, and a
   respondent aged 70 lands in `60+`.
9. `just translate-regen` / `just translate-check`, `just check`, `just test`.

---

## 8. Decisions from review

| # | Question | Decision |
|---|---|---|
| Q1 | Grouping for all methods or age only? | All four methods, dividers not cards |
| Q2 | Existing age-range configs? | Demo only: data migration deletes them, no legacy reader |
| Q3 | Auto-match failure UI | Pre-filled table plus a reason. Specific for gap/overlap, generic otherwise |
| Q4 | No bottom bracket → too young is `UNKNOWN`? | Yes, acceptable |
| Q5 | Require a from age for every target value? | Yes |
| Q6 | Keep Edit toggle across HTMX re-renders? | No, the server re-decides |
| Q7 | Rewrite `age-bracket-preview.js`? | Yes, rewrite |
| Q8 | Keep "as-of within a year of today" check? | Keep |
| Q9 | `info_icon` accessibility | (b) hint when editing, icon in text mode. Component fix in `793-two-step-fields/future-work.md` |
| Q10 | DATE limits | Keep rolling 120 years, improve the message |
| Q11 | Range-check year-of-birth integers feeding an age rule? | Yes |
| Q12 | Delete `eligibility_sentence()`? | Yes |
| — | Alternative (positional labels on generated brackets) | Dropped |
| — | Client-side date JS | Not doing |

## Out of scope (noted, not doing)

- Guidance when *creating* a target about how to name age values.
- Re-running auto-match when a linked age target's values are renamed. Today
  the resync path refuses age fields ("edit the age ranges or the target
  values instead"), and that stays.
- `validate_integer` / `validate_email_field` return untranslated error
  strings. That's a separate issue. The new year-range message is translated.
- Making `info_icon` a focusable toggletip (see future-work).
