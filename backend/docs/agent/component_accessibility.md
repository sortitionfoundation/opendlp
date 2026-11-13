# Component Accessibility Guidelines

This document defines accessibility requirements for all UX components in the backoffice design system. Follow these guidelines when creating new components or modifying existing ones.

## Core Principles

### 1. Semantic HTML First

Always use the most semantically appropriate HTML element:

- Use `<button>` for actions, not `<div>` or `<span>` with click handlers
- Use `<a>` for navigation to URLs, `<button>` for in-page actions
- Use `<nav>`, `<main>`, `<header>`, `<footer>` for page structure
- Use heading hierarchy (`<h1>` through `<h6>`) correctly
- Use `<ul>`/`<ol>` for lists, `<table>` for tabular data

**Rule:** If you need to add `role="button"` to make something accessible, consider using `<button>` instead.

### 2. WAI-ARIA Attributes

Add ARIA attributes when semantic HTML alone is insufficient:

#### Required ARIA for Common Patterns

| Pattern | Required Attributes |
|---------|---------------------|
| Icon-only button | `aria-label="Action description"` |
| Toggle button | `aria-pressed="true/false"` |
| Menu button | `aria-haspopup="menu"`, `aria-expanded="true/false"` |
| Expandable section | `aria-expanded="true/false"`, `aria-controls="panel-id"` |
| Tabs | `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected` |
| Breadcrumbs | `<nav aria-label="Breadcrumb">`, `<ol>`, `aria-current="page"` on current |
| Modal/Dialog | `role="dialog"`, `aria-modal="true"`, `aria-labelledby` |
| Loading state | `aria-busy="true"`, `aria-live="polite"` |
| Disabled elements | `aria-disabled="true"` (in addition to `disabled` attribute) |
| Descriptions | `aria-describedby="description-id"` |

#### ARIA Labels

- **`aria-label`**: Use when no visible text label exists (e.g., icon buttons)
- **`aria-labelledby`**: Use when the label text exists elsewhere in the DOM
- **`aria-describedby`**: Use for additional descriptions (e.g., error messages, hints)

**Warning:** `aria-label` is NOT translated by browser translation tools. Prefer visible text labels when possible.

### 3. Keyboard Navigation

All interactive elements MUST be keyboard accessible:

#### Focus Requirements

- Interactive elements must be focusable (`tabindex="0"` if not natively focusable)
- Focus order must be logical (follows DOM order or explicit `tabindex`)
- Focus must be visible (use browser default or ensure sufficient contrast)
- Focus must not be trapped (except in modals)

#### Keyboard Patterns by Component

| Component | Keys | Behavior |
|-----------|------|----------|
| Button | `Enter`, `Space` | Activate |
| Link | `Enter` | Navigate |
| Tabs | `Arrow Left/Right` | Move between tabs |
| Tabs | `Home/End` | Jump to first/last tab |
| Menu | `Arrow Up/Down` | Navigate items |
| Menu | `Escape` | Close menu |
| Modal | `Escape` | Close modal |
| Modal | `Tab` | Cycle focus within modal |

#### Roving Tabindex

For composite widgets (tabs, menus), use roving tabindex:
- Only one item has `tabindex="0"` (the active/selected item)
- Other items have `tabindex="-1"`
- Arrow keys move focus and update tabindex values

### 4. Focus Visibility

Focus indicators must be clearly visible:

- **Prefer browser defaults** - They are familiar to users and work across themes
- If customizing, ensure:
  - Minimum 2px outline
  - Sufficient contrast (3:1 against adjacent colors)
  - No `outline: none` without replacement
- Use `:focus-visible` for keyboard-only focus (not mouse clicks)

### 5. Focus Preservation

When page content changes (navigation, AJAX updates):

- Preserve focus position after page reload when navigating via keyboard
- Return focus to trigger element when closing modals/dialogs
- Move focus to new content when dynamically inserted (e.g., form errors)

## Component Checklist

Before completing work on any component, verify:

### Semantic Structure
- [ ] Uses appropriate HTML elements (not divs with roles)
- [ ] Has accessible name (visible text, `aria-label`, or `aria-labelledby`)
- [ ] Disabled state uses both `disabled` attribute and `aria-disabled="true"`

