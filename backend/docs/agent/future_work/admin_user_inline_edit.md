# Edit a user in place on the Site Admin user page

Deferred from `1206-admin-backoffice-style`. That branch moved the Site Admin
pages to the backoffice design system and kept a separate "Edit user" page
(`/admin/users/<id>/edit`, `templates/admin/user_edit.html`) for the first name,
last name and global role. Written to be pasted into an issue.

## What it would be

The user page (`/admin/users/<id>`) edits its own values, as "My account" does:

- **First name and last name** in place with `inline_edit_row`
  (`backoffice/components/inline_edit_row.html`), each posting to a small route
  that returns the row for htmx to swap in. See `backoffice/profile/_name_row.html`
  and the profile blueprint for the pattern, including the no-JavaScript
  fallback where a refused value comes back open with its error.
- **Global role** in a dialog opened from the role row, with the role radios and
  Save / Cancel, since a role change is weightier than a name.
- The edit page and its route go, or redirect to the user page.

## Things to keep

- An admin cannot change their own role. The role row shows no edit control for
  yourself, and the route still refuses it.
- Email cannot be changed; its row stays read-only.
- Whether the account is active stays with the Disable / Enable account
  buttons and their confirm dialogs.

## Tests

Component tests for each row route (save, refuse, no-JavaScript fallback) and
for refusing your own role change; a BDD scenario that edits a name and a role
in the browser.
