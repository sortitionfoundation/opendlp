**Container (row wrapper):**
- Flow: Horizontal (flexbox row), vertically centered
- Gap: 8px (between box and label)
- Width: Hug content (auto-sizes to content)
- Height: Hug content (resolves to ~20px with 16px box + alignment)

**Checkbox Box (the interactive square):**
- Width: 16px (`spacing/4`)
- Height: 16px (`spacing/4`)
- Border radius: 4px (`radius/sm`)
- Flow: Vertical (for centering the checkmark inside)
- Contains: checkmark icon when checked (12×12px / `spacing/3`)

**Label Text:**
- Font family: Lato
- Font weight: 500 (Medium)
- Font size: 14px
- Line height: 20px
- Letter spacing: 0.3px
- Color: neutrals-700 (#2F3442)

---

### STATE 1: DEFAULT (Unchecked)
`Checked: false, Disabled: false`

- Box background: theme/background (#FFFFFF — white)
- Box border: 1px solid brand-400 (#90003F), inner alignment
- Checkmark: not visible / not rendered
- Label color: neutrals-700 (#2F3442)
- Opacity: 100%
- Cursor: pointer

---

### STATE 2: SELECTED (Checked)
`Checked: true, Disabled: false`

- Box background: brand-400 (#90003F) — filled solid
- Box border: 1px solid brand-400 (#90003F), inner alignment
- Checkmark: white (#FFFFFF) check icon, 12×12px (`spacing/3`), centered in the box
- Label color: neutrals-700 (#2F3442)
- Opacity: 100%
- Cursor: pointer

---

### STATE 3: DEFAULT_DISABLED (Unchecked + Disabled)
`Checked: false, Disabled: true`

- Identical to DEFAULT state visually, but:
- **Opacity: 50%** (applied to entire row: box + label)
- Cursor: not-allowed
- Pointer events: none

---

### STATE 4: SELECTED_DISABLED (Checked + Disabled)
`Checked: true, Disabled: true`

- Identical to SELECTED state visually, but:
- **Opacity: 50%** (applied to entire row: box + label)
- Cursor: not-allowed
- Pointer events: none

---

### COMPONENT PROPERTIES (Figma Component Props → Code Props)

The Figma component exposes these properties:

| Figma Property | Code Prop   | Type      | Default  | Description                          |
|----------------|-------------|-----------|----------|--------------------------------------|
| Checked        | `checked`   | `boolean` | `false`  | Whether the checkbox is checked      |
| Disabled       | `disabled`  | `boolean` | `false`  | Whether the checkbox is disabled     |
| (Label text)   | `label`     | `string`  | `"Default"` | Text shown next to the checkbox   |
| —              | `onChange`  | `(checked: boolean) => void` | — | Callback when toggled |
| —              | `name`      | `string`  | —        | Form field name                      |
| —              | `id`        | `string`  | —        | Unique ID for label association       |
| —              | `className` | `string`  | —        | Additional CSS class overrides       |

In Figma, the 4 states are represented as a `Property 1` enum variant:
- `Default` → Checked=false, Disabled=false
- `Selected` → Checked=true, Disabled=false
- `Default_disabled` → Checked=false, Disabled=true
- `Selected_disabled` → Checked=true, Disabled=true

In code, use the two boolean props (`checked`, `disabled`) instead of a single variant enum.

---

### COMPONENT API (Suggested Props)
```tsx
interface CheckboxProps {
  checked?: boolean;
  disabled?: boolean;
  label: string;
  onChange?: (checked: boolean) => void;
  name?: string;
  id?: string;
  className?: string;
  indeterminate?: boolean; // optional: for tree/table partial selection
}
```

---

### CHECKMARK ICON

The checkmark inside the checked box:
- Component name in Figma: `check`
- Size: 12×12px (`spacing/3`)
- Color: white (#FFFFFF)
- Centered within the 16×16px box
- Implementation: use an inline SVG checkmark or an icon component. The SVG should be a simple check/tick path with `stroke: white` or `fill: white`.

Suggested SVG (12×12 viewBox):
```html
<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
  <path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

---

### IMPLEMENTATION NOTES

1. **Accessibility:** Use a native `<input type="checkbox">` visually hidden (sr-only), with a `<label>` wrapping the custom box + text. This ensures keyboard navigation, screen reader support, and form compatibility.

2. **Disabled state:** Apply `opacity: 0.5` to the entire container (box + label), not individually. Add `pointer-events: none` and `cursor: not-allowed`.

3. **Focus ring:** Add a visible `:focus-visible` ring around the checkbox box for keyboard navigation. Use the same focus ring pattern from the Button component: `outline: 2px solid #90003F; outline-offset: 2px`.

4. **Transitions:** Add `transition: background-color 150ms ease, border-color 150ms ease, opacity 150ms ease` for smooth state changes.

5. **Hover state (not in Figma, recommended for UX):** On hover (when not disabled), slightly darken the border or add a subtle background change to the box to indicate interactivity. Consider `brand-600` (#720046) for the border on hover for the unchecked state, or a lighter brand tint for the background.

6. **Token-based sizing:** Use CSS custom properties for all sizes to enable easy scaling:
```css
   --checkbox-size: 16px;       /* spacing/4 */
   --checkmark-size: 12px;      /* spacing/3 */
   --checkbox-radius: 4px;      /* radius/sm */
   --checkbox-gap: 8px;         /* gap between box and label */
```

7. **The Figma file uses TailwindCSS tokens (Auto Default mode).** If using Tailwind, map the design tokens to your Tailwind config:
    - `spacing/4` = `w-4 h-4` (16px)
    - `spacing/3` = `w-3 h-3` (12px)
    - `radius/sm` = `rounded` (4px)
    - `gap: 8px` = `gap-2`
    - `text-sm` for 14px, `font-medium` for weight 500, `leading-5` for 20px line-height

8. **Color consistency:** The checkbox border and checked fill both use `brand-400` (#90003F), the same color used for the primary button background and focus rings across the design system.

9. **Indeterminate state (optional enhancement):** While not shown in Figma, consider supporting an `indeterminate` prop that shows a horizontal dash (—) instead of a checkmark, useful for parent checkboxes in tree/table selection patterns. Use the same brand-400 fill with a white dash icon.
