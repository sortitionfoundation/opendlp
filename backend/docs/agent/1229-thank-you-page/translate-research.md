# Translating the default thank-you page into the EU languages

Research notes for issue 1229. The aim is for the default "thank you" page
shown after someone registers to be available in all 24 official EU languages.
English is the source language and Hungarian is already fully translated, which
leaves 22 languages. For now only the strings in
`templates/register/thank_you_default.html` need translating.

This document sets out what the work involves and the decisions the team needs
to make. It is not a plan yet.

## Assumption: respondents see the default page

Right now nobody sees `thank_you_default.html`. The public `thank_you` route
(`src/opendlp/entrypoints/blueprints/registration.py`) only uses it when a
page's `thank_you_html` is blank. But every page is created with
`DEFAULT_THANK_YOU_HTML`, an English HTML string with no translation calls in
it (`src/opendlp/domain/registration_page.py`), and no screen lets an organiser
change or clear that value.

That is being fixed on a separate branch. These notes assume the fix is in and
an admin can set up registration so that respondents see the translated
template.

## What has to be translated

The template has five msgids:

| msgid | Where |
| --- | --- |
| `Thank You` | the `<title>` |
| `Thank you for registering` | the panel heading |
| `Your registration has been received` | the panel body |
| `We'll be in touch.` | a paragraph |
| `Please click here if you wish to start a new registration.` | a link back to the form, shown only when there is a referer |

None of them has a placeholder or a plural form. Across 22 languages that is 110
translations.

The language codes would be:

| Language | Code | | Language | Code |
| --- | --- | --- | --- | --- |
| Bulgarian | `bg` | | Irish | `ga` |
| Croatian | `hr` | | Italian | `it` |
| Czech | `cs` | | Latvian | `lv` |
| Danish | `da` | | Lithuanian | `lt` |
| Dutch | `nl` | | Maltese | `mt` |
| Estonian | `et` | | Polish | `pl` |
| Finnish | `fi` | | Portuguese | `pt` |
| French | `fr` | | Romanian | `ro` |
| German | `de` | | Slovak | `sk` |
| Greek | `el` | | Slovene | `sl` |
| | | | Spanish | `es` |
| | | | Swedish | `sv` |

`pt` means European Portuguese here, not Brazilian (`pt_BR`).

We checked the installed Babel, and it has locale data and plural rules for all
22 codes, including the unusual ones: Irish has 5 plural forms, Maltese and
Slovene have 4 each. So `pybabel init` and `compile` will work for every one of
them. The plural rules do not matter for these five strings, but they will once
anyone translates more of a catalogue.

## Decisions for the team

### 1. Whose language: the visitor's or the page's?

`get_locale()` in `src/opendlp/entrypoints/extensions.py` chooses the language
in this order:

1. the `?lang=` URL parameter
2. the session
3. the user's account preference (only for signed-in users)
4. the browser's `Accept-Language` header

A registration page has a `language` field, but nothing on the public side reads
it. The registration form is HTML the organiser wrote, so it is in whatever
language they wrote it in. The thank-you page, though, follows the visitor's
browser. If an organiser builds a page in Polish and the visitor's browser
prefers English, the visitor fills in a Polish form and then sees an English
thank-you page.

The `<html lang>` attribute comes from the same `get_locale()` call. On that
Polish form it says `en`, so a screen reader reads Polish text with English
pronunciation. That is a WCAG 3.1.1 failure that exists today, separate from
this issue.

Options:

