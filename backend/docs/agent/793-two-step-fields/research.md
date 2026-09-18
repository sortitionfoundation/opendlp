# Two-step fields setup — research, critique, and open questions

**Status:** Decided — Chewie answered every §8 question on 2026-09-14; decisions
are folded into each section below and recorded verbatim in §8
**Date:** 2026-09-13 (decisions recorded 2026-09-14)
**Issue:** 793 (follow-on from the derived-fields backend and the fields-tab modal spike)
**Branch:** `793-two-step-fields`

The proposal under examination: split field setup into stages —

- **Step 0 — targets.** As today, no change.
- **Step 1 — target data sources.** For each target, say where its data comes
  from: an exactly-matching registration field, a registration field with more
  options plus a small mapping, a large (postcode) lookup, or an age bracket
  from a date/year of birth. Saving creates the registration field **and** the
  derived field (none needed for the exact-match case).
- **Step 2 — registration page fields.** Start from the fields step 1 created;
  arrange into sections, add extra fields, order them.

**Decisions at a glance (2026-09-14):** the full two-step flow is the
committed direction (§7 is not being taken). Both steps live inside the
**registration workflow** (§4.3), shaped as a revisitable **task-list hub**,
not a wizard (§4.4). The link is the field-side nullable `target_category_id`
FK (§5.1); sections stay the `RespondentFieldGroup` enum this round (§5.3).
Target edits after linking: mark-stale + explicit re-sync; category rename
while linked warns and requires an explicit force-unlink, never a cascade
(§4.5). Step 2 replaces the fields tab; derived fields exist only in step 1
(§4.7). MVP ends with the skeleton CTA + staleness warning (§4.6). The
`793-derived-fields-ui` spike is not landed as-is — its unmerged pieces are
retargeted into the new flow, branching from the current commit (§8 Q11).

---

## 1. The headline finding: this design already half-exists on paper

