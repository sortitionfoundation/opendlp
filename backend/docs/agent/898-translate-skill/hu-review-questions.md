# Hungarian translation — questions for a native speaker

The `/gettext-auto hu` run translated 2027 entries. Every one of them is flagged
`fuzzy`, so nothing reaches users until a person reviews it.

Reviewing 2027 entries one by one is not a good use of anyone's afternoon. This
file asks **35 questions instead**. Each one is a *decision* rather than a
single string — answer it once and the answer applies to every entry of that
shape. The "Applies to" line under each question says roughly how many entries
in the catalogue hang off it.

## How to use this

- Tick an option, or write your own in the **Answer:** line. Short is fine.
- "Don't care, either is fine" is a genuinely useful answer — it tells us to
  stop worrying about that one.
- You don't need to look at the `.po` file. Everything you need is quoted here.
- The English source is quoted exactly as it appears in the app, so if a
  question is really "the English is unclear", say so — that is a bug in the
  source, and worth more than a translation fix.

Counts below are entries **in this run**, from `grep`-style counts over the
translated strings. They are indicative, not exact.

---

# A. Tone and register

These four decide the feel of the whole product. Everything else is detail.

### A1. Informal (*tegeződés*) or formal (*magázás*)?

The existing catalogue is genuinely split — of the 137 previously-reviewed
entries, 7 use *magázás* and 8 use *tegeződés*:

| | |
| --- | --- |
| formal | "Nincs jogosultsága a közösségi gyűlés megtekintéséhez" |
| informal | "Az oldal eléréséhez kérjük jelentkezz be." |

I went **informal throughout**, because the exemplars `gettext-auto` picked out
of the catalogue happened to be the informal ones. That was a coin-flip, not a
judgement.

Bear in mind who the audience is: the backoffice is used by assembly organisers
(staff), but the registration pages and the emails are seen by **members of the
public being invited to a civic process**. Those two audiences may not want the
same register.

- [ ] Informal everywhere (what I did)
- [ ] Formal everywhere
- [x] Informal in the backoffice, formal in public registration pages + emails
- [ ] Formal in the backoffice, informal in public pages + emails

**Applies to:** all 2027 entries; ~63 have an unmistakable informal verb form
that would need rewriting if you choose formal.

**Answer:**

---

### A2. "Kérjük, próbáld újra" — is mixing polite *kérjük* with informal *-d* acceptable?

English: `An error occurred during login. Please try again.`

I kept the pre-existing "Hiba történt a bejelentkezés során. Kérjük, próbáld
újra." — which pairs the deferential plural *kérjük* with an informal singular
imperative *próbáld*. To an English ear this is unremarkable; I am told it can
read as inconsistent in Hungarian.

- [x] Fine as is, keep "Kérjük, próbáld újra"
- [ ] Drop the *kérjük*: "Próbáld újra"
- [ ] Something else

**Applies to:** 9 entries use "Kérjük"; the pattern would spread if it's the
house style for apologetic messages.

**Answer:**

---

### A3. Who is "we"?

English: `Successfully selected %(selected_count)s people. %(remaining_count)s remain in pool.`

I translated a lot of system actions in first person plural — "kiválasztottunk",
"töröltük", "nem sikerült beolvasnunk". The alternative is impersonal /
passive-ish phrasing that doesn't put a "we" behind the software.

- [ ] First person plural is good — it sounds human
- [ ] Prefer impersonal ("A kiválasztás megtörtént", "%(count)s sor törölve")
- [ ] Mix: impersonal for status/log lines, "we" for things a person did

**Applies to:** several hundred status, flash and progress messages.

**Answer:**
I like the third (mixed) option, however I am not sure in which point is a real person in the background. If such a case exists, I wold communicate clearly: "an assembly manager modified the value" or similar. But in general I prefer the impersonal or passive modus, and not personalising the algorithm. It is a bit 90' style for me with Clippy.
---

