# 1341: Retire the legacy (GOV.UK) signed-in pages

Status: **agreed, in progress.** Doctor Chewie's answers to Q1–Q14 are folded
in as decisions (section 3 lists them in one place). Progress is ticked off in
section 8. **O1** in section 5.2 was not answered, so the conservative reading
stands: the other nine `admin-users.feature` scenarios are left alone.

This supersedes `docs/agent/future_work/delete_legacy_pages.md`, which is
deleted as part of the work.

## 1. Scope

In scope:

- The legacy signed-in pages under `/assemblies/...` and `/dashboard`, their
  templates, their tests, and the flags that steered between old and new.
- Converting the high-level BDD features that currently drive those pages.
- Splitting the backoffice selection blueprints (section 7) — as a follow-up PR.

Out of scope:

- `templates/errors/*.html` — still GOV.UK, a later pass.
- Public registration pages (`templates/register/`, `base_public.html`) — GOV.UK
  for the long term.

The Site Admin pages are no longer a consideration: the backoffice restyle is
merged to `main`, and this branch starts from that commit.

Consequence: once the legacy templates go, **`templates/base.html` is used only
by the five error pages.** It, `static/css/application.css`, the vendored
`govuk-frontend.js` and the GOV.UK Sass all stay for now, because the error
pages (and, for the Sass, the public registration pages) still need them. This
round removes pages, not the GOV.UK toolchain.

## 2. What is there

### 2.1 Blueprints and routes

| Blueprint | File (lines) | Legacy routes | Templates |
| --- | --- | --- | --- |
| `main` | `blueprints/main.py` (488) | 9 of 10 | `templates/main/` (8 files) |
| `gsheets_legacy` | `gsheets_legacy.py` (1457) | 21 | `templates/gsheets/` (8 files) |
| `db_selection_legacy` | `db_selection_legacy.py` (463) | 12 | `templates/db_selection/` (4 files) |
| `targets_legacy` | `targets_legacy.py` (796) | 11 | `templates/targets/` (5 files) |
| `respondents_legacy` | `respondents_legacy.py` (202) | 3 | `templates/respondents/` (1 file) |

Roughly 3,350 lines of Python and 2,900 lines of template, 56 routes.

`main` is not called legacy, but nine of its ten routes are legacy GOV.UK pages
and go (decision Q1):

- `/dashboard` (`main.dashboard`) — already 404s unless one of two flags is on
- `/assemblies/new`, `/assemblies/<id>`, `/assemblies/<id>/edit`,
  `/assemblies/<id>/data`, `/assemblies/<id>/members` (GET, POST),
  `/assemblies/<id>/members/<user>/remove`, `/assemblies/<id>/search-users`

The tenth, `/` (`main.index`), is the live public home page and stays, so the
widely used `main.index` endpoint name does not change. `main` also gains the
two redirects of decision Q3.

Only `/dashboard` is actually *disabled* today. Every `/assemblies/...` route
is still served to anyone who types the URL — hidden, not off.

### 2.2 Live code that still points at legacy endpoints

Searched `src/opendlp` and every template outside the five legacy template
folders for the legacy endpoint names (re-run after the admin merge).

| Where | What | Fix |
| --- | --- | --- |
| `blueprints/admin.py` — 9 places | `redirect(url_for("main.dashboard"))` on error paths | → `backoffice.dashboard` |
| `templates/backoffice/components/footer.html:23-24` | "Old Dashboard" link, behind `FF_DASHBOARD_SWITCH_LINKS` | delete the block |
| `templates/base.html:183` | "New Dashboard" footer link, behind the same flag | delete the block |
| `feature_flags.py` | `OLD_DASHBOARD_ENDPOINT = "main.dashboard"` | goes with the flag |
| `templates/backoffice/service_docs/_respondents.html:327` | prose naming `respondents_legacy.reset_respondent_status` | correct to the backoffice route |

The `admin.py` ones are a small live bug on any install with both dashboard
flags off: an admin error path redirects to a 404.

Everything else is legacy calling legacy, and dies with it. No service, email
or URL generator builds a legacy link.

### 2.3 Feature flags

| Flag | Does | Read by |
| --- | --- | --- |
| `FF_OLD_DEFAULT_DASHBOARD` | Legacy dashboard is the post-login landing page | `feature_flags.default_dashboard_endpoint()`, `old_dashboard_route_enabled()` |
| `FF_DASHBOARD_SWITCH_LINKS` | Cross-links between the two dashboards | `base.html`, backoffice `footer.html`, `old_dashboard_route_enabled()` |
| `FF_CSV_DB_ASSEMBLY_LINKS` | CSV/DB links on the legacy project page | `templates/main/view_assembly_base.html:32` only; not in `env.example` |

