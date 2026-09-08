# Notes from the Hungarian `/gettext-auto hu` run

Working notes taken while running the `gettext-auto` skill over
`translations/hu/LC_MESSAGES/messages.po`. Nothing here was fixed _during_ the
translation pass — the skill's protocol says never touch a non-fuzzy entry and
never clear a fuzzy flag, so all of it was left alone deliberately and picked
up afterwards. Sections are marked FIXED as they are dealt with.

## 1. 80 duplicate msgids, and the catalogue did not compile — FIXED

`msgfmt -c` refused the file with 80 `duplicate message definition` errors, so
`just translate-compile` could not build a `.mo` and none of the Hungarian
reached users.

The diagnosis in the first draft of this note was wrong. There were **no
duplicates among live entries at all**. Every one of the 80 was a clash between
a live entry and an _obsolete_ (`#~`) entry carrying the same msgid — msgfmt
treats that as a fatal duplicate definition. So §1 and §1b were the same defect
wearing two hats.

That also explains the 41 `Refusing to overwrite clean translation` failures
during the run: `gettext-auto apply` looks an entry up by msgid, finds the
obsolete twin, sees it is not flagged fuzzy and refuses to write. The note's
original reassurance that "the clean twin is what a compiler would use anyway"
was therefore also wrong — an obsolete entry compiles to nothing, so those 41
were genuinely untranslated with a perfectly good Hungarian string sitting one
section further down the file.

The 80 broke down as:

- **41** live entries empty, obsolete twin translated.
- **22** live entries holding a bad fuzzy match — `Text` rendered as "Kezdés
  dátuma" (start date), `Targets Tab Name` as "Vezetéknév" (surname),
  `Task Type` as "Kész" (done). The obsolete text was right in every case.
  These are the same class of defect as §6.
- **16** already identical to their twin.
- **1** (`Sign out`) with a clean live translation, left alone.

Fixed by copying the obsolete translation onto its live twin, flagged fuzzy,
which is what `msgmerge` should have done. All 63 need review: some drifted
while obsolete, notably `The number of participants to select for this
assembly`, whose translation still opens with "Választható -" from an earlier
msgid that began "Optional -".

## 1b. 873 obsolete entries — FIXED

The catalogue carried **873** obsolete (`#~`) entries, not the 580 first
counted here (580 were untranslated; the rest carried the translations
recovered in §1). Removed with polib after the recovery, which also cleared
every duplicate from §1. `msgfmt -c` now passes and `pybabel compile` reports
2205 of 2207 messages translated — the two stragglers being the §2 artefacts,
since removed, taking the count to 2204 of 2204.

`just translate-regen` now passes `--ignore-obsolete` to `pybabel update` so
they cannot accumulate again. That flag is not free: a string deleted from the
source now loses its translation immediately rather than being parked as `#~`.
That is the right trade here — parked translations were never resurrected by
msgmerge anyway (which is how this mess arose), and the parking cost us a
compilable catalogue.

## 1c. The POT was stale — FIXED

`translations/messages.pot` is gitignored, so whatever a developer has locally
is whatever their last `just translate-regen` produced, and nobody had run it
since the renames at the top of this branch. Regenerating dropped four strings
(`Source:`, `Category Name`, `New category name`, `Add category`) and added
three, which were translated in the same pass and flagged fuzzy like the rest
of the run:

| msgid           | msgstr               |
| --------------- | -------------------- |
| Data Source:    | Adatforrás:          |
| Target Name     | Célkategória neve    |
| New target name | Új célkategória neve |

`msgmerge`'s fuzzy matching had guessed _Adatforrás_ (losing the colon) and
_Célszám neve_ for both of the others. _Célszám_ is wrong here: these label a
target **category** — the form class is `AddTargetCategoryForm` and the hint is
"e.g. Gender, Age, Ethnicity" — not a target number. See question B7.

The rest of that commit is reference-comment churn from line numbers moving.

## 2. Extraction artefacts: msgids that are dict keys, not messages — FIXED

`src/opendlp/service_layer/error_translation.py` did:

```python
context = _(ERROR_MESSAGES["parse_error_multi_column"]) % {...}
```

