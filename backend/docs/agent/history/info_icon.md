# Make `info_icon` readable without a mouse

**Status:** Done

First written up as future work during the review of `793-two-step-fields`, in
a file shared with the app-level error handlers
(now [`future_work/app_level_error_handlers.md`](../future_work/app_level_error_handlers.md)).

## Problem

`templates/backoffice/components/info_icon.html` carried its explanation in two
places: a `title` attribute (a hover tooltip) and `sr-only` text for screen
readers. The span wasn't focusable and had no toggle. So a sighted user on a
keyboard, or on a phone or tablet, had no way to read the text. The icon told
them something was explained, then didn't let them read it.

It's used in the target tables (`targets/category_block.html`,
`targets/bulk_edit_form.html`), by the `info` argument of `input()`,
`textarea()` and the options of `radio_group()` in `components/input.html`, and
on the registration hub, the registration pages list, the respondents status
filter and the target sources setup dialog.

## Proposal

Turn it into a **toggletip**: a real `<button type="button">` holding the icon,
with an accessible name ("More about <thing>"). Activating it shows the text in
a live region next to it, and Escape or a click elsewhere hides it. Heydon
Pickering's toggletip in *Inclusive Components* is the usual reference. The
WAI-ARIA APG tooltip pattern alone isn't enough, since a tooltip only appears on
hover or focus, and touch has neither.

It needs a small CSP-safe Alpine component plus a no-JS fallback. Drop the
`title` so desktop users don't see the text twice.

## What was built

- **The macro** (`templates/backoffice/components/info_icon.html`) renders a
  wrapper with `x-data="infoToggletip"`, a `<button type="button">`, an empty
  `role="status"` live region, and the bubble. It gains an `about` argument:
  the button is named `_("More about %(thing)s")` with it and
  `_("More information")` without. `input()`, `textarea()` and `radio_group()`
  pass their label; the table headings and other callers pass the heading or
  label they sit beside.
- **The component** (`src/js/components/info-toggletip.js`, registered in
  `src/js/backoffice/alpine-components.js`). Click toggles. Opening shows the
  bubble, empties the live region and fills it 100ms later, so the text is
  announced, and announced again on every reopen. Escape closes it, returns
  focus to the button and stops propagation when open, so `dialog-escape.js`
  doesn't also close an enclosing dialog (the icon appears in several). A click
  outside closes it, and so does tabbing to another control.
- **The bubble** is `aria-hidden="true"`, so a screen reader hears the text once,
  from the live region, rather than again when reading on. It's
  `popover="manual"`, so it renders in the top layer: the target category cards
  are `overflow-hidden` and would clip an absolutely positioned bubble. The
  component places it with `position: fixed` under the icon, centred, kept 8px
  inside the viewport, and flipped above the icon when there's no room below. It
  follows the icon on scroll and resize while open.
- **The bubble keeps the text in the DOM** at all times and carries the `id`, so
  `input()`'s `aria-describedby="<name>-info"` still points at it. Accessible
  description computation includes hidden content that's referenced directly.
- **No-JS fallback:** the server still renders `title="<text>"` on the button.
  The component binds `:title="nativeTitle"`, which is `null`, so Alpine removes
  it at start-up and desktop users don't see the text twice. Without JavaScript
  it's the same hover tooltip as before, and the title doubles as the button's
  accessible description.
- **CSS:** an `INFO TOGGLETIP` section in `static/backoffice/src/main.css`.
  Nothing sets `display` on the bubble: the UA stylesheet hides a closed popover.

## The open question

> Should the `input.html` `info` argument keep using the icon, or become a
> normal hint below the label?

It kept the icon. The `inline` layout of `input()` (the auto-reply form, one row
per field) was built around the icon, so a hint under every label would undo it.
With the icon now a button, it no longer needs replacing. A form that has the
room can still pass `hint=` instead.

## Tests

- **Unit** (`tests/unit/test_info_icon_macro.py`): the button and its name, with
  and without `about`, the bubble's popover, `aria-hidden` and id, the live
  region, the `title` fallback and its removal binding, and the close bindings.
  `tests/unit/test_input_macros.py` checks `input()` names the button after its
  label.
- **Component** (`tests/component/test_targets_pages.py`): each count heading's
  icon is a button named after the column, with the note in its bubble.
- **JS** (`src/js/components/info-toggletip.test.js`): open and close on click,
  the delayed announcement, a quick close cancelling it, Escape (including that
  it doesn't reach `dialog-escape.js`), focus out, placement, the viewport
  clamp, flipping above, and following on scroll.
- **BDD** (`features/targets.feature`, "A column's note can be read without a
  mouse"): Tab from the top of the targets page to "More about Respondents",
  press Enter, see the bubble, press Escape, see it gone and focus back on the
  button.
