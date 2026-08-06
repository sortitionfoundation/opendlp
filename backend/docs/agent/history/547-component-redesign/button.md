Redesign the button component in our design system to match the following Figma specification from the OpenDLP UI kit. The button system has 4 variants (Primary, Secondary, Tertiary, Icon-only), each with Default and Hover states, plus a Focus ring treatment. Implement this as a reusable component (React + CSS/Tailwind or CSS variables — adapt to whatever framework the project uses).

---

### DESIGN TOKENS (Color Palette)

Use CSS custom properties (or your framework's equivalent) for these semantic tokens:

- `--color-brand-400`: #90003F (primary button default bg, focus ring border)
- `--color-brand-600`: #720046 (primary button hover bg)
- `--color-neutral-50`: #F7F7F8 (page/section background)
- `--color-neutral-200`: #E1E2E5 (hover bg for secondary, tertiary, and icon-only buttons)
- `--color-neutrals-700`: #2F3442 (secondary button border, secondary/tertiary text & icon color)
- `--color-white`: #FFFFFF (primary button text/icon color, secondary button default bg)

---

### SHARED BUTTON ANATOMY

Every button (except icon-only) is composed of three optional slots arranged horizontally:

1. **Leading icon** (optional) — 16×16px, instance-swappable (e.g., "edit" pencil icon)
2. **Label** — text content
3. **Trailing icon** (optional) — 16×16px, instance-swappable (e.g., "chevron_forward" rotated −90° to form a dropdown caret)

Layout:
- Flow: Horizontal (flexbox row), vertically centered
- Gap between slots: 8px
- Width: Hug content (auto), or can be set to Fixed
- Height: Hug content, resolves to 40px with the given padding + 16px line-height

---

### TYPOGRAPHY (all button labels)

- Font family: Lato
- Font weight: 600 (SemiBold)
- Font size: 14px
- Line height: 16px
- Letter spacing: 0.4px

---

### VARIANT 1: PRIMARY BUTTON

**Default state:**
- Background: brand-400 (#90003F)
- Border: none
- Border radius: 4px
- Padding: 12px top, 16px right, 12px bottom, 16px left
- Text color: white (#FFFFFF)
- Icon color: white (#FFFFFF)

**Hover state:**
- Background: brand-600 (#720046)
- All other properties same as default

---

### VARIANT 2: SECONDARY BUTTON

**Default state:**
- Background: white (#FFFFFF)
- Border: 1px solid neutrals-700 (#2F3442), inner alignment
- Border radius: 4px
- Padding: 12px top, 16px right, 12px bottom, 16px left
- Text color: neutrals-700 (#2F3442)
- Icon color: neutrals-700 (#2F3442)

**Hover state:**
- Background: neutral-200 (#E1E2E5)
- Border: 1px solid neutrals-700 (#2F3442)
- All other properties same as default

---

### VARIANT 3: TERTIARY (GHOST) BUTTON

**Default state:**
- Background: transparent (none)
- Border: none
- Border radius: 4px
- Padding: 12px top, 16px right, 12px bottom, 16px left
- Text color: neutrals-700 (#2F3442)
- Icon color: neutrals-700 (#2F3442)

**Hover state:**
- Background: neutral-200 (#E1E2E5)
- All other properties same as default

---

### VARIANT 4: ICON-ONLY BUTTON

**Default state:**
- Background: transparent (none)
- Border: none
- Border radius: 4px
- Padding: 12px top, 8px right, 12px bottom, 8px left
- Contains only a single 16×16px icon (e.g., "edit" pencil), no label, no trailing icon
- Icon color: neutrals-700 (#2F3442)
- Resolves to 40×40px (square)

**Hover state:**
- Background: neutral-200 (#E1E2E5)
- All other properties same as default

---

### FOCUS RING (applies to all variants on focus/focus-visible)

When focused, the button is wrapped in a visual focus indicator:
- Outer container padding around the button: 4px
- Border: 2px solid brand-400 (#90003F)
- Border radius: 8px (larger than the button's 4px to accommodate the offset)
- Total focused element height: ~48px (40px button + 4px padding top/bottom)

Implementation: Use a `box-shadow` or `outline` with offset, or a pseudo-element wrapper. Prefer `outline` + `outline-offset` for accessibility:
- `outline: 2px solid #90003F`
- `outline-offset: 4px`
- `border-radius: 8px` (use a pseudo-element if outline-radius isn't supported)

---

### COMPONENT API (Props)

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `variant` | `"primary" \| "secondary" \| "tertiary" \| "icon"` | `"primary"` | Visual style variant |
| `children` / `label` | `string` | — | Button label text (not used for icon variant) |
| `leadingIcon` | `ReactNode \| IconName` | `undefined` | Optional 16×16 icon before the label |
| `trailingIcon` | `ReactNode \| IconName` | `undefined` | Optional 16×16 icon after the label (e.g., dropdown caret) |
| `icon` | `ReactNode \| IconName` | `undefined` | Icon for icon-only variant |
| `disabled` | `boolean` | `false` | Disabled state (reduce opacity to ~0.5, remove pointer events) |
| `onClick` | `() => void` | — | Click handler |
| `type` | `"button" \| "submit" \| "reset"` | `"button"` | HTML button type |
| `fullWidth` | `boolean` | `false` | If true, button stretches to 100% container width |
| `as` | `"button" \| "a"` | `"button"` | Render as anchor for link-style buttons |
| `className` | `string` | — | Additional CSS class overrides |

---

### IMPLEMENTATION NOTES

1. All icons are 16×16px and should inherit their color from the button variant (white for primary, neutrals-700 for everything else).
2. The component should use CSS custom properties referencing the design tokens above, making theme changes easy.
3. Ensure keyboard accessibility: visible focus ring on Tab navigation (`:focus-visible`), not on mouse click.
4. Add `cursor: pointer` on interactive states, `cursor: not-allowed` on disabled.
5. Use `transition: background-color 150ms ease, border-color 150ms ease` for smooth hover transitions.
6. The trailing chevron icon in the Figma design is "chevron_forward" rotated −90° (pointing downward), used as a dropdown indicator.
7. The component name in Figma is "button primary" — reused across all variants with different styling overrides. In code, use a single `<Button>` component with a `variant` prop.
8. The Figma file uses a "Variable collection" and "Tokens" mode system (Auto / Mode 1), suggesting the design supports theming. Structure CSS variables to allow easy dark-mode or theme switching.
