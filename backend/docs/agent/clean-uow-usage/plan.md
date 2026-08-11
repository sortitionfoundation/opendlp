# Plan: move the UnitOfWork context up to the entrypoints

The work. For why, and for where every figure here comes from, see
[research.md](research.md).

**The rule we are moving to:** only entrypoints - Flask routes, CLI commands,
Celery tasks - open `with uow:`. Everything below the entrypoint assumes an open
context and never opens its own.

**Scale:** 152 functions to convert, 36 production call sites, ~899 service calls
and ~585 bare repository accesses in 49 test files. Roughly 26 commits across
4 phases.

**Constraint:** `just check` and the full test suite pass at every commit.

**These figures are a snapshot and will drift.** Between first drafting this plan
and rebasing on main, the multiple-registration-pages work added 6 self-managing
service functions and 99 test call sites, and `registration_page_service.py` went
from the third-largest slice to the largest. Re-run the appendix scanners in
research.md before starting a slice rather than trusting the table. This drift is
the case for phase 0.4's allowlist: it is the only mechanism here that stops the
problem growing faster than the migration shrinks it.

## How every commit stays green

Four properties make this possible. They are worth understanding before starting,
because each phase depends on them.

1. **Nesting still works during the migration.** Today's `__exit__` commits and
   closes, and the closed Session silently resurrects on next use. That is the
   bug we are fixing - but until it is fixed it means wrapping a call to a
   not-yet-converted function in `with uow:` is harmless. So call sites can be
   corrected ahead of the functions they call.
2. **Converting a function whose callers already have a block needs no call-site
   change.** Most self-managing service functions are already called from inside
   a route's `with uow:`. Those conversions are one-sided.
3. **Bare `uow.<repo>` access in tests does not break during phase 1.** It only
   breaks when `FakeUnitOfWork` goes strict, which is phase 3. So phase 1 only
   has to fix the ~899 *service call* sites, not the ~585 repository accesses -
   and adopting the `uow` fixture fixes both at once anyway.
4. **The strict guards land last**, when nothing violates them.

The one thing that must be atomic is a slice: converting a function, fixing its
production callers, and migrating its tests all belong in the same commit.

## Phase 0 - groundwork

Four commits, no behaviour change, nothing depends on them being done together.

### 0.1 Narrow the exception handling around service calls

Replace `contextlib.suppress(Exception)` and bare `except Exception` around
service calls with the specific domain exceptions (`NotFoundError` and friends).
Sites are listed in research.md under "Exception handling around service calls":
`respondents.py`, `respondent_field_schema.py`, `gsheets.py`, and `_can_manage`
in `targets.py`.

Do this **first**. After phase 1 these run inside the caller's transaction, where
a swallowed database error leaves the transaction poisoned for every statement
that follows. Today they are merely hiding errors; later they would corrupt.

### 0.2 Add the `uow` fixtures

Add to `tests/conftest.py`:

```python
@pytest.fixture
def uow():
    """An already-entered fake UnitOfWork, so tests need no `with` block."""
    with FakeUnitOfWork(strict=True) as u:
        yield u
```

Plus a shared-store variant for component tests, and a SQL-backed equivalent for
integration tests that only need one UnitOfWork.

Nothing uses them yet, so this commit is green by construction.

### 0.3 Add `strict` to `FakeUnitOfWork`, defaulting to off

`strict=True` makes the fake mirror the real UnitOfWork: `__enter__` marks the
context open, `__exit__` marks it closed and swaps each repository for a
placeholder that raises. The `fake_<name>` aliases stay usable outside a block as
the deliberate arrange/inspect seam.

Default `strict=False`, so every existing test is unaffected. Add unit tests for
the strict behaviour itself.

### 0.4 Add the convention checker with a shrinking allowlist

`scripts/check_uow_convention.py`, wired into `just check`. It fails if a
function in `service_layer/` opens `with uow:` **and is not listed** in
`docs/agent/clean-uow-usage/known_self_managing.txt`.

Seed the allowlist with today's 130 service-layer offenders, so the commit is
green immediately. From this point CI blocks *new* offenders while the known ones
shrink slice by slice - the allowlist is the migration's progress bar, and
phase 3 deletes it.

Base the checker on the appendix script in research.md, and note its two blind
spots recorded there.

## Phase 1 - convert the service layer, slice by slice

One commit per slice. Order is: pilot first to establish the pattern, then
`assembly_service.py` because it holds `get_assembly_with_permissions` and
converting it removes most of the nesting in the codebase, then descending by
test-call count.

| # | Module | Fns | Test calls | Test files |
|---|---|---|---|---|
| 1 | `email_send_service.py` **(pilot)** | 2 | 19 | 3 |
| 2 | `assembly_service.py` | 25 | 156 | 9 |
| 3 | `registration_page_service.py` | 22 | 242 | 3 |
| 4 | `user_service.py` | 18 | 86 | 7 |
| 5 | `respondent_service.py` | 11 | 82 | 5 |
| 6 | `respondent_field_schema_service.py` | 11 | 80 | 3 |
| 7 | `registration_document_service.py` | 5 | 34 | 1 |
| 8 | `registration_image_service.py` | 5 | 33 | 1 |
| 9 | `email_template_service.py` | 7 | 30 | 1 |
| 10 | `invite_service.py` | 7 | 29 | 3 |
| 11 | `email_confirmation_service.py` | 4 | 29 | 4 |
| 12 | `password_reset_service.py` | 5 | 28 | 2 |
| 13 | `registration_submission_service.py` | 2 | 27 | 4 |
| 14 | `two_factor_service.py` | 6 | 24 | 3 |

