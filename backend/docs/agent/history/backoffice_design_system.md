## Backoffice Development

The backoffice uses a separate design system (Pines UI + Tailwind CSS) from the public-facing GOV.UK pages.

For feature-specific documentation showing these patterns in practice, see:
- [Assembly Module](backoffice_assembly.md) - CRUD, team members, access control

### Key Files

- **Routes:** `src/opendlp/entrypoints/backoffice/routes.py`
- **Templates:** `templates/backoffice/`
- **Components:** `templates/backoffice/components/` (Button, Card, Input, Navigation, Breadcrumbs, Footer, SearchDropdown macros)
- **Alpine.js Components:** `static/backoffice/js/alpine-components.js`
- **Design Tokens:** `static/backoffice/tokens/` (primitive.css, semantic.css)
- **Tailwind CSS:** `static/backoffice/src/main.css` → `static/backoffice/dist/main.css`

### Building CSS

```bash
# Build Tailwind CSS for backoffice
npm run build:backoffice

# Watch for changes during development
npm run watch:backoffice
```

### Component Showcase

Visit `/backoffice/showcase` to see all available components with usage examples.

### Using Components

```jinja
{# Import and use Button #}
{% from "backoffice/components/button.html" import button %}
{{ button("Click me", variant="primary") }}
{{ button("Cancel", variant="outline") }}

{# Import and use Card - simple (auto body) #}
{% from "backoffice/components/card.html" import card %}
{% call card(title="Card Title") %}
  Card content here
{% endcall %}

{# Card with footer (composed mode) #}
{% from "backoffice/components/card.html" import card, card_body, card_footer %}
{% call card(title="Card Title", composed=true) %}
  {% call card_body() %}
    Card content here
  {% endcall %}
  {% call card_footer() %}
    {{ button("Save", variant="primary") }}
  {% endcall %}
{% endcall %}

{# Import and use Input/Textarea #}
{% from "backoffice/components/input.html" import input, textarea %}
{{ input("email", label="Email Address", type="email", placeholder="you@example.com") }}
{{ input("title", label="Title", required=true, hint="A descriptive title for the assembly.") }}
{{ input("title", label="Title", value=form.title, error=errors.title) }}
{{ textarea("question", label="Assembly Question", rows=6, placeholder="What question will the assembly address?") }}
```

### Design Tokens

**Primitive tokens** define the raw color scales in `primitive.css`:

- **Brand scale** (pink/magenta/crimson): `--color-brand-50` through `--color-brand-800`
- **Neutral scale** (cool gray): `--color-neutral-0` through `--color-neutral-900`

**Semantic tokens** in `semantic.css` reference primitives by purpose:

| Token | Primitive | Usage |
|-------|-----------|-------|
| `--color-primary-action` | brand-400 | Primary buttons, CTAs |
| `--color-buttons-secondary` | brand-300 | Secondary buttons |
| `--color-active-states` | brand-500 | Active/selected states |
| `--color-page-background` | neutral-0 | Page background |
| `--color-tables-cards` | neutral-100 | Card backgrounds |
| `--color-borders-dividers` | neutral-200 | Borders, dividers |
| `--color-body-text` | neutral-600 | Body text |
| `--color-headings` | neutral-700 | Heading text |
| `--color-focus-ring` | brand-200 | Focus indicators |

### Typography

Fonts are self-hosted via `@fontsource` npm packages (no external Google Fonts CDN calls).

**Primitive layer** — CSS custom properties for font families in `primitive.css`:

```css
:root {
  --font-display: "Oswald", sans-serif;
  --font-heading: "Oswald", sans-serif;
  --font-body: "Lato", sans-serif;
  --font-caption: "Lato", sans-serif;
  --font-overline: "Lato", sans-serif;
  --font-label: "Lato", sans-serif;
  --font-button: "Lato", sans-serif;
}
```

**Semantic layer** — Tailwind utility classes in `main.css` (not CSS variables, because the `font` shorthand cannot include letter-spacing):

| Class | Weight | Size | Line Height | Family | Letter Spacing | Use Case |
|-------|--------|------|-------------|--------|----------------|----------|
| `.text-display-lg` | 500 | 2rem | 2.5rem | display | -0.32px | Page titles |
| `.text-display-md` | 500 | 1.75rem | 2.25rem | display | -0.28px | Section titles |
| `.text-display-sm` | 500 | 1.5rem | 2rem | display | -0.12px | Subsections |
| `.text-heading-lg` | 500 | 1.25rem | 1.75rem | heading | 0 | Card titles |
| `.text-heading-md` | 500 | 1.125rem | 1.5rem | heading | 0.18px | Panel headers |
| `.text-heading-sm` | 500 | 1rem | 1.375rem | heading | 0.24px | Group headers |
| `.text-body-lg` | 400 | 1rem | 1.5rem | body | 0 | Long-form text |
| `.text-body-md` | 400 | 0.875rem | 1.25rem | body | 0 | Default UI |
| `.text-body-sm` | 400 | 0.8125rem | 1.125rem | body | 0.13px | Dense UI |
| `.text-caption` | 400 | 1rem | 1.5rem | caption | 0 | Metadata |
| `.text-overline` | 500 | 0.6875rem | 0.875rem | overline | 0.88px | Uppercase labels |
| `.text-label-lg` | 500 | 0.875rem | 1.25rem | label | 0.28px | Form labels |
| `.text-label-md` | 500 | 0.8125rem | 1.125rem | label | 0.26px | Compact forms |
| `.text-button-lg` | 700 | 0.875rem | 1rem | button | 0.56px | Primary actions |
| `.text-button-md` | 700 | 0.8125rem | 1rem | button | 0.65px | Secondary actions |
| `.text-button-sm` | 700 | 0.75rem | 0.875rem | button | 0.72px | Toolbar buttons |

