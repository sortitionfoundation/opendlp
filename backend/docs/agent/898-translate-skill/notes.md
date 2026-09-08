# Notes from the Hungarian `/gettext-auto hu` run

Working notes taken while running the `gettext-auto` skill over
`translations/hu/LC_MESSAGES/messages.po`. Nothing here was fixed *during* the
translation pass — the skill's protocol says never touch a non-fuzzy entry and
never clear a fuzzy flag, so all of it was left alone deliberately and picked
up afterwards. Sections are marked FIXED as they are dealt with.

## 1. 80 duplicate msgids, and the catalogue did not compile — FIXED

`msgfmt -c` refused the file with 80 `duplicate message definition` errors, so
`just translate-compile` could not build a `.mo` and none of the Hungarian
reached users.

The diagnosis in the first draft of this note was wrong. There were **no
duplicates among live entries at all**. Every one of the 80 was a clash between
a live entry and an *obsolete* (`#~`) entry carrying the same msgid — msgfmt
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

## 1c. The checked-in POT is stale (NOT fixed)

`translations/messages.pot` is gitignored, so whatever a developer has locally
is whatever their last `just translate-regen` produced. Running it now picks up
the renames from the top of this branch: `Source:` → `Data Source:`,
`Category Name` → `Target Name`, `New category name` → `New target name`,
`Add category` dropped. Three new untranslated entries, four translations
discarded.

Worth doing deliberately as its own commit, with the three new strings
translated in the same pass, rather than as a side effect of someone else's
regen.

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

COMMENT: ERROR_MESSAGES is defined in the external package sortition-algorithms (that we own). That does not have gettext as a dependency. You can see the plan I was trying to follow at thirdparty/sortition-algorithms/docs/i18n.md (which is in a copy of the repo for that package, excluded from git for this project). Fixing this might take some research.

## 3. Source-string bugs found while translating

- `templates/admin/user_edit.html:101` — `href="%(url) s"` has a stray space
  inside the placeholder (should be `%(url)s`). Same shape in
  `templates/auth/register.html:9`: `mailto:%(email) s`. These almost certainly
  do not interpolate correctly at runtime. The Hungarian translations reproduce
  the typo verbatim so the msgstr keeps matching the msgid — **fix the source
  and the translations together**, or the fixed msgid becomes a new
  untranslated entry.

## 4. Stopping this coming back

- Add `msgfmt -c -o /dev/null translations/*/LC_MESSAGES/messages.po` to
  `just check` (or a prek hook). It catches duplicates, broken placeholders and
  bad plural forms in one go, and it is fast. Still to do — the catalogue
  compiles today (§1b) but nothing stops it regressing.
- `--ignore-obsolete` on `pybabel update` is done (§1b).
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
