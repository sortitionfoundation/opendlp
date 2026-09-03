# Ticket 718 — permission issues noted in passing

A place to record permission problems found while working on something else, so
they are not lost between now and the ticket that fixes them properly. Nothing
here has been acted on.

## `require_assembly_permission` fails open on keyword calls

Found during the code review of branch `886-dashboard-service-layer`
(see [../886-dashboard/service_layer_review.md](../886-dashboard/service_layer_review.md) §2).

### The mechanism

`src/opendlp/service_layer/permissions.py:161` reads the three arguments it needs
out of `args` positionally:

```python
def wrapper(*args: Any, **kwargs: Any) -> Any:
    # Expect signature: func(uow, user_id, assembly_id, ...)
    if len(args) >= 3:
        uow, user_id, assembly_id = args[0], args[1], args[2]
        ...
        if not permission_func(user, assembly):
            raise InsufficientPermissions(...)
    return func(*args, **kwargs)
```

When the call site passes those arguments by keyword, `len(args)` is 0, the whole
block is skipped, and `func` runs with **no permission check at all**. There is no
warning and no error — the decorated function looks entirely correct at both the
definition and the call site.

Demonstrated with a decorated stub called both ways:

```
keyword call    -> SERVICE BODY RAN                  permission_func invocations: []
positional call -> InsufficientPermissions raised    permission_func invocations: ['CHECK RAN']
```

### Current exposure: none, by luck rather than design

An AST audit of every `@require_assembly_permission`-decorated function and every
call site under `src/opendlp/` finds **17 decorated services** and exactly **two**
call sites that pass fewer than three positional arguments — both of them
`check_db_selection_data` (`service_layer/sortition.py:426`, guarded by
`can_manage_assembly`):

| Call site | Route's own gate |
| --- | --- |
| `entrypoints/blueprints/db_selection_backoffice.py:62` | `@require_assembly_management` |
| `entrypoints/blueprints/db_selection_legacy.py:150` | `@require_assembly_management` |

Both routes carry an independent `@require_assembly_management` decorator, so the
skipped service-layer check changes nothing today. **There is no live privilege
escalation.** What there is: a guard that silently does nothing at two call sites,
where the only thing standing between a user and an unauthorised action is a second
check that nobody knows is load-bearing.

### Why it still needs fixing

- It is invisible. A reviewer reading either the service or the call site sees a
  permission check that is not running.
- It is one keyword away. Any new decorated service, or any refactor that switches
  a call to keyword arguments for readability, silently disables enforcement.
- The 886 plan had to spend a paragraph warning implementers about it
  ([../886-dashboard/service_layer_plan.md](../886-dashboard/service_layer_plan.md),
  §2 "Permissions — two traps") and require a negative test per service to prove
  the decorator fires. That is a workaround for a decorator that should simply not
  have this failure mode.

### Suggested fix

Bind the arguments against the real signature instead of indexing `args`, and
**raise** rather than pass when the three cannot be found:

```python
bound = inspect.signature(func).bind(*args, **kwargs)
bound.apply_defaults()
# then read bound.arguments["uow"], ["user_id"], ["assembly_id"],
# raising a clear error if any is missing
```

That makes keyword and positional calls behave identically and turns a silent
bypass into a loud failure at the first call.

## Related, worth folding into the same ticket

**Two patterns for the same job.** `assembly_service.update_assembly`
(`assembly_service.py:82`) is *not* decorated — it repeats the
`uow.users.get` / `uow.assemblies.get` / `can_manage_assembly` sequence inline in
its body (lines 104-116). It is correct, but it means there are two ways a service
enforces assembly permissions, and a reader cannot tell which applies without
opening the function.

**An argument-order landmine.** That same function's signature is
`update_assembly(uow, assembly_id, user_id, **updates)` — `assembly_id` and
`user_id` in the *opposite* order to the `(uow, user_id, assembly_id)` convention
the decorator assumes. If anyone ever "tidies" it by adding the decorator, the
check will silently run with the two UUIDs swapped, looking up an assembly by a
user id. Either reorder the parameters or make the decorator bind by name (which
the fix above does anyway).

**A redundant guard that is worth keeping.** `dashboard_stats.py:150` raises
`AssemblyNotFoundError` for a missing assembly, which is unreachable through the
public services because the decorator raises first — it shows up as the single
uncovered line in that module. It is exactly the guard you would want if the
decorator were ever bypassed, so it should stay; noting it here so a coverage
sweep does not delete it.
