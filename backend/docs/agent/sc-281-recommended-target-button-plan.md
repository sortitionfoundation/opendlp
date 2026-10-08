# sc-281 — Add an "implement recommended target changes" button (initial selection)

## Context

When an **initial** stratified selection's targets are infeasible, the targets "Check"
page already shows the algorithm's recommended min/max changes (e.g. *"Suggested minimum:
12 (currently 15)"*) — but only as read-only text. To actually apply a recommendation the
organiser must manually enter edit mode and retype the number for each value. The
replacement feature (sc-447, now Done) solved the equivalent problem with one-click
**Accept** / **Accept all** buttons. sc-281 brings that same one-click experience to the
initial selection.

Branch: `281-recommended-target-button`.

See the companion interactive mockup: `sc-281-mockup.html` (open in a browser).

## Where the recommendations already live

- `check_targets_detailed()` (`backend/src/opendlp/service_layer/target_checking.py:282`)
  runs the feasibility check and, on `InfeasibleQuotasError`, produces structured
  `TargetAnnotation(level="suggestion", field="min"|"max", suggested_value=N)` entries
  keyed by category/value (`_annotations_from_infeasible_quotas`, line 189).
- The `check_targets` route (`backend/src/opendlp/entrypoints/blueprints/targets.py:366`)
  renders these via `assembly_targets.html` → `category_block.html`, where suggestions
  appear read-only (value-level at line 182, category-level at line 89).
- A **failed selection run** only stores a plain-text `error_message` — no structured
  suggestions — so the targets Check page is the only surface with the data, and is
  already "the box with targets + immediate feasibility check" the ticket's *To consider*
  section asks us to mirror from replacements.

## Decisions (confirmed with product)

- **Surface:** targets Check page — add buttons to the existing suggestion annotations.
- **Granularity:** per-suggestion **Accept** + an **Accept all** (mirrors sc-447).
- **Action:** Accept / Accept all → apply + save + **re-check feasibility** (stay on the
  targets page). Plus a separate **Accept all & re-run selection** button → apply + save +
  start the real selection run.

## Approach

Server-side POST (no client-side form-fill): the Check page is read-only, so unlike the
replacement modal — which fills live inputs in an open form — each button submits to a new
endpoint that applies the change authoritatively and re-renders.

### 1. Backend — new endpoint in `targets.py`

Add `POST /assembly/<uuid:assembly_id>/targets/accept-suggestions` to
`backend/src/opendlp/entrypoints/blueprints/targets.py` (beside `check_targets`, ~line 366).

Behaviour:
1. Re-run `check_targets_detailed(uow, user_id, assembly_id)` to get the **authoritative**
   current suggestions (don't trust client-sent numbers).
2. Read form:
   - `scope` = `"one"` or `"all"`.
   - for `scope="one"`: `category_id`, `value_id`, `field` ("min"/"max") identify which
     suggestion to apply.
   - `then` = `"recheck"` (default) or `"run"` (the "& re-run selection" variant).
3. For each targeted suggestion, apply it by calling the existing
   **`update_target_value()`** (`backend/src/opendlp/service_layer/target_service.py:530`)
   with the value's current `value` name, current min/max, and the one suggested field
   overridden (min→`suggested_value` keeping current max, or max→`suggested_value` keeping
   current min). This reuses the manual-override path (`set_manual_min_max`,
   `domain/targets.py:167`) and its validation; no new domain logic.
   - Batch all applies for `scope="all"` inside one `with uow:` block.
4. Redirect:
   - `then="recheck"` → `url_for("targets.check_targets", ...)` (re-renders with fresh
     feasibility — identical to what `save_all` already does at `targets.py:508`).
   - `then="run"` → start the selection the same way the Run button does
     (`start_db_selection` / `start_db_select_task`). Simplest is to apply+save here, flash
     success, then hand off to the selection run; confirm during impl whether to call
     `start_db_select_task` directly in this handler or redirect into the existing POST.

Guard with the same decorators/patterns as neighbouring routes (`@login_required`,
`get_assembly_with_permissions`, CSRF via the project's form pattern). Match the existing
`try/except NotFoundError/InsufficientPermissions/Exception` + `flash` structure in
`check_targets`.

### 2. Templates

In `backend/templates/backoffice/targets/category_block.html`:
- Value-level suggestion (line ~182): after `{{ ann.message }}`, render an **Accept**
  button inside a small `<form method="post">` posting `scope=one`, `category_id`
  (`category.id`), `value_id` (`val.value_id`), `field` (`ann.field`), `then=recheck`, and
  the CSRF token. Use the design-system `button` macro (`variant="tertiary"`), matching the
  replacement modal's Accept styling (`db_replacement_modal.html:97`).
- Category-level suggestions (line ~89): same treatment where a `suggested_value` exists.

In `backend/templates/backoffice/assembly_targets.html` (near where `check_result` is
consumed): when `check_result` has any suggestion annotations, render **Accept all
suggestions** (`scope=all, then=recheck`) and **Accept all & re-run selection**
(`scope=all, then=run`) as two POST forms. Only show them when at least one suggestion
exists.

No new JS needed (server-side POST). This is the deliberate divergence from
`replacement-suggestions.js`, which only works because the replacement modal has live
inputs in an open form.

### 3. i18n

New strings (`_("Accept")`, `_("Accept all suggestions")`,
`_("Accept all & re-run selection")`) go through the existing `gettext`/`_()` path. Run the
project's message-extraction step so `messages.po` picks them up (follow the repo's
existing translation workflow; do not hand-edit catalogues).

## Files to modify

- `backend/src/opendlp/entrypoints/blueprints/targets.py` — new `accept_suggestions` route.
- `backend/templates/backoffice/targets/category_block.html` — per-suggestion Accept forms.
- `backend/templates/backoffice/assembly_targets.html` — page-level Accept-all / re-run forms.
- (Reused, not modified) `target_service.update_target_value`,
  `target_checking.check_targets_detailed`, `db_selection_backoffice.start_db_selection`.

## Tests

- **Component** (`backend/tests/component/test_targets_pages.py`): posting to
  `accept-suggestions` with `scope=one` applies the suggested min/max to the right value and
  redirects to the re-check; `scope=all` applies every suggestion; `then=run` starts a
  selection. Assert the value's stored min/max and `minmax_manual=True` afterwards.
- **Unit** (`backend/tests/unit/test_target_checking.py` or `test_target_service.py`):
  confirm the apply-one-suggestion helper overrides only the targeted field and leaves the
  other bound. Mirror how `test_replacement_targets.py` covers accept logic.
- Render check: after accepting, `check_targets` shows no remaining suggestion for the
  accepted value (feasibility improved) — assert via the component test's response HTML.

## Verification (end-to-end)

1. In the worktree: `npm ci` + generated_version.txt if fresh, then `just run`.
2. Open an assembly whose targets are infeasible, go to the targets page, hit **Check** so
   suggestions appear.
3. Click a single **Accept** → value's min/max updates, page re-checks, that suggestion is
   gone.
4. Re-introduce infeasibility, click **Accept all suggestions** → all applied, re-checked.
5. Click **Accept all & re-run selection** → targets saved and a selection run starts
   (progress modal opens on the selection page).
6. Run `just test` (or the targeted pytest files above); BDD auth failures are pre-existing.
