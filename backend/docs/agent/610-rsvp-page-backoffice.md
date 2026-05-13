# RSVP Page Backoffice - Presentation Layer Specification

**Branch:** `610-rsvp-page-backoffice`
**Status:** Ready for implementation
**Last Updated:** 2026-05-13

## Overview

This specification covers the **presentation/representation layer** for the RSVP (Registration) page backoffice feature. The feature allows assembly managers to create custom HTML registration forms that respondents can use to subscribe to an assembly.

**Key Concept:** Instead of a complex form builder, we provide a raw HTML approach where technologically skilled users paste HTML code with template placeholders (wildcards) that the backend resolves to actual form elements.

## Scope

This specification covers **only** the backoffice UI (presentation layer):
- New "Registration" tab in assembly backoffice
- HTML textarea for form content
- Template placeholders reference
- URL/Short URL configuration
- QR code display and download
- Publish/unpublish toggle
- Thank you page HTML editor

**Out of scope for this spec:**
- Service layer implementation (handled by colleague)
- Domain models (RegistrationPage, RegistrationHTML, etc.)
- Public-facing form rendering
- Form submission processing
- Bot protection, JavaScript support, image uploads

---

## Feature Design

### 1. New Assembly Tab: "Registration"

Add a new tab to the assembly tabs navigation. This tab will be available to all assemblies regardless of data source configuration.

**Tab Position:** Before "Respondents" tab (after Targets, or after Fields if targets not yet configured)

**Tab Enable Logic:** Always enabled (no prerequisites like targets/respondents tabs)

### 2. Registration Tab Content

The registration tab is a **single cohesive form** with one "Save" button at the bottom. All configuration is saved together.

#### Card 1: Form URL Configuration

| Field | Type | Description |
|-------|------|-------------|
| URL Slug | Text input | Custom URL path for the form (e.g., `my-assembly-2026`) |
| Short URL Slug | Text input | Short URL path for compact links (e.g., `ma26`) |
| Full URL | Read-only display | Shows complete URL: `https://domain.com/register/my-assembly-2026` |
| Short URL | Read-only display | Shows complete short URL: `https://domain.com/r/ma26` |

#### Card 2: QR Code

- Display QR code image based on short URL
- "Download QR Code" button (downloads PNG image)
- Hint text: "Use this QR code on paper invitations"

#### Card 3: Publication Status

| Field | Type | Description |
|-------|------|-------------|
| Published | Switch/Toggle | When ON, form is publicly accessible |
| Preview Token | Read-only text | Auto-generated token for previewing unpublished forms |
| Preview URL | Read-only link | URL with token for testing: `/register/slug?token=abc123` |

**Behaviour when unpublished:**
- Public URL redirects to generic "Registration is Closed" page
- Form is only visible with valid preview token

#### Card 4: Registration Form HTML

Large textarea for pasting HTML code with template placeholders.

**UI Components:**
- Large textarea (20-30 rows minimum, resizable)
- "Save" button
- Template placeholders reference section below textarea
- Optional: "Copy Starter Template" button to get basic form structure

#### Card 5: Template Placeholders Reference

Display a reference table of available placeholders that users can copy-paste into their HTML:

**Required Placeholders:**

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{ csrf_form_element }}` | Hidden CSRF token input | `<input type="hidden" name="csrf_token" value="...">` |
| `{{ form_action }}` | Form action URL | `/register/my-assembly/submit` |

**Personal Fields (Required):**

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{ first_name }}` | First name input | `<input type="text" name="first_name" required ...>` |
| `{{ last_name }}` | Last name input | `<input type="text" name="last_name" required ...>` |
| `{{ email }}` | Email input | `<input type="email" name="email" required ...>` |
| `{{ phone }}` | Phone input | `<input type="tel" name="phone" ...>` |
| `{{ address_line_1 }}` | Address line 1 | `<input type="text" name="address_line_1" ...>` |
| `{{ address_line_2 }}` | Address line 2 | `<input type="text" name="address_line_2" ...>` |
| `{{ city }}` | City input | `<input type="text" name="city" ...>` |
| `{{ postcode }}` | Postcode input | `<input type="text" name="postcode" ...>` |

