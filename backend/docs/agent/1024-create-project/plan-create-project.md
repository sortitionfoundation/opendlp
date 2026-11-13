# 1024 — Create project in a three-step dialog

Shortcut sc-1024. One of two plans for this branch:

- this one: the **Create new project** dialog, and the data source form it
  shares with the project details page;
- [plan-project-details-tab.md](plan-project-details-tab.md): the project
  details page that absorbs the Data Source and Team Members tabs.

The split is by screen, but the two share one piece of work — the data source
form (step 3 here, the cog on the details page there) — and one schema change.
Both are described here and referred to from the other plan. Neither plan can
ship alone: removing the Data Source tab needs the form to exist, and the
dialog's last step needs somewhere to land.

**Status: agreed, not yet implemented.** Two rounds of questions are answered
and folded into the text; the answers are logged under
[Decisions](#decisions). Nothing is open.

Design: OpenDLP - UI Figma file, overview node 6025-5966. Figma draws two steps;
the decision since is three. Where this plan and Figma disagree, the brief wins
and the difference is listed under [Departures from Figma](#departures-from-figma).

## What exists today

| Thing | Where |
| --- | --- |
| Create page | `GET/POST /backoffice/project/new`, `backoffice.new_assembly` (`blueprints/backoffice.py:106`), `CreateAssemblyForm` (`forms.py:351`), `templates/backoffice/create_assembly.html` |
| Service | `assembly_service.create_assembly` (`:35`): checks `can_create_assembly`, makes the creator a project manager |
| Dashboard buttons | `templates/backoffice/dashboard.html:15` ("Create project") and `:45` ("Create your first project") |
| Data source page | `backoffice.view_assembly_data` → `render_assembly_data_page` (`backoffice.py:629-790`), `templates/backoffice/assembly_data.html` (603 lines) |
| Google Sheet form | `AssemblyGSheetForm` (`forms.py:359`), saved by `gsheets.save_gsheet_config` (`gsheets.py:1163`) |
| CSV uploads | targets: `targets.upload_targets_csv` (`targets.py:208`); respondents: `respondents.upload_respondents_csv` (`respondents.py:163`), which may detour to a confirm-diff page |
| Stepper | `stepper(items, mode="wizard")` in `components/stepper.html`, already used inside a dialog by the registration editor |
| Dialogs over htmx | the fragment-dialog host (`data-fragment-dialog-host`, `init/fragment-dialog-focus.js`), used by My account's password dialog; `init/htmx-422-swap.js` swaps a refused form back in |
| A dialog that re-renders as you choose | `target_sources/_setup_modal.html`: each `change` does an `hx-get` with the form's values and swaps the dialog body |

Two facts about the current data source that shape everything below:

1. **The data source is inferred, never stored.** `determine_data_source`
   (`assembly_service.py:657`) says "gsheet" if an `AssemblyGSheet` row exists,
   "csv" if the project has any target or respondent, and otherwise echoes the
   `?source=` query parameter. That is why every tab link carries `?source=`.
2. **"Locked" is the same inference.** The selector is disabled once either of
   those is true. Only the UI enforces it: no service refuses a CSV upload on a
   Google Sheet project, or a Google Sheet on a project with respondents.

## The flow

```
dashboard ──[Create new project]──▶ dialog
  step 1  Project details      title*, framing question, panel size
  step 2  Data location        Where will you manage your data?
                                 [In OpenDLP ▾ | In Google Sheets]
  step 3  Targets and people   depends on step 2
              In OpenDLP       → two dropdowns (+ CSV panels on "Import from CSV")
              In Google Sheets → the AssemblyGSheetForm fields
  [Save] ──▶ the new project's details page
```

- **Step 1.** Title is required (3–200 characters, as now). Framing question
  and panel size are optional; an empty panel size is stored as 0, as now.
  First event date is not asked for here — it is editable on the details page.
- **Step 2.** One dropdown, "In OpenDLP" selected by default.
- **Step 3, In OpenDLP.** Two dropdowns, both defaulting to "Decide later",
  each with an info icon carrying the text from the brief:

  | Target data source | Respondents data source |
  | --- | --- |
  | Decide later | Decide later |
  | Create inside OpenDLP | Through OpenDLP registration |
  | Import from CSV | Import from CSV |

  Choosing "Import from CSV" for either shows that kind's upload panel, lifted from
  the current data source page: the file input (and the ID column field for
  respondents), then once uploaded the green "4 targets uploaded" banner with
  "Delete targets" beside the heading (Figma node 6183-16836).
- **Step 3, In Google Sheets.** The `AssemblyGSheetForm`: URL, the five tab names,
  the two checkboxes, team configuration, and the three custom fields shown
  only when the team is "Custom". No source dropdowns.
- **Back.** Step 3 → 2 → 1 while nothing has been written. Once something has,
  step 2 is locked: Back from step 3 is gone, and the stepper shows step 2 as
  done.
- **The stepper shows progress; it is not navigation.** Wizard mode, steps are
  not links. Back and Next are the only way to move.
- **Leaving.** Before the project exists, ✕, Escape, the backdrop and Cancel
  ask "discard?" once anything has been typed (`dialogLeaveGuard`, as the
  target sources dialog does). Once it exists there is nothing to lose: the
  button reads **Close**, nothing is asked, and it goes to the new project.

## How it is built

### One host, one dialog, the server draws each step

The dashboard gets a fragment-dialog host. "Create new project" is an
`hx-get` to `GET /backoffice/project/new`, which answers with the dialog at
step 1. Each Next, Back and dropdown change is a request that returns the whole
dialog again, swapped into the host — the pattern of the target sources set-up
dialog. No step logic lives in JavaScript; Alpine only opens, closes and guards
the dialog (`modal`, `dialogLeaveGuard`).

**The wizard is stateless on the server.** What earlier steps collected rides
along as hidden inputs in the current step's form. No session state, no draft
row. Step 1's values are validated when Next is pressed (a 422 puts the step
back with the error under the field) and validated again when the project is
finally created, because hidden inputs are user input.

`GET /backoffice/project/new` without htmx renders the dashboard with the
dialog already open at step 1, as My account does for its password dialog. So
the URL still works as a link, and the existing "Create your first project"
link needs no special case.

That is as far as the no-JavaScript path goes. Steps 2 and 3 assume htmx; the
backoffice already relies on JavaScript in many places, and a create dialog
that does not work without it is acceptable.

### When the project is created

Uploading a CSV needs a project to upload into, so the project must exist
before the dialog's final Save in at least that case. It is created at the
first thing that writes:

| Path | The project is created when |
| --- | --- |
| In OpenDLP, no CSV | Save on step 3 |
| In OpenDLP, a CSV is uploaded | that upload (project first, then the import, one request) |
| Google Sheet | Save on step 3 (project and sheet settings together) |

Before that moment Cancel, the ✕ and Escape leave nothing behind. After it
the dialog is no longer "create": it is the data source form of an existing
project wearing the stepper. Cancel becomes Close, and closing it lands on
that project's details page with a flash saying the project was created.

The costs of doing it this way: step 1's values travel as hidden inputs, and
the two upload routes need a "create the project first" variant.

If the CSV import is refused (bad file, missing ID column), the project is
**not** created: the upload request creates and imports inside one unit of
work, and a refused import rolls both back. The dialog comes back at step 3
with the reason, still unlocked.

### One data source form, used twice

Step 3 and the details page's cog show the same thing, so there is one partial,
`templates/backoffice/data_source/_form.html`, taking the project (or none),
the chosen location, and whether the location is locked. Two wrappers:

- `_create_dialog.html`: title "Create new project", the stepper, Back.
- `_settings_dialog.html`: title "Data source settings", no stepper, and the
  location dropdown at the top (enabled until locked) — on an existing project
  there is no step 2 to go back to. See D-plan, *Data source section*.

A new blueprint module, `blueprints/data_source.py`, holds the dialog routes so
`backoffice.py` (already past 1000 lines) does not grow. The upload, delete and
sheet-save *services* are reused as they are; their *routes* get an htmx branch
that answers with the dialog instead of redirecting to the Data Source tab
(which will no longer exist).

### Storing the choices

"Decide later" and "Create inside OpenDLP" cannot be told apart by looking at
the data, and "you can return here when you know" means the dialog must
remember. So the three answers are stored, in three string columns on
`assemblies`:

| Column | Values | Default |
| --- | --- | --- |
| `data_source` | `""`, `opendlp`, `gsheet` | `""` |
| `targets_source` | `""`, `manual`, `csv` | `""` |
| `respondents_source` | `""`, `registration`, `csv` | `""` |

`""` reads as "Decide later" for the two sub-choices, and as "not yet stated —
infer it" for `data_source`. Plain strings validated in the domain (three small
`Enum`s with `_l()` label dicts, per the enum rule), not database enums.
Nullable-free columns with a `server_default` of `""` are a backwards
compatible migration: the previous release never reads or writes them. **No
downtime needed.** No data migration either: existing projects keep `""` and
the inference below covers them.

