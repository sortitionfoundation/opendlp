# Future work: a reused BDD server can be missing feature flags, and nothing says so

Spotted while working on sc-1024 (2026-11-18). Written to be pasted into an
issue.

## Problem

The BDD fixture (`test_server` in `tests/bdd/conftest.py`) reuses a server it
finds on port 5002 rather than starting one. A server started by hand with
`just flask-bdd` does not have the feature flags the suite needs, the fixture
does not notice, and seven scenarios fail with a 404 that looks like a bug in
the application:

| Scenarios | Route | Flag it needs |
| --- | --- | --- |
| `test_backoffice.py`: the three thank-you page scenarios | `/register/<slug>/thank-you` | `FF_REGISTRATION_PAGE` |
| `test_backoffice.py`: the four image scenarios in the visual editor | the public image route | `FF_REGISTRATION_PAGE` |

Stopping the hand-started server and re-running made them all pass, with no
change to the code. (When this was written two more scenarios failed the same
way, for want of the legacy dashboard's flags; that page and its flags have
since been deleted.)

## Why the flags differ

A server the fixture starts gets them from two places:

- any flag in `TEST_FEATURE_FLAGS` in `tests/conftest.py` (empty at present)
  is set in the pytest process, and the fixture hands its environment on
  (`env = os.environ.copy()`);
- `FF_REGISTRATION_PAGE` is pinned by the fixture itself.

The `flask-bdd` recipe in the `justfile` sets `FLASK_APP`, `DB_PORT`,
`REDIS_PORT`, `USE_CSV_DATA_SOURCE` and `FLASK_ENV`, and no flags. Its flags
are whatever the developer's `.env` says, which is usually nothing.

## Why the fixture does not notice

`_validate_existing_server` compares what `/health/bdd`
(`entrypoints/blueprints/health.py`) reports against what it expects, and
fails the run with "Kill the existing server and restart with: just flask-bdd"
on a mismatch. Two gaps:

1. **`/health/bdd` reports no feature flags**, so there is nothing to compare.
2. **The age check does not work with `--debug`.** It refuses a server that
   has been running more than 24 hours, measured from `_PROCESS_STARTED_AT`.
   `flask-bdd` runs with `--debug`, whose reloader starts a fresh child
   process on every file change, resetting that time. The server that caused
   this had been up for a week and reported `running_hours: 0.8`.

## Suggested fix

1. Set the flags in the `flask-bdd` recipe, beside the other inline
   variables, so a hand-started server matches a fixture-started one.
2. Have `/health/bdd` report the flags the suite depends on. One list should
   say which those are, read by the recipe's documentation, the endpoint and
   the fixture alike - `TEST_FEATURE_FLAGS` plus `FF_REGISTRATION_PAGE` - so
   that adding a flag to the suite cannot leave one of the three behind.
3. Have `_validate_existing_server` add a line to its existing list of
   problems for each flag that is off. The message it already prints is the
   right one.
4. Optionally, make the age check survive the reloader: the reloader's parent
   process outlives its children, so the parent's start time (or a timestamp
   in an environment variable set once at launch) measures what the check
   means to measure.

Steps 1-3 are small. Step 4 is separate and less pressing once 3 is in: a
stale server with the right configuration is mostly harmless, since `--debug`
reloads the code.

## Until then

If BDD scenarios fail with a 404 on a page you have not touched, look for a
server on port 5002 that you started yourself (`ps -ef | grep "flask run"`),
stop it, and run again.