Example class definition in `main.css`:
```css
@layer components {
  .text-display-lg {
    font: 500 2rem/2.5rem var(--font-display);
    letter-spacing: -0.32px;
  }
}
```

Usage: `<h1 class="text-display-lg">Page Title</h1>`

No functional token layer (e.g. `--card-title`). Use semantic classes directly in components.

### Spacing Conventions

Spacing uses Tailwind's default scale (base unit: 4px). For visual consistency across components:

| Purpose | Tailwind Class | Value |
|---------|---------------|-------|
| Card/component padding | `p-6` | 1.5rem (24px) |
| Section gap (grid/flex) | `gap-6` | 1.5rem (24px) |
| Heading margin bottom | `mb-2` | 0.5rem (8px) |
| Paragraph margin bottom | `mb-4` | 1rem (16px) |
| Section margin bottom | `mb-8` | 2rem (32px) |
| Large section margin | `mb-24` | 6rem (96px) |
| Button padding | `px-4 py-2` | 1rem / 0.5rem |
| Inline element gap | `gap-2` | 0.5rem (8px) |
| Card header/footer padding | `px-6 py-4` | 1.5rem / 1rem |
| Card footer (compact) | `px-6 py-3` | 1.5rem / 0.75rem |

Prefer even multiples (`p-2`, `p-4`, `p-6`, `p-8`) for visual rhythm. When adapting Pines UI components into Jinja macros, normalize spacing to match these conventions.

### Responsive Layout

Container: `max-w-screen-2xl mx-auto px-6` (max 1536px, centered with padding).

| Breakpoint | Width | Columns | Use Case |
|------------|-------|---------|----------|
| Default | < 640px | 1 | Mobile |
| `sm` | ≥ 640px | 1 | Large phone |
| `md` | ≥ 768px | 2 | Tablet |
| `lg` | ≥ 1024px | 3 | Laptop |
| `xl` | ≥ 1280px | 4 | Desktop |
| `2xl` | ≥ 1536px | 4+ | Large monitor |

Standard responsive grid pattern:
```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
```

### Alpine.js

The backoffice uses Alpine.js (CSP-compatible build) for interactivity, loaded from jsdelivr CDN with an SRI integrity hash in `base.html`.

#### Reusable Components

Custom Alpine.js data components are defined in `static/backoffice/js/alpine-components.js` and registered on `alpine:init`. This separates logic (JavaScript) from presentation (Jinja macros).

| Component | Purpose | Jinja Macro |
|-----------|---------|-------------|
| `autocomplete` | Search dropdown with debounce, keyboard nav | `search_dropdown.html` |

**Pattern for adding new components:**

1. Add `Alpine.data("componentName", ...)` in `alpine-components.js`
2. Create Jinja macro in `templates/backoffice/components/`
3. Macro uses `x-data="componentName({options})"` to initialize
4. Add showcase section in `templates/backoffice/showcase/`

**Example - Autocomplete:**

```javascript
// alpine-components.js
Alpine.data("autocomplete", function(options) {
    return {
        query: "",
        results: [],
        isOpen: false,
        onInput: function() { /* debounced fetch */ },
        selectItem: function(item) { /* handle selection */ }
    };
});
```

```jinja
{# search_dropdown.html macro #}
<div x-data="autocomplete({ fetchUrl: '{{ fetch_url }}', minChars: 2 })">
    <input x-model="query" @input="onInput()">
    <ul x-show="isOpen">
        <template x-for="item in results">
            <li @click="selectItem(item)" x-text="item.label"></li>
        </template>
    </ul>
    <input type="hidden" name="{{ name }}" :value="selectedId">
</div>
```

See [Assembly Module](backoffice_assembly.md#alpinejs-patterns) for detailed usage examples.

**TODO:** Consider self-hosting Alpine.js instead of using CDN + integrity hash:
- The SRI hash is error-prone (a single character typo silently breaks Alpine.js)
- Hash must be manually updated when upgrading Alpine.js version
- Self-hosting would eliminate CDN dependency and SRI maintenance burden
- Download from npm (`@alpinejs/csp`) and serve from `static/backoffice/js/`
