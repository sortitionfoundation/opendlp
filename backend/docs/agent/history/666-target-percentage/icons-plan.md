# Icons: one home, one showcase, one decision still to make

**Issue:** none yet — the question arose while reviewing `666-target-percentage`
**Branch:** proposed `icons-consolidation`, **not** `666-target-percentage`
**Status:** ✅ PHASE 1 IMPLEMENTED on `666-target-percentage`; ✅ PHASE 2 IMPLEMENTED on `icon-set-fix` — see §9
**Date:** 2026-08-27, phase 1 implemented 2026-08-27, phase 2 implemented 2026-09-03

## Scope of this document

Two phases, deliberately separated:

- **Phase 1** moves every UI icon into one file and builds a showcase page that
  displays *all* of them, including the near-duplicates, grouped by concept.
  It changes no pixels. Its purpose is to make the inconsistency visible enough
  for the team to decide about.
- **Phase 2** converges on one icon family and deletes the duplicates. It is
  **blocked** until the designer has decided which family we standardise on.

Phase 1 does not pre-judge phase 2. Nothing in it commits us to Lucide,
Heroicons or anything else.

---

## 1. What exists today

68 inline `<svg>` elements across `templates/`, forming **40 distinct shapes**.
Only about 20 sit behind a macro; the rest are copy-paste. Icon macros are
currently spread across four files:

| File                                        | Macros                                                                                                |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `backoffice/components/_nav_icons.html`     | `icon_question_circle`, `icon_user`, `icon_switch`, `icon_data_agreement`, `icon_about`, `icon_logout`, `icon_chevron_down`, `icon_arrow_back` |
| `backoffice/registration/_assets.html`      | `icon_plus`, `icon_info`, `icon_copy`, `icon_trash`                                                   |
| `backoffice/targets/bulk_edit_form.html`    | `icon_undo`, `icon_chevron_down`, `icon_chevron_up`, `icon_bin`                                       |
| `backoffice/components/modal.html`          | `dialog_close_icon`                                                                                    |

Note `icon_chevron_down` is defined **twice**, with different bodies.

### 1.1 The same concept, drawn more than once

This is the finding that matters. These are not code duplicates to be tidied
away — they are the same idea rendered in different visual languages, on
different pages of the same product.

| Concept       | Glyphs | Where                                                                                                                                                                                                 |
| ------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Info**      | **3**  | Lucide circle-i in `components/info_icon.html`; Heroicons v1 in `registration/_assets.html:16` (as `icon_info`) **and raw** in `assembly_respondents.html:44`, `assembly_targets.html:42`, `respondent_field_schema/view.html:38`; Lucide help-circle in `_nav_icons.html:7` |
| **Delete**    | **3**  | Heroicons outline `icon_trash` (`_assets.html:26`); Material **filled** `icon_bin` (`targets/bulk_edit_form.html:34`); Lucide trash-2 raw in `showcase/button_component.html:31`                       |
| **Tick**      | **3**  | Heroicons `M5 13l4 4L19 7` ×4 (`assembly_data.html:306,355,477`, `url_display.html:30`); a 20-box polyline in `stepper.html:95,124`; a 12-box tick in `input.html:322`                                 |
| **Plus**      | **2**  | Heroicons `icon_plus` (`_assets.html:11`); Lucide plus raw in `showcase/button_component.html:24`                                                                                                       |
| **Warning**   | **2**  | Heroicons triangle in `assembly_registration.html:41`; a 20-box triangle in `stepper.html:97,126`                                                                                                       |
| **Download**  | **2**  | `assembly_selection.html:227`; `registration/_step_preview.html:81` — different paths, same meaning                                                                                                     |
| **Chevron ↓** | **1**  | but **6 copies at two stroke widths**: sw2 in `_nav_icons.html:55`, `account_menu.html:46`, `dropdown_button.html:58`, `split_button.html:63`, `showcase/button_component.html:18`; sw1.5 in `bulk_edit_form.html:22` |

The 20-box and 12-box variants (stepper, checkbox) are sized for a specific
slot, so their divergence **may be justified** — that is a question for the
designer, not an assumption for us to make.

### 1.2 Straight duplication, no ambiguity

