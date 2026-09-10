# Language

The words OpenDLP's interface uses for things, and the conventions for writing
its English text. Read this before writing or rewording a user-facing string —
a flash message, a label, a hint, an email — whether you are a person or an
agent. `/sf-code-review` checks new strings against it.

This is the English counterpart of
[`translations/styleguide-hu.md`](../translations/styleguide-hu.md). That guide
decides how Hungarian says things; this one decides what the English source says,
which every translation starts from. When the English calls one thing by two
names, every translator has to work out whether they are the same thing, and
usually has to ask.

## How to use this

**Consistency matters more than the individual choice.** A reader who meets
"Google Spreadsheet" on one screen and "Google Sheet" on the next has to stop and
wonder whether they are different. So use the words below even where you would
have picked another.

**Rewording an existing string costs its translation.** Changing a msgid's
English discards the translation in every language — see the i18n section of
[`AGENTS.md`](../AGENTS.md). So do not tidy up an old string's wording in passing.
Write new strings to this guide; fix old drift in a deliberate pass of its own,
one term at a time, as was done for Google Sheets.

**The legacy screens are out of scope.** The templates under `main/` (apart from
the home page), `targets/`, `respondents/`, `db_selection/` and `gsheets/`, served
by the `*_legacy` blueprints, are due to be retired. Much of the drift below
lives there — the Title Case headings, the old "category" vocabulary — and is not
worth a retranslation to fix. This guide is for the backoffice, the public
registration pages and the emails.