Going with them:

- `OLD_DASHBOARD_ENDPOINT`, `NEW_DASHBOARD_ENDPOINT`,
  `default_dashboard_endpoint()`, `old_dashboard_route_enabled()` in
  `feature_flags.py`. `default_dashboard_endpoint()` has 13 callers
  (12 in `auth.py`, 1 in `main.index`) plus `tests/component/test_home_page.py`;
  each becomes the literal `"backoffice.dashboard"`.
- The two entries and the "when both are false" note in `env.example`.
- The two entries in `TEST_FEATURE_FLAGS` in `tests/conftest.py`. The dict and
  its scrub-then-set mechanism stay, empty, with the comment reworded
  (decision Q10).
- `tests/unit/test_dashboard_feature_flags.py` (whole file).
- `Urls.any_dashboard` in `tests/bdd/config.py`.

Staying: `FF_REGISTRATION_PAGE`, `FF_SHOWCASE`, `FF_RESULTS_DASHBOARD`,
`FF_OPEN_SIGNUP`. No flag exists whose job is to *enable* a backoffice page,
and no `config.py` setting is legacy-only.

### 2.4 Code only the legacy pages use

Re-verified for this draft with a search that includes each name's own module
(the first draft's search did not, and got one wrong — see below).

**To delete (decision Q8), each with its tests, in its own commit:**

| Name | Lives in | Why it is safe to delete |
| --- | --- | --- |
| `CreateAssemblyForm` | `entrypoints/forms.py` | only `main` used it; the create dialog has its own handling. Its parent `AssemblyForm` stays (`EditAssemblyForm` is live in `project_details.py`) |
| `AddTargetCategoryForm`, `EditTargetCategoryForm` | `entrypoints/forms.py` | only `targets_legacy` |
| `UploadRespondentsCsvForm` | `entrypoints/forms.py` | only `respondents_legacy` |
| `remove_assembly_gsheet` | `service_layer/assembly_service.py` | no longer required (Doctor Chewie) |
| `update_target_category`, `delete_target_category`, `delete_target_value` | `service_layer/target_service.py` | superseded — see "Targets" below |
| `count_non_pool_respondents` | `service_layer/respondent_service.py` | superseded — see "Non-pool warning" below |
| `count_non_pool` | abstract repo, SQL repo, `tests/fakes.py`, contract tests | its only caller is the function above |
| `_parse_comma_list` | `db_selection_legacy.py` | goes with the module; its tests in `tests/unit/test_db_selection.py` go too |

**Not orphaned after all:** `get_respondent_counts_for_category`. The first
draft listed it; it is called by `build_respondent_counts` in the same module,
which is what the backoffice targets page uses. It stays.

#### Targets: how the backoffice deletes a category or a value

There is no bug and no duplicate in live use — there are two generations of the
same capability, and only the newer one is reachable from the backoffice.

- **Legacy:** one route per action, each calling a single-purpose service
  function (`update_target_category`, `delete_target_category`,
  `delete_target_value`).
- **Backoffice:** the targets page is one form. `POST …/targets/save-all`
  parses it (`entrypoints/save_all_parser.py`) into `TargetCategoryEdit` /
  `TargetValueEdit` objects and hands them to `save_all_targets`. Each edit
  carries an explicit `deleted` flag, set from a hidden `deleted` field the
  page writes when the user removes a row.

So it is a bulk save, but **not** one that drops whatever is missing. The
docstring is explicit and the code agrees: "Deletion is explicit: a category or
value goes only when its edit says so. Absence from the payload still means
'leave alone', so a partial submission cannot silently destroy anything."

The link-breaking rule (deleting a category that registration fields feed needs
confirmation) exists in both generations: `delete_target_category` has its own
copy, `save_all_targets` uses `_guard_linked_categories`, which also collects
every affected category into one confirmation. Deleting the legacy functions
leaves exactly one implementation of that rule.

`create_target_category`, `add_target_value` and `update_target_value` are
*not* orphans — `targets.py` and `target_suggestions.py` call them.

#### Non-pool warning: what the backoffice does instead

The legacy database selection page counted respondents in any status other than
POOL (`count_non_pool_respondents`), showed "N respondents already have a
selection status…", and refused to run a selection while that count was above
zero.

The backoffice does not warn in those words, and it deliberately counts
something different: `count_held_respondents` — people who are **selected or
confirmed**. `render_selection_page` passes it to
`backoffice/components/selection_steps.html`, which uses it to

- show the places held against the number to select in the status panel;
- offer only the actions that apply — once anyone holds a place, the initial
  selection's buttons give way to "reset to pool" and replacements;
- enable replacements only while `0 < held < number_to_select`.

The switch from "non-pool" to "held" was your decision in September (my notes
from the guard-initial-selection planning): test submissions and people who
withdrew before selection are non-pool but must not block a selection. So the
old function is not merely unused, it encodes the rule that was rejected.

One thing that is still true and worth restating, though it is not this
branch's job: that gate lives **only in the template**. `start_db_select_task`
does not check the held count, so a hand-built POST can start an initial
selection over held places. That is the planned service-layer guard, still
outstanding as far as I can see; removing the legacy route does not make it
better or worse (the legacy route's own check was also in the entrypoint).

JavaScript: `src/js/components/team-selector.js` is used only by the legacy
gsheet config templates, and is the only component
`src/js/alpine-components.js` registers. Decision Q9 below.

## 3. Decisions

| # | Question | Decision |
| --- | --- | --- |
| Q1 | Is `main` in scope? | Yes: delete its nine legacy routes, keep `main.index` |
| Q2 | Admin pages | Moot — restyle merged to `main` |
| Q3 | Old URLs | `/dashboard` → `/backoffice/dashboard` and `/assemblies/<id>` → `/backoffice/project/<id>`, both **302**; everything deeper 404s |
| Q4 | How to decide which tests to port | Coverage diff before/after |
| Q5 | Legacy e2e smokes | One happy-path e2e smoke per backoffice flow that would otherwise have none |
| Q6 | Database implementation of `selection.feature` | Yes, in this branch |
| Q7 | The four CRUD features | Convert all four, feature files unchanged; reword "assembly" → "project" as a follow-up. Scroll-preservation: repoint if the backoffice pagination preserves scroll, otherwise come back |
| Q8 | Orphaned services and forms | Delete, per section 2.4 |
| Q9 | Emptied `alpine-components.js` bundle | Remove component, bundle, esbuild entry and script tag; leave the rest of `base.html` and the GOV.UK Sass alone |
| Q10 | `TEST_FEATURE_FLAGS` | Keep the empty mechanism |
| Q11 | Deployment flags | Safe to remove; infra locations listed in section 6 |
| Q12 | Blueprint shape | Three blueprints: `selection`, `gsheet_selection`, `db_selection`; `gsheet/check` moves to `data_source`. Dropping the other `backoffice` qualifiers → `future_work/` |
| Q13 | Same PR? | Separate PR after the deletion merges |
| Q14 | Other blueprint moves | Leave for now |

### The Q3 redirects

Two routes in `main.py`, both `@login_required` so a signed-out visitor goes
through sign-in and comes back:

- `GET /dashboard` → 302 `backoffice.dashboard`
- `GET /assemblies/<uuid:assembly_id>` → 302 `backoffice.view_assembly`
  (whatever the project page endpoint is called). No permission check here —
  the destination already does it and answers a stranger the way it always
  does.

`/assemblies/new`, `/assemblies/<id>/edit` and everything deeper are not
routed, so they 404. Because the redirect route is typed `<uuid:…>`,
`/assemblies/new` does not match it.

## 4. Tests

### 4.1 Wholly legacy — delete, after the coverage diff

| File | Tests | Legacy target | Backoffice cover I expect to exist in |
| --- | --- | --- | --- |
| `component/test_assembly_crud.py` | 28 | `main` CRUD | `test_create_project_dialog.py`, `test_project_details_page.py` |
| `e2e/test_assembly_crud.py` | 4 | `main` CRUD | as above |
| `component/test_assembly_user_management.py` | 14 | `main` members | `test_project_details_page.py` (team card) |
| `e2e/test_assembly_user_management.py` | 8 | `main` members + search | the `db_semantics` user-search tests are the ones to watch |
| `component/test_assembly_gsheet_crud.py` | 25 | `gsheets_legacy` config | `test_project_details_page.py`, `test_gsheet_access_check.py` |
| `e2e/test_assembly_gsheet_crud.py` | 6 | config + SelectionSettings JSON round trip | the round trip is the one to watch |
| `component/test_sortition_routes.py` | 54 | `gsheets_legacy` select/replace/tabs | `e2e/test_backoffice_gsheet_selection.py`, `e2e/test_gsheets_routes.py` |
| `e2e/test_sortition_routes.py` | 19 | same, plus Celery dispatch/revoke | as above |
| `component/test_db_selection_routes.py` | 49 | `db_selection_legacy` | `component/test_db_selection_backoffice.py` |
| `e2e/test_db_selection_routes.py` | 9 | `db_selection_legacy` | `e2e/test_db_selection_backoffice.py` |
| `e2e/test_targets_legacy_pages.py` | 38 | `targets_legacy` | `component/test_targets_pages.py` |
| `unit/test_targets_routes.py` | 10 | `targets_legacy` registration/auth | same |
| `e2e/test_respondents_pages.py` | 20 | `respondents_legacy` | backoffice respondents tests |
| `unit/test_respondents_routes.py` | 4 | `respondents_legacy` | same |
| `unit/test_dashboard_feature_flags.py` | — | the two flags | n/a |

About 290 tests. The right-hand column is my reading of file names and headers,
not proof, which is what the coverage diff is for.

**The coverage diff (decision Q4).** Before touching anything, run
`just test-nobdd-cov` and keep the per-file line coverage for everything except
the five legacy modules. After the deletions, run it again and diff. Any line
in `service_layer/`, `domain/`, `adapters/` or a surviving blueprint that was
covered before and is not now is one of two things:

- a behaviour whose only test was a legacy one → port that test to the
  backoffice route;
- code only legacy used → it should already be in section 2.4; if it is not, I
  stop and ask before deleting it.

Known limit, accepted: a line can stay covered while the *assertion* about it
is lost. The two rows marked "to watch" I will read by hand regardless.

### 4.2 Mixed — edit

| File | Change |
| --- | --- |
| `component/test_organiser_access.py` | drop the 5 legacy-dashboard / legacy-create-form tests; the backoffice twins are already in the file |
| `component/test_auth_flow.py` | 6 tests fetch `/dashboard` as "a page behind login"; point at `/backoffice/dashboard` |
| `unit/test_flask_app.py` | uses `/dashboard` as an arbitrary path in a request context — repoint |
| `component/test_legacy_header.py` | stays — now only about the error pages, still valid |
| `unit/test_db_selection.py` | drop the `_parse_comma_list` tests; keep the service and form tests |
| `integration/test_respondent_service.py`, `contract/test_respondent_repo.py`, `tests/fakes.py` | drop `count_non_pool` and its tests (section 2.4) |
| `component/test_home_page.py` | `default_dashboard_endpoint()` → literal |
| `component/test_2fa_flow.py`, `e2e/test_2fa_flow.py`, `e2e/test_auth_flow.py`, `e2e/test_oauth_flow.py`, `component/test_admin_user_management.py`, `e2e/test_admin_user_management.py`, `component/test_profile_management.py` | a handful of `/dashboard` redirect-target assertions each — repoint |
| `tests/conftest.py` | empty `TEST_FEATURE_FLAGS`, reword its comment |
| `tests/manual/scroll-preservation/scroll-preservation-manual-test-plan.md` | names the legacy data page in 8 places — repoint with the BDD scenario |

### 4.3 New tests

- **Retirement test** (component): parametrised over one representative URL
  from each of the five legacy blueprints, asserting 404 for a signed-in admin.
  Stops a blueprint being re-registered by accident.
- **Redirects** (decision Q3): component tests through the Flask client for
  both — signed in gets the 302 and its target; signed out is sent to sign-in;
  `/assemblies/new` and `/assemblies/<id>/edit` 404. An e2e test follows
  `/assemblies/<id>` through to a rendered project page on PostgreSQL. The BDD
  suite does not depend on either redirect (5.4 points it straight at the
  backoffice), so the redirects have their own tests and are not load-bearing
  for anything else.
- **E2E smokes** (decision Q5): after the coverage diff, for each backoffice
  flow whose legacy twin had an e2e smoke and which has none of its own — I
  expect create project, edit project details, add/remove team member, save
  Google Sheet settings — one happy-path test on real PostgreSQL. The exact
  list comes out of step 4 of the order of work; I will not add smokes that
  already exist under another name.

## 5. BDD features

### 5.1 `selection.feature` — convert, and add the database implementation

Five scenarios, deliberately implementation-free; the step file's docstring
says the plan was always several step files running the same feature.

**Google Sheets** — `tests/bdd/test_selection_manual_gsheet.py`, feature file
untouched, step bodies rewritten:

| Step | Legacy | Backoffice |
| --- | --- | --- |
| I open the Assembly | data page → "Configure Google Sheets" link | project details page → cog → data source settings dialog |
| I can specify the source / categories and targets / options | fields on the gsheet config page | same fields in the dialog |
| I can save the options | submit → back on data page | save → back on the details page, sheet shown on the card |
| I check the data | `/gsheet_select` → "Check Spreadsheet" | Selection tab → check button → progress modal |
| I start the selection | "Run Selection" | same, in the modal |
| I am told the number of categories… | "Full Run Report" text on the page | same text in the progress modal |
| I initialise the replacements process | "Replacements" → `/gsheet_replace/<run>` | Selection tab → replacement modal |
| I am asked for the number to select / I start the replacements | form on the page | form in the modal |

`replacement-selection.feature` and `project-details.feature` already drive
these dialogs, so the locators and waits exist to borrow.

**Database** (decision Q6) — new `tests/bdd/test_selection_db.py`, same feature
file, for a project whose respondents and targets are held in OpenDLP:

| Step | Database implementation |
| --- | --- |
| the assembly is set up / people are registered | project with respondents uploaded from a CSV fixture |
| I open the Assembly … I can save the options | data source settings: targets uploaded; selection settings dialog (id column, address columns) saved |
| the selection options are set | fixture: respondents, targets and confirmed selection settings |
| I check the data | Selection tab → check → progress modal |
| I start the selection | Selection tab → run → progress modal |
| I am told the number of categories… / selection has completed | same report text |
| I initialise the replacements process | needs held places first: fixture runs or seeds an initial selection with some withdrawn, then opens the replacement dialog |
| I am asked for the number to select / I start the replacements | the database replacement dialog |

Two things to settle when I get there, and I will come back if either does not
fit rather than bend the feature:

- pytest-bdd binds a feature's steps per test module, so two modules running
  one feature is fine, but the step *text* is shared — every step must have a
  sensible database meaning. "I am asked for the number to select" is the one
  I am least sure of: the database replacement dialog works from places to
  fill, and may present that differently from the gsheet form.
- The exact report line ("Found 4 targets with a total of 20 values") depends
  on the fixture data; the database fixture needs the same shape or its own
  step body.

### 5.2 `admin-users.feature`

"Add user to assembly" and "Remove user from assembly" stay, converted from the
legacy members page to the backoffice Team card and its add/remove dialogs.
`project-details.feature` has the dialog mechanics; these two scenarios add the
*other user's view* (cannot see → can see → cannot see), which is why they are
worth keeping.

- "the non-admin user cannot see the assembly" → backoffice dashboard
- "the admin adds them / removes them" → Team card dialogs
- "the non-admin user can see the assembly" → backoffice project page

Going with the conversion: the legacy mechanics those steps relied on
(`#user_search`, `.govuk-notification-banner`, the JS `confirm()` handler).

**O1 — still open.** Your note says "Add and remove user stay, the rest can
go." I have read "the rest" as the legacy mechanics above, and I am **leaving
the other nine scenarios in the file alone**: invite, lock out, let back in,
change your mind, rename, change role, clear search, export, back out of
export. They now run against the restyled Site Admin, not a legacy page, so
nothing in this branch requires touching them. If you meant those scenarios
should be deleted, say so — I did not want to remove nine freshly written
scenarios on a guess.

### 5.3 The four assembly CRUD features — convert

`create-assembly.feature`, `update-assembly.feature`, `view-assembly.feature`,
`view-assembly-list.feature` — six scenarios, all in
`tests/bdd/test_assembly_crud.py`. Feature files unchanged; about 15 step
bodies rewritten.

| Scenario | Backoffice implementation |
| --- | --- |
| Create Assembly | create dialog, title only, decide about data later |
| Edit Assembly | inline edit of the framing question on the details page |
| View Assembly | details page shows title and question |
| List page with no assemblies | backoffice dashboard empty state |
| List page with assemblies | backoffice dashboard cards |

Steps whose body changes meaning, not just locator:

- "the user should see that they created it" asserts "By Test Admin at" — I
  need to check the backoffice details page shows the creator. If it does not,
  that is a stop-and-ask.
- "the user sees the message "No assemblies"" — backoffice wording differs;
  only the step body changes.
- "the user finishes editing the assembly" was a submit button; inline edit
  saves on Enter/blur.

**Follow-up, not this branch:** rewording "assembly" → "project" across the
feature files and shared steps, to match the UI. Written up as
`docs/agent/future_work/bdd_assembly_to_project_wording.md` as part of this
work.

`scroll-preservation.feature` (skipped in CI): one scenario uses the legacy
data page as "a page with paginated content". Repoint to the backoffice
Selection tab's history pagination if it uses `$preserveScroll` links; if not,
come back to you.

### 5.4 BDD plumbing

- `Urls.dashboard`, `Urls.view_assembly_list`, `Urls.create_assembly`,
  `Urls.assembly_urls` / `for_assembly()` in `tests/bdd/config.py` — removed;
  callers use the existing `backoffice_*` helpers.
- `Urls.any_dashboard` regex → plain `Urls.backoffice_dashboard`
  (about 14 call sites).
- `admin_logged_in_page` / `normal_logged_in_page` in `tests/bdd/conftest.py`
  probe `/dashboard` to see whether a session exists → probe
  `/backoffice/dashboard` directly, not via the new redirect.
- "the user is signed in" in `shared/ui_shared.py` → backoffice dashboard.
- `ui_shared.py:181` heading regex `^Your (projects|Assemblies)$` → `Your projects`.

## 6. Leftovers

### JavaScript (decision Q9)

- Delete `src/js/components/team-selector.js` and its test.
- Delete `src/js/alpine-components.js`, its entry in `esbuild.config.mjs`
  (`"js/alpine-components"`), the built `static/js/alpine-components.js` and
  map if tracked, and its `<script>` tag in `templates/base.html`. Checked:
  `base.html` is the only template that loads it. The backoffice bundle of the
  same file name under `backoffice/js/` is a different file and is untouched.
- Leave the Alpine, htmx and utilities script tags in `base.html`, and all of
  `src/scss/`. With `base.html` down to the error pages most of that is now
  dead weight, but pruning it is the "later pass" on the error templates.

### Deployment (decision Q11)

Where `~/sftop/opendlp-infra/ansible-files/` sets the retired flags, to be
tidied in that repo whenever convenient after this ships (leaving them is
harmless, and the deploy is yours):

| Template | Flags to remove |
| --- | --- |
| `roles/opendlp-docker/templates/dot-env.j2` | `FF_OLD_DEFAULT_DASHBOARD=on` (line 151), `FF_DASHBOARD_SWITCH_LINKS=on` (159) and the "when both…" note (161), `FF_CSV_DB_ASSEMBLY_LINKS=on` (139), `FF_BACKOFFICE_LINK=on` (134) |
| `roles/opendlp-preview/templates/dot-env.j2` | `FF_OLD_DEFAULT_DASHBOARD=off` (130), `FF_DASHBOARD_SWITCH_LINKS=on` (127), `FF_CSV_DB_ASSEMBLY_LINKS=on` (133), `FF_BACKOFFICE_LINK=off` (126) |
| `roles/opendlp-git-docker/templates/dot-env-prod` | `FF_CSV_DB_ASSEMBLY_LINKS=on` (133), `FF_BACKOFFICE_LINK=on` (128) |

`FF_BACKOFFICE_LINK` is a fourth: nothing in the backend reads it any more.

Noted, not queried: the `opendlp-docker` template has
`FF_OLD_DEFAULT_DASHBOARD=on`, so an install built from it lands on the legacy
dashboard after login today and on the backoffice dashboard after this release.

No migration, no schema change, no new dependency. Zero-downtime safe.

### Translations

A good many msgids fall out with ~2,900 lines of template; the two redirects
add none. After the deletions: load the `translate-catalogues` skill,
regenerate, check. Expect the end-of-file-fixer hiccup on the first commit
after a regen, and `../.secrets.baseline` to need regenerating since test files
with allowlisted secrets shift or vanish.

### Docs

| File | Change |
| --- | --- |
| `docs/agent/future_work/delete_legacy_pages.md` | delete — done |
| `docs/agent/future_work/bdd_reused_server_feature_flags.md` | drop the legacy-dashboard row; the `FF_REGISTRATION_PAGE` half remains |
| `docs/agent/future_work/blueprint_shared_helpers.md` | names `targets_legacy.py` as one of eight `_is_htmx` copies — now seven |
| `docs/agent/future_work/bdd_assembly_to_project_wording.md` | **new** — the Q7 follow-up |
| `docs/agent/future_work/blueprint_names_without_backoffice.md` | **new** — the Q12 follow-up: with no legacy twins left, `backoffice_registration` and similar names carry a qualifier that distinguishes them from nothing; list each, its reference count, and the test patch targets a rename would move |
| `docs/testing.md`, `docs/architecture.md`, `docs/language.md`, `docs/sortition_error_translations.md`, `docs/agent/module_design.md`, `docs/agent/frontend-architecture/htmx-first.md`, `../docs/task_monitoring.md` | each mentions a legacy route, template or blueprint; read and correct each |
| `docs/configuration.md` | flags table already omits the dashboard flags; check prose |
| `env.example` | remove the two flags and the note |
| `docs/agent/migration_notes.md` | leave |

## 7. Blueprint reorganisation — follow-up PR

Decisions Q12 (a) and Q13 (a): three blueprints, in a separate PR straight
after the deletion merges. URLs do not change — only Flask endpoint names and
module paths.

### 7.1 What `gsheets.py` contains today

Of its 18 routes:

**Source-agnostic (5 routes + the page renderer):**

- `GET /project/<id>/selection` — `view_assembly_selection`, 88 references
  across `src/`, templates and tests
- `GET /project/<id>/selection/<run_id>` — redirect to the query-param form
- `GET /project/<id>/selection/history/<run_id>` — `view_run_details`
- `GET /project/<id>/replacement`, `/replacement/<run_id>` — redirects
- `render_selection_page()`, `selection_waiting_for()`,
  `unbound_selection_settings_form()` and the context helpers —
  `db_selection_backoffice.py` imports three of these from `gsheets.py`

**Google Sheets only (13 routes):** `selection/load`, `selection/run`,
`selection/<run>/cancel`, `selection/modal-progress/<run>`,
`selection/replacement-modal-progress/<run>`, `replacement/load`,
`replacement/run`, `replacement/<run>/cancel`, the four `manage-tabs/*`, and
`gsheet/check`.

### 7.2 Target shape

| Blueprint | Module | Holds |
| --- | --- | --- |
| `selection` | `selection.py` | the Selection page, history, the redirects, `render_selection_page` and shared helpers |
| `gsheet_selection` | `gsheet_selection.py` | the 12 gsheet task routes (load/run/cancel/progress, replacement, manage-tabs) |
| `db_selection` | `db_selection.py` | today's `db_selection_backoffice`, suffix dropped |
| `data_source` (existing) | `data_source.py` | gains `gsheet/check` |

The import arrow then points the right way: both task blueprints import the
page renderer from `selection`.

### 7.3 Cost and care

- ~90 `url_for` references to rename, 88 of them one endpoint.
- ~85 `patch("opendlp.entrypoints.blueprints.gsheets.…")` targets in
  `tests/e2e/test_gsheets_routes.py`, `test_backoffice_gsheet_selection.py`
  and others to re-aim at whichever module now owns the patched name. A patch
  aimed at a module that merely re-exports the name does not intercept the
  call, so every moved test has to actually run, not just import.
- Test files are renamed to follow their blueprint where the old name would
  mislead (`test_gsheets_routes.py`).
- Commits: move code with no behaviour change first (one commit per new
  module), then the endpoint renames, so `git log --follow` and review both
  stay readable.
- Timing: it conflicts with any open branch touching `gsheets.py` or the
  selection templates, so it lands at a quiet moment — your call when.

Dropping the `backoffice` qualifier from the *other* blueprints and the other
moves noted under Q14 (`backoffice.py`'s members routes, its leftover `/edit`
and `/data` redirects, a one-route `main`) are not part of this — the first
goes to `future_work/`, the rest are left.

## 8. Order of work

Each step leaves the suite green, so each is a commit (or a few).

1. [x] **Baseline.** `just test-nobdd-cov`; save the per-file coverage in the
   scratchpad. `just build-all`, then run the BDD suite once to confirm a clean
   start.
2. [x] **Convert BDD** (section 5) while the legacy pages still exist: step files,
   `tests/bdd/config.py` and `conftest.py` move to backoffice URLs; add the
   database implementation of `selection.feature`. Feature files unchanged.
3. [x] **Repoint live callers** (section 2.2): `admin.py`, footer links, service
   docs prose. Replace `default_dashboard_endpoint()` with the literal.
4. [x] **Port tests and add e2e smokes**: do the deletion on a throwaway branch,
   diff coverage, come back and write what the diff asks for (4.1, 4.3).
5. [x] **Delete** the four `*_legacy` blueprints, the nine `main` routes, the five
   template folders and the wholly-legacy test files; edit the mixed test
   files; add the two redirects, their tests and the retirement test.
6. [x] **Remove flags**: helpers in `feature_flags.py`, `env.example`,
   `TEST_FEATURE_FLAGS` entries, `test_dashboard_feature_flags.py`.
7. [x] **Orphans** (section 2.4, section 6 JavaScript): forms, service functions,
   the repository method, `team-selector.js` and its bundle. Second coverage
   diff to confirm nothing live lost cover.
8. [x] **Catalogues and baseline**: regenerate translations, `.secrets.baseline`.
9. [x] **Docs** (section 6), including the two new `future_work/` notes.
10. [ ] `just check`, then `just test` in full (serial, output to a file).
11. [ ] **Blueprint reorganisation** (section 7) — separate PR.

Notes from step 2:

- Baseline: 8,375 non-BDD tests passed, 96.52% coverage.
- The database run of `selection.feature` fits the shared step text. "I check
  the data" is a test selection, since the Selection tab offers no separate
  check for data held in OpenDLP (the `selection/db/check` route exists but
  nothing in the interface posts to it). "I am asked for the number to select"
  is the dialog's "1 place is to be filled", with the number field behind
  "Change the number of replacements".
- On the Google Sheets replacement path, a finished check's messages are not in
  the replacement dialog, which moves straight to the number field. The step
  reads them from the run in the selection history, in a second tab.
- `scroll-preservation.feature`: the pagination scenario now uses the Selection
  tab's history and passes headless. Three of the other four scenarios fail
  headless, as they did before; the file stays skipped in CI.
- "the user signs out" opens the account menu first: the backoffice keeps
  "Sign out" inside it.

Notes from steps 3 to 9:

- Steps 3, 5 and 6 went in as one commit: the suite ran with the legacy
  dashboard flags on, so the callers, the routes and the flags could not be
  changed apart and stay green.
- The redirect endpoints are `main.dashboard_redirect` and
  `main.assembly_redirect`, so a stale `url_for("main.dashboard")` fails
  loudly rather than quietly redirecting.
- **Coverage diff (Q4).** Outside the deleted and edited files, 18 lines in
  four modules lost cover. Three were behaviours whose only test drove a legacy
  page, and are ported:
  - a CSV added to existing respondents skips IDs already held
    (`tests/integration/test_csv_import_with_config.py`);
  - starting the check of a spreadsheet's replacement tabs records the run and
    dispatches the task (`tests/unit/test_sortition_service.py`);
  - `get_or_create_selection_settings`, now called only by the dev service docs
    (`tests/unit/test_assembly_service.py`).
  The round trip of selection settings through the Google Sheets form, one of
  the two rows marked "to watch", is ported to the data source dialog
  (`tests/e2e/test_backoffice_gsheet_selection.py`). The other, the user search,
  already had its `db_semantics` twins in `tests/e2e/test_backoffice_assembly.py`.
  A second diff after step 7 showed no surviving module with more missing lines.
- **E2E smokes (Q5).** None added: create, edit, add and remove a team member,
  user search and saving Google Sheets settings each already had a PostgreSQL
  smoke under a backoffice name.
- **Orphans (Q8).** The list in section 2.4 was re-derived from the imports of
  the deleted modules and matched exactly. The seven unit tests of the link
  rule that called `update_target_category` and `delete_target_category` now
  call `save_all_targets`, so the rule keeps its tests.
- **Secrets baseline.** Left alone: the hook passes, and a regenerated baseline
  pulls in 300 lines of unrelated entries.

**Found and left, for a decision** (code only the legacy pages used that is not
in section 2.4, so not deleted):

- `ManageOldTabsStatus.is_fresh` (`domain/value_objects.py`): only a legacy
  template read it. Three lines, now untested.
- `grant_user_assembly_role(..., email_adapter, template_renderer,
  url_generator)` (`service_layer/user_service.py`): only the legacy members
  route passed the adapters. The backoffice sends the email itself with
  `send_assembly_role_assigned_email`, so the three parameters and the branch
  that uses them are dead.
- `POST /backoffice/project/<id>/selection/db/check`
  (`db_selection_backoffice.check_db_data`): a live route with tests, but
  nothing in the interface posts to it.
- `tests/unit/test_env_scrub.py::test_the_declared_test_flags_are_on` passes
  vacuously while `TEST_FEATURE_FLAGS` is empty. It guards the mechanism Q10
  kept, so it stays.

I stop and ask, rather than decide, if any of these turns up:

- a legacy test asserting a behaviour the backoffice route does not have;
- a line losing coverage that is neither ported nor listed in section 2.4;
- a BDD step with no backoffice equivalent (the "created by" line, the gsheet
  selection options, scroll-preserving pagination, "asked for the number to
  select" on the database path).

## 9. Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| A service function loses its only test | medium | coverage diff, steps 1/4/7 |
| A live link into a legacy route was missed | low | audited by endpoint name; Flask raises `BuildError` at render, which component and BDD suites would hit; the retirement test |
| A capability existed only on a legacy page | low | the five candidates are each accounted for in section 2.4 |
| The database run of `selection.feature` does not fit the shared step text | medium | stop-and-ask, section 5.1; fallback is a `future_work/` note rather than a bent feature |
| Converted BDD steps are flakier (dialogs, modals) than the page-per-step legacy ones | medium | borrow locators and waits from the `replacement-selection` and `project-details` step files |
| The follow-up rename conflicts with open branches | medium | separate PR, timed by you |
