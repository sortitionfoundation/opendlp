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

| Say | Meaning | Not |
| --- | --- | --- |
| assembly | A citizens' assembly: the thing an organiser sets up and runs a selection for | |
| citizens' assembly | The same, in introductory or public-facing prose | |
| respondent | Anyone in an assembly's data, whatever their status | registrant, applicant |
| pool | The respondents who have not been selected | |
| target | One thing the selection balances on, such as Gender or Age | category, target category, feature |
| value | One option within a target, such as Woman or 18-24 | category value |
| min, max | The fewest and most people with a value that a selection may pick | quota |
| targets | All of an assembly's targets together: "Edit targets", "Targets saved" | |
| selection | Choosing people from the pool by stratified random lottery | draw, lottery, sortition |
| selection run | One run of the selection, recorded in the run history | |
| test selection | A selection run that is not for real | |
| replacement selection | A selection run to fill places left by people who withdrew | substitute, reserve |
| invite | What an admin sends so that someone can create an account | |
| assembly question | What the assembly is convened to decide | |

**assembly** is lowercase in running text: "Run the replacement selection for
this assembly". Use "citizens' assembly" where the reader might not know what an
assembly is — the home page, the invite email, "Set up a new citizens'
assembly." Straight apostrophe.

**target** is the standard word for Gender, Age and the like, replacing
"category": "Add target", "Target name", "Delete target". It is what the
redesigned targets editor says. The legacy targets page, the sortition-algorithms
library and the domain classes (`TargetCategory`) still say category or feature;
none of those are the interface's word. A few backoffice strings still say
"target category" or "category" — "No target categories defined yet.", the
"Create targets from respondent data" modal, the target check summary — and are
drift to fix in a pass, not a variant to copy. The Google Sheets tab labels
("Initial Selection Categories Tab:") name a tab the spreadsheet really has, and
are a harder case: the tab is named in the organiser's spreadsheet, not by us.

**respondent** is the word for a person in the data, at every stage: in the pool,
selected, confirmed, withdrawn. It is the dominant word by a long way. The code
still says `registrant` in places (`select_registrants_tab`, the `view_registrant`
page). Those are identifiers; the interface says "respondent". "registrant" in
the UI means something narrower — a visitor to a public registration page — and
appears in a single string.

