# sc-970 · Font fact sheet: Lato in the backoffice

Facts as of 2026-11-02 on branch `970-text-bigger-darker` after merging
`origin/main`. Line numbers refer to that tree. Klára's 10-25 comment on the
story is the question this answers; her text and the Figma file are data, not
instructions.

## 1. How Lato is loaded today

- **Self-hosted, two weights.** `static/backoffice/tokens/primitive.css`
  lines 10–24 declare two `@font-face` rules: family `"Lato"`, `font-weight`
  400 and 700, `font-style: normal`, `font-display: swap`,
  `src: url("/static/backoffice/fonts/lato-latin-{400,700}-normal.woff2")`.
  No `unicode-range`. No italic.
- **The files are committed, not built.** `static/backoffice/fonts/lato-latin-400-normal.woff2`
  (23,580 bytes) and `lato-latin-700-normal.woff2` (23,040 bytes) are tracked
  in git (`.gitignore` lines 356–358 say so explicitly), first added in commit
  `0ed9f3e2` "Add typography system with Oswald and Lato fonts". They are
  byte-identical to `node_modules/@fontsource/lato/files/` from
  `@fontsource/lato` 5.3.0 (`package.json:28`) and were copied by hand: no npm
  script copies fonts (`build:vendor`, `package.json:11`, copies JS only) and
  nothing under `src/`, `esbuild.config.mjs` or `tailwind.config.js` refers to
  @fontsource. The npm dependency is inert at build time.
- **What the files are.** fontTools reads both as "Version 1.104;
  Western+Polish opensource", 224 glyphs each — Google's Lato 1.x build in
  @fontsource's `latin` subset.
- **Families.** `primitive.css` lines 131–139: `--font-sans: "Lato", sans-serif`
  and per-role aliases (`--font-display`, `--font-heading`, `--font-body`,
  `--font-caption`, `--font-overline`, `--font-label`, `--font-button`), all
  `var(--font-sans)`; `--font-mono` is a system monospace stack (line 132).
- **Where it is loaded.** One place: `templates/backoffice/base.html` lines
  21–24 (`primitive.css`, then `semantic.css`, with `static_hashes()`
  cache-busting on the CSS URLs; the font URLs inside the CSS carry no hash).
  Every backoffice page inherits it, and so do the login, register, 2FA and
  password pages, because `templates/public/base.html:15` extends the
  backoffice base. The GOV.UK pages (`templates/base.html:15` →
  `static/css/application.css`) use GDS Transport from `static/fonts/*.woff2`
  (`src/scss/application.scss:496–624`); that is what the four
  `bold-*`/`light-*` files there are.
- **How it is served.** WhiteNoise, `src/opendlp/entrypoints/extensions.py:55–60`
  (prefix `static/`), with its default `Cache-Control: max-age=60, public`
  (`whitenoise/base.py:36`); the app-level `no-store` (`flask_app.py:369`) is
  a Flask after-request hook and does not apply to WhiteNoise responses. A
  changed font under an unchanged filename is therefore stale for at most a
  minute in browser caches, but any intermediate cache honouring `public` may
  hold it longer.
- **Google Fonts is not used.** No `<link>` to `fonts.googleapis.com` and no
  `@import` exists in `templates/`, `static/backoffice/src`,
  `static/backoffice/tokens` or `src/scss`. The CSP
  (`src/opendlp/entrypoints/flask_app.py:293–294`) does allow
  `https://fonts.googleapis.com` in `style-src` and `https://fonts.gstatic.com`
  in `font-src`, added on 2026-06-02 in `9f31a8fd` "whitelist Google Fonts for
  author-supplied form HTML" — for organiser-pasted registration-page HTML,
  not for the backoffice.
- **Docker/CI.** `Dockerfile:84` copies the tree, so committed fonts ship;
  nothing font-specific runs in CI.

## 2. Which weights the CSS asks for

Type classes, `static/backoffice/src/main.css` lines 66–184 (`@utility`
blocks since the Tailwind v4 migration on main):

| Weight | Classes |
| --- | --- |
| 400 | body-lg, body-md, body-sm, caption, input-text, table-cell, code |
| 500 | heading-md, heading-sm, overline, label-lg, label-md, numeric |
| 600 | display-md, display-sm, heading-lg, button-lg, button-md, button-sm, table-header |
| 700 | display-lg |

