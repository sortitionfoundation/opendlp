# sc-970 · Font fact sheet: Lato in the backoffice

Facts as of 2026-11-06 on branch `970-text-bigger-darker`, after the switch from
the two Lato 1.104 files to four Lato 2.015 files. Section 7 keeps what the
branch shipped before the switch, because the review discussion refers to it.

## 1. What the branch ships

- **Four faces, one per weight.** `static/backoffice/tokens/primitive.css`
  declares four `@font-face` rules, all family `"Lato"`, `font-style: normal`,
  `font-display: swap`, no `unicode-range`, no italic:

  | Weight | File (`static/backoffice/fonts/`) | Bytes |
  | --- | --- | --- |
  | 400 | `LatoLatin-Regular.woff2` | 43,760 |
  | 500 | `LatoLatin-Medium.woff2` | 43,920 |
  | 600 | `LatoLatin-Semibold.woff2` | 44,356 |
  | 700 | `LatoLatin-Bold.woff2` | 44,380 |

  ≈176 KB for the four, against 46.6 KB for the two files before. A page
  downloads only the faces its text uses.
- **Licence beside the files.** `static/backoffice/fonts/OFL.txt` is the SIL
  Open Font License 1.1 text from the kit (copyright Łukasz Dziedzic, Reserved
  Font Name "Lato"), with its CRLF line endings and one trailing space
  normalised to the repo's whitespace rules; the text is unchanged. `docs/frontend_build.md` ("The backoffice font is
  committed, not built") records the source, the version and how to upgrade.
- **The 1.104 files are gone.** `lato-latin-400-normal.woff2` and
  `lato-latin-700-normal.woff2` were referenced only by `primitive.css`; both
  are deleted. The new files have new names, and the font URLs carry no
  cache-busting hash, so no browser can pair a cached old file with the new
  rules.
- **Where it is loaded: unchanged.** `templates/backoffice/base.html` loads
  `primitive.css` then `semantic.css`; every backoffice page inherits it, and
  so do the login, register, 2FA and password pages through
  `templates/public/base.html`. The GOV.UK pages keep GDS Transport from
  `static/fonts/`.
- **How it is served: unchanged.** WhiteNoise (`extensions.py`), default
  `Cache-Control: max-age=60, public`. The files are committed (the
  `.gitignore` comment lists `static/backoffice/fonts/*` as maintained), so
  Docker and CI ship them with no build step.
- **No third party.** No Google Fonts URL anywhere in `templates/`,
  `static/backoffice/` or `src/scss`; `font-src 'self'` in the CSP
  (`flask_app.py`) already covers the files. The `fonts.googleapis.com` /
  `fonts.gstatic.com` CSP entries are for organiser-pasted registration HTML
  (`9f31a8fd`) and are untouched.
- **Comments corrected.** The `primitive.css` header and the showcase line
  (`templates/backoffice/showcase/typography.html`) said the files came from
  @fontsource and that 500/600 were "browser-synthesised"; both now describe the
  four files.
- **`@fontsource/lato` in `package.json`** supplied the two old files (copied by
  hand) and now supplies nothing; no script, config or template refers to it.
  Removing the dependency is a separate clean-up.

## 2. Source and verification

