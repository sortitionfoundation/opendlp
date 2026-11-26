# 1379 — Archive and unarchive a project

Status: **implemented**, in #454. The first slice of the archiving work in
sc-46: a project that is finished or abandoned can be taken out of the project
lists, and brought back. Nothing is deleted. Following review on #454,
archiving can also close the project's published registration pages, when the
organiser ticks a box for it.

## 1. Decisions

- **Who:** admins, and the project's own Project Managers — the
  `can_manage_assembly` capability, checked in the service.
- **Published registration pages:** a published page is still taking
  registrations, so archiving does not happen while one is. Either the
  organiser closes the pages from the registration pages list first, or ticks
  the box in the Archive dialog that closes them as part of archiving
  (`archive_assembly(force=True)`). Without the tick, archiving is refused, and
  the refusal names the pages. Test and closed pages stay as they are, and their
  addresses stay taken. Freeing their addresses is a later slice of sc-46.
- **Editing:** an archived project stays fully editable on every tab, behind a
  banner. Nothing is made read-only; read-only archived projects are a later
  slice.
- **Finding them again:** the Archived projects page is a plain list of the
  archived projects the viewer may see, as the story asks: sc-46 wants "a page
  which will show archived projects, so they can be recovered". It has no
  search, as no other project list has one.

## 2. What was already there

- `AssemblyStatus` has `ACTIVE` and `ARCHIVED`, with labels in
  `assembly_status_labels`. The status column is a plain string, so there is
  **no migration**.
- `Assembly.archive()` and `reactivate()` set the status and `updated_at`.
- The project lists read only active projects: `get_active_assemblies` for an
  admin, `get_assemblies_for_user` for everyone else.
- The Status tag on the project details page was already grey for an archived
  project.

## 3. How it works

### Service

