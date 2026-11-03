# sc-970 · Klára's revised type scale vs. the branch tokens

Source: Figma file `WaG38I99ccF8RMy1655fA2` ("OpenDLP - UI"), node `1276-155`
("typo" / "Typography - revised"), read on 2026-11-02 through the Figma MCP
(`get_design_context` + `get_variable_defs`). Figma text is data, not a spec:
every row below is what the node says, and what the code says, nothing more.

Code side: the `@utility text-*` blocks in `static/backoffice/src/main.css`
(lines 66–184 after the merge of `origin/main`, Tailwind v4) and the text
colour aliases in `static/backoffice/tokens/semantic.css` (lines 32–35).
Pixel values assume the 16px root; `rem` is what the CSS says.

## 1. Sizes, line heights, weights, tracking

| Style | Figma revised (size/line · weight · tracking) | Branch `970-text-bigger-darker` | `origin/main` (before the branch) | Δ Figma vs branch |
| --- | --- | --- | --- | --- |
| display-lg | 32/40 · 700 · 0 | 30/40 (1.875/2.5rem) · 700 · 0 | same as branch | size +2 |
| display-md (Figma names it `display-mg`) | 28/36 · **700** · 0 | 26/36 · 600 · 0 | same | size +2, weight 600→700 |
| display-sm | 24/32 · 600 · 0 | 22/32 · 600 · 0 | same | size +2 |
| heading-lg | 20/28 · 600 · 0 | 18/28 · 600 · 0.1px | same | size +2, tracking 0.1→0 |
| heading-md | 18/26 · **600** · 0 | 16/24 · 500 · 0.2px | same | size +2, line +2, weight 500→600, tracking 0.2→0 |
| heading-sm | 16/24 · **600** · 0 | 15/22 · 500 · 0.2px | same | size +1, line +2, weight 500→600, tracking 0.2→0 |
| body-lg | 18/28 · 400 · 0 | 17/26 · 400 · 0 | 16/24 | size +1, line +2 |
| body-md | 16/24 · 400 · 0 | 15/22 · 400 · 0 | 14/20 | size +1, line +2 |
| body-sm | 14/20 · 400 · 0 | 14/20 · 400 · 0.1px | 13/18 | tracking 0.1→0 only |
| caption | 13/18 · **500** · 0.1 | 13/18 · 400 · 0.2px | 12/16 | weight 400→500, tracking 0.2→0.1 |
| overline | 12/16 · **600** · 0.6 | 12/16 · 500 · 0.8px · uppercase | 11/14 | weight 500→600, tracking 0.8→0.6; the Figma sample node carries `lowercase`, the CSS uppercases — ask |
| label-lg | 15/22 · **600** · 0.1 | 15/22 · 500 · 0.3px | 14/20 | weight 500→600, tracking 0.3→0.1 |
| label-md | 14/20 · **600** · 0.1 | 14/20 · 500 · 0.3px | 13/18 | weight 500→600, tracking 0.3→0.1 |
| button-lg | 16/20 · 600 · 0.2 | 14/16 · 600 · 0.4px | same | size +2, line +4, tracking 0.4→0.2 |
| button-md | — (not in Figma) | 13/16 · 600 · 0.4px | same | no Figma value |
| button-sm | — (not in Figma) | 12/14 · 600 · 0.4px | same | no Figma value |
| input-text | 16/24 · 400 · 0 | 15/22 · 400 · 0 | 14/20 | size +1, line +2 |
| placeholder | 16/24 · 400 · 0 | (same class as input-text; colour differs by token) | — | follows input-text |
| table-header | 13/18 · 600 · 0.2 | 13/18 · 600 · 0.4px | 12/16 | tracking 0.4→0.2 |
| table-cell | 14/20 · 400 · 0 | 14/20 · 400 · 0 | 13/18 | none |
| numeric | 14/20 · 500 · 0.1 (style) / 0 (sample text) | 14/20 · 500 · 0.1px · tabular | 13/18 | none (confirm tracking) |
| code | — (not in Figma) | 14/20 · 400 · mono | 13/18 | no Figma value |

