# sc-281 — Add an "implement recommended target changes" button (initial selection)

## Context / the problem

When you run the initial selection at the end of recruitment, the algorithm may tell you
that the targets cannot be met — but that with a few adjustments they can be. The selection
run **failure view tells you what adjustments to make, but gives you no way to make them
there.** You have to open the Targets tab and apply the changes by hand, and in practice
keep two tabs open: one showing the suggestions, the other the targets-editing interface.

sc-281 closes that gap. The replacement feature (sc-447, now Done) solved the equivalent
problem for replacement selections with one-click **Accept** buttons; this brings the same
to the initial selection, wired from the place the problem actually surfaces — the failed
run.

Branch: `281-recommended-target-button`. Companion interactive mockup: `sc-281-mockup.html`.

## Why the targets page is the place the changes happen

The structured, machine-readable suggestions only exist on the targets **Check** flow:

- `check_targets_detailed()` (`backend/src/opendlp/service_layer/target_checking.py:282`),
  on `InfeasibleQuotasError`, emits
  `TargetAnnotation(level="suggestion", field="min"|"max", suggested_value=N)` per
  category/value (`_annotations_from_infeasible_quotas`, line 189).
- A **failed selection run** only stores a plain-text `error_message` — it shows the
  adjustments as prose, with no `suggested_value` to attach a button to.

So the design is a two-part journey, not a single page:

1. **Entry point** — the failed-run view gets a link that takes you straight to the targets
   Check page *with the check already run*, so the suggestions are showing and actionable.
2. **Action** — on the targets Check page, Accept buttons apply the authoritative suggested
   values and re-check (and, when you came from a run, offer to re-run the selection).

## Decisions

- **Entry point:** add an "Adjust targets" action to the **initial-selection failure view**
  (the run progress modal) → `targets/check?from=selection&run_id=…`. This is the fix to
  Hamish's main point: the standard flow starts at "run initial selection", not the targets
  tab.
- **Action surface:** targets Check page — per-suggestion **Accept** + **Accept all**
  (mirrors sc-447).
- **Provenance-gated re-run:** **Accept all & re-run selection** only appears when you
  arrived from a selection run (`from=selection`). Reaching `targets/check` the normal way
  (after editing + saving targets) shows only Accept / Accept all + re-check — no re-run
  button, because there is no run to re-run.
- **Audit comment on accept:** accepting a suggestion records a comment on that target value
  (e.g. *"Accepted algorithm suggestion — minimum 15 → 11"*), because accepting breaks the
  percentage link and sets `minmax_manual=True`; the change should leave a trail. **Two
  candidate behaviours, decision pending** — the mockup demonstrates both:
  - **A. Auto-written** — comment written automatically on accept; stays a one-click
    server-side save.
  - **B. Review before save** — accept pre-fills the value *and* an editable comment box
    and stages the edit; nothing persists until you Save. Closer to sc-447's edit-then-run
    shape, but a larger behavioural change.

## Approach

### 1. Entry point — link from the initial-selection failure view

In `backend/templates/backoffice/components/db_selection_progress_modal.html` (the run
progress modal; footer currently only offers **Close** once `run_record.has_finished`):
- When the run `is_failed` **and** it is an initial selection
  (`task_type == select_from_db`, not the replacement task), add an **Adjust targets**
  button → `url_for("targets.check_targets", assembly_id=…, from="selection",
  run_id=current_selection)`.
- Guard: show it for initial-selection failures only (replacements have their own flow).
- Optional refinement: record on the run whether the failure was an infeasibility (has
  suggestions) so the link only shows when there is something to accept; otherwise show it
  on any failed initial run and let the Check page show what it finds.

### 2. Action — new endpoint in `targets.py`

