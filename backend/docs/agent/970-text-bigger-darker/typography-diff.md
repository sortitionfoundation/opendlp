# sc-970 · Typography: the Figma frames vs. the branch tokens

Figma file `WaG38I99ccF8RMy1655fA2` ("OpenDLP - UI"), page "↪Typography". It
holds two frames side by side, both read through the Figma MCP
(`get_design_context`, `get_variable_defs`, `get_metadata`):

- node `6316-7167` "Typography", with its content frame `6316-7169`, read on
  2026-11-06 (section 1);
- node `1276-155` "Typography - revised", read on 2026-11-02, 2026-11-06 and
  2026-11-10 (section 3).

Section 5 is what the branch ships: the scale of `1276-155`.

Each frame writes every token out as
"Category/Size/Line height/Weight/Letter spacing (px)/color/usage" and sets a
sample line in a font style. The rows below are what the frames say and what the
code says, nothing more.

Code side: the `@utility text-*` blocks in `static/backoffice/src/main.css` and
the text colour aliases in `static/backoffice/tokens/semantic.css`. Pixel values
assume the 16px root. "Branch before" is the branch after merging `origin/main`
(2af873fb) and before the switch to Lato 2.0; "branch after" is with the four
Lato 2.0 files (`fonts.md`). The switch changes no token: it changes which face
renders 500 and 600, shown in brackets.

## 1. Node 6316-7169 ("Typography") against the branch

Size/line in px · weight · letter spacing in px.

| Token | Figma, written | Figma sample, where it differs from the written spec | Branch before | Branch after | `origin/main` |
| --- | --- | --- | --- | --- | --- |
| display-lg | 30/40 · 700 · 0 | | 30/40 · 700 (Bold) · 0 | 30/40 · 700 (Bold) · 0 | as Figma |
| display-md (Figma: `display-mg`) | 26/36 · 600 · 0 | Bold | 26/36 · 600 (renders Bold) · 0 | 26/36 · 600 (Semibold) · 0 | as Figma |
| display-sm | 22/32 · 600 · 0 | | 22/32 · 600 (renders Bold) · 0 | 22/32 · 600 (Semibold) · 0 | as Figma |
| heading-lg | 18/28 · 600 · 0.1 | | 18/28 · 600 (renders Bold) · 0.1 | 18/28 · 600 (Semibold) · 0.1 | as Figma |
| heading-md | 16/24 · 500 · 0.2 | SemiBold | 16/24 · 500 (renders Regular) · 0.2 | 16/24 · 500 (Medium) · 0.2 | as Figma |
| heading-sm | 15/22 · 500 · 0.2 | SemiBold | 15/22 · 500 (renders Regular) · 0.2 | 15/22 · 500 (Medium) · 0.2 | as Figma |
| body-lg | 16/24 · 400 · 0 | | **17/26** · 400 · 0 | 17/26 · 400 · 0 | as Figma |
| body-md | 14/20 · 400 · 0 | | **15/22** · 400 · 0 | 15/22 · 400 · 0 | as Figma |
| body-sm | 13/18 · 400 · 0.1 | no letter spacing | **14/20** · 400 · 0.1 | 14/20 · 400 · 0.1 | as Figma |
| caption | 12/16 · 400 · 0.2 | | **13/18** · 400 · 0.2 | 13/18 · 400 · 0.2 | as Figma |
| overline | 11/14 · 500 · 0.8 | lowercase (the CSS sets uppercase) | **12/16** · 500 (renders Regular) · 0.8 | 12/16 · 500 (Medium) · 0.8 | as Figma |
| label-lg | 14/20 · 500 · 0.3 | SemiBold | **15/22** · 500 (renders Regular) · 0.3 | 15/22 · 500 (Medium) · 0.3 | as Figma |
| label-md | 13/18 · 500 · 0.3 | SemiBold | **14/20** · 500 (renders Regular) · 0.3 | 14/20 · 500 (Medium) · 0.3 | as Figma |
| input-text | 14/20 · 400 · 0 | Medium, 13/18 | **15/22** · 400 · 0 | 15/22 · 400 · 0 | as Figma |
| placeholder | 14/20 · 400 · 0 | Medium, 13/18 | same class as input-text | same class as input-text | as Figma |
| button-lg | 14/16 · 600 · 0.4 | | 14/16 · 600 (renders Bold) · 0.4 | 14/16 · 600 (Semibold) · 0.4 | as Figma |
| button-md | not in Figma | | 13/16 · 600 (renders Bold) · 0.4 | 13/16 · 600 (Semibold) · 0.4 | as the branch |
| button-sm | not in Figma | | 12/14 · 600 (renders Bold) · 0.4 | 12/14 · 600 (Semibold) · 0.4 | as the branch |
| table-header | 12/16 · 600 · 0.4 | | **13/18** · 600 (renders Bold) · 0.4 | 13/18 · 600 (Semibold) · 0.4 | as Figma |
| table-cell | 13/18 · 400 · 0 | line height 20 | **14/20** · 400 · 0 | 14/20 · 400 · 0 | as Figma |
| numeric | 13/18 · 500 · 0.1 | letter spacing 0.013px | **14/20** · 500 (renders Regular) · 0.1 · tabular | 14/20 · 500 (Medium) · 0.1 · tabular | as Figma |
| code | not in Figma | | **14/20** · 400 · 0 · mono | 14/20 · 400 · 0 · mono | 13/18 |

