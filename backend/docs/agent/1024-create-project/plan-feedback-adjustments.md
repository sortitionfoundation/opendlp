# 1024 — Adjustments after team feedback and user testing

Shortcut sc-1024. The third plan for this branch. It changes things the first
two decided; read them first:

- [plan-create-project.md](plan-create-project.md) — the create dialog;
- [plan-project-details-tab.md](plan-project-details-tab.md) — the details page.

Where this plan and those two disagree, this one wins. The decisions it
reverses are named under [What this reverses](#what-this-reverses).

**Status: in progress.** Steps are ticked under [Order of work](#order-of-work)
as they land.

## The brief

1. The create dialog's stepper is clickable, and not greyed out.
2. A project held in OpenDLP:
   - the Respondents and Select and Replace tabs are always enabled;
   - the Respondents tab with no respondents shows instructions, not an empty
     table;
   - the Targets tab links to the data source dialog for an import;
   - the selection settings are a dialog behind a cog, not a section on the
     Select tab; while they are unconfirmed the tab's actions are disabled
     under a banner that opens the dialog;
   - Project details gets a Selection settings card whose cog opens the same
     dialog.
3. A project held in Google Sheets:
   - no Registration tab;
   - links that say "data configuration" open the data source dialog itself.

## 1. A clickable stepper

Each step in the create dialog is a link. Clicking one posts the dialog's form
to `new_project_step` with `go=<step number>`, exactly as Back posts
`go=back` — so what has been typed rides along, as it does for Back and Next.

- **Moving forward validates the step you leave.** A click on step 2 or 3 with
  a bad title answers 422 with the dialog at step 1 and the reason under the
  field, as Next does. Moving backward validates nothing.
- **Not greyed.** The stepper loses `disabled=true`. Steps already passed show
  their tick, the current one is `aria-current="step"`, later ones their
  number — all in the stepper's ordinary colours.
- **Once the project exists** (a CSV was uploaded at step 3) steps 1 and 2
  have nothing to go back to: the dialog is then the data source form of a
  real project. They stay ticked and are not links (the per-item
  `disabled`). The title, question and panel size are a click away on the
  details page. The greyed look of a disabled step is dropped for *done*
  steps, so they read as finished rather than unavailable.
- **Back and Next stay.** The stepper is a second way to move, not the only
  one.

**Focus.** The dialog host keeps focus on a control it can find again after a
redraw, by id. The stepper macro gives every step an id, so a clicked step
would keep focus — including after a refusal, leaving a keyboard user on
"step 3" while the dialog shows step 1 with an error. So the macro gains
`ids=false`: no `id` or `data-focus-id` on the steps, and focus goes where it
goes for Back and Next — the step's first field, or the refused one. The
steps are now the first focusable things in the dialog body, so each step's
first field carries `data-dialog-initial-focus` unconditionally (step 1's
title and the Google Sheets URL do not today).

## 2. Projects held in OpenDLP

### Tabs

`get_tab_enabled_states` answers `(True, True, True)` for a project held in
OpenDLP, whatever data it has. The Google Sheets rule is unchanged: all three
wait for the sheet's settings.

### Respondents tab with no respondents

When the project has no respondents at all (not merely none matching a
filter), the heading, filter, export and table give way to:

> **No respondents yet**
> Respondents arrive in one of two ways:
> - **Upload a CSV file** of people who have already registered elsewhere.
>   *[Upload respondents (opens in a new tab)]*
> - **Create a registration page** for people to fill in. *[Go to the
>   Registration tab]*

The upload link is `…/project/<id>?data_source=1` with `target="_blank"`, as
asked. Someone who cannot manage the project sees only the first line.

A caution worth recording: after the upload in the new tab, the first tab
still says "No respondents yet" until it is reloaded. If testing shows people
tripping on that, the cheap fix is to drop `target="_blank"`.

### Targets tab

With no targets, a manager sees beside "No targets defined yet." a link
"Import targets from a CSV file (opens in a new tab)" to the same dialog. A
new tab here as well: the Targets page may hold unsaved edits, and the two
links should behave alike.

### Select and Replace tab

**The page always shows the two steps and the history.** The "set up your
data first" branch for an empty OpenDLP project goes.

**One banner says what selection is waiting for.** A warning above the steps,
shown while any of these is true, listing only the ones that are:

| Missing | The banner says | And offers |
| --- | --- | --- |
| targets | "Add targets." | link to the Targets tab |
| respondents | "Add respondents." | link to the Respondents tab |
| confirmed settings | "Review and save the selection settings." | a button that opens the dialog |

While the banner is up, Run Selection, Run Test Selection, Reset and Select
replacements are disabled (`aria-disabled`, as the steps do today for missing
settings). The routes behind them keep their own `settings_confirmed` check.

**The settings are a dialog.** A cog (`aria-label` "Selection settings",
`aria-haspopup="dialog"`, managers only) sits above the steps, right-aligned.
It and the banner's button `hx-get` the dialog into the page's dialog host.

- `GET /backoffice/project/<id>/data/csv/settings` — the dialog (new; the URL
  is the existing save route's). Without htmx it redirects to the Select tab
  with `?settings=1`, which renders the page with the dialog open.
- `POST` (existing `save_db_settings`) — over htmx: 422 with the dialog and
  the errors, or `HX-Redirect` back to where it was opened with the success
  flash. Without htmx: as today, a redirect, or the Select page re-rendered
  with the dialog open.
- **Where it returns** is a token, not a URL: the opener sends `from=details`
  or nothing, the dialog carries it as a hidden input, and the route maps it
  to the details page (`#selection-settings`) or the Select tab. Close and
  Cancel just close the dialog — you are already on the page you came from.

The form inside is today's (`DbSelectionSettingsForm`, same fields, same
validation). `components/selection_settings.html` (the `<details>`) is
replaced by `components/selection_settings_dialog.html`.

**Before there are respondents** the dialog still opens and still saves: the
form already skips its column-name check when there are no columns to check
against. The banner will go on naming respondents as missing, so nobody can
run a selection on settings confirmed blind.

### Project details: a Selection settings card

For a project held in OpenDLP, between Data source and Registration link:

```
Selection settings   [To confirm]                                  ⚙
```

A heading, the same "To confirm" / "Confirmed" tag the old section showed, and
for managers the cog, opening the same dialog with `from=details`. Saving
lands back on the details page. Nothing else is in the card.

## 3. Projects held in Google Sheets

- **No Registration tab.** `assembly_tabs` takes `data_source` and leaves the
  tab out for `"gsheet"`. The nine templates that call it pass it on; the
  three whose routes do not yet put `data_source` in the context get it.
- **No Registration link card** on the details page either — a card whose
  only link goes to a tab that is not there.
- The registration routes are not blocked: reachable by URL, as the Dashboard
  tab is behind its flag. A Google Sheets project cannot use what it would
  collect, but hiding is what was asked for and refusing is a bigger change.
- **"View Data Configuration"** on the Targets and Respondents tabs and the
  respondent field schema page goes to `?data_source=1#data-source`: the
  dialog opens for a manager, and anyone else lands on the card.

## What this reverses

| Earlier decision | Now |
| --- | --- |
| C7: the stepper is not navigation | Clickable until the project exists |
| D-plan, *Tabs*: Respondents and Select stay disabled until there is data | Always enabled for a project held in OpenDLP |
| O2: selection settings open above the steps, then collapsed | A dialog behind a cog; a banner while unconfirmed |
| C5: "its own dialog is a possibility later" | Done here |

## Wording

| Where | Text |
| --- | --- |
| Cog, card and dialog title | "Selection settings" |
| Banner heading | "Before you can run a selection:" |
| Banner items | "Add targets.", "Add respondents.", "Review and save the selection settings." |
| Banner links | "Go to Targets", "Go to Respondents", "Review selection settings" |
| Respondents empty state | as quoted above |
| Targets link | "Import targets from a CSV file" |
| New-tab links | "(opens in a new tab)" in the link text, visible to everyone |

## Tests

- **Unit:** `get_tab_enabled_states` for OpenDLP with and without data; the
  stepper macro with `ids=false` and with a done-and-disabled step.
- **Component:** `new_project_step` with `go=1|2|3` (forward validates,
  backward does not, nonsense is ignored); the dialog's steps are links before
  the project exists and steps 1–2 are not after; the settings dialog GET and
  POST, with and without htmx, both `from` values, 422, a non-manager; the
  Select page's banner for each missing thing and its disabled buttons; the
  Respondents empty state for a manager and a viewer; the Targets import
  link; no Registration tab or card for a Google Sheets project; the
  "View Data Configuration" links.
- **BDD:** `create-project.feature` gains a stepper scenario; the selection
  settings scenarios open the dialog; scenarios that relied on a disabled
  Respondents or Select tab are rewritten around the new empty states.
- **Docs:** `component_accessibility.md` ("Wizard in a dialog" row), the
  showcase wizard entry, and the two earlier plans get a pointer here.

## Order of work

1. ✅ Clickable stepper.
2. ✅ Tabs always enabled for OpenDLP; Respondents empty state; Targets link.
3. ✅ Selection settings dialog, the Select tab's banner and cog.
4. ✅ Selection settings card on Project details.
5. ✅ Google Sheets: no Registration tab or card; direct links to the dialog.
6. BDD sweep, catalogues, docs.

## Decisions

| # | Question | Decision |
| --- | --- | --- |
| F1 | Where the settings dialog leaves you | Where it was opened |
| F2 | Select tab with data missing | Steps shown, actions disabled, one banner naming what is missing |
| F3 | Stepper once the project exists | Steps 1 and 2 ticked, not links |
| F4 | Process | Plan and implement, one commit per step |

Defaults taken without asking, cheap to change: the upload links open a new
tab on both the Respondents and Targets tabs; the Registration link card goes
with the tab for Google Sheets projects; the registration routes stay
reachable by URL; the settings dialog may be saved before respondents exist.