| Glyph                | Copies | Where                                                                                                          |
| -------------------- | ------ | ---------------------------------------------------------------------------------------------------------------- |
| Copy-to-clipboard    | 3      | `components/url_display.html:26`, `_assets.html:21`, `registration/_step_email.html:173`                        |
| ~~Import arrow~~     | 3      | **Not icons.** See the correction in §8 — these are GOV.UK pagination markup                                    |
| ~~Export arrow~~     | 3      | **Not icons.** See the correction in §8                                                                        |
| Spinner              | 2      | `components/modal.html:296`, `components/search_dropdown.html:96`                                              |
| Google brand mark    | 4      | `auth/login.html:43`, `auth/register.html:24`, `auth/register_google.html:57`, `profile/view.html:105`         |
| Microsoft brand mark | 4      | `auth/login.html:75`, `auth/register.html:56`, `auth/register_microsoft.html:57`, `profile/view.html:170`      |

### 1.3 There is no rule to break

Nothing in `docs/agent/frontend_design_system.md`, `docs/frontend_build.md`,
`docs/agent/component_accessibility.md` or the `sf-code-review` skill says a
word about icons. Drawing a fourth info circle currently violates nothing.

---

## 2. Decisions

### D1 — A new `backoffice/components/icons.html`, not `_assets.html`

`_assets.html` is a feature partial in `backoffice/registration/`. Its leading
underscore matches its neighbours (`_step_form.html`, `_modals.html`) and means
"private to this feature". Its public surface is five `asset_*` macros,
imported by `_step_form.html` and `_modals.html` and nowhere else. Making
`targets/`, `admin/` and `main/` import it to draw a bin points the dependency
the wrong way, and would grow a 346-line file into a grab-bag.

**What is left in `_assets.html` after the move is coherent:** imports, five
private helpers (`info_note`, `icon_button`, `readonly_copy_row`,
`required_text_field`, `inline_error`), and the five public `asset_*` macros.
That matches its ABOUTME exactly. Two follow-ons:

- `info_note` gains an import of `icon_info` from `icons.html`.
- `icon_button` is a `{% call %}` button wrapper, **not** an icon. Beside an
  `icons.html` import it will read as one. Renaming it `asset_icon_button` is
  recommended but optional — it is used only within its own file.

### D2 — Not everything with a `<svg>` tag is an icon

Three categories stay where they are:

| Category          | Items                                                                                                      | Why                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| **Brand marks**   | Google ×4, Microsoft ×4                                                                                     | Trademarks, must stay pixel-exact to brand guidelines. Own file: `components/brand_marks.html` |
| **Product logo**  | `sortition_logo` in `components/navigation.html:6`                                                          | One use, not an icon                                          |
| **Illustrations** | flow arrows in `service_docs/_registration.html:40,60`; decorative chevrons in `main/index.html:18,32`      | Diagram parts, sized and shaped for their diagram             |

Also excluded: the `<svg>` inside the docstring at `components/button.html:45`,
which is example text, not markup.

**Test for inclusion:** does the glyph name an action or a status? Then it is an
icon.

That leaves roughly **34 macros covering 54 call sites**. In the event: **32
macros in `icons.html` and 2 in `brand_marks.html`, covering 54 call sites**,
with 12 raw `<svg>` elements deliberately left in place (§8).

### D3 — Phase 1 keeps existing macro names wherever it can

The temptation is to rename everything to a concept scheme at the same time.
Resist it: that folds the design decision into the mechanical move, and makes
the diff unreviewable. Phase 1 should be as close to pure motion as possible so
a reviewer can confirm nothing changed visually.

Two collisions force a decision even so:

- **`icon_chevron_down` ×2.** Same glyph at sw2 and sw1.5. It is genuinely one
  icon at two weights, so: `icon_chevron_down(classes="w-4 h-4", stroke_width="2")`.
  The one sw1.5 call site in `bulk_edit_form.html` passes `stroke_width="1.5"`.
- **Info.** `icon_info` (Heroicons, in `_assets.html`) collides conceptually
  with the Lucide glyph inside `info_icon()`. Suffix both by family for the
  interim: `icon_info_heroicons`, `icon_info_lucide`.

