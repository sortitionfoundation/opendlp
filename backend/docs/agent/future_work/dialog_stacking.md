# Stack dialogs in the order they open

Turned up on the `1072-edit-sections` branch, the third time a dialog opened
over another dialog left the one underneath undimmed. Two ways to stop it for
good are written up below for the team to choose between. Written to be pasted
into an issue.

## Problem

Every dialog is a `.dialog-backdrop` plus a `.dialog-positioner`, and CSS gives
each a fixed z-index from a table in `static/backoffice/src/main.css`. A dialog's
layer comes from *where it sits in the page*, never from *when it opened*:

| Layer | Backdrop | Panel | Chosen by |
| --- | --- | --- | --- |
| Ordinary dialog | 40 | 50 | `.dialog-backdrop`, `.dialog-positioner` |
| Dialog over a takeover panel | 51 | 52 | `body:has(.dialog-panel--takeover) [data-fragment-dialog-host]` or `[data-takeover-dialog-host]` |
| Dialog over a dialog | 53 | 54 | `stacked=true` on `controlled_modal()` / `controlled_alert_dialog()` |

Two dialogs given the same pair leave the second one's backdrop *below* the
first one's panel: the page greys out, the dialog underneath does not, and it
looks as if both are live. Each fix so far has added a layer:

- `e1dfa751` - a registration step dialog was not dimmed behind its sub-dialog
  (added the takeover layer for fragment hosts);
- `bd55c979` - the registration editor was not dimmed behind its own dialogs
  (added `[data-takeover-dialog-host]`);
- `e3a4067b` - "Discard changes?" and the Link dialog did not dim the heading or
  text, question, or target set-up dialog they open over (added `stacked=true`).

The next nesting the table does not foresee - a dialog over a stacked dialog, a
fragment dialog opened from inside another fragment dialog - breaks the same
way. The diff never shows it: what goes wrong is a number in a CSS rule a long
way from the template that nests the dialogs.

### What catches it today

`pytest_bdd_after_step` in `tests/bdd/conftest.py` checks, after every BDD step,
that no more than one open dialog is drawn above every backdrop. A scenario that
opens one dialog over another therefore tests the stacking whether or not it
meant to. It only covers nestings some scenario reaches, and it reports the bug
rather than preventing it, so either option below is still worth having.

## Option A - give each dialog its layer as it opens (small JS manager)

A module under `src/js/init/` watches the document with a `MutationObserver`.
When a `.dialog-backdrop` / `.dialog-positioner` pair appears - from an Alpine
`<template x-if>`, an HTMX swap into a fragment host, or an `x-show` turning
visible - it gets `z-index: base + 2 × (dialogs already open)`, backdrop one
below its panel. When the pair goes, the count drops.

Gains:

- the layer table above collapses to one rule; `stacked=true`,
  `[data-takeover-dialog-host]` and the takeover-host z-index rules go;
- any nesting works, in the order the user opened things, whatever the DOM order;
- the change is one module with a Vitest test, plus deleting CSS.

Costs and risks:

- `x-show` dialogs (`modal()`, `alert_dialog()`) stay in the DOM while closed, so
  "appeared" means "became visible": the observer has to watch `style`
  attribute changes as well as added nodes;
- the progress modals (`src/js/init/progress-modals.js`) re-render by HTMX
  polling every second, so a re-render must keep its layer rather than count as
  a new dialog on top;
- flash alerts (`#floating-alerts`) and the registration editor's toast must
  stay above whatever is open, so they move to a fixed layer above the
  manager's range rather than the current 45/55 juggling;
- one more piece of startup JavaScript every backoffice page loads.

## Option B - native `<dialog>` with `showModal()`

A modal `<dialog>` goes into the browser's top layer, which stacks in opening
order by definition, and each gets its own `::backdrop`. The browser also makes
everything outside the top dialog inert and turns Escape into a `cancel` event.

Gains:

- no z-index for dialogs at all, and no layer table;
- much of `src/js/init/fragment-dialog-focus.js` (making the host's siblings
  inert) and `src/js/init/dialog-escape.js` (Escape through nested dialogs) is
  done by the platform instead;
- `aria-modal`, the backdrop element and its click handling become part of the
  element rather than our markup.

Costs and risks:

- it rewrites every dialog. Nine templates draw a positioner, and the macros in
  `components/modal.html` are called around two dozen times (`modal`,
  `alert_dialog`, `controlled_modal`, `controlled_alert_dialog`,
  `progress_modal`, `step_dialog`);
- `showModal()` is an imperative call. Alpine's `x-if` / `x-show` and HTMX swaps
  insert markup, so every open path needs a hook that calls `showModal()` and
  every close path `close()`; a fragment swapped in by HTMX needs an
  `htmx:afterSwap` handler;
- anything that must show above a dialog has to be in the top layer too: flash
  alerts and the toast would become `popover` elements, and a popover opened
  *before* a dialog sits *under* it, so they need re-showing when a dialog opens;
- the takeover panel (`.dialog-panel--takeover`) is the page's scroll container
  (`lib/page-scroller.js`), and that needs re-checking inside a `<dialog>`;
- the BDD and component tests that look for `.dialog-positioner` /
  `role="dialog"` markup change with it.

## Recommendation

Option A, unless the dialogs are being reworked for some other reason. It
removes the class of bug for a contained change. Option B is the better end
state, but its cost is a rewrite of every dialog and of flash alerts, and the
stacking bug alone does not justify that.
