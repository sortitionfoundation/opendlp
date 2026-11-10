# sc-970 · The showcase pages a typography/component pass touches

Klára's 10-26 comment asks how "the Storybook and the demo environment" get
updated. There is no Storybook in this repository. What she has been looking
at is the **component showcase**:

- URL `/backoffice/showcase`, route `showcase()` in
  `src/opendlp/entrypoints/blueprints/backoffice.py:79–88`; takes no login.
- Index template `templates/backoffice/showcase.html`; one partial per
  section under `templates/backoffice/showcase/` (31 files), each a macro
  called from the index in the order below.
- Visibility: `showcase_enabled()` in `src/opendlp/feature_flags.py:63` —
  always on outside production; on a production install it is opt-in with
  `FF_SHOWCASE=true` (`docs/configuration.md:420`, `env.example:223`). That is
  the "demo environment" question: a staging server shows the showcase only if
  the flag is set there.
- Tests that pin it: `tests/component/test_backoffice_general.py:130–205`
  (page loads, every shared icon is listed, production gating with and without
  the flag), the BDD step `visit_backoffice_showcase` in
  `tests/bdd/test_backoffice.py:113` (URL from `tests/bdd/config.py:40`), and
  `tests/unit/test_icons.py` for the icon sheet. Nothing asserts the
  scale's numbers; `tests/unit/test_design_tokens.py` asserts that every
  `var(--…)` used in templates and `main.css` is defined in the token files.

## Agenda for the walkthrough, in index order

Sizes are the branch's (`main.css` lines 71–190, the revised scale of `typography-diff.md` section 5); "type
classes" are the `text-*` utilities a partial renders; "CSS consumers" are
component rules in `main.css` that `@apply` a type class, so they move with
the scale without a template change.

### Foundations

| # | Section (nav label) | Partial | Why it is on the agenda |
| --- | --- | --- | --- |
| 1 | Typography | `typography.html` | The table of the 21 classes (lines 17–37) is hand-written and must be regenerated whenever the scale changes; its description (line 11) names the four Lato 2.0 files, one per weight (see `fonts.md`); until the switch it called 500/600 "browser-synthesised", which they never were. The use-case rows (45–63) are the visual check. |
| 2 | Semantic Tokens | `semantic_tokens.html` | Text colour aliases, now as the Figma typography pairs them: `--color-body-text` and `--color-headings` neutral-700, the new `--color-display-text` and `--color-input-text` neutral-800, `--color-secondary-text` neutral-600, `--color-placeholder-text` neutral-500; the swatch captions show that mapping. |
| 3 | Primitive Tokens | `primitive_tokens.html` | `--color-neutral-500` is #6F7482 in the repo and #646a78 in the Figma node. |
| 4 | Spacing Conventions | `spacing.html` | Uses body/heading/code classes; line-height changes alter the rhythm shown. |
| 5 | Responsive Layout | `responsive.html` | Uses body-md/sm, button-md, heading-sm, code. |
| 6 | Icons | `icons.html` | Only labels (body-md/sm, code); the `test_showcase_renders_every_shared_icon` test depends on this page. |

### Components with CSS consumers of the type classes (changed by this branch)

| # | Section | Partial | CSS consumers in `main.css` | Type classes in the partial |
| --- | --- | --- | --- | --- |
| 7 | Button | `button_component.html` | `.btn` `@apply text-button-lg` (line 229): 16/20 · 600 · 0.2px | body-md, caption, heading-sm, label-md |
| 8 | Split Button | `split_button_component.html` | shares `.btn` | body-sm |
| 9 | Input | `input_component.html` | input macro uses label-lg, body-md/sm, button-md; the typed values take `--color-input-text`; placeholders via `input::placeholder` (line 44) | body-md/sm, heading-md, label-lg/md |
| 10 | Checkbox | `checkbox_component.html` | `.checkbox-label` `@apply text-label-lg` (line 560) | caption, label-md |
| 11 | Radio Button | `radio_component.html` | `.radio-label` `@apply text-label-lg` (line 657) | label-md |
| 12 | Switch | `switch_component.html` | `.switch-label` `@apply text-label-lg` (line 745) | caption, label-md |
| 13 | Search Dropdown | `search_dropdown_component.html` | `.menu-item` `@apply text-body-md` (line 418) | body-md/sm, heading-sm, label-lg/md |
| 14 | Select Dropdown | `select_dropdown_component.html` | `.menu-item` | body-md/sm, heading-sm, label-lg/md |
| 15 | Modal | `modal_component.html` | `.dialog-text-stack__description` `@apply text-body-md` (line 1487); `.dialog-title` 500 · 20/28 (line 1303) and `.dialog-text-stack__title` 700 · 18/28 (line 1480) are outside the scale | body-md/sm, caption, label-lg |
| 16 | Table | `table_component.html` | none: the questions list's header row is for screen readers only (`.question-table thead th` sets just `padding: 0`), so no rule in `main.css` applies `text-table-header`; table macro uses body-sm, label-md | — (all in the macro) |
| 17 | Tabs | `tabs_component.html` | `.tab-item` 400 / `.tab-item-selected` 700 (lines 790, 808) — weights outside the scale | body-md/sm, label-md |
| 18 | Stepper | `stepper_component.html` | `.stepper-number` `@apply text-label-lg`, `.stepper-label` `@apply text-body-md` (lines 898, 907); active/error labels force 500 (918, 933) | body-sm, label-md |
| 19 | Account Menu | `account_menu_component.html` | `.menu-item` | — |

