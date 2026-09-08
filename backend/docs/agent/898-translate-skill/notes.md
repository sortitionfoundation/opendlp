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
2205 of 2207 messages translated — the two stragglers being the §2 artefacts.

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

## 2. Extraction artefacts: msgids that are dict keys, not messages

`src/opendlp/service_layer/error_translation.py` does:

```python
context = _(ERROR_MESSAGES["parse_error_multi_column"]) % {...}
```

Babel cannot evaluate the subscript, so it extracts the **key** string. The POT
therefore contains:

- `parse_error_multi_column`
- `parse_error_single_column`

At runtime `_()` is called with the _value_ from `ERROR_MESSAGES`, so translating
these two msgids has no effect whatsoever. They were left untranslated rather
than filled with plausible-looking nonsense.

Fix direction: mark the `ERROR_MESSAGES` values with `_l()` where the dict is
defined, so the real format strings land in the POT, and drop the `_()` at the
call site. Check whether the same pattern appears elsewhere —
`grep -rn '_(\w*\[' src/`.

COMMENT: ERROR_MESSAGES is defined in the external package sortition-algorithms (that we own). That does not have gettext as a dependency. You can see the plan I was trying to follow at thirdparty/sortition-algorithms/docs/i18n.md (which is in a copy of the repo for that package, excluded from git for this project). Fixing this might take some research. It might be a whole branch in itself. For now, add a new .md file in this directory to describe the problem in more detail, if you think that would be useful.

## 3. Stray spaces in format placeholders — FIXED

Ten templates wrote `%(email) s` / `%(url) s`, with a space before the
conversion character — not the two this note first claimed. All four affected
msgids are shared across several templates:

| msgid                                                        | templates |
| ------------------------------------------------------------ | --------- |
| `Need help? Contact us at <a href="mailto:%(email) s">…`      | 5 emails  |
| `You need an invitation code to create an account…`           | 3 auth    |
| `Whether the account is active is changed from the…`          | 1 admin   |
| `Contact <a href="mailto:%(email) s">OpenDLP Support</a>…`    | 1 main    |

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
- One thing to watch: `msgfmt` is a system binary from GNU gettext, not a
  Python dependency. It is present on the GitHub `ubuntu-latest` runner, but if
  CI ever reports "msgfmt not found - install gettext", that is why.
- Consider a check that no msgid looks like an identifier (`^[a-z0-9_]+$` with
  no spaces) — that is the signature of the §2 artefact.
- `gettext-auto apply` deliberately leaves every entry it writes flagged
  `fuzzy`, so `gettext-auto scan` keeps returning them. The skill's stated loop
  ("repeat until scan returns zero entries") therefore never terminates on this
  project. This run was driven from a frozen snapshot of the initial scan
  instead. Worth writing that down in the skill, or having the skill track what
  it has already offered a translation for.

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
  each standing in for a whole class of entries. Start here for review.
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
