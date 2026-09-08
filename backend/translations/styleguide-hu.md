# Hungarian style guide

The tone, vocabulary and formatting conventions for `hu/LC_MESSAGES/messages.po`.
Read this before translating anything into Hungarian, whether you are a person or
an agent — the `/translate hu` skill is told to.

## Status: provisional

Everything here was decided in a single automated pass and **none of it has been
confirmed by a Hungarian speaker.** The open questions are in
[`docs/agent/898-translate-skill/hu-review-questions.md`](../docs/agent/898-translate-skill/hu-review-questions.md),
which asks 35 questions standing in for the whole catalogue. Each decision below
that has an open question is tagged with its number, like *(A1)*.

Provisional is not the same as optional. A consistent catalogue can be corrected
in one pass when the answers arrive; an inconsistent one cannot. So follow this
guide as written, and if you disagree with something, change the guide and the
entries together rather than translating around it.

When the answers do arrive, update this file first, then bring the catalogue
into line with it.

## Tone and register

- **Informal (*tegeződés*) throughout** — "jelentkezz be", "próbáld újra",
  "Üdvözlünk". *(A1)*
- The audience is not homogeneous: organisers use the backoffice, but members of
  the public see the registration pages and the emails. The current answer
  applies one register to both. *(A1)*
- Keep the deferential "Kérjük" in apologetic messages, alongside the informal
  imperative: "Kérjük, próbáld újra". *(A2)*
- System actions are first person plural — "kiválasztottunk", "töröltük", "nem
  sikerült beolvasnunk". *(A3)*
- Buttons and menu items take the **noun form**, not the imperative: "Mentés",
  "Törlés", "Exportálás", "Fiók létrehozása" — not "Ments", "Töröld". *(A4)*

## Glossary

Use these words. Consistency matters more than the individual choice: a reader
who meets *célszám* on one screen and *cél* on the next has to work out whether
they are the same thing.

### Domain

| English             | Hungarian      | |
| ------------------- | -------------- | --- |
| assembly            | gyűlés         | *(B5)* |
| selection           | kiválasztás    | |
| respondent          | válaszadó      | *(B8)* |
| target(s)           | célszám(ok)    | *(B7)* |
| category            | kategória      | |
| pool                | merítés        | *(B6)* |
| replacement         | pótkiválasztás | *(B9)* |
| invite              | meghívó        | |

### Roles

| English             | Hungarian       | |
| ------------------- | --------------- | --- |
| admin               | adminisztrátor  | |
| organiser           | szervező        | *(C14)* |
| assembly manager    | gyűléskezelő    | *(C12)* |
| confirmation caller | megerősítő hívó | *(C13)* |
| read only           | csak olvasó     | *(C15)* |
| role                | szerepkör       | |

### Interface

| English                         | Hungarian             | |
| ------------------------------- | --------------------- | --- |
| dashboard                       | irányítópult          | *(B11)* |
| spreadsheet                     | (Google) Táblázat     | |
| tab (in a spreadsheet)          | lapfül                | *(B10)* |
| URL slug                        | URL-azonosító         | |
| 2FA / two-factor authentication | kétlépcsős azonosítás | |
| backup code                     | tartalék kód          | |

"dashboard" is **irányítópult**, one word. Some older entries have "Irányító
pult" with a space; those are wrong and will be corrected in the review pass.

### Left in English on purpose

`OAuth`, `CSV`, `PDF`, `URL`, `AJAX`, `Alpine.js`, `CSP`, `HTML`, `Jinja`, `QR`,
`SHA-256`, `backoffice`, and the algorithm names `maximin`, `leximin`, `Nash`,
`diversimax`, `legacy`. *(E25)*

Preset configuration names ("UK Team", "EU Team", "Australia Team") are currently
translated — "Egyesült Királyság csapat". *(E27)*

## Grammar and formatting

- **Articles before a placeholder:** use `a(z)`, since which article is correct
  depends on a value only known at runtime — `A(z) "%(email)s" felhasználó
  sikeresen frissítve`. Rewriting the sentence so the placeholder does not follow
  an article is nicer where it is easy. *(D16)*
- **Counted nouns take the singular:** `%(count)s válaszadó betöltve`, not
  *válaszadók*. *(D17)*
- **Quotation marks:** Hungarian low-high `„…"` in prose, ASCII `"…"` around
  anything the reader will match against literal data such as a spreadsheet
  column name. *(D18)*
- **Dashes:** en dash `–` where English uses a parenthetical hyphen —
  `Felhasználó – Hozzáférés azokhoz a gyűlésekhez…`. *(D19)*
- **"email", not "e-mail"** — "email cím". This follows the majority of the
  pre-existing catalogue rather than Hungarian orthography, and is one of the
  likelier answers to come back changed. *(D20)*
- **Sentence case for headings and buttons**, not the English Title Case: "Új
  meghívó létrehozása", not "Új Meghívó Létrehozása". *(D21)*
- **Ordinals:** `(%(current)s. iteráció)` — the full stop makes the injected
  number an ordinal. *(D22)*
- **"N/A"** is currently inconsistent: `—` for the bare one, "Nem értelmezhető
  (OAuth)" for the other. Pick one when the answer arrives. *(D23)*
- **Example values** in placeholder text are localised ("például: nem, életkor"),
  except literal spreadsheet column names, which stay in English. *(E26)*

## Not up for review

These are mechanical constraints, not stylistic choices. They do not change
whatever the review says.

- **Reproduce every placeholder exactly**, spelling and all: `%(count)s`,
  `%(email)s`, `%s`, `{name}`. A renamed or dropped placeholder is a runtime
  crash, not a typo. Their *order* may change to suit Hungarian word order —
  named placeholders make that safe.
- **Never introduce a lone `%`.** Flask-Babel uses newstyle gettext, which runs
  printf formatting over the result, so a stray `%` fails with "incomplete
  format". Percent signs are concatenated outside the translated string.
- **Leave the `fuzzy` flag alone.** Fuzzy is what keeps unreviewed text out of
  the `.mo`, and therefore out of the product. Only a human reviewer clears it.
- **Match the plural count.** Hungarian has two plural forms in gettext terms
  (`nplurals=2`), so an entry with `msgid_plural` needs both.
- **Run `just translate-check`** after editing. `pybabel compile` accepts a
  catalogue that `msgfmt` rejects.

## Known-bad entries — do not imitate

A handful of older entries were auto-accepted from bad fuzzy matches and are
simply wrong. They are still in the catalogue, so do not take a nearby entry as
a worked example without reading it:

| msgid | current msgstr | actually means |
| ----- | -------------- | -------------- |
| `Assembly Role` | Gyűlés címe | Assembly Title |
| `Repeat for confirmation` | Google Táblázat beállításainak eltávolítása | Remove Google Sheet settings |
| `Password confirmation` | Beállítások mentése | Save settings |
| `New password confirmation` | Google Táblázat beállításainak eltávolítása | Remove Google Sheet settings |
| `You don't have permission to upload targets` | Nincs jogosultsága a közösségi gyűlés megtekintéséhez | You don't have permission to view the assembly |
| `An error occurred while uploading targets` | Hiba történt a gyűlés frissítése közben | An error occurred while updating the assembly |

These also use formal *magázás*, which the rest of the catalogue does not.