### A4. Button and menu labels: noun or imperative?

I used the noun form throughout — "Mentés", "Törlés", "Exportálás",
"Fiók létrehozása" — rather than imperatives ("Ments", "Töröld").

- [x] Noun form (what I did)
- [ ] Imperative
- [ ] Noun for toolbar/short buttons, imperative for full-sentence CTAs

**Applies to:** ~200 button and menu labels.

**Answer:**
Same as above: nobody things there is a person behind the scene when a machine saves something, so definitely the Noun. This is the default nowadays, unless we wanna explicitly behave as a cute assistant on your phone, like a smart bird who teaches you Japanese and called Duolingo.
---

# B. Core domain vocabulary

Each of these is a word that recurs constantly. Getting them right matters more
than any individual sentence.

### B5. "assembly" → *gyűlés* or *közösségi gyűlés*?

The product is for Citizens' Assemblies. The existing catalogue uses **both**:
"A '%(title)s' gyűlés sikeresen létrehozva" but also "Nincs jogosultsága a
**közösségi gyűlés** megtekintéséhez".

I used bare **gyűlés** in running text (shorter, and the civic context is
usually clear) and kept "közösségi gyűlés" only where the full term reads
better — which is inconsistent.

- [ ] *gyűlés* everywhere
- [x] *közösségi gyűlés* everywhere
- [ ] *közösségi gyűlés* on first mention / headings, *gyűlés* in running text
- [ ] Something else (*állampolgári gyűlés*? *polgári gyűlés*?)

**Applies to:** 106 entries.

**Answer:**
We can consider using abbreviation when it appears too many times repeatedly, like 'k. gyűlés'. Not very beautiful, but practical, and 'gyűlés' alone sound odd for me, even though the user would understand from of the context.
---

### B6. "pool" → *merítés*?

This is the term I am least confident about in the whole run.

In sortition, the "pool" is the set of registered people that the lottery draws
from. It is both a **status label** on a person (`Pool`, shown in a table) and a
**common noun** (`%(count)s remain in pool`, `Reset all respondents to Pool
status`).

I invented **merítés** and used it consistently, capitalised when it is a status
name ("Merítés állapotba") and lowercase otherwise ("marad a merítésben").

- [ ] *merítés* is right
- [ ] *jelentkezői kör*
- [ ] *meríthető kör* / *alapsokaság*
- [ ] Keep the English "Pool" — it's a term of art the organisers already use
- [x] Something else: *jelentkezők* is definitely the best option. Maybe "regisztráltak", but I feel a bit confusion, sounds like the users of some application, while "jelentkezők" is absolutely clear.

**Applies to:** 16 entries, but they are high-traffic ones (a status shown in
every respondent table).

**Answer:**

---

### B7. "target" / "targets" → *célszám*?

