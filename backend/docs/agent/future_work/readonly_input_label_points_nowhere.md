# A read-only `input()` has a label that points at nothing

Found on `1361-auto-reply-fixes`, which switched the auto-reply step's reply-to
and subject fields to the `input` macro's `readonly=true` display. Not fixed
there because the macro is shared. Written to be pasted into an issue.

## Problem

With `readonly=true`, the `input` macro in
`templates/backoffice/components/input.html` shows the value as a `<p>`, but
still renders the label as `<label for="{{ input_id }}">`. No element has that
id, so:

- the label is a `<label>` for no control. Assistive technology gets a label
  with nothing to name, and the value in the `<p>` is not tied to its label in
  any way, only by order on the page;
- it is invalid HTML: the W3C validator reports that a label's `for` must be
  the id of a form control;
- tests cannot find the value by its label. `get_by_label("Reply-to name")`
  fails in Playwright, which is how this showed up: the BDD step
  `replies should go to "…" at "…"` had to switch to finding the text inside
  the step's panel (commit `67155f69`).

The macro's other read-only displays are already right. `checkbox` and `switch`
render their label as a `<span>` beside a "Yes"/"No" or "On"/"Off" `<span>`.

## Where it shows

Every `input(…, readonly=…)` call:

- `templates/backoffice/assembly_data.html`: 14 fields (project details, plus
  two in the CSV section), when the viewer cannot edit or the page is not in
  edit mode;
- `templates/backoffice/registration/_step_email.html`: reply-to name, reply-to
  email and subject, outside edit mode.

## Related: read-only `radio_group`

A read-only `radio_group` keeps `<fieldset role="radiogroup">` around a single
`<p>` holding the chosen option. A screen reader announces a radio group that
has no radios in it. One read-only call, at `assembly_data.html:194`.

## Proposal

Match `checkbox` and `switch`.

1. In `input`'s read-only branch, render the label as
   `<span id="{{ input_id }}-label" class="text-label-lg" …>` instead of
   `<label for=…>`. Keep the info icon and the inline grid layout as they are.
   The label's markup is shared by both branches today, so split it on
   `readonly` without duplicating the info-icon wrapper.
2. In `radio_group`'s read-only branch, leave out `role="radiogroup"` (and
   consider a plain `<div>` with the legend's text as a `<span>`, as `checkbox`
   does, since a `<fieldset>` around one value adds nothing).
3. Do not try to label the `<p>` with `aria-labelledby`: ARIA does not allow
   naming a generic element, and screen readers ignore it. Label then value, in
   reading order, is enough for static text.

The change is all in the macro, so the callers need no edits.

## Tests

- Component: render a read-only `input` (the auto-reply step outside edit mode
  is a good real page) and assert there is no `<label for="template_reply_to_name"`
  and the label text and value are both present. Same for a read-only
  `radio_group` on the project details page: no `role="radiogroup"`.
- The showcase pages (`templates/backoffice/showcase/`) cover `checkbox`,
  `radio` and `switch` read-only states but not `input`; add a read-only
  `input` example there so it can be checked by eye and with an accessibility
  checker.
- See `docs/agent/component_accessibility.md` for the wider rules.