Totals: 130 functions, 899 test calls - the whole service layer.

Slices 2 and 3 are large enough to split into two or three commits each, by
group of related functions. Slice 3 is now the largest in the list and should
definitely be split. A partial slice is still green, provided the commit
converts a function together with all its callers and tests.

### The per-slice recipe

1. Remove `with uow:` from each function in the module.
2. Drop the internal `uow.commit()` where the caller's block now owns the commit.
   Keep it where the function deliberately commits mid-sequence, converting those
   to `commit_and_reset()`.
3. Update each docstring to say the caller manages the context. Reuse the
   existing wording: "The caller is expected to manage the `uow` context
   (`with uow: ...`)".
4. Fix production call sites - wrap in the caller's existing block, or open one at
   the entrypoint. Keep the block off `render_template` and external I/O.
5. Migrate the module's test files to the `uow` fixture: delete the
   `uow = FakeUnitOfWork()` line, add `uow` as a test parameter. **Do not** wrap
   test bodies in a `with` block; that re-indents everything and makes the diff
   unreadable.
6. Delete the module's entries from `known_self_managing.txt`.
7. `just check && just test`.

### The 75 tests that need hand migration

42 e2e and 33 integration tests construct **two or more** `SqlAlchemyUnitOfWork`
instances in a single test. They do that to prove data committed by the first is
visible to a fresh session.

Giving those the fixture would collapse them into one transaction and leave them
asserting nothing **while still passing**. Migrate them by hand, keeping the
explicit second block. When a slice touches one, say so in the commit message.

## Phase 2 - entrypoint helpers

Two commits. Same rule, applied above the service layer.

### 2.1 `blueprints/dev.py`

5 routes, 25 `_handle_*` helpers (20 self-managing, 5 already conforming). Every
handler is dispatched from `_execute_service`, which builds the uow and calls
`handler(uow, params)`. So the whole module is one `with uow:` around that call
plus 20 removals.

Changes behaviour: each handler currently commits independently, afterwards there
is one transaction per request. Fine for a dev-only tool.

### 2.2 `blueprints/auth.py` helpers

`_verify_2fa_code_for_user` and `_complete_2fa_login` move their blocks up into
`verify_2fa`, which already has three of its own - so this also collapses that
route's block count.

## Phase 3 - enforce

Four commits, in this order. Each is only green because everything before it is
done.

### 3.1 Make `SqlAlchemyUnitOfWork` strict

- `session` raises if the context is not open.
- `__exit__` uses `try/finally`, so a failing commit still releases the
  connection.
- `__exit__` clears `self._session`, so a closed Session can never be
  resurrected.
- `__exit__` swaps each repository for a placeholder that raises. Repositories
  hold their own session reference, so guarding only the `session` property would
  miss `uow.users.get(...)` after the block.

Use `setattr` with names read off `AbstractUnitOfWork.__annotations__`, not a
`__getattr__` on the UnitOfWork - a `__getattr__` makes mypy accept any attribute
name and loses typo detection across the codebase.

This commit is where the original leak actually dies.

### 3.2 Make `FakeUnitOfWork` strict by default

Flip the default, delete the `strict` flag, and migrate any test still
constructing a loose fake. This is where the ~585 bare repository accesses must
all be inside a block or switched to the `fake_<name>` aliases.

### 3.3 Delete the allowlist

`known_self_managing.txt` should be empty by now. Delete it and the checker's
allowlist logic, so the rule is absolute.

### 3.4 Write the convention down

- `docs/architecture.md` - the convention, and why it departs from *Architecture
  Patterns with Python*. This is what the code-review skill's
  "Review `docs/architecture`" bullet resolves to.
- `CLAUDE.md` - a short entry under "Development Patterns" pointing at it.
- `.claude/skills/sf-code-review/SKILL.md` - a "Things to Check" bullet covering
  the judgement calls the checker cannot make. Do not restate the checker; that
  skill's "Do NOT report" section excludes anything CI already enforces. See
  research.md for the four questions worth giving a reviewer.

## Phase 4 - follow-ups

Separate pieces of work, unblocked by the above but not part of it. Details in
research.md.

- **Read-only workstream.** 64 of 87 GET routes never write, and 75% of the
  service layer is read-only. An AUTOCOMMIT read-only UnitOfWork would make this
  whole class of failure structurally impossible on those paths. Blocked on the
  23 routes that write on a GET. This is the highest-value follow-up.
- **Three pre-existing test warnings** now visible since runs reach their summary.
- **`teardown_appcontext` backstop** for `bootstrap.get_flask_uow()`.

## If a commit cannot be green

Do not weaken a guard or skip a test to get past it. Either the slice is too
large - split it by function group - or the call site needs a judgement call
about transaction boundaries that should be raised rather than guessed. Stop and
ask.

The one failure mode to watch for is a test that goes green for the wrong reason:
a multi-UnitOfWork test collapsed into one transaction still passes, but has
stopped testing anything. Any commit touching those 75 tests deserves a careful
second look.
