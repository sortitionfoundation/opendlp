# 869 — My account: names edited in place, Change password in a dialog

Shortcut [sc-869](https://app.shortcut.com/sortitionfoundation/story/869), the
follow-up to the move of the profile pages onto the backoffice design
(`../869-profile-backoffice/plan.md`, PR #400). Two changes to My account
(`/profile`):

1. The first and last name are edited where they are shown, in the pattern of
   the project details design in the OpenDLP - UI Figma file: node 6025-7120 at
   rest, 6676-15096 editing. The separate Edit profile page is gone.
2. Change password opens in a dialog over My account instead of a page of its
   own.

Two-factor authentication is unchanged; its flow is a separate question. Set
password, for an account that signs in with Google or Microsoft only, stays a
page of its own.

## The design, and what the codebase had

At rest the row shows the value with a pencil at its end. The pencil turns the
value into a field and itself into a green tick. The design's note on the
flow: the input is saved on a click on the tick, on Enter, or on a click outside
the field.

Nothing in the codebase edited a value in place, so the row is built from the
design system's parts: `input()` for the field, `button(variant="icon")` for
the pencil and the tick, `icon_check` in `--color-success-text`, and
`icon_pencil`, Lucide's pencil from the Icons sheet (node 5032:10151), added to
`icons.html` and the icons showcase. `icon_edit` is Lucide's square-pen, a
pencil over a square; the design draws the plain pencil.

Two departures from the design, both small:

- **Escape puts the stored value back.** The design shows no way back; Escape is
  the keyboard's undo, and it returns focus to the pencil.
- **The row keeps the page's geometry.** The design sets a 112px label column
  and 40px rows; My account's other rows have a 192px label column and
  dividers, so the two name rows follow them. The text at rest takes the
  field's height, so opening a name moves nothing.

## How the names are saved

`templates/backoffice/profile/_name_row.html`, `src/js/components/inline-edit.js`.

- Each row is a form posting its own field to `profile.edit` (`POST
  /profile/edit`, `field=first_name` or `last_name`). The other name keeps its
  stored value.
- htmx sends the form on the component's `inline-edit-save` event rather than on
  submit, so a value that has not changed is never sent, and swaps the answer
  in for the row:
  - **200**: the row at rest with the saved name, and the success flash
    appended out of band to the page's floating alerts;
  - **422**: the row still open, the field focused, the reason under it
    (`aria-invalid`, `aria-describedby`), the refused value in the field and the
    stored one kept apart for Escape.
- **Focus.** A save made from inside the row (the tick or Enter) sends
  `return_focus=1`, and the row comes back with `autofocus` on the pencil, which
  htmx focuses after the swap: a keyboard user keeps their place. A save made by
  leaving the row (Tab, a click elsewhere) leaves focus where it went.
- **Leaving the row** is read once the browser has moved focus, not from the
  focusout event: a click on the page around the row, a click on a button in
  Safari (which does not focus buttons), and switching to another window all
  report no related target. Switching windows leaves focus on the field, so it
  does not save.
- **A save that fails outright** (network, a server error htmx does not swap)
  keeps the field open with what was typed and says "Something went wrong.
  Please try again." under it.
- **Without htmx** the form posts like any other: a save redirects to My account
  with the flash, a refusal renders My account with the row open.
- `GET /profile/edit` redirects to My account, for old bookmarks.

The keyboard and screen reader behaviour is in the "Edit in place" row of
`../component_accessibility.md`.

## How the password is changed

`templates/backoffice/profile/_change_password_dialog.html`, `profile.change_password`.

- The Change password button (`aria-haspopup="dialog"`) loads the dialog over
  htmx into `#profile-dialog-host`, a `data-fragment-dialog-host`, as the export
  dialogs do. `init/fragment-dialog-focus.js` moves focus to the current
  password, makes the page behind inert, and returns focus to the button when
  the dialog closes (Escape, the X, Cancel, the backdrop).
- The form posts over htmx back into the host:
  - a refusal is the dialog again (**422**), each reason beside its field and
    `data-dialog-initial-focus` on the first refused field. A wrong current
    password and a password the strength rules refuse are field reasons now,
    not flashes: the floating alerts sit beneath an open dialog, and a flash
    that nothing showed would turn up on the next page;
  - a change answers with nothing for the host, which closes the dialog, and
    the flash appended out of band to the page's alerts.
- Without htmx, `/profile/change-password` is My account with the dialog open.
  That is where `/.well-known/change-password` sends a password manager. Closing
  the dialog there goes to `/profile`, so the address stops opening it. A
  refusal without htmx renders the same; a change redirects to My account.
- An account without a password is sent to Set password, with `HX-Redirect`
  over htmx so the set-password page is not swapped into the host.

## Not changed

- The two-factor pages and their flow.
- Set password stays a page.
- The avatar initials in the top bar follow a name change on the next page
  load: the row swap does not reach the top bar.

## Verification

- `tests/component/test_profile_management.py`: `TestNamesEditedInPlace` (the
  markup the component needs, each answer of `profile.edit`, focus return,
  refusals, a broken save, without htmx) and `TestChangePasswordDialog` (the
  opener and host, each answer of `profile.change_password`, the reasons beside
  their fields, the full page with the dialog open, `HX-Redirect`).
- `src/js/components/inline-edit.test.js`: opening, Escape, the tick, Enter,
  leaving the row by Tab, click and window switch, the unchanged value, a failed
  request.
- `tests/e2e/test_profile_management.py`: both names saved against PostgreSQL,
  one of them over htmx.
- In a browser (Chromium, 1440 and 390 wide): the pencil, Escape, Enter, the
  tick, a click outside, Tab out of the row, focus after each; the dialog's
  focus on open, the inert page, Escape, Cancel, the X, a refused change, the
  address opening My account with the dialog open.

## Session log

- **2026-11-10** — Branch `869-profile-inline-edit` from `origin/main`. Names
  edited in place, Change password in a dialog; `profile/edit.html` and
  `profile/change_password.html` deleted. Four new msgids (the pencil and tick
  names), Hungarian proposals flagged fuzzy.
