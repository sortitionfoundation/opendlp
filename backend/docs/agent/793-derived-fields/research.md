# Derived Fields — Research

**Status:** Reviewed — decisions taken, ready to turn into a plan
**Date:** 2026-08-12, revised 2026-08-14 after review
**Issue:** 793
**Scope:** How derived respondent fields (age bracket, small mapping, large mapping) should be modelled in the domain, computed in the service layer, and reconciled with existing respondent data. Intersection is explicitly out of scope for MVP.

The options below are kept for the record, but each now records the decision taken in review. [§12](#12-questions-for-you) lists the two things still open and the ideas we have deliberately parked.

**Decisions at a glance:** full Option C storage from the start (§2.4) · reuse `options` for output values (§2.7) · one `AGE_BRACKET` type, precision follows the source field (§3.1) · `as_of_date` is a required fixed date, never "today" (§3.3) · `min_age` must be > 0 · new `DERIVED` field group · rules do **not** share a `derive()` signature (§2.6) · exact matching only for large mappings, pending a team check on postcode-list granularity (§5.3) · recompute applies directly, dry-run preview parked (§6).

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
| Parameters        | as-of date (required), min age, max age, boundaries                 | —                                          | none in MVP (see §5.3)                |
| Lookup table size | none                                                                | ≤ ~20 entries                              | tens of thousands of entries          |

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
{"as_of_date": "2026-05-13", "min_age": 16, "max_age": 100, "boundaries": [22, 30, 55], "fallback": "unknown"}
// small mapping
{"mapping": {"White British": "White", "White Irish": "White", ...}, "fallback": "unknown"}
// large mapping — the whole table inline
{"mapping": {"SW1A 1AA": "London", ...}, "fallback": "unknown"}
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
- **Against:** two storage shapes for what is conceptually one thing, plus one new table, repository, UoW property, and `_delete_all_test_data()` entry (child before parent, so before `respondent_field_definitions`).

**Decided: full Option C from the start.** The table and its repository land in the first data-model step, not when large mapping arrives — no staged migration, no C-lite. The two storage shapes are fine: small and large mappings are genuinely different things (§2.6 takes the same line about the rule classes) and pretending otherwise buys nothing.

### 2.5 Keep `derived_from`, or fold sources into the config?

`derived_from: list[str]` is denormalised — the source key also appears inside the config for some types. I recommend keeping it as the **canonical dependency list**, because it answers a query we genuinely need: _"which derived fields depend on field X?"_, asked when deleting a field, renaming a choice option, or changing a field's type (§7). Config holds parameters only, never source keys.

### 2.6 Domain shape

Follow the existing `ChoiceOption` / `RespondentComment` pattern: frozen dataclasses with `to_dict` / `from_dict`, serialised into the JSON column by a custom SQLAlchemy type like `ChoiceOptionListJSON`.

**Decided: the three rules do not share a `derive()` signature.** An earlier draft proposed a `DerivationContext` passed to every rule so the calls would look uniform. That is generic-for-its-own-sake: passing a date to a postcode lookup is dishonest about what the code does. Each rule takes exactly the arguments it needs, and the dispatcher supplies them. Since `as_of_date` is a required fixed date (§3.3), no rule needs "today" at all.

```python
# src/opendlp/domain/respondent_derivation.py

@dataclass(frozen=True)
class AgeBracketRule:
    as_of_date: date                    # required — no "today", see §3.3
    min_age: int = 16                   # must be > 0
    max_age: int = 100
    boundaries: tuple[int, ...] = ()
    fallback: str = "unknown"

    def bracket_labels(self) -> list[str]: ...     # ["under-16", "16-21", ..., "100+"]
    def eligibility_sentence(self) -> str: ...     # see §3.2
    def derive_from_date(self, born: date) -> str: ...
    def derive_from_year(self, year: int) -> str: ...   # birthday assumed 1 January

@dataclass(frozen=True)
class SmallMappingRule:
    mapping: Mapping[str, str]
    fallback: str = "unknown"
    def derive(self, value: str) -> str: ...

@dataclass(frozen=True)
class LargeMappingRule:
    fallback: str = "unknown"
    # No mapping data here: the lookup is injected by the caller so the domain
    # stays pure and we never load 50,000 rows into a value object.
    def derive(self, value: str, lookup: Callable[[str], str | None]) -> str: ...
```

Two notes on the age rule:

- `as_of_date` is a plain required field. The alternative — default `None` and resolve to today in `__post_init__` — was considered and rejected in §3.3: a value that silently means "whenever this object happened to be constructed" is exactly what we do not want.
- `derive_from_date` / `derive_from_year` rather than one `derive` that sniffs its argument type. The caller already knows which it has, because it read the source field's `field_type` (§3.1).

**Where the dispatch lives.** Something has to look at a derived field, work out which rule it carries, fetch the source value, and call the right method. That belongs in the service layer, not the domain, because for large mappings it needs a repository. Sketch:

```python
# service_layer/derivation_service.py
def derived_value_for(field_def, rule, source_def, source_value, lookup=None) -> str
def apply_derivations(respondent, field_defs, lookups) -> None   # mutates respondent.attributes
```

`apply_derivations` takes the whole respondent, walks the derived fields, and is the single thing the four write paths call. The per-rule `match` on `derivation_type` sits inside `derived_value_for`, in one place, and reads as three genuinely different cases rather than a forced abstraction.

`bracket_labels()` is worth having as a domain function in its own right: it is what populates the derived field's `options` (§2.7) and what the config UI shows back to the organiser. Your worked example — min 16, max 100, boundaries 22,30,55 — yields `under-16, 16-21, 22-29, 30-54, 55-99, 100+`.

**`min_age` must be greater than zero**, settled in review. Babies do not attend assemblies, and the constraint removes the "what does `under-0` mean" branch from the label generator entirely. Validated in `AgeBracketRule.__post_init__` alongside the boundary checks (sorted, unique, strictly between `min_age` and `max_age`).

### 2.7 Where do the output values live?

You said target values can be stored directly on the field for now, with a link to `TargetValue` later. There is a neater option:

- **Option 1 — `target_values: list[str]` inside `derivation_config`.** Explicit, but it is a second list of allowed values living alongside `options`, and nothing else in the system knows about it.
- **Option 2 (recommended) — reuse the existing `options: list[ChoiceOption]` column,** with the derived field typed `CHOICE_RADIO`/`CHOICE_DROPDOWN`.

Option 2 means every existing consumer works unchanged: the registrant detail page renders a select, the export writes the value, `_validate_type_and_options` already enforces "choice type ⇒ non-empty options", and a future `TargetValue` FK replaces one list instead of two. For age brackets the options are _generated_ from the rule and rewritten whenever the rule changes; for mappings they are the set of distinct outputs the organiser declares. The mapping config then only needs input → output.

The one wrinkle: `RespondentFieldDefinition.update()` currently raises `FixedFieldError` when changing type/options on a fixed field, and lets anyone change them on a non-fixed field. Derived fields need the same protection — options on a derived field are owned by the derivation, not hand-editable. Suggest a `DerivedFieldError(ValueError)` sibling, and the schema view page renders the type/options cells read-only for derived rows (it already special-cases `on_registration_page`).

**Decided: Option 2.** Output values live in the existing `options` column; `derivation_config` never carries a `target_values` list.

### 2.8 A new `DERIVED` field group

Derived fields get their own `RespondentFieldGroup.DERIVED` rather than sitting in `ABOUT_YOU` next to fields the registrant actually filled in. Concretely: a new enum member, an entry in `GROUP_DISPLAY_ORDER` (proposing between `CONSENT` and `OTHER`, so derived values sit near the bottom of the registrant detail page but above the catch-all), and a `GROUP_LABELS` entry — `_l("Derived")`. `field_group` is stored via `EnumAsString`, so no migration is needed. New derived fields default to this group; the organiser can still move them, since group is freely editable.

One knock-on: `respondent_field_schema_heuristics.classify_field_key` must never classify an imported CSV header into `DERIVED` — that group is only ever set deliberately.

---

## 3. The date-of-birth special case

Decision taken: **one new `FieldType.DATE`**, one schema row (e.g. `date_of_birth`), `derived_from = ["date_of_birth"]`.

### 3.1 Year of birth — the data-minimising variant

Not every assembly needs a full date of birth, and an organiser who only needs age brackets should be able to ask for less. So the age-bracket derivation must accept **either** a `DATE` source **or** an `INTEGER` year-of-birth source, treating the birthday as 1 January when only the year is known.

Two ways to model that, and you said you don't mind which — the UI reads fine either way:

- **Option 1 — two derivation types** (`AGE_BRACKET_FROM_DATE`, `AGE_BRACKET_FROM_YEAR`). Explicit in the data, two entries in the "add a derived field" menu, two near-identical config forms and two rule classes to keep in step.
- **Option 2 (recommended) — one `AGE_BRACKET` type; precision follows the source field's `field_type`.** The organiser picks which field feeds the bracket, and a `DATE` source means exact-date arithmetic while an `INTEGER` source means "1 January of that year". No extra config key, no way to get the two out of sync, and adding a third precision later (month+year, say) is a branch rather than a type.

Option 2 does mean the config page needs a line of copy explaining what the organiser gets — something like _"Ages will be worked out from 1 January, because this field only records the year."_ Worth surfacing, since it silently shifts some people down a bracket. The rule stores no precision flag; the dispatch already has the source `RespondentFieldDefinition` in hand, so it reads `field_type` and picks `derive_from_date` or `derive_from_year`.

**Decided: Option 2**, and **1 January is the only assumption we offer** — no "assume 31 December" or "assume 1 July" knob.

**What that costs.** Everyone born in a given year is treated as having had their birthday already. Someone born in December 2010, assessed on 13 May 2026, is "16" by year arithmetic but is actually 15. That is acceptable because the eligibility checkbox does the real gatekeeping (§3.2) — the bracket is a data-quality backstop, not the age gate. The config page should still state the assumption plainly, since it silently shifts some people down a bracket.

### 3.2 The eligibility checkbox carries the minimum age

Your point, and it changes how much weight the `min_age` bracket has to bear: registration forms normally carry an "I am eligible" checkbox whose wording states the age rule — _"I will be at least 16 on 13 May 2026 and …"_. That is a self-declaration made before submission, so the `under-16` bracket is a data-quality backstop, not the primary gate.

Two things follow:

- The age config knows `min_age` and `as_of_date`, so it can **generate that sentence**: `_("I will be at least %(min_age)s on %(date)s", …)`. That keeps the form wording and the bracket arithmetic from drifting apart — exactly the kind of drift nobody notices until the selection looks wrong. **Scope decision: build `eligibility_sentence()` as a domain function and stop there.** How it reaches the organiser (copy-to-clipboard on the config page, auto-inserted help text, or a `{{ }}` placeholder the authored HTML can call) is deferred — the domain function is the part that has to exist first, and it is cheap.
- It settles the as-of date argument below: the sentence has to name a specific date, and the sentence and the derivation must quote the same one.

### 3.3 Implementation work

Work the `DATE` type implies, none of it derivation-specific (the `INTEGER` year-of-birth source needs none of this — `FieldType.INTEGER` already exists end to end, which is a point in its favour):

1. **`FieldType.DATE` + `FIELD_TYPE_LABELS[DATE] = _l("Date")`.** Storage in `Respondent.attributes` as an ISO string `"1985-03-07"` — attributes are a JSON dict of mostly-strings today, and an ISO string sorts and compares correctly.
2. **A validator** — `validators.validate_date_field(str_value) -> tuple[str | None, str | None]`, matching the `validate_integer` / `validate_email_field` shape (returns cleaned value + error message). Rejects impossible dates (31 Feb), future dates, and implausible ones (age > 120).
3. **Registration form parsing.** `_validate_form_data` does `form_data.get(fd.field_key)`, one key per field. The GOV.UK date input is three inputs named `date_of_birth-day`, `-month`, `-year`. Since registration HTML is _authored by the organiser_, we cannot assume either shape. Recommend: for a `DATE` field, first try the three-part names, and fall back to a single value under the bare key parsed as ISO or `dd/mm/yyyy`. Both starter generators (`generate_starter_form_html`, `generate_starter_form_html_govuk` in `domain/registration_page.py`) emit the three-part form. Error reporting attaches to the bare key so `field_errors()` markup keeps working.
4. **Backoffice edit + view.** A date control in `edit_respondent_form._build_field_for_definition` and a branch in the `render_view_field` macro.
5. **Type-guessing.** `guess_field_types` could learn to spot ISO dates; not required, and arguably it should _not_ auto-convert, since flipping a field to DATE has consequences. Leave it alone.
6. **CSV import.** Imported DOB values are free text. Parse leniently (ISO, `dd/mm/yyyy`), and where parsing fails the derived field takes its fallback rather than the import failing. Worth reporting the count in the import's `errors` list, which is already a general "things you should know" channel.

**PII note.** Date of birth is personal data of a more sensitive kind than most of what we hold. It lands in `Respondent.attributes`, so `delete_personal_data()` blanks it along with everything else (`dict.fromkeys(self.attributes, "")`) — the right-to-erasure path is already correct, no change needed. Two things to flag in the eventual UI copy: the age bracket is itself blanked by erasure (correct — it is derived from PII), and **year of birth (§3.1) should be offered as the default**, with full date of birth the deliberate opt-up for organisers who need it. Collecting a year rather than a full date is a genuine data-minimisation win for no loss of bracketing accuracy in most configurations, and it is the kind of default we should be setting rather than merely permitting. Nothing here changes the cookie/analytics conclusions in [docs/personal-data.md](../../personal-data.md).

**As-of date — decided: a fixed date, always. There is no "today" option.**

The original brief said "date to calculate age on — default to today". On review that is the wrong default: a relative date means the derived value depends on _when derivation ran_, so a recompute six months later silently moves people between brackets, and the eligibility sentence (§3.2) has no specific date to name. So:

- `as_of_date` is a **required** field on `AgeBracketRule`. No `None`, no resolve-to-today.
- The config form **pre-fills** it from `Assembly.first_assembly_date` when that is set (it is `date | None` today).
- When the assembly has no `first_assembly_date`, the organiser must enter a date. **The derivation cannot be saved without one** — a validation error on the field, not a silent fallback.

The upshot is that derivation becomes fully deterministic: recomputing a year later gives the same answer, which makes the recompute in §6 idempotent and removes the "warn when the field is date-relative" case entirely.

Worth noting for whoever builds the config form: this makes `first_assembly_date` load-bearing where it previously was not. It stays optional on `Assembly` — we are not making it required — but an assembly without one now costs the organiser an extra decision at derivation-config time.

---

## 4. Computing derivations

### 4.1 Where the code lives

Per §2.6, the rule classes stay in the domain and know nothing about each other; the dispatch that picks a rule and feeds it the right arguments lives in the service layer, because large mappings need a repository.

- **Option 1 (chosen)** — rule classes in `domain/respondent_derivation.py`, dispatch and orchestration in `service_layer/derivation_service.py`:
  ```python
  # service_layer/derivation_service.py
  def apply_derivations(
      respondent: Respondent,
      field_defs: list[RespondentFieldDefinition],
      lookups: Mapping[uuid.UUID, Callable[[str], str | None]],   # keyed by derived field id
  ) -> None: ...
  ```
  `apply_derivations` reads source values off the respondent (`attributes`, or a top-level column when the source is a fixed field), calls `derived_value_for` per derived field, and writes results back into `respondent.attributes`. It touches no repository — the caller loads the schema and builds the `lookups` — so it stays unit-testable with no database and no Flask.
- **Option 2** — a method on `Respondent`. Rejected: `Respondent` has no business knowing about the schema, and it would need the schema passed in anyway.
- **Option 3** — a SQLAlchemy `before_flush` event hook so derivation is impossible to forget. Rejected: hidden magic, needs DB reads mid-flush for large mappings, and makes the bulk import path unpredictable. The four call sites are few enough to hook explicitly.

New service module `service_layer/derivation_service.py` holding: config CRUD, mapping upload, the dispatch, `apply_derivations`, and recompute/backfill (§6).

### 4.2 The call sites

| Call site                                                     | When                                                            | Note                                                                       |
| ------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `registration_submission_service._create_and_save_respondent` | after `cleaned_data` is built, before constructing `Respondent` | schema already loaded by the caller — pass it down rather than re-querying |
| `respondent_service.create_respondent`                        | before `uow.respondents.add`                                    | needs a schema load                                                        |
| `respondent_service.import_respondents_from_rows`             | inside the row loop, via `respondent_from_row`                  | **load schema + build lookups once, outside the loop**                     |
| `respondent_service.update_respondent`                        | after `respondent.apply_edit(...)`, before `uow.commit()`       |                                                                            |

`respondent_from_row` is currently a pure function with no `uow` — pass the prepared schema and lookups in as optional arguments rather than giving it repository access, so it stays unit-testable.

For large mappings in the import path, a per-row indexed SELECT over thousands of rows is avoidable: gather the distinct source values for the batch and fetch matching entries in one query (`WHERE field_id = ? AND lookup_key = ANY(...)`), then look up in memory. Worth doing from the start — a 5,000-row import should not become 5,000 extra round trips.

### 4.3 Precedence: what if the incoming data already has the derived column?

Real scenario: an organiser exports respondents (the export writes derived fields as ordinary columns), edits, and re-imports; or their source system already computes `age_bracket`. Options:

- (a) **Derivation always wins.** Simple, consistent. Silently discards a supplied column.
- (b) **Supplied column wins.** Undermines the whole feature.
- (c) **(Recommended) Derive when the source values are present and usable; otherwise keep the supplied value; otherwise fall back.** Add a line to the import `errors` list (which is really a "notes" channel) whenever a supplied derived column was overwritten, so it is visible rather than silent.

Option (c) makes export→edit→re-import round-trip sanely, and makes a partial import (source column missing) non-destructive. **Decided: (c).**

### 4.4 Chained derivations

Intersection (post-MVP) derives from two fields that may themselves be derived. For MVP, **validate at config time that every source field is not itself derived** and compute in a single pass. `apply_derivations` takes the full field list and iterates, so adding a topological sort later is a local change. Also worth a config-time cycle check even in MVP, cheap insurance.

### 4.5 Failure and fallback

Decision taken: **store a fallback value, accept the submission.** Concretely:

- Age: below `min_age` → `under-16` (using the configured minimum), above `max_age` → `100+`. These are real brackets in your example, not errors — an assembly with a 16+ eligibility rule still wants to see that someone under 16 registered despite ticking the eligibility box (§3.2). Missing or unparsable date / year → the configured fallback. A year-of-birth outside a sane range (say, before 1900 or in the future) is a typo, not a person, so it takes the fallback rather than producing a `100+`.
- Mappings: no match → the configured fallback (default `"unknown"`).
- The fallback value **must** be in the field's `options` so the value round-trips through the edit form and export cleanly, and so the organiser can see it in target counts. Suggest the config UI adds it automatically.
- Every fallback is worth counting: knowing _how many_ respondents fell back is the organiser's signal that their postcode table has holes. That is what `RecomputeReport` carries (§8).

---

## 5. The mapping tables

### 5.1 Small mapping

Config UI: pick the source choice field, declare the output values, then one row per source option with a dropdown of output values. Because the source is a `CHOICE_*` field we know the complete input set — so the UI can show every option and flag any that are unmapped, and "unmapped" is a config-time warning rather than a runtime surprise.

### 5.2 Large mapping — CSV upload

- Two columns. Match headers by normalised name (`normalise_field_name` in `domain/respondents.py` already does the lowercase/strip work) against the source field key and the derived field key — your "postcode" / "region" example. Fall back to positional (first = input, second = output) with a warning if the headers don't match, rather than rejecting.
- Validate outputs against the declared option list; report unknown outputs with counts and offer "add these as options" vs "reject".
- Tens of thousands of rows is the normal case, not the extreme one (§5.3): an invite list of 50,000 postcodes is routine. Upload is a normal form POST parsed in memory then `bulk_add`. Suggest a row cap around 250,000 with a clear error above it — well clear of real invite lists, and low enough that a request-cycle upload stays sane. Beyond that we would want the Celery path ([docs/background_tasks.md](../../background_tasks.md)), which is not MVP.
- **GDPR:** a postcode→region table is reference data, not personal data, so storing it long-term is fine and does not touch the erasure story in [docs/personal-data.md](../../personal-data.md). The _uploaded file_ must not be persisted — parse to rows, discard the file. That is the existing rule and this path obeys it naturally.

### 5.3 Match modes — the postcode problem

This one matters. A registrant types `SW1A 1AA`. An organiser's mapping table almost certainly lists _outcodes_ (`SW1A`) or districts, not all 1.8M full postcodes. Exact matching fails for every single registrant.

Options:

- (a) **Exact match only** (after normalising: uppercase, strip all whitespace). Correct only if the organiser's table is at the same granularity registrants type.
- (b) **A `match_mode` on the rule: `EXACT` or `LONGEST_PREFIX`.** Longest-prefix normalises both sides and finds the longest stored key that is a prefix of the input — so `SW1A1AA` matches a stored `SW1A`, and one table can mix granularities. A small number of prefix queries per lookup, or in memory for the batch case.
- (c) Postcode-specific normalisation baked in (split off the inward code, match on the outward code). Too special-cased; prefix matching gets the same result generically.

**Decided (provisionally): (a), exact matching only.** Your point in review kills the premise of my original recommendation — the postcode list is usually **the list of postcodes we sent invites to**, not the whole country. A 50,000-row invite list matched exactly is a completely reasonable table, and 50,000 rows is comfortable in the entries table with an index on `(field_id, lookup_key)`.

Two consequences worth being deliberate about:

- **Normalisation is now doing all the work.** With full postcodes on both sides, `SW1A 1AA` / `sw1a1aa` / `SW1A  1AA` must all collapse to the same key, on upload _and_ on lookup, or the match rate quietly craters. One normalisation function, applied in both places, unit-tested against the messy variants — this is the single highest-risk detail in the large-mapping work.
- **A non-match is now meaningful information**, not just a gap. If the table is the invite list, an unmatched postcode means the registrant is outside the invited area, has moved, or has typo'd. That makes the unmatched-inputs list in the recompute report genuinely worth surfacing rather than a nice-to-have.

`match_mode` is **not** stored in MVP — absent means exact. It is a JSON config key, so adding `LONGEST_PREFIX` later needs no migration and no config-shape change. Still open pending your check with the team (§12, Q-A): if the tables turn out to be outcode-level in practice, prefix matching comes back and it is a bigger piece of work than it looks.

---

## 6. Adding or editing derived fields when respondents already exist

You asked. My answer: **yes, allow it, with an explicit recompute.** Forbidding it would be unworkable — the normal order of events is import-or-open-registration first, configure targets second.

Options considered:

- (a) **Forbid once respondents exist.** Simplest, and wrong for the actual workflow.
- (b) **Allow, apply to new respondents only.** Leaves the pool half-derived — the worst outcome, because the resulting target counts are quietly wrong.
- (c) **(Decided) Allow, and recompute every affected respondent, synchronously.** Creating or editing a derivation recomputes the pool and reports what happened — "1,204 respondents updated, 37 fell back to _unknown_".
- (d) As (c) but via Celery for large pools. Keep it synchronous for MVP with batched commits, and lift it into a task if real-world timings demand it. The existing task system is there if we need it.

**A dry-run preview before applying is parked, not built.** Your point stands: the common case is configuring these fields on an assembly with no respondents yet, where a preview shows nothing and costs a click. The report after the fact carries the same numbers. Recorded here so it is easy to pick up if organisers start configuring derivations against live pools: `derived_value_for` is pure, so a `preview_recompute` that shares the apply path is a small addition whenever we want it.

Details for (c), all confirmed in review:

- Skip `RespondentStatus.DELETED` respondents — their attributes are deliberately blanked and must stay that way.
- The recompute records nothing in `Respondent.comments`. Derivation is not a user edit and 1,200 identical comments would drown the activity log.
- **Warn when the assembly has completed selection runs.** `SelectionRunRecord` snapshots the _targets_ but not respondent attributes, so recomputing a derived field changes the data a past run was based on. It does not invalidate the run's results, but it does make the run un-reproducible. A warning is enough; blocking would be over-reach.
- Deleting a derived field: leave the computed values in `attributes` (consistent with `delete_field`'s existing "respondent attribute data is untouched" behaviour) and drop any mapping rows via the FK cascade.

Note that with `as_of_date` fixed (§3.3) an age-bracket recompute is now **idempotent** — re-running it changes nothing unless the config or the source data changed. Only mapping recomputes can move values without a config change, and only because the mapping table was re-uploaded.

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
recompute_derived_field(uow, user_id, assembly_id, field_id)                    -> RecomputeReport
derivations_depending_on(uow, assembly_id, field_key)                           -> list[RespondentFieldDefinition]
load_mapping_lookups(uow, assembly_id, field_defs)                              -> dict[uuid.UUID, Callable]
derived_value_for(field_def, rule, source_def, source_value, lookup=None)       -> str    # pure dispatch, §2.6
apply_derivations(respondent, field_defs, lookups)                              -> None   # in-memory, mutates
```

`RecomputeReport` carries `total`, `changed`, `fell_back`, and a sample of unmatched inputs — that last one is what an organiser needs to fix a postcode table (§5.3). `preview_recompute` is deliberately absent, per §6. Permission checks use the existing `_ensure_manage_permission` pattern; all messages `_l()`-wrapped per the i18n rules.

---

## 9. UI touchpoints — handover notes for frontend / design

Not a specification. This is the list of surfaces the frontend and design work will touch, plus the constraints the backend design imposes on them. It is deliberately not fleshed out further.

- **Schema page** (`respondent_field_schema/view.html`): "Add derived field" action; derived rows get an "Edit derivation" link and read-only type/options cells.
- **Three config pages**, one per derivation type, since their forms have nothing in common. The age one can preview its bracket labels live as boundaries are typed (Alpine, flat `x-model` properties per the CSP patterns).
- **Large-mapping page**: upload form, row count, "replace table" action, list of unmatched inputs from the last recompute.
- **Registrant detail / edit**: replace the `"(derivation not yet implemented)"` string with the real value, rendered read-only. A "why this value?" hint (_derived from postcode SW1A 1AA_) would be genuinely useful for confirmation callers.
- **Registration form starter HTML**: `DATE` field rendering in both generators. Derived fields are already excluded.
- **Export**: no change — derived fields are ordinary attributes.

Constraints that are not obvious from the screens, and that the backend will enforce regardless:

1. **Derived fields are read-only everywhere a respondent is edited.** Their value, type and options are owned by the derivation (§2.7).
2. **An age derivation cannot be saved without an as-of date** (§3.3). Pre-fill from `Assembly.first_assembly_date` where it exists; otherwise it is a required field, and "leave blank for today" is not an option we offer.
3. **The 1 January assumption must be stated on the page** whenever the source is a year-of-birth field (§3.1) — it moves people between brackets and organisers should not discover it by accident.
4. **Year of birth is the recommended source, full date of birth the opt-up** (§3.3 PII note). The copy should lead with the data-minimising choice.
5. **Saving a derivation triggers a recompute of the whole pool** and returns counts to display (§6). No dry-run step to design.
6. Accessibility per [component_accessibility.md](../component_accessibility.md); the GOV.UK date input pattern has a documented fieldset/legend structure to copy rather than invent.

---

## 10. Migration

One Alembic migration (`uv run alembic revision --autogenerate`, then hand-check):

1. `respondent_field_definitions`: add `derivation_type` (String(32), not null, server_default `''`), add `derivation_config` (JSON, nullable), drop `derivation_kind`. **No data to preserve, confirmed both ways:** every existing row holds the column defaults (`is_derived=false`, `derived_from=NULL`, `derivation_kind=''`) because nothing has ever written to them, and a grep for non-test writes finds none. So this is a plain drop-and-add — no backfill, no data migration, no need to keep `derivation_kind` around during a transition.
2. Create `respondent_field_mapping_entries` (Option C, from the start — §2.4).
3. `tests/conftest.py::_delete_all_test_data` — add the new table _before_ `respondent_field_definitions`. Same for `delete_all_except_standard_users()` in `tests/bdd/conftest.py`.

Neither `FieldType.DATE` nor `RespondentFieldGroup.DERIVED` needs a migration — both columns are `EnumAsString`. But `src/js/components/service-docs/fields.js` and `templates/backoffice/service_docs/_fields.html` enumerate field types and will need the new value, and anything iterating `GROUP_DISPLAY_ORDER` picks up the new group for free.

---

## 11. Testing

Per the no-exceptions policy, all three layers:

- **Unit** — bracket-label generation across edge configs (no boundaries, boundary equal to min/max, unsorted input, duplicates); `min_age <= 0` and a missing `as_of_date` both rejected at construction; age at an exact boundary and on a birthday; leap-year birthdays; **year-of-birth arithmetic against a date-of-birth source for the same person, including the December-born case in §3.1, and out-of-range years**; `eligibility_sentence()` wording and its translation parameters; `derived_value_for` dispatch for each rule type incl. every fallback path; date parsing and rejection; **postcode normalisation against the messy variants — this is the one in §5.3 that decides whether large mapping works at all**; CSV mapping parsing (header match, positional fallback, duplicate keys, unknown outputs).
- **Contract** — the mapping-entry repository against the abstract interface, following the existing contract-test pattern.
- **Integration** — derivation on each of the four write paths; recompute with report counts; **recompute is idempotent for age brackets** (§6); source-field protection rules; import precedence (§4.3); large-mapping batch lookup does not degenerate to N queries at 50,000 rows.
- **E2E / BDD** — configure an age bracket and see a registration land in the right bucket; upload a postcode table and see the region target populate; edit a derivation on an existing pool and confirm the recompute.

---

## 12. Open questions, and what we parked

### Still open

**Q-A — Confirm the granularity of real postcode mapping tables (§5.3).**
You said you would check with the team. The design now assumes exact matching against an invite-list-sized table (tens of thousands of full postcodes). If it turns out organisers typically hold outcode- or district-level tables, longest-prefix matching comes back into scope — and it is a bigger change than it looks, because it changes the lookup from an index hit to a prefix search and changes how the batch import path loads its lookups. Worth settling before the large-mapping step starts, not during it.

**Answer:**

**Q-B — The fallback value (was Q5).**
Still unanswered. Proposing the literal `"unknown"`, editable per field, auto-added to the options list. Is there a house convention to match instead (`""`, `"not specified"`, `"other"`)? It shows up in target counts, so it wants to read as "needs attention" to an organiser scanning the page. With exact postcode matching (§5.3) this value will appear more often than it would have with prefix matching — everyone outside the invited area lands on it — which makes the wording matter more than it did.

**Answer:**
COMMENT: "UNKNOWN" as the fallback value is what we tend to use - note the all-caps.

**Q-C — Where the `DERIVED` group sits in `GROUP_DISPLAY_ORDER` (§2.8).**
Proposing between `CONSENT` and `OTHER`. Trivial to change later; flagging only because it affects every registrant detail page.

**Answer:**

### Settled in review

|                        | Decision                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Storage                | Full Option C from the start — config JSON on the field, mapping rows in `respondent_field_mapping_entries` (§2.4) |
| Rule classes           | No shared `derive()` signature; no `DerivationContext`; dispatch lives in the service layer (§2.6)                 |
| Output values          | Reuse the existing `options` column (§2.7)                                                                         |
| Age source             | One `AGE_BRACKET` type; precision follows the source field's `field_type` (§3.1)                                   |
| Year of birth          | 1 January assumption, no alternatives (§3.1)                                                                       |
| As-of date             | Required fixed date, pre-filled from `first_assembly_date`; never "today"; cannot save without one (§3.3)          |
| `min_age`              | Must be > 0                                                                                                        |
| Field group            | New `RespondentFieldGroup.DERIVED` (§2.8)                                                                          |
| Eligibility sentence   | Domain function only; delivery mechanism deferred (§3.2)                                                           |
| Import precedence      | Derive when sources are usable, else keep the supplied value, else fall back (§4.3)                                |
| Large mapping matching | Exact only, pending Q-A (§5.3)                                                                                     |
| Recompute              | Applies directly on save; no comment per respondent; warn when selection runs exist (§6)                           |

### Parked ideas

- **Dry-run preview before recompute** (§6) — the common case is configuring derivations before any respondents exist. Cheap to add later, since the dispatch is pure.
- **`LONGEST_PREFIX` match mode** (§5.3) — no config key stored in MVP, so adding it needs no migration.
- **Celery-backed recompute and mapping upload** for very large pools (§5.2, §6).
- **`TargetValue` FK** replacing the `options` list on derived fields (§2.7).
- **Intersection derivation** — out of scope by your original brief.

---

## 13. Rough sequencing

1. `FieldType.DATE` end to end — validator, form parsing, starter HTML, edit/view, tests. Independently useful, no derivation involved. Deferrable if we want to ship year-of-birth brackets first: an `INTEGER` year source needs none of this.
2. Data model: `derivation_type` + `derivation_config` + the `respondent_field_mapping_entries` table + migration; `RespondentFieldGroup.DERIVED`; the three rule dataclasses and `derived_value_for`. Domain-only, fully unit-tested.
3. Age bracket: config page (both source precisions, required as-of date, eligibility sentence), wire the four write paths, recompute + report.
4. Small mapping: config page, source-field protection rules (§7).
5. Large mapping: CSV upload, normalisation, batch lookup, unmatched-inputs reporting.
6. Intersection — separate piece of work, with the "we generally do not recommend this" warning and its dead "see docs for why" link.

Steps 1 and 2 are the ones with no user-visible output and the most leverage; steps 3–5 each land a usable feature. Note that step 2 now creates the mapping table even though nothing uses it until step 5 — that is the deliberate consequence of taking full Option C up front, and it keeps the schema to one migration.
