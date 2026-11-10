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
the pencil, the tick and the X, `icon_check` in `--color-success-text`,
`icon_close` in `--color-error-text` (it takes a `style`, as `icon_check` does),
and `icon_pencil`, Lucide's pencil from the Icons sheet (node 5032:10151), added
to `icons.html` and the icons showcase. `icon_edit` is Lucide's square-pen, a
pencil over a square; the design draws the plain pencil.

Two departures from the design, both small:

- **A way back without saving.** The design shows none, and leaving the row
  saves. Escape puts the stored value back, and so does a red X beside the
  tick ("Cancel editing first name"), for a mouse user; both return focus to
  the pencil.
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
- **The X never saves.** The tick and the X cancel their `mousedown`, so
  pressing either keeps focus in the field. Safari focuses no pressed button:
  without that, the field would blur to the page on the way to the X, which
  counts as leaving the row, and leaving the row saves. From the keyboard, Tab
  reaches the X inside the row, so that is no leaving either.
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
  the dialog closes (Escape, the close button, Cancel, the backdrop).
- **Show** beside each password works in the dialog because the password
  toggle (`init/document-actions.js`) listens on the document in the capture
  phase. Every dialog panel stops clicks from bubbling out of it (`@click.stop`
  in `components/modal.html`), so a bubbling listener never heard them; the
  sign-in and sign-up pages, with no dialog, always worked.
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
  their fields, the full page with the dialog open, `HX-Redirect`), and the X's
  markup: a plain button that cancels, red, never taking focus when pressed.
- `src/js/components/inline-edit.test.js`: opening, Escape, the X, the tick,
  Enter, leaving the row by Tab, click and window switch, the unchanged value, a
  failed request.
- `src/js/init/document-actions.test.js`: the password toggle, including a click
  inside an element that stops propagation, as a dialog panel does.
- `tests/e2e/test_profile_management.py`: both names saved against PostgreSQL,
  one of them over htmx.
- `features/my-account.feature` (`tests/bdd/test_my_account.py`), what only a
  browser shows: Enter saves and focus comes back to the pencil across the
  swap, Escape and the X leave the name (still there after a reload), a click
  outside saves, the dialog opens with focus in the current password and gives
  it back to the button on Escape, Show reveals a password in the dialog, a
  wrong current password is said beside its field. The scenarios sign in as the
  disposable user, so the shared accounts keep their names and passwords.
- By hand in a browser (Chromium, 1440 and 390 wide), beyond the scenarios: the
  tick, Tab out of the row, an unchanged name sending nothing, the inert page
  behind the dialog, Cancel, the close button, the address opening My account
  with the dialog open.

## Session log

- **2026-11-10** — Branch `869-profile-inline-edit` from `origin/main`. Names
  edited in place, Change password in a dialog; `profile/edit.html` and
  `profile/change_password.html` deleted. Four new msgids (the pencil and tick
  names), Hungarian proposals flagged fuzzy.
- **2026-11-10** — Review. Show did nothing beside the dialog's password fields,
  over htmx and with the page alike: the panel's `@click.stop` swallowed the
  click before the toggle's document listener heard it, which now listens in
  the capture phase. A red X beside the tick cancels an edit for a mouse user,
  as Escape does. Two new msgids (the X's names), Hungarian proposals fuzzy.