`docs/explainers/workflow-targets-and-fields.html` describes almost exactly
this flow. Its **Flow 6 — "Create field(s) from a target"** has the same four
methods under the same logic ("start from the target and let it fill in what
it can — the fastest route to a form that passes the coverage check"):

| Explainer Flow 6 | This proposal's step 1 |
| --- | --- |
| Exact copy | registration field with same options |
| Map from more options | registration field with more options + small mapping |
| Map postcode to value | large mapping |
| Age ranges | age bracket from date/year of birth |

The explainer also has the **coverage check** ("can every target get its data
from these fields?") as the gate between fields and form generation, free-form
**sections**, and an open-questions list that overlaps heavily with what this
document raises (deleting a target a derived field feeds; the map-from-more
ordering constraint; coverage check button-vs-automatic).

The difference — and it is a real improvement — is one of emphasis: the
explainer treats Flow 6 as *one of several entry points* on a fields page,
while this proposal makes it **the primary step in its own right**, with the
fields page (step 2) reduced to arranging what step 1 produced plus adding
non-target extras. And step 1 goes further than Flow 6 in one useful way: the
source field (the "more options" field, the postcode field, the DOB field) is
**defined inline and created in the same save**, which dissolves the
explainer's open question about "map more to fewer" requiring its source field
to exist first.

The current modal spike (`793-derived-fields-ui`, see
[plan-simple-ui.md](../793-derived-fields/plan-simple-ui.md)) sits between the
two: its decision Q8 already made the target mandatory and made it own the
derived field's key/label/outputs. The two-step proposal is essentially
promoting Q8 from "a panel inside the add-field modal" to "the organising
principle of the whole flow". Much of the spike's config panels (age config
with live preview, mapping table, upload dialog, recompute report display) is
directly reusable as step-1 UI.

## 2. What the code gives us today (verified 2026-09-13)

### 2.1 Backend derived-field machinery — complete

From the `793-derived-fields` chunk (`service_layer/derivation_service.py`):
`create_derived_field` / `update_derivation` (both recompute the pool and
return a `RecomputeReport`), `upload_large_mapping`, `recompute_derived_field`,
`derivations_depending_on`, `compatible_source_fields`, plus the rule classes
in `domain/respondent_derivation.py`. Source-field protection is wired into
the schema service (delete/type-change blocked, option renames cascade into
small-mapping configs). Step 1 is a new orchestration over this surface, not
new derivation machinery.

One detail worth copying: the spike's derived-field route uses the target's
name **verbatim** as the field key
(`entrypoints/blueprints/respondent_field_schema.py:975-980`, with a comment
explaining why) — because the runtime target↔field join is a *case-fold-only*
name match, **not** `normalise_field_key`. `age_bracket` does not match a
target named `Age Bracket`. Step 1's exact-match fields must do the same.

### 2.2 How targets link to fields and values — name-coincidence, no FK

- **Category → field:** case-insensitive exact name match, in three places
  that deliberately agree: `respondent_field_spec_service.build_field_spec`
  (~:101), `target_respondent_helpers.get_respondent_counts_for_category`
  (:32), and the spike's `_matching_choice_target`
  (`blueprints/respondent_field_schema.py:378`).
- **Value → attribute value:** the backoffice UI counts by **exact,
  case-sensitive** string match (`templates/backoffice/targets/category_block.html:160`),
  while the sortition library at selection time is **case-insensitive**. So
  `Male` target vs `male` data selects fine but shows "0 respondents" in the
  UI. Exact-copy creation from the target eliminates this footgun — a point
  in the proposal's favour.
- **No FK anywhere.** `TargetCategory` (single table, values as a JSON list,
  unique `(assembly_id, name)`) knows nothing about fields; fields know
  nothing about targets. `target_service` has **no protection at all** in the
  other direction: you can rename or delete a target that a derived field
  feeds, silently orphaning it. (`derivations_depending_on` protects
  *source* fields from field-side edits; nothing protects anything from
  target-side edits.)
- `create_target_category` (`target_service.py:166`) already auto-populates
  values from a case-insensitively matching respondent column with few
  distinct values — the *reverse* flow (data first, targets second) exists
  and matters for the import-first workflow (§4.3).

### 2.3 The registration page — authored HTML that never regenerates

- The live form is an organiser-authored Jinja blob
  (`domain/registration_page.py:347 RegistrationPageHtml`). Starter HTML is
  **copy-paste via the "Show Form Skeleton" modal**, never auto-inserted, and
  nothing rewrites or checks the blob when the schema changes.
- `on_registration_page` (NO / YES_OPTIONAL / YES_REQUIRED) drives **server-side
  submission validation independent of the HTML**
  (`registration_submission_service._validate_form_data:131-162`). Known
  drift consequence: add a YES_REQUIRED field without editing the HTML and
  **every submission fails**.
- "Sections" today = `RespondentFieldGroup`, a **fixed enum** (ELIGIBILITY,
  NAME_AND_CONTACT, ADDRESS, ABOUT_YOU, CONSENT, OTHER, DERIVED). It drives
  both the backoffice registrant page grouping and the starter HTML's `<h2>`
  sections; `sort_order` orders within a group. The explainer instead assumed
  **free-form named sections**. This is a genuine fork in the road for step 2
  (§5.3, Q4).

### 2.4 Flow/wizard machinery

No setup wizard exists; navigation is flat assembly tabs with soft gating
(`assembly_service.get_tab_enabled_states`). A reusable stepper component
exists (`templates/backoffice/components/stepper.html`, wizard and tabs
modes), used today only by the registration editor's form → email → preview
sub-flow.

## 3. Assessment: what the two-step split gets right

1. **It matches the honest direction of causality.** Organisers agree targets
   with the client in target-shaped language; the form is a means of getting
   target data. The current spike's "add a field, type = Derived, now pick a
   target" is backwards — you configure the *means* and then attach the
   *end*. Step 1 asks the question the organiser actually has: "how will
   Region get its data?"
2. **Coverage becomes a visible checklist instead of an emergent property.**
   A per-target list with "no source yet" states *is* the explainer's
   coverage check, rendered as a page rather than run as an audit.
3. **It collapses the ordering constraint.** Creating source field + derived
   field in one save removes "the choice field must exist before you can map
   from it" (explainer open question) and the current spike's inline
   "no compatible field exists yet" dead-ends.
4. **Step 2 becomes safe.** Once type/options/derivation are owned elsewhere,
   arranging sections and ordering is low-stakes work that cannot break
   selection — a good property for the least-technical users.
5. **Exact-copy creation guarantees value-string equality** between target
   values and field options, closing the `Male`/`male` UI-counting trap
   (§2.2).

## 4. Critique and wrinkles

### 4.1 Shared source fields — step 1 must "create *or reuse*"

The proposal says "when you save, the server will create the field". But
sources are shared in practice: postcode feeds *Region* **and** *IMD
quintile*; one DOB field could feed two bracketings. Configuring the second
target must reuse the existing postcode field, not create `postcode_2`. So
each step-1 method needs a "use existing field / create new" affordance —
prefilled sensibly (if a compatible field whose name matches the default
already exists, default to reusing it). This also gives legacy assemblies
(fields built the old way) a path through step 1: "use existing field".

**Decision:** confirmed — create-or-reuse, plus "use existing field as-is".
The same affordance also covers the CSV case: the raw data (say, postcode)
arrives in an upload rather than from the form, but the organiser still wants
OpenDLP to derive the extra fields from it — "use existing field" plus a
derivation, with no registration field created.

### 4.2 The recompute report on a fresh source field will look alarming

Creating source + derived field on an assembly that *already has respondents*
means no respondent has the source value yet → the recompute reports "1,204
fell back to UNKNOWN". That is correct (precedence rule (c) keeps any supplied
values from imports) but reads as failure. The report display needs one line
of copy for this case: "Existing respondents have no *Postcode* yet — their
*Region* will show UNKNOWN until the data arrives or is imported."

