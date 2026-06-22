# Registration Page — Split Button for Status Controls

**Date:** 2026-05-29 (updated 2026-06-01)
**Status:** Wired into `assembly_registration.html` for PUBLISHED and CLOSED states. Browser keyboard-flow verification still pending.

## Problem

The button cluster on the registration editor was confusing in two ways:

1. **"Close" was ambiguous.** Editors read it as "close the editor UI" rather than "close the form to new submissions."
2. **Two-dimensional lifecycle, one row of buttons.** From the PUBLISHED state the row showed *Unpublish + Close + Save and Republish*. A normal user has to remember that "Unpublish" goes back to TEST (form still visible, banner says test mode), while "Close" → CLOSED (visitors see a "registration closed" page). Both labels read like "make it stop." Forcing a user to hold both axes in their head defeats the lifecycle metaphor.

The form lifecycle has TEST ⇄ PUBLISHED bidirectional, but CLOSED only goes forward:

```
TEST  ⇄  PUBLISHED  ⇄  CLOSED
              ↑__________|
```

`unpublish_registration_page()` only accepts pages in the PUBLISHED state — there is no `CLOSED → TEST` transition. From CLOSED the only forward move is `reopen` (back to PUBLISHED).

## Decisions

### 1. Rename "Close" → "Stop Accepting Submissions"

Chosen over "Close Registration" and "End Registration" because it puts the *behaviour* in the label: existing form stays visible, new submissions are blocked. This is the action editors need to recognise without reading docs.

Applied to `templates/backoffice/assembly_registration.html:132` and the matching service-docs mockup at `templates/backoffice/service_docs/_registration.html:134`.

### 2. Replace the cluster with a split button

A *split button* — one primary action joined to a chevron dropdown — collapses the row to a single primary CTA per state. The forward step (or the obvious next step) is always primary; the rewind/recovery step is one click away in the menu.

**Mapping by state:**

| State        | Primary button                  | Dropdown menu                |
|--------------|---------------------------------|------------------------------|
| `TEST`       | `Publish`                       | _(empty — single button, no dropdown needed)_ |
| `PUBLISHED`  | `Stop Accepting Submissions`    | `Back to Test`               |
| `CLOSED`     | `Accept Submissions Again`      | _(empty — `CLOSED → TEST` is not a valid transition)_ |

The independent `Save` / `Save and Republish` button stays — it is orthogonal to the status transitions.

### 3. Stepper considered and dropped

We discussed adding a `TEST → PUBLISHED → CLOSED` stepper above the buttons to visualise the lifecycle. Rejected (for now) because the split-button label already communicates the next step, and the stepper adds chrome without much extra signal. Easy to add later if testing shows users still get lost.

## Resolved decisions

- **`Reopen` label → `Accept Submissions Again`** (decided 2026-06-01). Chosen over `Resume Accepting Submissions` because it reads more naturally in English even though it breaks the exact mirror with `Stop Accepting Submissions`. The action value (`reopen`) is unchanged — only the label.

## Component implementation

**New file:** `templates/backoffice/components/split_button.html`

Macro signature:

```jinja
{{ split_button(
    primary_text=_("Stop Accepting Submissions"),
    primary_attrs='name="action" value="close"',
    items=[
        { "text": _("Back to Test"), "attrs": 'name="action" value="unpublish"' },
    ],
    variant="secondary",          # "primary" | "secondary" | "danger"
    primary_type="submit",
    id="status-toggle",
    aria_label_menu=_("More actions"),
) }}
```

**Markup shape:** two `<button>` elements visually joined inside an `inline-flex` wrapper:

- Left: primary `<button type="submit">` with `primary_attrs` injected raw (so callers pass `name="action" value="close"` etc.). Rounded on the left only.
- Right: chevron toggle `<button type="button">` — opens the menu, `aria-haspopup="menu"`, `aria-expanded` bound to Alpine state. Rounded on the right only, with a faint left border to look like a divider.
- Menu: `role="menu"` containing one `<button role="menuitem" type="submit">` per item. Each menu item is also a form submit so the same form/handler picks up the new `action` value.

**Alpine.js (CSP-safe):**

- Inline `x-data="{ open: false }"` on the wrapper.
- Toggle: `@click="open = !open"`, `@click.outside="open = false"`.
- Wrapper: `@keydown.escape.window="open = false"` so Escape closes from anywhere.
- Menu items: `@click="open = false"` so the menu collapses when an action is fired.
- Menu item hover/focus highlighting: `@mouseenter/@mouseleave/@focus/@blur` set `$el.style.backgroundColor` against `--color-subtle-background-panels`. (Inline `onmouseover` would have violated CSP — `$el` is Alpine's reference to the current element and is CSP-safe.)

**Variants:** `primary`, `secondary`, `danger`. Internally maps to the same `--color-button-*` tokens and `btn-*-hover` classes used by the standard `button` macro, so the halves look native to the design system.

**Accessibility:**

- `aria-haspopup="menu"` + `x-bind:aria-expanded`
- `aria-controls` links toggle ↔ menu via the `id` prefix
- `aria-labelledby` on the menu points back at the toggle
- Toggle has an `aria-label` (default `_("More actions")`) because its only visible content is the chevron icon
- Visible focus outline via the existing `btn-focus` class

## Showcase

**New file:** `templates/backoffice/showcase/split_button_component.html` — three live demos:

1. Published-state pattern (secondary primary + `Back to Test` rewind)
2. Closed-state pattern (primary `Resume Accepting Submissions` + `Back to Test` rewind)
3. Multi-item primary example (`Save and Continue` + draft/save-close/discard menu)

Each example wraps in `<form @submit.prevent>` so the showcase doesn't actually navigate.

Wired into `templates/backoffice/showcase.html` directly after `button_section()` in the Components tab.

URL to verify: `http://127.0.0.1:5000/backoffice/showcase` → Components tab → Split Button.

## Outstanding work

1. Verify keyboard flow end-to-end in a browser (Tab into toggle → Enter opens → Tab to menu items → Escape closes) on the actual registration editor, not just the showcase.
2. Translate the new strings in `translations/hu/LC_MESSAGES/messages.po`: `Stop Accepting Submissions`, `Accept Submissions Again`. (`Back to Test` and `More actions` already have stub Hungarian values — review whether they're accurate.)

## Files / commits

- `feat(backoffice): add split button component and rename Close action` (commit `50596ce`)
  - `templates/backoffice/components/split_button.html` (new)
  - `templates/backoffice/showcase/split_button_component.html` (new)
  - `templates/backoffice/showcase.html` (registered the new section)
  - `templates/backoffice/assembly_registration.html` (Close → Stop Accepting Submissions)
  - `templates/backoffice/service_docs/_registration.html` (matching mockup label)
  - `translations/hu/LC_MESSAGES/messages.po` (regenerated; entries for `Stop Accepting Submissions` and `More actions` await translation)

## Related context

- `plan-613-public-routes.md` — public-facing route plan for the form itself (separate concern, mostly complete on this branch).
- Status-lifecycle service functions live in `src/opendlp/service_layer/registration_page_service.py` (`publish_*`, `unpublish_*`, `close_*`, `reopen_*`). The action values posted by the split-button menu (`unpublish`, `close`, `reopen`, `save`) map 1:1 to existing handlers in `_handle_registration_action()` at `src/opendlp/entrypoints/blueprints/backoffice.py:508` — no backend change needed when the split button is wired in.