Reading of the table:

- **The written spec of 6316-7169 is `origin/main`'s type scale, value for
  value**: all 19 tokens it lists, in size, line height, weight and letter
  spacing. What is new in the frame is the colour written beside each token
  (section 2).
- **Against the branch it differs only in size and line height, and exactly
  where this branch added its +1px** (the bold cells: body, caption, overline,
  label, input, table and numeric classes). Weights and letter spacing are the
  same as the branch's. Taking the frame's sizes would therefore return every
  changed size to `origin/main`'s, and the branch would no longer make text
  bigger. The branch does not take them; it follows `1276-155` (section 5).
- **The frame's samples disagree with its written spec in seven tokens**:
  display-md is set Bold (written 600); heading-md, heading-sm, label-lg and
  label-md are set SemiBold (written 500); input-text and placeholder are set
  Medium 13/18 (written 400 · 14/20); table-cell's line height is 20 (written
  18). Smaller differences: body-sm's sample has no letter spacing (written
  0.1), numeric's has 0.013px (0.1 % of 13px, where the spec says 0.1px), and
  the overline sample is lowercase. The samples are hand-set: none of them uses
  one of the file's named text styles (section 3). The branch follows the
  written spec wherever the two disagree.
- With the Lato 2.0 files in, those weight differences are now visible: a 500
  token renders Medium and a 600 token Semibold. Before, 500 rendered Regular
  and 600 Bold.

## 2. Colours

