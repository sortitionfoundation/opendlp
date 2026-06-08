# Registration Page Creation CTA — Implementation Plan

**Branch:** `610-registration-page-html`
**Date:** 2026-05-26
**Status:** Draft
**Depends on:** Existing `create_registration_page()` service function

---

## 1. Overview

Currently, registration pages are created silently when a user first saves content on the Registration tab. This is confusing because:

1. The user doesn't know a page was created
2. URL slugs need to be set **weeks before** form content (for printing invitations, etc.)
3. The creation action is hidden inside a save operation

This plan introduces an explicit "Create Registration Page" CTA on the Assembly Details tab, with auto-generated slugs that can be edited afterward.

---

## 2. User Flow

### 2.1 Assembly Details Tab (no registration page)

**Current:** Shows "No registration URLs configured yet" with link to edit assembly.

**New:**
```
┌─────────────────────────────────────────────────────────────┐
│ Registration Page Details                                    │
│                                                              │
│ No registration page has been created for this assembly.    │
│                                                              │
│ [Create Registration Page]  ← Primary button                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Click "Create Registration Page"

1. Auto-generate `url_slug` from assembly name (see §4.1)
2. Auto-generate `short_url_slug` as random 6-digit number (see §4.2)
3. Call `create_registration_page()` service function
4. Stay on Details tab, refresh to show the new URLs (read-only)
5. User can click "Edit" to modify slugs if needed

### 2.3 Assembly Details Tab (registration page exists)

**Same as current:** Shows registration URL, short URL (if set), QR code, with copy buttons.

### 2.4 Registration Tab (no registration page)

**Current:** Shows editor with defaults, creates page silently on first save.

**New:**
```
┌─────────────────────────────────────────────────────────────┐
│ ⚠ Registration page not created                             │
│                                                              │
│ Before you can configure the registration form, you need    │
│ to create a registration page from the Details tab.         │
│                                                              │
│ [Go to Details tab]                                         │
└─────────────────────────────────────────────────────────────┘
```

Yellow warning panel (GOV.UK warning style). No editor shown.

### 2.5 Registration Tab (registration page exists)

**Same as current:** Full editor with HTML content, status actions, etc.

---

## 3. Implementation Steps

### 3.1 Remove Silent Creation

**File:** `src/opendlp/service_layer/registration_page_service.py`

In `save_registration_page_html()` (or wherever the silent creation happens), remove the auto-creation logic. The function should raise an error or return early if no registration page exists.

**File:** `src/opendlp/entrypoints/blueprints/backoffice.py`

In `save_assembly_registration()`, remove the call to `create_registration_page()`. Instead, check if page exists and return an error response if not.

### 3.2 Add Slug Generation Utilities

**File:** `src/opendlp/service_layer/registration_page_service.py` (or new utility module)

```python
def generate_url_slug_from_name(name: str, max_length: int = 25) -> str:
    """Generate a URL slug from assembly name.

    Takes first N words that fit within max_length characters.
    Slugifies: lowercase, hyphens for spaces, remove special chars.
    """
    ...

def generate_unique_url_slug(
    uow: AbstractUnitOfWork,
    base_slug: str,
) -> str:
    """Ensure slug is unique, appending -2, -3, etc. if needed."""
    ...

def generate_short_url_slug() -> str:
    """Generate a random 6-digit numeric string."""
    import random
    return str(random.randint(100000, 999999))

def generate_unique_short_url_slug(uow: AbstractUnitOfWork) -> str:
    """Generate unique 6-digit short slug, retrying on collision."""
    ...
```

### 3.3 Add Creation Endpoint

**File:** `src/opendlp/entrypoints/blueprints/backoffice.py`

New route:
```python
@backoffice.route("/assembly/<uuid:assembly_id>/registration/create", methods=["POST"])
@login_required
@require_assembly_management
def create_assembly_registration_page(assembly_id: uuid.UUID):
    """Create a registration page with auto-generated slugs."""
    ...