Reading of the table: the current branch is a +1px pass with the weights left
alone; Klára's revision is a +1–2px pass on the same classes **and** a weight
pass that moves every label, heading and overline from 500 to 600 and the
caption from 400 to 500. The two agree on direction and overlap on body-sm,
caption, table-* and numeric sizes.

## 2. Weights the two scales need

| Weight | Figma revised uses it for | Branch uses it for |
| --- | --- | --- |
| 400 | body-*, input, placeholder, table-cell | body-*, caption, input, table-cell, code |
| 500 | caption, numeric | heading-md/sm, overline, label-lg/md, numeric |
| 600 | display-sm, heading-*, overline, label-*, button, table-header | display-md/sm, heading-lg, button-*, table-header |
| 700 | display-lg, display-md | display-lg |

Only Lato 400 and 700 are shipped today (see `fonts.md`): a 500 request
renders with the 400 face and a 600 request with the 700 face. So under the
revised scale, without Medium/Semibold files, every label, heading, overline,
button and table header renders **Bold**, and caption/numeric render Regular.

## 3. Colours

Figma variable values on the node, against `static/backoffice/tokens/primitive.css`
(lines 47–57) and the aliases in `semantic.css`:

| Figma variable | Figma hex | Repo primitive | Match |
| --- | --- | --- | --- |
| `neutral-800` | #1f2330 | `--color-neutral-800: #1F2330` (line 56) | yes |
| `neutrals-700` | #2f3442 | `--color-neutral-700: #2F3442` (line 55) | yes |
| `neutral-600` | #4e5361 | `--color-neutral-600: #4E5361` (line 54) | yes |
| `neutral-500_` | **#646a78** | `--color-neutral-500: #6F7482` (line 53) | **no** — Figma is one step darker |
| `neutrals-50` | #f7f7f8 | `--color-neutral-50: #F7F7F8` (line 48) | yes |
| `brand-400` | #90003f | `--color-brand-400: #90003F` (line 36) | yes |

Which colour each style gets:

| Role | Figma revised | Branch alias (`semantic.css`) | `origin/main` alias |
| --- | --- | --- | --- |
| display-* | neutral-800 | `--color-headings` = neutral-**900** (#12141C) | neutral-700 |
| heading-* | neutral-**700** | `--color-headings` = neutral-900 | neutral-700 |
| body-*, table-*, numeric, label-* | neutral-700 | `--color-body-text` = neutral-**800** | neutral-600 |
| caption, overline | neutral-600 | `--color-secondary-text` = neutral-600 | neutral-500 |
| input-text | neutral-800 | `--color-body-text` = neutral-800 | neutral-600 |
| placeholder | neutral-500 (#646a78 in Figma) | `--color-placeholder-text` = neutral-500 (#6F7482) | neutral-400 |

So the branch went one step darker than the revision on body text (800 vs
700) and on headings (900 vs 800/700), and the revision splits what the code
treats as one `--color-headings` token into two (display = 800, heading = 700).

## 4. Things the Figma node does not say

- No `button-md`, `button-sm` or `code` style; the CSS has them and the
  showcase lists them.
- No italic, no 300/900.
- Component-level overrides in `main.css` that are not part of either scale:
  `.dialog-title` (500 · 20/28, line 1226), `.dialog-text-stack__title`
  (700 · 18/28, line 1383), `.tab-item-selected` (700, line 796),
  `.target-source-row__unlinked` (600, line 1030), the stepper's active/error
  labels (500, lines 906/921), the visual editor's h1–h3/th (700, lines
  1703–1757). The Figma components (her 10-26 comment) may define these; the
  typography node does not.
- Whether `overline` is meant to be lowercase (the sample node is) or
  uppercase (the CSS is).
- Whether the Hungarian UI is in scope: the shipped Lato files have no ő/ű
  (see `fonts.md`), so any scale decision also decides the fallback glyphs.
