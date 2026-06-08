# Registration Page — Deltas to Reconcile Between the Two Plans

**Date:** 2026-05-14 (decisions recorded 2026-05-15)
**Updated:** 2026-05-22 for Q17 (DRAFT→TEST, preview token retired)
**Plans compared:** `plan-data-service.md` (domain/adapters/service layer) and `plan-frontend.md` (backoffice presentation layer)

This note lists the divergences between the two plans. Most exist because `plan-frontend.md` was written without sight of the resolved Q&A in `plan-data-service.md`. As of 2026-05-15 every delta below has a decision recorded — `plan-data-service.md` has been updated to match, and `plan-frontend.md` still needs to absorb the implications listed under each section.

> **Q17 (2026-05-20):** The preview token was retired. Section §3 below is now obsolete. A TEST page is publicly loadable at its slug with no token.

## Already resolved

**URL structure** — `plan-data-service.md` has been updated to match `plan-frontend.md`: canonical long form at `/register/<url_slug>`, short form at `/r/<short_url_slug>`. One open clarification carried over: the short→long redirect is a **302** (temporary), not 301 — a short slug may be cleared and reused by a different assembly later, and a cached permanent redirect would misroute. `plan-frontend.md` should state 302 wherever it describes the short-URL redirect.

---

## Meaty topics

### 1. Templating model & field placeholders (was comparison item #4) — DECIDED

This was the biggest gap. `plan-frontend.md` had effectively pre-decided the templating model, in a direction that was **neither** of the two options `plan-data-service.md` put to the team (Q15), and that conflicted with the codebase and with prior discussion.

**What `plan-frontend.md` assumed:**

- A **fixed list of flat per-field placeholders**: `{{ first_name }}`, `{{ last_name }}`, `{{ email }}`, `{{ phone }}`, `{{ address_line_1 }}`, `{{ address_line_2 }}`, `{{ city }}`, `{{ postcode }}`, `{{ opt_in_email }}`, etc.
- Each placeholder expanded to a complete widget — including `{{ target_age_range }}` expanding to "select, radio, or checkbox group" as a single unit.
- Demographic fields sourced from the assembly's **target categories**.

**Why this conflicted:**

- **It pre-decided the open Q15.** `plan-data-service.md` had Q15 (Option A: system-generated starter form, minimal substitution; Option C: Jinja sandbox with per-field attributes + loops) explicitly pending team discussion. The frontend model was a third thing — flat per-field whole-widget substitution.
- **It removed author control over option markup.** Prior discussion established that authors will need loops to control individual radio/select option markup. Expanding `{{ target_age_range }}` to a whole widget gives the author zero control over per-option HTML.
- **Field names can't be hardcoded.** The domain has no fixed `first_name`/`postcode`. `RespondentFieldDefinition` is a **per-assembly schema** with arbitrary `field_key`s. Any personal-field placeholder list has to be schema-driven, not static.
- **Wrong source of truth for fields.** `plan-frontend.md` drew demographic fields from `TargetCategory` (selection quotas). `plan-data-service.md` and the codebase's `respondent_field_schema` treat `RespondentFieldDefinition` as the canonical field catalogue. They are different concepts and only one can feed the registration form.

**Decision:** Q15 Option A is the chosen path.