- **a. Use the page's language.** When `page.language` is set, render the
  thank-you page (and ideally the form page's `<html lang>` too) in that
  language. When it is not set, fall back to the normal order above.
  *Recommended:* the visitor sees one language from start to finish, and the
  `lang` attribute is correct.
- **b. Keep following the visitor.** No code change, but the mismatch described
  above remains.

### 2. What `SUPPORTED_LANGUAGES` does to the rest of the app

`SUPPORTED_LANGUAGES` (`src/opendlp/config.py`) is one list for the whole app.
The default is `en,es,fr,de`, although `es`, `fr` and `de` have no catalogues.
We could not see the production value from the repo — **can someone confirm
it?**

If we add the 22 codes to that list, browser language matching uses them on
every page, the backoffice included. An organiser whose browser prefers Polish
would get:

- five Polish strings, with the rest of the backoffice still in English
- Polish date and number formatting
- `<html lang="pl">` on a page that is mostly English, so a screen reader reads
  the English with Polish pronunciation

There is no language switcher in the UI today (`get_supported_languages()` has
no callers in the templates), so the change would happen silently, driven only
by browser settings.

Options:

- **a. A separate list of registration languages.** Public registration pages
  accept any of the 24. Every other page negotiates only among languages whose
  catalogues are substantially complete (today `en` and `hu`).
- **b. Rely on decision 1a.** If the thank-you page uses `page.language`, it
  doesn't need browser matching. The new languages can then have catalogues
  without being added to `SUPPORTED_LANGUAGES`. `load_translations()` in
  `src/opendlp/translations.py` only loads locales in `config.LANGUAGES`, so we
  would need to check how Flask-Babel's `force_locale` handles a locale that is
  not on the list before relying on this.
- **c. Add all 24 to the global list** and accept a mixed-language backoffice
  for organisers whose browsers prefer one of the new languages. Simplest, but
  it causes the accessibility problem above.

### 3. Who reviews the translations?

Our policy (see `.gettext-auto.toml` and `docs/translations.md`) is that any
translation an agent writes is marked fuzzy. `msgfmt` leaves fuzzy entries out
of the `.mo` file, so they display in English until a person clears the flag
with `just translate-accept-fuzzy` or by hand.

An agent can write all 110 translations. They are short and conventional, and
for most of these languages the quality should be good. Confidence is lowest for
Irish and Maltese, which have far less training data, and somewhat lower for the
Baltic languages.

Options:

- **a. Native-speaker review for each language** before accepting the entries.
  Best quality, but it needs 22 reviewers or a translation service.
- **b. Review where we can, accept the rest.** Accept the languages someone on
  the team or among our partners can check. Accept the others after a sanity
  check, for example a back-translation. Treat Irish and Maltese as provisional.
- **c. Accept them all as written by the agent.** Fastest. A wrong translation
  of "We'll be in touch." does little harm, but it is shown to the public.

### 4. Register: formal or informal

The Hungarian style guide (`translations/styleguide-hu.md`) uses the formal
register for public-facing pages and the informal one for the backoffice. These
strings are public, so the natural default is the formal register in every
language that has the distinction: German's formal "you", *vous*, *usted*, *Lei*,
*Vy*, *Pan/Pani* or an impersonal phrasing, and so on. In Nordic languages and Dutch, informal
forms are normal even in official text (*du*, *je*), so "formal" there means
following what local public services actually use.

We would like the team to confirm that, and to say whether we want a short style
guide per language (like `styleguide-hu.md`) now, or only when a language's
catalogue grows past these five strings.

### 5. Should the English wording change first?

Every English change made after the translations exist has to be repeated in 23
languages, so now is the cheapest time to change the wording. Two candidates:

- **"Please click here if you wish to start a new registration."** "Click here"
  is weak link text: it assumes a mouse, and read on its own, out of context, it
  does not say where it goes. Something like "Start a new registration" would be
  better link text and easier to translate.
- **"Thank You"** in the `<title>` is title-cased, while the heading is sentence
  case. A title such as "Registration received" or "Thank you for registering"
  would match the heading and the conventions in `docs/language.md`.

## Practical consequences

### Catalogue size

gettext has no partial catalogues. `pybabel init` creates a full `.po` for each
language, which means about 2,229 entries, nearly all untranslated. The
Hungarian catalogue is about 450 KB, so 22 more add very roughly 9–10 MB to the
repository. After that, every `just translate-regen` updates 24 files, and the
diff for one changed string appears in 24 places. The `normalise-po` pre-commit
hook keeps each of those diffs to the entries that changed, so this is noise in
diffs, not churn across whole files.

An untranslated entry falls back to the English msgid at runtime, so the empty
entries are harmless.

### Language names

`get_supported_languages()` in `src/opendlp/config.py` maps codes to display
names, and most of the 22 are missing from that mapping (they would show as `BG`,
`HR` and so on). Nothing in the templates uses it today, but if a language
switcher is ever added it should show each language's own name (*български*,
*hrvatski*, *Gaeilge*, *Malti*, …). Babel can supply these
(`Locale.parse(code).get_display_name(code)`), which may be better than
extending the hand-written mapping.

### Build and CI

Nothing new is needed. `just translate-compile`, the `Dockerfile` and the
`setup-env` CI action all compile every catalogue under `translations/`, and
`just translate-check` runs `msgfmt --check` over each one.

### Tests

At minimum:

- a parametrised test, one case per locale, that renders the default thank-you
  page and checks that the translated heading appears, so a fuzzy or missing
  entry fails CI rather than quietly showing English;
- a check that every catalogue has the five msgids translated and not marked
  fuzzy;
- if we take decision 1a, a test that a page with `language` set renders its
  thank-you page in that language whatever `Accept-Language` the browser sends,
  and with the matching `<html lang>`.

## Summary of questions

1. Should the thank-you page follow the page's language or the visitor's?
2. Should the 22 new languages be negotiated across the whole app, only on
   registration pages, or only by explicit page language? What is
   `SUPPORTED_LANGUAGES` in production?
3. What review do the agent-written translations need before they go live?
4. Should we use the formal register on public pages, and do we want
   per-language style guides now or later?
5. Should we change "click here" and "Thank You" before translating them?
