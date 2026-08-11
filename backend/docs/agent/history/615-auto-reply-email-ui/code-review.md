# Code Review — `615-auto-reply-email-ui`

The branch mixes two pieces of work in the merge-base diff — **615** (auto-reply email UI, stepper macro, multi-step registration editor) and **617** (log redaction / structured logging), which was independently merged to `main` via PR #188. If you rebase before opening the 615 PR, the 617 noise will drop out. Overall quality is high; nothing blocks. The main "should-fix" clusters are (1) leftover f-string logging + `.error()`-instead-of-`.exception()` in the touched blueprints, (2) a few over-mocked component tests, (3) missing doc updates for the new production check and the new use of `SECRET_KEY` as an HMAC key, and (4) a latent HTML-escape footgun in the new stepper macro.

## Code Quality Rules

**Should-fix**
- `src/opendlp/entrypoints/decorators.py:75-77, 122, 135-136, 203-205` — 4 log calls still use f-strings after the structlog conversion. Convert to structured kwargs (`user_id=str(current_user.id)`, `endpoint=request.endpoint`, `role=...`).
- Catch-all `except Exception as e: logger.error(...)` in code the branch touched — should be `.exception(...)`:
  - `gsheets_legacy.py` ~21 spots; `admin.py` ~14; `main.py` ~7. `backoffice_registration.py:504` already does it right.
- `backoffice_registration.py:344-346, 352-354` — silent `except (EmailTemplateNotFoundError, InsufficientPermissions): email_template = None`. Add a `logger.debug(...)` so "no template assigned" vs "permission denied at load time" is distinguishable.

**Nits**
- `log_redaction.py:92` — `secret: str | None = None` violates the "prefer empty string default" preference, but the sentinel is legitimate here for DI.
- `logging.py` — missing ABOUTME header (pre-existed on main; opportunistic fix).

## Testing

**Should-fix**
- `tests/component/test_backoffice_registration_email.py:238-312` — over-mocks `update_email_template` / `create_email_template` to raise, which `docs/testing.md:539-544` explicitly forbids. `EmailTemplateInvalid` is reachable via the empty-strings pattern already used in `test_dev_email_handlers.py:173`; `NotFoundError` via a stray UUID. Drop the mocks.
- `test_backoffice_registration_email.py:285-296` — assertion is a tautology (`"…" not in loc or "…" not in loc`). Assert on the concrete destination.
- `tests/component/test_dev_email_handlers.py:95-124` — reinvents fixtures instead of reusing `tests/component/conftest.py` (`fake_store` / `existing_assembly` / `admin_user`). Consolidate.
- **BDD gap.** No `features/` or `tests/bdd/` scenario for the new multi-step editor / auto-reply UI. Given this is a substantial user-facing journey, at least a happy-path scenario is warranted. The e2e test drives HTTP, not the browser.
- `tests/unit/test_stepper_macro.py:38-45` — `"completed" in html` / `"has errors" in html` matches almost any incidental copy. Anchor on the actual `<span class="sr-only">` or parse the HTML.

**Nits**
- `tests/e2e/test_health_check_monitoring.py` — collapsing per-URL loops loses coverage of the `/health` aggregate wiring.
- `capture_json_handler` fixture in `tests/conftest.py:429-455` is a nice pattern — replaces the wrong-tool `caplog` assertions for structlog output.

## Architecture

**Should-fix**
- `log_redaction.py:99` — module-load import of `opendlp.config`. `logging.py` imports `log_redaction` at load and is one of the earliest imports in `flask_app.py`. Fine today, but any future logging in `config.py` would cycle. Consider taking the secret at the call site (`login_rate_limit_service.py:70` already knows the config) so `log_redaction.py` becomes a pure helper.
- `backoffice_registration.py:325-467` — auto-reply "prefer assigned else first template" fallback (`_load_auto_reply_context`) and the enable-vs-assign dispatch (`_dispatch_email_action`) are business rules that belong in `email_template_service`, not the blueprint. Same file opens 24 separate short UoW transactions per request — push multi-step reads into one service call.

