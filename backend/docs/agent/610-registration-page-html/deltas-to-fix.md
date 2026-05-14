# Registration Page — Deltas to Reconcile Between the Two Plans

**Date:** 2026-05-14
**Plans compared:** `plan-data-service.md` (domain/adapters/service layer) and `plan-frontend.md` (backoffice presentation layer)

This note lists the divergences between the two plans. Most exist because `plan-frontend.md` was written without sight of the resolved Q&A in `plan-data-service.md` — so the bulk of these are "frontend plan needs to move", but the two **meaty topics** at the top are genuine design discussions that need both authors.

## Already resolved

**URL structure** — `plan-data-service.md` has been updated to match `plan-frontend.md`: canonical long form at `/register/<url_slug>`, short form at `/r/<short_url_slug>`. One open clarification carried over: the short→long redirect is a **302** (temporary), not 301 — a short slug may be cleared and reused by a different assembly later, and a cached permanent redirect would misroute. `plan-frontend.md` should state 302 wherever it describes the short-URL redirect.

---

## Meaty topics — need both authors

### 1. Templating model & field placeholders (was comparison item #4)

This is the biggest gap. `plan-frontend.md` has effectively pre-decided the templating model, and in a direction that is **neither** of the two options `plan-data-service.md` put to the team (Q15), and that conflicts with the codebase and with prior discussion.

**What `plan-frontend.md` assumes:**
- A **fixed list of flat per-field placeholders**: `{{ first_name }}`, `{{ last_name }}`, `{{ email }}`, `{{ phone }}`, `{{ address_line_1 }}`, `{{ address_line_2 }}`, `{{ city }}`, `{{ postcode }}`, `{{ opt_in_email }}`, etc.
- Each placeholder expands to a complete widget — including `{{ target_age_range }}` expanding to "select, radio, or checkbox group" as a single unit.
- Demographic fields sourced from the assembly's **target categories**.

**Why this conflicts:**
- **It pre-empts the open Q15.** `plan-data-service.md` has Q15 (Option A: system-generated starter form, minimal substitution; Option C: Jinja sandbox with per-field attributes + loops) explicitly pending team discussion. The frontend model is a third thing — flat per-field whole-widget substitution.
- **It removes author control over option markup.** Prior discussion established that authors will need loops to control individual radio/select option markup. Expanding `{{ target_age_range }}` to a whole widget gives the author zero control over per-option HTML.
- **Field names can't be hardcoded.** The domain has no fixed `first_name`/`postcode`. `RespondentFieldDefinition` is a **per-assembly schema** with arbitrary `field_key`s. Any personal-field placeholder list has to be schema-driven, not static.
- **Wrong source of truth for fields.** `plan-frontend.md` draws demographic fields from `TargetCategory` (selection quotas). `plan-data-service.md` and the codebase's `respondent_field_schema` treat `RespondentFieldDefinition` as the canonical field catalogue. Which one feeds the registration form needs settling — they are different concepts.

**To resolve:** decide Q15 first (Option A vs C), then `plan-frontend.md`'s "Template Placeholders Reference" card (Cards 4 & 5) is largely rewritten to match. The placeholder reference UI also has to become schema-driven (rendered from the assembly's `RespondentFieldDefinition` set) rather than a static table.

### 2. Service-layer interface (was comparison item #5) — DECIDED

`plan-frontend.md`'s "Expected service layer interface" diverged from `plan-data-service.md` §5.1 on every signature.

**Decision:** go with the `plan-data-service.md` shape on every row — `user_id` + `assembly_id` keying, explicit `create_registration_page` per Q11, publish/unpublish split with `RegistrationPageNotReady` as a real error path, child-table HTML save — **with one change**: the thank-you HTML gets its **own** function, `update_thank_you_html(uow, user_id, assembly_id, thank_you_html)`, rather than being folded into `update_registration_page(..., thank_you_html=)`. `plan-data-service.md` §5.1 and §5.6 have been updated to match.