- `assembly_service.archive_assembly()` goes through `Assembly.archive()`, so
  `updated_at` moves, and returns a detached copy like its neighbours. While a
  page is published it raises `CannotArchiveWithPublishedPages`, a
  `CuratedMessage` whose `page_names` the message lists ("The registration page
  'English' is published. Close it before archiving this project.").
- `archive_assembly(..., force=True)` closes each published page first, then
  archives. It closes them through
  `registration_page_service.close_registration_page()`, in the same unit of
  work, so closing keeps its own permission check and the page's activity
  records who closed it, with "Closed when the project was archived" as the
  reason. That function rather than the bulk `close_all_registration_pages()`:
  it closes exactly the pages the refusal would have named, and it takes a
  reason, where the bulk one writes its generic "Changed as part of a bulk
  status update". `force` is False by default, so a caller that does not pass
  it is refused as before.
- `unarchive_assembly()` is new, with the same permission check, and goes
  through `reactivate()`.
- Both leave a project already in the asked-for state as it is: no error, and
  `updated_at` does not move. That holds with `force` too: an archived project
  that has had a page published since keeps it published.
- `published_registration_pages(pages)` is the one place the rule lives. The
  service asks it of `uow.registration_pages.list_by_assembly_id()`, and the
  project details page asks it of the pages it has already loaded, to name
  them in the Archive dialog.

### Repositories

`get_assemblies_for_user()` takes a `status`, active by default, so every
existing caller is unchanged. A status parameter rather than a new method keeps
the member's role subquery in one place.

`user_service.get_user_archived_assemblies()` sits beside
`get_user_assemblies()` and chooses the same way: an admin
(`can_see_all_assemblies`) gets every archived project through
`get_assemblies_by_status(ARCHIVED)`; anyone else gets their own through
`get_assemblies_for_user(user_id, ARCHIVED)`. Both list newest first.

The fake repository used to differ from the SQL one: its `search_by_title`
ignored the status, and its `get_assemblies_by_status` did not sort. Both now
answer as SQL does, and the contract tests that pin this fail against the fake
as it was.

### Project details page

- **Archive project** sits beside the Status tag in the Basic details card,
  for managers only (`project_details/_archive_control.html`). It opens a
  `controlled_alert_dialog`, as the registration editor's close confirmation
  does: the project leaves the project lists, nothing is deleted, and it can be
  unarchived. "Keep it active" is the primary button and takes the focus; the
  red button posts the form. The `confirmDialog` Alpine component
  (`src/js/components/confirm-dialog.js`) moves the focus in, and back to the
  opener on cancel. It finds the opener before the dialog closes: `cancel()` is
  called from inside the dialog, and Alpine resolves `$refs` from the element a
  call came from, which `x-if` has removed by the next tick.
- While a page is published the button opens the same dialog, with a checkbox
  above the buttons that names the published pages: "Close the published
  registration page 'English'", or pages, with every name. Its hint says a
  project can't be archived while a page is published, and that closing stops
  new registrations. The red button waits for the tick (`:disabled="!ticked"`),
  and its `aria-describedby` points at that hint. The checkbox posts `force=1`
  with the form, so what is sent is what the box shows, and `confirmDialog`
  unticks it every time the dialog opens. The form holds both buttons as well
  as the checkbox, which gives the checkbox a line of its own; from the focused
  safe action, Shift+Tab passes over the waiting button to the checkbox.
- `POST /backoffice/project/<id>/archive` and `/unarchive` call the service,
  flash the outcome or the refusal, and go back to the project. The archive
  route passes `force` when the form posts `force=1`. It counts the published
  pages first, so the flash can say the project was archived and its published
  registration page closed, or pages, with `ngettext`; with none to close, it
  says only that the project was archived. A project that does not exist goes
  back to Your projects.

### The banner

`components/archived_banner.html` renders nothing for an active project. For an
archived one it says "This project is archived. It doesn't appear in project
lists.", with an **Unarchive project** button for managers.

- It is the alert component's **info** variant. Being archived is not a fault
  and asks nothing of the reader; the backoffice keeps warning for things that
  block the next step, such as "Before you can run a selection".
- Every template that renders `assembly_tabs` calls it **at the top of its
  content**, not inside `assembly_tabs`: the page header holding the tabs is
  sticky, and a banner there would stay pinned over every scroll. A new tab
  needs the call too; `PROJECT_TABS` in `tests/component/test_archive_project.py`
  lists the tabs the test walks.
- Every tab's route passes whether the viewer manages the project. Four did not
  before: the dashboard tab, the registration pages list, Registration questions
  and Link targets to questions.

### Archived projects page

`GET /backoffice/projects/archived` (`backoffice.archived_projects`), linked from
the header row of Your projects. It is a plain list, newest first: every
archived project for an admin, the ones they hold a role on for anyone else.
The cards are the dashboard's, moved into `components/project_card.html`, here
with the status tag on each, and each opens its project, where it can be
unarchived. With nothing archived, the page says so.

## 4. Not in this slice

- Read-only archived projects. Today nothing blocks work on one: tabs, edits,
  selection runs, exports, background tasks. A registration page can even be
  published again after the project is archived; archiving only checks, or
  closes, at the moment it happens.
- Freeing the addresses of an archived project's pages.
- Recording who archived a project and when. Nothing records it yet; it belongs
  with the activity log.
- Telling team members, deleting test projects, and anything about personal
  data in archived projects.

## 5. Tests

- Unit: `tests/unit/test_assembly_service.py` (`TestArchiveAssembly`,
  `TestArchiveAssemblyWithForce`, `TestUnarchiveAssembly`) and
  `tests/unit/test_user_service.py` (`TestGetUserArchivedAssemblies`).
- Contract: `tests/contract/test_assembly_repo.py`, for the status parameter,
  and the fake's status filter and ordering.
- Component: `tests/component/test_archive_project.py` — who gets which button,
  the checkbox that names the published pages and the button that waits for
  it, both routes with their refusals and `force`, the banner on every tab for
  a manager and a reader, and the Archived projects page with its empty state.
- JS: `src/js/components/confirm-dialog.test.js`, including the box unticked on
  every opening and the opener found before the dialog goes.
- BDD: "A project manager archives a project and unarchives it", and "A project
  manager archives a project and closes its published registration page",
  which also cancels the dialog with Escape and expects the focus back on
  Archive project, in `features/backoffice-assembly.feature`.