**Decision:** low priority — this case should be rare, since target sources
will normally be configured on brand-new assemblies (all live assemblies are
still on Google Sheets, where derivation doesn't apply). The line of copy is
worth having but is polish, not a launch requirement.

### 4.3 Not every target's data comes from the registration form

- **CSV-import-first assemblies**: the pool arrives with columns already
  present; targets may be satisfied by imported data with no registration
  field at all (and `create_target_category` already auto-populates values
  from such columns).
- **Google-Sheet assemblies**: no DB respondents; derivation doesn't apply at
  all (research §1); the fields tab is already read-only for them.

Step 1 therefore needs a per-target answer that creates nothing: roughly
"the data is already in the imported respondent data" (satisfied when a
matching column exists), plus a read-only explanation for gsheet assemblies.
Otherwise the checklist nags forever on assemblies that are configured
correctly.

**Decision:** both steps live inside the **registration workflow**. If you
are not creating a registration page you probably don't need derived fields
either, so the flow simply isn't in your way — at most it becomes an advanced
option kept hidden when the registration page isn't in use. Step 1 does get
the per-target "data comes from the import" answer that creates nothing.
Gsheet assemblies don't show the fields section at all: their fields tab
reduces to "fields are defined by the spreadsheet — manage them there".

### 4.4 Steps must be revisitable — a task-list hub, not a wizard

The research already established the real order of events is often
import-first, targets-second; targets get edited late; and "the check targets
button… is a button you come back to" (explainer). A one-way wizard would
fight that. The natural shape is the GOV.UK **task-list pattern**: three
named steps with per-step (and per-target) status, freely revisitable, with
soft nudges ("2 of 4 targets have no data source") rather than gates. The
existing stepper component in tabs mode, or a plain task-list page, both fit;
tab gating precedent already exists.

**Decision:** agreed — task-list hub, not a wizard, sitting inside the
registration workflow (§4.3).

### 4.5 What happens when targets change *after* step 1 — the missing half

This is where the proposal creates new obligations. Today `target_service`
can freely mutate targets; once fields are generated *from* targets, every
target edit has a downstream effect:

| Target edit | Exact-match field | Mapping-derived field | Age-derived field |
| --- | --- | --- | --- |
| Add a value | options out of date (new value unreachable on the form) | derived `options`/mapping outputs out of date | bracket labels may no longer match |
| Rename a value | option mismatch → UI counts break at once | mapping outputs stale → derives values the target doesn't have | ditto |
| Delete a value | form still offers it → respondents land outside targets | mapping rows now map to a non-value | ditto |
| Rename the category | **runtime name-match breaks immediately** — the field no longer feeds anything | same | same |
| Delete the category | field orphaned (explainer open question) | field + mapping table orphaned | field orphaned |

Two design choices:

- **Auto-cascade** (target edit rewrites field options / derived outputs +
  recompute): keeps things consistent but makes the targets page mutate the
  registration form and the pool behind the organiser's back — and the
  authored form HTML *still* won't update (§4.6), so full consistency is
  unreachable anyway.
- **Mark stale + explicit re-sync** (recommended): target edits succeed but
  flip the linked field's status to "needs attention" on the step-1
  checklist, with a "re-sync from target" action that regenerates
  options/outputs and recomputes, showing the report. Target edits are often
  exploratory; deferring the expensive, visible consequence to an explicit
  action is both safer and more legible.

**Category rename is the special case**: because the runtime join is
name-match, a rename breaks selection data flow *immediately*, and the field
key cannot follow it (it is the respondents' attribute key and the form
HTML's input name). Options: block rename while linked ("unlink first"), or
allow it and cascade a full field-key rename (attribute rewrite across the
pool + authored-HTML breakage — heavy, and a rename path for field keys does
not exist today). Same logic says target **delete** while linked should warn
and unlink (leaving an editable orphan field plus its data), not
cascade-delete respondent data.

**Decision:** mark-stale + explicit re-sync for the MVP — no auto-cascade.
For category rename, no cascading rename path will be built: attempting a
rename (or delete) while linked warns and requires an explicit force-unlink;
it then proceeds with the field(s) left as editable, unlinked orphans.

### 4.6 Step 2 ends exactly where today's real pain begins

Step 2 arranges the *schema*; the *page* is still authored HTML that nothing
regenerates (§2.3). So the guided flow, as proposed, walks the user carefully
to the top of a cliff: finish step 2, and the live form is still the old
HTML. Three levels of response:

1. **MVP:** step 2 ends with a prominent "Generate your form skeleton" CTA
   into the existing copy-paste flow, plus a **staleness warning** on the
   registration editor when any field's `updated_at` postdates the
   `form_html`'s last save. Cheap, honest.
2. **Better:** the skeleton modal offers per-section snippets (regenerating
   one section to paste is a smaller merge than the whole form).
3. **Eventually:** render the form *from the schema* with the authored HTML
   as an optional override. That is a big architectural step (it changes what
   `RegistrationPageHtml` is) and firmly out of scope here, but the two-step
   flow makes it more attractive, and it's worth not designing step 2 in a
   way that forecloses it.

**Decision:** level 1 for the MVP — the skeleton CTA plus the staleness
warning is enough for now. Levels 2–3 are agreed as direction and will
definitely be revisited down the line.

### 4.7 Where derived fields live in the UI afterwards

Once step 1 owns them, derived fields stop being things you "add" on a fields
page. Suggest: step 2 hides the DERIVED group entirely; the step-1 checklist
row for each target carries the derivation summary and its actions
(Edit config · Upload lookup table · Recompute · last report). The "Derived"
option disappears from the step-2 add-field modal. The backoffice registrant
detail page keeps showing the DERIVED group as now.

**Decision:** agreed.

### 4.8 Step 1's field-creation defaults

Small decisions the flow must make when it creates fields:

- `on_registration_page`: **Decided** — the *source* field defaults to
  YES_REQUIRED; the *derived* field is NO, since it is never on the
  registration page. (Required-vs-optional stays editable on the source
  field afterwards, Q9 — a blank answer just means UNKNOWN, which some
  organisers may prefer to forcing an answer.)
- `group`/section: run `classify_field_key` heuristics (postcode → ADDRESS,
  date of birth → ABOUT_YOU), default ABOUT_YOU; step 2 exists to fix this.
  **Decided** — yes, if cheap to do. Organiser-managed sections are a
  medium-term idea, not this round of work (§5.3).
- Labels: pre-filled from the target name (exact match) or the conventional
  name ("Postcode", "Date of birth"), editable — as the proposal says. Note
  the label is free; only the **key** is owned by the link. **Decided** —
  agreed.
- Age brackets: boundaries pre-parsed from target value names where they look
  like ranges, mismatch warns but never blocks (spike decision Q9 —
  unchanged). **Decided** — agreed.

## 5. Data model — what needs storing

### 5.1 The link (the question asked directly)

The gap: for mapping/age targets, the *derived* field feeds the target and
its *source* field is already protected via `derived_from`. But the
**exact-match case has no derived field**, so nothing marks that field as
target-linked, nothing locks its options, and nothing can render "why can't I
edit this?". Options considered:

- **(a) A boolean flag** (`is_target_linked`). Insufficient: can't say
  *which* target, so no status display, no staleness detection, no useful
  error message. Rejected.
- **(b) The target's name as a string** (`feeds_target: str`, empty = not
  linked — the house empty-string convention). Matches the loose-coupling
  style of `derived_from`, but it duplicates `field_key` (which already
  equals the target name by construction) and goes stale on rename in
  exactly the way we need to detect. Rejected.
- **(c) (Recommended) A nullable FK: `target_category_id UUID NULL`** on
  `respondent_field_definitions`, `ON DELETE SET NULL`. Set on **the feeding
  field only** — the exact-match field, or the derived field for the other
  three methods. NULL means "not target-linked" (all pre-existing fields, and
  freely-added step-2 extras). Stable across renames, cheap to query in both
  directions, and `SET NULL` makes "target deleted" legible as "this field
  is no longer linked" rather than an error.
- **(d) Target-side link** (`TargetCategory.source_field_id` or a source
  config JSON on the category). Reads well ("the target knows its source")
  and matches step 1's per-target framing — but the derivation config already
  lives on the field, so truth would split across two aggregates; and the
  targets table is written through the all-or-nothing `save_all_targets`
  bulk path and its Alpine page, which is exactly the code one does not want
  to entangle with field creation. Rejected for MVP; (c) supports the same
  UI queries.
- **(e) An IDENTITY derivation type** so *every* target has a derived field
  and one uniform code path. Superficially elegant, but the exact-match case
  would need a shadow pair (`gender_raw` on the form deriving `gender`),
  giving every export a pointless duplicate column and every organiser a
  confusing extra field. Rejected.

**Invariant to enforce with (c):** linked ⇒ `field_key == target.name`
(verbatim, per §2.1), key read-only, and target renames requiring an
explicit force-unlink while any link exists (§4.5).

**Decision:** option (c) — the field-side nullable `target_category_id` FK.

### 5.2 New locking rules (domain + service)

- A third error sibling — `TargetLinkedFieldError` alongside
  `FixedFieldError`/`DerivedFieldError` — raised by
  `RespondentFieldDefinition.update()` when type/options change on a field
  with `target_category_id` set. Label, help text, per-option `help_text`
  (already on `ChoiceOption`), group, order, `on_registration_page` stay
  editable. The modal's options editor needs a mode that locks option
  *values* while allowing option *help text* — which the proposal explicitly
  wants.
- `target_service` mutators (`update_target_category`, `delete_target_category`,
  value add/rename/delete, and their `save_all` equivalents) gain the reverse
  lookup ("fields linked to this category") to gate category rename/delete
  behind an explicit force-unlink (§4.5) and to flag staleness — the mirror
  image of `derivations_depending_on`.
- Radio-vs-dropdown: presentational, suggest leaving it editable on linked
  fields (locking only option values), see Q9.

### 5.3 Sections for step 2

Fork in the road (see §2.3): the current fixed `RespondentFieldGroup` enum
vs the explainer's free-form named sections (a new `sections` table +
`section_id` on fields).