Babel's Python extractor is token-based: it takes **every string literal**
between the parens of a `_(` call. The only literal here is the dict key, so
`parse_error_multi_column` and `parse_error_single_column` landed in the POT as
msgids. Nothing ever looks them up — at runtime `_()` is handed the dict
_value_ — so they were dead weight, and they were what kept
`pybabel compile --statistics` reporting 2205 of 2207 for ever. They were left
untranslated during the run rather than filled with plausible-looking nonsense.

The rest of this section's original diagnosis was wrong, and so was the worry
in the COMMENT below it. **The library i18n pipeline already works end to
end.** The `N_()` no-op markers on the `ERROR_MESSAGES` and `REPORT_MESSAGES`
values — the pattern that exists precisely so a library can be
translation-ready without a gettext dependency — are picked up by the
`--keyword=N_` in `just translate-regen`, which extracts from the installed
package as well as from `src/`. 104 entries in the Hungarian catalogue carry
occurrences from `site-packages/sortition_algorithms/`, translated. Verified by
compiling with `--use-fuzzy` and rendering a real `ParseTableMultiError`
through the app: both the core message and its row/column context come out in
Hungarian, on the single- and multi-column paths.

So no change was needed in sortition-algorithms, and `_l()` on the dict values
would have been worse — it would force a gettext dependency on the library.

Fixed by hoisting the two templates to module constants, so no literal sits
inside a `_()` call, and by extending `just translate-check` to fail on any
msgid shaped like an identifier. Note that §4's suggested `^[a-z0-9_]+$` would
have flagged fourteen legitimate msgids (`login`, `page`, `values`, `px`, …);
requiring at least one underscore gives zero false positives. The check reads
the POT when one is present as well as the committed `.po` files, but it is
still a lagging indicator: an artefact only shows up after a
`just translate-regen`.

`thirdparty/sortition-algorithms/docs/i18n.md` described a different,
_key_-based scheme throughout — msgids like `errors.missing_column`, reached
via `_(f"errors.{code}")`. That scheme cannot work with this toolchain, because
Babel cannot extract an interpolated f-string, so the msgid list would have to
be hand-maintained. The code has always used the value-based scheme. That doc
has been rewritten to match reality (and to warn about the literal-in-`_()`
trap); it is deliberately **not** committed here, since it belongs to the other
repo.

Two things left as watch items rather than fixed:

- The msgid _is_ the upstream English string, so a reworded template in a new
  sortition-algorithms release changes the msgid. With §1b's `--ignore-obsolete`
  the old translation is now discarded outright rather than parked as `#~`. Still
  the right trade, but the 104 library entries are the most exposed to it.
- `just translate-regen` depends on the trailing library path argument. Drop it
  and those 104 msgids vanish silently, taking their translations with them. A
  one-line assertion that the POT contains a `sortition_algorithms` occurrence
  would be cheap insurance.

Adjacent, not part of this: `tests/unit/test_error_translation.py:130` mocks
gettext with stale key-based keys (`"errors.not_a_number"`), which never match,
so the fake is a pass-through and the test asserts against the real English. It
passes for the wrong reason.

## 3. Stray spaces in format placeholders — FIXED

Ten templates wrote `%(email) s` / `%(url) s`, with a space before the
conversion character — not the two this note first claimed. All four affected
msgids are shared across several templates:

| msgid                                                      | templates |
| ---------------------------------------------------------- | --------- |
| `Need help? Contact us at <a href="mailto:%(email) s">…`   | 5 emails  |
| `You need an invitation code to create an account…`        | 3 auth    |
| `Whether the account is active is changed from the…`       | 1 admin   |
| `Contact <a href="mailto:%(email) s">OpenDLP Support</a>…` | 1 main    |

**The claim that these "almost certainly do not interpolate correctly" was
wrong.** A space is a valid Python conversion flag, so `"%(url) s" % {...}`
produces exactly what `%(url)s` does. Verified by rendering `/auth/register`
and `/` through the test client: the links come out correct.

Fixed anyway — it is inconsistent with every other placeholder in the
codebase, it reads as a bug, and it is a trap for translators, who have to
reproduce the oddity verbatim or trip a placeholder checker. The msgids and
the four msgstrs (which reproduced the typo faithfully) were renamed in the
same commit, so nothing was orphaned; a following `just translate-regen`
adds and drops nothing.