`determine_data_source` changes from "infer, else `?source=`" to "infer, else
the stored `data_source`, else `opendlp`":

- a sheet row → `gsheet`, locked;
- any target or respondent → `opendlp`, locked;
- otherwise the stored value, unlocked, with "In OpenDLP" as the fallback.

The function keeps answering in the two tokens the routes and templates
already compare against, `"gsheet"` and `"csv"` — `"csv"` meaning "held in
OpenDLP". Only the stored column says `opendlp`. Renaming the token everywhere
would touch every tab route for no change in behaviour.

**The lock stays inferred from real data. Storing a choice does not lock
anything.** Someone who picked "In OpenDLP", saved, and then learns the client
has a Google Sheet can still switch from the details page; switching away from
In OpenDLP clears the two sub-choices.

In practice an In OpenDLP project locks early, and by the organiser's own
hand: the standard workflow is to create targets first and build the
registration page from them, so the first target — typed on the Targets tab or
imported — locks the location long before anyone registers. Deleting every
target and respondent unlocks it, as now.

This also makes the `?source=` query parameter redundant — the unlocked
preference now has a home. Removing it from the tabs is in scope for the
details plan, where the tab bar changes anyway (D-plan, *Tabs*).

**The two sub-choices describe intent; they restrict nothing.** They decide
which panels the form shows and what the details page says. Nothing elsewhere
checks them: you can pick "Import from CSV" and still add a target by hand on
the Targets tab. Two rules keep them honest:

