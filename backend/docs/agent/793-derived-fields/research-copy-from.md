# Research: copying targets, fields and registration pages from another assembly

Status: research / option-generation only. No decisions made, no plan yet.

The idea: when setting up an assembly you are often doing a similar job to a
previous one. Let the organiser pick a previous assembly and copy its setup —
everything, or a checklist of parts — instead of rebuilding from scratch.

## TL;DR

- **Mechanically, copying is easy.** All three kinds of object are plain Python
  domain objects keyed by `assembly_id`, with no SQLAlchemy relationship magic.
  "Read from A, rebuild with new UUIDs and B's `assembly_id`, add via the
  repository" works, and we already have a working precedent:
  `duplicate_registration_page` in `registration_page_service.py` does exactly
  this within one assembly (including deep-copying the auto-reply email
  template so the copies never share mutable state).
- **The real work is in the edges**: derived fields whose source field isn't
  copied, fixed fields that exist in *every* assembly and therefore always
  collide, registration page HTML that embeds URLs from the source assembly,
  globally-unique slugs, and target min/max numbers that were computed for a
  different assembly size.
- **Recommendation to consider**: copy-then-edit (not edit-before-write),
  per-kind collision rules rather than a blanket "only into an empty assembly",
  and ship in dependency order: targets (easiest) → fields → pages (hardest).

## Inventory: what "everything" actually is

The copyable setup, with its dependencies:

| Thing | Tables | Depends on |
|---|---|---|
| Targets | `target_categories` (values are JSON on the row) | Nothing hard — categories match respondent attribute columns *by name, case-insensitively* at display/selection time. No FK to fields. |
| Field schema | `respondent_field_definitions` | Derived fields reference their source field **by `field_key` string** (`derived_from`), not by FK. |
| Large-mapping lookup rows | `respondent_field_mapping_entries` | Belong to a derived field via `field_id`. Can be hundreds of thousands of rows (postcode → region). |
| Registration pages | `registration_pages` + `registration_page_html_sources` | Form HTML posts field keys that the **destination's field schema** must know about; may embed image/document URLs; may reference an auto-reply `email_templates` row. |
| Registration images / documents | `registration_images`, `registration_documents` (bytes in DB, unique per `(assembly_id, sha256)`) | Referenced from page HTML by absolute URL `/register/<slug>/assets/<sha>.<ext>` — i.e. via the **source page's slug**. |
| Auto-reply email template | `email_templates` (per-assembly) | Referenced by `registration_pages.auto_reply_email_template_id`. |

Adjacent things we could add to the checklist later but are out of scope for
now: selection settings (`selection_settings`, per-assembly, has its own
team-defaults logic), gsheet/CSV config, other email templates.

### The dependency graph, in words

Targets are freestanding. Fields are freestanding except that derived fields
need their source field. Pages need the field schema (the form is generated
from it and submissions are validated against it), and optionally images,
documents and an email template. So the natural copy order is:
**targets → fields (+ mapping entries) → images/documents/templates → pages.**

## The core question: can we just copy the objects?

Yes. Domain objects are constructed fresh (they are not SQLAlchemy-mapped
classes with lazy relationships), every one already has a
`create_detached_copy()`, and repositories take plain objects. A copy service
would, inside one UnitOfWork (one entrypoint, one `with uow:` as usual):

1. read the source objects,
2. rebuild each with a **new UUID**, the destination `assembly_id`, and fresh
   `created_at`/`updated_at`,
3. add them to the destination.

Things that must *not* be carried over verbatim:

- **All UUIDs regenerate.** Including the `value_id` on every `TargetValue`
  inside the category JSON — `create_detached_copy()` deliberately preserves
  IDs, so it is *not* the copy primitive; we'd write a `copy_for_assembly()`
  style constructor per kind.
- **Timestamps** reset to now.
- **Registration page state** resets: status → TEST, fresh activity log
  seeded with a "copied from assembly X, page 'Y'" entry, new slugs (slugs are
  **globally** unique across all assemblies — partial unique indexes on
  `url_slug` and `short_url_slug`; the generators
  `generate_unique_url_slug` / `generate_unique_short_url_slug` already exist).