**Nits**
- `_create_default_auto_reply_template` (`backoffice_registration.py:514-538`) is a side-effect of creating a registration page; belongs in `registration_page_service.create_registration_page_with_slugs` or `email_template_service.seed_default_auto_reply`.
- `config.py:579-580` production check is good; consider a matching runtime guard in `bootstrap.py` where the adapter is constructed.
- `gsheets_legacy.py` +570 lines confirmed to be pure logging/kwargs conversion, no logic drift.

## Configuration

- **Env vars added:** none. **Env vars removed:** none.

**Should-fix**
- `docs/configuration.md` not updated for the new production check that rejects `EMAIL_ADAPTER=console` (config.py:578-580). Same gap in `env.example:139-143`.
- `SECRET_KEY` is now also the HMAC key for `hash_email` (log_redaction.py:92-102). Rotating it invalidates log-correlation tokens — worth documenting under `SECRET_KEY` (docs/configuration.md:55-60) and under "Rotate secrets regularly" (line 413).

**Nits**
- `"dev-secret-key-change-in-production"` is hardcoded at both config.py:49-51 and config.py:571 — extract a constant so the production guard can't silently drift.

## Templates & Accessibility

The stepper's ARIA/keyboard/SR contract is correct: roving tabindex via `tabsKeyboard`, `role="tab"`+`aria-selected`+`aria-controls` in tabs mode, `aria-current="step"` in wizard mode, panels wired with matching ids + `aria-labelledby`, and done/error state announced via `sr-only` suffixes ("completed" / "has errors"). i18n is essentially complete in the new files.

**Should-fix**
- `stepper.html:63-68` — the extra-attrs pass-through builds `key="value"` strings and applies `|safe`. No `|e` on `value`. Latent XSS/attribute-break footgun if any caller ever passes a value containing `"` (including a translated string). Escape each value or use `|forceescape` before `|safe`.
- `service_docs/_emails.html` heading hierarchy jumps h2 → h4 throughout. The `card()` macro emits h2, then interior labels are h4 with no intervening h3.
- `assembly_registration.html:52` — page h1 (line 29) is followed by h3 in the "no registration page" panel. Bump to h2.
- `assembly_registration.html:432-448` — variable-copy row: `<label for="variable-N">` on a `readonly` input will invite "edit text" hints in SR. Consider `<code>` + button, or add `aria-readonly="true"`.

**Nits**
- `stepper.html:83, 112` — bare `!` for error state relies on colour + text. A warning-triangle SVG (matching the checkmark) would help WCAG 1.4.1.
- `stepper.html:48-52` — `aria-label` on both the outer `<nav>` and inner `<ol role="tablist">` is redundant.
- `assembly_registration.html:232, 242, 253` — `"Details for" + image.display_name` isn't translator-reorderable. Use `%(name)s` server-side.

## JavaScript & CSP

All inline scripts carry `nonce="{{ csp_nonce }}"`, CSP-safe `@alpinejs/csp@3.15.8` build is in use, JS logic lives in `static/backoffice/js/alpine-components.js`, AJAX includes `X-CSRFToken`. No `eval` / `new Function` / unsafe `.innerHTML`.

**Should-fix**
- `stepper.html:48` uses `x-scroll-preserve-links` (registered in `static/js/alpine-scroll-manager.js`, loaded by `backoffice/base.html:29`). If the stepper is used outside backoffice base, it silently no-ops. Document the dependency in the macro docstring.
- `assembly_registration.html:440` accretes another `@click="copyToClipboard('lit1', 'lit2')"` (CLAUDE.md flags "`@click` handlers cannot have string arguments"). The CSP Alpine build accepts literals in practice — the pattern already exists on main — but if the constraint is meant strictly, prefer `data-copy-*` attributes + `copyToClipboard($el)`.

**Nits**
- Big inline `registrationPageController` script (`assembly_registration.html:895-1180`, ~285 lines) — justifiable due to Jinja interpolation, but pushing to `Alpine.data(...)` with values via `data-*` attributes would match `frontend_security.md`'s "prefer external files".
- `service_docs/_emails.html`, `showcase/stepper_component.html`, `patterns/_stepper.html` add many `style="color: var(--color-...)"` inline attributes. Static tokens — could be utility classes. Not a CSP issue, aesthetic.
