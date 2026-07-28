# Code Review Findings — branch `800-email-fixes`

- **Date:** 2026-07-28
- **Diff reviewed:** `git diff main...HEAD` (24 changed files), after the branch was rebased onto `main` (post PR #213 / 768 PDF uploads)
- **Method:** high-effort multi-agent review — 4 finder angles (3 correctness + 1 cleanup) produced 23 candidates; every distinct location was independently verified (22 confirmed, 1 refuted); duplicates merged into 15 distinct defects; the top 10 were reported.

## Executive summary

The most serious cluster comes from the branch's **"auto-reply is always on" product change shipping without a migration for legacy pages**. Three findings (1, 2, 3) share that root cause and should be resolved together, starting with a product decision:

> **Product decision (2026-07-28):** the enable/disable toggle never shipped to production, so no deliberate OFF choice exists to honor. Auto-reply is unconditionally always-on: an irreversible data migration (`3d7f07de5b72`) backfills the template assignment for any page left unassigned, the dummy checked+disabled checkbox stays, and all remaining toggle-era functionality (self-heal, `templates[0]` fallback, posted `template_id` handling) is removed. Legacy `enable`/`disable` actions are rejected outright.

The remaining confirmed issues are more contained: legacy toggle POSTs falling into the save handler, an ARIA regression on the disabled stepper, preview-iframe links navigating into frame-blocked pages, and an unterminated `<div>` on the dev patterns page.

## Todo checklist

Ranked by severity; items 1–3 share one root cause and one fix design.

- [x] **0. Decide the legacy auto-reply migration strategy** — decided: always-on, backfill migration, no OFF state to honor (toggle never reached production)
- [x] 1. Backfill migration `3d7f07de5b72` assigns each assembly's oldest template to its unassigned page, making the always-checked checkbox truthful
- [x] 2. Save now ignores the posted `template_id` entirely and operates only on the page's assigned template — the cross-assembly overwrite path no longer exists
- [x] 3. Self-heal re-assignment and the `templates[0]` fallback removed from the save path
- [x] 4. `_dispatch_email_action` rejects unknown/legacy actions (`enable`/`disable`) with a warning flash and no changes
- [ ] 5. Emit `aria-selected` on the active tab in the stepper's disabled span branch
- [ ] 6. Neutralise link navigation inside the form preview iframe (block anchor clicks like submits, or `sandbox` the iframe)
- [ ] 7. Fix the unterminated toast `<div>` in `patterns.html`
- [x] 8. `preview_registration_form`'s catch-all now uses `logger.exception`
- [x] 9. Shared `_create_and_assign_default_template` helper extracted (create action + page seeding both use it)
- [x] 10. `preview_registration_form` (and the email dispatch) now use `get_registration_page`, dropping the discarded HTML-source reads
- [ ] (Optional) lower-priority cleanups — see "Not reported" section

---

## Confirmed findings (reported top 10)

### 1. Auto-reply checkbox lies for legacy pages (correctness, CONFIRMED)

**Where:** `templates/backoffice/assembly_registration.html:391`

The email step renders the "Send auto-reply email" checkbox as unconditionally `checked=true, disabled=true` ("always sent in the current version of the product"), even for legacy pages whose template was never assigned (`auto_reply_email_template_id is None`). But `email_send_service.py:96` skips sending exactly in that state, and the branch ships no migration to assign legacy templates.

**Failure scenario:** A pre-deploy assembly whose organiser left the old auto-reply switch OFF (template seeded but unassigned — a state `_load_auto_reply_context`'s fallback explicitly supports) upgrades to this release. The organiser sees the checkbox checked and locked and believes auto-reply is on; real respondents register on the published form and receive nothing. The only self-heal path is someone happening to press Save.

**Fix direction:** either an Alembic data migration backfilling `auto_reply_email_template_id` for pages with exactly one seeded template (making "always on" true), or render the checkbox state from the actual assignment.

### 2. Cross-assembly template overwrite before ownership check (correctness, CONFIRMED)

**Where:** `src/opendlp/entrypoints/blueprints/backoffice_registration.py:451` (`_handle_email_action_save`)

`update_email_template` (which commits) runs on the form-posted `template_id` **before** `assign_auto_reply_template` validates that the template belongs to this assembly.

**Failure scenario:** A user managing assemblies A and B posts the email-save form for assembly A with `template_id` set to B's template (stale tab or edited hidden field). `update_email_template`'s permission check passes (they manage B), B's live subject/body are overwritten and committed with A's content, then `assign_auto_reply_template` raises `EmailTemplateNotFoundError`. The user sees "The auto-reply email could not be found" while assembly B now sends A's email text to its registrants.

**Fix direction:** verify the template's assembly membership (or fetch it scoped to `assembly_id`) before calling `update_email_template`; or make update+assign one transactional service operation.

### 3. Save silently re-enables a deliberately disabled auto-reply (correctness, CONFIRMED)

**Where:** `src/opendlp/entrypoints/blueprints/backoffice_registration.py:461` (self-heal in `_handle_email_action_save`, plus the `templates[0]` fallback in `_dispatch_email_action:489-495`)

The "self-heal" re-assigns an unassigned template on any Save. For legacy pages where the organiser used the old switch to deliberately turn auto-reply OFF, editing the wording and pressing Save re-enables outbound email to the public without warning.

**Fix direction:** depends on the item-0 decision. If backfilling, the self-heal becomes unnecessary; if honoring OFF, the self-heal must go or become an explicit user action.

### 4. Legacy enable/disable POSTs fall through to save (correctness, CONFIRMED)

**Where:** `src/opendlp/entrypoints/blueprints/backoffice_registration.py:494-496` (`_dispatch_email_action`)

Dispatch is `if action == "create": ... else save`. The removed `enable`/`disable` actions from a stale pre-deploy tab (which post only csrf/action/template_id) are treated as saves with empty subject/body. Only the domain validation in `_validate()` prevents the template being blanked; the user instead gets baffling flashes ("The email template needs a subject" / "The email template body is empty") for what used to be a toggle.

**Fix direction:** whitelist known actions and redirect unknown ones back to the email step with a neutral flash (or 400).

### 5. Disabled stepper drops `aria-selected` (correctness / accessibility, CONFIRMED)

**Where:** `templates/backoffice/components/stepper.html:87-92` (disabled span branch); reachable in tabs mode since line 71 became `disabled or (item.disabled and is_wizard)`; caller `assembly_registration.html:80-82` passes `disabled=edit_mode`

In edit mode the whole tablist renders as disabled spans without `aria-selected`, so no tab is marked selected while the visible panel's `aria-labelledby` still points at the active one. Screen-reader users cannot tell which step the visible tabpanel belongs to — a regression against the tabs ARIA pattern required by `docs/agent/component_accessibility.md`.

**Fix direction:** emit `aria-selected="true"` (and probably keep `tabindex="-1"`) on the active item in the span branch, mirroring the anchor branch at line 116.

### 6. Preview iframe links navigate into frame-blocked pages (correctness, CONFIRMED)

**Where:** `templates/register/form_preview.html:12-14`; embedding iframe at `assembly_registration.html:545-548` (no `sandbox` attribute)

The preview only neutralises `submit` events. Anchor clicks (author-HTML links, or `base_public.html` footer links like "Cookies") navigate the iframe to pages outside `SAME_ORIGIN_FRAMEABLE_ENDPOINTS`, whose `X-Frame-Options`/`frame-ancestors 'none'` (or external sites' own anti-framing headers) blank the frame. The preview looks broken until the whole backoffice page is reloaded.

**Fix direction:** capture-phase click handler that prevents default on anchors (matching the submit treatment), and/or open links in a new tab, and/or add a `sandbox` attribute to the iframe.

### 7. Unterminated toast `<div>` blanks toast text on dev patterns page (correctness, CONFIRMED)

**Where:** `templates/backoffice/patterns.html:105-109`

Line 107 ends the `:style` attribute with no closing `>` for the div opened on line 105, so `<span x-text="toast.message">` is parsed as attributes of the div; the message element never exists in the DOM. Triggering any AJAX demo on `/backoffice/dev/patterns` shows an empty colored pill — the very element this branch restyled to top-center. Dev-only page, but it's the documented reference for CSP-compatible Alpine patterns.

**Fix direction:** add the missing `>`.

### 8. `logger.error` instead of `logger.exception` in catch-all (cleanup, CONFIRMED)

**Where:** `src/opendlp/entrypoints/blueprints/backoffice_registration.py:663-664` (`preview_registration_form`)

`except Exception as e: logger.error(..., error=str(e))` violates the permanent rule in `docs/agent/code_quality_rules.md` ("Use `logger.exception` in catch-all handlers"); the same file's other new catch-all handlers (e.g. line 570) follow it. Without the traceback the operator cannot locate a production preview failure, and `str(e)` may quote author-supplied form HTML, which can carry PII.

### 9. Duplicated create-and-assign template sequence (cleanup, CONFIRMED)

**Where:** `backoffice_registration.py:424-433` (`_handle_email_action_create`) vs `:558-567` (`_create_default_auto_reply_template`)

Both contain the identical `_default_email_template_content()` → `create_email_template(...)` → `assign_auto_reply_template(...)` sequence; the diff added the assign call to the seeding helper, making them identical except for flash/error handling. The "a created template is an assigned template" invariant is enforced in two hand-synchronized places — a future change applied to one but not the other re-creates the unassigned-template legacy state this branch adds self-healing for.

**Fix direction:** extract a shared `_create_and_assign_default_template` helper.

### 10. Redundant HTML-source DB read on the preview route (cleanup, CONFIRMED)

**Where:** `backoffice_registration.py:642` (`preview_registration_form`)

`get_registration_page_with_source` is called but only `result[0]` is used; `render_registration_form` re-loads the same HTML source internally via `_load_html_source`. Every load of the preview step reads the full HTML source (potentially tens of KB) twice and throws one copy away. The lighter permission-checked `get_registration_page` (`registration_page_service.py:217`) exists for exactly this need.

---

## Confirmed but not reported (lower-severity cleanups, 5 merged-out items)

Verified as real but ranked below the reporting cut. Worth folding into future cleanup passes:

- **Hand-rolled confirm dialogs** — `assembly_registration.html:977-1013` (close-registration) and `:1018-1051` (discard-changes) duplicate each other's backdrop/positioner/panel markup and re-implement the existing `alert_dialog` macro in `templates/backoffice/components/modal.html:36`.
- **Four hand-copied sticky wizard footers** — identical `<div class="wizard-footer"> / <div class="wizard-footer-box">` wrappers at `assembly_registration.html:294, 353, 502, 626`, with the edit-mode hint string byte-identical in two of them; a macro would remove the copies.
- **Toast markup triplicated** — the positioning class string `fixed top-6 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-lg shadow-lg` plus near-identical type-conditional `:style` bindings appear in `assembly_registration.html:1062`, `patterns.html:106`, and `service_docs.html:101`.
- **Unscoped `body { overflow-x: clip }`** — `static/backoffice/src/main.css:1101-1103`, added outside any `@layer` solely to absorb the stuck wizard footer's `100vw` breakout (`margin-inline: calc(50% - 50vw)` at line 1085). Global side effect for a component-local problem (verdict: PLAUSIBLE).
- One further duplication/efficiency item merged into finding 9's root cause.

## Refuted (for the record)

- **CSP string surgery in `flask_app.py:292-295`** — the same-origin-frameable relaxation does `.replace("frame-ancestors 'none'", "frame-ancestors 'self'")` on the serialized header. The verifier confirmed the mechanism is fragile-looking but refuted the claimed failure: the byte form is produced by this codebase's own `.frame_ancestors("'none'")` policy two functions up, so the replace cannot silently no-op under current code. Style concern only; no defect.
