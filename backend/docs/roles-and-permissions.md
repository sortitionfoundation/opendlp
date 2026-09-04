# Roles and permissions

Who can do what, and how to ask.

## The three global roles

| Role | Create assemblies | Sees | Invites and user management | Site admin UI |
|---|---|---|---|---|
| `admin` | yes — and becomes assembly manager of what they create | every assembly | yes | yes |
| `organiser` | yes — and becomes assembly manager of what they create | only assemblies they hold a role on | no | no |
| `user` | no | only assemblies they hold a role on | no | no |

**No non-admin role sees every assembly.** Creating an assembly is not the same
capability as reading everyone else's; an organiser has the first and not the
second. This is what distinguishes `organiser` from the `global-organiser` it
replaced, which was "admin without user management" and could read the whole
system.

## The three assembly roles

Held per assembly, in `user_assembly_roles`:

- **assembly-manager** — full control of that assembly, including adding and
  removing its members
- **confirmation-caller** — view the assembly, edit respondents, call
  confirmations
- **read-only** — view the assembly, change nothing

## Ask a capability, not a role

New code calls a capability function from `service_layer/permissions.py`. It
does not compare `user.global_role` and it does not use `get_role_level`. The
point is that a coming permissions refactor has one file to replace rather than
a scatter of role comparisons.

Global capabilities, shaped `(user) -> bool`:

```python
can_create_assembly(user)     # ADMIN or ORGANISER
can_see_all_assemblies(user)  # ADMIN only
can_administer_site(user)     # ADMIN only - users, invites, the admin UI
```

Per-assembly capabilities, shaped `(user, assembly) -> bool`:

```python
can_view_assembly(user, assembly)
can_manage_assembly(user, assembly)
can_manage_assembly_members(user, assembly)
can_edit_respondent(user, assembly)
can_call_confirmations(user, assembly)
```

Those two shapes are what a future policy object
(`Policy(user).can_view(assembly)`) can absorb without touching call sites, so
keep to them.

**In routes**, use `require_capability(can_create_assembly)` from
`entrypoints/decorators.py` (or the named `require_create_assembly`) rather than
`require_global_role`. The service-layer check stays as well — the CLI and the
dev blueprint reach services directly, without passing a route.

**In templates**, ask `perms`, injected into every context by
`inject_capabilities`:

```jinja
{% if perms.create_assembly %}...{% endif %}
{% if perms.administer_site %}...{% endif %}
```

Anonymous visitors get a bundle where nothing is permitted, so a template never
has to guard on `current_user.is_authenticated` first.

The full matrix — every global role crossed with every assembly role, for every
capability — is a parametrised table in `tests/unit/test_permissions.py`. That
table is the specification. A refactor should be able to re-run it unchanged.

## Things worth knowing

**Adding members can leak account existence.** An assembly manager searching for
a colleague matches on a *full email address only*; partial search over email
and name is admin-only. The endpoint therefore still confirms "does this exact
address have an account?" to any assembly manager, which is the minimum a
member-adding UI can leak. See [personal data](personal-data.md).

**An assembly can be orphaned.** If the last user holding assembly-manager on an
assembly is disabled, nobody but an admin can manage it. That is accepted: an
admin can always reassign the role. There is no automatic transfer.

**`created_by_user_id` is nullable.** Assemblies created before the column
existed have no recorded creator, and it is set to NULL if that user's row is
ever deleted outright. It stores only a UUID, so a GDPR erasure — which blanks
the user's details but keeps the row — needs no extra work here.

**Open signup will make `can_create_assembly` a public boundary.** Once anyone
can create an account from the internet, `user` is what they get, and
`can_create_assembly` is what stands between the public and our compute. It is
one named function for exactly that reason.