- If a kind already has data, its panel (count and Delete) shows whatever the
  dropdown says, so data is never hidden behind a "Decide later".
- A successful CSV upload stores "Import from CSV" for that kind there and
  then, without waiting for Save. Closing the dialog after an upload never
  leaves the details page saying "Decide later" beside "100 respondents
  uploaded".

### Step 3 with a Google Sheet

`AssemblyGSheetForm` as it is, rendered by the markup now in
`assembly_data.html`'s `render_gsheet_content` (edit/new modes), moved into the
partial. Team selection keeps its Alpine `selectedTeam` show/hide.

Save validates the form together with step 1's hidden values, then in one unit
of work calls `create_assembly` and `add_assembly_gsheet`. A refused form is a
422 with the dialog at step 3. On success: `HX-Redirect` to the details page,
where the sheet access check runs as it does today after a save (`?check=1`;
see D-plan, *Data source section*).

Today's soft warning when "columns to keep" is empty is a flash on the next
page; it stays a flash.

### Step 3 in OpenDLP

The two dropdowns re-render the dialog on `change` (`hx-get` with the form's
values, as the target sources dialog does), so the CSV panels appear without
client-side logic.

- **Targets CSV.** `hx-post` multipart to the targets upload route. Success
  re-renders the dialog with the banner. Today a successful upload redirects to
  the Targets tab; inside the dialog it stays put.
- **Respondents CSV.** Same, with the ID column field. On a *new* project there
  is no existing field schema, so the confirm-diff detour cannot arise. From
  the settings dialog on an existing project it can: the route answers
  `HX-Redirect` to the confirm-diff page as now, and that page's exits point at
  the details page instead of the Data Source tab.
- **Delete targets / Delete respondents.** As now, including the force-unlink
  confirmation page for targets linked to registration questions; its exits
  are re-pointed too. Deleting everything unlocks step 2 again, as it does
  today.
- **Save.** Stores the two dropdown values (and creates the project if nothing
  has yet). Then the details page.

