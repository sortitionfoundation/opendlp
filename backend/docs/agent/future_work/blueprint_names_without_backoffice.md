# Future work: blueprint names that still carry a "backoffice" qualifier

Left over from sc-1341, retiring the legacy signed-in pages (2026-11-25).
Written to be pasted into an issue.

## Problem

While the legacy pages existed, a blueprint's name said which generation it
belonged to: `db_selection_legacy` beside `db_selection_backoffice`. The legacy
blueprints are gone, so the qualifier now distinguishes a blueprint from
nothing.

| Blueprint | Module | `url_for` references | Test patch targets |
| --- | --- | --- | --- |
| `db_selection_backoffice` | `blueprints/db_selection_backoffice.py` | 12 | 11 |
| `backoffice_registration` | `blueprints/backoffice_registration.py` | 47 | 16 |
| `backoffice` | `blueprints/backoffice.py` | 167 | 4 |

Counts are across `src/`, `templates/` and `tests/`, taken on 2026-11-25.

## What to do

- **`db_selection_backoffice` → `db_selection`.** Already part of the plan for
  splitting the selection blueprints
  (`docs/agent/1341-retire-legacy-routes/plan.md`, section 7), so it needs
  nothing more here.
- **`backoffice_registration` → `registration_editor`** or similar. It cannot
  simply drop the qualifier: `registration` is taken by the public
  registration pages (`blueprints/registration.py`), which are a different
  thing for a different audience. The new name has to say "the organiser's
  side".
- **`backoffice`**: leave. It is not a qualifier here, it is what the blueprint
  is: the dashboard, the project page and the pages that have not been given a
  home of their own. Renaming 167 references buys nothing. Moving its
  remaining members routes and leftover redirects out is a separate question.

## What a rename moves

- every `url_for("<blueprint>.<endpoint>")` in Python and in templates;
- every `patch("opendlp.entrypoints.blueprints.<module>.<name>")` in the
  tests. A patch aimed at a module that only re-exports a name does not
  intercept the call, so each moved test has to be run, not just imported;
- test file names that follow the blueprint
  (`tests/component/test_db_selection_backoffice.py`,
  `tests/e2e/test_db_selection_backoffice.py`);
- the blueprint tables in [docs/architecture.md](../../architecture.md).

URLs do not change, so nothing outside the repository is affected.