Figma variables on node 6316-7169: `neutral-800` #1f2330, `neutrals-700`
#2f3442, `neutral-600` #4e5361, `neutral-500` #6f7482, `neutrals-50` #f7f7f8 —
all equal to `static/backoffice/tokens/primitive.css`. (Node 1276-155 still uses
a `neutral-500_` variable, #646a78, one step darker than the repo's #6F7482.)

The code has one colour alias per role, not one per type token. Which alias the
templates pair with each class (counted over `templates/`): heading, label,
table-header and numeric classes with `--color-headings`; body and table-cell
with `--color-body-text`; caption and overline with `--color-secondary-text`.
Form fields took `--color-body-text` as well; they now have
`--color-input-text` (section 5). Display classes were paired with `--color-headings`
too; they now have their own alias, `--color-display-text`, which the 40 tags
with a `text-display-*` class and that colour use (the one brand-coloured public
page heading keeps `--color-primary-action`).

The branch follows the frames' colours wherever the code has an alias for the
role. "Before" is the branch up to the Lato 2.0 switch, "now" is with this
change:

| Text | 6316-7169 | 1276-155 | Branch before | Branch now | `origin/main` |
| --- | --- | --- | --- | --- | --- |
| display-* | neutral-800 | neutral-800 | `--color-headings` neutral-900 #12141C | `--color-display-text` **neutral-800** #1F2330 | neutral-700 |
| heading-*, label-*, table-header, numeric | neutral-700 | neutral-700 | `--color-headings` neutral-900 | `--color-headings` **neutral-700** #2F3442 | neutral-700 |
| body-* | neutral-700 | neutral-700 | `--color-body-text` neutral-800 | `--color-body-text` **neutral-700** | neutral-600 |
| input-text | neutral-800 | neutral-800 | `--color-body-text` neutral-800 | `--color-input-text` **neutral-800** (section 5) | neutral-600 |
| table-cell | neutral-600 | neutral-700 | `--color-body-text` neutral-800 | `--color-body-text` neutral-700 (no own alias) | neutral-600 |
| caption, overline | neutral-600 | neutral-600 | `--color-secondary-text` neutral-600 #4E5361 | unchanged | neutral-500 |
| placeholder | neutral-500 #6f7482 | neutral-500_ #646a78 | `--color-placeholder-text` neutral-500 #6F7482 | unchanged | neutral-400 |
| button-lg | none written; sample #4e5361 | white on brand-400 | per button variant | unchanged | per button variant |

Against `origin/main`, body text, captions, placeholders and display titles are
one step darker, and input values two; headings, labels, table headers and
numbers are back on `origin/main`'s neutral-700, the same colour as body text,
as in both frames.

Where a frame's colour has no counterpart in the code, the code is unchanged:

- **Table cells** are neutral-600 in 6316-7169 and neutral-700 in 1276-155. The
  code has no table-cell alias; cells use `--color-body-text`, so they are
  neutral-700, as in 1276-155.
- **The button-lg sample** carries a colour in each frame, but buttons take
  their colours from the button tokens (`--color-button-*`) per variant, which
  neither frame describes.
- **neutral-500**: the repo and 6316-7169 have #6F7482; 1276-155's
  `neutral-500_` variable is #646a78. The primitive is unchanged.

## 3. Node 1276-155 ("Typography - revised") against the branch

Its values on 2026-11-06 are those read on 2026-11-02; the button-lg sample now
sits white on brand-400. Unlike 6316-7169, its samples use the
file's named text styles (`Display-lg` … `numeric`), and the written spec agrees
with them, apart from letter spacings that the styles hold in per cent
(table-header 0.2 % = 0.026px at 13px; numeric 0.1 %, written as 0).

| Token | 1276-155 (size/line · weight · tracking) | Branch | Δ revised vs branch |
| --- | --- | --- | --- |
| display-lg | 32/40 · 700 · 0 | 30/40 · 700 · 0 | size +2 |
| display-md | 28/36 · 700 · 0 | 26/36 · 600 · 0 | size +2, weight 600→700 |
| display-sm | 24/32 · 600 · 0 | 22/32 · 600 · 0 | size +2 |
| heading-lg | 20/28 · 600 · 0 | 18/28 · 600 · 0.1 | size +2, tracking 0.1→0 |
| heading-md | 18/26 · 600 · 0 | 16/24 · 500 · 0.2 | size +2, line +2, weight 500→600, tracking 0.2→0 |
| heading-sm | 16/24 · 600 · 0 | 15/22 · 500 · 0.2 | size +1, line +2, weight 500→600, tracking 0.2→0 |
| body-lg | 18/28 · 400 · 0 | 17/26 · 400 · 0 | size +1, line +2 |
| body-md | 16/24 · 400 · 0 | 15/22 · 400 · 0 | size +1, line +2 |
| body-sm | 14/20 · 400 · 0 | 14/20 · 400 · 0.1 | tracking 0.1→0 |
| caption | 13/18 · 500 · 0.1 | 13/18 · 400 · 0.2 | weight 400→500, tracking 0.2→0.1 |
| overline | 12/16 · 600 · 0.6 (sample lowercase) | 12/16 · 500 · 0.8 · uppercase | weight 500→600, tracking 0.8→0.6 |
| label-lg | 15/22 · 600 · 0.1 | 15/22 · 500 · 0.3 | weight 500→600, tracking 0.3→0.1 |
| label-md | 14/20 · 600 · 0.1 | 14/20 · 500 · 0.3 | weight 500→600, tracking 0.3→0.1 |
| input-text, placeholder | 16/24 · 400 · 0 | 15/22 · 400 · 0 | size +1, line +2 |
| button-lg | 16/20 · 600 · 0.2 | 14/16 · 600 · 0.4 | size +2, line +4, tracking 0.4→0.2 |
| table-header | 13/18 · 600 · 0.2 written, 0.2 % in the style | 13/18 · 600 · 0.4 | tracking |
| table-cell | 14/20 · 400 · 0 | 14/20 · 400 · 0 | none |
| numeric | 14/20 · 500 · 0 written, 0.1 % in the style | 14/20 · 500 · 0.1 · tabular | tracking |

So the branch sits between the two frames: 6316-7169 is `origin/main`'s scale,
1276-155 is one to two pixels above the branch with a heavier weight pass
(headings, labels and overline 600, display-md 700, caption 500).

## 4. Not in either frame

- No `button-md`, `button-sm` or `code` style; the CSS and the showcase have
  them.
- No italic, no 300 or 900.
- Component rules outside the scale (`main.css`): `.dialog-title` (500 ·
  20/28), `.dialog-text-stack__title` (700 · 18/28), `.tab-item` 400 and
  `.tab-item-selected` 700, `.target-source-row__unlinked` 600, the stepper's
  active/error labels 500, the visual editor's h1–h3/th 700. (`.btn` was a copy
  of button-lg's values; it now applies the class, section 5.)
- `overline` is uppercase in the CSS; both frames' samples are lowercase.

## 5. What the branch ships: the scale of 1276-155

The type classes follow node `1276-155`: the 19 named text styles of its
content frame (`1276:157`, read again on 2026-11-10 through
`get_variable_defs`) value for value, which is the "1276-155" column of
section 3 with every letter spacing in px. They use 400, 500, 600 and 700, the
four Lato 2.0 files that already ship (`fonts.md`); no font file was added.
The showcase's typography table shows the new values.

Where the frame is silent, or says it differently from the code:

- **button-md and button-sm** are not in the frame. They step down from
  button-lg (16/20) a pixel at a time: button-md 15/18, button-sm 14/16, both
  600 · 0.2px.
- **`.btn`** no longer copies button-lg's values; it applies `text-button-lg`,
  so buttons are 16/20 · 600 · 0.2px and follow the class from now on.
- **code** is not in the frame and stays 14/20 · 400 · monospace, like
  `.code-inline`.
- **overline** stays uppercase (`text-transform` in the class); the frame's
  sample is lowercase.
- **Input values** have their own colour alias, `--color-input-text`, at
  neutral-800 as in the frame. The 62 `<input>`, `<textarea>` and `<select>`
  tags in 20 templates that coloured their text with `--color-body-text` (the
  `input.html` macros among them) use it, and the showcase lists it with the
  other text colours. Fields that set no colour of their own still inherit
  their container's. The visual editor's content area and the HTML code editor
  are editors rather than form fields and keep body text.
- **Placeholders** stay `--color-placeholder-text`, neutral-500 #6F7482; the
  frame's `neutral-500_` #646a78 is not a colour of the code.
- **Letter spacing held in per cent**: the table-header and numeric styles
  hold 0.2 % and 0.1 %. The classes read both as px, like every other style:
  table-header 0.2px, numeric 0.1px.
- **Rules outside the scale** keep their values: `.dialog-title` (500 ·
  20/28), `.dialog-text-stack__title` (700 · 18/28), `.tab-item` (400 · 15/22,
  700 when selected), the stepper's active and error labels (500),
  `.content-block-row__heading` (600 · 18/24) and the visual editor's content
  h1–h3/th (700). The component rules that `@apply` a type class (menu items,
  the checkbox, radio and switch labels, the stepper's number and label, the
  dialog description, the editor's toggles, menu and tooltips) move with it.
- **`text-body-xs`**, used five times and defined nowhere, is gone. The frame
  has no style for it, so each use takes the nearest class for what the text
  is: the language badge beside a registration page's name (in the pages list
  and on the project details page) and the caption of the compact URL display
  are uppercase micro-labels, `text-overline`; the two field hints in the
  service docs are `text-body-sm`, as every hint in the `input.html` macros is.
