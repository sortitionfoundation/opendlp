# Organiser role — a user who can create assemblies but only sees their own

**Issue:** 913
**Branch:** `913-user-create-project`
**Date:** 2026-09-01, decisions recorded 2026-09-02
**Status:** Decided. Nothing implemented yet. §7 records the decisions; §9 lists the
few consequences those decisions created, with the call I've made on each.

## 0. Terminology

The issue says "project"; the code, the DB and the UI all say **assembly**. This
plan uses "assembly" throughout and there is no rename (D6). "Create a project"
therefore means `create_assembly`, and "added with the role assembly manager"
means `AssemblyRole.ASSEMBLY_MANAGER`, which already exists.

## 1. What we have today

Three global roles (`domain/value_objects.py:10`), stored as their string values
via `EnumAsString` (`adapters/orm.py:254` for users, `:313` for invites):

| Role | Create assemblies | See/manage assemblies | Invites | Site admin UI |
|---|---|---|---|---|
| `admin` | yes | **all of them** | yes | yes |
| `global-organiser` | yes | **all of them** | yes | link shown, but 403 |
| `user` | no | only where granted an assembly role | no | no |

So today `global-organiser` is "admin without user management", and it is the
only thing standing between "can create an assembly" and "can read every
assembly in the system". That is the conflation this issue unpicks.

Facts worth having in front of us:

- **Blanket access funnels through four functions.** `can_view_assembly`,
  `can_manage_assembly`, `can_edit_respondent` (`service_layer/permissions.py:15-71`)
  and `User.can_access_assembly` (`domain/users.py:106`). Everything else —
  every sortition entry point, the exports, target checking — goes through
  `@require_assembly_permission(can_manage_assembly)`
  (`service_layer/sortition.py`, `respondent_export_service.py`,
  `target_checking.py`). Narrowing those four functions narrows the whole app.
  There is no route that fetches an assembly and renders it without one of them.
- **Two more places grant "see everything"** outside those functions:
  `user_service.get_user_assemblies:187` and
  `sql_repository.get_assemblies_for_user:261` (the dashboard lists).
- **`has_global_organiser` (`permissions.py:105`) is doing three unrelated
  jobs**: "can create an assembly" (`assembly_service.py:78`), "can do anything
  with invites" (all six checks in `invite_service.py`), and "bypass the
  per-assembly role check" (`entrypoints/decorators.py:193`).
- **`require_global_organiser` (`entrypoints/decorators.py:93`) is dead** — no
  route uses it.
- **The backoffice "Create New Assembly" button is not gated at all**
  (`templates/backoffice/dashboard.html:19` and `:43`). A plain user can click
  it, fill the form, and gets a flash + redirect from the service-layer
  `InsufficientPermissions`. The old dashboard does gate it
  (`templates/main/dashboard.html:21`).
- **The "Site Admin" nav link is shown to global-organisers**
  (`templates/base.html:60`, `templates/backoffice/base_page.html:18`) but every
  route in `blueprints/admin.py` is `@require_admin`, so it is a link to a 403.
- **Only admins can add members to an assembly.**
  `can_manage_assembly_users = has_global_admin(current_user)`
  (`blueprints/backoffice.py:420`, `blueprints/main.py:171`), and
  `search_assembly_candidate_users` requires `has_global_admin`
  (`user_service.py:1017`) even though its own error message says "admin or
  global-organiser". The underlying `grant_user_assembly_role` is happy with an
  assembly manager — it is only the UI and the search that are admin-locked.
- **`create_assembly` gives the creator no role at all**
  (`assembly_service.py:82-90`), and records no creator either — it takes
  `created_by_user_id` purely to check permissions. It doesn't need to today,
  because only all-seeing roles can call it.
- **`sql_repository.get_admins():214`** returns admins *and* global-organisers.
  Nothing in `src/` calls it; only `tests/integration/test_repositories.py`.

## 2. The shape we're building (confirmed)

**`GLOBAL_ORGANISER` is repurposed into `ORGANISER` with the new meaning. After
this PR, `global-organiser` does not exist — not as an enum member, not as a
stored value, not in the UI.** No non-admin role can see every assembly.

| Role | Create assemblies | Sees | Invites | Site admin |
|---|---|---|---|---|
| `admin` | yes — and is added as assembly manager of what they create | all assemblies | yes | yes |
| `organiser` | yes — and is added as assembly manager of what they create | only assemblies they hold a role on | no | no |
| `user` | no | only assemblies they hold a role on | no | no |