- **Kit.** latofonts.com download page → `/files/Lato2OFLWeb.zip` (one
  redirect to the site's file bucket), fetched 2026-11-06: 22,791,538 bytes,
  sha256 `6f6b564ce12f105744d8e8b438152a458a99797cb323faf026483174f8144e6e`,
  the same bytes as a download on 2026-11-02; `unzip -t` clean.
  `README-WEB.txt`: "Version 2.015; Latin+Cyrillic+Greek+IPA opensource",
  "Licensed under the SIL Open Font License, Version 1.1".
- **Files.** Copied unchanged from `Lato2OFLWeb/LatoLatin/fonts/`:

  | File | sha256 |
  | --- | --- |
  | `LatoLatin-Regular.woff2` | `ddd4ef7f97f4361b60841d59753218a57134b0f99f5b46a9612234f1c2733ab0` |
  | `LatoLatin-Medium.woff2` | `60593ef08991381d651875bc78e259b2b66938e1b66175a445a7fefdb46e3d78` |
  | `LatoLatin-Semibold.woff2` | `267eef3001852f3fb5fa919e9ecaf8885ed9232e08dfa9b6e3a8547ebfd47907` |
  | `LatoLatin-Bold.woff2` | `276401632a998400be8a5895038f4f72d3760d3c3d6aaf3cf445d109cb9d1540` |

- **What fontTools reads.** Name table "Version 2.015; 2015-08-06",
  `head.fontRevision` 2.015; `usWeightClass` 400/500/600/700; 467, 467, 465 and
  467 glyphs, 392 code points each. All Hungarian letters are mapped, ő ű Ő Ű
  included. Copyright "2011-2015 by tyPoland Lukasz Dziedzic ... with Reserved
  Font Name 'Lato'. Licensed under the SIL Open Font License, Version 1.1".
- **Licence terms that matter here.** Free for commercial use, self-hosting and
  bundling; the licence text travels with the files; the fonts may not be sold
  on their own; a modified version (a self-made subset counts) may not carry
  the name "Lato". `LatoLatin` is the author's own subset, used unmodified.
- **Vertical metrics.** The hhea, OS/2 typo and win values are identical in
  1.104 and 2.015 (ascent 1974, descent 426 on a 2000 em). 2.015 sets the
  `USE_TYPO_METRICS` bit and 1.104 did not; renderers on Windows honour it, so
  text may sit slightly differently in its line box there. macOS uses the hhea
  values either way. Not measured on Windows.

## 3. Which weights the CSS asks for

Type classes, `static/backoffice/src/main.css` (`@utility` blocks):

| Weight | Classes |
| --- | --- |
| 400 | body-lg, body-md, body-sm, caption, input-text, table-cell, code |
| 500 | heading-md, heading-sm, overline, label-lg, label-md, numeric |
| 600 | display-md, display-sm, heading-lg, button-lg, button-md, button-sm, table-header |
| 700 | display-lg |

Component rules with their own weight: `.btn` 600, `.tab-item` 400,
`.tab-item-selected` 700, the stepper's active/error label 500,
`.target-source-row__unlinked` 600, `.dialog-title` 500,
`.dialog-text-stack__title` 700, the visual editor's h1/h2/h3/th 700,
`.info-toggletip__bubble` 400. Templates (`templates/backoffice`,
`templates/public`): Tailwind `font-medium` ×12, `font-semibold` ×30,
`font-bold` ×12, `font-normal` ×1, inline `font-weight: 700` ×3. No rule or
template sets 100, 300, 800 or 900, so the four files cover every declared
weight. (A `<strong>` inside 600 text computes to 900 through `bolder` and gets
the 700 face, as it did before.)

## 4. What each weight renders as now

Measured in the running app (headless Chromium, `/backoffice/showcase`, the
sample "Hamburgefonstiv 0123456789" at 64px in `var(--font-sans)`):

| Requested | 300 | 400 | 500 | 600 | 700 | 900 |
| --- | --- | --- | --- | --- | --- | --- |
| Width (px) | 872.27 | 872.27 | 874.44 | 876.75 | 880.67 | 880.67 |

400, 500, 600 and 700 each use their own face (`document.fonts` reports all
four `Lato` faces `loaded`); 300 and 900, which nothing asks for, fall back to
400 and 700 as CSS font matching prescribes. On screen: everything declared 500
(heading-md/sm, overline, labels, numeric) is now Medium where it rendered
Regular, and everything declared 600 (display-md/sm, heading-lg, buttons, table
headers) is now Semibold where it rendered Bold.

## 5. Hungarian

ő and ű now come from Lato in every weight. Before, the 1.104 files (an
@fontsource `latin` subset) had no U+0150/0151/0170/0171, and with no
`unicode-range` the browser drew those letters from the fallback `sans-serif`,
one glyph at a time; 530 `msgstr` lines in
`translations/hu/LC_MESSAGES/messages.po` contain ő or ű.

## 6. The claim "Google Fonts serves Lato only at 100/300/400/700/900"

True (checked against the css2 API on 2026-11-02: `wght@500` and `wght@600`
return HTTP 400), and moot: this repo requests no Google Fonts URL. Google
Fonts and @fontsource carry Lato 1.x; Lato 2.0, with Medium, Semibold and the
wider character set, is what the author distributes at latofonts.com.

## 7. Before the switch (for the record)

- Two `@font-face` rules, 400 and 700, pointing at
  `lato-latin-{400,700}-normal.woff2`: Lato "Version 1.104; Western+Polish
  opensource", 224 glyphs each, byte-identical to `@fontsource/lato` 5.3.0's
  files.
- By CSS font matching a request for 500 took the 400 face and a request for
  600 the 700 face; the measured widths at 300/400/500 were identical, as were
  those at 600/700/900. The old comment's "browser-synthesised" was the wrong
  mechanism: synthetic bold applies only when no face at or above 600 exists.
- Limiting the scale to 400/700 was the alternative considered. It would have
  changed nothing on screen (the declarations would have matched what rendered)
  and would have left ő/ű in the fallback font.