**Recommend the enum for this iteration.** It already drives both the starter
HTML `<h2>`s and the backoffice grouping; step 2 is then a re-skin of the
existing fields tab (sections + up/down + add) with type/options editing
removed, rather than a data-model project. Free-form sections are a clean
later addition — but note they would then diverge from the backoffice
registrant grouping, which needs its own decision.

**Decision:** keep the enum for this iteration; free-form sections are
deferred to a later round of work.

### 5.4 Migration summary

1. `respondent_field_definitions.target_category_id` — nullable UUID FK,
   `ON DELETE SET NULL`, index. No backfill (legacy fields stay unlinked; an
   optional "adopt" action can set it later by name match, §4.1).
2. Field-spec JSON: serialise the link (e.g. `feeds_target` as the category
   name or null) → `spec_version` bump, schema update, fixture re-record —
   the usual three-part change.
3. Nothing else if sections stay the enum. No targets-table change.

### 5.5 New service surface

One orchestrating function per step-1 save, in `derivation_service` (or a
thin `target_source_service`):

```python
configure_target_source(uow, user_id, assembly_id, target_category_id, spec)
    -> (fields_created_or_reused, RecomputeReport | None)
```

where `spec` is one of four shapes (exact / small-mapping / large-mapping /
age). Internally: create-or-reuse the source field, call
`create_derived_field`/`update_derivation` where applicable, set
`target_category_id` on the feeding field, one UoW, one recompute. Plus
`target_source_status(uow, assembly_id) -> per-target status list` to render
the checklist (covers: linked field, legacy name-match ("matched but not
linked"), import-column match, nothing).

## 6. Minimising confusion — UX notes

- **Always name the owner, never just lock.** The direct answer to "flag vs
  name of the linked thing": store the *link* (the FK), and render it as an
  explanation — a chip reading "Feeds target: Region" with a link to the
  step-1 row where the thing *can* be edited. A disabled control with no
  stated reason is what generates confusion; a disabled control that says
  who owns it and where to go is guidance. (Same pattern as the existing
  "Fixed" chip, but with a destination.)
- **Task-list hub with per-target status** (§4.4): `Region — ✓ Postcode
  lookup, 231,401 rows · Edit · Upload table · Recompute` /
  `Gender — ✗ No data source · Set up`.
- **Reuse the explainer's method names and hint text** — "Exact copy",
  "Age ranges", "Map from more options", "Map postcode to value" are
  organiser-tested wording; the current spike's "Derived" never was.
- **Preview before save**: step 1 shows the registration question(s) it is
  about to create ("this will add *Postcode* to your form"), which makes the
  create-two-things-at-once behaviour legible instead of surprising.
- **Keep showing the recompute report in the dialog** (spike Q11), with the
  fresh-source copy from §4.2.
- **Step transitions**: after a step-1 save, nudge to step 2 ("Now arrange
  your registration page"); after step 2, nudge to the skeleton/HTML step
  with the staleness warning (§4.6). Nudges, not gates.

**Decision:** agreed with all of the above.

## 7. A minimal-change alternative, for contrast

If two new pages is more appetite than exists: keep the current tabs and add
(a) a **coverage panel on the Targets page** — per-target source status with a
"Create field from this target" button opening the existing spike modal
pre-filled (Flow 6 as an entry point, not a step); (b) the
`target_category_id` column and locking rules (§5.1–5.2) — wanted under any
variant; (c) the staleness warning on the registration editor. This captures
most of the guidance value for perhaps a third of the work, at the cost of
the fields tab remaining the confusing do-everything page. The full two-step
version is the better information architecture; this is the fallback if
scope needs cutting.

**Decision:** not taken — the full two-step flow is the committed direction
(Q12). Kept here for the record.

## 8. Decisions (answers from Doctor Chewie, 2026-09-14)

The questions as originally asked, each with the decision recorded.

1. **Hub or wizard?** A revisitable task-list (steps as status-carrying
   pages, soft nudges, no gates) over a linear wizard.
   **Decision:** agreed — task-list hub.

2. **Shared sources**: must step 1 support create-*or-reuse* for source
   fields (postcode feeding two targets), and "use an existing field as-is"
   for legacy assemblies (§4.1)?
   **Decision:** yes, support create-or-reuse (and it also serves the
   CSV-uploaded-raw-data case, §4.1).

3. **Import-only and gsheet assemblies**: does step 1 get a per-target "data
   comes from the import" answer that creates nothing (§4.3)? What should
   gsheet assemblies see?
   **Decision:** yes, support "data comes from the import". Gsheet
   assemblies don't show the fields section at all — their fields tab just
   says "fields are defined by the spreadsheet, manage them there".

4. **Sections**: keep `RespondentFieldGroup` as step 2's sections for now,
   or build free-form sections (§5.3)?
   **Decision:** keep the enum; free-form sections deferred to a later
   round of work.

5. **The link**: field-side nullable `target_category_id` FK,
   `ON DELETE SET NULL` (§5.1)?
   **Decision:** agreed — the nullable FK.

6. **Target rename while linked**: block ("unlink first"), or cascade a
   field-key rename through respondent attributes and authored HTML?
   **Decision:** no cascading — a warning with an explicit force-unlink is
   fine (rename proceeds only after the organiser confirms, leaving the
   field(s) unlinked).

7. **Target value edits after linking**: mark-stale + explicit "re-sync from
   target", or auto-cascade with recompute (§4.5)?
   **Decision:** mark-stale + explicit re-sync.

8. **Fate of the fields tab**: does step 2 replace it outright, and do
   derived fields move into the step-1 checklist (§4.7)?
   **Decision:** yes to both — step 2 replaces the fields tab; derived
   fields exist only in step 1.

9. **Linked exact-match fields**: required-vs-optional editable? Radio vs
   dropdown editable?
   **Decision:** yes to both.

10. **Step-2 add-field modal**: "Derived" option removed entirely (§4.7)?
    **Decision:** yes.

11. **The spike branch**: land `793-derived-fields-ui` first, or retarget
    its unmerged pieces directly into the new flow?
    **Decision:** retarget its unmerged pieces, branching from the current
    commit.

12. **Scope check**: minimal-change alternative (§7) in reserve, or full
    two-step flow?
    **Decision:** the full two-step flow.

## 9. Pointers

- [793-derived-fields/research.md](../793-derived-fields/research.md) — the
  backend decisions this builds on (recompute, fallbacks, protections).
- [793-derived-fields/plan-simple-ui.md](../793-derived-fields/plan-simple-ui.md)
  — the modal spike; its Q8–Q11 decisions carry forward into step 1.
- `docs/explainers/workflow-targets-and-fields.html` — Flow 6 and the
  coverage check; its open-questions list overlaps with §8.
- `docs/explainers/targets-builder-explainer.html`,
  `docs/explainers/fields-and-targets.html` — earlier guided-flow sketches.
- Key code: `service_layer/derivation_service.py` (surface listed §2.1);
  `entrypoints/blueprints/respondent_field_schema.py:955-995` (verbatim-name
  convention); `respondent_field_spec_service.py:96-111` (the join, and why
  it is case-fold-only); `target_service.py:642` (`save_all_targets` — why
  the link should not live target-side); `domain/registration_page.py:347`
  (the authored-HTML model behind §4.6).
