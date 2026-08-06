# Radio Button Component — Design Specification

> Source: Figma file "OpenDLP / UI", page "Radio", component set "Radio button"
> Design tokens: TailwindCSS (Auto Default mode)

---

## ANATOMY

Container (row wrapper):

- Flow: Horizontal (flexbox row), vertically centered
- Gap: 8px (between circle and label)
- Width: Hug content (auto-sizes to content)
- Height: Hug content (resolves to ~20px with 16px circle + alignment)

Radio Circle (the interactive outer ring):

- Width: 16px (spacing/4)
- Height: 16px (spacing/4)
- Border radius: 9999px / 50% (radius/full — fully rounded circle)
- Flow: Vertical (for centering the inner dot inside)
- Contains: inner filled dot when selected (10×10px / spacing/2.5)

Inner Dot (the selection indicator, visible when selected only):

- Width: 10px (spacing/2.5)
- Height: 10px (spacing/2.5)
- Shape: Circle (ellipse, fully rounded)
- Color: brand-400 (#90003F)
- Centered within the 16×16px outer circle

Label Text:

- Font family: Lato
- Font weight: 500 (Medium)
- Font size: 14px
- Line height: 20px
- Letter spacing: 0.3px
- Color: neutrals-700 (#2F3442)

---

### STATE 1: DEFAULT (Unselected)

Selected: false, Disabled: false

- Circle background: theme/background (#FFFFFF — white)
- Circle border: 1px solid brand-400 (#90003F), inner alignment
- Inner dot: not visible / not rendered
- Label color: neutrals-700 (#2F3442)
- Opacity: 100%
- Cursor: pointer

---

### STATE 2: SELECTED (Checked)

Selected: true, Disabled: false

- Circle background: theme/background (#FFFFFF — white)
- Circle border: 1px solid brand-400 (#90003F), inner alignment
- Inner dot: brand-400 (#90003F) filled circle, 10×10px (spacing/2.5), centered in the outer circle
- Label color: neutrals-700 (#2F3442)
- Opacity: 100%
- Cursor: pointer

---

### STATE 3: DEFAULT_DISABLED (Unselected + Disabled)

Selected: false, Disabled: true

- Identical to DEFAULT state visually, but:
- Opacity: 50% (applied to entire row: circle + label)
- Cursor: not-allowed
- Pointer events: none

---

### STATE 4: SELECTED_DISABLED (Selected + Disabled)

Selected: true, Disabled: true

- Identical to SELECTED state visually, but:
- Opacity: 50% (applied to entire row: circle + label)
- Cursor: not-allowed
- Pointer events: none

---

### COMPONENT PROPERTIES (Figma Component Props → Code Props)

The Figma component exposes these properties:

| Figma Property | Code Prop   | Type      | Default   | Description                              |
|----------------|-------------|-----------|-----------|------------------------------------------|
| Property 1     | selected    | boolean   | false     | Whether the radio button is selected     |
| (Disabled via variant) | disabled | boolean | false   | Whether the radio button is disabled     |
| (Label text)   | label       | string    | "Default" | Text shown next to the radio button      |
| —              | onChange    | (selected: boolean) => void | — | Callback when toggled       |
| —              | name        | string    | —         | Form field name (groups radios together) |
| —              | value       | string    | —         | Value submitted with the form            |
| —              | id          | string    | —         | Unique ID for label association          |
| —              | className   | string    | —         | Additional CSS class overrides           |

In Figma, the 4 states are represented as a Property 1 enum variant:

- Default → Selected=false, Disabled=false
- Selected → Selected=true, Disabled=false
- Default_disabled → Selected=false, Disabled=true
- Selected_disabled → Selected=true, Disabled=true

In code, use the two boolean props (selected, disabled) instead of a single variant enum.

---

### COMPONENT API (Suggested Props)

```tsx
interface RadioButtonProps {
  selected?: boolean;
  disabled?: boolean;
  label: string;
  onChange?: (value: string) => void;
  name?: string;
  value?: string;
  id?: string;
  className?: string;
}
```

For a radio group wrapper:

```tsx
interface RadioGroupProps {
  name: string;
  value?: string;
  onChange?: (value: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}
```

---

### KEY VISUAL DIFFERENCES FROM CHECKBOX

The radio button differs from the checkbox in these specific ways:

1. **Shape**: Radio uses `border-radius: 9999px` (radius/full — a perfect circle) instead of `border-radius: 4px` (radius/sm — rounded square).
2. **Selection indicator**: Radio uses an inner filled dot (10×10px brand-400 circle centered inside the 16×16px outer ring) instead of a checkmark icon.
3. **Selected background**: The radio outer circle background stays white (#FFFFFF) when selected; the checkbox fills entirely with brand-400. The radio conveys selection via the inner dot only.
4. **Mutual exclusivity**: Radio buttons within a group are mutually exclusive (only one can be selected at a time). Checkboxes are independent.
5. **No indeterminate state**: Radio buttons do not support an indeterminate/partial state.

---

### INNER DOT ELEMENT

The inner dot inside the selected radio circle:

- Component name in Figma: Circle
- Size: 10×10px (spacing/2.5)
- Shape: Ellipse (fully rounded circle)
- Color: brand-400 (#90003F) — solid fill
- Centered within the 16×16px outer circle
- Implementation: use a `<span>` or `<div>` with `border-radius: 50%`, `width: 10px`, `height: 10px`, `background-color: #90003F`, centered using flexbox on the parent.

Alternatively, use a CSS pseudo-element (`::after`) on the radio circle:

```css
.radio-circle::after {
  content: '';
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: var(--brand-400, #90003F);
  /* Hidden by default, shown when selected */
  transform: scale(0);
  transition: transform 150ms ease;
}

.radio-button.selected .radio-circle::after {
  transform: scale(1);
}
```

---

### IMPLEMENTATION NOTES

1. **Accessibility**: Use a native `<input type="radio">` visually hidden (sr-only), with a `<label>` wrapping the custom circle + text. This ensures keyboard navigation, screen reader support, and form compatibility. Radio buttons in a group must share the same `name` attribute.

2. **Disabled state**: Apply `opacity: 0.5` to the entire container (circle + label), not individually. Add `pointer-events: none` and `cursor: not-allowed`.

3. **Focus ring**: Add a visible `:focus-visible` ring around the radio circle for keyboard navigation. Use the same focus ring pattern from the Button and Checkbox components: `outline: 2px solid #90003F; outline-offset: 2px`.

4. **Transitions**: Add `transition: background-color 150ms ease, border-color 150ms ease, opacity 150ms ease, transform 150ms ease` for smooth state changes. The inner dot should animate in/out with a scale transform for a polished feel.

5. **Hover state (not in Figma, recommended for UX)**: On hover (when not disabled), slightly darken the border or add a subtle background change to the circle to indicate interactivity. Consider `brand-600 (#720046)` for the border on hover for the unselected state, or a light brand tint for the circle background.

6. **Token-based sizing**: Use CSS custom properties for all sizes to enable easy scaling:

```css
   --radio-size: 16px;          /* spacing/4 */
   --radio-dot-size: 10px;      /* spacing/2.5 */
   --radio-radius: 9999px;      /* radius/full */
   --radio-gap: 8px;            /* gap between circle and label */
```

7. **The Figma file uses TailwindCSS tokens (Auto Default mode)**. If using Tailwind, map the design tokens to your Tailwind config:

    - spacing/4 = `w-4 h-4` (16px)
    - spacing/2.5 = `w-2.5 h-2.5` (10px)
    - radius/full = `rounded-full` (9999px)
    - gap: 8px = `gap-2`
    - text-sm for 14px, font-medium for weight 500, leading-5 for 20px line-height
    - tracking-wide or custom `tracking-[0.3px]` for 0.3px letter spacing

8. **Color consistency**: The radio circle border and inner dot fill both use brand-400 (#90003F), the same color used for the checkbox border/fill, primary button background, and focus rings across the design system.

9. **Radio Group behavior**: Radio buttons should always be used in groups of 2 or more. Implement a `RadioGroup` wrapper component that:
    - Manages the selected value state
    - Passes `name`, `onChange`, and selection state down to child radio buttons
    - Supports `disabled` at the group level (disabling all children)
    - Uses `role="radiogroup"` for accessibility
    - Supports keyboard navigation: arrow keys to move between options, Space/Enter to select

10. **Form integration**: Ensure the native `<input type="radio">` is properly wired so the component works within `<form>` elements, including form submission and reset behavior.
