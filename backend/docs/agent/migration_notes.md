# Migration Notes: Bootstrap to GOV.UK

This document provides guidance for converting Bootstrap components to GOV.UK Design System components.

## Grid System

**Bootstrap → GOV.UK:**
- `row` → `govuk-grid-row`
- `col-*` → `govuk-grid-column-*`
- `col-12` → `govuk-grid-column-full`
- `col-8` → `govuk-grid-column-two-thirds`
- `col-4` → `govuk-grid-column-one-third`
- `col-6` → `govuk-grid-column-one-half`

## Buttons

**Bootstrap → GOV.UK:**
- `btn` → `govuk-button`
- `btn-primary` → `govuk-button` (default is primary)
- `btn-secondary` → `govuk-button--secondary`
- `btn-success` / `btn-info` / etc. → Use appropriate `govuk-button` with custom classes if needed

## Cards

**Bootstrap cards must be replaced with custom styled components:**
- Use `govuk-!-margin-*` and `govuk-!-padding-*` utilities
- Create custom classes like `assembly-card` or `feature-card`
- Use GOV.UK summary lists for structured data

## Spacing Utilities

**Bootstrap → GOV.UK:**
- `mt-3`, `mb-3`, etc. → `govuk-!-margin-top-3`, `govuk-!-margin-bottom-3`, etc.
- `pt-3`, `pb-3`, etc. → `govuk-!-padding-top-3`, `govuk-!-padding-bottom-3`, etc.

GOV.UK spacing scale:
- 0-9 for standard spacing
- Use responsive spacing where needed

## Custom Styling

- Always use Sortition Foundation color palette from `_sortition.scss`
- Never inline styles; use SCSS variables and classes
- Ensure all custom styles are in `src/scss/` directory
- Test mobile navigation across Chrome and Firefox

## CSS Specificity

- GOV.UK styles are well-scoped and shouldn't conflict
- If you need to override, be specific with selectors
- Avoid `!important` unless absolutely necessary
- Document any overrides with comments explaining why

## Cross-Browser Testing

- Chrome and Firefox handle mobile navigation slightly differently
- Test hamburger menu functionality on both browsers
- Verify focus states are visible with saffron-yellow highlighting
- Ensure ARIA labels and roles are correct for screen readers
