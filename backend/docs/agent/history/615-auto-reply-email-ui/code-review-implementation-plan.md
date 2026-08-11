# Incremental Implementation Plan

Ordered by risk + coupling: quick low-risk fixes first, then docs, then tests, then refactors that need thinking. Each step should be one commit (or a couple of tight ones), reviewable in isolation.

## Step 0 — Rebase onto `main`

Drops the 617 noise from the diff. Do this before anything else so the PR shape reflects only 615 work.

```bash
git fetch origin main
git rebase origin/main
```

Verify: `git diff --merge-base main --stat` should shrink dramatically. Run tests.

## Step 1 — Security footgun: escape stepper attributes

Highest-impact, tiniest change. In `templates/backoffice/components/stepper.html:63-68`, escape each value before `|safe`. Either:
- `{% set _ = extra_attrs.append(key ~ '="' ~ (value | e) ~ '"') %}`
- Or drop `|safe` and use `|forceescape` on the joined string.

Add a `test_stepper_macro` case that passes a value containing `"` and asserts the output stays inside the attribute.

## Step 2 — Silent except → debug log

`backoffice_registration.py:344-346, 352-354`: add `logger.debug("auto_reply_template_load_failed", assembly_id=..., reason="not_found"|"forbidden")` in the two except arms. One-file change.

## Step 3 — Logging convention cleanup (mechanical)

Sweep in a single commit — pure refactor, no behaviour change:
- `entrypoints/decorators.py:75, 122, 135, 203` — f-strings → structured kwargs.
- `gsheets_legacy.py`, `admin.py`, `main.py` — `logger.error(...)` inside catch-all `except Exception` → `logger.exception(...)` (drop the redundant `error=str(e)` where the traceback now carries it).

Verify: `grep -n 'logger\.error' src/opendlp/entrypoints/blueprints/{gsheets_legacy,admin,main}.py` after the sweep, cross-check each remaining one is *not* in a catch-all.

## Step 4 — Config documentation

Two-file change, no code:
- `docs/configuration.md` — extend "Configuration Validation" with the console-adapter rejection; extend `SECRET_KEY` section with the HMAC-key usage + rotation implication.
- `env.example:139-143` — one-line comment: "production startup fails if this is `console`".

## Step 5 — Extract dev-secret constant

`config.py:49-51` and `571` both hardcode `"dev-secret-key-change-in-production"`. Pull to a module-level `_DEV_SECRET_KEY = "..."` so the production guard can't silently drift. Trivial.

## Step 6 — Test cleanup

Split into three commits if you want them reviewable:
1. `test_backoffice_registration_email.py:238-312` — remove `update_email_template`/`create_email_template` mocks, drive `EmailTemplateInvalid` with empty strings, `NotFoundError` with a stray UUID. Drop the `RuntimeError` case.
2. `test_backoffice_registration_email.py:285-296` — replace the tautological assert with a concrete-destination check.
3. `test_dev_email_handlers.py:95-124` — swap the local fixtures for `tests/component/conftest.py`'s (`fake_store`, `existing_assembly`, `admin_user`). Move the `patch(current_user)` calls to `session_transaction` login.
4. `test_stepper_macro.py:38-45` — anchor assertions on `<span class="sr-only">` (or parse the HTML with `BeautifulSoup` — already a project dep).

## Step 7 — Accessibility fixes (template-only)

- `stepper.html:83, 112` — swap the bare `!` for a warning-triangle SVG (mirror the checkmark).
- `stepper.html:48-52` — drop the outer `<nav aria-label>`, keep it only on `<ol role="tablist">`.
- `stepper.html` docstring — add a "Dependencies: requires `x-scroll-preserve-links` from `backoffice/base.html` if `preserve_scroll=true`" note.
- `service_docs/_emails.html` — bump interior h4s to h3.
- `assembly_registration.html:52` — h3 → h2.
- `assembly_registration.html:432-448` — variable-copy row: add `aria-readonly="true"` to the input (or restructure to `<code>` + button).
- `assembly_registration.html:232, 242, 253` — `_("Details for %(name)s", name=image.display_name)` etc., built server-side.

Manually verify with a screen reader (VoiceOver) — or at least keyboard tab through the stepper.

## Step 8 — Alpine `@click` string-arg pattern

`assembly_registration.html:440` — switch to `data-copy-expr="{{ variable.expr }}" data-copy-msg="{{ _('...') }}" @click="copyToClipboard($el)"`. Update `copyToClipboard` in `alpine-components.js` to read from `$el.dataset` when passed a DOM element. Grep for other call sites and migrate them together — this is a mini-refactor across the file.

## Step 9 — Business logic → service layer

Bigger, riskier. Do this after everything above is green.

- Move `_load_auto_reply_context` fallback logic into `email_template_service.get_editor_context_for_assembly(uow, user_id, assembly_id)` returning a dataclass with `template`, `all_templates`, `assigned_id`.
- Move `_dispatch_email_action` enable-vs-assign rule into `email_template_service.enable_auto_reply(uow, assembly_id, template_id | None)`.
- Move `_create_default_auto_reply_template` into either `registration_page_service.create_registration_page_with_slugs` or `email_template_service.seed_default_auto_reply`.
- Blueprint becomes thin: one `with bootstrap.get_flask_uow() as uow:` per request, service calls inside.

Add unit tests at the service layer for each rule. Trim the component tests once real service coverage exists.

## Step 10 — BDD happy path

Add a scenario for "manager creates registration page → enables auto-reply → edits template → previews → publishes" under `tests/bdd/`. Match the existing project style. Update `delete_all_except_standard_users()` in `tests/bdd/conftest.py` if the new flow creates rows that aren't already covered.

## Step 11 — Optional: log_redaction DI cleanup

`log_redaction.py` — remove the `opendlp.config` import, take `secret` as a required arg on `hash_email`. Update the two call sites (`login_rate_limit_service.py`, wherever else) to pass it. Eliminates the latent circular import.

## Step 12 — Optional: extract inline Alpine controller

`assembly_registration.html:895-1180` → move to `static/backoffice/js/registration-page-controller.js` as `Alpine.data("registrationPageController", ...)`. Pass `url_for` / translated strings / `images|tojson` via `data-*` attributes on the root `<div x-data>`.

Skip if you're happy with the inline version — the CSP nonce covers it.

---

**Ship boundary suggestion:** steps 0-7 in this PR (safe, tightly scoped), step 8 if you have appetite. Steps 9-12 as a follow-up PR — they change architecture and deserve separate review focus.
