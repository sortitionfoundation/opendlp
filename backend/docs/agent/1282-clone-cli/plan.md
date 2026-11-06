# 1282 - Clone a project from the CLI

Status: agreed after three rounds of review, not yet implemented. The
decisions are recorded in [Decisions](#decisions); the order of work is in
[Implementation order](#implementation-order).

## Goal

An admin can run one CLI command to make a copy of an existing project, for
demos and training. The copy is a new, independent project: editing or deleting
either one never touches the other.

Only projects whose data lives in OpenDLP (the "csv" / database data source,
with or without registration pages) can be cloned. A project with a Google
Sheet configured is refused.

The code that does the copying lives in the service layer
(`service_layer/assembly_clone_service.py`), so a web UI or a "copy this
template" feature can call the same function later. The CLI is a thin wrapper.

A second command, `opendlp projects list`, prints the projects one per line so
an admin can find the ID to clone.

## What gets cloned

| Part | Option | Default | Tables |
|---|---|---|---|
| Title, question, first date | always | - | `assemblies` |
| Number to select | always | - | `assemblies` |
| Selection settings | always | - | `selection_settings`, `assembly_csv` |
| Targets, and derived fields | `--targets/--no-targets` | yes | `target_categories`, derived rows of `respondent_field_definitions`, `respondent_field_mapping_entries` |
| Registration questions | `--questions/--no-questions` | yes | non-derived rows of `respondent_field_definitions`, `registration_content_blocks` |
| Registration form | `--registration/--no-registration` | yes | `registration_pages`, `registration_page_html_sources`, `registration_images`, `registration_documents`, `email_templates` |
| Respondents | `--respondents` (needs `--for-training-or-demo`) | no | `respondents` |
| Team members | `--team` | no | `user_assembly_roles` |

Never cloned:

- selection history - `selection_run_records`
- respondent email send records - `respondent_email_send_records` (an audit
  trail of real emails sent; it describes the original, not the copy)
- Google Sheet export config - `assembly_export_gsheets`. This one matters: an
  export sheet with `auto_export` on would push the clone's (demo) respondents
  into the original project's real spreadsheet.
- the Google Sheet config itself - we refuse those projects anyway
- reply-to name and email, on the project and on its email templates - blanked,
  so a demo's emails never invite replies to the real organiser
- respondent comments
- respondents with status DELETED (see [Respondents](#respondents))
- the `assemblies.config` JSON column - nothing reads or writes it, so there is
  nothing to copy. Dropping it is written up in
  [future_work/unused_assembly_config_column.md](../future_work/unused_assembly_config_column.md).

## What has to change on copy

Every row gets a new UUID, and every foreign key inside the clone is remapped
to the new IDs. Beyond that:

### The title

`assemblies.title` has no unique constraint and `create_assembly` does not
check for duplicates. This plan adds one rule, shared by creating, renaming
and cloning (see [The title rule](#the-title-rule)):

> A project's title may not match the title of an unarchived project that the
> acting user can see.

For the clone, the acting user is the admin named by `--user-email`, and an
admin can see every project, so in practice the CLI checks against every
unarchived project.

- `--title` given: if it breaks the rule, the clone fails and says so.
- `--title` not given: try `"<original title> (copy)"`, then
  `"<original title> (copy 2)"` up to `"(copy 9)"`. The first one the rule
  allows is used. If none is allowed, the clone fails and asks for `--title`.

The check is not backed by a database constraint (it can't be - it depends on
who is asking), so two creations racing each other could land the same title.
That is an accepted gap: the rule is there to stop confusion, not to guarantee
uniqueness.

The "(copy)" suffix is English and not wrapped in `_()`: it comes from a CLI
run in no request locale. When a web UI calls the same function, it should
pass a translated title in rather than have the service translate.

### The title rule

> A project's title may not match the title of an unarchived project that the
> acting user can see.

It applies to creating, renaming and cloning.

Why this rule:

- It targets the actual harm. Two projects with the same title only cause
  trouble when they sit side by side on one person's dashboard, and the
  dashboard shows exactly the unarchived projects you can read.
- Scoping it to what you can read means the rule leaks nothing. A global
  check would tell an organiser "a project called X exists somewhere", about
  a project they have no right to know about.
- It costs no new query. `user_service.get_user_assemblies` already returns
  exactly "the unarchived projects this user can see" (all active ones for an
  admin, the ones they hold a role on otherwise), so the check is a
  comparison over that list. Projects number in the hundreds, not the
  millions, so loading them is fine. If that ever changes, it becomes one
  query.

How it applies:

1. **Renaming too, not only creating.** Otherwise you create "Climate 2" and
   rename it to "Climate", and the rule is defeated by the edit form.
   `update_assembly` checks when the title is in its updates.
2. **Only when the title actually changes.** Production almost certainly
   already has some duplicates. Editing the question on one of them must not
   start failing because of a title nobody touched. The rename check excludes
   the project itself, and is skipped if the new title matches the old one.
3. **Match on the stripped, case-folded title.** "Climate Assembly" and
   "climate assembly " are the same title to a person reading a dashboard.

What it can't catch, and doesn't need to: two organisers each make
"Climate Assembly" in their own corners, and later one is added to the
other's team. They then see two projects with the same title. That's rare,
and fixed by a rename.

One knock-on: creating and renaming happen on web forms, so they need a
translated error message - "You already have a project called %(title)s" or
similar - and the form shows it against the title field. That means touching
`main.py` and `backoffice.py` (the routes that call `create_assembly` and
`update_assembly`), their tests, and the catalogues. That's more than this
CLI ticket strictly needs, but the rule only makes sense if it applies
everywhere at once, so it goes in this branch, as its own commit ahead of the
clone work.

A risk to flag: about 50 files across `tests/` and `src/` call
`create_assembly`. Any test that creates two projects with the same title for
the same user, or for two admins, will start failing. I expect a handful, each
fixed by giving the second project its own title, but I won't know the number
until the rule is in and the suite has run.

The rule lives in one service-layer function,
`assembly_service.check_title_available(uow, user_id, title, exclude_assembly_id=None)`,
raising a new `AssemblyTitleTaken` exception, which carries the title and
opts in to `CuratedMessage` so the web form can show it. Create, update and
clone all call it. The "(copy N)" fallback calls a non-raising sibling,
`is_title_available`, in its loop.

### Registration page slugs

`url_slug` and `short_url_slug` are globally unique (partial unique indexes).
The clone generates fresh ones with the existing helpers in
`registration_page_service.py`: `_generated_url_slug` (built from the clone's
new title plus language / page name) and `generate_unique_short_url_slug`.
`_generated_url_slug` is private today - I'll make it public rather than
reimplement it.

Page `name` is unique only per project, so it is copied as is.

### Links inside the HTML point at the original

The page HTML (intro, form and thank-you) and email template bodies hold
literal URLs:

- images: `/register-assets/images/<image-id>.png` - by image **ID**. Cloned
  images get new IDs, so the clone's HTML would keep showing the *original*
  project's images. It works until the original is deleted or its pages stop
  being public (the by-id route only serves publicly when the image's own
  project has a loadable page) - then the clone's images vanish.
- older images: `/register/<slug>/assets/<sha>.png` - by page **slug**.
- documents: `/register/<slug>/documents/<sha>.pdf` - by page **slug**.

So the clone rewrites these: each old image ID becomes the new image ID, and
each old page slug in an asset URL becomes the matching new slug. Plain string
replacement of the exact URL prefixes, in `intro_html`, `form_html`,
`thank_you_html` and `email_templates.body_html`. That rewrite is a pure
function and belongs in the domain (or a small helper module), with unit tests.

### Registration page state

- `status` - always `TEST`. Cloning a PUBLISHED page would put a second live
  registration form on the public internet without anyone pressing publish. A
  TEST page also keeps its slugs editable (`slugs_frozen`). A demo that wants a
  published page publishes the clone's page in the usual way.
- `activity` - not copied. Replaced by one CREATE entry,
  "Registration page cloned from <original title>", authored by the user
  running the clone. The original log names people who never touched the clone.
- `auto_reply_email_template_id` - remapped to the cloned template.
- `thank_you_use_default`, `name`, `language` - copied.

### "Form is behind the questions" timestamps

A page's form HTML counts as out of date when `assembly.questions_updated_at`
is later than the HTML source's `form_updated_at`. If the clone stamps fresh
`now()` on everything in the wrong order, every cloned form shows as stale (or
a stale one shows as fresh). The clone copies both timestamps from the
original, so the relationship survives exactly.

### Targets, questions and derived fields

Derived fields (age ranges, option mappings, postcode lookups) only make sense
with the target they feed, so they travel with the **targets**, not the
questions. With `--no-targets`, no derived field is cloned, and neither are
their large-mapping lookup rows.

`respondent_field_definitions.target_category_id` points at a target category:

- targets cloned - remapped to the cloned category.
- targets not cloned - a plain (non-derived) question linked to a target
  becomes NULL, which is what deleting a category does today (the FK is
  `SET NULL`). The field ends up as a free editable field - a state the app
  already handles.

Large-mapping lookup rows (`respondent_field_mapping_entries`, e.g. postcode to
region) hang off a field ID, so they are copied with the new field ID. They can
run to hundreds of thousands of rows, so they go through the existing
`bulk_add`, not one by one.

`derived_from` and `derivation_config` refer to fields by `field_key`, not ID,
so they copy unchanged. Target values' `value_id`s live inside the category's
JSON and are only addressed within that category, so they can be copied as is.

A derived field's source is always a question, so cloning targets with
`--no-questions` would leave derived fields reading from fields that don't
exist. So `--targets` with `--no-questions` keeps the target categories but
drops the derived fields, the same as `--no-targets` does. (This is the
"targets without questions" case below.)

### Respondents

- `registration_page_id` - remapped to the cloned page, or NULL if
  registration is not cloned.
- `selection_run_id` - NULL (no history is cloned).
- `comments` - dropped. They are history, and their run IDs point at the
  original's selection runs.
- `selection_status` - reset by default (see below), or kept with
  `--preserve-respondent-status`.
- `attributes` - copied, except that derived values are stripped when derived
  fields are not cloned (see below).
- `external_id`, `email`, flags, `source_type` - copied. `external_id` is
  unique per project only, so it can be kept.

**Status reset.** The clone is a starting point for a demo or a training
session, made from test data, not a record of what happened to real people. So
the default puts everyone back in the pool, as if nothing had happened to them
yet - withdrawals included. The clone has no selection history to explain a
SELECTED or CONFIRMED status anyway. `--preserve-respondent-status` keeps the
statuses, for a demo that starts from a later point, such as replacements or
confirmation calling:

| Original status | Default (reset) | `--preserve-respondent-status` |
|---|---|---|
| POOL | POOL | POOL |
| SELECTED | POOL | SELECTED |
| CONFIRMED | POOL | CONFIRMED |
| WITHDRAWN | POOL | WITHDRAWN |
| TEST_SUBMISSION | TEST_SUBMISSION | TEST_SUBMISSION |
| DELETED | not cloned | not cloned |

- TEST_SUBMISSION is kept as is even on reset. Resetting it to POOL would
  promote test data into the selection pool, which the app only allows as a
  deliberate one-way step.
- DELETED respondents are never cloned. A DELETED row is the tombstone left
  when someone's details were blanked on request: its details are gone and it
  exists only so the original's references to its ID stay valid. The clone
  has no such references.

The flag is `--preserve-respondent-status` rather than `--preserve-status`
because the project and its registration pages have statuses too.

**Derived values in attributes.** Derived fields write their values into
`respondent.attributes` (`derivation_service.apply_derivations`), so a
respondent carries e.g. `age_range: "30-44"` alongside `date_of_birth`. With
`--respondents --no-targets` the derived field definitions are not cloned, but
those values would be - keys with no field definition behind them. So the
derived fields' keys are stripped from the cloned attributes, and the clone
looks like a project that never had them.

### Everything else

- `status` - ACTIVE, even if the original is archived.
- `created_by_user_id` - the user named by `--user-email` (see
  [Permissions](#permissions)), who also becomes its assembly manager (same as
  `create_assembly`).
- `created_at` / `updated_at` - now, apart from the timestamps above.
- images/documents `created_by` - the user running the clone.
- `assembly_csv` - copy `csv_id_column` and `settings_confirmed`; blank
  `last_import_filename` / `last_import_timestamp` (no import happened).
- `reply_to_name` / `reply_to_email` - blank, on the project and on every
  email template.

## How the options depend on each other

- **Registration form needs the questions.** The form HTML is generated from
  the field definitions and posts fields by `field_key`. A form without its
  questions accepts submissions that fit no schema. `--registration` with
  `--no-questions` is an error.
- **Respondents need the questions.** `attributes` are keyed by `field_key`,
  and the respondent screens group and label them from the field definitions.
  `--respondents` with `--no-questions` is an error.
- **Questions without targets** is allowed: target-linked questions come
  loose, and derived fields are dropped.
- **Targets without questions** is allowed: targets with no linked question,
  which is how a project looks before its registration form is built. Derived
  fields are dropped, as they have no source question.

Since `--registration` and `--targets` default to on, `--no-questions` on its
own is an error too - the message says to add `--no-registration`. That's
deliberate: it makes you say you want the form gone rather than losing it
quietly.

## Respondents and personal data

The respondents are the one part that can carry real personal data, and
cloning them doubles every copy that a right-to-be-forgotten request has to
find. The copies are ordinary rows in the database, so they stay findable -
that is fine by our GDPR rule - but we don't want it done casually.

Both of these, not one or the other:

1. `--respondents` is refused unless `--for-training-or-demo` is also given.
   The flag name is the statement "this is not real personal data", which is
   what we want to be explicit in shell history.
2. With both flags, an interactive confirmation that names the count:
   "This will copy 412 respondents. Confirm they contain no real personal
   data [y/N]". Skippable with `--yes` for scripts.

In the service layer the guard is a required keyword argument,
`confirm_no_personal_data: bool`, so a future web UI has to make the same
statement rather than inheriting the CLI's flag.

There is no check on whether the original ever had a published page: a demo
project may publish one to show what it looks like.

## Team members

`--team` copies every `user_assembly_roles` row with the same role. The user
running the clone is skipped (they are already manager) - unless they already
had a different role on the original, in which case manager wins.

## Permissions

**Service layer** - `clone_assembly` takes the acting `user_id` and checks:

- `can_create_assembly(user)` - organiser or admin
- `can_view_assembly(user, source)`, with a `TODO` comment to revisit once the
  planned permissions refactor is done - cloning team members hands out roles,
  which may turn out to want a manage capability.

**CLI** - `--user-email` is required. The command fails unless it names an
existing, active user whose global role is ADMIN. That admin is the clone's
`created_by_user_id` and its assembly manager.

The admin-only rule lives in the CLI command, not the service: it is a policy
for the CLI, and a future web UI will want organisers to clone their own
projects through the same service function. (An admin passes both service
checks anyway, since admins can view every project.)

## Service layer design

New module `service_layer/assembly_clone_service.py`:

```python
@dataclass(frozen=True)
class CloneOptions:
    title: str = ""            # "" means the first free "<original> (copy N)"
    targets: bool = True
    questions: bool = True
    registration: bool = True
    respondents: bool = False
    preserve_respondent_status: bool = False
    team: bool = False
    confirm_no_personal_data: bool = False


@dataclass(frozen=True)
class CloneResult:
    assembly: Assembly
    registration_pages: list[RegistrationPage]  # for the CLI to print the new slugs
    counts: dict[str, int]     # "targets": 7, "respondents": 412, ... for the CLI to print


def clone_assembly(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, source_assembly_id: uuid.UUID, options: CloneOptions
) -> CloneResult: ...
```

It takes an open `uow` and does not open or commit one - the CLI command opens
`with uow:` around the call and commits, per the UnitOfWork convention. The
whole clone is then one transaction: it either all lands or none of it does.

Internally one private function per part (`_clone_targets`,
`_clone_questions`, `_clone_registration`, `_clone_respondents`,
`_clone_team`), each returning the old-ID to new-ID map the later parts need
(category IDs for questions, page IDs and image IDs for respondents and HTML).
The domain objects gain nothing - the clone builds new instances through their
constructors, which also re-runs their validation.

The CLI's confirmation prompt needs the respondent count before the clone
runs, so the service also offers
`count_respondents_to_clone(uow, user_id, source_assembly_id) -> int`
(non-DELETED respondents, behind the same permission checks).

New exceptions in `service_layer/exceptions.py`:

- `CannotCloneGSheetAssembly`
- `InvalidCloneOptions` - the dependency rules above, and respondents without
  the personal data confirmation
- `AssemblyTitleTaken` - shared with create and rename (see
  [The title rule](#the-title-rule)); for a clone, also raised when no free
  "(copy N)" title was found

## CLI

New `entrypoints/cli/projects.py`, with a `projects` group registered in
`cli/__init__.py`. The UI says "project"; the code underneath still says
"assembly".

### `projects clone`

```
opendlp projects clone SOURCE_ID --user-email admin@example.com
    [--title "Demo assembly"]
    [--no-targets] [--no-questions] [--no-registration]
    [--respondents --for-training-or-demo] [--preserve-respondent-status]
    [--team]
    [--yes]
```

`SOURCE_ID` is the project UUID (it is in every backoffice URL, and in
`projects list`). Prints the new project's ID, its backoffice URL path, the new
registration slugs, and the counts of what was copied.

`--preserve-respondent-status` without `--respondents` is an error rather than
silently ignored.

### `projects list`

```
opendlp projects list [--member user@example.com] [--include-archived]
```

One project per line, tab-separated, so it pipes into `grep`, `cut` and `sort`:

```
<uuid>	<status>	<data source>	<title>
```

- data source is `gsheet`, `csv`, or `-` for a project with no source chosen
  yet, from the existing `determine_data_source`. It's there so you can see
  at a glance which projects can be cloned.
- title goes last, as the only column that can contain spaces.
- newest first, matching the dashboard.
- archived projects are left out unless `--include-archived` is given. (No
  project can be archived through the app yet, but the status column exists.)
- `--member` keeps only the projects that user holds a role on. It fails if
  the email names no user.

No acting user is needed on the CLI: listing reads nothing that the person
with shell access to the server can't already read.

#### The service function: `list_assemblies`

Named for what it does rather than its first caller, because an admin web UI
is expected to use it too - to find projects an admin is not a member of, and
the projects some user X is a member of:

```python
@dataclass(frozen=True)
class AssemblyListing:
    assembly: Assembly
    data_source: str          # "gsheet", "csv" or ""


def list_assemblies(
    uow: AbstractUnitOfWork, *, member_user_id: uuid.UUID | None = None, include_archived: bool = False
) -> list[AssemblyListing]: ...
```

in `assembly_service.py` (it is a read, not part of cloning), newest first.

Two things those use cases shaped:

- **Filter by membership, not by access.** "Projects user X is a member of"
  is a question about roles. "Projects user X can see" is the same question
  for an organiser, but for an admin it is "all of them", which tells you
  nothing. So the filter is `member_user_id`, and the CLI flag is `--member`
  rather than `--accessible-by`. Nothing is lost - for a non-admin the two
  give the same list, and for an admin `--accessible-by` would be the same as
  no flag at all.
- **It does no permission check, unlike nearly every other service
  function.** The CLI has no acting user to check. That's a trap for the web
  UI: a route that forgets to check would show every project to anyone. The
  docstring says so in its first line, and the web UI work should either add
  an `acting_user_id` parameter checked with `can_see_all_assemblies`, or
  wrap it in a function that does. The parameter is not added now, for a
  caller that doesn't exist yet - that is left to the web UI work.

The plumbing: one repository method,
`AssemblyRepository.list_filtered(member_user_id=None, include_archived=False)`
(abstract, SQL and fake), with both filters in one query. The existing
`get_active_assemblies` and `get_assemblies_for_user` stay as they are - the
dashboard and the title rule use them through `get_user_assemblies`, and they
mean what they say.

## Tests

- **Unit**:
  - the HTML URL rewrite (each URL form; IDs and slugs that are prefixes of
    other IDs/slugs; HTML with no asset URLs is unchanged)
  - option validation (every forbidden combination)
  - title choice: "(copy)", "(copy 2)", running out, an explicit title taken,
    case and whitespace in the match
  - the respondent status reset table
  - stripping derived keys from attributes
- **Integration** (real Postgres, service layer): a fully populated source -
  targets, linked and derived fields, a large mapping, content blocks, two
  registration pages with images, a document and an auto-reply template,
  reply-to set, respondents in every status with comments and derived values,
  team members, an export sheet, a selection run - cloned with each option on
  and off. Asserts: new IDs everywhere, remapped FKs, no row of the clone
  references the source, the source is unchanged, pages are TEST with new
  slugs, rewritten HTML, form staleness preserved, reply-to blank, derived
  fields present only with targets and questions, nothing from the never-cloned
  list exists. Plus: gsheet source refused, permission refused, invalid option
  combos refused, title clash refused. And `list_filtered` against Postgres,
  with each combination of its two filters.
- **The title rule** (service layer, integration): create, rename and clone
  each refused on a clash with an unarchived project the user can see;
  allowed on a clash with an archived one, or with one the user can't see;
  case and whitespace ignored; a rename to the same title, or an edit that
  doesn't touch the title of an already-duplicated project, still allowed.
  Plus component tests for the create and edit forms showing the error
  against the title field.
- **E2E**: the CLI commands through `CliRunner`, as `test_cli_integration.py`
  does:
  - `projects clone`: default clone; a non-admin, inactive or unknown
    `--user-email` refused; the respondents flag guard and its confirmation
    prompt (yes, no and `--yes`); the printed output.
  - Then load the clone's registration page by its new slug through the Flask
    test client and check it renders, with its images served from the clone.
  - `projects list`: line format, `--member` for an admin and a non-admin,
    an unknown `--member` email refused, `--include-archived`.

No migration and no new table, so `_delete_all_test_data()` is untouched.

## Docs

- `docs/cli.md` - both new commands.
- `docs/personal-data.md` - a line under erasure noting that cloned
  respondents are separate rows, and the training/demo flag.

## Decisions

From the first review:

1. Title: default `"<original> (copy)"`, checked against the title rule; fall
   back to "(copy 2)" ... "(copy 9)", then fail and ask for `--title`. An
   explicit `--title` that breaks the rule fails.
2. `number_to_select` is always copied.
3. Selection settings are always copied. Reply-to settings are blanked.
4. `--respondents` with `--no-questions` is an error.
5. Respondent status is reset by default; `--preserve-respondent-status`
   keeps it.
6. Respondent comments are dropped.
7. No check on whether the original was ever published.
8. `can_view_assembly` on the source, with a TODO for the permissions
   refactor. The CLI requires an ADMIN `--user-email`.
9. CLI group `projects`, file `projects.py`.
10. `projects list` is in scope, one per line, with a user filter and
    `--include-archived`.
11. TEST_SUBMISSION respondents are copied.
12. Derived fields are cloned only with the targets.

From the second review:

13. The title rule: a title may not match an unarchived project the acting
    user can see. Applies to create, rename and clone.
14. The listing service function is `list_assemblies()`.
15. The unused `assemblies.config` column goes in
    `docs/agent/future_work/` - written up as
    `unused_assembly_config_column.md`.
16. On a status reset, WITHDRAWN goes back to POOL, like SELECTED and
    CONFIRMED.
17. DELETED respondents are never cloned.
18. With `--respondents --no-targets`, derived values are stripped from the
    cloned attributes.

From the third review:

19. The title rule applies to renaming too, checked only when the title
    actually changes, and goes in this branch as its own commit ahead of the
    clone work.
20. `projects list --member` (holds a role on), not `--accessible-by`.
21. `list_assemblies` has no permission check for now; adding one is left to
    the web UI work.

Taken as agreed in the first round, since there was no comment on them:

- respondents need both `--for-training-or-demo` and the interactive
  confirmation (or `--yes`)
- cloned registration pages are always TEST, with a fresh activity log
- `--team` copies roles as they are, with the cloning admin as manager
- `_generated_url_slug` becomes public

## Implementation order

Each step is its own commit, with its tests, and leaves `just test` and
`just check` passing.

1. ✅ **The title rule** - `check_title_available` / `is_title_available` and
   `AssemblyTitleTaken`; called from `create_assembly` and `update_assembly`;
   the error shown on the web create and edit forms; catalogues regenerated;
   existing tests that reuse a title fixed.
2. ✅ **`list_assemblies`** - the `list_filtered` repository method (abstract,
   SQL, fake) and the service function.
3. **`projects list`** - the `projects` CLI group and the `list` command.
4. **The HTML URL rewrite** - the pure function and its unit tests.
5. **`clone_assembly`** - options and their validation, then each part in
   dependency order: project and settings, targets, questions and derived
   fields, registration, respondents, team. `_generated_url_slug` made public
   on the way.
6. **`projects clone`** - the CLI command, its admin check, the personal data
   flag and confirmation.
7. **Docs** - `docs/cli.md` and `docs/personal-data.md`.

## Open questions

None.