**selection** is the backoffice word. "Democratic lottery" belongs to the brand
and to introductory text ("Open Democratic Lottery Platform", "Run the democratic
lottery selection for this assembly…"). "Sortition" appears only in "sortition
algorithm". Neither is the everyday name of the operation.

### Roles

| Label | What it is |
| --- | --- |
| Admin | Global role: sees and manages every assembly, users and invites |
| Organiser | Global role: can create assemblies |
| User | Global role: sees only the assemblies they have a role on |
| Assembly Manager | Per-assembly role: manages that assembly and its team |
| Confirmation Caller | Per-assembly role: calls selected respondents to confirm |
| Read Only | Per-assembly role: can look but not change |

These are the role names as the interface shows them, capitalised as names.
"Organiser" is always spelled with an *s*. Keep "administrator" for the "contact
an administrator" messages, where it means a person rather than the role. See
[roles-and-permissions.md](roles-and-permissions.md) for what each role can do.

### Google Sheets

| Say | Meaning | Not |
| --- | --- | --- |
| Google Sheets | The product | Google Sheet, Google Spreadsheet, GSheet, gsheet |
| spreadsheet | One file in Google Sheets | sheet, document |
| tab | One tab inside a spreadsheet | worksheet, sheet |

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
The one "Worksheet / tab name" label predates this guide.

**Do not abbreviate the product to save space.** Where a label is tight, drop the
product name rather than shortening it — the heading or hint around it almost
always names it already. "GSheet" was never a user's word: it is the code's word
(`AssemblyGSheet`, `load_gsheet`), leaked into the interface. The Hungarian review
reached the same rule independently *(G36 in the Hungarian guide)*.

### Code names are not interface words

Identifiers and the words the interface uses have drifted apart in places. Never
put the code's word on the page.

| In the code | In the interface |
| --- | --- |
| `gsheet`, `GSheet` | Google Sheets, spreadsheet |
| `registrant` (`select_registrants_tab`, …) | respondent |
| `db`, `DB` | database |
| `TargetCategory`, `category` | target |
| `TargetValue` | value |
| `feature` (sortition-algorithms) | target |
| `agent` (sortition-algorithms) | respondent |
| `committee`, `panel` (sortition-algorithms) | one possible line-up of the whole assembly |
| an `Enum` member's `.value` | its label from the labels dict beside the enum |

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
  reason *(A3)*.
- **"We" is fine where a real organisation is speaking** — the public
  registration pages, the emails, the error pages ("Something went wrong on our
  end").

### Spelling

- **British English**: organise, optimisation, initialise, normalised,
  cancelled. The app strings are already consistent; keep them so.
- **email**, not e-mail, lowercase in running text.

### Words

- **Sign in / sign out**, not log in / log out. The buttons and headings already
  say "Sign in"; some older flash messages still say "log in".
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
  data: "Category '%(name)s' added". This is the dominant form; a few newer
  strings use double quotes.
- **Flash messages**: no full stop on a single sentence, full stops when there
  are several. That is what most of them do already.
- **No lone `%`** in a msgid; it breaks at render time. See `AGENTS.md`.

## Still open

Each of these is a place where the English calls one thing by two names or one
name means two things. Recommendations are recommendations; settle them here
before sweeping the source.

1. **Title Case or sentence case.** The redesigned backoffice templates are about
   70% sentence case; the Title Case is concentrated in the legacy screens and
   the older admin pages. At least 44 msgids exist twice differing only in case
   — "Save Changes" / "Save changes", "Target Name" / "Target name" — and each
   pair is two entries for a translator. *Recommend sentence case* for every new
   string, which is what GOV.UK prescribes and where the redesign is already
   heading, reusing the existing sentence-case msgid where there is one. With the
   legacy screens out of scope, the remaining Title Case is small enough to sweep.
2. **participant.** Used both for everyone in the pool ("participants with the
   same address") and for only the people selected ("Successfully selected
   %(num)s participants"). One string defines one term with the other:
   "Respondent data (participant information)". *Recommend* **respondent** for
   anyone in the data, and **participant** only for someone selected.
3. **replacements** is both the process ("Run Replacements") and the people
   ("Available replacements:"), and those people are also "replacement
   participants" and "replacement members". *Recommend* **replacement selection**
   for the process and **replacements** for the people.
4. **Dashboard** labels both the per-assembly statistics tab and the link to the
   list of assemblies, in one msgid. The Hungarian guide has the same complaint
   *(B11)*. *Recommend* **Statistics** for the tab and **Your assemblies** (or
   "Assemblies") for the list, and splitting the msgid.
5. **Pool as a status name.** "Reset all respondents to Pool" capitalises Pool
   mid-sentence as a status, while "remain in pool" does not. The Hungarian
   guide lists this pair as badly worded *(F35)*. *Recommend* "Reset %(count)s
   respondents to the pool", and capitalising a status only where it appears as
   a label or tag.
6. **Two names for one thing.** "registration page" and "registration form";
   "invite code" and "invitation code"; "Site Admin" and "Site Administration";
   "Address Columns" / "Columns to Keep" on the Google Sheets form and "Address
   Attributes" / "Attributes to Keep" on the database one. *Recommend* the first
   of each pair.
7. **member(s)** means both an assembly's team ("Team Members") and respondents
   ("replacement members"). *Recommend* keeping "team member" for the team and
   never using "member" for a respondent.
8. **Small punctuation drift**: "…" and "..." both appear — "Processing…" and
   "Processing..." are separate msgids; em dashes in newer strings but a spaced
   hyphen in older ones ("Admin - Full system access"); "N/A" in two places and
   "—" or "-" in other empty cells. *Recommend* "…", the em dash, and "—" for an
   empty cell, which is where the newer strings already are.