```

**Logic:**
1. Load assembly
2. Check registration page doesn't already exist (400 if exists)
3. Generate `url_slug` from `assembly.title`
4. Ensure uniqueness with suffix if needed
5. Generate `short_url_slug` (random 6-digit)
6. Ensure uniqueness (regenerate if collision)
7. Call `create_registration_page()`
8. Update slugs via `update_registration_page()`
9. Flash success message
10. Redirect to Details tab

### 3.4 Update Assembly Details Template

**File:** `templates/backoffice/assembly_details.html`

Replace the "Registration URLs" section:

```jinja
{# Registration Page Details Section #}
<div class="mb-8">
    {% call section() %}
        <h2 class="text-heading-lg mb-6" style="color: var(--color-headings);">
            {{ _("Registration Page Details") }}
        </h2>

        {% if registration_page %}
            {# Existing display: URLs, QR code, copy buttons #}
            <div class="space-y-6 max-w-2xl">
                {{ readonly_url_display(...) }}
                ...
            </div>
        {% else %}
            {# CTA to create registration page #}
            <p class="text-body-md mb-4" style="color: var(--color-secondary-text);">
                {{ _("No registration page has been created for this assembly.") }}
            </p>
            <form method="POST"
                  action="{{ url_for('backoffice.create_assembly_registration_page', assembly_id=assembly.id) }}">
                {{ csrf_hidden_input() }}
                <button type="submit" class="govuk-button" data-module="govuk-button">
                    {{ _("Create Registration Page") }}
                </button>
            </form>
        {% endif %}
    {% endcall %}
</div>
```

### 3.5 Update Registration Tab Template

**File:** `templates/backoffice/assembly_registration.html`

Wrap existing content in a conditional:

```jinja
{% if registration_page %}
    {# Existing editor UI #}
    ...
{% else %}
    {# Warning panel #}
    <div class="govuk-warning-text">
        <span class="govuk-warning-text__icon" aria-hidden="true">!</span>
        <strong class="govuk-warning-text__text">
            <span class="govuk-visually-hidden">{{ _("Warning") }}</span>
            {{ _("Registration page not created") }}
        </strong>
    </div>
    <p class="govuk-body">
        {{ _("Before you can configure the registration form, you need to create a registration page from the Details tab.") }}
    </p>
    <a href="{{ url_for('backoffice.view_assembly', assembly_id=assembly.id) }}"
       class="govuk-button govuk-button--secondary">
        {{ _("Go to Details tab") }}
    </a>
{% endif %}
```

### 3.6 Update Route Handler

**File:** `src/opendlp/entrypoints/blueprints/backoffice.py`

In `view_assembly_registration()`:
- Pass `registration_page` (or `None`) to template
- Don't set defaults when page doesn't exist (let template handle it)

---

## 4. Slug Generation Details

### 4.1 URL Slug from Assembly Name

**Algorithm:**
1. Take assembly title (e.g., "Dublin Citizens' Assembly on Housing 2026")
2. Slugify: lowercase, replace spaces/special chars with hyphens
   → `dublin-citizens-assembly-on-housing-2026`
3. Split into words by hyphen
4. Take first N words where total length ≤ 25 chars
   → `dublin-citizens-assembly` (24 chars)
5. If collision exists, append `-2`, `-3`, etc.

**Edge cases:**
- Empty name → use `assembly-<random-6-digits>`
- Name with no valid slug chars → use `assembly-<random-6-digits>`
- Very long first word (>25 chars) → truncate to 25

### 4.2 Short URL Slug

**Algorithm:**
1. Generate random 6-digit number (100000-999999)
2. Check for collision in database
3. If collision, regenerate (max 10 attempts, then fail)

**Why 6 digits:**
- 900,000 possible values — plenty of headroom
- Easy to type/remember
- QR code stays compact

---

## 5. Testing Strategy

### 5.1 Unit Tests

**Slug generation:**
- `test_generate_url_slug_from_name_basic` — simple name works
- `test_generate_url_slug_truncates_to_max_length` — respects 25 char limit
- `test_generate_url_slug_handles_special_chars` — apostrophes, accents removed
- `test_generate_url_slug_handles_empty_name` — fallback to random
- `test_generate_short_url_slug_is_6_digits` — format check

**Uniqueness:**
- `test_generate_unique_url_slug_appends_suffix_on_collision`
- `test_generate_unique_short_url_slug_retries_on_collision`

### 5.2 Integration Tests

- `test_create_registration_page_endpoint_creates_with_slugs`
- `test_create_registration_page_endpoint_rejects_duplicate`
- `test_registration_tab_shows_warning_when_no_page`
- `test_details_tab_shows_cta_when_no_page`

### 5.3 BDD Tests

- "As an organiser, I can create a registration page from the Details tab"
- "When I create a registration page, URLs are auto-generated from assembly name"
- "When I visit the Registration tab before creating a page, I see a warning"

---

## 6. Migration Notes

**No database migration needed** — uses existing tables and columns.

**Existing assemblies:** If an assembly already has a registration page (created via the old silent method), no change needed. If it doesn't have one, user will see the new CTA.

---

## 7. Open Questions

### Q1 — Should CTA require confirmation?

Currently proposed: Single click creates immediately.

Alternative: Show a preview of the generated slugs with "Create" / "Cancel" buttons.

**Recommendation:** Single click is fine — user can edit slugs afterward via the Edit button.

### Q2 — What if user is in Edit mode on Details tab?

Should the CTA be visible in edit mode? Or only in view mode?

**Recommendation:** Show CTA in view mode only. In edit mode, the slug fields would be shown (if page exists) or the CTA area would be non-editable.

### Q3 — Flash message after creation?

**Recommendation:** Yes, show success flash: "Registration page created. You can edit the URLs below."

---

## 8. Files to Modify

| File | Changes |
|------|---------|
| `service_layer/registration_page_service.py` | Add slug generation functions, remove silent creation |
| `entrypoints/blueprints/backoffice.py` | Add create endpoint, update `view_assembly_registration()` |
| `templates/backoffice/assembly_details.html` | Rename section, add CTA |
| `templates/backoffice/assembly_registration.html` | Add warning panel conditional |
| `tests/unit/service_layer/test_registration_page_service.py` | Add slug generation tests |
| `tests/integration/test_registration_page_routes.py` | Add endpoint tests |

---

## 9. Implementation Order

1. **Slug generation utilities** — pure functions, easy to test
2. **Remove silent creation** — clean up existing code
3. **Add creation endpoint** — new route with slug generation
4. **Update Details template** — CTA and section rename
5. **Update Registration template** — warning panel
6. **Tests** — unit, integration, BDD
7. **Regenerate translations** — `just translate-regen`