**Rule:** where one concept has more than one glyph, suffix each with its family
(`_lucide`, `_heroicons`, `_material`) — or, where the drawings come from the
same family and differ only in the grid they are built on, with that grid size
(`_20`, `_16`, `_12`). Where a concept has exactly one glyph, keep its current
name. Phase 2 drops every suffix. The suffixes are ugly on
purpose — they are a to-do list visible at every call site.

### D4 — Wrapper components stay put and import from `icons.html`

`info_icon()`, `provenance_icon()` and `dialog_close_icon()` are not icons.
They are labelled-tooltip and button components that happen to contain one.
They keep their homes and their behaviour; only their `<svg>` moves.

### D5 — The showcase page shows the duplicates, it does not hide them

This is the point of phase 1. See §4.

---

## 3. Phase 1 — the move ✅ DONE

No visual change. Every rendered page must be byte-identical apart from
whitespace.

1. Create `templates/backoffice/components/icons.html` with a two-line ABOUTME
   and the ~34 macros, grouped by concept with section comments. Uniform
   signature `icon_name(classes="w-4 h-4")`; every `<svg>` carries
   `aria-hidden="true"` (the accessible name belongs to the wrapping control,
   per `docs/agent/component_accessibility.md`). Standardise on `w-4 h-4`
   ordering — `_assets.html` currently writes `h-4 w-4`.
2. Create `templates/backoffice/components/brand_marks.html` for the Google and
   Microsoft marks; point the four auth/profile templates at it.
3. Delete `components/_nav_icons.html`; move its eight macros in. Update
   `base_page.html`, `components/navigation.html`, `components/page_header.html`
   and the two showcase pages.
4. Move the four `_assets.html` icons; drop its ICONS section header; add the
   `icons.html` import for `info_note`.
5. Move the four `bulk_edit_form.html` icons; `icon_bin` becomes
   `icon_trash_material`.
6. Move `dialog_close_icon`'s `<svg>` into `icons.html` as `icon_close`;
   `dialog_close_icon` stays in `modal.html` and calls it.
7. Replace the raw inline SVGs at every site listed in §1.1 and §1.2 with macro
   calls.
8. `just build-all && just test-js && just test-nobdd && just test-bdd-headless`,
   then a visual check of the showcase, targets, registration editor, account
   menu and the OAuth login page.

**Ordering note:** step 7 is the bulk of the diff and is mechanical. Consider
splitting the commit at the `backoffice/` boundary so the `auth/`, `admin/`,
`main/` and `respondents/` templates land separately — they are outside the
backoffice design system and are the ones most likely to want a second look.

## 4. Phase 1 — the showcase page ✅ DONE

`templates/backoffice/showcase/icons.html`, wired into the showcase index
alongside the existing 28 component pages.

**It shows every glyph, including all the duplicates.** Grouped by *concept*,
not by file, so that "three different bins" is the first thing a reader sees.

For each glyph:

- rendered at 16px and 24px, on both light and dark backgrounds
- the macro name, copy-pasteable
- the family label (Lucide / Heroicons v1 / Material / unknown), stroke width,
  and viewBox
- **every call site**, as `file:line`

For each concept group with more than one glyph, a highlighted note naming the
question — e.g. *"Delete: 3 glyphs. Heroicons outline in the registration
editor, Material filled in targets, Lucide in the showcase only. Which?"* —
and, where relevant, the case for the divergence being deliberate (the 20-box
stepper tick and 12-box checkbox tick are sized for their slots).

That page is the artefact the designer reviews. It should be readable by
someone who has never opened a Jinja template.

## 5. Phase 2 — converge (✅ DONE, see §9)

Blocked on the designer choosing a family. Once chosen:

1. Delete the losing glyphs; drop every `_lucide` / `_heroicons` / `_material`
   suffix; update call sites.
2. Decide the stepper and checkbox tick question — one glyph scaled, or
   genuinely two.
3. Revisit whether `icon_question_circle` and the info glyph should remain
   distinct.
4. Rebuild the showcase page without the "needs a decision" notes.

**For the record, the headcount favours Lucide** — all eight nav icons, the
`info_icon` component and both `provenance_icon` glyphs are Lucide, and it is
the set that looks deliberately chosen rather than reached for. But a headcount
is a weak argument and loses to whatever the Figma design system specifies.

