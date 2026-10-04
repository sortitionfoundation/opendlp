---
name: ui-components
description: Prerequisites for creating or modifying UI components, templates, or Alpine.js components - accessibility requirements and the CSP-compatible Alpine patterns. Load before touching any template, component, or Alpine.js code.
---

# ui-components

## Before creating or modifying UI components

Read the [Component Accessibility Guide](../../../docs/agent/component_accessibility.md). All components MUST comply with:

- Semantic HTML structure
- WAI-ARIA attributes (aria-label for icon buttons, aria-pressed for toggles, etc.)
- Keyboard navigation (focusable, logical tab order, expected shortcuts)
- Visible focus indicators (prefer browser defaults)

Research complex patterns at https://www.w3.org/WAI/ARIA/apg/patterns/ before implementation.

## Before implementing Alpine.js components

Check the interactive patterns documentation at `/backoffice/dev/patterns` (dev only) or read the template at `templates/backoffice/patterns.html`. This documents CSP-compatible patterns for dropdowns, forms, and AJAX with working examples and links to existing implementations. Key constraints:

- `x-model` must use flat properties (`x-model="selected"` not `x-model="form.field"`)
- `@click` handlers cannot have string arguments (`@click="doThing()"` not `@click="doThing('arg')"`)
- AJAX requests must include `X-CSRFToken` header

The `patterns.html` page is canonical and maintained as a reference. The dev blueprint that serves it (`src/opendlp/entrypoints/blueprints/dev.py`) is **not** a pattern source - it is a dev-only scratch space held to a lower bar, with partial test coverage by design. Don't copy production code from it; see the note at the top of that file for where the real examples are.