- At render time the **only** substitutions are `{{ csrf_form_element }}` and `{{ form_action }}` (form-action placeholder name decided in §4 below).
- The system generates a plain HTML form from `domain/respondent_field_schema.py` (the assembly's `RespondentFieldDefinition` set, including `ChoiceOption` lists for choice fields). That generated HTML can be fed to an LLM to add styling and then pasted back into the textarea.
- A new service/domain function generates this starter HTML on demand (separate generator function, NOT auto-seeded at create time). The UI calls it explicitly — typically via a "Generate starter HTML" button — and shows the result for the author to copy / paste / edit.
- The canonical example is `610-registration-page-html/example-form-a-raw-html.html`.
- `plan-frontend.md`'s "Template Placeholders Reference" card (Cards 4 & 5) and the frontend's static field-placeholder list both fall away as a consequence.

### 2. Service-layer interface (was comparison item #5) — DECIDED

`plan-frontend.md`'s "Expected service layer interface" diverged from `plan-data-service.md` §5.1 on every signature.

**Decision:** go with the `plan-data-service.md` shape on every row — `user_id` + `assembly_id` keying, explicit `create_registration_page` per Q11, publish/unpublish split with `RegistrationPageNotReady` as a real error path, child-table HTML save — **with one change**: the thank-you HTML gets its **own** function, `update_thank_you_html(uow, user_id, assembly_id, thank_you_html)`, rather than being folded into `update_registration_page(..., thank_you_html=)`. `plan-data-service.md` §5.1 and §5.6 have been updated to match.

| Concern        | `plan-frontend.md`                                                | Decided (`plan-data-service.md` §5.1)                                                                                                              |
| -------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Permission arg | no `user_id` on any function                                      | `user_id` threaded through every management function                                                                                               |
| Create         | `create_or_update_registration_page(...)`                         | explicit `create_registration_page(...)` that raises if one already exists (Q11)                                                                   |
| Publish        | `toggle_registration_publish(...) -> bool`                        | separate `publish_registration_page` / `unpublish_registration_page`; `publish` raises `RegistrationPageNotReady` with the problem list            |
| Keying         | some functions keyed by `registration_page_id`                    | everything keyed by `assembly_id` (consistent with `assembly_service`)                                                                             |
| HTML save      | `save_registration_html(uow, registration_page_id, html_content)` | `update_registration_page_html(uow, user_id, assembly_id, form_html)` — operates on the child `RegistrationPageHtml`                               |
| Thank-you save | separate `save_thank_you_html(...)`                               | separate `update_thank_you_html(uow, user_id, assembly_id, thank_you_html)` — **frontend's separate-method idea adopted, renamed for consistency** |

**Frontend impact:** the **single combined Save button** still needs adjusting. With explicit `create` that raises if-exists, the route has to `get` first and branch create-vs-update; with publish/unpublish split plus `RegistrationPageNotReady`, the toggle needs an error path; and with slugs / thank-you / form-HTML now updated by three separate functions, the route fans one Save out to several service calls. All doable in the route layer — `plan-frontend.md` should reflect it.

---

## Other divergences — frontend plan to update

### 3. ~~Preview query parameter name~~ — OBSOLETE (Q17)

> **Q17 (2026-05-20):** The preview token was retired. This section is obsolete. A TEST page is publicly loadable at its slug with no token. There is no `?token=` or `?preview=` URL form.

~~`plan-frontend.md`: `/register/slug?token=abc123`. `plan-data-service.md` + story-notes line 110: `?preview=<token>`.~~

~~**Decision:** use `?token=<preview_token>`. `plan-data-service.md` updated to match.~~

### 4. Form-action placeholder name — DECIDED

`plan-frontend.md`: `{{ form_action }}`. `plan-data-service.md` + story-notes line 17: `{{ form_url }}`. Trivial, but it's a published author-facing contract.

**Decision:** use `{{ form_action }}` (it reads better since it lands in `action=`). `plan-data-service.md` and `example-form-a-raw-html.html` updated to match.

### 5. Feature flag missing — DECIDED

Story-notes line 52: "an early version behind a feature flag." `plan-data-service.md` §7 gates the tab and public routes behind `FF_REGISTRATION_PAGE`. `plan-frontend.md` doesn't mention a flag — it adds the tab unconditionally ("always enabled").

**Decision:** use the feature flag. `plan-data-service.md` already reflects this; `plan-frontend.md` needs to flag-gate the tab and the routes.

### 6. Permissions too broad — OPEN

`plan-frontend.md`: all routes behind `@require_assembly_management`. `plan-data-service.md` §6 / Q10: read-only assembly members should **see** the registration tab (read-only), only management can write. A blanket management gate excludes read-only members.

**Decision:** keep this question open and revisit as we learn from what we build. `plan-data-service.md` §6 / Q10 stays as written (read-only members can view); the frontend can choose to gate more tightly initially and we relax once we have a clearer picture.

> **Note (Q17):** With preview tokens retired, read-only view is simpler — no sensitive token to hide. The form URL is always visible (TEST pages load publicly).

### 7. Thank-you page placeholders — DECIDED

`plan-frontend.md` wants `{{ first_name }}` / `{{ email }}` / `{{ assembly_title }}` substituted into the thank-you page now. `plan-data-service.md` §5.3 returns `thank_you_html` verbatim in v1 and defers all thank-you substitution to the form-submission story.

**Decision:** no placeholders in the thank-you page for this round (revisit later). The system seeds a default `<h1>` title and `<p>` body so authors have something to edit. `plan-data-service.md` updated to define the default constant and seed it at create time.

### 8. Explicit create (Q11) — DECIDED

`plan-frontend.md`'s flow shows the full form immediately and "saving" creates the row — no deliberate create step. Q11 resolved as **explicit create** ("should not just auto-generate", because a future HTML-vs-template choice plugs in here).

**Decision:** showing the form does NOT auto-create the database row. The user must click Save (or the explicit "Create" action) to create it. `plan-data-service.md` already reflects this in §5.1; `plan-frontend.md` needs an explicit create step in the UI flow.

### 9. Frozen slugs while published (Q6) vs combined Save — DECIDED

Q6 resolved: slugs are frozen while `is_published=True`; `update_registration_page` raises `ValueError` on a slug change. `plan-frontend.md` is one cohesive form with always-editable slug inputs and one Save — if the page is published and the user edits a slug, the service raises and the **entire** combined save fails.

**Decision:** slugs stay frozen while published (no change to the service-layer rule). The frontend needs to disable slug inputs when published, or split the save. `plan-data-service.md` is unchanged.

### 10. `html_content` flat access vs child object — DECIDED

`plan-frontend.md` templates assume `registration_page.html_content`. `plan-data-service.md` puts `form_html` on the child `RegistrationPageHtml`; the route hands the template `(page, source)` and the textarea binds to `source.form_html`.

**Decision:** go with the `plan-data-service.md` version — the field is `form_html` on the child `RegistrationPageHtml`. `plan-frontend.md` needs to update the template binding accordingly.

---

## Minor / cosmetic

### 11. Branch name & feature name — DECIDED

`plan-frontend.md` header says branch `610-rsvp-page-backoffice`; the actual branch is `610-registration-page-html`. The title also says "RSVP Page" while story, codebase, and `plan-data-service.md` say "Registration" throughout.

**Decision:** branch is `610-registration-page-html` and the feature is "Registration" everywhere. `plan-frontend.md` needs the header / title fix.

### 12. Slug validation errors in the UI — DECIDED

`plan-data-service.md` raises `ValueError` for taken / reserved / malformed slugs. `plan-frontend.md` Step 8 mentions "handle validation errors" generally but doesn't enumerate slug errors — worth a line so the UI surfaces them on the right field.

**Decision:** service-layer exceptions for slug problems must carry enough information for the UI to attribute the error to the correct field (which slug, which kind of failure). `plan-data-service.md` §5.1 updated with a note on this; the precise mechanism (distinct exception types vs. an attribute on the raised error) can be picked during implementation.

### 13. `qrcode` dependency — DECIDED

`plan-frontend.md` says "may need to add `qrcode`". It's already a dependency (TOTP uses it).

**Decision:** use the existing `qrcode` dependency — no add needed. `plan-frontend.md` can drop the "may need to add" line.
