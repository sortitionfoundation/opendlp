# Frontend Design System

## GOV.UK Design System with Sortition Foundation Branding

This project uses the GOV.UK Frontend framework v5.11.1 with custom Sortition Foundation styling. The design system is built using Sass/SCSS compilation.

## Key Files

- `src/scss/application.scss` - Main SCSS file importing govuk-frontend and custom styles
- `src/scss/_sortition.scss` - Sortition Foundation color palette variables
- `static/css/application.css` - Compiled CSS output (never edit directly)

## Build Pipeline

CSS must be built using npm/Sass before running the application:

```bash
# Build CSS once
just build-css
# or: npm run build:sass

# Watch and rebuild CSS on changes
just watch-css
# or: npm run watch:sass

# Build and run application
just run  # Automatically builds CSS first
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
<script src="https://cdn.jsdelivr.net/npm/govuk-frontend@5.11.1/dist/govuk/all.bundle.min.js"></script>
<script>
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
