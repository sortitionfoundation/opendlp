# Public Registration Page Rendering - Implementation Plan

**Branch:** `610-registration-page-html`
**Date:** 2026-05-27

## Overview

Implement public-facing routes to render registration pages and handle form submissions. The domain model, service layer, and submission logic already exist - we need the Flask routes and templates.

## URL Structure

| Route | Method | Purpose |
|-------|--------|---------|
| `/register/<url_slug>` | GET | Render registration form |
| `/register/<url_slug>` | POST | Handle form submission |
| `/register/<url_slug>/thank-you` | GET | Thank-you page after submission |
| `/r/<short_url_slug>` | GET | 302 redirect to canonical URL |
| `/registration-closed` | GET | Static closed page |

## Status Behavior

| Page Status | Route Response |
|-------------|---------------|
| `TEST` | Render form with test banner, submissions → `TEST_SUBMISSION` |
| `PUBLISHED` | Render form normally, submissions → `POOL` |
| `CLOSED` | 302 redirect to `/registration-closed` |
| Not found | 404 |

## Implementation Steps

### Step 1: Create the Blueprint

**File:** `src/opendlp/entrypoints/blueprints/registration.py` (new)

```python
"""ABOUTME: Public registration page routes for assembly registration forms
ABOUTME: Handles form rendering, submission, and URL resolution without login"""

from flask import Blueprint
registration_bp = Blueprint("registration", __name__)
```

Key imports:
- `flask`: Blueprint, abort, redirect, render_template, request, url_for
- `flask_wtf.csrf`: generate_csrf
- Domain: `RenderContext` from `opendlp.domain.registration_page`
- Services: `find_registration_page_by_url_slug`, `find_registration_page_by_short_url_slug`, `resolve_visibility`, `get_page_and_source_for_render`, `render_thank_you_html` from `registration_page_service`
- Submission: `submit_registration`, `RegistrationClosedError`, `RegistrationNotFoundError` from `registration_submission_service`
- Feature flags: `has_feature` from `opendlp.feature_flags`
- Bootstrap: `bootstrap` from `opendlp`

### Step 2: Feature Flag Decorator

```python
def require_registration_feature(f):
    """Return 404 if FF_REGISTRATION_PAGE is not enabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not has_feature("registration_page"):
            abort(404)
        return f(*args, **kwargs)
    return decorated
```

### Step 3: GET `/register/<url_slug>` - Render Form

1. Look up page via `find_registration_page_by_url_slug()`
2. Call `resolve_visibility(page)` to get state
3. Handle by state:
   - `NOT_FOUND` → `abort(404)`
   - `CLOSED` → `redirect("/registration-closed", 302)`
   - `LIVE` or `TEST` → render form
4. Load HTML source via `get_page_and_source_for_render()`
5. Build `RenderContext` with:
   - `csrf_form_element`: `<input type="hidden" name="csrf_token" value="{generate_csrf()}">`
   - `form_action`: `url_for("registration.submit_registration_form", url_slug=url_slug)`
6. Call `source.render(ctx)` to get rendered HTML
7. Return `render_template("register/form.html", rendered_form=..., is_test=...)`

### Step 4: POST `/register/<url_slug>` - Handle Submission

1. Call `submit_registration(uow, url_slug=url_slug, form_data=request.form)`
2. Handle exceptions:
   - `RegistrationNotFoundError` → `abort(404)`
   - `RegistrationClosedError` → `redirect("/registration-closed", 302)`
3. Check `result.is_valid`:
   - **Valid:** `redirect(url_for("registration.thank_you", url_slug=url_slug))`
   - **Invalid:** Re-render form with errors via `RenderContext(values=result.values, errors=result.field_errors, form_level_errors=result.form_errors)`

### Step 5: GET `/register/<url_slug>/thank-you` - Thank You Page

1. Look up page (return 404 if not found)
2. Get custom HTML via `render_thank_you_html(page)`
3. If empty, render default template
4. Otherwise render custom HTML template

### Step 6: GET `/r/<short_url_slug>` - Short URL Redirect

1. Look up via `find_registration_page_by_short_url_slug()`
2. If not found or no `url_slug` → `abort(404)`
3. Redirect with **302** (not 301 - short slugs may be reused)

### Step 7: GET `/registration-closed` - Closed Page

Simple static template render.

### Step 8: Create Templates

**Directory:** `templates/register/` (new)

