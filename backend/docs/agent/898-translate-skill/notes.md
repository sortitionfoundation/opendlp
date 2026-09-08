# Notes from the Hungarian `/gettext-auto hu` run

Working notes taken while running the `gettext-auto` skill over
`translations/hu/LC_MESSAGES/messages.po`. Everything here is something to
**follow up after** the translation pass, not something fixed during it — the
skill's protocol says never touch a non-fuzzy entry and never clear a fuzzy
flag, so all of these were left alone deliberately.

## 1. The catalogue has 80 duplicate msgids, and does not compile

`msgfmt -c` refuses the file:

```
translations/hu/LC_MESSAGES/messages.po:12201: duplicate message definition...
translations/hu/LC_MESSAGES/messages.po:3736: ...this is the location of the first definition
```

3080 entries, 3000 distinct msgids, so 80 extra copies. The full list is in
[duplicate-msgids.txt](duplicate-msgids.txt).

Consequences:

- **`just translate-regen` cannot compile a `.mo`**, so none of this catalogue
  reaches users until the duplicates are resolved.
- **57 pending entries could not be translated at all.** `gettext-auto apply`
  looks an entry up by msgid, finds the *clean* twin first and refuses with
  `Refusing to overwrite clean translation for msgid=...`. Those 57 are not a
  loss — the clean twin is what a compiler would use anyway — but it means the
  fuzzy copies are dead weight that will keep showing up in every future scan.

Likely cause: a `.po` was merged or concatenated rather than `msgmerge`d at some
point. Worth checking `just translate-regen` for a step that appends instead of
merging.

Fix direction: `msguniq` (or `msgcat --use-first`) over the file, then re-run
`msgfmt -c` in CI so it can never regress. See §4.

## 1b. 580 obsolete entries

Separately from the duplicates, the catalogue carries **580 obsolete (`#~`)
entries** — strings that no longer exist anywhere in the source. They are all
untranslated and `gettext-auto scan` correctly ignores them, but they are 580
entries of dead weight in a 3080-entry file, and they make every "how much is
translated?" count misleading.

`msgattrib --no-obsolete` removes them. Worth doing at the same time as the
duplicate fix (§1) since both are one-off catalogue surgery.

## 2. Extraction artefacts: msgids that are dict keys, not messages

`src/opendlp/service_layer/error_translation.py` does:

```python
context = _(ERROR_MESSAGES["parse_error_multi_column"]) % {...}
```

Babel cannot evaluate the subscript, so it extracts the **key** string. The POT
therefore contains:

- `parse_error_multi_column`
- `parse_error_single_column`

At runtime `_()` is called with the *value* from `ERROR_MESSAGES`, so translating
these two msgids has no effect whatsoever. They were left untranslated rather
than filled with plausible-looking nonsense.

Fix direction: mark the `ERROR_MESSAGES` values with `_l()` where the dict is
defined, so the real format strings land in the POT, and drop the `_()` at the
call site. Check whether the same pattern appears elsewhere —
`grep -rn '_(\w*\[' src/`.

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
  bad plural forms in one go, and it is fast.
- Consider a check that no msgid looks like an identifier (`^[a-z0-9_]+$` with
  no spaces) — that is the signature of the §2 artefact.
- `gettext-auto apply` deliberately leaves every entry it writes flagged
  `fuzzy`, so `gettext-auto scan` keeps returning them. The skill's stated loop
  ("repeat until scan returns zero entries") therefore never terminates on this
  project. This run was driven from a frozen snapshot of the initial scan
  instead. Worth writing that down in the skill, or having the skill track what
  it has already offered a translation for.

## 5. Translation conventions used

Tone: informal (*tegeződés*), matching the exemplars `gettext-auto scan`
returned from the existing catalogue ("jelentkezz be", "próbáld újra",
"Üdvözlünk"). Note the pre-existing catalogue is **inconsistent** — a good
number of the older clean entries use formal *magázás* ("Nincs jogosultsága",
"Állítsa be"). Those were not touched. A later consistency pass over the whole
catalogue would be worthwhile.

Glossary fixed at the start of the run and used throughout:

| English | Hungarian |
| --- | --- |
| assembly | gyűlés |
| respondent | válaszadó |
| selection | kiválasztás |
| target(s) | célszám(ok) |
| category | kategória |
| pool | merítés |
| replacement | pótkiválasztás |
| invite | meghívó |
| organiser | szervező |
| admin | adminisztrátor |
| assembly manager | gyűléskezelő |
| confirmation caller | megerősítő hívó |
| read only | csak olvasó |
| spreadsheet | (Google) Táblázat |
| tab | lapfül |
| dashboard | irányítópult |
| role | szerepkör |
| 2FA / two-factor authentication | kétlépcsős azonosítás |
| backup code | tartalék kód |
| URL slug | URL-azonosító |

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
- `duplicate-msgids.txt` — the 80 duplicated msgids (§1).
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