Why not add `ORGANISER` alongside a properly-defined `GLOBAL_ORGANISER`: the
only capability `global-organiser` has that `admin` lacks is *not* being able to
manage users — a "trusted staff member, don't let them edit accounts" tier. That
is a real thing, but it is a question about **admin** privileges, not about
assemblies, and nothing needs it today (D1).

The hierarchy `USER(1) < ORGANISER(2) < ADMIN(3)` in `get_role_level` still
holds under the new meaning, so `require_admin` and friends keep working
unchanged.

**Worth noting given open signup is coming** (D3): once anyone can create an
account off the internet, `user` is what they get, and `can_create_assembly`
becomes the boundary between the public and our compute. It is worth having that
boundary be a single named function before that lands, rather than after.

## 3. The seam for the coming permissions refactor

Everything below adds capability-named functions and routes all callers through
them, so the refactor has one file to replace rather than a scatter of role
comparisons. Three rules:

1. **Ask a capability, never a role.** New code calls
   `can_create_assembly(user)`, not `user.global_role == GlobalRole.ORGANISER`
   and not `has_global_organiser(user)`.
2. **Every capability function has one of two shapes** — `(user) -> bool` for
   global capabilities, `(user, assembly) -> bool` for per-assembly ones. That
   is the shape a future policy object (`Policy(user).can_view(assembly)`) can
   absorb without touching call sites.
3. **No new callers of `get_role_level` / `require_global_role(role)`.** The
   numeric hierarchy is the assumption most likely to die in the refactor
   (D9 keeps it, but frozen). Routes get
   `require_capability(can_create_assembly)` instead (§4.5).

New in `service_layer/permissions.py`:

```python
def can_create_assembly(user: User) -> bool          # ADMIN or ORGANISER
def can_see_all_assemblies(user: User) -> bool       # ADMIN only
def can_administer_site(user: User) -> bool          # ADMIN only — user mgmt, invites, admin UI
def can_manage_assembly_members(user, assembly) -> bool  # admin, or manages this assembly
```

`has_global_organiser` is deleted once its seven call sites are migrated;
`has_global_admin` stays (it is the honest name for what it does) and
`can_administer_site` is defined in terms of it.

## 4. Implementation, in the order I'd do it

Each phase is a commit that leaves the suite green.

### 4.1 Capability functions, no behaviour change — DONE

Add the four functions above, defined to return exactly what the current code
returns. Migrate every caller of `has_global_organiser` to the right one:

- `assembly_service.create_assembly:78` → `can_create_assembly`
- `invite_service` ×6 → `can_administer_site`
- `decorators.require_assembly_role:193` → `has_global_admin` alone (this is a
  behaviour change and belongs in 4.4, but the *call* moves here)

Also add `UserCapabilities` (a small frozen dataclass or a set of properties)
for templates, injected by a context processor as `perms` — see 4.6.

### 4.2 Rename the role — DONE

- `GlobalRole.GLOBAL_ORGANISER = "global-organiser"` → `ORGANISER = "organiser"`
  (D8: the stored value changes too).
- `global_role_options` labels rewritten (§4.8).
- Templates carrying the literal string: `admin/users.html:75` (filter option
  value), `:135` (badge), `admin/invites.html:84`, `admin/invite_view.html:56`,
  `admin/user_view.html:52`, `main/dashboard.html:21,69`, `base.html:60`,
  `backoffice/base_page.html:18`, and
  `backoffice/service_docs/_assembly.html:15` (a "🔒 global-organiser or admin"
  annotation).
- A bookmarked `?role=global-organiser` now raises `ValueError` inside
  `filter_paginated` (`sql_repository.py:98`), which the route's blanket
  `except Exception` turns into a 500 (`blueprints/admin.py:114`). Fix while
  we're here: an unknown role filter is ignored (treated as no filter).
- 34 `required_role="..."` strings across seven files mention "global-organiser"
  (`assembly_service.py` 9, `target_service.py` 8, `invite_service.py` 6,
  `respondent_service.py` 6, `user_service.py` 3, `blueprints/main.py` 1,
  `respondent_field_schema_service.py` 1). These are log/diagnostic strings, not
  response bodies, but they'd be lying. Mechanical replacement with the accurate
  requirement ("assembly-manager or admin", "admin", etc. — the right one per
  site, not a blanket string).