#### `form.html`
```html
{% extends "base.html" %}
{% block content %}
<div class="govuk-grid-row">
  <div class="govuk-grid-column-two-thirds">
    {% if is_test %}
    <div class="govuk-notification-banner govuk-notification-banner--warning" role="alert">
      <div class="govuk-notification-banner__header">
        <h2 class="govuk-notification-banner__title">{{ _("Test Mode") }}</h2>
      </div>
      <div class="govuk-notification-banner__content">
        <p>{{ _("This is a test registration page. Submissions will not be entered into the selection pool.") }}</p>
      </div>
    </div>
    {% endif %}
    {{ rendered_form | safe }}
  </div>
</div>
{% endblock %}
```

**Note:** `| safe` is acceptable because `RegistrationPageHtml.render()` uses Jinja2 `SandboxedEnvironment` with `autoescape=True`.

#### `thank_you.html` - Custom HTML wrapper
#### `thank_you_default.html` - Default GOV.UK confirmation panel
#### `closed.html` - Registration closed message

### Step 9: Register Blueprint

**File:** `src/opendlp/entrypoints/flask_app.py`

Add to `register_blueprints()`:
```python
from .blueprints.registration import registration_bp  # noqa: PLC0415
app.register_blueprint(registration_bp)  # No url_prefix - routes define full paths
```

### Step 10: Update Translations

Run `just translate-regen` after adding translatable strings.

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/opendlp/entrypoints/blueprints/registration.py` | **Create** - New blueprint |
| `src/opendlp/entrypoints/flask_app.py` | **Modify** - Register blueprint |
| `templates/register/form.html` | **Create** - Form wrapper |
| `templates/register/thank_you.html` | **Create** - Custom thank-you |
| `templates/register/thank_you_default.html` | **Create** - Default thank-you |
| `templates/register/closed.html` | **Create** - Closed page |
| `tests/unit/entrypoints/test_registration_routes.py` | **Create** - Unit tests |
| `tests/e2e/test_registration_public.py` | **Create** - E2E tests |

## Existing Code to Use (Read-Only)

- `src/opendlp/service_layer/registration_page_service.py:458-471` - `resolve_visibility()`
- `src/opendlp/service_layer/registration_submission_service.py:121-180` - `submit_registration()`
- `src/opendlp/domain/registration_page.py:303-318` - `RegistrationPageHtml.render()`
- `src/opendlp/feature_flags.py:16-21` - `has_feature()`

## Testing Strategy

### Unit Tests
- Feature flag returns 404 when disabled
- Each route returns correct status for each visibility state
- Validation errors re-render form with preserved values
- Short URL redirects with 302

### E2E Tests
- Full submission flow: GET form → POST data → see thank-you
- CSRF token validation works
- Validation errors display correctly

### Manual Testing
1. Set `FF_REGISTRATION_PAGE=true` in environment
2. Create assembly, create registration page via backoffice
3. Set URL slug and publish
4. Visit `/register/<slug>` and submit form
5. Verify respondent created in database

## Security Considerations

1. **XSS:** `SandboxedEnvironment` with `autoescape=True` handles this
2. **CSRF:** Standard Flask-WTF protection via `generate_csrf()`
3. **No auth required:** Public routes intentionally skip `@login_required`
4. **Feature flag:** Routes return 404 when flag disabled

---

## Implementation deltas (2026-06-02)

The plan above landed largely as written. The list below records changes layered on top during user testing and review, both on the public-route side directly and on the adjacent backoffice editor that drives these routes.

### `RenderContext` carries assembly title and question

`RenderContext` picked up two optional fields, both defaulting to empty:

- `assembly_title: str` → substitutes `{{ assembly_title }}`
- `assembly_question: str` → substitutes `{{ assembly_question }}`

Both the initial GET and the post-validation re-render in `registration.py` now call `uow.assemblies.get(page.assembly_id)` and populate the context. The starter form skeleton (`generate_starter_form_html`) emits `<h1>{{ assembly_title }}</h1>` and `<p>{{ assembly_question }}</p>` above the `<form>` tag by default. Neither token is in `REQUIRED_TOKENS`, so authors are free to remove them.

### CSP: Google Fonts whitelisted

Authors paste arbitrary HTML/CSS and the first thing a real form used was Google Fonts. `get_secure_headers()` in `flask_app.py` was widened:

- `style_src` += `https://fonts.googleapis.com`
- `font_src` += `https://fonts.gstatic.com`

Backoffice and login pages don't load Google Fonts, so the practical surface didn't grow outside the new behavior.

### Backoffice editor UX (drives the public routes)