Two things on the current CSV data page are not in the data source form. The
"Create from respondent data" dialog already lives on the Targets tab as well.
The **selection settings form** (check same address, address attributes,
attributes to keep) moves to the Select and replace tab — see the details
plan, *Selection settings*. It is not part of the create dialog: its hints
list the respondents' columns, which do not exist yet.

### Permissions

- Opening and using the dialog before the project exists: `can_create_assembly`.
- Every request once it exists (uploads, deletes, Save): `can_manage_assembly`
  on that project, as the existing routes already require. The creator is its
  project manager, so they pass.

### Legacy blueprint

`main.create_assembly_page` (`/assemblies/new`) and the other legacy pages are
untouched, except that any link from them to the Data Source tab is re-pointed
so nothing 404s. They have not been live for a while and can be deleted, but
not in this story: see
[../future_work/delete_legacy_pages.md](../future_work/delete_legacy_pages.md).

### The title rule from the clone CLI

Branch `1282-clone-cli` (unmerged, lower priority, will merge after this) adds
a rule about project titles. When it lands it must also apply at step 1's
Next, so the refusal comes at step 1 and not at Save on step 3. That is work
for *that* branch, since this one merges first. It is recorded here and
nowhere on that branch, so whoever rebases 1282 onto main needs to read this
paragraph.

## As built: where the code departs from the text above

Found while implementing; none changes what the organiser can do.

- **The dialog has routes of its own**, in `blueprints/data_source.py`, rather
  than htmx branches on the old upload and sheet-save routes. The old routes
  were written around redirects to the Data Source tab and are deleted with it;
  the new ones call the same services.
- **The two source dropdowns show and hide their CSV panels with Alpine**
  (`x-show`), not by asking the server to redraw. A redraw empties file inputs,
  so choosing a respondents source would have thrown away a targets file
  already picked. Only the *location* dropdown in the settings dialog redraws.
- **Deleting is a page load, not an htmx swap.** Delete targets, Delete
  respondents and Remove Google Sheets settings post to the existing routes
  (which own the "these targets have linked questions" confirmation page) and
  come back to the project details page with the settings dialog open
  (`?data_source=1`). In the create dialog that means a delete lands on the
  new project's page rather than back in the stepper.
- **What an upload reports is said in the panel**, not flashed: a flash would
  sit beneath the open dialog.
- **The routes enforce the lock.** A CSV posted at a project with a Google
  Sheet is refused, and a location posted at a locked project is ignored. The
  old page relied on a disabled dropdown.
- **Back and Next carry no name or id**, so that after each redraw focus goes
  to the new step's first field (or the refused one) rather than staying on
  the button. Back is not a submit button: on the last step, submitting saves.
- **The creation is flashed when it happens**, at the first upload or at Save,
  and shows on the next full page - the project's details page.
- **Team configuration stays a radio group**, as `AssemblyGSheetForm` renders
  it today; Figma draws a dropdown.
- **The dialog is wider than the standard one** (`dialog-panel--wide`, 55rem)
  to hold the two-column form.

## Departures from Figma

| Figma | This plan | Why |
| --- | --- | --- |
| Two steps | Three | Decided since |
| Source dropdowns on the Google Sheet path | None | Brief |
| "Select one" placeholders, Save disabled until chosen | Defaults ("In OpenDLP", "Decide later"), Save always enabled | Brief: defaults |
| "Enter manually" | "Create inside OpenDLP" | Brief |
| No check-same-address / generate-remaining-tab checkboxes on the sheet form | Present | Brief: "basically it is the AssemblyGSheetForm" |
| Required asterisks on the two source dropdowns | None | They have a default |

## Wording

Settled. Cheap to change if team review says otherwise.

| Where | Text |
| --- | --- |
| Button on the dashboard | "Create project" (unchanged) |
| Dialog title | "Create new project" |
| Step names | "Project details", "Data location", "Targets and people" |
| Step 2 label | "Where will you manage your data?" |
| Step 2 options | "In OpenDLP", "In Google Sheets" |
| First dropdown | "Target data source" |
| Second dropdown | "Respondents data source" (as Figma) |
| Target options | "Decide later", "Create inside OpenDLP", "Import from CSV" |
| Respondent options | "Decide later", "Through OpenDLP registration", "Import from CSV" |
| Footer | "Cancel" until the project exists, then "Close"; "Back", "Next", "Save" |

