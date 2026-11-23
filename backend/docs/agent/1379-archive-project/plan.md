# 1379 — Archive and unarchive a project

Status: **implemented**, on `1379-archive-project`. The first slice of the
archiving work in sc-46: a project that is finished or abandoned can be taken
out of the project lists, and brought back. Nothing is deleted.

## 1. Decisions

- **Who:** admins, and the project's own Project Managers — the
  `can_manage_assembly` capability, checked in the service.
- **Published registration pages:** archiving is refused while any of the
  project's registration pages is published, because a published page is still
  taking registrations. The refusal names the pages, and the organiser closes
  them from the registration pages list. Test and closed pages stay as they
  are, and their addresses stay taken. Closing pages as part of archiving, and
  freeing their addresses, are later slices of sc-46.
- **Editing:** an archived project stays fully editable on every tab, behind a
  banner. Nothing is made read-only; read-only archived projects are a later
  slice.

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
- `unarchive_assembly()` is new, with the same permission check, and goes
  through `reactivate()`.
- Both leave a project already in the asked-for state as it is: no error, and
  `updated_at` does not move.
- `published_registration_pages(pages)` is the one place the rule lives. The
  service asks it of `uow.registration_pages.list_by_assembly_id()`, and the
  project details page asks it of the pages it has already loaded, to disable
  the button.

### Repositories

`get_assemblies_for_user()` and `search_by_title()` take a `status`, active by
default, so every existing caller is unchanged. `get_assemblies_for_user()`
also takes a `title_search`, a case-insensitive "title contains". A status
parameter rather than new methods keeps the member's role subquery in one
place.

`user_service.get_user_archived_assemblies()` sits beside
`get_user_assemblies()` and chooses the same way: an admin
(`can_see_all_assemblies`) gets `search_by_title(q, ARCHIVED)`, where an empty
search matches every title; anyone else gets their own through
`get_assemblies_for_user(user_id, ARCHIVED, q)`.

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
  opener on cancel.
- While a page is published the button is disabled, described by the reason
  and a link to the registration pages list.
- `POST /backoffice/project/<id>/archive` and `/unarchive` call the service,
  flash the outcome or the refusal, and go back to the project. A project that
  does not exist goes back to Your projects.

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
the header row of Your projects. The cards are the dashboard's, moved into
`components/project_card.html`, here with the status tag on each. The search is
a plain GET form (`q`), so a search is an ordinary link. The empty state says
whether nothing is archived or nothing matched.

## 4. Not in this slice

- Read-only archived projects. Today nothing blocks work on one: tabs, edits,
  selection runs, exports, background tasks. A registration page can even be
  published again after the project is archived; archiving only checks at the
  moment it happens.
- Closing published pages as part of archiving, and freeing the addresses of
  an archived project's pages.
- Recording who archived a project and when. Nothing records it yet; it belongs
  with the activity log.
- Telling team members, deleting test projects, and anything about personal
  data in archived projects.

## 5. Tests

- Unit: `tests/unit/test_assembly_service.py` (`TestArchiveAssembly`,
  `TestUnarchiveAssembly`) and `tests/unit/test_user_service.py`
  (`TestGetUserArchivedAssemblies`).
- Contract: `tests/contract/test_assembly_repo.py`, for the status and title
  parameters and the fake's ordering.
- Component: `tests/component/test_archive_project.py` — who gets which button,
  the disabled state, both routes with their refusals, the banner on every tab
  for a manager and a reader, and the Archived projects page and its search.
- JS: `src/js/components/confirm-dialog.test.js`.
- BDD: "A project manager archives a project and unarchives it" in
  `features/backoffice-assembly.feature`.