## 6. Enforcement ✅ DONE EARLY

A doc paragraph will not hold. There is exact precedent in
`tests/unit/test_design_tokens.py`, which fails the build on a `var(--...)`
that no token file defines.

`tests/unit/test_icons.py` now does the same for icons: a raw `<svg` in any
template outside `backoffice/components/icons.html`,
`components/brand_marks.html` and a short explicit allowlist fails, and a
stale allowlist entry fails too. Every allowlist entry carries its reason. It
also asserts that every icon macro is `aria-hidden`.

**This was planned for after phase 2 and landed in phase 1 instead**, because
phase 1 already reached the clean state and there was no reason to leave it
unguarded while the family question is open. `tests/component/`
`test_backoffice_general.py` additionally asserts the showcase lists every
macro in the set, which renders all 32 through a real route.

Still to do, and still after phase 2 — the documentation:

- a section in `docs/agent/frontend_design_system.md` — where icons live, the
  house family, the `icon_name(classes)` signature, `aria-hidden` on the glyph
  and the accessible name on the control, and the "action or status → icon"
  test from D2
- a bullet in `.claude/skills/sf-code-review/SKILL.md`

## 7. Open questions for the team

1. **Which family?** Blocks phase 2 entirely.
2. **Is the small-viewBox divergence deliberate?** The stepper's 20-box tick and
   triangle and the checkbox's 12-box tick are drawn for their slots. Keep, or
   scale one glyph?
3. ~~**Does phase 1 cover `auth/`, `admin/`, `main/` and `respondents/`, or
   backoffice only?**~~ Settled by §8: `admin/`, `main/` and `respondents/`
   turned out to hold nothing but GOV.UK pagination markup, so phase 1 covers
   the backoffice plus the `auth/` and `profile/` brand marks, which landed in
   their own commit.
4. **Rename `icon_button` to `asset_icon_button`?** (D1) Left alone in phase 1,
   since it was an open question rather than a decision.
5. **Should this doc live under `666-target-percentage/`?** It is filed there
   because that is where the question came up, but the work is unrelated to
   target percentages. It probably wants its own folder once it has an issue
   number.

---

## 8. What actually happened, and where it departed from the plan

Phase 1 is on `666-target-percentage` in two commits: `fb3d0adf` (brand marks)
and `cd6668c0` (the backoffice set, the showcase page and the tests).

### 8.1 A correction to §1.2

**The "import arrow" and "export arrow" rows were wrong.** Identified from path
data alone, they looked like two icons copied three times each. They are in fact
`govuk-pagination__icon--prev` and `--next`: GOV.UK Frontend's own pagination
markup, hand-rolled in three templates. They are not ours to restyle, so they
are excluded and allowlisted.

That leaves a **separate finding, out of scope here**: `admin/users.html`,
`main/view_assembly_data.html` and `respondents/view_respondents.html` each
hand-roll a GOV.UK pagination block rather than using
`backoffice/components/pagination.html`. Worth its own issue.

### 8.2 Deviations

| Deviation | Why |
| --------- | ---- |
| Enforcement test landed now, not after phase 2 (§6) | Phase 1 reached the clean state; leaving it unguarded for the length of a design decision invites regressions |
| Suffix rule extended to grid sizes (D3) | The tick, warning and download duplicates differ by viewBox, not family, so `_20` / `_16` / `_12` says more than a family label would |
| The showcase page uses no `gettext` | Every other `backoffice/showcase/*.html` template writes plain English. Consistency with the surrounding code beat the general i18n rule, and it keeps paragraphs about icon families — most of which phase 2 deletes — out of the translation catalogue |
| "Light and dark backgrounds" became one inverted swatch | The backoffice has no dark theme at all. The swatch uses the `--color-neutral-800` primitive; there is no semantic dark-surface token and inventing one for a showcase page is not this branch's business |
| `xmlns` added where a few inline SVGs lacked it | Inert for inline SVG in HTML, and it makes the file uniform |
| `stroke-width` moved from `<svg>` to `<path>` on the warning glyph | It inherits, so the rendering is identical |
| `icon_button` not renamed | It is open question 4, not a decision |