The two info icons:

- **Target data source:** If you're not sure, select "Decide later" - you can
  return here when you know. "Create inside OpenDLP" can mean entering targets
  by hand or creating them from imported respondent data - go to the Targets
  tab to do that.
- **Respondents data source:** If you're not sure, select "Decide later" - you
  can return here when you know. "Through OpenDLP registration" means you will
  set up a registration page for respondents to fill in - first set up
  targets, then go to the Registration tab.

"Targets and people" departs from the glossary, which says respondent
everywhere. That is deliberate for now; the glossary may be revisited after
this story, so `docs/language.md` is not changed here.

## Tests

- **Unit:** the three source enums and their labels; `Assembly` accepting and
  refusing source values; `determine_data_source` with stored values (the
  existing cases keep passing with the new fallback); the service that creates
  a project with sheet settings in one go, and the one that creates then
  imports and rolls back on a refused import.
- **Component (Flask test client):** each step's GET/POST with and without
  htmx; 422s with the error in place; hidden values tampered with; step 2
  locked after an upload; the upload/delete routes' htmx branches; permissions
  (a plain user cannot open the dialog; a non-manager cannot post to another
  project's form).
- **Integration:** the migration; persistence of the three columns;
  create-with-sheet and create-with-CSV against the real database.
- **JS (vitest):** nothing new is planned in JavaScript. If a component is
  added, it gets a test.
- **BDD:** `features/create-project.feature` replaces the create scenarios in
  `backoffice-assembly.feature` (`create-assembly.feature` is the legacy page
  and is left alone) — the three paths (decide later,
  CSV for both, Google Sheet), Back, Cancel leaving nothing, and step 2
  locking after an upload. `just build-all` first.
- **Showcase:** a "wizard dialog" entry in the patterns page, since this is
  the first stepper in a default-size dialog.

## Order of work

1. ✅ Migration, domain fields, enums and labels, `determine_data_source`.
2. ✅ The shared pieces (`data_source/_parts.html`: the Google Sheets fields,
   the example CSV link, the upload errors) extracted from `assembly_data.html`, rendered by the
   *existing* data source page first — a pure refactor, tests unchanged. The
   selection settings form is left behind on that page for now; the details
   plan moves it.
3. ✅ `data_source` blueprint: settings dialog on an existing project (used by the
   details plan), with the htmx branches on upload/delete/sheet-save.
4. ✅ Create dialog: steps 1 and 2, then step 3 for each path.
5. ✅ Dashboard buttons, old create page removed, BDD and docs, and
   `future_work/delete_legacy_pages.md` (written with this plan).

Steps 1–3 are shared with the details plan; step 3 is where the two meet.

---

## Decisions

Both rounds of questions, for the record.

| # | Question | Decision |
| --- | --- | --- |
| C1 | When the project comes into existence | At the first write: a CSV upload, or Save |
| C2 | Where the three choices are stored | Three string columns on `assemblies` |
| C3 | Does saving with no data lock step 2 | No. The lock is inferred from data. In practice the first target locks it |
| C4 | Do the sub-choices restrict anything | Intent only. An upload sets its dropdown to "Import from CSV" at once |
| C5 | CSV selection settings form | Moves to the Select and replace tab. Its own dialog is a possibility later, after user testing |
| C6 | Wording | Button stays "Create project"; "Targets and people"; "Where will you manage your data?"; "In Google Sheets" |
| C7 | Clickable stepper | No. Back and Next only |
| C8 | Leaving a half-filled dialog | Ask before the project exists; "Close" and no question after |
| C9 | Legacy `main` pages | Untouched here; deletion written up in `future_work/delete_legacy_pages.md` |
| C10 | Without JavaScript | Step 1 opens; later steps need htmx |
| C11 | Title rule from 1282 | This branch merges first; 1282 must apply the rule at step 1 |
| O1 | Recording the title rule on the 1282 branch | In this plan only, for now |
| O2 | "Respondents data source" or "People data source" | "Respondents data source", as Figma |
| O3 | Info icon texts | As written under Wording |
