# 1024 — Project details absorbs Data Source and Team Members

Shortcut sc-1024. The second of two plans for this branch; read
[plan-create-project.md](plan-create-project.md) first — it defines the data
source form and the three stored choices that this page shows.

**Status: agreed, not yet implemented.** Two rounds of questions are answered
and folded into the text; the answers are logged under
[Decisions](#decisions). Nothing is open.

Design: OpenDLP - UI Figma file, nodes 6025-7141 (Google Sheet project),
6860-17012 (In OpenDLP, CSVs imported), 6030-8378 (add a team member).

## The page

Four cards in one column, under the tab bar:

```
Basic details
  Project title        Walthamstow People's Panel on Hate Crime   ✎
  Project question     How do we live together well?              ✎
  Status               ● Active
  Panel size           10                                         ✎
  First event date     01 Apr 2026                                ✎
  Created              by Hamish Downer on 24 Feb 2026 at 17:34
  Last updated         24 Feb 2026 at 17:34

Data source                                                       ⚙
  Data location                In OpenDLP
  Target data source           Import from CSV    [4 targets uploaded]
  Respondents data source      Import from CSV    [100 respondents uploaded]

Registration link                                           See all (3)
  URL link             https://…/register/walthamstow
  Short URL link       https://…/r/abc123
  QR code              ⤓ Download

Team                                          [ Add a team member ]
  User            Email                          Role
  Hamish Downer   hamish@…                       Project manager   🗑 ✎
```

The Data Source and Team Members tabs go. The "Edit project" page goes.

## What exists today

| Thing | Where |
| --- | --- |
| Details page | `backoffice.view_assembly` (`backoffice.py:157`), `templates/backoffice/assembly_details.html` |
| Edit page | `backoffice.edit_assembly` (`:516`), `EditAssemblyForm`, `assembly_service.update_assembly` (`:87`) — which recalculates target min/max when the panel size changes |
| Panel size dialog on the Selection tab | `backoffice.update_number_to_select` (`:591`) — stays |
| Edit in place | `profile/_name_row.html` + `components/inline-edit.js` + `profile.edit` (branch 869) |
| Members page | `backoffice.view_assembly_members`, `add_user_to_assembly`, `remove_user_from_assembly`, `search_users` (`:793-1010`), `templates/backoffice/assembly_members.html` |
| Member services | `grant_user_assembly_role`, `revoke_user_assembly_role`, `sole_assembly_manager_id` (`user_service.py:811-930`) |
| Registration rows | `registration_hub.registration_page_rows` (URLs and QR per page); pages come back oldest first |
| Tabs | `components/assembly_tabs.html`; every link carries `?source=` |

## Basic details: edit in place

### A row macro that is not about names

869's `name_row` is specific to My account: its ids, its endpoint and its
labels are profile's. The mechanism is general. So:

- `components/inline_edit_row.html` gets a macro
  `inline_edit_row(row_id, field, label, value, action, kind, …)` holding what
  `name_row` holds now — the form, the htmx attributes, the pencil/tick/X, the
  hidden `field` and `return_focus`. `kind` picks the control: `text`,
  `textarea`, `number`, `date`.
- `profile/_name_row.html` becomes a three-line call to it, so there is one
  implementation and My account's tests guard the refactor.
- `inline-edit.js` is reused as it is, with one addition for the textarea
  (below).

869 is merged to main (PR #417) and this branch sits on that merge commit, so
`name_row` is main's code now. The generalisation happens here, in its own
commit, before any project field uses it.

### The four fields

| Field | Control | Notes |
| --- | --- | --- |
| Project title | text | Required, 3–200. Saving also updates the page heading and the browser title (out-of-band swap). |
| Project question | textarea | Optional, ≤1000. Empty shows "Not set" in muted text with the pencil. |
| Panel size | number | ≥0. Saving recalculates target min/max, as the edit page does today. |
| First event date | date | Optional. Native date input. |

**The textarea.** The tick or leaving the row saves, as for the other rows.
Enter adds a line; Ctrl+Enter (⌘+Enter) also saves. Escape and the X cancel.
This is the one addition to `inline-edit.js`.

**Panel size.** Saving behaves as the edit page does — values with an intact
auto-calculate link get new min/max (`recalculate_minmax_for_assembly`); those
set by hand or imported are left alone — but the flash now says so.
`update_assembly` discards the list of changes the recalculation returns; it
will pass them back so the route can choose between "Panel size saved." and
"Panel size saved. Target min and max recalculated." The second appears only
when something actually moved.

**Status** is read-only. Archiving is out of scope: it would also need
archived projects hidden from the normal list and a way to see them, which is
a story of its own. Created and Last updated are read-only; Last updated is
refreshed out of band on each save so it is never stale.

### The endpoint

`POST /backoffice/project/<id>/edit-field`, `field=<name>` plus the value —
one field per request, validated by the matching field of `EditAssemblyForm`,
saved through `update_assembly`. Answers as `profile.edit` does:

- **200** — the row at rest, plus out-of-band: the success flash, Last
  updated, and for the title the heading;
- **422** — the row still open with the reason under the field;
- **without htmx** — redirect to the details page with a flash.

`GET/POST …/edit` (the old edit page) redirects to the details page; the
template `edit_assembly.html` and the `assembly_form` macro go once the create
dialog no longer uses them.

Viewers who cannot manage the project see the rows with no pencils.

## Data source section

Rows depend on the location (from `determine_data_source`, create plan):

- **In Google Sheets:** "Data location" and "Spreadsheet URL" (a link,
  truncated with the full URL as its title), then the access check.
- **In OpenDLP:** "Data location", "Target data source", "Respondents data
  source" — each showing the stored choice's label, with a count tag when
  there is data.

Figma labels the first row "Where is your data stored?". Step 2 now asks
"Where will you manage your data?", which does not work as a row label, so the
row takes step 2's *name*.

The cog (labelled "Data source settings", `aria-haspopup="dialog"`, managers
only) opens the settings dialog from the create plan: the same form as step 3,
titled "Data source settings", with the location dropdown at the top — enabled
until the project has data, disabled with today's explanatory hint after. That
answers the brief's "that exact modal, or a new one": **a new wrapper around
the same form**. The create dialog's stepper and "Create new project" title
would be wrong on a project that already exists.

Saving or closing the dialog refreshes the section (and the tab bar, whose
enabled tabs depend on the data).

Things the old tab did that need a home:

| Old tab | New home |
| --- | --- |
| Google Sheet access check (runs after save, and on demand) | The Data source card: the `gsheet_access_status` partial under the URL row, loaded after a save, with its "Check again" button. Visible without opening anything, because a failed check is the thing an organiser most needs to see |
| Remove Google Sheet settings (the way to unlock) | In the settings dialog, a destructive link beside the form, like "Delete targets" |
| Tab names, team settings (view mode) | Only in the settings dialog. The card stays two rows, as Figma. |
| Example CSV links | In the dialog's CSV panels |
| "Create targets from respondent data" | Already on the Targets tab; not repeated |
| CSV selection settings | The Select and replace tab — next section |

### What the two source rows say

| Stored choice | Data | The row shows |
| --- | --- | --- |
| Import from CSV | some | "Import from CSV" and the tag "4 targets uploaded" |
| Create inside OpenDLP / Through OpenDLP registration | some | the choice and the tag "4 targets" / "100 respondents" |
| any | none | the choice, no tag |
| none ("Decide later") | some | no source text, only the tag "4 targets" / "100 respondents" |
| none | none | "Decide later" |

The tag says "uploaded" only when the stored choice is CSV. The fourth row is
what every existing project with data shows on the day this ships, since no
project has a stored choice and nothing records how its targets were made. No
data migration guesses one. Location is inferred for those projects, as now.

### Selection settings move to Select and replace

For an In OpenDLP project the old tab ended with the selection settings form
(`DbSelectionSettingsForm`: check same address, address attributes, attributes
to keep), and selection is refused until it has been saved once
(`settings_confirmed`). It moves to the Select and replace tab, where it is
needed:

- The form, with its hints listing the respondents' columns, becomes a
  "Selection settings" section on the Selection tab, shown for In OpenDLP
  projects once respondents exist. Unconfirmed, it is open and sits above the
  selection steps; confirmed, it is collapsed to a summary with an Edit
  control, so it does not push the steps down the page every visit.
- The tab's existing "confirm your settings" warning
  (`assembly_selection.html:57`) and the step that reports settings missing
  (`selection_steps.html:8`) point at the section on the same page instead of
  at the Data Source tab.
- `db_selection_backoffice.save_db_settings` keeps its URL and its service
  calls; its success redirect and its error re-render go to the Selection tab.
- The Selection tab is disabled until the project has both targets and
  respondents, so nobody reaches the form before it can be filled in.

This may become its own small dialog later, depending on user testing; the
form is kept as a self-contained partial so that would be a small move.

Google Sheet projects are unaffected: their equivalent settings are fields of
the sheet form.

## Registration link section

One page's links only: the first published page; if none is published, the
first test page; otherwise the oldest. "First" within each is by creation
date. A project with an old closed page and a live one shows the live link.

| Pages | Rows | Header link |
| --- | --- | --- |
| none | (card body empty) | "Create" |
| one | URL link, Short URL link, QR code | "See details" |
| several | the first page's three rows | "See all (3)" |

The link always goes to the Registration tab. Rows reuse
`registration_page_rows`, which already builds both URLs and the QR download.
The count goes through `ngettext`-free phrasing — "See all (%(count)s)" — since
it only appears for two or more.

## Team section

The table from the members page — User, Email, Role — with a bin and a pencil
per row and "Add a team member" in the card header, all for those who
`can_manage_assembly_members`; others see the table alone.

The role cell is `role.role.value` today, which the enum rule forbids. It gets
a labels dict (`assembly_role_labels`, short forms: "Project manager",
"Confirmation caller", "Read only") beside `assembly_role_options`.

### Add

A fragment dialog from the details page's dialog host:
`GET …/members/add` returns it, `POST` adds and answers with the refreshed
Team card and a closed dialog, or 422 with the dialog and the error.

One person per submit, with two buttons: **Add**, which closes the dialog, and
**Add and add another**, which adds, refreshes the Team card behind the
dialog, and hands back an empty form with focus in the search field and a
line saying who was just added. Figma's several-rows-at-once form is not
built: this gives most of its convenience without per-row errors or partial
failures, and each person's notification email follows one clear success.

Role is a dropdown in Figma; today it is a radio group whose labels explain
each role ("Project Manager — Can manage the project and add other users").
The dropdown uses those same long labels as its options so the explanation is
not lost.

### Change role

New: no route does this today. The pencil opens a small dialog — the person's
name and email as text, the role dropdown, Save.
`POST …/members/<user_id>/role`.

`grant_user_assembly_role` updates an existing role in place but does **not**
check whether it demotes the last project manager. The check is added in the
service (raising `CannotRemoveLastAssemblyManager`, as revoke does), with the
same admin exemption revoke has, and the pencil is hidden where the bin is
hidden today (sole manager, non-admin viewer).

### Remove

The bin, with a confirmation: `$confirm`, the browser's own `confirm()`, as
the members page and the delete buttons across the backoffice use now. A
design-system alert dialog would be nicer, and is better made as its own
change across the backoffice than started here.

`POST …/members/<user_id>/remove` gains an htmx branch that answers with the
Team card. Removing yourself from a project you can then no longer see answers
`HX-Redirect` to the dashboard.

## Tabs

- "Data Source" and "Team Members" leave `assembly_tabs`.
- `GET …/data` and `GET …/members` redirect to the details page (to
  `#data-source` and `#team`), so bookmarks still work.
- About 50 `url_for('backoffice.view_assembly_data')` calls across
  `respondents.py` (20), `targets.py`, `gsheets.py`, `db_selection_backoffice.py`
  and six templates are re-pointed: error exits to the details page, and the
  "go and upload data" prompts on the Targets, Respondents and Selection tabs
  to the details page with the settings dialog open (`?data_source=1`, in the
  manner of `?edit_number=1`).
- `?source=` comes off every tab link, and `get_assembly_nav_context` stops
  taking a preferred source: the stored `data_source` replaces it (create
  plan). Done in this branch, so an unlocked project never has two sources of
  truth. A stray `?source=` on an old bookmark is ignored.
- With "In OpenDLP" as the fallback location, a brand new undecided project
  has its Targets tab enabled (today, with no `?source=`, all three data tabs
  are disabled). Respondents and Select and replace stay disabled until there
  is data, as now.

## Layout

The four cards sit in one column of the width Figma gives them (620px), not
the full page. Label column and row height follow what 869 settled for My
account (192px labels, dividers) rather than Figma's 112px, so the two pages
that share the row macro look the same.

Two things Figma shows are left as they are: the tab reads "Registration" (not
"Registration fields"), and the page heading stays the project title, which
updates when the title is edited.

## Tests

- **Unit:** the `inline_edit_row` macro for each kind; the role labels; the
  last-manager guard on a role change; the source rows table above, case by
  case; which registration page is chosen (published, test, oldest) and the
  header link for 0, 1 and N pages; `update_assembly` reporting what the
  recalculation moved.
- **Component:** `edit-field` for each field — 200, 422, without htmx, without
  permission, unknown field name; the heading and Last updated out-of-band
  swaps; the two panel size flashes; the old `/edit`, `/data`, `/members`
  URLs redirecting; the Team card's add / add another / change / remove with
  their htmx and plain branches; the selection settings section on the
  Selection tab (open when unconfirmed, saving confirms, errors re-render
  there); a read-only viewer sees no pencils, cog, bin or Add button.
- **Integration:** role change persisted; last-manager guard against the
  database.
- **JS (vitest):** `inline-edit.test.js` extended for the textarea behaviour.
- **BDD:** `backoffice-assembly.feature` (edit scenarios become edit-in-place),
  `backoffice-assembly-members.feature` (dialog; new change-role scenarios),
  `backoffice-assembly-gsheet.feature` and `backoffice-csv-upload.feature`
  (start from the cog, not the tab; lock and delete-unlocks), and every
  scenario elsewhere that navigates via the Data Source tab.
- **e2e:** `test_backoffice_assembly.py`, `test_assembly_user_management.py`,
  `test_assembly_gsheet_crud.py`, `test_backoffice_respondents.py` follow the
  moved routes.
- **Docs:** `component_accessibility.md` (the "Edit in place" row now names the
  shared macro), the showcase entry for it, `roles-and-permissions.md` if the
  role-change guard is news to it.

The test churn from removing the Data Source tab is the largest single cost in
either plan — most CSV and Google Sheet scenarios start there.

## Order of work

After steps 1–3 of the create plan (schema, form partial, settings dialog):

1. `inline_edit_row` extracted; My account switched to it.
2. Basic details card with the four fields; old edit page removed.
3. Data source card and the cog; access check rehomed.
4. Selection settings section on the Select and replace tab.
5. Registration link card.
6. Team card: table, add dialog, remove; then change role with its guard.
7. Tabs removed, redirects, the ~50 re-pointed links, `?source=` removed.
8. BDD/e2e sweep, catalogues, docs.

Steps 2–6 each leave a working page with the old tabs still present, so the
branch can be reviewed card by card; step 7 is the one that removes things.

---

## Decisions

Both rounds of questions, for the record.

| # | Question | Decision |
| --- | --- | --- |
| D1 | What saves the framing question | Tick or leaving the row; Enter adds a line; Ctrl/⌘+Enter saves; Escape and X cancel |
| D2 | Panel size recalculates min/max | Same as now, and the flash says so when something moved |
| D3 | Status and archiving | Out of scope: needs hiding and listing archived projects too |
| D4 | Where the sheet access check shows | In the Data source card, under the URL |
| D5 | Existing projects' source rows | No stored choice and data exists: the count only |
| D6 | Which registration page, which rows | First published, else first test, else oldest; URL, short URL and QR |
| D7 | Adding several team members | One per submit, plus "Add and add another" |
| D8 | Confirming a removal | Keep `$confirm` |
| D9 | Removing `?source=` | In this branch |
| D10 | Layout | My account's rows, Figma's card width |
| D11 | Figma's tab name and heading | Left as they are |
| O1 | First row's label in the Data source card | "Data location" |
| O2 | Shape of selection settings on Select and replace | Open above the steps until confirmed, then collapsed to a summary with Edit |
