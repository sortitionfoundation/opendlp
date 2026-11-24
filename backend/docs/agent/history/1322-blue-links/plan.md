# 1322 — Links in link blue

Status: implemented. Every link in the backoffice and on the public pages is
link blue instead of the brand crimson. This is the fourth point of 1287, "Link
text blue, not red", which that change left to one that repoints
`--color-links` itself (see `docs/agent/1287-sign-up-fixes/plan.md`).

Design reference: the OpenDLP - UI Figma file. Its sign-up frame (node
`5570-7007`) binds "View data agreement" to `info-600`, #2B5FA6, which the code
already has as `--color-info-600`.

## What changed

1. **The tokens.** `--color-links` and `--color-link-text` in
   `static/backoffice/tokens/semantic.css` were aliases of
   `--color-primary-action` (brand-400, #90003F). Both are now
   `var(--color-info-600)`. That turns every link coloured through them blue:
   the sign in, sign up, forgot password, resend confirmation, 2FA and home
   pages, the profile and 2FA settings, the registration steps, the URL
   display, the rich editor's links and the `linkify` filter.
2. **Links that set the crimson themselves.** These used
   `color: var(--color-primary-action)` directly, so the token alone would have
   left them crimson. They now use `--color-links`:
   - "View spreadsheet": the respondents page and the selection, replacement
     and delete-old-tabs dialogs.
   - "Show all runs" / "Show only the current selection" and the run history's
     "View" on the selection page (both history tables).
   - The panel size "Edit" in the selection steps.
   - The "Feeds target" tags in the respondent schema editor and its question
     dialog, coloured from `.question-tags a` in `static/backoffice/src/main.css`.
   - The showcase's spacing link, which was `--color-pressed` (brand-700).
   - The replacement dialog's "Change the number of replacements", a button
     drawn as a link, so it matches the panel size "Edit".
3. **The table link macro** (`table_cell_link` in
   `components/table.html`). It swapped crimson for brand-500 on hover with
   inline `onmouseover`/`onmouseout` handlers. The CSP blocks inline handlers
   (`docs/frontend_security.md`), so the colour never changed and each hover
   logged a violation. The handlers are gone; the link is `--color-links` and
   underlines on hover, like the other text links in tables.
4. **Links with no colour.** Four text links set none, so the preflight's
   `a { color: inherit }` showed them in body text: the respondents list's
   "View" and "Edit", the DB selection dialog's "View" for each person
   selected, and the run link in a respondent's history. They now use
   `--color-links`, so they match the other links in those tables.
5. **Tests.** `tests/unit/test_link_colours.py` pins both tokens to
   `var(--color-info-600)` and info-600 to #2B5FA6, and fails if an `<a>` in
   the templates is coloured `--color-primary-action`, apart from the two
   exceptions below.

## Not changed, and why

- **Error links stay red, like the errors they list:** the project form's
  error summary (`assembly_form.html`, `--color-primary-action`), the edit
  respondent page's error summary and the "Registration closed" banner's link
  (both `--color-error-600`).
- **The page header's back arrow** (`components/page_header.html`) stays
  crimson: it is an icon control, not a text link.
- **Links inside warning alerts** take the alert's own text colour, as the
  alert component's example does: "Go to Data Settings" on the selection page,
  "Initialise the field schema first" on the edit respondent page.
- **Navigation** keeps its neutral colours: the header, breadcrumbs, tabs,
  stepper, pagination, the footers and the skip links.
- **Links drawn as buttons or controls**: the button macro's links, the
  dashboard's Chart / Table toggle, the QR code download, link cards and the
  registration setup steps.
- **The registration assets list** shows each file's name in body text as the
  name of the row; it is also a link to the file.
- **The OpenDLP wordmark** above the sign in and sign up titles
  (`public/_page_heading.html`) is decoration, not a link.
- **The GOV.UK-styled pages** (`templates/admin`, `main`, `db_selection`,
  `gsheets`, `targets`, `respondents`, `register`) use `govuk-link`, which is
  already GOV.UK's own blue. The emails carry their own inline styles.

## Contrast

#2B5FA6 against the backgrounds links sit on:

| Background | Ratio |
| --- | --- |
| White (#FFFFFF) | 6.4:1 |
| Page background, neutral-50 (#F7F7F8) | 6.0:1 |
| Info background, info-100 (#E8F1FA) | 5.6:1 |
| Success background, success-100 (#E6F4EA) | 5.6:1 |

All pass WCAG AA for normal text (4.5:1).

## Seen, not changed

- Links that underline only on hover, such as "Show all runs" in its sentence,
  are told from the text around them by colour alone while at rest. Blue is
  1.95:1 against body text (#2F3442) and 1.20:1 against secondary text
  (#4E5361); the crimson was 1.34:1 and 1.21:1. WCAG technique G183 asks for
  3:1 in that case, so this is no worse than before. Underlining those links
  all the time would meet it.
- `link_card` in `components/card.html` changes its border colour on hover
  with the same inline handlers the CSP blocks. It is a whole-card link, not a
  text link.
