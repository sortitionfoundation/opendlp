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
| Tabs | `components/tabs.html` | ARIA roles, keyboard nav, roving tabindex, focus preservation |
| Button | `components/button.html` | `aria-label`, `aria-pressed`, `aria-haspopup`, `aria-expanded`, `aria-describedby`, `role="button"` on links |

## Common Mistakes to Avoid

1. **Using `outline: none` without replacement** - Always provide visible focus
2. **Forgetting `aria-label` on icon buttons** - Screen readers need text
3. **Changing toggle button labels based on state** - Keep label constant, use `aria-pressed`
4. **Using `tabindex > 0`** - Disrupts natural tab order; use DOM order instead
5. **Forgetting to update `aria-expanded`** - Must reflect current state
6. **Links that behave like buttons** - Add `role="button"` or use `<button>`
7. **Custom focus styles with poor contrast** - Prefer browser defaults
