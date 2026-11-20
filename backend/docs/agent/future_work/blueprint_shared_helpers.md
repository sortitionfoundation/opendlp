# Pull the repeated blueprint helpers into one module

Turned up by a sweep of `src/opendlp/entrypoints/blueprints/` for small private
helpers that are copied from file to file. Written to be pasted into an issue.

## Problem

Several blueprints carry their own copy of the same few lines, usually near the
top of the file. The copies are identical today, but nothing keeps them that
way, and some routes skip the helper altogether and inline the logic, so a fix
to one copy does not reach the others.

## Findings, most worthwhile first

### 1. `_is_htmx()` - eight copies

```python
def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"
```

Defined, identically, in `data_source.py`, `db_selection_backoffice.py`,
`profile.py`, `project_details.py`, `respondent_field_schema.py`,
`target_sources.py`, `targets.py` and `targets_legacy.py` - about 70 call sites
between them. `gsheets.py:1143` inlines the same check (inverted) rather than
defining it.

### 2. The HTMX-aware redirect - three named copies, three inlined

```python
def _redirect(location: str) -> ResponseReturnValue:
    """Redirect, telling htmx to load the page rather than swap it into the dialog host."""
    if _is_htmx():
        response = make_response("", 200)
        response.headers["HX-Redirect"] = location
        return response
    return redirect(location)
```

- `data_source.py:90` as `_redirect`
- `profile.py:73` as `_redirect`
- `db_selection_backoffice.py:419` as `_settings_redirect` - same body, docstring
  and all; the name is the only "settings" thing about it.

The same branch is written out inline in:

- `respondent_field_schema.py:772` (`_target_sources_redirect`)
- `targets_legacy.py:368` (delete of a linked target)
- `gsheets_legacy.py:782` (always HTMX there, so only the header half)

This is the one with real risk. A plain 302 in answer to an HTMX request is
followed by htmx and the whole target page is swapped into the fragment that
asked - the bug every one of these copies exists to avoid. A route that forgets
reintroduces it, and review is the only thing that catches it. One shared
`htmx_redirect(location)` makes the right thing the obvious thing to reach for.

### 3. The out-of-band floating alerts snippet - two places

```python
'{% from "backoffice/components/floating_alerts.html" import floating_alerts %}'
"{{ floating_alerts(oob=true) }}"
```

`profile.py:57` and `:65` (as part of `_NAME_ROW_RESPONSE` and
`_DIALOG_CLOSED_RESPONSE`), and `target_sources.py:523` (`_toast_response`).
This is how an HTMX response that is not a full page carries a flash. A
`render_flashes_oob() -> str` helper would let a route append it without
knowing the macro's path. Low risk, small win; worth doing alongside 1 and 2
because the next HTMX dialog will need it too.

### 4. `_can_manage(assembly_id)` - two copies that have already drifted

`targets.py:91` and `targets_legacy.py:55` both load the user and the assembly
in their own UnitOfWork and call `can_manage_assembly`. The `targets_legacy.py`
copy wraps it in `except Exception: pass`, so any failure - a database error
included - reads as "cannot manage". `tests/e2e/test_service_error_propagation.py`
(`test_permission_check_failure_is_not_swallowed`) records that `targets.py`
had the same bug and was fixed; the legacy copy was not.

Two ways to go:

- **Leave both alone.** `targets_legacy.py` is on the list in
  [delete_legacy_pages.md](delete_legacy_pages.md), and the drift dies with it.
  Fix the swallowed exception in place if the legacy page is going to live a
  while.
- **Do not share it.** Other routes (`backoffice.py:113`, `gsheets.py:383`,
  `respondents.py:606`) call `can_manage_assembly` on an assembly they already
  loaded in the request's one UnitOfWork, which is the better pattern. A shared
  `_can_manage` would encourage the second-UnitOfWork version.

Recommendation: not a candidate for the shared module. Fix or delete the legacy
copy.

### 5. Refusals that go to the dashboard - covered elsewhere

`respondent_field_schema.py:88` (`_refusals_go_to_the_dashboard`, a decorator)
and `target_sources.py:551` (`_dashboard_redirect`) are local answers to "a
`NotFoundError` or `InsufficientPermissions` escaped". Both issue a plain
`redirect()` whether or not the request is HTMX. This belongs to
[app_level_error_handlers.md](app_level_error_handlers.md), whose open
questions already ask for an HTMX-aware `dashboard_redirect()` - which would be
built on the `htmx_redirect` from item 2. Do item 2 first; leave these to that
issue.

## Looked at and not worth moving

- **The Google Sheets export runners** (`_run_gsheet_export` in `respondents.py`
  and `targets.py`, `_run_dashboard_gsheet_export` in `backoffice.py`) look
  alike but are already thin wrappers over the shared `run_gsheet_export_flow`
  in `entrypoints/gsheet_export_flow.py`. What is left differs per caller.
- **`_details_url`** in `data_source.py` and `project_details.py` both build
  `backoffice.view_assembly`, but with different arguments (query params vs the
  `#team` anchor). `entrypoints/data_source_urls.py` already holds the one that
  is shared. A two-line wrapper over `url_for` gains nothing.
- **`HX-Refresh` when a task finishes** - four copies of the same three lines in
  the progress routes of `db_selection_legacy.py` and `gsheets_legacy.py`. Real
  duplication, but all in legacy pages due for deletion.
- **`_parse_comma_list`** (`db_selection_legacy.py:460`) and its inline twin at
  `db_selection_backoffice.py:498`. Legacy again; the backoffice one could call a
  shared helper, but it is one line.
- **`dev.py`'s `_handle_*` functions** - many, but each is one dev service, not a
  copy of another.

## Proposal

A new module for items 1-3. Two candidate homes:

- `entrypoints/htmx.py` (recommended) - sits beside `scroll_utils.py`,
  `data_source_urls.py` and `decorators.py`, which are the existing pattern for
  "small helpers routes share", and the name says what is in it.
- `entrypoints/blueprints/helpers.py` - closer to the callers, but a module
  called `helpers` tends to become the place everything goes that has no better
  home.

Contents:

```python
def is_htmx() -> bool: ...
def htmx_redirect(location: str) -> ResponseReturnValue: ...
def render_flashes_oob() -> str: ...
```

Then, file by file, delete the local copy and import the shared one, and
replace the inlined versions in `respondent_field_schema.py`, `gsheets.py`, and
(if not deleted first) `targets_legacy.py` and `gsheets_legacy.py`.

`_settings_redirect` should go entirely - its name implies something
settings-specific that is not there. `_settings_return_url` beside it is
genuinely settings-specific and stays.

## Tests

- Unit: `is_htmx` is true only for `HX-Request: true` (not for a missing
  header, not for `false`), in a `test_request_context`.
- Unit: `htmx_redirect` gives a 200 with `HX-Redirect` and an empty body for an
  HTMX request, and a 302 with `Location` otherwise.
- Unit: `render_flashes_oob` renders a flashed message with the out-of-band
  attribute, and nothing visible when there is no flash.
- The existing component tests over the routes that use these (data source
  dialog, profile, selection settings dialog, schema editor) already assert the
  `HX-Redirect` behaviour and should pass unchanged - that is the check that the
  move changed nothing.

## Watch out for

- Tests that `patch()` a name in a blueprint module stop working if that name
  moves. None patch the helpers above today; check again before starting.
- This is a pure refactor across up to ten blueprints. Keep it on its own
  branch, one commit per helper, so a regression bisects to one helper rather
  than to "the refactor".