### 4.3 The data migration — DONE

Hand-written Alembic revision (`uv run alembic revision -m "retire global-organiser role"`,
no autogenerate). Both columns are plain strings (`EnumAsString`), so this is a
value update, not a type change:

```sql
UPDATE users        SET global_role = 'user' WHERE global_role = 'global-organiser';
UPDATE user_invites SET global_role = 'user' WHERE global_role = 'global-organiser';
```

Per D2 the single production `global-organiser` is a test account belonging to
someone Chewie knows; it becomes a plain `user` and gets sorted out by hand
afterwards. No backfill of `user_assembly_roles`, no attempt to preserve access.

**The downgrade cannot reverse this** — after the update there is nothing to
distinguish a converted row from a row that was always `user`. So `downgrade()`
is a documented no-op with a comment saying why, rather than a lie that turns
every user into a global-organiser. The rest of the PR's downgrade path is
unaffected. If that feels wrong when we come to write it, the alternative is to
record the affected ids in the migration file itself as a literal list, produced
by running the `SELECT` in §5 first — for one row that is entirely reasonable
and I'd take it if the id is to hand.

`EnumAsString.process_result_value` calls `GlobalRole(value)`, so any row still
holding `'global-organiser'` after the new code is live raises `ValueError` on
load — i.e. that account cannot log in. `docs/deploy.md:274-279` already says stop
the app, migrate, start, so there is no rolling-deploy window to worry about;
this just means the migration is not optional.

### 4.4 Narrow the blanket access — DONE

Remove `ORGANISER` from:

- `permissions.can_view_assembly:54`, `can_manage_assembly:31`,
  `can_edit_respondent:63`
- `domain/users.User.can_access_assembly:108`
- `user_service.get_user_assemblies:187`
- `sql_repository.get_assemblies_for_user:261`
- `decorators.require_assembly_role:193` (bypass becomes admin-only)
- `sql_repository.get_admins:214` — deleted outright, along with its test (D10)
- `decorators.require_global_organiser:93` — deleted (D10)

After this, an organiser with no assembly roles has an empty dashboard and 403s
on every assembly URL. That is the point of the change, and it is also why 4.5
and 4.7 have to land in the same PR.

### 4.5 Creator becomes assembly manager, and is recorded — DONE

Two things, both in `create_assembly`, both unconditional — admins get the same
treatment as organisers (D5), so there is no branch here.

**The role.** After `uow.assemblies.add(assembly)`:

```python
assign_assembly_role(uow, created_by_user_id, assembly.id, AssemblyRole.ASSEMBLY_MANAGER)
```

`user_service.assign_assembly_role` already exists and already handles the
"role already present" case; `assembly_service` already imports from
`user_service`, so no new import cycle. `User.assembly_roles` is mapped with
`cascade="all, delete-orphan"` (`adapters/database.py:105`), so appending
persists without an explicit `add`.

One thing to prove with an integration test rather than reason about: the new
`user_assembly_roles` row and the new `assemblies` row are flushed in the same
`commit()`, and the FK ordering has to come out right. SQLAlchemy sorts inserts
by table dependency and there *is* a FK from `user_assembly_roles.assembly_id`
to `assemblies.id` (`orm.py:295-301`), so it should be fine — but it is exactly
the kind of thing that fails only against a real Postgres, so it gets a real
test.

**The column** (D11). `assemblies.created_by_user_id`:

```python
Column("created_by_user_id", PostgresUUID(as_uuid=True),
       ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
```

- `SET NULL`, not `CASCADE` — deleting a user must never delete their
  assemblies. (In production users are blanked, not deleted; the row and its id
  survive, so `created_by_user_id` keeps pointing at a real, now-anonymous row —
  which is exactly what `docs/personal-data.md` asks for. It stores a UUID, no
  PII, so erasure needs no new code.)
- Nullable, because existing assemblies have no recorded creator and we cannot
  invent one. Guessing from the earliest `user_assembly_roles` row would be
  plausible-looking and wrong often enough to be worse than NULL.
- Its own autogenerated revision, separate from §4.3 — one is schema, one is
  data, and mixing them makes both harder to read.
- `Assembly.__init__` gains `created_by_user_id: uuid.UUID | None = None`, and
  **`create_detached_copy` (`domain/assembly.py:153`) must copy it** — that
  method is a hand-written field list, so a new field is silently dropped unless
  added. A test asserts the round trip.