The `/backoffice/assembly/<id>/registration` editor changed significantly during testing. Documented here because the public routes serve what the editor produces — every visitor-facing artifact (URL, banner, redirect) is configured from this page.

#### Status badge + header dropdown replace bottom-row transition buttons

The original layout placed `Save` and `Publish` (or `Save and Republish` and `Stop Accepting Submissions`) next to each other at the bottom of the form. Real testing surfaced a near-miss "I almost clicked Publish when I meant Save." The new layout:

- **Header left** — fixed-width slot holding the status badge (`Test` / `Published` / `Closed`), followed by a `Change status ▾` dropdown. The badge slot has `min-width: 7rem` so the variable badge text doesn't shift the dropdown trigger as status changes.
- **Header right** — `Show Form Skeleton` only (it's an authoring helper, not a state change).
- **Footer** — pairs `Preview and Test Responses` / `Share Form` with `Save` / `Save and Republish`. The "view what you just edited" action sits next to "save it."

The dropdown items are named after the target STATE (nouns), with a one-line description of what visitors will experience:

- From `TEST`:
  - **Published** — *Form goes live; submissions enter the selection pool.*
- From `PUBLISHED`:
  - **Closed for Submissions** — *Visitors are redirected to a registration-closed page; no new submissions are accepted.*
  - **Test** — *Form stays public, but new submissions are flagged as test entries and skipped from the pool.*
- From `CLOSED`:
  - **Published** — *Form goes live again; new submissions enter the selection pool.*

Forbidden TEST↔CLOSED jumps are simply absent from the menus, enforcing the lifecycle at the UI layer (the service layer rejects them too).

Action values posted to `save_assembly_registration` (`publish`, `unpublish`, `close`, `reopen`, `save`) are unchanged.

#### CLOSED state is read-only

In `CLOSED`, there is no `Save` button (form is redirecting, edits have no public effect). `Share Form` stays visible-but-disabled with a `title` tooltip explaining that the URL redirects to the closed page.

#### `dropdown_button` component

A new `components/dropdown_button.html` macro powers the status control. Sibling of `split_button` but with no primary action elevated outside the menu — every option lives in the dropdown. Items support an optional `description` field for two-line entries. Menu width is `min(100%, 20rem) – 26rem`. Hover/focus use `--color-button-tertiary-bg-hover` so the affordance matches the rest of the design system.

#### Preview / Share modal mirrors the Details tab

Triggered from the footer-row button:

- **TEST** → labeled `Preview and Test Responses`. Modal shows an amber TEST notice, the long URL, the short URL (if set), and the QR code (if a short slug exists, mirrors the Details tab).
- **PUBLISHED** → labeled `Share Form`. Same modal contents, no TEST notice.
- **CLOSED** → button disabled.

The QR is now sourced from `registration_page.short_url_slug` (matching the Details tab) instead of a placeholder built from `url_slug`. `readonly_url_display` was extracted into `components/url_display.html` so the Details tab and this modal share one implementation.

#### `/edit` page locks slugs while published or closed

`RegistrationPage.slugs_frozen` now mirrors current status (`status != TEST`) rather than `has_ever_been_published()`. Editing the assembly title while the page is in TEST no longer fails with a slug-update error, even if the page was published at some point in the past. The `/edit` page:

- Renders the URL inputs disabled (`prefixed_url_input` picked up a `disabled` arg)
- Shows an info alert above them when frozen
- Short-circuits the `update_registration_page` call entirely when `registration_page.slugs_frozen` is true

Defense in depth: `update_registration_page` also no-ops when submitted slugs match the current values, so a future caller forgetting both the UI lock and the route gate still won't spuriously error.

### Scroll preservation

Every status-action and Save submission on the registration form preserves scroll across the POST→redirect→GET cycle:

- The form carries `x-preserve-scroll-on-submit`.
- All four `view_assembly_registration` redirect paths in the save handler use `redirect_preserving_scroll(...)` instead of plain `redirect(...)`.

### Translation strings added

The following English strings need Hungarian translations on the next `just translate-regen` cycle:

- `Preview and Test Responses`, `Share Form`
- `Change status`, `Published`, `Closed for Submissions`, `Test` (the **target-state** nouns — separate keys from the badge text even though spelling matches)
- The three status-description sentences in the dropdown
- `Registration is closed — the form URL redirects to the closed page`
- `These URLs are locked while the registration page is published or closed, so links shared in invites, QR codes, and elsewhere keep working. Switch the form back to test mode from the Registration tab to edit them.`
- `Cannot change slugs while the registration page is published or closed` (domain-side error message)