One thing checked along the way and found to be fine: several of these
templates embed an `<a>` inside `_()` **without** `| safe` and still render
the anchor unescaped. That is not an autoescape hole. Flask-Babel installs
Jinja's i18n extension with newstyle gettext, which returns `Markup` for the
(developer-written) msgid while escaping the interpolated values — so the
`| safe` on the other templates is redundant rather than load-bearing.

## 4. Stopping this coming back

- **Done.** `just translate-check` runs `msgfmt --check` over every catalogue,
  and `just check` / `just check-ci` call it. It catches duplicates, broken
  placeholders and bad plural forms in one go, and it is fast.
  `pybabel compile` is no substitute — it compiled the 80-duplicate
  catalogue happily, which is why this went unnoticed for so long.
- **Done.** `--ignore-obsolete` on `pybabel update` (§1b), and
  `docs/translations.md` now points at the `just` recipes rather than giving
  raw `pybabel` commands that omit the flag.
- **Done.** `msgfmt` is a system binary from GNU gettext, not a Python
  dependency, and the `ubuntu-latest` runner does **not** carry it — the first
  CI run after `translate-check` landed failed with "msgfmt not found - install
  gettext", exactly as this note predicted. The quality job in
  `.github/workflows/main.yml` now installs `gettext` (the package that provides
  `msgfmt`; `gettext-base` does not). The recipe exiting 1 rather than skipping
  is what made this a two-minute diagnosis.
- **Done.** `just translate-check` also fails on any msgid shaped like an
  identifier — the signature of the §2 artefact. The pattern needs at least one
  underscore (`^[a-z0-9]+(_[a-z0-9]+)+$`): the bare `^[a-z0-9_]+$` first
  suggested here matches fourteen legitimate msgids.
- **Done.** `gettext-auto apply` deliberately leaves every entry it writes
  flagged `fuzzy`, so `gettext-auto scan` keeps returning them, and the skill's
  stated loop ("repeat until scan returns zero entries") could never terminate
  on this project — it would retranslate the catalogue until someone stopped it.
  This run was driven from a frozen snapshot of the initial scan instead, and
  `.claude/skills/gettext-auto/SKILL.md` now says to do that, with the reason.
  The skill also gained a step to run `just translate-check` at the end: `apply`
  writes `#. AUTOTRANS-ERROR:` comments for entries it cannot verify, and
  nothing in the protocol was surfacing them.
- **Done.** `docs/translations.md` had *two* sections describing the workflow.
  The lower one was fixed to use the `just` recipes; the Quick Start above it
  still gave raw pybabel, including `pybabel update` with no `--ignore-obsolete`
  — the exact command that caused §1b. Quick Start is now the canonical list and
  the other section points at it, because two copies is how the wrong one
  survived.
- **Done.** The i18n section of `AGENTS.md` names `just translate-check` as well
  as `translate-regen`, and records the two msgid constructs that look right and
  are not (§2's dict key, §3's lone `%`), plus the fact that rewording a msgid
  silently discards its translation in every language.
- **Done.** `.claude/skills/sf-code-review/SKILL.md` gained two check items for
  source-side i18n hygiene. Three of the four problems in this document
  originated in `.py` and `.html`, not in the catalogue, and the skill had one
  i18n item, about JavaScript. Its "do not report" exclusion was also narrowed
  from `translations/**/*` to the generated `.po`/`.pot`/`.mo`, so a
  hand-written file under `translations/` is still reviewable.
- **Done.** `translations/styleguide-hu.md` holds the §5 conventions and
  glossary, each tagged with the `hu-review-questions.md` question it awaits,
  plus the §6 known-bad entries so nobody copies one as an example. The skill
  reads `styleguide-<lang>.md` before translating. It lives beside the
  catalogues rather than in `.claude/skills/`, because a human reviewing the
  `.po` needs the same glossary and will not look in `.claude/`.
- **Done.** `.gettext-auto.toml` sets `context`, which the skill passes to the
  model verbatim on every batch — the only project context that reaches the
  translator without an agent remembering to open a file, so it carries the
  domain words that mean something else outside civic tech ("assembly",
  "selection", "pool").
- The `Dockerfile` calls `pybabel compile` directly, since there is no `just` in
  the build image. Left as is and commented: compile is the one subcommand with
  no flags we depend on, and the publish workflow needs the quality job — which
  runs `translate-check` — before it builds an image, so a broken catalogue
  cannot reach a registry.

## 5. Translation conventions used

