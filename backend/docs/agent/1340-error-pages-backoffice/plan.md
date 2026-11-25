# 1340 — The error pages on the backoffice design

Status: **implemented**, on `1340-error-pages-backoffice`. The error pages in
`templates/errors/` (400, 403, 404, 413 and 500) used the GOV.UK `base.html`,
with Bootstrap markup that nothing on the site styles any more. They move to
the backoffice design system.

## 1. Decisions

- **Layout:** the public layout, `public/base.html`, which the sign-in and
  home pages use: the logo and help header, a centred narrow column and the
  footer. Whoever meets an error page may not be signed in, so it has no
  account menu.
- **One layout for all five:** `errors/base.html`. A page sets its title
  block, which is its heading as well as its browser title, and its message;
  403 and 500 set a support line as well. The heading block is the public
  pages' `page_heading`, as on the sign-in page.
- **The way back:** a full-width primary button, **Your projects** for a
  signed-in user and **Go to the home page** for anyone else.
- **Support contact:** on the 403 and 500 pages, which were the two that told
  the reader to contact an administrator. It links the support address
  (`SUPPORT_EMAIL`), as the sign-up page does.
- **No status code on the page.** The old pages printed 404 and the rest in
  large type. The heading now says what happened in words; the HTTP status
  codes are unchanged.
- **Where the templates live:** they stay in `templates/errors/`, and
  `tailwind.config.js` scans that folder as it scans `templates/public/`.
  Moving them into `templates/public/`, as the account pages were moved, would
  have meant changing the fifteen routes in the legacy blueprints (`main.py`,
  `gsheets_legacy.py`, `admin.py`) that render `errors/500.html` themselves.
- **The 2026-10-08 decision reversed.** The public pages redesign had kept the
  error pages on GOV.UK because respondents see them
  (`docs/agent/public-pages-redesign/plan.md`). Story sc-1340 moves them.

### Wording

Sentence case, after `docs/language.md`: "Your projects" is the name of the
link, and "we" is allowed on an error page.

| Page | Heading | Message |
| --- | --- | --- |
| 400 | The form has expired | The old message, unchanged: open too long or not verified; go back, reload and try again |
| 403 | You don't have access to this page | Your account doesn't have the role this page needs; support line |
| 404 | Page not found | Check the web address is correct; if you followed a link, the page may have been moved or deleted |
| 413 | The file is too large | The file is larger than OpenDLP accepts; try a smaller one |
| 500 | Sorry, something went wrong | The problem is on our end; try again in a few minutes; support line |

The 400 page is the CSRF error's page: it is the only 400 with a handler, so a
plain `abort(400)` still gets Werkzeug's own page, as before.

The 413 page no longer names a limit. It said 10 MB, but the request limit,
`MAX_CONTENT_LENGTH`, is the largest of the upload limits (50 MB by default),
and each upload route checks its own tighter limit before that.

## 2. The 500 page and the database

The 500 page has to render when the database is what failed. The old one did
not, for a signed-in visitor: the page itself reads nothing from the database,
but Flask-Login loads the signed-in user from it the first time anything in
the request asks for `current_user`, and rendering asks — Flask-Login's own
context processor, `inject_capabilities`, the locale selector (for a
`preferred_language` that users do not have) and the page. When the user
could not be loaded, rendering failed the same way, the 500 handler raised,
and the visitor got the server's bare error.

`render_server_error_page()` in `flask_app.py` settles the user first: it
loads the user, and if that fails it puts the request on an anonymous user,
as Flask-Login does when nobody is signed in, through
`login_manager._update_request_context_with_user()`. That is a Flask-Login
internal, and `test_the_page_renders_when_the_database_is_down` pins it. The
page then offers what it offers a visitor who is not signed in, and nothing
later in the request — the after-request handlers included — tries the
database again.

The fifteen legacy routes that render `errors/500.html` themselves are
unchanged: they are behind `login_required`, which has loaded the user before
they fail.

## 3. What a registration visitor sees

A missing page under `/register/…` or `/r/…` gets the same 404 page as any
other address, in the backoffice design.

## 4. Tests

- `tests/component/test_error_pages.py`: each status renders its page on the
  public layout with no GOV.UK markup (the 403 through a non-admin on Site
  Admin, the 413 through a lowered `MAX_CONTENT_LENGTH`, the 400 through a
  login post without a CSRF token); the way back for a signed-in user and for
  anyone else, and the support line, on each of the five; the 500 page through
  an app with a failing route, signed out, signed in, with the database down,
  and with a flashed message.
- `tests/unit/test_flask_app.py`: the 404 and CSRF checks follow the new
  wording.
- `tests/component/test_legacy_header.py` checks the GOV.UK header's Your
  projects link on `base.html` itself, as no error page uses that header now.

## 5. Not in this change

- The public footer's row of links is wider than a phone screen on every
  public page, the sign-in page included, so those pages scroll sideways at
  390px.
- The legacy routes' own 500 responses still go through `render_template()`
  (see section 2).