- **Cross-references re-point.** The auto-reply template must be copied as a
  new `email_templates` row with the **destination** assembly_id (note: the
  existing `_copy_auto_reply_template` helper keeps the *source's*
  assembly_id — correct for in-assembly duplication, wrong for cross-assembly;
  don't reuse it blindly). Mapping entries re-point at the new field's id.

## Gotchas and edge cases

### Uniqueness collisions

- `target_categories`: unique `(assembly_id, name)`.
- `respondent_field_definitions`: unique `(assembly_id, field_key)`.
- `registration_pages`: name unique per assembly (when non-empty); slugs
  globally unique.
- `registration_images`/`documents`: unique `(assembly_id, sha256)` — copying
  the same image twice is naturally idempotent if we check first (the upload
  path already dedupes by sha).

**Fixed fields always collide.** Every seeded schema contains the same five
fixed rows (`email`, `eligible`, `can_attend`, `consent`, `stay_on_db`). So
"copy the field schema" can never be a blind insert into a seeded assembly —
at minimum it must *merge* fixed fields (skip, or overwrite group/order/label
settings — that's a design choice). Conversely, a brand-new assembly may have
**no** schema rows at all (seeding happens on first visit to the schema page
or first CSV upload, not at assembly creation), so the copy may also be the
thing that seeds it.

### Derived fields

- `derived_from` is a list of field-key **strings**, not FKs. A raw copy of a
  derived field whose source field is absent in the destination would pass
  domain validation (which only checks the list is non-empty) but produce a
  field whose values can never compute — a state the normal
  `create_derived_field` path explicitly refuses (`_validate_source`). We
  should not create states the UI can't create. Options: auto-include the
  source field when a derived field is ticked; or skip the derived field with
  a warning; or copy it "broken" and surface it in the schema UI (needs new UI
  for "broken derivation", so probably not).
- **Small mappings** key off the source field's option values. If the
  destination already has a source field with the same key but *different
  options*, the copied mapping half-matches. (Within one assembly the schema
  service keeps these in sync on option rename; across assemblies nothing
  does.) Simplest honest rule: if the destination already has the source
  field, either require its options to match or refuse/warn.
- **Large mappings** mean bulk-copying potentially 100k+ rows. Fine, but do it
  as a bulk insert, not object-at-a-time, and it may push the copy toward the
  background-task machinery if we allow huge ones. (Or: v1 copies the
  derivation *definition* but not the lookup table, and tells the user to
  re-upload the CSV — honest but annoying. Probably just bulk-copy.)

### Targets and assembly size

`TargetValue.min/max` were computed (or hand-set) for the **source** assembly's
`number_to_select`. After copying into an assembly with a different size:

- percentage-linked values: fine — run the existing
  `recalculate_minmax_for_assembly` after the copy and they snap to the new
  size.
- `minmax_manual` values (auto-calc link broken) and values with no percentage
  at all: carried numbers are for the wrong assembly size and nothing will
  correct them. Options: copy as-is and let the organiser edit (they'd have to
  anyway); or copy but clear `minmax_manual` where a percentage exists so
  recalculation applies; or flag them in the UI after copy. This is the main
  "silently wrong data" risk in the whole feature, worth a deliberate choice.

Otherwise targets are the easy case: no FK links, and if the category name
matches no respondent column yet, the UI already handles that (it's the normal
state before data is uploaded).

### Registration pages

The hard part, in rough order of pain:

1. **Field schema dependency.** A copied form posts the source assembly's
   field keys. If the destination schema lacks them, submissions
   break/mismatch. The copy UI should either force "fields" whenever "pages"
   is ticked, or check key coverage and warn.
2. **Embedded asset URLs.** Image snippets are absolute URLs containing the
   *source page's slug* (`/register/<source-slug>/assets/<sha>.png`). Left
   alone, the copied page hotlinks the source page — which breaks when the
   source closes, and is just wrong. A real copy must (a) copy the
   image/document rows into the destination assembly and (b) rewrite the URLs
   in the HTML to the new page's slug. The rewrite is string surgery on
   author-owned HTML — doable (the URL shape is well-defined) but it's the
   fiddliest bit. Deciding *which* images to copy: either all of the source
   assembly's images, or parse the HTML for referenced shas (parse is nicer —
   avoids dragging junk).
3. **Auto-reply template** — copy as a new row under the destination assembly
   (see above).
4. **Slugs, name, status, activity** — all reset; generators and validation
   already exist.
5. **Jinja placeholders** (`{{ assembly_title }}`, `{{ assembly_question }}`)
   resolve against the destination assembly automatically — nice, free win.

### Process / concurrency

- Double-click on "Copy" → second run hits the unique constraints. Whatever
  collision policy we pick (skip/suffix/abort) also answers this.
- Copy is not atomic with respect to the *source* being edited mid-read, but a
  single UoW/transaction reads a consistent snapshot; not a real concern.
- Nothing here touches respondents, so there's no GDPR angle beyond what the
  copied objects already carry (target comments and source URLs are
  organiser-authored, not PII).

## Permissions and scoping

- Destination: must be able to **manage** the destination assembly
  (`can_manage_assembly`).
- Source: needs a decision. Minimum defensible: **view** access on the source
  (`can_view_assembly`) — you can already see everything you'd be copying.
  Requiring *manage* on the source seems needlessly strict.
- The "copy from" picker falls out of `get_user_accessible_assemblies`:
  organisers see their own assemblies, admins see all. No new scoping concept
  needed. (No organisation entity exists, so "your organisation's assemblies"
  is not currently expressible — the accessible-assemblies list is the proxy.)
- Archived assemblies: probably *should* be offered as sources (last year's
  job is exactly what you want to copy). Worth confirming the picker includes
  them.

## Constraint options: when is copying allowed?

Rather than one global rule, a per-kind rule fits the data:

| Option | Pros | Cons |
|---|---|---|
| **A. Only at assembly creation** ("create from copy") | No collisions ever, simplest mental model, one-shot UI | Can't adopt a page/targets later; creation flow gets heavier; still needs the fixed-field merge (seeding) logic |
| **B. Any time, but only into emptiness per kind** (copy targets only if none exist; fields only if schema unseeded; pages always additive) | Simple, no merge logic, no surprise overwrites; failure mode is a clear "delete yours first" message | "I have 2 targets and want their 10" requires deleting yours first (existing `delete_targets_for_assembly` helps); fields-only-if-unseeded is awkward because visiting the schema page seeds it |
| **C. Any time, merge by name/key** (skip ones that already exist, or suffix-rename) | Most flexible, re-runnable | Merge semantics are where the bugs live (esp. derived-field/source-option mismatches); skip-vs-rename is a genuinely confusing UX either way |

A workable middle line: **targets = B** (offer "replace all" as the escape
hatch), **fields = C-lite** (merge by key, skip anything that already exists —
which cleanly absorbs the fixed-field collision as the normal case), **pages =
always additive** (names get suffixed, slugs regenerate; pages have no
collision problem beyond the name). But this is a decision for the planning
stage.

## Edit-before-write vs copy-then-edit

**Copy-then-edit is the strong default.** Copy the objects, save, then use the
existing editors (targets editor, schema page, page editor) to adjust.

- Edit-before-write means rebuilding each editor inside a wizard, plus a
  staging representation for unsaved copies — a large chunk of new UI that
  duplicates three existing, tested edit surfaces, for the benefit of saving
  one page-visit.
- The checklist ("tick what you want") gives coarse control at copy time;
  everything finer-grained is a normal edit afterwards.
- One refinement that's cheap and valuable: after the copy, show a **report**
  ("3 target categories copied; 2 values carried manual min/max sized for a
  60-seat assembly — review them; derived field 'region' copied with 180,000
  lookup rows; page 'Main (copy)' created in TEST with new slugs") with links
  to the edit pages. That captures most of the value of pre-editing at a
  fraction of the cost.

## UI shape options

1. **"Copy everything from…"** — one picker, one button. Least work, least
   control; still needs all the same merge/collision machinery underneath, so
   it saves UI work only, not service-layer work.
2. **Checklist by kind** — pick source assembly, tick Targets / Fields /
   Registration pages (pages per-page, since an assembly can have several).
   This matches the dependency structure well: ticking a page force-ticks
   fields; ticking a derived field force-includes its source. Recommended
   shape.
3. **Fine-grained per-item checklist** (every category, every field) — maximum
   control, but per-item selection multiplies the dependency edge cases
   (derived→source, page→fields) and pushes toward edit-before-write
   complexity. Not worth it for v1; per-kind (with per-page granularity) seems
   like the right coarseness.

## Rough effort feel (not a plan)

- **Targets copy**: small. Freestanding data, existing recalc helper, existing
  delete-all helper for "replace". The one design decision is manual-min/max
  handling.
- **Fields copy**: medium. Merge-by-key, fixed-field handling, derived-field
  dependency rules, bulk mapping-entry copy.
- **Pages copy**: medium-large. Mostly precedented by
  `duplicate_registration_page`, but cross-assembly adds template re-homing,
  image/document copying, and HTML URL rewriting.
- **UI + permissions + report**: medium, largely independent of the above.

Each kind is independently shippable in the order listed.

## Recorded idea (explicitly not planned now)

**Template assemblies.** An assembly status (or flag) of "template": excluded
from normal operations (no registrations, no selection), easy to find in the
copy-from picker, and maintained over time as the organisation's standard
targets/fields/pages evolve. The copy feature above is the prerequisite; a
template is then just a well-known source. Parking it here so it isn't lost.

## Open questions for Doctor Chewie

1. **Scope of "pages"**: copy one chosen page, or all of the source assembly's
   pages? (Assemblies can have several — languages/variants.)
2. **Manual min/max targets**: copy as-is, clear the manual flag where a
   percentage exists (so recalc fixes them), or copy + flag for review?
3. **Fields merge policy** when the destination already has a key: always
   skip, or offer overwrite? (Skip is safer; overwrite matters if you want to
   re-pull an updated "standard" schema — which the template idea will
   eventually want.)
4. **Derived field with missing source**: auto-include the source field, or
   skip the derived field with a warning?
5. **Source permission**: is view access on the source assembly enough?
6. Is "targets only when none exist (with a replace-all escape hatch)"
   acceptable, or do you want merge for targets too?
7. Should the copy-from picker include archived assemblies? (I'd say yes.)
