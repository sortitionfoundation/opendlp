# Applying Design System to Dashboard & Assembly Pages

This document tracks the process of migrating GOV.UK-styled pages to the backoffice design system (PineUI + Tailwind CSS).

## Current Context

**Completed:** Edit Assembly page

**Key files for this task:**
- `templates/backoffice/components/` - Component macros (button, input, card, navigation, breadcrumbs, footer)
- `templates/backoffice/assembly_details.html` - Assembly details page (completed)
- `templates/backoffice/edit_assembly.html` - Edit assembly page (completed)
- `src/opendlp/entrypoints/backoffice/routes.py` - Backoffice routes

**Components available:**
- `button(text, variant, href, ...)` - Buttons and link buttons
- `input(name, label, type, ...)` - Text inputs with label/hint/error
- `textarea(name, label, rows, ...)` - Multi-line text input
- `card(title, subtitle, ...)` - Card containers
- `navigation(...)` - Site header/nav
- `breadcrumbs([...])` - Navigation trail
- `footer()` - Site footer

**What was done:**
1. Created `templates/backoffice/edit_assembly.html` with form for editing assembly details
2. Added `edit_assembly` route in `src/opendlp/entrypoints/backoffice/routes.py`
3. Updated `assembly_details.html` to link to backoffice edit route
4. Added flash message handling to `assembly_details.html`
5. Fixed input component to handle `0` values correctly
6. Added BDD tests for edit assembly functionality

---

## Overview

**Goal:** Migrate dashboard and assembly detail pages from GOV.UK design to the backoffice design system.

**Approach:**
1. Use existing backoffice components (navigation, footer, breadcrumbs, buttons, cards)
2. Apply semantic design tokens for colors
3. Use typography classes for text styling
4. Maintain responsive layouts with Tailwind utilities

## Pages Migrated

### 1. Dashboard (`/backoffice/dashboard`)

**Status:** ✅ Complete

**Components Used:**
- Navigation component (with conditional nav items)
- Footer component
- Card component (for assembly cards)
- Button component

**Key Changes:**
- Replaced GOV.UK header with backoffice navigation macro
- Replaced GOV.UK footer with backoffice footer macro
- Assembly cards use card component with button for "Go to Assembly"
- Applied semantic tokens: `--color-headings`, `--color-secondary-text`, `--color-body-text`
- Typography: `text-display-lg`, `text-heading-lg`, `text-body-lg`, `text-body-md`, `text-body-sm`

**Layout:**
- Container: `max-w-screen-2xl mx-auto px-6 py-8`
- Grid: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6`
- Footer pushed to bottom with `min-h-screen flex flex-col` on body and `flex-1` on main

**Route:** `backoffice.dashboard` (`/backoffice/dashboard`)

---

### 2. Assembly Details (`/backoffice/assembly/<uuid:assembly_id>`)

**Status:** ✅ Complete

**Components Used:**
- Navigation component
- Breadcrumbs component (Dashboard → Assembly Title)
- Footer component
- Button component (Edit Assembly, Back to Dashboard)

**Key Changes:**
- Breadcrumbs navigation trail
- Assembly Question section with `text-heading-lg` + `text-body-lg`
- Details summary using styled `<dl>/<dd>` with design tokens
- Status badge using inline styles (TODO: create badge component?)
- TODO comment for tab navigation (Details | Data & Selection | Team Members)

**Details Summary Styling:**
```css
Background: var(--color-tables-cards)
Border: 1px solid var(--color-borders-dividers)
Rows: border-bottom with --color-borders-dividers
Labels: text-body-md font-medium, --color-secondary-text
Values: text-body-md, --color-body-text
```

**Layout:**
- Same container and flex layout as dashboard
- Breadcrumbs in `mb-6` div
- Sections with `mb-8` spacing
- Responsive `dl/dd`: `flex flex-col sm:flex-row` with fixed label width on desktop

**Route:** `backoffice.view_assembly` (`/backoffice/assembly/<uuid:assembly_id>`)

---

## Design System Components Created/Updated

### Breadcrumbs Component

**File:** `templates/backoffice/components/breadcrumbs.html`

**Usage:**
```jinja
{% from "backoffice/components/breadcrumbs.html" import breadcrumbs %}

