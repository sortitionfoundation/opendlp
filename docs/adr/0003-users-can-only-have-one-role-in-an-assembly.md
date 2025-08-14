# 3. Users can only have one role in an assembly

Date: 2025-08-14

**tl;dr** For now a user can just have a single role for an Assembly. This might be revisited as the roles develop - there are notes on what to change below.

## Status

Accepted

To be reviewed as we start using and fleshing out the roles for a user in an Assembly.

## Context

For non-Admin/Global users, they must be given a role for an Assembly to even be able to see it exists. The roles defined at this point are:

- Assembly Manager - can do anything
- Confirmation Caller - can view registrants and edit data to support making confirmation calls.

(See `AssemblyRole` enum in `domain/value_objects.py`)

So currently the AssemblyManager can do everything that the Confirmation Caller can do - so we can just use one role for any user.

But we plan to expand the roles, but have yet to define them. At some point we might have two roles where the permissions are not a superset of each other - maybe some permissions relate to invites and the other to registrants. At that point we might want to give a user both roles.

## Decision

For now we will only support one role per User/Assembly combination.

## Consequences

The code is simpler.

Having multiple roles per User/Assembly is more flexible, but means more code:

- support multiple records per User/Assembly in the database,
  - note that we already have
- more complex web pages for showing what roles people have,
- more complex web forms for managing the roles people have.

See Context for more.

## Other

Places to update if we revisit this decision:

- `service_layer/user_service.py` - `assign_assembly_role()` - currently if a new role is assigned it will edit that rather than add a new one.
- `service_layer/repositories.py` and `adapters/sql_repository.py` - `get_by_user_and_assembly()` and `remove_role()` both assume there is only one role to be got/removed.
- any bits of the web UI that show the roles people have for an assembly, or allow editing that.
- removing an assembly role would need to look for multiple

No updates required:

- Quite a lot of code just looks through all assembly_roles for a user/assembly, so it can cycle through multiple. Example: `can_manage_assembly()` in `service_layer/permissions.py`