| Concern | `plan-frontend.md` | Decided (`plan-data-service.md` §5.1) |
|---|---|---|
| Permission arg | no `user_id` on any function | `user_id` threaded through every management function |
| Create | `create_or_update_registration_page(...)` | explicit `create_registration_page(...)` that raises if one already exists (Q11) |
| Publish | `toggle_registration_publish(...) -> bool` | separate `publish_registration_page` / `unpublish_registration_page`; `publish` raises `RegistrationPageNotReady` with the problem list |
| Keying | some functions keyed by `registration_page_id` | everything keyed by `assembly_id` (consistent with `assembly_service`) |
| HTML save | `save_registration_html(uow, registration_page_id, html_content)` | `update_registration_page_html(uow, user_id, assembly_id, form_html)` — operates on the child `RegistrationPageHtml` |
| Thank-you save | separate `save_thank_you_html(...)` | separate `update_thank_you_html(uow, user_id, assembly_id, thank_you_html)` — **frontend's separate-method idea adopted, renamed for consistency** |

**Frontend impact:** the **single combined Save button** still needs adjusting. With explicit `create` that raises if-exists, the route has to `get` first and branch create-vs-update; with publish/unpublish split plus `RegistrationPageNotReady`, the toggle needs an error path; and with slugs / thank-you / form-HTML now updated by three separate functions, the route fans one Save out to several service calls. All doable in the route layer — `plan-frontend.md` should reflect it.

---

## Other divergences — frontend plan to update

### 3. Preview query parameter name
`plan-frontend.md`: `/register/slug?token=abc123`. `plan-data-service.md` + story-notes line 110: `?preview=<token>`. Pick `preview`.

### 4. Form-action placeholder name
`plan-frontend.md`: `{{ form_action }}`. `plan-data-service.md` + story-notes line 17: `{{ form_url }}`. Trivial, but it's a published author-facing contract — pick one. (`form_action` arguably reads better since it lands in `action=`; `form_url` is what the story and our plan currently say.)

### 5. Feature flag missing
Story-notes line 52: "an early version behind a feature flag." `plan-data-service.md` §7 gates the tab and public routes behind `FF_REGISTRATION_PAGE`. `plan-frontend.md` doesn't mention a flag — it adds the tab unconditionally ("always enabled"). The tab and routes need to be flag-gated.

### 6. Permissions too broad
`plan-frontend.md`: all routes behind `@require_assembly_management`. `plan-data-service.md` §6 / Q10: read-only assembly members should **see** the registration tab (read-only), only management can write. A blanket management gate excludes read-only members.

### 7. Thank-you page placeholders
`plan-frontend.md` wants `{{ first_name }}` / `{{ email }}` / `{{ assembly_title }}` substituted into the thank-you page now. `plan-data-service.md` §5.3 returns `thank_you_html` verbatim in v1 and defers all thank-you substitution to the form-submission story. Either pull that scope forward (and agree the context) or drop the thank-you placeholders from the frontend plan for now.

### 8. Explicit create (Q11)
`plan-frontend.md`'s flow shows the full form immediately and "saving" creates the row — no deliberate create step. Q11 resolved as **explicit create** ("should not just auto-generate", because a future HTML-vs-template choice plugs in here). The frontend flow needs an explicit "Create registration page" action for an assembly that doesn't have one yet (Step 8 hints at this but the UI doesn't show it).

### 9. Frozen slugs while published (Q6) vs combined Save
Q6 resolved: slugs are frozen while `is_published=True`; `update_registration_page` raises `ValueError` on a slug change. `plan-frontend.md` is one cohesive form with always-editable slug inputs and one Save — if the page is published and the user edits a slug, the service raises and the **entire** combined save fails. The UI needs to disable the slug inputs when published (or split the save).

### 10. `html_content` flat access vs child object
`plan-frontend.md` templates assume `registration_page.html_content`. `plan-data-service.md` puts `form_html` on the child `RegistrationPageHtml`; the route hands the template `(page, source)` and the textarea binds to `source.form_html`. Field name (`html_content` vs `form_html`) and access path both need aligning.

---

## Minor / cosmetic

### 11. Branch name & feature name
`plan-frontend.md` header says branch `610-rsvp-page-backoffice`; the actual branch is `610-registration-page-html`. The title also says "RSVP Page" while story, codebase, and `plan-data-service.md` say "Registration" throughout. Pick one name and use it consistently.

### 12. Slug validation errors in the UI
`plan-data-service.md` raises `ValueError` for taken / reserved / malformed slugs. `plan-frontend.md` Step 8 mentions "handle validation errors" generally but doesn't enumerate slug errors — worth a line so the UI surfaces them on the right field.

### 13. `qrcode` dependency
`plan-frontend.md` says "may need to add `qrcode`". It's already a dependency (TOTP uses it) — no add needed.
