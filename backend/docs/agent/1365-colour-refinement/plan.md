# 1365 — Colour refinement: the error reds

Status: the error colours are implemented. The story asks for a few
refinements to colour; the first, written down by Hamish, is that the error
red is too close to the brand reds. Further refinements from Klára are a
follow-up.

Design reference: the OpenDLP UI Figma file, Colors section (node `1275:8124`).
Its success, warning and info colours already matched the code. Only error
differed.

## The problem

The error tokens were the brand reds themselves:

- `--color-error-400`, #C70039, was `--color-brand-300`.
- `--color-error-600`, #90003F, was `--color-brand-400`, which is also
  `--color-primary-action` and the primary button's background.

So an error message was exactly the colour of the Sign in button beside it.
And the form fields did not use the error tokens at all: they drew an error's
border and message in `--color-primary-action`, so a new error red in the
tokens alone would not have reached them.

## What changed

1. **The error tokens** (`static/backoffice/tokens/semantic.css`), to the
   design's values:

   | Token | Was | Now |
   | --- | --- | --- |
   | `--color-error-100` (background) | #FDEBEC | #FCEBE7 |
   | `--color-error-400` (border) | #C70039 | #D6361A |
   | `--color-error-600` (text) | #90003F | #B42318 |

   There is a new alias, `--color-error-border`, beside
   `--color-error-background` and `--color-error-text`, as success, warning
   and info already had one. The brand tokens and `primitive.css` are
   unchanged.
2. **Field errors use the error tokens.** Every field macro drew its error in
   `--color-primary-action`. Borders now use `--color-error-border` and
   messages `--color-error-text`:
   - `components/input.html`: the border of `input`, `textarea` and `select`,
     and the message of those three plus `checkbox`, `radio_group`,
     `file_input` and `switch`.
   - `components/select_dropdown.html` and `components/search_dropdown.html`:
     border and message.
   - `assembly_edit_respondent.html`: the date field's message.
   - `targets/bulk_edit_form.html`: the error under a target row and the one
     above a category.

   That covers the public sign in and sign up pages too, as they use the same
   macros.
3. **Error links.** Links inside an error take the error's text colour, so
   they still match the error they sit in: the edit respondent page's error
   summary and the "Registration closed" banner's link. Both, and the text
   around them, now use `--color-error-text`, and their boxes
   `--color-error-background` and `--color-error-border`. They were
   `--color-error-600`, the same value under its scale name.
4. **The deleted respondent banner** (`assembly_view_respondent.html`) was the
   one box drawn in Tailwind reds (`border-red-300 bg-red-50`). It says
   "Personal data deleted, deleted on <date> by <who>": a record of a deletion
   someone asked for and made, not an error. It is now drawn in the info
   colours (`--color-info-background`, `--color-info-border`). The status tag
   beside it was already neutral grey.
5. **The showcase.** The Foundations tab prints each status colour's hex as
   text, so the error swatches' labels change with the values
   (`showcase/semantic_tokens.html`). The input, select dropdown and search
   dropdown sections list `--color-error-border` and `--color-error-text`
   among the tokens they use.
6. **Docs.** `docs/agent/frontend_design_system.md` says errors are drawn in
   the error tokens, never a brand colour, and lists the `-border` alias. The
   three standalone explainers in `docs/explainers/` copy the app's tokens, so
   their error line follows.
7. **Tests.**
   - `tests/unit/test_error_colours.py` pins the three values and the three
     aliases; fails if any error token equals a brand token (on the old values
     it does, twice); checks the twelve status labels on the Foundations tab
     against `semantic.css`; and fails if a template draws an error in
     `--color-primary-action`. That scan finds an element coloured
     `--color-primary-action` whose content is an error expression
     (`{{ error }}`, `{{ row_error }}` …), and a style that switches to
     `--color-primary-action` under `{% if has_error %}`. Run against the old
     templates it lists the seventeen places above.
   - `tests/unit/test_input_macros.py` renders all nine field macros in error:
     the message is `--color-error-text`, the border (where there is one) is
     `--color-error-border`, nothing is `--color-primary-action`; without an
     error the border is the usual divider colour.
   - `tests/component/test_backoffice_respondents.py`: the deleted respondent
     banner is drawn in the info colours.

## Not changed, and why

- **The brand tokens and the primary button** stay as they are. The point is
  to move errors away from the brand, not the brand away from errors.
- **Required field asterisks** stay `--color-primary-action`. An asterisk marks
  a field as required; it is not an error.
- **Templates that use the error scale by name** (`--color-error-100/400/600`)
  directly, such as the alert component, the target check, the data source
  upload errors and the registration page list, are not touched. They follow
  the new values as they are.
- **The GOV.UK-styled pages** (`templates/admin`, `main`, `db_selection`,
  `gsheets`, `targets`, `respondents`, `register`) use GOV.UK's own error
  styles, not these tokens.
- **The link guard** (`tests/unit/test_link_colours.py`) needed no change. It
  fails on a link coloured `--color-primary-action`, and the error links were
  never that; its one exception is still the page header's back arrow.

## Contrast

| Colour | On | Ratio | Needs |
| --- | --- | --- | --- |
| #B42318 (text) | White | 6.6:1 | 4.5:1 |
| #B42318 | Page grey, neutral-50 (#F7F7F8) | 6.1:1 | 4.5:1 |
| #B42318 | Error background, #FCEBE7 | 5.7:1 | 4.5:1 |
| #D6361A (border) | White | 4.8:1 | 3:1 |
| #D6361A | Page grey, neutral-50 | 4.5:1 | 3:1 |
| #D6361A | Error background, #FCEBE7 | 4.1:1 | 3:1 |

Text needs WCAG AA's 4.5:1, a field's border the 3:1 for non-text contrast.

## Distance from the brand

CIEDE2000 colour difference, where 0 is the same colour and above 10 reads as
clearly different:

| | brand-300 #C70039 | brand-400 #90003F (primary action) |
| --- | --- | --- |
| error-400 #D6361A | 14.2 | 26.5 |
| error-600 #B42318 | 10.4 | 19.8 |

Before, both of these were 0. The closest pair now is error-600 against
brand-300; brand-300 is used only for the step accents on the public home page,
where no error is shown.

## Errors are not told by colour alone (WCAG 1.4.1)

Checked, nothing missing:

- **Field errors**: a message in words under the field. `input`, `textarea`,
  `select`, `checkbox` and both dropdowns also set `aria-invalid` and point
  `aria-describedby` at the message; a radio group's fieldset is described by
  it.
- **Error alerts**: the "!" glyph and the message, with `role="alert"`.
- **The danger button**: every use names its action in words ("Delete
  personal data", "Close registration", "Remove link" …).
- **Error summaries**: "There is a problem" and the list; the "Registration
  closed" banner opens with ⛔ and the words.
- **A stepper step in error**: a warning icon in place of its number, and
  "(has errors)" for screen readers.
- **Status pills and dots** in the error colours ("Closed", "Withdrawn")
  always carry their word.

## Seen, not changed

- `file_input` and `switch` show an error message, but it has no `id`, and the
  control has no `aria-invalid` or `aria-describedby`, so a screen reader is
  not told the two belong together. No page passes either an error today.
- The Foundations tab has three labels that do not match their tokens, none of
  them an error colour: the brand-700 swatch says #0F5389 where the token is
  #5E003A (`showcase/primitive_tokens.html`); `--color-tables-cards` says
  "→ neutral-100" where it is neutral-0, and `--color-focus-ring` says
  "→ brand-200" where it is brand-400 (`showcase/semantic_tokens.html`).