### Components whose typography comes only from the type classes in their macro

| # | Section | Partial | Type classes (partial + macro) |
| --- | --- | --- | --- |
| 20 | Pie Chart Card | `pie_chart_card_component.html` | macro: body-sm, caption, display-sm |
| 21 | Card | `card_component.html` | heading-lg, body-md/sm |
| 22 | Section | `section_component.html` | heading-md, body-md |
| 23 | Progress Bar | `progress_component.html` | caption; the progress modals use body-md/sm, label-lg/md |
| 24 | Pagination | `pagination_component.html` | body-sm, label-md |
| 25 | Navigation | `navigation_component.html` | none directly (navigation macro has no type class) |
| 26 | Avatar | `avatar_component.html` | `font-medium` utility in the macro (500) |
| 27 | Page Header | `page_header_component.html` | display-sm |
| 28 | Breadcrumb | `breadcrumb_component.html` | body-sm, label-md |
| 29 | Alert | `alert_component.html` | macro: body-lg, body-md; partial: body-sm, caption, heading-sm |
| 30 | Suggestion Row | `suggestion_row_component.html` | body-md/sm, label-md; `font-bold` in the macro — new on main (`1187f429`) |
| 31 | Alpine.js Interactivity | `interactivity.html` | body-md |

### Typography-bearing components that have no showcase section

These render on real pages only, so a walkthrough of the showcase does not
show them: `tag.html` (label-md), `info_card.html` (heading-md, body-md),
`footer.html`, `url_display.html` and `registration_page_list.html` (their
uppercase caption and language badge are `text-overline`, as is the badge in
`assembly_details.html`; all three used `text-body-xs`, a class defined
nowhere, as did the field hints in `service_docs/_macros.html`, now
`text-body-sm`),
`respondent_status_form.html` (display-sm, label-*), `selection_steps.html`,
the selection/replacement/db-replacement/manage-tabs progress modals,
`gsheet_*`, `prefixed_url_input.html`, `rich_editor.html` (toggle buttons and
menu items `@apply` body-md/caption, lines 1650–1764; editor content h1–h3/th
hardcode 700, lines 1832–1886), the registration wizard footer, and the bulk
targets editor (`font-bold` ×11 in `targets/bulk_edit_form.html` and
`targets/category_block.html`).

Tailwind weight utilities used outside the scale, for the record:
`font-semibold` ×25, `font-medium` ×12, `font-bold` ×12, `font-normal` ×1
across `templates/backoffice` and `templates/public` (the public login,
register, 2FA and password pages use `font-semibold`, served from the
backoffice bundle).

## Questions the walkthrough should settle

1. Her component refactor: which of the 31 sections changed beyond the type
   scale (spacing, colours, states), so the showcase can be updated section by
   section rather than guessed.
2. The component-level overrides outside the scale (dialog titles, tabs,
   stepper states, editor content) — are they in her Figma components?
3. `button-md`/`button-sm`/`code`: keep as code-only extensions of her scale?
4. `--color-neutral-500` (#6F7482 vs #646a78) and the split of headings into
   display (neutral-800) vs heading (neutral-700).
5. The demo environment: is `FF_SHOWCASE` set on the staging server, and is
   staging what she means by "demo"?

How the branch now handles 2–4 (the rules outside the scale, the code-only
styles, neutral-500) is in `typography-diff.md`, section 5.
