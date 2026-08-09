# Frontend Design System

## GOV.UK Design System with Sortition Foundation Branding

This project uses the GOV.UK Frontend framework v5.11.1 with custom Sortition Foundation styling. The design system is built using Sass/SCSS compilation.

## Key Files

- `src/scss/application.scss` - Main SCSS file importing govuk-frontend and custom styles
- `src/scss/_sortition.scss` - Sortition Foundation color palette variables
- `static/css/application.css` - Compiled CSS output (never edit directly)

## Build Pipeline

Frontend assets (CSS and JavaScript) must be built using npm before running the application.
There are three build tools: Dart Sass (GOV.UK CSS), Tailwind (backoffice CSS), and esbuild
(backoffice JavaScript bundles). See [Frontend Build](../frontend_build.md) for the full picture.

```bash
# Build everything (CSS + JS) once
just build-all
# or: npm run build

# Build CSS only
just build-css        # GOV.UK (npm run build:sass)
just build-backoffice # backoffice Tailwind (npm run build:backoffice)

# Build JS only
just build-js         # esbuild (npm run build:js)

# Watch and rebuild on changes
just watch-css        # or watch-backoffice / watch-js

# Build and run application
just run  # Automatically runs build-all first
```

## Sortition Foundation Color Palette

Custom color variables defined in `_sortition.scss`:

```scss
$hot-pink: #e91e63;
$burnt-orange: #ff7043;
$purple-red: #9c27b0;
$blood-red: #c62828;
$sap-green: #4caf50;
$woad-blue: #3f51b5;
$scarlet-red: #f44336;
$saffron-yellow: #ffeb3b;
$buttermilk: #f5f5dc;
$dark-grey: #424242;
$white: #ffffff;
```

## Backoffice Design Tokens

The backoffice (Tailwind) side uses CSS custom properties as design tokens:

- `static/backoffice/tokens/primitive.css` - raw palette (`--color-brand-400`, `--color-neutral-600`, spacing, fonts, radii, shadows)
- `static/backoffice/tokens/semantic.css` - purpose-based aliases (`--color-primary-action`, `--color-body-text`, `--color-links`, status colours)

Rules for using tokens in templates:

- **Every `var(--...)` referenced in a template must be defined in one of the two token files.** An undefined token is not an error - `var(--x)` with no fallback silently resolves to the inherited value, so links render in body-text colour and status banners lose their background. `tests/unit/test_design_tokens.py` enforces this in CI.
- Prefer semantic tokens over primitives (`--color-links`, not `--color-brand-400`).
- Never invent a token name in a template. If no existing token fits, add a semantic alias to `semantic.css` first.
- Status colours use a `100/400/600` scale (background/border/text), with purpose-named aliases `--color-{success,warning,error,info}-{background,text}`. There are no `-500`/`-700` shades - use `-400` for borders/strokes and `-600` for text.
- Links need an explicit colour (`--color-links` or `--color-link-text`) because the Tailwind preflight sets `a { color: inherit }`.

## HTML Template Requirements

All templates must extend `base.html` which includes:

### 1. Required CSS classes on body element

```html
<body class="govuk-template__body govuk-frontend-supported"></body>
```

### 2. CSS import (compiled, not CDN)

```html
<link
  rel="stylesheet"
  href="{{ url_for('static', filename='css/application.css') }}"
/>
```

### 3. JavaScript initialization

```html
<script
  nonce="{{ csp_nonce }}"
  src="{{ url_for('static', filename='js/vendor/govuk-frontend.js', v=static_hashes('js/vendor/govuk-frontend.js')) }}"
></script>
<script nonce="{{ csp_nonce }}">
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof window.GOVUKFrontend !== "undefined") {
      window.GOVUKFrontend.initAll();
    }
  });
</script>
```

## Accessibility Requirements

- All interactive elements must be keyboard accessible
- Color contrast ratios must meet WCAG standards
- Screen reader compatibility maintained
- Mobile navigation close button hidden but functional for assistive technology
- Focus styles use saffron-yellow highlighting