**Opt-in Fields:**

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{ opt_in_email }}` | Email opt-in checkbox | `<input type="checkbox" name="opt_in_email" ...>` |
| `{{ opt_in_phone }}` | Phone opt-in checkbox | `<input type="checkbox" name="opt_in_phone" ...>` |
| `{{ opt_in_post }}` | Postal opt-in checkbox | `<input type="checkbox" name="opt_in_post" ...>` |

**Demographic/Target Fields:**

The target fields will be dynamically generated based on the assembly's configured target categories. Each placeholder resolves to appropriate inputs (select, radio, checkbox group, etc.).

| Placeholder Pattern | Description |
|---------------------|-------------|
| `{{ target_<field_name> }}` | Target category input (e.g., `{{ target_age_range }}`, `{{ target_gender }}`) |

**UI for Placeholders Section:**
- Collapsible/expandable section
- Each placeholder in a `<code>` block with "Copy" button
- Group placeholders by category (Form Structure, Personal, Opt-ins, Targets)
- Show which placeholders are required vs optional

#### Card 6: Thank You Page HTML

Second textarea for the confirmation/thank you page shown after successful registration.

**Fields:**
- Large textarea (10-15 rows)
- "Save" button (can be combined with main form save)

**Available Placeholders for Thank You Page:**

| Placeholder | Description |
|-------------|-------------|
| `{{ first_name }}` | Registrant's first name |
| `{{ email }}` | Registrant's email |
| `{{ assembly_title }}` | Assembly title |

---

## UI Mockup (ASCII)

Single cohesive form with one Save button. Tab positioned before "Respondents".

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Assembly: My Citizens Assembly 2026                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Details] [Data] [Fields] [Targets] [Registration] [Respondents] ...      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  <form>                                                                      │
│                                                                              │
│  ── URL Configuration ──────────────────────────────────────────────────────│
│                                                                              │
│  URL Slug              [my-assembly-2026                    ]                │
│  Short URL Slug        [ma26                                ]                │
│                                                                              │
│  Full URL:   https://example.com/register/my-assembly-2026                  │
│  Short URL:  https://example.com/r/ma26                                     │
│                                                                              │
│  ── QR Code ────────────────────────────────────────────────────────────────│
│                                                                              │
│  ┌────────┐                                                                  │
│  │ ▓▓▓▓▓▓ │  Scan this code to access the registration form                │
│  │ ▓    ▓ │                                                                  │
│  │ ▓▓▓▓▓▓ │  [Download QR Code]                                             │
│  └────────┘                                                                  │
│                                                                              │
│  ── Publication Status ─────────────────────────────────────────────────────│
│                                                                              │
│  Published   [○━━━] Off                                                      │
│                                                                              │
│  Preview Token:  abc123xyz                                                   │
│  Preview URL:    https://example.com/register/my-assembly-2026?token=abc123 │
│                                                                              │
│  ── Registration Form HTML ─────────────────────────────────────────────────│
│                                                                              │
│  Paste your HTML form code below. Use template placeholders for form        │
│  elements that will be resolved by the system.                              │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ <form action="{{ form_action }}" method="POST">                      │   │
│  │   {{ csrf_form_element }}                                            │   │
│  │   <div class="form-group">                                           │   │
│  │     <label>First Name</label>                                        │   │
│  │     {{ first_name }}                                                 │   │
│  │   </div>                                                             │   │
│  │   ...                                                                │   │
│  │ </form>                                                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  (monospace font, ~25 rows, resizable)                                      │
│                                                                              │
│  ── Thank You Page HTML ────────────────────────────────────────────────────│
│                                                                              │
│  This page is shown after successful registration.                          │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ <h1>Thank you, {{ first_name }}!</h1>                                │   │
│  │ <p>Your registration for {{ assembly_title }} is complete.</p>      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  (monospace font, ~12 rows, resizable)                                      │
│                                                                              │
│  ── Available Placeholders ─────────────────────────────────────────────────│
│                                                                              │
│  ▼ Form Structure (Required)                                                │
│    {{ csrf_form_element }}  [Copy]  - CSRF protection token                 │
│    {{ form_action }}        [Copy]  - Form submission URL                   │
│                                                                              │
│  ▼ Personal Fields                                                          │
│    {{ first_name }}  [Copy]  - First name input (required)                  │
│    {{ last_name }}   [Copy]  - Last name input (required)                   │
│    {{ email }}       [Copy]  - Email input (required)                       │
│    {{ phone }}       [Copy]  - Phone input                                  │
│    ...                                                                       │
│                                                                              │
│  ▼ Opt-in Fields                                                            │
│    {{ opt_in_email }}  [Copy]  - Email opt-in checkbox                      │
│    {{ opt_in_phone }}  [Copy]  - Phone opt-in checkbox                      │
│    {{ opt_in_post }}   [Copy]  - Postal opt-in checkbox                     │
│                                                                              │
│  ▼ Target Fields (based on assembly configuration)                          │
│    {{ target_age_range }}  [Copy]  - Age range selection                    │
│    {{ target_gender }}     [Copy]  - Gender selection                       │
│    ...                                                                       │
│                                                                              │
│                                                              [Save]          │
│  </form>                                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

Each step is designed to be **independently testable** with manual verification. Service layer calls are stubbed/mocked until the service layer is ready.

---

### Step 1: Basic Tab and Empty Page

**Goal:** Registration tab appears in navigation and links to a working page.

**Files to modify:**
- `templates/backoffice/components/assembly_tabs.html` - Add tab
- `src/opendlp/entrypoints/blueprints/backoffice.py` - Add route
- `templates/backoffice/assembly_registration.html` - Create template (minimal)

**Implementation:**

1. Add "Registration" tab before "Respondents" in `assembly_tabs.html`
2. Create GET route `/assembly/<uuid:assembly_id>/registration`
3. Create minimal template with page header and assembly tabs

**Manual Test:**
- Navigate to any assembly
- Click "Registration" tab
- Page loads with header "Registration" and all tabs visible
- Tab highlighting shows "Registration" as active

---

### Step 2: Form Layout with URL Configuration

**Goal:** URL configuration fields display with mock data; form submits but shows "not implemented" flash.

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Add URL fields
- `src/opendlp/entrypoints/blueprints/backoffice.py` - Add POST route (stub)

**Implementation:**

1. Add URL slug and short URL slug input fields
2. Add read-only full URL display (computed from slug)
3. Add POST route that flashes "Save not yet implemented" and redirects back
4. Single "Save" button at bottom of form

**Template structure:**
```jinja
<form method="post" action="{{ url_for('backoffice.save_assembly_registration', assembly_id=assembly.id) }}">
    {{ csrf_token_input() }}

    {# URL Configuration section #}
    {{ input(name="url_slug", label=_("URL Slug"), value=registration_page.url_slug if registration_page else "", ...) }}
    {{ input(name="short_url_slug", label=_("Short URL Slug"), value=...) }}

    {# Read-only computed URLs #}
    <p>Full URL: https://example.com/register/{{ url_slug or "your-slug" }}</p>

    {{ button(_("Save"), type="submit") }}
</form>
```

**Manual Test:**
- Navigate to Registration tab
- See URL slug input fields
- Type a slug, see full URL preview update (if using Alpine.js for live preview)
- Click Save → Flash message appears
- Form values persist after reload (once service layer ready)

---

### Step 3: QR Code Display and Download

**Goal:** QR code displays on page and can be downloaded as PNG.

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Add QR code section
- `src/opendlp/entrypoints/blueprints/backoffice.py` - Add QR download route

**Implementation:**

1. Generate QR code server-side using `qrcode` library
2. Embed as base64 data URL in `<img>` tag
3. Add download route that returns PNG with `Content-Disposition: attachment`

**QR Code generation (in route or helper):**
```python
import qrcode
import io
import base64

def generate_qr_code_base64(url: str) -> str:
    qr = qrcode.make(url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
```

**Manual Test:**
- Navigate to Registration tab
- QR code image displays
- Click "Download QR Code" → PNG file downloads
- Scan QR code with phone → Opens correct URL

---

### Step 4: Publication Status Toggle

**Goal:** Publish toggle displays current state; toggling shows feedback.

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Add publish toggle section
- `src/opendlp/entrypoints/blueprints/backoffice.py` - Update to handle publish toggle

**Implementation:**

1. Add switch component for published state
2. Add preview token display (read-only, shown when unpublished)
3. Add preview URL display with clickable link
4. Toggle submits form and flashes status change message

**Manual Test:**
- Navigate to Registration tab
- See publish toggle (default: unpublished)
- Toggle to "Published" → Flash "Form published" (stubbed)
- When unpublished, preview token and preview URL display
- Click preview URL → Opens in new tab (will 404 until public routes exist)

---

### Step 5: HTML Textarea with Monospace Font

**Goal:** Large HTML textarea displays with monospace styling; form saves (stubbed).

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Add HTML textarea
- `static/backoffice/css/` - Add monospace styling if needed

**Implementation:**

1. Add large textarea (rows=25) for registration form HTML
2. Apply monospace font via classes or inline style
3. Add hint text explaining the purpose

**Textarea styling:**
```jinja
{{ textarea(
    name="html_content",
    label=_("Registration Form HTML"),
    value=registration_page.html_content if registration_page else "",
    hint=_("Paste your HTML form code. Use template placeholders for form fields."),
    rows=25,
    classes="font-mono text-sm"
) }}
```

**Note:** May need to add `font-mono` utility class to Tailwind config or use inline style `font-family: monospace;`

**Manual Test:**
- Navigate to Registration tab
- See large textarea with monospace font
- Paste HTML code → Text appears in monospace
- Resize textarea vertically
- Click Save → Flash message, form reloads with content (once service layer ready)

---

### Step 6: Thank You Page Textarea

**Goal:** Second textarea for thank you page HTML.

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Add thank you textarea

**Implementation:**

1. Add second textarea (rows=12) for thank you page HTML
2. Same monospace styling as main textarea
3. Separate section heading

**Manual Test:**
- Navigate to Registration tab
- See both textareas: "Registration Form HTML" and "Thank You Page HTML"
- Both have monospace font
- Single Save button saves both (once service layer ready)

---

### Step 7: Placeholder Reference Section

**Goal:** Collapsible section showing copyable placeholders organized by category.

**Files to create:**
- `templates/backoffice/components/placeholder_reference.html` - Reusable macro

**Files to modify:**
- `templates/backoffice/assembly_registration.html` - Include placeholder reference

**Implementation:**

1. Create macro for placeholder reference section
2. Use `<details>`/`<summary>` for native collapsible behavior
3. Group placeholders by category (Form Structure, Personal, Opt-ins, Targets)
4. Each placeholder in `<code>` block with copy button

**Copy button pattern (CSP-compliant):**
```html
<div class="flex items-center gap-2" x-data="{ copied: false }">
    <code class="font-mono text-sm px-2 py-1 rounded"
          style="background-color: var(--color-subtle-background-panels);">
        {{ "{{ csrf_form_element }}" }}
    </code>
    <button type="button"
            class="text-button-sm"
            data-copy-text="{{ csrf_form_element }}"
            @click="navigator.clipboard.writeText('{{ csrf_form_element }}'); copied = true; setTimeout(() => copied = false, 2000)"
            x-text="copied ? '{{ _('Copied!') }}' : '{{ _('Copy') }}'"
            :aria-label="copied ? '{{ _('Copied to clipboard') }}' : '{{ _('Copy placeholder to clipboard') }}'">
    </button>
</div>
```

**Manual Test:**
- Navigate to Registration tab
- See "Available Placeholders" section (collapsed by default)
- Click to expand → See categorized placeholders
- Click "Copy" on any placeholder → Text changes to "Copied!"
- Paste in textarea → Placeholder text appears
- Categories visible: Form Structure, Personal Fields, Opt-ins, Target Fields

---

### Step 8: Wire Up Service Layer

**Goal:** Connect presentation layer to service layer functions.

**Files to modify:**
- `src/opendlp/entrypoints/blueprints/backoffice.py` - Replace stubs with real calls

**Implementation:**

1. Import service layer functions
2. Replace flash stubs with actual save operations
3. Load existing registration page data in GET route
4. Handle validation errors from service layer

**This step depends on service layer being available.**

**Manual Test:**
- Save URL configuration → Persists after reload
- Save HTML content → Persists after reload
- Toggle publish → State persists
- Create new registration page for assembly without one

---

## Files to Create/Modify

### New Files

| File | Description |
|------|-------------|
| `templates/backoffice/assembly_registration.html` | Main registration tab template |
| `templates/backoffice/components/placeholder_reference.html` | Reusable placeholder reference macro |

### Modified Files

| File | Changes |
|------|---------|
| `templates/backoffice/components/assembly_tabs.html` | Add "Registration" tab |
| `src/opendlp/entrypoints/blueprints/backoffice.py` | Add registration routes |

---

## Accessibility Considerations

Following the [Component Accessibility Guide](component_accessibility.md):

1. **Textarea:**
   - Proper `<label>` association via `for`/`id`
   - Hint text linked via `aria-describedby`
   - Error states announced

2. **Copy Buttons:**
   - Meaningful `aria-label` (e.g., "Copy placeholder to clipboard")
   - Visual feedback on copy (text changes to "Copied!")
   - `aria-live="polite"` region for copy confirmation

3. **Collapsible Sections:**
   - Use `<details>`/`<summary>` for native keyboard support
   - Or: `aria-expanded` + `aria-controls` pattern

4. **QR Code:**
   - `alt` text: "QR code linking to registration form at [URL]"
   - Download button has clear label

5. **Switch/Toggle:**
   - Use existing `switch` macro which has `role="switch"` and `aria-checked`

---

## Internationalization

All user-facing strings must be wrapped in gettext:

```jinja
{{ _("Registration") }}
{{ _("Form URL") }}
{{ _("Save HTML") }}
{{ _("Copy") }}
{{ _("Copied!") }}
{{ _("Available Placeholders") }}
{{ _("Download QR Code") }}
{{ _("Published") }}
```

---

## Security Considerations

1. **CSRF Protection:** All forms include `{{ csrf_token_input() }}`

2. **HTML Content:** The HTML entered by users is stored as-is. When rendered publicly:
   - Service layer handles template placeholder resolution
   - No server-side sanitization of user HTML (intentional - allows custom styling)
   - Scripts are **not** executed (inline JS disabled, external JS not loaded)

3. **Preview Token:** Auto-generated secure token for unpublished form preview

4. **Permission Check:** All routes use `@require_assembly_management` decorator

---

## Testing Strategy

### Manual Testing

1. **Tab Navigation:**
   - Navigate to assembly → Registration tab appears
   - Tab is always enabled regardless of data configuration

2. **URL Configuration:**
   - Enter URL slug → Full URL updates
   - Enter short URL slug → Short URL updates
   - Save → Success flash message

3. **QR Code:**
   - QR code displays correctly
   - Download button downloads PNG file
   - Scanning QR leads to correct URL

4. **Publication Toggle:**
   - Toggle published OFF → Preview token appears
   - Preview URL works with token
   - Public URL redirects to "closed" page
   - Toggle published ON → Public URL works

5. **HTML Editor:**
   - Paste HTML → Saves correctly
   - Placeholders in reference are copyable
   - Form renders correctly when previewed

### Unit Tests

```python
def test_view_assembly_registration_route():
    """Registration tab accessible to assembly managers."""

def test_save_registration_urls():
    """URL slugs save correctly."""

def test_toggle_registration_publish():
    """Publication toggle works."""
```

### BDD Tests (Future)

```gherkin
Scenario: Assembly manager configures registration form
  Given I am logged in as an assembly organiser
  And I have an active assembly
  When I navigate to the Registration tab
  Then I see the URL configuration card
  And I see the HTML editor card
```

---

## Dependencies

### Python Packages

May need to add:
- `qrcode` - For QR code generation
- `Pillow` - Image processing for QR code (likely already installed)

Check if already in `pyproject.toml`:
```bash
grep -i qrcode pyproject.toml
```

### Service Layer (Not Yet Implemented)

The presentation layer will call these service functions (to be implemented by colleague):

```python
# Expected service layer interface
def get_registration_page(uow, assembly_id) -> RegistrationPage | None
def create_or_update_registration_page(uow, assembly_id, url_slug, short_url_slug) -> RegistrationPage
def save_registration_html(uow, registration_page_id, html_content) -> None
def save_thank_you_html(uow, registration_page_id, html_content) -> None
def toggle_registration_publish(uow, registration_page_id) -> bool
def regenerate_preview_token(uow, registration_page_id) -> str
```

---

## Reference Files

| Purpose | File Path |
|---------|-----------|
| Assembly tabs macro | `templates/backoffice/components/assembly_tabs.html` |
| Input/textarea components | `templates/backoffice/components/input.html` |
| Card component | `templates/backoffice/components/card.html` |
| Button component | `templates/backoffice/components/button.html` |
| Switch component | `templates/backoffice/components/input.html` (switch macro) |
| Example assembly page | `templates/backoffice/assembly_details.html` |
| Routes pattern | `src/opendlp/entrypoints/blueprints/backoffice.py` |
| Accessibility guide | `docs/agent/component_accessibility.md` |
| Frontend patterns | `/backoffice/dev/patterns` (dev only) |

---

## Resolved Design Decisions

1. **Tab Position:** Before "Respondents" tab (after Targets/Fields) ✓
2. **Combined Save:** Single cohesive form with one "Save" button ✓
3. **Monospace Font:** Yes, use monospace for HTML editing ✓
4. **Syntax Highlighting:** Future enhancement - consider CodeMirror with HTML parsing ✓
5. **Validation Feedback:** Post-MVP - defer placeholder validation warnings ✓