### Keyboard Accessibility
- [ ] All interactive elements are focusable
- [ ] Focus order is logical
- [ ] Expected keyboard shortcuts work (Space/Enter for buttons, arrows for composite widgets)
- [ ] Focus is visible when element receives focus

### ARIA Compliance
- [ ] Required ARIA attributes are present (see table above)
- [ ] `aria-label` values describe the action, not the element type
- [ ] Dynamic states (`aria-expanded`, `aria-pressed`, etc.) update correctly
- [ ] `aria-describedby` used for supplementary information

### Testing
- [ ] Navigate component using only keyboard (Tab, arrows, Enter, Space, Escape)
- [ ] Verify focus visibility on all interactive elements
- [ ] Test with screen reader if available (VoiceOver on macOS: Cmd+F5)

## Research Requirements

When implementing complex patterns (tabs, menus, dialogs, carousels, etc.):

1. **Consult WAI-ARIA Authoring Practices Guide**: https://www.w3.org/WAI/ARIA/apg/patterns/
2. **Check MDN for ARIA roles**: https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Roles
3. **Review GOV.UK Design System**: https://design-system.service.gov.uk/components/ (our design basis)

Document any deviations from standard patterns with rationale.

## Existing Component Reference

Components with accessibility support implemented:

| Component | Location | A11y Features |
|-----------|----------|---------------|
| Tabs | `components/tabs.html` | ARIA roles, keyboard nav, roving tabindex, focus preservation, scroll preservation |
| Breadcrumbs | `components/breadcrumbs.html` | `<nav>` landmark with `aria-label`, semantic `<ol>` list, `aria-current="page"`, CSS-based separators |
| Button | `components/button.html` | `aria-label`, `aria-pressed`, `aria-haspopup`, `aria-expanded`, `aria-describedby`, `role="button"` on links |
| Search Dropdown | `components/search_dropdown.html` | WAI-ARIA combobox pattern: `role="combobox/listbox/option"`, `aria-expanded`, `aria-activedescendant`, `aria-selected`, live region for results count, keyboard nav (arrows/enter/escape) |
| Select Dropdown | `components/select_dropdown.html` | Native `<select>` with built-in a11y, `aria-describedby` for hints/errors, `aria-required`, `aria-invalid`, `aria-disabled`, keyboard nav (arrows/enter/space/escape/type-ahead) |
| Formatting toolbar | `components/rich_editor.html`, `src/js/backoffice/rich-editor-toolbar.js` | WAI-ARIA toolbar pattern: `role="toolbar"` with `aria-label` and `aria-controls`, one Tab stop with roving tabindex (arrows, Home/End), `aria-pressed` on toggles kept in step with the selection. Each button is a Lucide icon plus its label in a span that is visually hidden until hover or keyboard focus shows it as a tooltip - so the accessible name is real translated text, not an `aria-label`. The tooltip is a child of the button (hovering it keeps it open) and the first Escape hides it without closing the surrounding dialog (WCAG 1.4.13). Unavailable commands use `aria-disabled` without `disabled` so they stay in the arrow-key order - a deliberate departure from the checklist's "both attributes" rule. Buttons keep the editor's selection by cancelling `mousedown`. The Table button is a WAI-ARIA menu button (`aria-haspopup="menu"`, `aria-expanded`, `aria-controls`): it is one stop in the toolbar's arrow-key order, Enter/Space/Down open the menu on its first item and Up on its last, arrows and Home/End move between items, Escape closes it and returns to the button without closing the dialog, Tab closes it. **Alt+F10** moves from the text to the toolbar without moving the cursor, because inside a table Tab and Shift+Tab move between cells; they leave the table from its first and last cells, so the editor never traps focus. |
| Info icon (toggletip) | `components/info_icon.html`, `src/js/components/info-toggletip.js` | A toggletip after Heydon Pickering's (*Inclusive Components*), not a tooltip: a tooltip needs hover or focus, and touch has neither. The circled i is a real `<button type="button">` named "More about <thing>" (the `about` argument; "More information" without it). Activating it shows the text in a bubble and puts it in an always-present `role="status"` region a moment later, so it is announced, and announced again each time it is reopened. The bubble is `aria-hidden` so the text is not read twice, and `popover="manual"` so it renders in the top layer and no `overflow:hidden` card clips it; the component positions it under the icon, or above it when there is no room. Clicking again, Escape (stopped there, so an enclosing dialog stays open, with focus back on the button), a click elsewhere or tabbing away hides it. The bubble keeps the text in the DOM, so a control can point `aria-describedby` at its `id`. Without JavaScript the text is the button's `title`, which the component removes once it is running. |
| Fragment dialog (HTMX) | `src/js/init/fragment-dialog-focus.js`, `dialog-escape.js` | Mark the element the dialog is swapped into with `data-fragment-dialog-host`. Focus moves into the dialog on open (first control in `.dialog-body`, or `data-dialog-initial-focus`), stays on the same control through a re-render, and returns to the opener on close - give the opener a `data-focus-id`, and its row a `data-focus-row` if menu items or forms in the row open dialogs too. The host's siblings are `inert` while a dialog is open. The full-screen backdrop link is `tabindex="-1" aria-hidden="true"`: a pointer affordance only, since the X and Escape serve keyboard users. |
| Wizard in a dialog | `backoffice/data_source/_dialog.html`, `entrypoints/blueprints/data_source.py` | Create new project: three steps in one fragment dialog, each drawn by the server. The stepper shows progress and is not navigation - every step is a non-focusable span (`stepper(mode="wizard", disabled=true)`), the current one carrying `aria-current="step"`, done ones a visually hidden "(completed)". Back and Next are the only way to move; Back is not a submit button, because on the last step submitting saves. No button has an `id` or a `name`, so after each redraw the dialog host cannot find the control that had focus and sends it to the new step's first field, or to the field marked `data-dialog-initial-focus` when a value was refused (`aria-invalid`, with the reason beside it). The X, Cancel and the backdrop are links, which Escape follows; until the project exists they ask before discarding what was typed (`dialogLeaveGuard`), and once it exists Cancel reads Close. The two CSV panels are shown and hidden by the dropdown above each (`x-show`), and are plain sections named by their headings. |
| Edit in place | `components/inline_edit_row.html` (`inline_edit_row`), `src/js/components/inline-edit.js` | One value of a details list edited where it is shown, as the project details design draws it: the names on My account (`profile/_name_row.html`) and the title, question, panel size and first event date of a project. `kind` picks the control - text, textarea, number or date. In a textarea Enter adds a line, so Ctrl+Enter (Cmd+Enter) saves; everything else is the same. With `editable=false` the row is the value alone, with no form and no pencil, for someone who may read it but not change it. At rest the value is text and the row ends in an icon button named "Edit <thing>" (the pencil). Pressing it swaps the text for the input, focused with its text selected, and the pencil for a submit button named "Save <thing>" (the tick) and a button named "Cancel editing <thing>" (the red X). The row's `<dt>` holds the input's `<label>`. Enter or the tick saves; Escape or the X puts the stored value back and returns focus to the pencil; leaving the row - Tab, or a click elsewhere - saves and leaves focus where it went. The tick and the X cancel their `mousedown`, so pressing them never takes focus from the input: Safari focuses no pressed button, and the input blurring to the page would count as leaving the row, which saves. A value that has not changed is not sent. htmx swaps the server's answer in for the row, so after a save made from inside the row the answer carries `autofocus` on the pencil and the keyboard user keeps their place; a refused value comes back open with the input focused, `aria-invalid` and `aria-describedby` pointing at the reason. A save that fails outright (network, server error) keeps the input open and says so in a `role="alert"` line under it. Switching to another window is not leaving the row. |

## Common Mistakes to Avoid

1. **Using `outline: none` without replacement** - Always provide visible focus
2. **Forgetting `aria-label` on icon buttons** - Screen readers need text
3. **Changing toggle button labels based on state** - Keep label constant, use `aria-pressed`
4. **Using `tabindex > 0`** - Disrupts natural tab order; use DOM order instead
5. **Forgetting to update `aria-expanded`** - Must reflect current state
6. **Links that behave like buttons** - Add `role="button"` or use `<button>`
7. **Custom focus styles with poor contrast** - Prefer browser defaults
