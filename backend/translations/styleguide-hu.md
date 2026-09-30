# Hungarian style guide

The tone, vocabulary and formatting conventions for `hu/LC_MESSAGES/messages.po`.
Read this before translating anything into Hungarian, whether you are a person or
an agent — the `/translate hu` skill is told to. The English conventions it
translates from are in [`docs/language.md`](../docs/language.md).

## Status: reviewed

The conventions below were reviewed by a native Hungarian speaker on the team in
September 2026. The questions put to them, and their reasoning, are in
[`docs/agent/898-translate-skill/hu-review-questions.md`](../docs/agent/898-translate-skill/hu-review-questions.md);
each decision here is tagged with the question it came from, like *(A1)*, so you
can go and read why.

One thing is still open and is listed under [Still open](#still-open) at the
foot of this file. Everything else is settled — follow it as written, and if you
disagree, change this guide and the catalogue together rather than translating
around it.

## Tone and register

The audience is not one audience. Organisers and staff use the backoffice;
members of the public see the registration pages and receive the email. Those two
get different registers. *(A1)*

- **Backoffice and admin: informal (*tegeződés*)** — "jelentkezz be", "próbáld
  újra", "Üdvözlünk".
- **Public registration pages (`templates/register/`) and all outbound email
  (`templates/emails/`): formal (*magázás*)** — "jelentkezzen be", "próbálja
  újra". A civic process writing to a stranger does not address them as *te*.
- Keep the deferential "Kérjük" in apologetic messages. In the backoffice it
  pairs with the informal imperative — "Kérjük, próbáld újra" — which is fine and
  is the house style; in public text it pairs with the formal one — "Kérjük,
  próbálja újra". *(A2)*
- **Buttons and menu items take the noun form**, not the imperative: "Mentés",
  "Törlés", "Exportálás", "Fiók létrehozása" — not "Ments", "Töröld". Nobody
  imagines a person behind the machine when it saves a file, and the noun form is
  the modern default. *(A4)*

### The software is not a person

Write system actions **impersonally or in the passive**, never in the first
person plural. The software is an algorithm, not a helpful assistant. *(A3)*

| No | Yes |
| --- | --- |
| "Kiválasztottunk %(count)s embert" | "%(count)s személy kiválasztva" |
| "Töröltük a beállítást" | "A beállítás törölve" |
| "Nem sikerült beolvasnunk a fájlt" | "A fájl beolvasása nem sikerült" |

The exception is when a **real person** did the thing. Then say so, and say who:
"A gyűlésszervező módosította az értéket", not "Módosítottuk az értéket".

## Glossary

Use these words. Consistency matters more than the individual choice: a reader
who meets *célszám* on one screen and *cél* on the next has to work out whether
they are the same thing.

### Domain

| English | Hungarian | |
| --- | --- | --- |
| assembly | közösségi gyűlés | *(B5)* |
| selection | kiválasztás | |
| respondent | jelentkező | *(B8)* |
| pool | jelentkezők | *(B6)* |
| target(s) | célszám(ok) | *(B7)* |
| category / feature | kiválasztási szempont | *(B7, F34)* |
| replacement (the process) | résztvevő pótlása | *(B9)* |
| replacement (the person) | pótszemély | *(B9)* |
| invite | meghívó | |
| assembly question | a közösségi gyűlés témája | *(F28)* |

**assembly** is *közösségi gyűlés* in full. Bare *gyűlés* is too vague — it is any
old meeting. Where the full term repeats several times in one short block of text
the abbreviation **k. gyűlés** is acceptable; it is not pretty, but it is
practical. In compounds the *közösségi* is dropped: *gyűlésszervező*, not
*közösségigyűlés-szervező*. *(B5)*

**respondent** is *jelentkező*, not *válaszadó*. They applied to take part; they
did not answer a survey. *(B8)*

**pool** is *jelentkezők* — the applicants who have not been drawn yet. Not
*merítés*, which was invented for this catalogue and means nothing to a reader.
*(B6)* Note that this lands on the same word as *respondent*, deliberately: a
respondent **is** someone in the pool. Where one sentence needs both and the
repetition reads badly, name the status rather than the group — "visszaállítás
Jelentkező állapotba".

**category** and the sortition library's **feature** are the same thing — the
field a target is set on (Gender, Age, Ethnicity) — so they get the same
Hungarian: *kiválasztási szempont*. The English source's own
category/feature split is an inconsistency worth not reproducing. In dense report
lines the short form **szempont** is fine where the context is clear. *(F34)*

**target** stays *célszám* — it really is a target number. But a *target
category* is not a number, so it takes the *kiválasztási szempont* above:
`Target Name` is "Kiválasztási szempont neve", not "Célszám neve". *(B7)*

**assembly question** is *a közösségi gyűlés **témája*** — the topic, not the
question. `Assembly Question` names the field where an organiser writes what the
assembly is convened to decide, and Hungarian says that as a topic; *kérdése*
reads as a query someone asked. No *fő*: the field is not one of several topics.
The help text goes with it — "a fő téma, amellyel…", not "a fő kérdés". *(F28)*

### Respondent fields

These came in with derived fields, after the review, and no native speaker has
checked them yet. Use them consistently until someone does.

| English | Hungarian | |
| --- | --- | --- |
| derived field | számított mező |  |
| derivation | számítás módja | |
| source field | bemeneti mező | |
| mapping (configuring one) | érték hozzárendelése | |
| mapping (applying one) | érték cseréje | |
| mapping file | hozzárendelési fájl | |
| input / output value | bemeneti / kimeneti érték | |
| options (of a choice field) | választható értékek | |

**derived field** is *számított*, not *származtatott* — the existing `Derived`
label has been updated to match, so both now read *Számított*.

**mapping** splits in two, depending on which side of the feature a string is
talking about. Setting one up — declaring or editing the rule that turns a
source value into an output value, as in `A large mapping needs its output
values declared…` or `The mapping file is empty` — is *érték hozzárendelése*
(*hozzárendelés*), matching **mapping file** (*hozzárendelési fájl*), which is
also about configuration. Running one — the moment a respondent's value is
actually replaced by what the rule produces — is *érték cseréje*. Every string
in the catalogue so far is about configuring a mapping, so *hozzárendelés* is
what you will mostly reach for; reserve *érték cseréje* for a string that
describes a value changing on a respondent's row, not the rule that will do
it. **options** was already settled in the catalogue as *választható értékek*
("Rögzített mező típusát vagy választható értékeit nem módosíthatod"); it is
listed here so the derived-field strings do not drift to *opciók* or
*lehetőségek*.

### Roles

The global **Organiser** and the per-assembly **Assembly Manager** are different
roles and must not read as synonyms. *(C14)*

| English | Hungarian | |
| --- | --- | --- |
| admin | adminisztrátor | |
| organiser (global role) | főszervező | *(C14)* |
| assembly manager (per-assembly) | gyűlésszervező | *(C12, C14)* |
| confirmation caller | visszaigazoló | *(C13)* |
| read only | megtekintő | *(C15)* |
| role | szerepkör | |

*megerősítő hívó* was a calque and is gone; *csak olvasó* is gone too — a
*megtekintő* is a person who looks, which is what the role is.

### Interface

| English | Hungarian | |
| --- | --- | --- |
| spreadsheet | (Google) Táblázat | *(G36)* |
| tab (in a spreadsheet) | munkalap | *(B10, G36)* |
| cancel (button) | Mégse | |
| URL slug | URL-azonosító | |
| 2FA / two-factor authentication | kétlépcsős azonosítás | |
| backup code | tartalék kód | |
| service account (Google) | szolgáltatásfiók | *(unreviewed)* |

**cancel** as a button — backing out of a dialog or form without doing anything —
is **Mégse**, the word every Hungarian UI uses for that button. Not
*Megszakítás*, which is the other sense of cancel: stopping something already
running. That sense keeps *megszakít* — "Feladat megszakítása", "A feltöltés
megszakítva".

**tab** is *munkalap*, which is what the Hungarian Google Sheets UI calls it —
users will have both screens open side by side. Not *lapfül*, in compounds
either: *Munkalapkezelés* and *Munkalaplista*, not *Lapfülkezelés* and
*Lapfüllista*. A term sweep that matches whole words will miss those. *(B10)*

**The two words stay apart.** A tab is a bare *munkalap*; the spreadsheet is
*Google Táblázat*, the name the localised Google UI itself uses. Don't coin
"GS", don't rename *Google Táblázat* to *Google Sheets*, and don't prefix
standalone tab labels with the product — write "Jelentkezők munkalapja", not
"Jelentkezők Google Sheets munkalapja". Name the sheet only where the English
names it, as in "A **Google Táblázatban** a regisztráltak adatait tartalmazó
**munkalap** neve". The reason is that every screen mentioning a tab already
says *Google Táblázat* in its heading or hint, so a prefix repeats context the
reader has, 14 characters at a time, in the table headings and buttons with
least room for it. *(G36)*

**dashboard** is *Vezérlőpult*, but under protest: neither page in this app is a
dashboard in the original sense. One is the **közösségi gyűlések listája** and
the other is **Statisztikák**, and where a string clearly means one of those —
`Back to Dashboard`, which always goes to the assembly list — say so instead.
The bare `Dashboard` msgid cannot: the source uses the one string for both the
per-assembly statistics tab and the nav link to the assembly list, so it takes
the generic word until someone splits it. *(B11)*

### Left in English on purpose

`OAuth`, `CSV`, `PDF`, `URL`, `AJAX`, `Alpine.js`, `CSP`, `HTML`, `Jinja`, `QR`,
`SHA-256`, `backoffice`, and the algorithm names `maximin`, `leximin`, `Nash`,
`diversimax`, `legacy`. *(E25)*

Preset configuration names — **"UK Team"**, **"EU Team"**, **"Australia Team"** —
are proper names and stay in English. A Hungarian user picking a preset is
picking *the UK team's settings*. *(E27)*

### Sortition library reports

The `sortition-algorithms` library writes its own run reports, in optimisation
jargon. They are read by organisers, not by mathematicians.

| English | Hungarian | |
| --- | --- | --- |
| agent | jelölt | *(F32)* |
| committee | csoport-összeállítás | *(F33)* |
| panel | csoport-összeállítás | *(F33)* |
| feature | kiválasztási szempont | *(F34)* |

An "agent" is a person in the pool: still a candidate, not yet a participant, so
*jelölt* — not *ügynök* (jargon), not *résztvevő* (overstates their status).
*(F32)*

A "committee" or "panel" here is one complete candidate line-up of the whole
assembly; the algorithm builds many and draws one. *csoport-összeállítás* says
exactly that. *bizottság* wrongly suggests a standing committee and *alcsoport*
wrongly suggests the assembly gets divided up. It is a heavy nine-syllable
compound in dense report lines — accepted as cosmetic. *(F33)*

## Grammar and formatting

- **No article before a placeholder.** Hungarian needs *a* or *az* depending on
  the following sound, which a runtime value does not tell us. Do not write
  `a(z)`, and do not rewrite the sentence to dodge it — just drop the article:
  `"%(email)s" felhasználó sikeresen frissítve`. *(D16)*
- **Counted nouns take the singular:** `%(count)s jelentkező betöltve`, not
  *jelentkezők*. *(D17)*
- **Quotation marks:** Hungarian low-high `„…”` in prose, ASCII `"…"` around
  anything the reader will match against literal data such as a spreadsheet
  column name. *(D18)*
- **Dashes:** en dash `–` where English uses a parenthetical hyphen —
  `Felhasználó – Hozzáférés azokhoz a közösségi gyűlésekhez…`. *(D19)*
- **"e-mail", not "email"** — "e-mail cím". Hungarian orthography takes the
  hyphen. *(D20)*
- **Sentence case for headings and buttons**, not the English Title Case: "Új
  meghívó létrehozása", not "Új Meghívó Létrehozása". *(D21)*
- **Ordinals:** `(%(current)s. iteráció)` — the full stop makes the injected
  number an ordinal, and that reads correctly at runtime. *(D22)*
- **"N/A"** is an em dash: `—`, and `— (OAuth)` for the OAuth variant. Short
  enough for a table cell. *(D23)*
- **Example values** in placeholder text are localised ("például: nem, életkor"),
  except literal spreadsheet column names such as `first_name, last_name`, which
  a UK team really would have in their sheet and which stay in English. *(E26)*
- **Status values are past participles**, in tabs and in per-person status cells
  alike: *Kiválasztva*, *Megerősítve*, *Visszalépett*, *Törölve*. The one
  exception is `Pool`, which has no participle and takes the glossary's
  *Jelentkezők*. *(F31)*
- **Email greeting:** `Hi %(name)s,` is "Kedves %(name)s!" — the exclamation mark
  is the Hungarian letter convention, and *Kedves* rather than *Szia* follows the
  formal register for email. *(F30)* Where there is no first name, the fallback
  word is *Résztvevő*, so the greeting renders "Kedves Résztvevő!". *(F29)* The
  transactional emails have their own nameless greeting, `Hi,`, which is
  "Kedves Címzett!" — same family, no invented name.

## Not translated

Developer-only pages — the Alpine pattern reference at `/backoffice/dev/patterns`,
the service layer docs, the component showcase and the dev dashboard — are
English technical reference for the people building the app. `babel.cfg` ignores
those templates and `blueprints/dev.py`, so they never reach the catalogue. The
strings stay wrapped in `_()` and simply render in English. *(E24)*

## Not up for review

These are mechanical constraints, not stylistic choices. They do not change
whatever a reviewer says.

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

## Known-bad entries — fixed, but read this anyway

A handful of older entries had been auto-accepted from bad fuzzy matches and
said something else entirely — `Assembly Role` rendered as "Gyűlés címe"
(Assembly *Title*), `You don't have permission to create assemblies` as "you
don't have access to any assemblies", `An error occurred during registration`
as "an error occurred during *login*". Those are corrected.

The lesson survives the fix: **an entry not marked `fuzzy` is not evidence that
anyone read it.** A bad fuzzy match auto-accepted years ago looks exactly like a
reviewed translation. Do not take a neighbouring entry as a worked example
without checking it against the English.

## Still open

1. **Two English strings that are badly worded** — `Not in targets`, and the pair
   `Reset %(count)s respondents to Pool status` / `Reset all respondents to
   Pool`. Fix the English first, then both languages at once. *(F35)*
2. ~~**The English cannot decide what to call a Google Sheet**~~ — settled. The
   English now says **Google Sheets** for the product and **spreadsheet** for the
   file, per [`docs/language.md`](../docs/language.md). That is the same split
   this guide already makes between *Google Táblázat* and a bare *munkalap*, so
   the Hungarian convention above does not change. The reworded msgids arrived
   `fuzzy`, carrying their old Hungarian as a suggestion; most of those
   suggestions still fit, but a handful of the new run-history task labels were
   matched against unrelated strings, so read each one before clearing it.
   *(G36)*
3. ~~**Terms coined for the target-sources and registration-question strings**~~
   — settled. Krisztina Kocsis reviewed the questions below on 25 September
   2026 and accepted every choice as made, so these terms are now house style.
   The list is kept as a record of the alternatives that were considered:
   - **age range / age bracket → korcsoport.** *kortartomány* is more literal
     but reads as a maths term; *korcsoport* is what an organiser would say.
     Used for both English words, since they name the same thing (a band like
     16–29). Is *korcsoport* right, or should it be *korosztály*?
   - **target value → célérték.** Already in the catalogue ("Minden célértéknek
     kell nevet adni"), so the new strings follow it: *Célérték*, *Célértékek:*,
     *%(n)d. válasz célértéke*. Note that this sits beside *célszám* (the target
     number) and *kiválasztási szempont* (the category); three words for the
     three parts of one target. Is that clear, or should the value be
     *a szempont értéke*?
   - **lookup table → hozzárendelési tábla; lookup row → hozzárendelési sor.**
     Chosen to sit in the same family as *hozzárendelési fájl* (mapping file),
     and to avoid *táblázat*, which this catalogue reserves for a Google Sheet.
     *keresőtábla* was the alternative.
   - **fallback (the value a respondent gets when nothing matches) → tartalék.**
     "fall back to X" is rendered as "X értéket kap", and the label in the
     mapping form is "(tartalék: %(fallback)s)". The report line is "Tartalék
     értéket (%(fallback)s) kapott:". The catalogue already had "tartaléknak"
     for the email greeting fallback.
   - **computed question / derived → számított**, per the glossary above. The
     standalone `Derived` label, which still read *Származtatott* (a non-fuzzy
     entry the run did not touch), has since been changed by hand to
     *Számított*, so the catalogue and the "Respondent fields" section now
     agree.
   - **The 'Link targets to questions' step → „Kiválasztási szempontok és
     kérdések összekapcsolása”.** The step name is quoted inside four other
     messages, so it must stay identical everywhere; change all five together.
     Its verbs: link → *összekapcsol*, unlink → *leválaszt*, re-sync →
     *újraszinkronizál*, recompute → *újraszámít*, "feeds a target" →
     *kiválasztási szempontot táplál*.
   - **Tags → Jelölők**, not *Címkék*, because *Címke* is already `Label` and the
     two appear as neighbouring column headings in the question editor. If a
     reviewer prefers *Címkék* the clash needs another answer for `Label`.
   - **Radio → Választógomb, Dropdown → Legördülő lista, Choice → Választás,
     Checkbox → Jelölőnégyzet, Exact copy → Pontos másolat.**
   - **Guess question types → Kérdéstípusok becslése**, not *kitalálása*.
   - **Signup survey (the optional questions organisers answer when they create
     an account) → Regisztrációs kérdőív.** Informal register, since the
     audience is staff: "Mesélj egy kicsit magadról", "Hol élsz a világban?".
     Organisation sizes use *fő*: "2–10 fő". Is *deliberatív folyamat* the term
     the team uses for "deliberative process"?
   - **`Please select` (the blank first option of a dropdown) → "Kérjük,
     válassz".** It comes from a backoffice form class, so informal, but the
     same form class could one day back a public page.
   - **Date input labels: Day/DD → Nap/NN, Month/MM → Hónap/HH, Year/YYYY →
     Év/ÉÉÉÉ**, and the example "For example, 27 3 1985" was kept in
     day-month-year order because that is the order of the three input boxes.
     Hungarian writes dates year-first; if the form is ever reordered for
     Hungarian, the example must follow it.
   - **Ordinal counters: "Option %(n)d" → "%(n)d. választható érték", "Answer
     %(n)d" → "%(n)d. válasz"**, per the ordinal rule above (D22).
   - **Plural forms — resolved in favour of this guide.** The catalogue header
     now says `nplurals=2; plural=(n != 1);`, the CLDR rule for Hungarian and
     what Babel ships, so a later `pybabel init`/`update` will not quietly
     revert it. Every plural entry carries both forms. Where the count sits
     right before the noun the two forms are identical — "%(count)s
     hozzárendelési sor" reads correctly for any count — and they diverge only
     where the sentence refers back to the counted thing away from the number,
     as in the recompute warning ("amelyekből a kiválasztás készült" /
     "amelyekből a kiválasztások készültek").
