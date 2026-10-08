# Two-step fields setup — implementation plan

**Status:** Implemented — all six chunks landed on `793-two-step-fields`
(2026-09-14, commits `5380ac65..d171b4f2`); per-chunk notes below
**Date:** 2026-09-14
**Branch:** `793-two-step-fields` (already contains the `793-derived-fields`
backend and the `793-derived-fields-ui` spike commits; per decision Q11 the
spike's unmerged pieces are retargeted here, not landed separately)

## 0. Scope and shape

What we are building (all decided, see research.md):

- **Step 1 — target data sources**: a per-target checklist inside the
  Registration workflow. Each target row says where its data comes from and
  offers "Set up" / "Edit" via the four methods (Exact copy, Age ranges, Map
  from more options, Map postcode to value) plus "data comes from the
  import". Saving creates (or reuses) the source registration field and the
  derived field in one transaction, links the feeding field to the target,
  and shows the recompute report.
- **Step 2 — registration fields**: the existing fields editor re-skinned as
  "arrange the registration page": sections (the `RespondentFieldGroup` enum,
  unchanged), ordering, adding non-target extras. No type/options editing on
  target-linked fields, no "Derived" option. This **replaces the Fields
  tab**.
- Both steps live in the **Registration tab**, shaped as a revisitable
  task-list (sources → fields → page), not a wizard. Gsheet assemblies see
  none of it — just "fields are defined by the spreadsheet".
- New data: nullable `target_category_id` FK on field definitions; new
  `TargetLinkedFieldError`; target mutators gain reverse-lookup guards
  (force-unlink on rename/delete, staleness on value edits).
- MVP form-HTML story: step 2 ends with the skeleton CTA plus a staleness
  warning on the registration editor. Nothing regenerates the authored HTML.

Out of scope (explicitly deferred): free-form sections, auto-cascade of
target edits, per-section skeleton snippets, schema-rendered forms,
organiser-managed section sets.

### Assumptions made here (flag if wrong)

1. **Placement**: the Registration tab's landing view becomes a small
   task-list — *1. Target data sources · 2. Registration fields · 3.
   Registration page(s)* — where entry 3 is the existing pages list +
   takeover editor. Steps 1 and 2 are per-assembly (one field schema), while
   the existing form → email → preview stepper is per-page, so steps 1–2
   sit **above** the page editor, not inside its stepper.
2. **Staleness is computed, not stored**: a linked field is stale when its
   options (exact-match) or its derived outputs (mapping/age) no longer
   equal the target's values. Rename is impossible while linked, so
   comparing values is sufficient and needs no new column. (If we later
   want "stale because mapping outputs changed" nuances, revisit.)
3. **"Data comes from the import" is detected, not stored**: a target with
   no linked field but a case-insensitively matching respondent column
   shows as "covered by imported data". No new state to persist or forget.
4. The old `/fields` route stays reachable and redirects to step 2 (so
   bookmarks and in-flight links don't 404); only the tab entry is removed.

---

## 1. Chunk A — domain: the link and its locking rules ✅ done

Files: `domain/respondent_field_schema.py`, `domain/errors.py` (wherever
`FixedFieldError`/`DerivedFieldError` live), `adapters/orm.py`.

1. `RespondentFieldDefinition.__init__` gains
   `target_category_id: uuid.UUID | None = None`; detached-copy and
   serialisation updated.
2. New `TargetLinkedFieldError` sibling of `FixedFieldError` /
   `DerivedFieldError`. `update()` raises it for `field_type` / `options`
   value changes when `target_category_id` is set. Still editable on a
   linked field: label, help text, per-option `help_text`, group,
   sort order, `on_registration_page` (required-vs-optional), and the
   radio-vs-dropdown presentation (decision Q9).
   - Note the options editor distinction: option **values** locked, option
     **help text** editable — `update()` must accept an options list that
     differs only in help texts.
3. Invariant helpers: `is_target_linked` property; a guard that a linked
   field's `field_key` equals the target name verbatim is enforced at the
   service layer (the domain object doesn't hold the target).
4. ORM: `target_category_id` column on `respondent_field_definitions` —
   nullable UUID, FK to `target_categories.id` **ON DELETE SET NULL**,
   indexed. Alembic autogenerate migration. No backfill (legacy fields stay
   unlinked; the "adopt" action in Chunk B links them on demand).
5. Field-spec JSON (`respondent_field_spec_service`): serialise the link as
   `feeds_target` (the category name, or null) → `spec_version` bump, JSON
   Schema update in `src/opendlp/schemas/json_api/`, fixture re-record
   (`UPDATE_API_FIXTURES=1`), read the diff.

Tests: domain unit tests for every lock/allow combination on a linked
field; migration up/down; field-spec contract test.

## 2. Chunk B — service layer: configure, status, guards ✅ done

New module `service_layer/target_source_service.py` (thin orchestration
over `derivation_service` + `respondent_field_schema_service`; keeps
`derivation_service` focused on derivation mechanics).

1. `configure_target_source(uow, user_id, assembly_id, target_category_id,
   spec) -> (fields, RecomputeReport | None)` where `spec` is one of four
   shapes (exact / small-mapping / large-mapping / age), each carrying the
   source-field part (`create` with label/help/group, or `reuse:
   field_id`). Internally, one UoW context (caller-opened, per the
   convention):
   - create-or-reuse the source field (reuse validates compatibility via
     `compatible_source_fields` rules);
   - exact: create the choice field with options copied verbatim from the
     target's values, `field_key = target.name` verbatim (§2.1 of
     research.md), link it;
   - mapping/age: create source if needed, then
     `create_derived_field`/`update_derivation`, link the **derived**
     field;
   - `on_registration_page`: source field YES_REQUIRED, derived field NO
     (decision §4.8);
   - `group`: `classify_field_key` heuristics if cheap, else ABOUT_YOU;
   - return the recompute report (None for exact-match).
2. `target_source_status(uow, assembly_id) -> list[TargetSourceStatus]` —
   per-target: `linked_exact` / `linked_derived` (with derivation summary,
   lookup-row count, staleness) / `matched_not_linked` (legacy name-match —
   offers "adopt") / `import_covered` (matching respondent column, no
   field) / `none`. This is the checklist's single data source and also
   what the task-list hub summarises ("2 of 4 targets have no data
   source").
3. `adopt_field(uow, user_id, assembly_id, target_category_id, field_id)` —
   sets the FK on a name-matched existing field (validates verbatim-name
   and option compatibility; warns, never rewrites).
4. `resync_from_target(...)` — regenerate options (exact) or outputs
   (derived) from the target's current values, recompute, return the
   report. `unlink(...)` — clear the FK (field becomes a free editable
   field; derivation, if any, stays).
5. **Reverse-lookup guards in `target_service`** (mirror of
   `derivations_depending_on`): a `fields_linked_to_category(uow,
   category_id)` helper; `update_target_category` / value mutators /
   `delete_target_category` / the `save_all_targets` path check it:
   - category **rename or delete** while linked → raise a new
     `TargetLinkedError` unless `force_unlink=True` is passed, in which
     case unlink first, then proceed (decision Q6 — warn + explicit force,
     no cascade);
   - value add/rename/delete → allowed; linked fields simply become stale
     (computed, assumption 2).

Tests: service tests for all four spec shapes × create/reuse, adopt,
resync, unlink, both force-unlink paths, `save_all_targets` interaction,
and status classification for each of the five states.

## 3. Chunk C — step 1 UI: the target data sources checklist ✅ done

> Implementation note: the small-mapping method reuses an existing choice
> field only — creating the wider choice field (with its full option list)
> happens on the registration fields step first. The modal says so.
>
> Superseded: the set-up modal now creates the choice question, its answers
> and the mapping in one save — see `docs/agent/793-small-mapping-flow/plan.md`.

Files: extend `entrypoints/blueprints/respondent_field_schema.py` (or a new
`target_sources.py` blueprint — prefer new, the existing file is already
1000+ lines), templates under `templates/backoffice/target_sources/`.

1. Checklist page (HTMX-first, same fragment conventions as the spike:
   routes branch on `HX-Request`, 422 re-renders the modal, success returns
   the row/list fragment with `hx-swap-oob`): one row per target from
   `target_source_status`, e.g. `Region — ✓ Postcode lookup, 231,401 rows ·
   Edit · Upload table · Recompute` / `Gender — ✗ No data source · Set up`.
2. "Set up" modal: method chooser using the explainer's wording ("Exact
   copy", "Age ranges", "Map from more options", "Map postcode to value") —
   **not** "Derived". Panels are the spike's, retargeted: age config with
   `ageBracketPreview` + boundary prefill from target values (mismatch
   warns, never blocks), mapping table, large-mapping naming (prefill
   "Postcode"). New: the source-field create-or-reuse selector (defaults to
   reuse when a compatible name-matching field exists) and the
   preview-before-save line ("This will add *Postcode* to your
   registration form").
3. In-modal recompute report (spike Q11's `_derivation_report_modal.html`,
   reused). The fresh-source copy line ("existing respondents will show
   UNKNOWN until…") is a low-priority nicety — add if trivial.
4. Row actions: Edit config · Upload lookup table (spike modal, reused) ·
   Recompute · Re-sync from target (only when stale, with report) ·
   Unlink. `matched_not_linked` rows get "Adopt"; `import_covered` rows are
   informational.
5. Target-side surfacing: the Targets page shows the force-unlink
   confirmation when renaming/deleting a linked category (the
   `TargetLinkedError` from Chunk B rendered as a confirm step naming the
   affected fields).

Tests: route tests for each fragment/action; BDD scenarios in Chunk F.

## 4. Chunk D — step 2 UI: arrange the registration fields ✅ done

Files: `respondent_field_schema.py` blueprint + its templates, reworked in
place.

1. The editor becomes sections (enum groups) + up/down ordering + add/edit
   — with the DERIVED group hidden and the "Derived" option removed from
   the add modal (decisions §4.7, Q10). The backoffice registrant detail
   page keeps its DERIVED group display, untouched.
2. Linked fields render a chip — "Feeds target: Region" — linking to the
   step-1 row (the "always name the owner, never just lock" rule). Their
   edit modal locks type and option values, keeps label/help/option-help/
   group/order/required/presentation editable, and surfaces
   `TargetLinkedFieldError` as the explanation if something slips through.
3. End-of-step CTA: "Generate your form skeleton" into the existing
   skeleton modal, plus the nudge chain (step 1 save → "now arrange your
   registration page"; step 2 → skeleton/HTML with the staleness warning).

## 5. Chunk E — navigation and the task-list hub ✅ done

> Implementation note: the old `/respondent-schema` route needs no redirect —
> it *is* the step-2 page, reworked in place; only the tab entry went away.

1. Registration tab landing (`assembly_registration.html` +
   `backoffice_registration.py`): prepend the task-list — three entries
   with status lines (sources: n of m targets covered; fields: count +
   staleness; page: existing status), each a link. Existing pages list +
   takeover editor unchanged as entry 3. Use the GOV.UK task-list styling
   or the existing stepper in tabs mode, whichever reads better with the
   pages list below.
2. `assembly_tabs.html`: remove the "fields" tab entry. The old
   `/fields` route 302s to the step-2 page (assumption 4).
3. Gsheet assemblies: the task-list is replaced by one line — "Fields are
   defined by the spreadsheet — manage them there" — and the old fields
   route shows the same (decision Q3).
4. Staleness warning on the registration HTML editor: warn when any
   field's `updated_at` postdates the `form_html` last save (research
   §4.6, MVP level 1).

## 6. Chunk F — tests, i18n, docs, housekeeping ✅ done

> Implementation note: BDD covers exact copy e2e, age ranges with the
> recompute report, and the forced-unlink confirmation
> (`features/target-data-sources.feature`); the retired age-bracket modal
> scenario left `respondent-field-schema.feature` with it. The remaining
> scenarios from the wish list (postcode reused across two targets, adopt,
> stale→re-sync, gsheet message) are covered at component-test level in
> `tests/component/test_backoffice_target_sources.py` and
> `tests/unit/test_target_source_service.py`.

1. **BDD** (`tests/bdd/`): scenarios for — each of the four set-up methods
   end-to-end (target → source configured → field appears in step 2 →
   registrant derivation works); postcode reused across two targets;
   adopt on a legacy assembly; target value edit → stale → re-sync;
   category rename blocked then forced-unlink; gsheet assembly sees the
   spreadsheet message; step-2 lock chip and editable-help behaviour.
2. **JS**: any new/changed Alpine or HTMX helper gets vitest coverage per
   `docs/agent/frontend_js_testing.md`; fixtures (never hand-typed
   responses) for any JSON the UI consumes.
3. **i18n**: all new strings through `_()`/`_l()`; check
   `docs/language.md` for wording; `just translate-regen` +
   `just translate-check`. Reuse the explainer's method names verbatim.
4. **Fixtures/schemas**: field-spec `spec_version` bump artefacts from
   Chunk A; re-record with `UPDATE_API_FIXTURES=1` and read the diff.
5. **Docs**: update `docs/respondent_field_spec.md` (new `feeds_target`
   key); note in `docs/explainers/workflow-targets-and-fields.html` is
   *not* needed (it's a design artefact), but
   `docs/agent/793-derived-fields/plan-simple-ui.md` gets a pointer that
   its UI has been superseded by this flow.
6. **Housekeeping**: `../.secrets.baseline` regen if test line numbers
   shift; conftest delete-order untouched (no new table); `just check` and
   `just test` green before each commit; accessibility pass on the new
   checklist/modals per `docs/agent/component_accessibility.md` (the spike
   modals lack Escape-close — fix while retargeting them).

## 7. Suggested commit sequence

Each lands green on its own:

1. `feat(domain)`: `target_category_id` + `TargetLinkedFieldError` +
   migration + spec bump (Chunk A)
2. `feat(services)`: `target_source_service` + target-side guards (Chunk B)
3. `feat(ui)`: step-1 checklist + modals, spike panels retargeted (Chunk C)
4. `feat(ui)`: step-2 editor rework, derived UI removed from it (Chunk D)
5. `feat(ui)`: registration task-list hub, tab removal/redirect, gsheet
   message, staleness warning (Chunk E)
6. `test/docs`: BDD suite, i18n regen, doc updates (Chunk F — though most
   tests land inside their chunks; this is the sweep)