Add `POST /assembly/<uuid:assembly_id>/targets/accept-suggestions` beside `check_targets`
(`backend/src/opendlp/entrypoints/blueprints/targets.py:366`):
1. Re-run `check_targets_detailed()` to get the **authoritative** current suggestions
   (don't trust client-sent numbers).
2. Read form: `scope` (`one`|`all`); for `one`: `category_id`, `value_id`, `field`;
   `then` (`recheck` default | `run`); carry `from`/`run_id` through for redirects.
3. Apply each targeted suggestion via existing **`update_target_value()`**
   (`backend/src/opendlp/service_layer/target_service.py:530`) — override the one suggested
   field (min→`suggested_value` keeping current max, or vice-versa), **and set `comment`**
   to the audit string (behaviour A). Reuses `set_manual_min_max` (`domain/targets.py:167`)
   and its validation; no new domain logic. Batch all applies in one `with uow:` block.
4. Redirect: `then="recheck"` → `targets.check_targets` (fresh feasibility, carrying
   `from`/`run_id`); `then="run"` → start the selection the Run button's way
   (`start_db_select_task`). Only valid when `from=selection`.

Same decorators/guards/`try-except`/`flash` structure as `check_targets`.

**Parity caveat to verify during impl:** confirm the targets-check re-derivation reproduces
the same infeasibility the run hit (same settings — same-address, test vs real,
`number_to_select`). If they can diverge, the failure view could promise adjustments the
Check page then doesn't surface.

### 3. Templates — Accept buttons + provenance + comment modes

`backend/templates/backoffice/targets/category_block.html`:
- Value-level suggestion (~line 182) and category-level (~line 89): **Accept** button in a
  small `<form method="post">` posting `scope=one`, `category_id`, `value_id`, `field`,
  `then=recheck`, `from`, `run_id`, CSRF. Design-system `button` macro (`variant="tertiary"`),
  matching `db_replacement_modal.html:97`.

`backend/templates/backoffice/assembly_targets.html`:
- When `check_result` has suggestions: **Accept all suggestions** (`scope=all,
  then=recheck`), and — **only if `from=selection`** — **Accept all & re-run selection**
  (`scope=all, then=run`).

Comment behaviour A is pure server-side (no JS). Behaviour B (review-before-save) would
instead stage the edit into the existing targets edit form with the comment pre-filled —
decide before building.

### 4. i18n

New strings (`_("Adjust targets")`, `_("Accept")`, `_("Accept all suggestions")`,
`_("Accept all & re-run selection")`, the audit-comment template) via the existing
`gettext`/`_()` path; run the repo's message-extraction step. Do not hand-edit catalogues.

## Files to modify

- `backend/templates/backoffice/components/db_selection_progress_modal.html` — "Adjust
  targets" link on initial-selection failure. **(new entry point)**
- `backend/src/opendlp/entrypoints/blueprints/targets.py` — new `accept_suggestions` route.
- `backend/templates/backoffice/targets/category_block.html` — per-suggestion Accept forms.
- `backend/templates/backoffice/assembly_targets.html` — Accept-all + provenance-gated re-run.
- (Reused) `target_service.update_target_value` (now also writing the comment),
  `target_checking.check_targets_detailed`, `db_selection_backoffice.start_db_select_task`.

## Tests

- **Component** (`tests/component/test_targets_pages.py`): `scope=one` applies the suggested
  min/max to the right value, writes the audit comment, redirects to re-check; `scope=all`
  applies all; `then=run` with `from=selection` starts a selection; the re-run button is
  absent without `from=selection`. Assert stored min/max, `minmax_manual=True`, and comment.
- **Component** (`tests/component/test_db_selection_routes.py`): a failed initial-selection
  run's modal shows the **Adjust targets** link; a successful / replacement run does not.
- **Unit** (`tests/unit/test_target_service.py`): apply-one-suggestion overrides only the
  targeted field, leaves the other bound, and sets the comment. Mirror
  `test_replacement_targets.py`.

## Verification (end-to-end)

1. Worktree: `npm ci` + generated_version.txt if fresh, then `just run`.
2. Run an initial selection on an assembly with infeasible targets → it fails.
3. In the failure modal, click **Adjust targets** → land on targets Check with suggestions
   showing and the re-run button present (came from selection).
4. Click a single **Accept** → value updates, audit comment recorded, re-check runs, that
   suggestion is gone.
5. **Accept all & re-run selection** → targets saved and a selection run starts.
6. Reach `targets/check` the normal way (edit + save) → suggestions + Accept, **no** re-run
   button.
7. `just test` (or targeted pytest); BDD auth failures are pre-existing.