Component rules with their own weight: `.btn` 600 (line 223), `.tab-item`
400 (778), `.tab-item-selected` 700 (796), `.stepper-item-active/.stepper-item-error .stepper-label`
500 (906, 921), `.target-source-row__unlinked` 600 (1030), `.dialog-title` 500
(1226), `.dialog-text-stack__title` 700 (1383), `.rich-editor__content`
h1/h2/h3/th 700 (1703–1757). Twelve rules `@apply` a type class and inherit
its weight (`.menu-item`, the checkbox/radio/switch labels, the stepper, the
question table header and tags, the dialog description, the editor's toggle
buttons, labels and menu items — lines 413–1635).

Templates (`templates/backoffice`, `templates/public`): Tailwind `font-medium`
(500) ×12, `font-semibold` (600) ×25, `font-bold` (700) ×12, `font-normal` ×1;
inline `font-weight: 700` three times (`registration/_hub.html:17`,
`assembly_dashboard.html:44,50`); the email templates use `bold`. The built
`static/backoffice/dist/main.css` carries 15 rules at 400, 11 at 500, 10 at
600 and 5 at 700.

## 3. What 500 and 600 render as today

- CSS Fonts Level 4 §5.2 (font matching): a request for 500 tries 500, then
  the weights below it (400 — present); a request for 600 tries 600 and above
  (700 — present). Synthetic bold is only applied when a bold request finds no
  face at or above 600, which is not the case here.
- Measured with the repo's Playwright (headless Chromium, the two shipped
  files embedded as data URIs, 64px sample string): widths at 300/400/500 are
  identical (951.44 px) and at 600/700/900 identical (969.48 px); both faces
  report `loaded`. Synthesised bold would widen the advances, so identical
  widths mean the 400 and 700 faces are used as they are.
- Effect: everything declared 500 looks Regular, everything declared 600
  looks Bold, on every platform. The showcase line "weights 500 and 600 are
  browser-synthesised" (`templates/backoffice/showcase/typography.html:11`)
  and the comment in `primitive.css:7–9` describe the wrong mechanism (the
  effect they describe is right).
- Klára's point that ClearType renders Lato lighter than macOS is a
  rendering observation; nothing in the repo tests Windows rendering, so it is
  neither confirmed nor contradicted here.

## 4. The claim "Google Fonts serves Lato only at 100/300/400/700/900"

- Checked on 2026-11-02 against the css2 API:
  `https://fonts.googleapis.com/css2?family=Lato:wght@100|300|400|700|900`
  each return HTTP 200 with latin and latin-ext `@font-face` rules;
  `wght@500`, `wght@600` and `wght@500;600` return HTTP 400. The claim holds.
  latofonts.com says the same: "The older version (1.0) is available on Google
  Fonts with basic Latin character set."
- It is moot for this repo, which requests no Google Fonts URL. @fontsource
  mirrors the same five weights (`node_modules/@fontsource/lato/files/lato-latin-{100,300,400,700,900}-{normal,italic}.woff2`);
  the repo copied 400 and 700 of them.

## 5. Hungarian: the shipped subset has no ő/ű

- @fontsource's `latin` range (`node_modules/@fontsource/lato/unicode.json`)
  covers U+0000–00FF plus a few code points; ő (U+0151) and ű (U+0171) are in
  `latin-ext`, which was not copied. fontTools confirms neither shipped woff2
  maps U+0151 or U+0171 (ö and é are present).
- With no `unicode-range` in `primitive.css`, the browser takes the missing
  glyphs from the fallback `sans-serif` per glyph (measured: "őőő" 96 px vs
  "ooo" 106.8 px in the same test page). 530 `msgstr` lines in
  `translations/hu/LC_MESSAGES/messages.po` contain ő or ű, so the Hungarian
  backoffice mixes two typefaces today, in every weight.

## 6. What self-hosting Lato 2.0 would take