### 8.3 A new finding

**`icon_about` is drawn by nothing.** It came across with the rest of the
account menu set from `_nav_icons.html` and has no call site anywhere. It is
kept, flagged on the showcase page, and raised there as a question — deleting it
is the team's call, not a refactor's.

### 8.4 Verification

`prek run --all-files`, `mypy`, `deptry`, the UnitOfWork checker and
`uv lock --locked` all pass. `just test-js` (423), `just test-nobdd` (4570) and
`just test-bdd-headless` (159 passed, 5 pre-existing skips) are green. The
showcase Icons section and the OAuth sign-in page were checked visually in a
real browser.

Note for whoever picks up phase 2: `just check` could not run as written in this
environment — `uv tool run prek` needs to write to a read-only tools directory.
Running `prek run --all-files` plus the other four commands directly is
equivalent.

---

## 9. Phase 2 — what was decided and done (branch `icon-set-fix`, 2026-09-03)

The blocking question resolved itself: the designer published the icon set on
the "Icons" sheet of the OpenDLP - UI Figma file (node `5032:8946`, 1,767
glyphs), and it is **Lucide** — current Lucide, post-rename names like
`circle-question-mark` and `triangle-alert`. That also matches the §5
headcount. Every 24-grid macro body in `icons.html` was replaced with the SVG
exported from that sheet (via the Figma MCP asset endpoint), so the file now
matches the design source verbatim rather than approximately.

Decisions taken against the open questions in §7:

1. **Family: Lucide** (the Figma sheet). Every Heroicons/Material/Tailwind
   glyph was deleted or replaced. All `_lucide`/`_heroicons`/`_material`
   suffixes are gone: `icon_info`, `icon_plus`, `icon_trash` (the Lucide
   `trash-2` drawing, with the inner lines).
2. **Small-viewBox divergence: kept, declared deliberate.** `icon_check_20`,
   `icon_warning_20` and `icon_check_12` are drawn to fill the stepper bubble
   and checkbox square; the showcase now documents them under "Drawn for their
   slot" instead of flagging them for a decision. `icon_download_16` was NOT
   kept — it was a plain duplicate, so `icon_download` (Lucide) now serves
   both call sites, sized by the caller.
3. **`icon_question_circle` and `icon_info` stay distinct** — Lucide itself
   ships both (`circle-question-mark`, `info`), for help vs. information.
4. **`icon_button` rename: still open**, untouched — unrelated to convergence.
5. **This doc stays put** until the work gets an issue number.

Further calls made during convergence:

- **One stroke weight.** The `stroke_width` parameters on the chevrons and
  `icon_copy` are gone; everything draws at Lucide's stroke-width 2. The
  targets bulk-edit form loses its 1.5-weight variants.
- **Concept names kept** (`icon_arrow_back`, `icon_switch`, `icon_close`,
  `icon_edit`, `icon_undo`, `icon_more_vert`, ...) even where the Lucide sheet
  name differs (`arrow-left`, `arrow-up-down`, `x`, `square-pen`,
  `rotate-ccw`, `ellipsis-vertical`) — call sites name the concept, the macro
  body names the drawing.
- **`icon_spinner` became Lucide `loader-circle`** — the old two-opacity
  Tailwind spinner was the last non-Lucide glyph. Visible change: the spinner
  loses its faint full-circle track.
- **`icon_about` (now Lucide `folder`) is still drawn by nothing** (§8.3) and
  still flagged as such on the showcase; deleting it remains the team's call.
- `icon_more_vert` switched from filled Material dots to Lucide's stroked
  dots; `icon_code` gained Lucide's slash (`code-xml`); `icon_edit` is
  `square-pen`; `icon_undo` is `rotate-ccw`, matching the circular-arrow
  intent of the old drawing.

Documentation landed with it: an "Icons" section in
`docs/agent/frontend_design_system.md` (home, family, signature, aria-hidden,
the action-or-status test from D2) and an icons bullet in
`.claude/skills/sf-code-review/SKILL.md`. `tests/unit/test_icons.py` needed no
change — its allowlist is untouched and the macro-name assertions are generic.