Tone: informal (_tegeződés_), matching the exemplars `gettext-auto scan`
returned from the existing catalogue ("jelentkezz be", "próbáld újra",
"Üdvözlünk"). Note the pre-existing catalogue is **inconsistent** — a good
number of the older clean entries use formal _magázás_ ("Nincs jogosultsága",
"Állítsa be"). Those were not touched. A later consistency pass over the whole
catalogue would be worthwhile.

Glossary fixed at the start of the run and used throughout:

| English                         | Hungarian             |
| ------------------------------- | --------------------- |
| assembly                        | gyűlés                |
| respondent                      | válaszadó             |
| selection                       | kiválasztás           |
| target(s)                       | célszám(ok)           |
| category                        | kategória             |
| pool                            | merítés               |
| replacement                     | pótkiválasztás        |
| invite                          | meghívó               |
| organiser                       | szervező              |
| admin                           | adminisztrátor        |
| assembly manager                | gyűléskezelő          |
| confirmation caller             | megerősítő hívó       |
| read only                       | csak olvasó           |
| spreadsheet                     | (Google) Táblázat     |
| tab                             | lapfül                |
| dashboard                       | irányítópult          |
| role                            | szerepkör             |
| 2FA / two-factor authentication | kétlépcsős azonosítás |
| backup code                     | tartalék kód          |
| URL slug                        | URL-azonosító         |

Some of the pre-existing clean entries disagree with this glossary (e.g.
`Dashboard` → "Irányító pult" with a space). Left alone; candidate for the same
consistency pass.

## 6. Some older clean translations are simply wrong

Not touched, because the protocol forbids it, but spotted in passing:

- `Assembly Role` → "Gyűlés címe" (that is "Assembly Title")
- `Repeat for confirmation` → "Google Táblázat beállításainak eltávolítása"
- `Password confirmation` → "Beállítások mentése"
- `New password confirmation` → "Google Táblázat beállításainak eltávolítása"
- `You don't have permission to upload targets` → "Nincs jogosultsága a
  közösségi gyűlés megtekintéséhez"
- `An error occurred while uploading targets` → "Hiba történt a gyűlés
  frissítése közben"

These look like the result of a bad fuzzy-match auto-accept. A pass that
re-fuzzies entries whose msgstr length is wildly out of line with the msgid
might find the rest.

## Files in this directory

- `hu-review-questions.md` — 35 questions for a native Hungarian speaker,
  each standing in for a whole class of entries. Start here for review. The
  decisions they are asking about are recorded in `translations/styleguide-hu.md`,
  which is where the answers should land.
- `duplicate-msgids.txt` — the 80 duplicated msgids (§1). Historical record;
  they are all resolved, so nothing regenerates this list.
- `chunk.py` — prints a slice of a frozen `gettext-auto scan` JSON snapshot as
  one compact JSON object per line, for feeding to the model:
  `python3 chunk.py scan_all.json 0 50`
- `apply.sh` — pipes a batch of translations into `gettext-auto apply` and
  summarises the result, filtering out the (expected) duplicate-msgid refusals:
  `./apply.sh hu batch.json`

Both take the working files as arguments, so freeze a snapshot first with
`uv run gettext-auto scan hu --batch 99999 > scan_all.json`. Working from a
frozen snapshot matters: `apply` leaves every entry it writes flagged `fuzzy`,
so a fresh `scan` keeps returning the entries you have already done (§4).

## Run summary (2026-09-07)

`gettext-auto scan hu` reported **2070 pending entries** (1284 untranslated,
786 fuzzy). All 2070 were put through the model in batches of 50.

- **2027 written** — translated and left flagged `fuzzy` for human review, which
  is what `gettext-auto apply` always does.
- **41 refused** — `Refusing to overwrite clean translation`, the duplicate-msgid
  problem in §1. A translated copy of each of these msgids already exists, so
  nothing is actually missing.
- **2 deliberately skipped** — `parse_error_multi_column` and
  `parse_error_single_column`, the extraction artefacts in §2.

No placeholder mismatches and no `msgfmt` warnings were reported by `apply` on
any batch. The catalogue still does not compile as a whole, because of the
pre-existing duplicates in §1.

**Nothing here has been reviewed by a Hungarian speaker.** Every entry this run
touched is `fuzzy`, so a review pass is expected before the `.mo` is built.