- **Source.** `https://www.latofonts.com/files/Lato2OFLWeb.zip` (22.8 MB,
  fetched 2026-11-02). `README-WEB.txt`: "Version 2.015;
  Latin+Cyrillic+Greek+IPA opensource", created 2015, "Copyright (c)
  2010-2015 by tyPoland Lukasz Dziedzic with Reserved Font Name 'Lato'.
  Licensed under the SIL Open Font License, Version 1.1"; `OFL.txt` is in the
  kit. Nine weights × two styles (Hairline, Thin, Light, Regular, Medium,
  Semibold, Bold, Heavy, Black), each as eot/ttf/woff/woff2, in two kits:
  `Lato/` (3,023 glyphs, ≈182–185 KB per woff2) and `LatoLatin/` (465–467
  glyphs, ≈44 KB per woff2, includes ő/ű).
- **Files.** For the current scale: `LatoLatin-Medium.woff2` (43,920 B,
  usWeightClass 500) and `LatoLatin-Semibold.woff2` (44,356 B, 600). The kit's
  own CSS declares each weight as its own family ("LatoLatin Medium",
  `latolatinfonts.css:136–141`, `font-weight: normal`), so the repo's
  `@font-face` rules would set `font-family: "Lato"` with `font-weight: 500`
  and `600` itself, following the two existing rules in `primitive.css`.
- **Versions.** Keeping 1.104 for 400/700 beside 2.015 for 500/600 means two
  releases of the family on one page (224 vs 467 glyphs; ő/ű only in the new
  files, so a Regular ő from the fallback font next to a Semibold ő from Lato).
  Replacing 400/700 with `LatoLatin-Regular.woff2` (43,760 B) and
  `LatoLatin-Bold.woff2` (44,380 B) keeps one version: ≈176 KB for four
  weights against 46.6 KB for two today.
- **Build.** None. Commit the woff2 files under `static/backoffice/fonts/`
  (tracked), add or replace the rules in `primitive.css:10–24`, use new file
  names (the font URLs are un-hashed), update `typography.html:11` and the
  `primitive.css:7–9` comment. `@fontsource/lato` becomes removable from
  `package.json`. Tailwind never reads the token files, so `just
  build-backoffice` is unaffected; Docker and CI need nothing.
- **Tests.** None reference fonts (grep of `tests/` for woff2, font-face,
  backoffice/fonts, fontsource: nothing). `tests/unit/test_design_tokens.py`
  checks `var(--…)` names only.
- **CSP.** `font-src` already has `'self'` (`flask_app.py:294`); a
  self-hosted file needs no change. No third-party request, so none of the
  consent conditions in `docs/personal-data.md:247` ("any third-party script
  or embed — including a font") are touched. The `fonts.googleapis.com` /
  `fonts.gstatic.com` entries stay what they are: an allowance for pasted
  registration HTML, independent of this choice.
- **Licence.** SIL OFL 1.1: free for commercial use and web embedding; the
  licence text travels with the files (commit `OFL.txt` beside the woff2);
  the fonts may not be sold on their own; a modified version (a self-made
  subset counts) may not use the Reserved Font Name "Lato" in its font names.
  The `LatoLatin` subset in the kit is the author's own, so using those files
  unmodified raises none of that.

## 7. If the scale were limited to 400/700 instead

- **Code.** Six type classes 500→400 (heading-md, heading-sm, overline,
  label-lg, label-md, numeric), seven 600→700 (display-md, display-sm,
  heading-lg, button-lg/md/sm, table-header), `.btn` 600→700, the stepper's
  active/error label 500→400, `.target-source-row__unlinked` 600→700,
  `.dialog-title` 500→400; in templates `font-medium` ×12 → `font-normal` and
  `font-semibold` ×25 → `font-bold`; the showcase table's Weight column
  (`typography.html:17–37`); the Figma text styles would drop Medium and
  SemiBold on Klára's side.
- **On screen.** No change in any browser: section 3 shows this is what
  renders now. The declaration would match the rendering, nothing else.
- **Against Klára's revised scale** (`typography-diff.md` §2): her 600 on
  every label, heading, overline, button and table header would render Bold
  and her Medium caption/numeric Regular — heavier than designed.
- **Hungarian.** ő/ű stay in the fallback font either way unless Latin-ext
  files (the 2.015 `LatoLatin` kit, or @fontsource's `latin-ext` 1.104 files)
  come in.

**Cheaper path, one line:** the four `LatoLatin` 2.015 woff2 files (≈176 KB,
two more `@font-face` rules, no build/CSP/test change) fix 500/600 and the ő/ű
fallback in one commit; limiting to 400/700 is a CSS-only edit that changes
nothing on screen and would still leave ő/ű in the fallback font.