{{ breadcrumbs([
    {"label": _("Dashboard"), "href": url_for('backoffice.dashboard')},
    {"label": assembly.title}
]) }}
```

**Features:**
- Last item automatically non-clickable (current page)
- Chevron separators
- Semantic tokens: `--color-tables-cards`, `--color-borders-dividers`, `--color-secondary-text`, `--color-body-text`
- Accessibility: `aria-label="Breadcrumb"`, `aria-current="page"`, `aria-hidden` on chevrons

---

## Migration Pattern

When migrating a GOV.UK page to backoffice:

1. **Change base template:**
   ```jinja
   {% extends "backoffice/base.html" %}
   ```

2. **Import components:**
   ```jinja
   {% from "backoffice/components/navigation.html" import navigation %}
   {% from "backoffice/components/breadcrumbs.html" import breadcrumbs %}
   {% from "backoffice/components/footer.html" import footer %}
   {% from "backoffice/components/button.html" import button %}
   ```

3. **Replace GOV.UK breadcrumbs:**
   ```jinja
   {# Old: GOV.UK breadcrumbs #}
   <div class="govuk-breadcrumbs">
       <ol class="govuk-breadcrumbs__list">
           <li class="govuk-breadcrumbs__list-item">
               <a class="govuk-breadcrumbs__link" href="...">Dashboard</a>
           </li>
       </ol>
   </div>

   {# New: Backoffice breadcrumbs #}
   {{ breadcrumbs([
       {"label": _("Dashboard"), "href": url_for('backoffice.dashboard')},
       {"label": "Current Page"}
   ]) }}
   ```

4. **Replace GOV.UK typography:**
   ```jinja
   {# Old #}
   <h1 class="govuk-heading-l">Title</h1>
   <p class="govuk-body">Text</p>

   {# New #}
   <h1 class="text-display-lg" style="color: var(--color-headings);">Title</h1>
   <p class="text-body-lg" style="color: var(--color-body-text);">Text</p>
   ```

5. **Replace GOV.UK summary lists:**
   ```jinja
   {# Old #}
   <dl class="govuk-summary-list">
       <div class="govuk-summary-list__row">
           <dt class="govuk-summary-list__key">Label</dt>
           <dd class="govuk-summary-list__value">Value</dd>
       </div>
   </dl>

   {# New #}
   <dl class="rounded-lg p-6" style="background-color: var(--color-tables-cards); border: 1px solid var(--color-borders-dividers);">
       <div class="flex flex-col sm:flex-row sm:gap-4 py-3" style="border-bottom: 1px solid var(--color-borders-dividers);">
           <dt class="text-body-md font-medium sm:w-48" style="color: var(--color-secondary-text);">Label</dt>
           <dd class="text-body-md" style="color: var(--color-body-text);">Value</dd>
       </div>
   </dl>
   ```

6. **Replace GOV.UK buttons:**
   ```jinja
   {# Old #}
   <a href="..." class="govuk-button">Edit</a>

   {# New #}
   {{ button(_("Edit"), href=url_for('...'), variant="primary") }}
   ```

7. **Update routes:**
   - Create matching route in `src/opendlp/entrypoints/backoffice/routes.py`
   - URL pattern: `/backoffice/<resource>/<action>`

---

## Testing

All migrated pages have BDD tests in `tests/bdd/test_backoffice.py` and `features/backoffice.feature`:

- Dashboard: ✅ Tested (assemblies display, cards, footer)
- Assembly Details: ✅ Tested (navigation, breadcrumbs, content, edit button)
- Edit Assembly: ✅ Tested (form fields, save/cancel, update functionality)

---

## TODO / Next Steps

### Assembly Page Migration

- [ ] Migrate Data & Selection tab
- [ ] Migrate Team Members tab
- [ ] Create tab navigation component
- [ ] Create badge component (for status display)
- [ ] Create table component (for registrants/selection runs)
- [ ] Create pagination component

### Other Pages

- [x] Edit Assembly page
- [ ] Create Assembly page
- [ ] User profile pages
- [ ] Admin pages

---

## Notes

- **Footer version display:** Currently uses `{{ opendlp_version }}` from context processor. See TODO in `backoffice_design_system.md`.
- **Navigation conditional items:** Uses `isVisible` prop for role-based visibility.
- **Navigation attribute passthrough:** Any non-reserved attributes on nav items are passed to anchor tags (e.g., `target="_blank"`).
- **Breadcrumbs last item:** Always non-clickable, represents current page.

---

## References

- **Design System Documentation:** `backend/docs/backoffice_design_system.md`
- **Component Showcase:** `/backoffice/showcase`
- **Original GOV.UK Pages:** `templates/main/view_assembly_*.html`
