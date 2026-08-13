# Derived Fields — Research

**Status:** Research / options, for review
**Date:** 2026-08-12
**Issue:** 793
**Scope:** How derived respondent fields (age bracket, small mapping, large mapping) should be modelled in the domain, computed in the service layer, and reconciled with existing respondent data. Intersection is explicitly out of scope for MVP.

Everything below is a proposal. Where more than one approach works I have listed the options and marked a recommendation. Comments welcome inline — questions for you are collected in [§12](#12-questions-for-you) but there are a few embedded in the option lists too.

---

## 1. What exists today

### The placeholder columns

`RespondentFieldDefinition` (`src/opendlp/domain/respondent_field_schema.py`) already carries three columns that were shipped as placeholders in the 446 work and have never been written to:

| Column            | Type                | Current meaning                                                             |
| ----------------- | ------------------- | --------------------------------------------------------------------------- |
| `is_derived`      | `bool`              | Flags the row as derived. Forces `on_registration_page = NO` in `__init__`. |
| `derived_from`    | `list[str] \| None` | Source field keys. Required non-empty when `is_derived`.                    |
| `derivation_kind` | `str` (max 100)     | Free-form label, e.g. `"age_bracket_from_dob"`.                             |

The design note that introduced them ([446 respondent_field_schema.md](../history/446-grouped-registrant-view/respondent_field_schema.md)) says explicitly: _"Derived-field placeholders ship now, derivation logic does not."_

Everywhere `is_derived` is consulted today, the field is simply skipped or badged:

- `entrypoints/edit_respondent_form.py:119` — no form control is built for a derived field.
- `entrypoints/blueprints/respondents.py:834, 929` — excluded from attribute collection and from the edit page's groups.
- `service_layer/respondent_field_schema_service.py:366` — `guess_field_types` skips derived rows.
- `templates/backoffice/assembly_view_respondent.html:34` — renders the literal string _"(derivation not yet implemented)"_.
- `templates/backoffice/respondent_field_schema/view.html:182` — yellow "Derived" tag, `on_registration_page` shown as "Not shown".
- Derived fields are omitted from the registration form because `generate_starter_form_html*` filters on `on_registration_page != NO`.

So the schema-side plumbing (table, ORM, repository, detached copies, display) is already there. What is missing is (a) somewhere to put the _parameters_ of a derivation, and (b) anything that computes.

### Where respondents get created or changed

Four write paths, all of which you have asked to derive on:

| Path                    | Function                                                                                     | Notes                                                                 |
| ----------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Registration form       | `registration_submission_service._create_and_save_respondent`                                | Values already validated against the schema by `_validate_form_data`. |
| CSV / tabular import    | `respondent_service.respondent_from_row`, called in a loop by `import_respondents_from_rows` | Bulk; thousands of rows per import. All values are strings.           |
| Backoffice manual entry | `respondent_service.create_respondent`                                                       |                                                                       |
| Backoffice edit         | `respondent_service.update_respondent` → `Respondent.apply_edit`                             | Merges an attributes dict.                                            |

Google Sheet-backed assemblies do not store respondents in the database at all, so derivation does not apply to them. Worth stating in the UI when we get there.

### How targets relate to respondent fields

`TargetCategory.name` is matched case-insensitively against respondent attribute keys (`target_respondent_helpers.get_respondent_counts_for_category`). There is no FK. A derived field therefore becomes usable as a target the moment its `field_key` matches a `TargetCategory.name` — no target-side change is needed for MVP, which is convenient.

---

## 2. Data modelling — the core decision

### 2.1 What the three derivation types actually need

|                   | Age bracket                                                         | Small mapping                              | Large mapping                         |
| ----------------- | ------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------- |
| Source field(s)   | one `DATE` field, **or** one `INTEGER` year-of-birth field (see §3) | one `CHOICE_RADIO`/`CHOICE_DROPDOWN` field | one `TEXT` field                      |
| Output values     | computed bracket labels                                             | fixed list (eventually target values)      | fixed list (eventually target values) |
| Parameters        | as-of date, min age, max age, boundaries                            | —                                          | match mode (see §5.3)                 |
| Lookup table size | none                                                                | ≤ ~20 entries                              | hundreds to millions of entries       |

The size asymmetry between small and large mapping is the thing that drives the storage decision.

### 2.2 Option A — one `derivation_config` JSON column on `respondent_field_definitions`

Replace `derivation_kind: str` with a `derivation_type` enum column, and add `derivation_config: JSON`.

```python
class DerivationType(Enum):
    AGE_BRACKET = "age_bracket"
    SMALL_MAPPING = "small_mapping"
    LARGE_MAPPING = "large_mapping"
    # INTERSECTION = "intersection"   # not MVP
```

```jsonc
// age bracket
{"as_of_date": null, "min_age": 16, "max_age": 100, "boundaries": [22, 30, 55], "fallback": "unknown"}
// small mapping
{"mapping": {"White British": "White", "White Irish": "White", ...}, "fallback": "unknown"}
// large mapping — the whole table inline
{"mapping": {"SW1A": "London", ...}, "match_mode": "exact", "fallback": "unknown"}
```

- **For:** no new table, no new repository, no migration beyond two columns, the whole config travels with `create_detached_copy()` for free, and it matches the existing JSON-heavy style of the codebase (`options`, `comments`, `attributes`).
- **Against:** a full UK postcode table is ~1.8M rows; even at postcode-district level (~2,900) or sector level (~11,000) the JSON blob is 100 KB–several MB. Every `list_by_assembly()` call — which happens on the schema page, the registrant detail page, the edit page, the registration form validation path, and once per CSV import — would drag that blob out of Postgres. That is a real performance cliff on the hottest read path in the schema module.

### 2.3 Option B — separate `respondent_field_derivations` table, 1:1 with the derived field

Move `is_derived` / `derived_from` / `derivation_type` / `derivation_config` out of `respondent_field_definitions` entirely into a child table; the presence of a row _is_ `is_derived`.

- **For:** the hot schema read never touches derivation data. Cleanly separated aggregate.
- **Against:** every consumer that currently asks `field.is_derived` (six call sites plus two templates) needs either a join or a second query; `create_detached_copy()` and the repository interface get more complex; and it throws away the placeholder columns that were deliberately put in place. It also does not, on its own, solve the large-mapping size problem — the blob just moves.

### 2.4 Option C — config JSON on the field, mapping rows in their own table (recommended)

Keep `is_derived` and `derived_from` where they are, swap `derivation_kind` for a typed `derivation_type`, add a small `derivation_config` JSON column for _parameters only_, and put large-mapping entries in a dedicated table:

```sql
-- respondent_field_definitions: alter
--   derivation_kind (String(100))  ->  derivation_type (EnumAsString(DerivationType, 32), default "")
--   + derivation_config JSON NULL

CREATE TABLE respondent_field_mapping_entries (
    id            UUID PRIMARY KEY,
    field_id      UUID NOT NULL REFERENCES respondent_field_definitions(id) ON DELETE CASCADE,
    lookup_key    VARCHAR(255) NOT NULL,   -- normalised: upper/trim, see §5.3
    output_value  VARCHAR(255) NOT NULL,
    UNIQUE (field_id, lookup_key)
);
CREATE INDEX ix_rf_mapping_entries_field_key ON respondent_field_mapping_entries (field_id, lookup_key);
```

Small mappings (≤ ~20 entries) stay inline in `derivation_config`, because they are edited as a form on one page and want to round-trip atomically with the rest of the config. Large mappings go in the table, uploaded as CSV, never edited row-by-row in the UI.

- **For:** hot read path stays cheap; a single indexed lookup per respondent per field; bulk insert on upload; `replace all rows` is a trivial delete-then-`bulk_add`; and the placeholder columns are honoured rather than discarded.
- **Against:** two storage shapes for what is conceptually one thing (mitigated by the domain giving both the same `derive()` interface — §2.6), plus one new table, repository, UoW property, and `_delete_all_test_data()` entry (child before parent, so before `respondent_field_definitions`).

**Recommendation: C.** The extra table is cheap; putting a postcode table in a JSON column read on every page is not.

An intermediate worth mentioning: **C-lite** — start with Option A (everything inline) and add the table only when large mapping lands, if we want to sequence age-bracket and small-mapping first. The migration from A to C is then a data migration over a handful of rows. I would rather not: the shape is knowable now.

### 2.5 Keep `derived_from`, or fold sources into the config?

`derived_from: list[str]` is denormalised — the source key also appears inside the config for some types. I recommend keeping it as the **canonical dependency list**, because it answers a query we genuinely need: _"which derived fields depend on field X?"_, asked when deleting a field, renaming a choice option, or changing a field's type (§7). Config holds parameters only, never source keys.

### 2.6 Domain shape

Follow the existing `ChoiceOption` / `RespondentComment` pattern: frozen dataclasses with `to_dict` / `from_dict`, serialised into the JSON column by a custom SQLAlchemy type like `ChoiceOptionListJSON`.

```python
# src/opendlp/domain/respondent_derivation.py

@dataclass(frozen=True)
class AgeBracketRule:
    min_age: int = 16
    max_age: int = 100
    boundaries: tuple[int, ...] = ()
    as_of_date: date | None = None      # None -> "today", evaluated at derivation time
    fallback: str = "unknown"

    def bracket_labels(self) -> list[str]: ...          # ["under-16", "16-21", ..., "100+"]
    def eligibility_sentence(self) -> str: ...          # see §3.2
    # Source precision (full date vs year-only) is read from the source field's
    # field_type, not stored here — see §3.1.
    def derive(self, source_values: Mapping[str, str], today: date) -> str: ...

@dataclass(frozen=True)
class SmallMappingRule:
    mapping: Mapping[str, str]
    fallback: str = "unknown"
    def derive(self, source_values, today) -> str: ...

@dataclass(frozen=True)
class LargeMappingRule:
    match_mode: MatchMode = MatchMode.EXACT
    fallback: str = "unknown"
    # NB: no mapping data here. The lookup is injected by the caller so the
    # domain stays pure and we never load a million rows into a value object.
    def derive(self, source_values, today, lookup: Callable[[str], str | None]) -> str: ...
```

The signature asymmetry on `LargeMappingRule.derive` is slightly ugly. Two ways to smooth it:

- (a) every `derive()` takes a `lookup` argument and the small/age rules ignore it — uniform, mildly dishonest;
- (b) a `DerivationContext` dataclass carrying `today` and a `lookups: dict[field_key, Callable]`, passed to every rule. **Recommended** — it also gives us somewhere to put future context (assembly dates, locale) without changing every signature again.

`bracket_labels()` is worth having as a domain function in its own right: it is what populates the derived field's `options` (§2.7) and what the config UI previews back to the organiser. Your worked example — min 16, max 100, boundaries 22,30,55 — yields `under-16, 16-21, 22-29, 30-54, 55-99, 100+`.

### 2.7 Where do the output values live?

You said target values can be stored directly on the field for now, with a link to `TargetValue` later. There is a neater option:

- **Option 1 — `target_values: list[str]` inside `derivation_config`.** Explicit, but it is a second list of allowed values living alongside `options`, and nothing else in the system knows about it.
- **Option 2 (recommended) — reuse the existing `options: list[ChoiceOption]` column,** with the derived field typed `CHOICE_RADIO`/`CHOICE_DROPDOWN`.

Option 2 means every existing consumer works unchanged: the registrant detail page renders a select, the export writes the value, `_validate_type_and_options` already enforces "choice type ⇒ non-empty options", and a future `TargetValue` FK replaces one list instead of two. For age brackets the options are _generated_ from the rule and rewritten whenever the rule changes; for mappings they are the set of distinct outputs the organiser declares. The mapping config then only needs input → output.

The one wrinkle: `RespondentFieldDefinition.update()` currently raises `FixedFieldError` when changing type/options on a fixed field, and lets anyone change them on a non-fixed field. Derived fields need the same protection — options on a derived field are owned by the derivation, not hand-editable. Suggest a `DerivedFieldError(ValueError)` sibling, and the schema view page renders the type/options cells read-only for derived rows (it already special-cases `on_registration_page`).

---

## 3. The date-of-birth special case

Decision taken: **one new `FieldType.DATE`**, one schema row (e.g. `date_of_birth`), `derived_from = ["date_of_birth"]`.

### 3.1 Year of birth — the data-minimising variant

Not every assembly needs a full date of birth, and an organiser who only needs age brackets should be able to ask for less. So the age-bracket derivation must accept **either** a `DATE` source **or** an `INTEGER` year-of-birth source, treating the birthday as 1 January when only the year is known.

Two ways to model that, and you said you don't mind which — the UI reads fine either way:

- **Option 1 — two derivation types** (`AGE_BRACKET_FROM_DATE`, `AGE_BRACKET_FROM_YEAR`). Explicit in the data, two entries in the "add a derived field" menu, two near-identical config forms and two rule classes to keep in step.
- **Option 2 (recommended) — one `AGE_BRACKET` type; precision follows the source field's `field_type`.** The organiser picks which field feeds the bracket, and a `DATE` source means exact-date arithmetic while an `INTEGER` source means "1 January of that year". No extra config key, no way to get the two out of sync, and adding a third precision later (month+year, say) is a branch rather than a type.

Option 2 does mean the config page needs a line of copy explaining what the organiser gets — something like _"Ages will be worked out from 1 January, because this field only records the year."_ Worth surfacing, since it silently shifts some people down a bracket. The rule stores no precision flag; `derive_values` already has the source `RespondentFieldDefinition` in hand, so it reads `field_type` directly.

**Where the two land differently.** With a 1 January assumption, everyone born in a given year is treated as having their birthday already passed. Someone born in December 2010, assessed on 13 May 2026, is "16" by year arithmetic but is actually 15. For a min-age of 16 that is exactly the population the organiser cares about getting right. Two mitigations, not mutually exclusive:

1. The eligibility checkbox does the real work (below).
2. The config page states the assumption plainly and the recompute report counts how many people sit within a year of a bracket boundary.

Given (1), I do not think we need a "assume 31 December instead" option. Flagged as Q9 in case you disagree.

### 3.2 The eligibility checkbox carries the minimum age

Your point, and it changes how much weight the `min_age` bracket has to bear: registration forms normally carry an "I am eligible" checkbox whose wording states the age rule — _"I will be at least 16 on 13 May 2026 and …"_. That is a self-declaration made before submission, so the `under-16` bracket is a data-quality backstop, not the primary gate.

Two things follow:

- The age config knows `min_age` and `as_of_date`, so it can **generate that sentence** for the organiser to paste into their registration HTML or into the `eligible` field's help text: `_("I will be at least %(min_age)s on %(date)s", …)`. Cheap to build, and it keeps the form wording and the bracket arithmetic from drifting apart — which is exactly the kind of drift nobody notices until the selection looks wrong. That is `eligibility_sentence()` in §2.6.
- It strengthens the case for a **fixed** as-of date over "today": the sentence has to name a specific date, and the sentence and the derivation should be quoting the same one. If the field is configured date-relative, the generated wording has to fall back to something vaguer ("I am at least 16 today"), which is weaker legally and weaker practically.

### 3.3 Implementation work

Work the `DATE` type implies, none of it derivation-specific (the `INTEGER` year-of-birth source needs none of this — `FieldType.INTEGER` already exists end to end, which is a point in its favour):

1. **`FieldType.DATE` + `FIELD_TYPE_LABELS[DATE] = _l("Date")`.** Storage in `Respondent.attributes` as an ISO string `"1985-03-07"` — attributes are a JSON dict of mostly-strings today, and an ISO string sorts and compares correctly.
2. **A validator** — `validators.validate_date_field(str_value) -> tuple[str | None, str | None]`, matching the `validate_integer` / `validate_email_field` shape (returns cleaned value + error message). Rejects impossible dates (31 Feb), future dates, and implausible ones (age > 120).
3. **Registration form parsing.** `_validate_form_data` does `form_data.get(fd.field_key)`, one key per field. The GOV.UK date input is three inputs named `date_of_birth-day`, `-month`, `-year`. Since registration HTML is _authored by the organiser_, we cannot assume either shape. Recommend: for a `DATE` field, first try the three-part names, and fall back to a single value under the bare key parsed as ISO or `dd/mm/yyyy`. Both starter generators (`generate_starter_form_html`, `generate_starter_form_html_govuk` in `domain/registration_page.py`) emit the three-part form. Error reporting attaches to the bare key so `field_errors()` markup keeps working.
4. **Backoffice edit + view.** A date control in `edit_respondent_form._build_field_for_definition` and a branch in the `render_view_field` macro.
5. **Type-guessing.** `guess_field_types` could learn to spot ISO dates; not required, and arguably it should _not_ auto-convert, since flipping a field to DATE has consequences. Leave it alone.
6. **CSV import.** Imported DOB values are free text. Parse leniently (ISO, `dd/mm/yyyy`), and where parsing fails the derived field takes its fallback rather than the import failing. Worth reporting the count in the import's `errors` list, which is already a general "things you should know" channel.

**PII note.** Date of birth is personal data of a more sensitive kind than most of what we hold. It lands in `Respondent.attributes`, so `delete_personal_data()` blanks it along with everything else (`dict.fromkeys(self.attributes, "")`) — the right-to-erasure path is already correct, no change needed. Two things to flag in the eventual UI copy: the age bracket is itself blanked by erasure (correct — it is derived from PII), and **year of birth (§3.1) should be offered as the default**, with full date of birth the deliberate opt-up for organisers who need it. Collecting a year rather than a full date is a genuine data-minimisation win for no loss of bracketing accuracy in most configurations, and it is the kind of default we should be setting rather than merely permitting. Nothing here changes the cookie/analytics conclusions in [docs/personal-data.md](../../personal-data.md).

**As-of date.** `as_of_date = None` means "today", i.e. the value depends on _when derivation ran_. That makes recomputation (§6) non-idempotent: re-running a backfill six months later moves people between brackets. A fixed as-of date (typically the first assembly date) is deterministic, is what most real assemblies want — you want the age someone will be at the assembly, not at registration — and is the only thing the eligibility sentence in §3.2 can quote. Default remains "today" as you specified; recommend the config UI offers "the day they register" vs "a fixed date" as an explicit either/or, nudges towards the fixed date, and warns on recompute when the field is date-relative.

---

## 4. Computing derivations

### 4.1 Where the code lives

- **Option 1 (recommended)** — pure domain function plus a thin service wrapper.
  ```python
  # domain/respondent_derivation.py
  def derive_values(
      field_defs: list[RespondentFieldDefinition],
      attribute_values: Mapping[str, Any],
      fixed_values: Mapping[str, Any],       # email/eligible/... in case a source is a fixed field
      context: DerivationContext,
  ) -> dict[str, str]: ...
  ```
  Testable with no database, no Flask. The service layer's job is to load the schema once, build the `lookup` callables for any large mappings, and merge the result into `respondent.attributes`.
- **Option 2** — a method on `Respondent`. Rejected: `Respondent` has no business knowing about the schema, and it would need the schema passed in anyway.
- **Option 3** — a SQLAlchemy `before_flush` event hook so derivation is impossible to forget. Rejected: hidden magic, needs DB reads mid-flush for large mappings, and makes the bulk import path unpredictable. The four call sites are few enough to hook explicitly.

New service module `service_layer/derivation_service.py` holding: config CRUD, mapping upload, the "apply to a respondent" helper, and recompute/backfill (§6).

### 4.2 The call sites

| Call site                                                     | When                                                            | Note                                                                       |
| ------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `registration_submission_service._create_and_save_respondent` | after `cleaned_data` is built, before constructing `Respondent` | schema already loaded by the caller — pass it down rather than re-querying |
| `respondent_service.create_respondent`                        | before `uow.respondents.add`                                    | needs a schema load                                                        |
| `respondent_service.import_respondents_from_rows`             | inside the row loop, via `respondent_from_row`                  | **load schema + build lookups once, outside the loop**                     |
| `respondent_service.update_respondent`                        | after `respondent.apply_edit(...)`, before `uow.commit()`       |                                                                            |

`respondent_from_row` is currently a pure function with no `uow` — pass the prepared derivation context in as an optional argument rather than giving it repository access, so it stays unit-testable.

For large mappings in the import path, a per-row indexed SELECT over thousands of rows is avoidable: gather the distinct source values for the batch and fetch matching entries in one query (`WHERE field_id = ? AND lookup_key = ANY(...)`), then look up in memory. Worth doing from the start — a 5,000-row import should not become 5,000 extra round trips.

### 4.3 Precedence: what if the incoming data already has the derived column?

Real scenario: an organiser exports respondents (the export writes derived fields as ordinary columns), edits, and re-imports; or their source system already computes `age_bracket`. Options:

- (a) **Derivation always wins.** Simple, consistent. Silently discards a supplied column.
- (b) **Supplied column wins.** Undermines the whole feature.
- (c) **(Recommended) Derive when the source values are present and usable; otherwise keep the supplied value; otherwise fall back.** Add a line to the import `errors` list (which is really a "notes" channel) whenever a supplied derived column was overwritten, so it is visible rather than silent.

Option (c) makes export→edit→re-import round-trip sanely, and makes a partial import (source column missing) non-destructive.

### 4.4 Chained derivations

Intersection (post-MVP) derives from two fields that may themselves be derived. For MVP, **validate at config time that every source field is not itself derived** and compute in a single pass. Design `derive_values` to take the full field list and iterate, so adding a topological sort later is a local change. Also worth a config-time cycle check even in MVP, cheap insurance.

### 4.5 Failure and fallback

Decision taken: **store a fallback value, accept the submission.** Concretely:

- Age: below `min_age` → `under-16` (using the configured minimum), above `max_age` → `100+`. These are real brackets in your example, not errors — an assembly with a 16+ eligibility rule still wants to see that someone under 16 registered despite ticking the eligibility box (§3.2). Missing or unparsable date / year → the configured fallback. A year-of-birth outside a sane range (say, before 1900 or in the future) is a typo, not a person, so it takes the fallback rather than producing a `100+`.
- Mappings: no match → the configured fallback (default `"unknown"`).
- The fallback value **must** be in the field's `options` so the value round-trips through the edit form and export cleanly, and so the organiser can see it in target counts. Suggest the config UI adds it automatically.
- Every fallback is worth counting: a `derive` result that reports _how many_ respondents fell back is the organiser's signal that their postcode table has holes. See the preview/report idea in §8.

---

## 5. The mapping tables

### 5.1 Small mapping

Config UI: pick the source choice field, declare the output values, then one row per source option with a dropdown of output values. Because the source is a `CHOICE_*` field we know the complete input set — so the UI can show every option and flag any that are unmapped, and "unmapped" is a config-time warning rather than a runtime surprise.

### 5.2 Large mapping — CSV upload

- Two columns. Match headers by normalised name (`normalise_field_name` in `domain/respondents.py` already does the lowercase/strip work) against the source field key and the derived field key — your "postcode" / "region" example. Fall back to positional (first = input, second = output) with a warning if the headers don't match, rather than rejecting.
- Validate outputs against the declared option list; report unknown outputs with counts and offer "add these as options" vs "reject".
- Thousands of rows, occasionally far more. Upload is a normal form POST parsed in memory then `bulk_add`; if we ever accept full-postcode tables (1.8M rows) this wants the Celery path ([docs/background_tasks.md](../../background_tasks.md)). Suggest a row cap for MVP (say 50,000) with a clear error above it.
- **GDPR:** a postcode→region table is reference data, not personal data, so storing it long-term is fine and does not touch the erasure story in [docs/personal-data.md](../../personal-data.md). The _uploaded file_ must not be persisted — parse to rows, discard the file. That is the existing rule and this path obeys it naturally.

### 5.3 Match modes — the postcode problem

This one matters. A registrant types `SW1A 1AA`. An organiser's mapping table almost certainly lists _outcodes_ (`SW1A`) or districts, not all 1.8M full postcodes. Exact matching fails for every single registrant.

Options:

- (a) **Exact match only** (after normalising: uppercase, strip all whitespace). Correct only if the organiser supplies a table at the same granularity registrants type. For postcodes that means a 1.8M-row table.
- (b) **(Recommended) A `match_mode` on the rule: `EXACT` or `LONGEST_PREFIX`.** Longest-prefix normalises both sides and finds the longest stored key that is a prefix of the input — so `SW1A1AA` matches the stored `SW1A`, and a table can mix granularities. Implementable as a small number of prefix queries per lookup, or in memory for the batch case.
- (c) Postcode-specific normalisation baked in (split off the inward code and match on the outward code). Too special-cased; prefix matching gets the same result generically.

Prefix matching is a genuine addition to the MVP but I think it is the difference between the feature working and not working for its headline use case. Flagging it explicitly rather than assuming — see Q3.

---

## 6. Adding or editing derived fields when respondents already exist

You asked. My answer: **yes, allow it, with an explicit recompute.** Forbidding it would be unworkable — the normal order of events is import-or-open-registration first, configure targets second.

Options considered:

- (a) **Forbid once respondents exist.** Simplest, and wrong for the actual workflow.
- (b) **Allow, apply to new respondents only.** Leaves the pool half-derived — the worst outcome, because the resulting target counts are quietly wrong.
- (c) **(Recommended) Allow, and recompute every affected respondent, synchronously, with a confirmation step.** Creating or editing a derivation shows a preview — "1,204 respondents will be updated, 37 will fall back to _unknown_" — and applies on confirm. `derive_values` is pure, so the preview and the apply share one code path.
- (d) As (c) but via Celery for large pools. Recommend keeping it synchronous for MVP with batched commits, and lifting it into a task if real-world timings demand it. The existing task system is there if we need it.

Details for (c):

- Skip `RespondentStatus.DELETED` respondents — their attributes are deliberately blanked and must stay that way.
- The recompute records nothing in `Respondent.comments`. Derivation is not a user edit and 1,200 identical comments would drown the activity log. (Alternative: one comment per respondent, `RespondentAction.EDIT`. I think that is noise, but it is a judgement call — Q4.)
- **Warn when the assembly has completed selection runs.** `SelectionRunRecord` snapshots the _targets_ but not respondent attributes, so recomputing a derived field silently changes the data a past run was based on. It does not invalidate the run's results, but it does make the run un-reproducible. A warning on the confirm page is enough; blocking would be over-reach.
- Deleting a derived field: leave the computed values in `attributes` (consistent with `delete_field`'s existing "respondent attribute data is untouched" behaviour) and drop any mapping rows via the FK cascade.

---

## 7. Protecting source fields

Derived fields create dependencies the schema module currently has no concept of. `derived_from` is what makes these checkable.

| Action                                                              | Today                           | Needs to become                                                                  |
| ------------------------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------- |
| `delete_field` on a source field                                    | allowed for any non-fixed field | blocked with "X is used to derive Y" (or offer to delete both)                   |
| `update_field` changing a source field's `field_type`               | allowed                         | blocked, or forces the derivation into an invalid state that the UI must surface |
| `update_choice_option` renaming an option on a small-mapping source | allowed                         | rename the corresponding mapping key in step, or the mapping goes stale silently |
| `remove_choice_option` on a small-mapping source                    | allowed                         | drop the mapping entry and warn                                                  |
| `update_field` on a derived field's own type/options                | allowed                         | blocked — owned by the derivation (§2.7)                                         |

Recommend: a `derivations_depending_on(field_key)` helper in the derivation service, called by the four schema-service mutators. Rename-in-step for `update_choice_option` is worth doing rather than warning, since a rename with a stale mapping produces wrong data with no visible symptom.

---

## 8. Service-layer surface

New `service_layer/derivation_service.py`:

```python
create_derived_field(uow, user_id, assembly_id, field_key, label, group, rule)  -> RespondentFieldDefinition
update_derivation(uow, user_id, assembly_id, field_id, rule)                    -> RespondentFieldDefinition
upload_large_mapping(uow, user_id, assembly_id, field_id, csv_content)          -> MappingUploadReport
preview_recompute(uow, user_id, assembly_id, field_id)                          -> RecomputeReport   # dry run
recompute_derived_field(uow, user_id, assembly_id, field_id)                    -> RecomputeReport
derivations_depending_on(uow, assembly_id, field_key)                           -> list[RespondentFieldDefinition]
build_derivation_context(uow, assembly_id, field_defs)                          -> DerivationContext # loads lookups
apply_derivations(respondent, field_defs, context)                              -> None              # in-memory
```

`RecomputeReport` carries `total`, `changed`, `fell_back`, and a sample of unmatched inputs — that last one is what an organiser needs to fix a postcode table, and it is the same data the preview shows. Permission checks use the existing `_ensure_manage_permission` pattern; all messages `_l()`-wrapped per the i18n rules.

---

## 9. UI touchpoints (sketch, for sizing only)

- **Schema page** (`respondent_field_schema/view.html`): "Add derived field" action; derived rows get an "Edit derivation" link and read-only type/options cells.
- **Three config pages**, one per derivation type, since their forms have nothing in common. The age one previews its bracket labels live as boundaries are typed (Alpine, flat `x-model` properties per the CSP patterns).
- **Large-mapping page**: upload form, row count, "replace table" action, list of unmatched inputs from the last recompute.
- **Registrant detail / edit**: replace the `"(derivation not yet implemented)"` string with the real value, rendered read-only. A "why this value?" hint (_derived from postcode SW1A 1AA_) would be genuinely useful for confirmation callers.
- **Registration form starter HTML**: `DATE` field rendering in both generators. Derived fields are already excluded.
- **Export**: no change — derived fields are ordinary attributes.
- Accessibility per [component_accessibility.md](../component_accessibility.md); the GOV.UK date input pattern has a documented fieldset/legend structure that we should copy rather than invent.

---

## 10. Migration

One Alembic migration (`uv run alembic revision --autogenerate`, then hand-check):

1. `respondent_field_definitions`: add `derivation_type` (String(32), not null, server_default `''`), add `derivation_config` (JSON, nullable), drop `derivation_kind`. No data to preserve — nothing has ever written it. Confirmed by grep: the only non-test writes are the placeholder defaults.
2. Create `respondent_field_mapping_entries` (Option C).
3. `tests/conftest.py::_delete_all_test_data` — add the new table _before_ `respondent_field_definitions`. Same for `delete_all_except_standard_users()` in `tests/bdd/conftest.py`.

`FieldType.DATE` needs no migration (`EnumAsString`), but `src/js/components/service-docs/fields.js` and `templates/backoffice/service_docs/_fields.html` both enumerate field types and will need the new value.

---

## 11. Testing

Per the no-exceptions policy, all three layers:

- **Unit** — bracket-label generation across edge configs (no boundaries, boundary equal to min/max, unsorted input, duplicates); age at exact boundary and on a birthday; leap-year birthdays; **year-of-birth arithmetic against a date-of-birth source for the same person, including the December-born case in §3.1, and out-of-range years**; `eligibility_sentence()` wording and its translation parameters; `derive_values` for each rule type incl. every fallback path; date parsing and rejection; CSV mapping parsing (header match, positional fallback, duplicate keys, unknown outputs); longest-prefix matching.
- **Contract** — the mapping-entry repository against the abstract interface, following the existing contract-test pattern.
- **Integration** — derivation on each of the four write paths; recompute with report counts; source-field protection rules; import precedence (§4.3); large-mapping batch lookup does not degenerate to N queries.
- **E2E / BDD** — configure an age bracket and see a registration land in the right bucket; upload a postcode table and see the region target populate; edit a derivation on an existing pool and confirm the recompute.

---

## 12. Questions for you

**Q1 — Option C, or start simpler?**
Recommendation is the separate `respondent_field_mapping_entries` table from day one (§2.4). The alternative is inline JSON for everything and a data migration later. Happy either way, but I would rather build the shape we know we need.

**Answer:**

**Q2 — Reuse `options` for the derived field's output values (§2.7)?**
Recommended, because everything downstream then works unchanged and the future `TargetValue` link replaces one list rather than two. The cost is that derived fields' options become read-only in the schema UI.

**Answer:**

**Q3 — Longest-prefix matching for large mappings in MVP (§5.3)?**
Without it, a postcode→region mapping needs every full postcode in the country. With it, an outcode table works. I think it is close to essential for the headline use case, but it is scope.

**Answer:**

**Q4 — Should a recompute leave a comment on each respondent (§6)?**
I say no — it is machine-generated churn in a log meant for human actions, and the recompute report already records what happened. But it does mean the change is invisible on an individual respondent's history.

**Answer:**

**Q5 — Default fallback value.**
Proposing the literal `"unknown"`, editable per field, auto-added to the options list. Is there a house convention I should match instead (`""`, `"not specified"`, `"other"`)? Note that whatever we choose shows up in target counts, so it wants to be something an organiser reads as "needs attention".

**Answer:**

**Q6 — Age brackets when `min_age` is 0.**
With min 16 you get an `under-16` bracket. With min 0 that bracket is empty and meaningless — suppress it, or always emit it? Same question at the top end when `max_age` is very high.

**Answer:**

**Q7 — Should the derived field's `group` default to `ABOUT_YOU`, or a new `DERIVED` group?**
Derived fields are never on the registration form, so they sit oddly in "About you" next to fields the registrant filled in. A separate group keeps them together and out of the way on the registrant detail page, at the cost of extending the fixed group catalogue.

**Answer:**

**Q8 — Is `preview_recompute` (dry-run before applying) worth the MVP scope?**
It is a modest addition given `derive_values` is pure, and it is what turns "I uploaded a postcode table" into "I uploaded a postcode table and 340 people didn't match". Or defer it and rely on the post-hoc report.

**Answer:**

**Q9 — Year of birth: is "assume 1 January" the only rule we offer (§3.1)?**
It over-states age for anyone not born in January. Given the eligibility checkbox does the real gatekeeping I think that is fine and an alternative ("assume 31 December", or "assume 1 July" to halve the average error) is a config knob nobody will understand. Say if you want the option anyway.

**Answer:**

**Q10 — Should the age config generate the eligibility sentence (§3.2), and where does it go?**
Recommend generating it. The open bit is delivery: a copy-to-clipboard snippet on the config page, auto-insertion into the `eligible` field's help text, or a substitution placeholder the authored registration HTML can call (the render context already supports `{{ ... }}` placeholders). The placeholder is the only one that cannot drift, but it is the most machinery.

**Answer:**

---

## 13. Rough sequencing

1. `FieldType.DATE` end to end — validator, form parsing, starter HTML, edit/view, tests. Independently useful, no derivation involved. Deferrable if we want to ship year-of-birth brackets first: an `INTEGER` year source needs none of this.
2. Data model: `derivation_type` + `derivation_config` + migration; `DerivationType`, the rule dataclasses, `derive_values`. Domain-only, fully unit-tested.
3. Age bracket: config page (both source precisions, eligibility sentence), wire the four write paths, recompute + report.
4. Small mapping: config page, source-field protection rules (§7).
5. Large mapping: table, repository, CSV upload, batch lookup, match modes.
6. Intersection — separate piece of work, with the "we generally do not recommend this" warning and its dead "see docs for why" link.

Steps 1 and 2 are the ones with no user-visible output and the most leverage; steps 3–5 each land a usable feature.
