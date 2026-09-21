# Future work arising from `793-two-step-fields`

Things the review of this branch turned up that are worth doing, but not on this
branch. Each section is written to be pasted into an issue.

## App-level handlers for `InsufficientPermissions` and `NotFoundError`

### Problem

`flask_app.py` registers error handlers for 404, 500, 403, 413 and CSRF only. A
service-layer `InsufficientPermissions` or `NotFoundError` that a route does not
catch becomes a 500, with a traceback in the logs and the generic error page for
the user - for what is an ordinary "you can't see that" or "that's gone".

Every route is therefore expected to catch both itself, and the blueprints hold
roughly 207 `except InsufficientPermissions` clauses and 243 not-found ones.
Nearly all do the same thing: flash a message and redirect to the dashboard. The
convention holds only as long as nobody forgets, and it is easy to forget in ways
that pass review:

- a service call placed just *before* the `try` (`recompute_view` and
  `upload_view` in `target_sources.py` called `_linked_field_id()` there);
- work done *inside* an `except` handler that can itself raise (`configure_view`
  re-rendered its modal from the handler, which re-ran the permission check);
- a route that catches `NotFoundError` for the thing it is about and so swallows
  `AssemblyNotFoundError` into the wrong message (`unlink_view`).

All three were on `793-two-step-fields`, all were found by review rather than by
a test, and all were fixed locally. Nothing stops the next one.

### Proposal

Register two app-level handlers as a **safety net**. Routes keep their local
catches - those carry the route-specific message and destination - and the
handlers only see what a route missed.

For both:

- log through `structlog` at `warning` with `user_id`, the endpoint and the
  exception class (never the message for `NotFoundError` - it carries UUIDs, and
  never an email). Reaching the handler means a route forgot a case; it should be
  visible, but it is not an error;
- choose the response by the kind of request:
  - **ordinary backoffice request** - flash and redirect to
    `backoffice.dashboard`, matching what the routes do by hand;
  - **HTMX request** (`HX-Request: true`) - an empty response with an
    `HX-Redirect` header. A plain 302 is followed by htmx and the dashboard HTML
    is swapped into whatever fragment container made the request;
  - **JSON route** - the standard error body from
    `docs/agent/json_api_conventions.md`, with 403 or 404;
  - **public pages** (registration pages and anything else outside the
    backoffice) - the 403 / 404 error page. Bouncing a member of the public to a
    backoffice dashboard they cannot sign in to is worse than a 404.

Messages: `exc.user_msg()` for `InsufficientPermissions` (it mixes in
`CuratedMessage`); a literal `_("Not found")` for `NotFoundError`, which is
uncurated and must not have its message shown.

### Explicitly not proposed

- **A handler for `ServiceLayerError`.** It spans everything from
  `PasswordTooWeak` to `TargetLinkedError`, most of it uncurated, so the only
  possible response is a generic message - which is what the 500 page already
  is. A handler would turn bugs into a polite flash with no traceback and nothing
  in error monitoring: the "blanket catch turns a bug into a plausible-looking
  error message" failure, moved to the app level.
- **Deleting the ~450 local catches.** With the net in place many become
  redundant, but removing them is a large, separate, optional change, and the
  ones carrying a route-specific message or destination should stay.

### Open questions

- How does the handler know a request is a JSON one? By blueprint is probably the
  most reliable; `request.accept_mimetypes` is not, since `fetch` callers are not
  consistent about it.
- How does it know a request is a public one? Again probably by blueprint - which
  suggests a small registry (`blueprint name -> response style`) rather than
  conditionals in the handler.
- Do the existing local catches in HTMX fragment routes have the 302-into-a-
  fragment problem already? `_dashboard_redirect` in `target_sources.py` issues a
  plain redirect whether or not the request is HTMX, and so do its siblings in
  other blueprints. If so, a shared `dashboard_redirect()` helper that is
  HTMX-aware is part of this work, and the handlers should use it.

### Tests

- Component: a throwaway route registered in the test app that raises each
  exception, exercised as an ordinary, an HTMX, a JSON and a public request.
- Component: the log line is emitted at `warning`, with `user_id` and without the
  exception message.
- The per-blueprint "no route answers a refusal with a 500" parametrised test in
  `tests/component/test_backoffice_target_sources.py`
  (`TestRoutesTurnAwayThoseWithoutAccess`) is cheap and found real bugs. Worth
  generalising: walk `app.url_map` for every rule taking an `assembly_id`, call
  it as a user with no role and with an unknown assembly, and assert the status
  is never 500.

### Why not on `793-two-step-fields`

It changes behaviour on every blueprint in the application, and that branch is
already a 9.4k-line diff. Landed on its own it is a twenty-line commit that
`git bisect` can point at if a public 404 starts redirecting somewhere odd.