The sections below are settled. Things the English has not yet made up its mind
about are listed under [Still open](#still-open) at the foot, each with a
recommendation. Until one is settled, match the part of the app you are working
in, and don't add a third variant.

## Glossary

### Domain

| Say                   | Meaning                                                                       | Not                                |
| --------------------- | ----------------------------------------------------------------------------- | ---------------------------------- |
| assembly              | A citizens' assembly: the thing an organiser sets up and runs a selection for |                                    |
| citizens' assembly    | The same, in introductory or public-facing prose                              |                                    |
| respondent            | Anyone in an assembly's data, whatever their status                           | registrant, applicant, member      |
| participant           | A respondent who has been selected for the assembly                           | member                             |
| pool                  | The respondents who have not been selected                                    |                                    |
| remaining respondents | The pool, once a selection has run                                            | unselected                         |
| target                | One thing the selection balances on, such as Gender or Age                    | category, target category, feature |
| value                 | One option within a target, such as Woman or 18-24                            | category value                     |
| min, max              | The fewest and most people with a value that a selection may pick             | quota                              |
| targets               | All of an assembly's targets together: "Edit targets", "Targets saved"        |                                    |
| selection             | Choosing people from the pool by stratified random lottery                    | draw, lottery, sortition           |
| selection run         | One run of the selection, recorded in the run history                         |                                    |
| panel                 | One possible line-up of the whole assembly; a selection picks one             | committee, line-up                 |
| test selection        | A selection run that is not for real                                          |                                    |
| replacement selection | A selection run to fill places left by people who withdrew                    | replacements, substitute, reserve  |
| replacements          | The people a replacement selection selects                                    | replacement participants, members  |
| team member           | A user with a role on an assembly                                             | member (for a respondent)          |
| registration page     | The public page where people put themselves forward for an assembly           | registration form                  |
| invite                | What an admin sends so that someone can create an account                     |                                    |
| invite code           | The code in an invite                                                         | invitation code                    |
| assembly question     | What the assembly is convened to decide                                       |                                    |

**assembly** is lowercase in running text: "Run the replacement selection for
this assembly". Use "citizens' assembly" where the reader might not know what an
assembly is — the home page, the invite email, "Set up a new citizens'
assembly." Straight apostrophe.

**target** is the standard word for Gender, Age and the like, replacing
"category": "Add target", "Target name", "Delete target". It is what the
redesigned targets editor says. The legacy targets page, the sortition-algorithms
library and the domain classes (`TargetCategory`) still say category or feature;
none of those are the interface's word, and nor is "target category". The
Google Sheets tab labels
("Initial Selection Categories Tab:") name a tab the spreadsheet really has, and
are a harder case: the tab is named in the organiser's spreadsheet, not by us.

**respondent** is the word for a person in the data, at every stage: in the pool,
selected, confirmed, withdrawn. It is the dominant word by a long way. The code
still says `registrant` in places (`select_registrants_tab`, the `view_registrant`
page). Those are identifiers; the interface says "respondent". Someone looking
at a public registration page is a **visitor**.

**participant** is narrower than respondent: only someone who has been selected.
"Successfully selected %(num)s participants" is right. The address check looks
for "respondents with the same address", because it means everyone in the pool.

**pool** is the respondents who have not been selected, and it works whether or
not a selection has run yet. Once one has, "remaining respondents" says the same
thing and is often clearer: it is what the Google Sheets output calls them. A
replacement selection chooses from the pool and selects **replacements**. Keep
those two apart — "replacements" is the people, never the process, so the
button is "Run Replacement Selection", and the people are just "replacements",
not "replacement participants" or "replacement members". Whether the
per-person status should also say "Pool" is [still open](#still-open).

**team member** is a user with a role on an assembly: "Team Members". "Member"
never means a respondent, whatever state they are in.

**registration page** is the thing an organiser creates, publishes and closes —
not "registration form".

**selection** is the backoffice word. "Democratic lottery" belongs to the brand
and to introductory text ("Open Democratic Lottery Platform", "Run the democratic
lottery selection for this assembly…"). "Sortition" appears only in "sortition
algorithm". Neither is the everyday name of the operation.

### Roles

| Label               | What it is                                                      |
| ------------------- | --------------------------------------------------------------- |
| Admin               | Global role: sees and manages every assembly, users and invites |
| Organiser           | Global role: can create assemblies                              |
| User                | Global role: sees only the assemblies they have a role on       |
| Assembly Manager    | Per-assembly role: manages that assembly and its team           |
| Confirmation Caller | Per-assembly role: calls selected respondents to confirm        |
| Read Only           | Per-assembly role: can look but not change                      |

These are the role names as the interface shows them, capitalised as names.
"Organiser" is always spelled with an _s_. Keep "administrator" for the "contact
an administrator" messages, where it means a person rather than the role. See
[roles-and-permissions.md](roles-and-permissions.md) for what each role can do.

### Pages

| Say             | Meaning                                         | Not                            |
| --------------- | ----------------------------------------------- | ------------------------------ |
| Your Assemblies | The list of assemblies you see after signing in | dashboard, backoffice homepage |
| Dashboard       | An assembly's statistics tab                    |                                |
| Site Admin      | The admin area                                  | Site Administration            |

**Your Assemblies** is the page heading the list already has. The team calls it
the "backoffice homepage", which is fine between ourselves and wrong on the page.
**Dashboard** is only the per-assembly statistics tab. Every link to the list —
the header, the error pages, "Back to Your Assemblies" — says so. The list page's
own heading still says "Dashboard"; that is [still open](#still-open).

### Google Sheets

| Say           | Meaning                      | Not                                              |
| ------------- | ---------------------------- | ------------------------------------------------ |
| Google Sheets | The product                  | Google Sheet, Google Spreadsheet, GSheet, gsheet |
| spreadsheet   | One file in Google Sheets    | sheet, document                                  |
| tab           | One tab inside a spreadsheet | worksheet, sheet                                 |

**Google Sheets** is Google's name for the product, and it is a proper noun. It
works as a name ("Export to Google Sheets", "Configure Google Sheets") and in
front of another noun ("Google Sheets configuration", "Google Sheets data"). It
does not work as a countable noun: "enter the URL of your Google Sheets" does not
parse.

**spreadsheet** is the file. Where the product has to be named, write "your
Google Sheets spreadsheet"; where the screen already says Google Sheets, a bare
"spreadsheet" is enough — "View spreadsheet", "Check Spreadsheet", "Could not
write to the spreadsheet". Not "document": in Google's own vocabulary a document
is a Google Doc, and a reader who goes looking in Drive for one will be misled.

**tab** is a tab within the spreadsheet, as the Google Sheets interface calls it.

**Do not abbreviate the product to save space.** Where a label is tight, drop the
product name rather than shortening it — the heading or hint around it almost
always names it already. "GSheet" was never a user's word: it is the code's word
(`AssemblyGSheet`, `load_gsheet`), leaked into the interface. The Hungarian review
reached the same rule independently _(G36 in the Hungarian guide)_.

### Code names are not interface words

Identifiers and the words the interface uses have drifted apart in places. Never
put the code's word on the page.

| In the code                                   | In the interface                               |
| --------------------------------------------- | ---------------------------------------------- |
| `gsheet`, `GSheet`                            | Google Sheets, spreadsheet                     |
| `registrant` (`select_registrants_tab`, …)    | respondent                                     |
| `db`, `DB`                                    | database                                       |
| `backoffice.dashboard`, "backoffice homepage" | Your Assemblies                                |
| `TargetCategory`, `category`                  | target                                         |
| `TargetValue`                                 | value                                          |
| `feature` (sortition-algorithms)              | target                                         |
| `agent` (sortition-algorithms)                | respondent                                     |
| `committee` (sortition-algorithms)            | panel                                          |
| an `Enum` member's `.value`                   | its label from the labels dict beside the enum |

The sortition-algorithms library writes its own run reports in optimisation
jargon, and its messages are extracted into our catalogue. We cannot reword those
here, only translate them. The last row is also a translation bug, not only a
wording one: see "Never render an `Enum` member's `.value`" in `AGENTS.md`.

## Writing

### Voice

- **Address the reader as "you".** It is how the app already speaks.
- **In the backoffice, the software is not a person.** Say what happened, not
  what "we" did: "Respondents exported to Google Sheets", not "We've exported
  your respondents". The Hungarian guide makes the same call for the same
  reason _(A3)_.
- **"We" is fine where a real organisation is speaking** — the public
  registration pages, the emails, the error pages ("Something went wrong on our
  end").

### Spelling

- **British English**: organise, optimisation, initialise, normalised,
  cancelled. The app strings are already consistent; keep them so.
- **email**, not e-mail, lowercase in running text.

### Words

- **Sign in / sign out**, not log in / log out.
- **Cancel** is the button that backs out of a dialog or form without doing
  anything. **Back to …** is navigation.
- **Delete** destroys data: a respondent, a target, a tab. **Remove** undoes a
  relationship and leaves the thing itself: a user from an assembly, a sign-in
  method, a Google Sheets configuration. "Respondents deleted: %(count)d removed"
  is the kind of string this rules out.

### Punctuation

- **Straight quotes** everywhere, `'` and `"`. There are no curly quotes in the
  source.
- **Single quotes around a placeholder** the reader will match against their own
  data: "A target called '%(name)s' already exists".
- **Flash messages**: no full stop on a single sentence, full stops when there
  are several.
- **Ellipsis**: the single character `…`, not three full stops.
- **Dashes**: an em dash `—` where English wants a dash, not a spaced hyphen:
  "Admin — Full system access…", "Optional — your first name". The " - OpenDLP"
  at the end of page and email titles is a separator, not a dash, and stays a
  hyphen.
- **An empty table cell** shows `—`, not "N/A" or `-`.
- **No lone `%`** in a msgid; it breaks at render time. See `AGENTS.md`.

## Still open

Each of these is a place where the English calls one thing by two names or one
name means two things. Recommendations are recommendations; settle them here
before sweeping the source.

1. **Title Case or sentence case.** The redesigned backoffice templates are about
   70% sentence case; the Title Case is concentrated in the legacy screens and
   the older admin pages. At least 44 msgids exist twice differing only in case
   — "Save Changes" / "Save changes", "Target Name" / "Target name" — and each
   pair is two entries for a translator. _Recommend sentence case_ for every new
   string, which is what GOV.UK prescribes and where the redesign is already
   heading, reusing the existing sentence-case msgid where there is one. With the
   legacy screens out of scope, the remaining Title Case is small enough to sweep.
2. **What the pool status is called.** "pool" as the name of the group is
   settled — see the glossary — and so is writing it lowercase in running text:
   "Reset %(count)s respondents to the pool", not "…to Pool status" _(F35 in the
   Hungarian guide)_. What is open is the status tag on one person, which today
   also says "Pool".

   The statuses a real respondent moves through — Selected, Confirmed, Withdrawn,
   Deleted — each describe the person; "Pool" alone names a group, which is why
   "Status: Pool" reads oddly. (Test submission is a noun too, but it marks test
   data rather than a stage anyone passes through.) So the question may be less "is there a better word than pool?" than
   "should the status be a different word from the group?" The word has to work
   both before any selection and after one:

   | Status tag                | Before any selection       | After a selection                                                  | Against it                                                                                                                      |
   | ------------------------- | -------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
   | Pool (as now)             | fine                       | fine                                                               | a noun among adjectives                                                                                                         |
   | In pool                   | fine                       | fine                                                               | a phrase where the others are single words                                                                                      |
   | Remaining                 | odd: remaining after what? | exact, and matches "remaining respondents" and the Remaining tab   | only half the life of the status                                                                                                |
   | Available                 | fine                       | fine                                                               | assembly registration forms often ask whether someone is available for the dates, and it will be read as that                   |
   | Eligible                  | fine                       | fine                                                               | eligibility is a separate test (lives in the area, old enough) that selected people pass too                                    |
   | Unselected / Not selected | fine                       | reads as rejected, though they can still be drawn as a replacement |                                                                                                                                 |
   | Waiting                   | fine                       | promises a turn that may never come                                |                                                                                                                                 |
   | Registered                | fine                       | fine                                                               | selected people are registered too; respondents imported from a spreadsheet never registered; collides with "registration page" |
   | Candidate                 | fine                       | fine                                                               | in politics a candidate stands for election, which is what sortition replaces                                                   |

   _Recommend_ keeping **pool** for the group and making the tag **In pool**. It
   fixes the one thing wrong with "Pool" — that it names the group rather than
   describing the person — without bringing in a new concept, and it keeps the
   tag and the group visibly the same thing. If a single word matters more,
   **Remaining** is the runner-up. Either way it is a label
   change only: the enum value stays `POOL`, so one msgid changes and nothing in
   the database does.

3. **Columns, fields and attributes in the selection settings.** The Google
   Sheets form says "Address Columns", "Columns to Keep" and "ID Column", which is
   right: they are columns in the spreadsheet. The database settings form has the
   same settings as "Address Attributes" and "Attributes to Keep". "Fields" is
   the word the rest of the interface uses for these ("Fields are defined by
   your Google Sheets spreadsheet"), so "Address Fields" and "Fields to Keep" are
   the likely answer, but this is waiting on a team discussion.
4. **The Your Assemblies page's own heading.** Every link to the list now says
   "Your Assemblies", but the backoffice page itself has a hard-coded, untranslated
   `<h1>Dashboard</h1>` with "Your Assemblies" as the `<h2>` beneath it (and
   "Welcome back" and "Created:" are untranslated too). Renaming the `<h1>`
   alone would stack two identical headings. _Recommend_ an `<h1>` of "Your
   Assemblies", dropping the `<h2>` but keeping the "Create New Assembly" button
   beside it, and wrapping the remaining strings for translation. The legacy list
   page has the same pair of headings, and can stay as it is until it is retired.
5. **Capitalising "Citizens' Assembly".** The glossary writes "citizens'
   assembly" in lowercase, but the home page, the footer and the invite email
   capitalise it in running prose — "a platform for supporting Citizens'
   Assemblies", "Democratic Lottery and Citizens' Assembly management" — where it
   reads as a term of art. _Recommend_ lowercase in running text, capitals in
   headings and the brand, but this touches how the Sortition Foundation writes
   about itself, so it wants a decision rather than a sweep.