In this app a "target" is a demographic quota: the category *Gender* has values
*Male*/*Female*, and each value has a min/max **target** for how many should be
selected. Note the app recently renamed "Category name" to "Target name", so
"target" now names both the category and the quota.

I used **célszám** (literally "target number"), and *célkategória* for "target
category".

- [ ] *célszám* / *célkategória* (what I did)
- [ ] *kvóta* — the standard word for this in sampling
- [ ] *cél* plain
- [x] Something else: target = *célszám*  / *kiválasztási szempont*

The form labels `Target Name` and `New target name` are the sharp end of this.
They name a category (the form class is `AddTargetCategoryForm` and the hint is
"e.g. Gender, Age, Ethnicity"), not a number, so I translated them
*Célkategória neve* and *Új célkategória neve* rather than *Célszám neve*. If
you pick one word for both senses these get simpler — and so does the English.

**Applies to:** 45 entries.

**Answer:**
"Célszám" is perfect for target, while target category is hard to translate. The "célkategória" is definitely wrong. We have to express that we talk about an attribute of the person which we set a target number for. We can simple use the "jellemző" which is "attribute", but it does not express the relationship with the "célszám" (target). Maybe "keresett jellemző" (searched-for attribute) or "kiválasztási szempont" (selection criterion)


---

### B8. "respondent" → *válaszadó*?

A "respondent" here is someone who filled in the registration form and is now a
candidate for selection. They have not necessarily "responded" to anything —
the word is inherited from survey research.

I used **válaszadó** (following the existing catalogue).

- [ ] *válaszadó* (existing convention, what I did)
- [x] *jelentkező* — "applicant", arguably more accurate for what they did
- [ ] *regisztráló*
- [ ] Something else:

**Applies to:** 102 entries.

**Answer:**
Yes, I would be consistent with the above "jelentkező", and yes, it is not a survey for the first place anyways even they answered a couple of questions.
---

### B9. "replacement" → *pótkiválasztás*?

When someone selected for the assembly drops out, you run a "replacement
selection" to draw a substitute. The existing catalogue translated the bare word
`Replacement` as the whole explanatory phrase "Kieső emberek pótlása új
kiválasztással" — which is accurate but far too long for a tab label.

I used **pótkiválasztás** for the process and **pótrésztvevő** for the person.

- [ ] *pótkiválasztás* / *pótrésztvevő* (what I did)
- [ ] *pótlás* / *pótszemély*
- [x] Something else: "résztvevő pótlása" / "pótszemély"

**Applies to:** 11 entries.

**Answer:**
I would say "résztvevő pótlása" (replacement of a participant) is not longer but more clear, then the odd "pótkiválasztás". "pótszemély" is a bit odd, but no alternative exists, and it is understandable.
---

### B10. Spreadsheet "tab" → *lapfül*?

Google Sheets terminology. I used **lapfül** (following the existing
catalogue), e.g. "Válaszadók lapfül neve".

- [ ] *lapfül* (what I did)
- [x] *munkalap* — which is what Google Sheets Hungarian actually calls it
- [ ] *fül*

Worth checking against the Hungarian Google Sheets UI, since users will be
looking at both screens side by side.

**Applies to:** 56 entries.

**Answer:**
What about "GS Munkalap" to keep it sort but link to Google Sheet?
---

### B11. "Dashboard" → *irányítópult* (one word) or *Irányító pult* (two)?

The existing catalogue has "**Irányító pult**" (two words). I wrote
"**irányítópult**" (one word), which I believe is the standard spelling.

If I'm right, the existing entry is a typo and should be corrected — but it is
a reviewed, non-fuzzy entry so I left it alone.

- [ ] *irányítópult* — fix the old entry too
- [ ] *Irányító pult* — I'm wrong, revert mine
- [x] Something else (*vezérlőpult*?): Vezérlőpult

**Applies to:** ~10 entries, plus one pre-existing entry to correct.

**Answer:**
"Vezérlőpult" is the common translation however, we do not have a real dashboard in its original meaning. One of them is the "Közösségi gyűlések listája" (list of citizen assemblies) while the other is "Statisztikák" (statistics)
---

# C. Role names

These four appear in dropdowns, permission errors and invitation emails. They
need to be short enough for a `<select>` and clear enough for an email.

### C12. "Assembly Manager" → *gyűléskezelő*?

English: `Assembly Manager - Can manage the assembly and add other users`

I coined **gyűléskezelő**. It's compact but "kezelő" is a bit machine-operator.

- [ ] *gyűléskezelő*
- [ ] *gyűlésszervező* — but this collides with the global "Organiser" role (C14)
- [ ] *gyűlésfelelős*
- [x] Something else: *Szervező* on the UI, "A gyűlés szervezője" in descriptive textual contexts

**Answer:**
First answer was "Szervező" on the UI, "A gyűlés szervezője" in descriptive
textual contexts — but that collided with the global "Organiser" role.
Final decision in C14: Assembly Manager = **gyűlésszervező** (global
Organiser = *főszervező*).
---

### C13. "Confirmation Caller" → *megerősítő hívó*?

English: `Confirmation Caller - Can call confirmations for selected participants`

This is a person who telephones selected participants to confirm they will
attend. My **megerősítő hívó** is a literal calque and I think it's poor —
it reads like "a caller who confirms" rather than "someone who makes
confirmation calls".

- [ ] *megerősítő hívó*
- [x] *visszaigazoló* / *visszaigazolást kérő*
- [ ] *kapcsolattartó* — "contact person", less literal but clearer
- [ ] Something else:

**Answer:**
*visszaigazoló*

---

### C14. "Organiser" (global role) vs "Assembly Manager" (per-assembly role)

These are two different roles and must not read as synonyms. An **Organiser**
can create assemblies; an **Assembly Manager** runs one particular assembly.

I used *szervező* and *gyűléskezelő*. Do those stay distinct in Hungarian, or
does one need reworking to make the contrast obvious?

**Answer:**
Global "Organiser" → **főszervező**; per-assembly "Assembly Manager" →
**gyűlésszervező**. (This supersedes the bare "Szervező" in C12 — the pair
keeps the contrast obvious.)

---

### C15. "Read Only" role → *csak olvasó*?

English: `Read Only - Can view the assembly but cannot make changes`

I used **csak olvasó** for the person and *csak olvasható* for the state.

- [ ] *csak olvasó* / *csak olvasható*
- [x] *megtekintő*
- [ ] Something else:

**Answer:**
*megtekintő*

---

# D. Grammar and formatting conventions

Small, mechanical, and worth deciding once.

### D16. Is `a(z)` acceptable in UI text?

Hungarian needs *a* or *az* depending on the following sound, and with a runtime
placeholder we cannot know which. The standard workaround is `a(z)`:

> `A(z) '%(email)s' felhasználó sikeresen frissítve`

I used it 32 times. It is unambiguous but ugly. The alternative is to rewrite
the sentence so the placeholder never follows an article — e.g.
"Felhasználó sikeresen frissítve: %(email)s".

- [ ] `a(z)` is fine, keep it
- [ ] Prefer rewriting to avoid the article (more work, nicer result)
- [ ] Rewrite where it's easy, `a(z)` where it isn't
- [x] Drop the article entirely — no `a(z)`, no rewrite needed

**Applies to:** 32 entries directly, and it's the default I'd apply to any
future string with a leading placeholder.

**Answer:**
We do not need the article: "'%(email)s' felhasználó sikeresen frissítve" is
fine. Drop `a(z)` everywhere.

---

### D17. Counted nouns: singular after a number?

Hungarian takes the singular after a numeral. I wrote:

> `%(count)s válaszadó betöltve.` (not *válaszadók*)
> `%(count)s kategória feltöltve`

Confirming this is right, and that it reads naturally even when the number is
large or is a placeholder the reader can't see.

- [x] Correct, singular throughout
- [ ] Needs care in some of these — see notes

**Applies to:** ~80 entries with a count placeholder.

**Answer:**
Correct, singular throughout.

---

### D18. Quotation marks: `„…"` or `"…"`?

The English strings use a mix of `'...'`, `"..."` and `&quot;`. I used Hungarian
low-high quotes **„…"** in 17 places where I was writing fresh prose, but kept
the ASCII quotes where they wrap a placeholder that the user will match against
literal data:

> `A(z) "%(id_column)s" nevű oszlop...`  (kept ASCII — it's a column name)
> `Használd inkább a „Jelszó megváltoztatása" lehetőséget.`  (Hungarian — it's a UI label)

- [x] That distinction is right
- [ ] Use `„…"` everywhere
- [ ] Use ASCII everywhere (simpler, matches the English)

**Answer:**
The distinction is right — keep it.
---

### D19. Dashes: `–` vs `-`

I replaced the English hyphen-as-parenthetical with an en dash:

> `Felhasználó – Hozzáférés azokhoz a gyűlésekhez, amelyekhez hozzáadták`

Used 63 times. Is the en dash right for Hungarian typography here, and does it
survive in places where the string ends up in a plain-text email or a CSV?

- [x] En dash is right
- [ ] Use a plain hyphen
- [ ] Use `:` instead in the role-description pattern

**Answer:**
En dash is right.

---

### D20. "email" or "e-mail"?

The existing catalogue is inconsistent: 5 entries say "email", 2 say "e-mail".
I followed the majority and wrote **email cím** throughout (92 entries).

My understanding is that Hungarian orthography prefers **e-mail**, which would
make the whole catalogue wrong.

- [ ] "email" — fine, keep it
- [x] "e-mail" — correct it everywhere, including the old entries
- [ ] "e-mail-cím" as one hyphenated compound

**Applies to:** 92 entries.

**Answer:**
"e-mail" — correct it everywhere, including the old entries.

---

### D21. Headings: sentence case or Title Case?

English uses Title Case for headings and buttons ("Create New Invite", "Delete
Configuration"). Hungarian normally doesn't. I used **sentence case**
("Új meghívó létrehozása", "Beállítás törlése").

- [x] Sentence case (what I did)
- [ ] Match the English Title Case
- [ ] Sentence case, but capitalise proper nouns and product names

**Applies to:** ~300 headings and buttons.

**Answer:**
Sentence case.

---

### D22. Ordinals with a placeholder

English: `Optimising for maximin fairness (iteration %(current)s)`
Mine: `Optimalizálás maximin méltányosságra (%(current)s. iteráció)`

The trailing full stop makes the number an ordinal ("the 60th iteration"). Does
that read correctly when the number is injected at runtime, or is
"iteráció: %(current)s" safer?

**Answer:**
The ordinal form "%(current)s. iteráció" is fine — keep it.

---

### D23. "N/A" → what?

English: `N/A` and `N/A (OAuth)`, shown in table cells where a value doesn't
apply. I used an em dash **—** for the bare one and "Nem értelmezhető (OAuth)"
for the other, which is inconsistent.

- [x] `—` for both (short, fine in a table)
- [ ] "Nem értelmezhető" for both
- [ ] "N.A." / "n.a."
- [ ] Something else:

**Answer:**
`—` for both, i.e. "—" and "— (OAuth)".

---

# E. What should be translated at all

### E24. Should the developer documentation pages be translated?

**483 of the 2027 entries — nearly a quarter of the whole run — are
developer-only documentation**: the `/backoffice/dev/patterns` page, the service
layer docs, the component showcase. These are dev-only, English-language
technical reference ("Alpine.js x-model binding for the editable value",
"z-index 45 … above the sticky header").

I translated them because they were in the catalogue. It may be that they should
never have been extracted for translation in the first place.

- [x] Don't translate them — remove them from extraction, and drop my
      translations
- [ ] Translate them; developers on the team may not all read English
- [ ] Leave them translated now, decide later

**Applies to:** 483 entries. This is the single biggest lever in the file —
answering "don't translate" cuts the review burden by a quarter.

**Answer:**
Don't translate — remove them from extraction and drop the translations.

---

### E25. Technical terms left in English

I deliberately did **not** translate: `OAuth`, `CSV`, `PDF`, `URL`, `AJAX`,
`Alpine.js`, `CSP`, `HTML`, `Jinja`, `QR`, `SHA-256`, `backoffice`, and the
algorithm names `maximin`, `leximin`, `Nash`, `diversimax`, `legacy`.

- [x] All correct to leave in English
- [ ] Some of these should be translated — namely:

**Answer:**
All correct to leave in English.

---

### E26. Example values inside placeholder text

English: `e.g. Gender, Age, Ethnicity` and `e.g. Male, Female, 16-29`

I **localised** these: "például: nem, életkor, etnikai hovatartozás",
"például: férfi, nő, 16–29".

But English column-name examples like `e.g., primary_address1, zip_royal_mail`
and `e.g., first_name, last_name, email` I left **in English**, because those
are literal spreadsheet column names a UK team would actually have.

- [x] That split is right
- [ ] Localise the column names too
- [ ] Leave all examples in English

**Answer:**
The split is right.

---

### E27. "UK Team" / "EU Team" / "Australia Team"

These are named preset configurations. I translated them ("Egyesült Királyság
csapat"). They might be better as untranslated proper names, since a Hungarian
user picking a preset is picking *the UK team's settings*.

- [ ] Translate (what I did)
- [x] Leave as "UK Team" etc.

**Answer:**
Leave as "UK Team" etc. — untranslated proper names.

---

# F. Individual strings I'm least sure about

### F28. "Assembly Question" — literal or interpretive?

The existing reviewed translation is "**A gyűlés fő témája**" — "the assembly's
main topic". The English is `Assembly Question`, and the help text says "the key
question this assembly will address". Elsewhere I translated `Assembly question:`
literally as "A gyűlés kérdése:".

So the catalogue now says both. Which is right — and is "topic" actually a
better rendering of what the field means?

- [ ] "A gyűlés fő témája" everywhere
- [ ] "A gyűlés kérdése" everywhere
- [ ] They're different fields and both are fine

**Answer:**
UNANSWERED — needs more thought and context (where the field appears in the
app). Revisit later.

---

### F29. "Friend" as a name fallback

English: `First name, or 'Friend' as a fallback` — used in auto-reply emails as
`Hi {{ respondent.first_name_or_friend }},` when we have no first name.

I translated the fallback as "**Barátunk**". In an email from an official civic
process to a stranger, that may be too familiar or simply odd.

- [ ] "Barátunk"
- [x] "Kedves Olvasó" / "Kedves Résztvevő"
- [ ] Something else:

**Answer:**
"Kedves Résztvevő" — i.e. the fallback word is *Résztvevő*, so the greeting
renders as "Kedves Résztvevő!" when no first name is known.

---

### F30. Email greeting: `Hi %(name)s,`

I wrote "**Szia %(name)s!**" — swapping the comma for an exclamation mark, which
is the Hungarian letter convention. Also: is *Szia* right for an official email
about a civic process, or does it want *Kedves %(name)s!*?

- [ ] "Szia %(name)s!"
- [x] "Kedves %(name)s!"
- [ ] Depends on A1

**Answer:**
"Kedves %(name)s!" — consistent with A1 (formal in emails) and F29.

---

### F31. Selection statuses as table values

These appear as single words in a status column: `Pool`, `Selected`,
`Confirmed`, `Withdrawn`, `Test submission`, `Deleted`.

I used plural nouns for the tab labels (Kiválasztottak, Megerősítettek) but past
participles for the per-person status (Törölve, Visszalépett). That may be the
right instinct — a tab groups people, a status describes one — or it may just be
inconsistent.

- [ ] The split is right
- [x] Use one form throughout — namely: past participles

**Answer:**
Use the past participles everywhere, tabs included (Kiválasztva, Megerősítve,
Visszalépett, Törölve...). Exception: `Pool` is governed by B6 and stays
*jelentkezők* — it has no participle form.

---

### F32. "agent" in the algorithm reports

The `sortition-algorithms` library emits `Agent %(agent_id)s not contained in
any feasible committee.` "Agent" is optimisation jargon; it means a person in
the pool.

I translated it as **személy** ("person") rather than *ügynök*, on the grounds
that these reports are read by organisers, not mathematicians.

- [ ] "személy" — right call
- [ ] Keep the technical "ügynök"
- [x] "jelölt" / "résztvevő"

**Applies to:** the 101 sortition-library messages, which are shown verbatim in
run reports.

**Answer:**
**jelölt**. Why: at the point these reports are generated the person is still
only in the pool — a candidate for selection, not yet a participant — so
*jelölt* is the accurate term. *Résztvevő* would overstate their status (and
is already used as the email greeting fallback in F29); *ügynök* is jargon the
organisers reading these reports don't use; *személy* is accurate but says
nothing about their role in the process.

---

### F33. "committee" in the algorithm reports

Same source. `Algorithm produced distribution over %(total_committees)s
committees` — here a "committee" is one candidate panel the algorithm
considered, not a committee in the everyday sense.

I used **bizottság**. *Panel* is used elsewhere in the same reports and I left
that as "panel".

- [ ] "bizottság" for committee, "panel" for panel
- [ ] Use "panel" for both — they mean the same thing here
- [x] Something else: **csoport-összeállítás** for both

**Answer:**
Use **csoport-összeállítás** for both "committee" and "panel" — one Hungarian
word for one concept, dropping the English source's inconsistency.

Reasoning: each "committee/panel" is one complete candidate composition of the
whole assembly — the algorithm builds many alternative full line-ups and draws
one. The main information is that they are a *set of people*, one possible
line-up, not a body with a role. So:

- *bizottság* wrongly suggests an official standing committee;
- *alcsoport* was considered and rejected — it suggests the assembly gets
  divided into subgroups, which is the wrong picture;
- *panel* (the runner-up) is short, matches the headline success message and
  HU sortition usage, but is borrowed jargon and vaguer;
- *csoport-összeállítás* says exactly what the thing is in plain Hungarian.
  Known costs, accepted as cosmetic: it is a heavy 9-syllable compound in
  dense report lines, and in the success message ("1 csoport-összeállítás
  kiválasztva") the selected thing becomes the actual assembly, which reads
  slightly oddly.

---

### F34. "feature" in the algorithm reports

Same source again. A "feature" is what the rest of the app calls a **category**
(Gender, Age). The library says `feature`, the app UI says `category`.

I translated the library's "feature" as **jellemző** and the app's "category" as
**kategória** — which faithfully reproduces an inconsistency that will confuse
users who see both.

- [ ] Keep them distinct (faithful to source)
- [x] Translate both the same so the UI is coherent — as **kiválasztási szempont**
- [ ] Something else:

**Answer:**
Translate both the library's "feature" and the app's "category" as
**kiválasztási szempont**, aligning with B7 (target = *célszám*, target
category = *kiválasztási szempont*). They name the same thing (Gender, Age…),
and users see both in one workflow — configure the szempontok on the targets
page, then read the run report about the same fields — so one term everywhere.
This also quietly fixes the English source's own feature/category
inconsistency. In dense report lines the bare short form **szempont** is
allowed where context is clear (same pattern as the B5 "k. gyűlés"
abbreviation idea).

---

### F35. Two English strings that may just be badly worded

Not translation questions — the English itself is doing something odd, and if we
fix the source we should fix both languages at once.

1. `Not in targets` — a dashboard row label meaning "this value appears in the
   respondent data but has no target set for it". I wrote "Nem szerepel a
   célszámok között". Is there a shorter phrasing that fits a table row?

2. `Reset %(count)s respondents to Pool status` vs
   `Reset all respondents to Pool` — two strings for one concept, worded
   differently. Worth unifying in English before translating.

**Answer:**
UNANSWERED — could not decide, review later (together with F28).

---

## After you've answered

Hand this back and I'll apply the answers across all the matching entries in one
pass, rather than editing them individually. The mechanical items (D16–D23,
B-series terminology) are find-and-replace scale; the tone question (A1) is the
only one that means genuinely rewriting a lot of strings.

Related: [notes.md](notes.md) lists the catalogue defects found during the run
(80 duplicate msgids that stop it compiling, 580 obsolete entries, two
extraction artefacts, two source-string typos). Those are independent of
anything here.