- `_delete_all_test_data` (`tests/conftest.py:293`) already deletes `assemblies`
  before `users`, and the BDD `delete_all_except_standard_users` keeps its
  standard users, so neither needs reordering for the new FK. Worth an explicit
  check when the migration lands rather than an assumption.
- No UI for it in this PR. The obvious home when we want it is a "Created by X
  on <date>" line on the assembly members page, next to the existing member
  list.

**And a route-level gate**, so the check is visible at the entry point rather
than only in the service:

```python
def require_capability(check: Callable[[User], bool]) -> Callable[[F], F]  # entrypoints/decorators.py
require_create_assembly = require_capability(can_create_assembly)
```

applied to `backoffice.new_assembly` and `main.create_assembly_page`. The
service-layer check stays — defence in depth, and the CLI and dev blueprint
(`blueprints/dev.py:521`) reach the service directly.

### 4.6 UI gating

- `templates/backoffice/dashboard.html:19,43` — wrap both buttons in
  `{% if perms.create_assembly %}`. The empty-state card needs different copy
  for someone who cannot create anything ("You have not been added to any
  assemblies yet — ask an organiser to add you.").
- `templates/base.html:60` and `templates/backoffice/base_page.html:18` —
  `_is_site_admin` becomes admin-only, so the Site Admin link stops being a
  link to a 403.
- `templates/main/dashboard.html:21,69` — same capability check instead of the
  hardcoded role list.

Context processor (`entrypoints/context_processors.py`) injects `perms` for
authenticated users and a "nothing is permitted" instance for anonymous ones —
templates must not have to guard on `current_user.is_authenticated` before
asking.

### 4.7 Assembly managers can manage their own members

Without this an organiser can create an assembly and then cannot add a single
colleague to it, so it is in scope rather than a follow-up:

- `blueprints/backoffice.py:420` and `blueprints/main.py:171` —
  `can_manage_assembly_users = can_manage_assembly_members(user, assembly)`.
- `grant_user_assembly_role` / `revoke_user_assembly_role` already allow
  assembly managers; no change needed.
- `user_service.search_assembly_candidate_users:1017` — accept assembly
  managers, not just admins, **but non-admins match on an exact full email
  address only** (D4); admins keep partial matching over email and display name.
  This is the one privacy-relevant change in the plan: it lets a non-admin
  query the user table, and partial matching would make that an
  account-enumeration surface (`docs/personal-data.md`).

  Implementation: a separate repository method rather than a boolean flag on
  `search_users_not_in_assembly` — `get_by_email_not_in_assembly(assembly_id, email)`
  returning `User | None`, so the two access levels are two different queries
  and no one has to reason about a flag's default. The route
  (`backoffice.search_users:732`) is unchanged: it still returns a JSON array of
  `{id, label, sublabel}`, just with at most one element for a non-admin. No
  response-shape change, so no JSON Schema or API fixture churn.

  Consequence to accept knowingly: the endpoint still answers "does this exact
  address have an account?" for any assembly manager. That is the minimum a
  member-adding UI can leak, short of D4's option (c) — never confirm, just
  attempt the add — which makes typos undebuggable. Worth a line in
  `docs/personal-data.md`, since that document currently has no entry for
  non-admin access to the user table.

### 4.8 Profile page context

`templates/profile/view.html:30` currently renders the raw enum value
(`global-organiser`) in a tag. Replace with the human label plus a short
explanation of what the role means (D7 — label and one-liner, no assembly list):

| Role | Tag | Explanation under it |
|---|---|---|
| admin | Admin | "You can see and manage every assembly, and manage users and invites." |
| organiser | Organiser | "You can create assemblies. You can see the assemblies you have been added to, and the ones you create." |
| user | User | "You can see the assemblies you have been added to. An organiser can add you to one." |

Strings live next to the role definitions in `domain/value_objects.py` (a
`global_role_descriptions` dict alongside the existing `global_role_options`,
both `_l()`), so the form labels and the profile page cannot drift apart.

Listing the assemblies you hold a role on, with your role in each, is the
natural follow-up — it turns the profile page into the answer to "why can't I
see X?" — but it needs a service call from a route that currently makes none,
so it is a separate issue.

### 4.9 Docs, seeds and i18n

- `AGENTS.md` — "Global roles: admin, global-organiser, user" → new names, and
  a sentence on what each means.
- New `docs/roles-and-permissions.md` (short): the table from §2, the capability
  functions, the "ask a capability, not a role" rule, and the orphaned-assembly
  note from D12. Nothing in `docs/` currently states what a global-organiser is,
  which is how we got here.
- `docs/personal-data.md` — the non-admin user lookup from §4.7.
- `docs/agent/history/spec.md:140` is historical — leave it.
- `service_layer/db_utils.py:81,122` — seeded organiser user and organiser
  invite. The seeded organiser should now also own a seeded assembly, otherwise
  local dev with that account shows an empty dashboard.
- `just translate-regen` after the label/description changes.
- If test files with secret-looking lines shift, regenerate `../.secrets.baseline`.

## 5. Deploying it

Per D2 there is one `global-organiser` in production, a known test account.
Confirm that before running the migration, because the plan is built on it:

```sql
SELECT global_role, count(*) FROM users GROUP BY global_role;
SELECT id, email FROM users WHERE global_role = 'global-organiser';
SELECT global_role, count(*) FROM user_invites GROUP BY global_role;
```

If the answer is still "one, and it's the test account", the migration converts
it to `user` and Chewie grants whatever access it actually needs by hand. If the
count has grown by deploy day, stop and revisit §4.3 — a silent downgrade of
several real accounts is not something to discover afterwards.

The invite query is the one most likely to surprise us: an unredeemed
`global-organiser` invite also becomes a `user` invite, so anyone holding that
link signs up with less access than they were promised. One row or none, most
likely, but worth looking rather than assuming.

Otherwise the sequence is the standard one from `docs/deploy.md:274-279` — backup,
stop the app, `alembic upgrade head`, start.

## 6. Test plan

Following `docs/testing.md`; nothing here is "not applicable".

**Unit** (`tests/unit/test_permissions.py`, `tests/unit/domain/test_users.py`)
— the full matrix: {admin, organiser, user} × {no role, assembly-manager,
confirmation-caller, read-only} × {can_view, can_manage, can_edit_respondent,
can_call_confirmations, can_create_assembly, can_see_all_assemblies,
can_administer_site, can_manage_assembly_members}. Written as a parametrised
table, because that table *is* the specification and the refactor will want to
re-run it against the new implementation unchanged.

**Unit/service** (`test_assembly_service.py`, `test_user_service.py`,
`test_invite_service.py`) — organiser creating an assembly gets the
assembly-manager role and `created_by_user_id`; **admin creating one gets the
same** (D5, and it is the case most likely to regress if someone reintroduces a
branch); organiser refused view/update/archive on an assembly they hold no role
on; `get_user_assemblies` returns only their own; invites refused for organisers
and allowed for admins.

**Unit/domain** — `create_detached_copy` preserves `created_by_user_id`.

**Integration** — the role migration up (and the no-op downgrade, asserted as a
no-op, so nobody "fixes" it later by accident); the `created_by_user_id`
migration up and down; the creator-role row and the creator column land in one
real commit with the right FK ordering; `get_assemblies_for_user` per role; the
exact-email search returns one row for an assembly manager and partial search
still works for an admin.

**Component** — dashboard with and without the Create button per role; the
empty-state copy for a user with nothing; 403 on an assembly URL for a
non-member organiser; profile page shows the right label and explanation for
each of the three roles; Site Admin link present for admin only; members page
shows the add-member form to an assembly manager; the member search endpoint
returns `[]` + 403 for a non-member and a single exact match for a manager.
(Per the e2e→component migration we've been doing, these go in
`tests/component/` rather than `tests/e2e/`.)

**BDD** (`features/`) — one scenario file: an organiser signs in, creates an
assembly, sees it on their dashboard, is listed as its assembly manager, adds a
colleague by exact email; a second organiser cannot reach it by URL.

**Existing tests that will need updating** (all currently assert the blanket
access we are removing): `tests/unit/test_permissions.py` (17 refs),
`tests/unit/test_user_service.py` (10), `tests/unit/test_invite_service.py` (6),
`tests/component/test_admin_user_management.py`,
`tests/component/test_admin_invite_management.py`,
`tests/integration/test_user_assembly_role_management.py`,
`tests/integration/test_cli_integration.py`, `tests/integration/test_repositories.py`
(includes deleting the `get_admins` test outright),
`tests/e2e/test_admin_user_management.py`, `tests/unit/domain/test_users.py`,
`tests/unit/test_respondent_service.py`, `tests/unit/test_assembly_service.py`.

## 7. Decisions

Recorded from Chewie's comments, 2026-09-02.

| # | Question | Decision |
|---|---|---|
| D1 | Does anything need "sees every assembly but is not an admin"? | **No.** Admin covers it. Two tiers plus per-assembly roles. |
| D2 | What happens to existing `global-organiser` accounts? | **Convert to `user`.** Exactly one exists in production, a known test account; access is restored by hand afterwards. No backfill migration. |
| D3 | Can an organiser create invites? | **No — invites become admin-only.** Invites are being retired in favour of open signup soon, so this is not worth designing around. |
| D4 | Non-admin user search when adding members? | **Exact full email only** for non-admins; admins keep partial search. |
| D5 | Does an admin who creates an assembly also get assembly-manager? | **Yes**, uniformly — wanted independently, and it removes a branch. |
| D6 | Rename "assembly" to "project" in the UI? | **No.** Keep this change focused. |
| D7 | How much context on the profile page? | **Role label + one-line explanation.** Assembly list is a separate issue. |
| D8 | Rename the stored DB value, or only the Python name? | **Both.** |
| D9 | Keep `get_role_level` / the numeric hierarchy? | **Keep**, add no new callers, let the permissions refactor decide its fate. |
| D10 | `require_global_organiser` and `get_admins` | **Delete both**, and `get_admins`' test. |
| D11 | Should `Assembly` gain a `created_by` column? | **Yes** — add it. Nullable, `SET NULL`, no UI in this PR. |
| D12 | Orphaned assemblies when the last manager is disabled | **Acceptable** — admins can still reassign. Note it in the roles doc. |

## 8. Files this touches

| Area | Files |
|---|---|
| Roles & labels | `domain/value_objects.py`, `domain/users.py` |
| Assembly | `domain/assembly.py` (`created_by_user_id` + `create_detached_copy`) |
| Capabilities | `service_layer/permissions.py` |
| Services | `assembly_service.py`, `user_service.py`, `invite_service.py`, plus `required_role=` strings in `target_service.py`, `respondent_service.py`, `respondent_field_schema_service.py` |
| Persistence | `adapters/orm.py`, `adapters/sql_repository.py`, two new `migrations/versions/*.py` (schema: `created_by_user_id`; data: retire `global-organiser`) |
| Entrypoints | `entrypoints/decorators.py`, `blueprints/backoffice.py`, `blueprints/main.py`, `blueprints/admin.py`, `entrypoints/context_processors.py` |
| Templates | `base.html`, `backoffice/base_page.html`, `backoffice/dashboard.html`, `main/dashboard.html`, `profile/view.html`, `admin/{users,invites,invite_view,user_view}.html`, `backoffice/service_docs/_assembly.html` |
| Seeds & docs | `service_layer/db_utils.py`, `AGENTS.md`, `docs/personal-data.md`, new `docs/roles-and-permissions.md` |
| Tests | see §6 |

## 9. Consequences of the decisions, and the calls I've made

Things that only became questions once the decisions above were taken. Say if
any of these is wrong; otherwise I'll implement them as written.

1. **The role migration's downgrade is a no-op** (§4.3). Converting
   `global-organiser` → `user` destroys the information needed to reverse it.
   The alternative — hardcode the affected user id in the migration — is
   reasonable for one row, and I'd take it if you paste me the id from the
   `SELECT` in §5.
2. **Unredeemed `global-organiser` invites are downgraded too**, silently.
   Probably zero rows; §5 checks before assuming.
3. **`created_by_user_id` is NULL for every existing assembly.** No backfill —
   inferring the creator from the earliest assembly-manager row would be
   plausible-looking and wrong often enough to be worse than an honest NULL.
4. **The member-search endpoint still confirms account existence** for any
   assembly manager, by design (§4.7). It is the least a member-adding UI can
   leak; recorded in `docs/personal-data.md` rather than left implicit.
5. **The seeded local-dev organiser needs a seeded assembly** (§4.9), otherwise
   `just` dev with that account shows an empty dashboard and looks broken.
6. **Open signup (D3) will make `can_create_assembly` a public-facing
   boundary.** Nothing to do now beyond having it be one named function — worth
   flagging in `docs/roles-and-permissions.md` so whoever builds open signup
   sees it.
