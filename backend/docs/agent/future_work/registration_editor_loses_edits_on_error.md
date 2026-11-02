# The registration editor throws away unsaved edits when a save fails

## Background

Found while planning 1220 (reply-to for the auto-reply email). See
[`1220-reply-to/plan.md`](../1220-reply-to/plan.md), Q8. We accepted it for that
round and noted it here.

## What happens

Every step of the registration editor handles a failed save the same way. It
flashes the error and **redirects** back to the step in edit mode. A redirect is a
fresh GET, so the step re-renders from what's in the database, and everything the
manager typed is gone.

- **Auto-reply email step:** `save_assembly_registration_email`
  (`entrypoints/blueprints/backoffice_registration.py`, the
  `except EmailTemplateInvalid` branch) redirects to
  `_email_section_url(..., edit=True)`. A missing subject, a template syntax error
  or an over-size body loses the subject, the body and (after 1220) the
  "Replies go to" fields.
- **Page, intro and form steps:** `save_assembly_registration` builds
  `error_redirect_url` with `edit="1"` and redirects there on
  `RegistrationPageNotReady` and `ValueError`, for example a bad slug or a duplicate
  name. A long intro or form-HTML edit is lost the same way.

The flash message tells the manager what was wrong. They then have to make all
their changes again, not just fix the one field.

1220 makes the email step easier to trip, because it adds a free-text email address
that can fail validation. The input's `type="email"` catches the common typo in the
browser, so the server-side rejection is a backstop. But it still costs the
manager their body edit when it fires.

## Possible fixes

1. **Re-render instead of redirecting on a validation failure.** Render the step
   template directly with the posted values and the problems (a `200` with errors,
   or a `422`), rather than redirecting. This is the usual pattern for form
   errors. The complication is that the editor's view function
   (`view_registration_page`) assembles a lot of context for every step. That
   would need pulling out into a helper the save routes can call with
   "values from the form" overrides. The rich-text editors (intro and email body)
   need to start from the posted HTML, which they should, since they read the
   textarea's value.
2. **Stash the posted values in the session across the redirect.** Keep
   post/redirect/get, and have the GET prefer the stashed values once. This is less
   restructuring, but the stash can hold large HTML and, for the form step,
   anything the manager pasted. Session storage is Redis, so that's acceptable,
   but it adds a second source of truth for what the editor shows.
3. **Client-side validation for the common cases** (required fields, email format,
   body size). This reduces how often the problem happens but doesn't fix it.
   Template syntax errors and server-only checks (slug uniqueness) still get
   through.

I'd lean towards 1, done one step at a time, starting with the email step: it has
the smallest context and the most validation.

## Tests that would show it fixed

- Component: post an invalid save to each step and assert the response contains the
  posted values, not the stored ones, along with the error.
- BDD: edit the auto-reply body, enter a bad reply-to address that gets past the
  browser check (or blank the subject by script), save, and see the error with the
  body edit still in place.
