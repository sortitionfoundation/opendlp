# 869 — Profile / My account on the backoffice design

Shortcut [sc-869](https://app.shortcut.com/sortitionfoundation/story/869) (epic
*New Backoffice Design*): bring the signed-in account pages under `/profile`
from GOV.UK Frontend onto the OpenDLP design system — the layout, navigation
and components the backoffice pages already use.

The story has no description. This document is the inventory, the precedent
to copy, and a page-by-page proposal; the open questions at the end are the
ones this document cannot settle on its own.

## Inventory

### The pages (as they were before this branch, all GOV.UK)

Every template under `templates/profile/` extended the GOV.UK `base.html` and
is rendered by `src/opendlp/entrypoints/blueprints/profile.py`:

| Route | Template | Form / context | Notes |
|---|---|---|---|
| `GET /profile` (`profile.view`) | `profile/view.html` | `role_label`, `role_description`; `current_user` | Three GOV.UK summary lists: profile, authentication methods (password / Google / Microsoft with Remove / Unlink / Set / Link actions as inline POST forms with `data-confirm`), security (2FA status + *Manage*). Bottom: *Edit profile*, *Change password*, *Back to Your projects*. |
| `GET/POST /profile/edit` (`profile.edit`) | `profile/edit.html` | `EditOwnProfileForm` (first_name, last_name; optional, max 100) | Hand-written `govuk-form-group` markup, `novalidate`, `form.hidden_tag()`. |
| `GET/POST /profile/change-password` | `profile/change_password.html` | `ChangeOwnPasswordForm` + `password_help` (HTML) | `govuk_password_input` macro ×3, requirements in a GOV.UK inset. OAuth users without a password are redirected to set-password. |
| `GET/POST /profile/set-password` | `profile/set_password.html` | `SetPasswordForm` + `password_help` | Same shape, two fields. |
| `GET /profile/2fa` (`two_factor_settings`) | `profile/2fa_settings.html` | `status` (`enabled`, `enabled_at`, `backup_codes_remaining`, `is_oauth_user`) | Summary list + two `<details>` disclosures wrapping POST forms (regenerate codes, disable) each with a TOTP code input; `data-confirm` on disable. |
| `GET /profile/2fa/setup` (`setup_2fa`) | `profile/2fa_setup.html` | `qr_code_url`, `totp_secret`, `backup_codes` | Three steps: QR image + manual-secret `<details>`, backup codes grid with *Download* / *Print* (`data-download-backup-codes`, `data-print`), verification form posting to `enable_2fa`. |
| `POST /profile/2fa/backup-codes/regenerate` | `profile/2fa_backup_codes.html` | `backup_codes` | Success banner, warning, codes grid, Download / Print / Done. |

POST-only routes with no template: `remove_password`, `remove_oauth`,
`enable_2fa`, `disable_2fa`, `regenerate_backup_codes`, plus the OAuth link
GETs `link_google` / `link_microsoft` and their callbacks. Flash messages
carry every outcome; the templates themselves render no inline errors except
the WTForms field errors on edit / change-password / set-password.

Behaviour the templates rely on and that the design-system shell already
provides (`src/js/init/document-actions.js`, bundled into `static/js/utilities.js`
and loaded by `backoffice/base.html`): `data-confirm` on a `<form>` (confirm
dialog on submit), `data-download-backup-codes`, `data-print`, and the
`data-toggle-password` show/hide button that `input(type="password")` renders.

Tests touching these routes: `tests/component/test_profile_management.py`,
`tests/component/test_oauth_flow.py::TestOAuthProfileDisplay`,
`tests/component/test_2fa_flow.py`, `tests/e2e/test_profile_management.py`,
`tests/e2e/test_oauth_flow.py`, `tests/e2e/test_wellknown.py` (the
`/.well-known/change-password` redirect). No BDD scenario visits `/profile`.

### The backoffice design system

- Shell: `templates/backoffice/base.html` — token CSS, compiled Tailwind, CSP
  Alpine, htmx, `utilities.js`; no GOV.UK assets.
- Page layout: `templates/backoffice/base_page.html` — sticky top
  `navigation()` (logo → `backoffice.dashboard`, help icon, **account menu**
  with *My account* → `profile.view`, *Switch to Site Admin*, *User Data
  Agreement*, *Sign out*), a sticky `page_header` block, `page_content`,
  `floating_alerts()` for flashes, `footer()`.
- Components (`templates/backoffice/components/`, showcased at
  `/backoffice/showcase`): `page_header()` (back arrow + h1), `section()`
  (white box), `card()`, `input()` / `checkbox()` / `select()` /
  `textarea()`, `button()` (primary / secondary / tertiary / danger / icon),
  `tag()` (grey / blue / green / yellow / red), `alert()`, icons via
  `icons.html` macros only, `brand_marks.html` for the Google / Microsoft marks.
- Key/value rows: no component; `assembly_details.html` is the idiom
  (`<dl>` of `flex flex-col sm:flex-row` rows, `dt.text-label-lg sm:w-48`,
  `dd.text-body-md`, divider `--color-borders-dividers`).
- Build: `just build-backoffice` (Tailwind v4, `static/backoffice/src/main.css`
  → `static/backoffice/dist/main.css`). `tailwind.config.js` scans **only**
  `templates/backoffice/**` and `templates/public/**` — a template left under
  `templates/profile/` would have its utility classes purged.
- Guards in CI: `tests/unit/test_design_tokens.py` (every `var(--…)` must be
  defined in the token files), `tests/unit/test_icons.py` (no raw `<svg>`
  outside the allowlist), `tests/component/test_html_lang.py`.

## Precedent

**PR #331** (`1053-signup-redesign`) built `templates/public/base.html` on the
backoffice shell and moved the create-account page; **PR #395**
(`public-auth-pages-redesign`) moved every remaining `templates/auth/` page
the same way, one commit per page group. The recipe, applied here:

1. The template moves into a Tailwind-scanned folder and switches its base
   (`auth/login.html` → `public/login.html`; here `profile/view.html` →
   `backoffice/profile/view.html` extending `backoffice/base_page.html`).
2. GOV.UK markup becomes component macros: `input()` with WTForms adapted at
   the call site (`name`, `label=form.x.label.text`, `value=form.x.data or ""`,
   `error=form.x.errors | join("\n")`, `attrs='autocomplete="…"'`),
   `button(variant="primary", type="submit")`, links as
   `underline font-semibold` in `--color-links`.
3. Flash messages come from the layout's `floating_alerts()`; tests that read
   `.govuk-error-summary` read `#floating-alerts` instead.
4. The route's `render_template` path changes; nothing else in the blueprint.
5. A component test pins the page as GOV.UK-free (`b"govuk-" not in
   response.data`, no `css/application.css`) and on the intended layout
   (`tests/component/test_public_auth_pages.py`).
6. Catalogues regenerated in a separate `i18n:` commit; the plan document
   gets a session-log entry.

One difference from #395: the auth pages are **public**, so they went onto the
narrow centred `public/base.html`. The profile pages are **signed-in** pages.
`docs/agent/public-pages-redesign/plan.md` lists `profile/*` under "legacy
authenticated pages … superseded by the backoffice redesign", and
`base_page.html` opens *My account* with `target="new"` precisely because it
is an old-design page. So the base here is `backoffice/base_page.html`, and
the pages become ordinary backoffice pages — the same move the dashboard and
project pages made.

## Proposal, page by page

### `/profile` — view (done in this branch)

- `templates/backoffice/profile/view.html` extends `backoffice/base_page.html`.
- `page_header` block: `page_header(title=_("My account"),
  back_href=url_for('backoffice.dashboard'), back_label=_("Back to Your
  projects"))` — the detail-page header `assembly_details.html` uses. The old
  bottom link pointed at `main.dashboard`, which 404s unless
  `FF_OLD_DEFAULT_DASHBOARD` is on; the back arrow fixes that in passing.
- Three `section()` boxes, each with an `h2.text-heading-lg` and the
  `assembly_details.html` `<dl>` rows: *Profile information* (email, first
  name, last name, role as `tag(role_label, colour="blue")` + the description
  in `text-body-sm`), *Authentication methods* (password, Google, Microsoft:
  `tag()` green/grey for the state, the action in a trailing `<dd>`),
  *Security* (2FA state + *Manage*).
- Actions keep their semantics: the POST forms (Remove / Unlink) stay forms
  with `csrf_token` and `data-confirm`, their buttons become
  `button(variant="tertiary", type="submit")`; the GET actions (Set password,
  Manage) are links in `--color-links`; *Link Google / Microsoft account*
  are `button(variant="secondary", href=…, leading_icon=brand_*())` exactly as
  the sign-in page draws its SSO buttons (the routes are plain GETs). The
  `gsi-material-button` CSS lived in the GOV.UK stylesheet and is gone with it.
- Bottom row: *Edit profile* and *Change password* as secondary buttons.
- `base_page.html`: the *My account* menu item loses `target="new"` — the
  comment's reason (old-design page in its own tab) no longer holds; *Switch
  to Site Admin* keeps it.

### `/profile/edit` — edit (done in this branch)

- `templates/backoffice/profile/edit.html`, the `create_assembly.html` /
  `edit_assembly.html` form idiom: `h1.text-display-lg`, a `max-w-2xl` form,
  `input()` per field (label, hint from `description`, all errors joined,
  `autocomplete` passed through `attrs`), `button(_("Save changes"),
  type="submit", variant="primary")` + `button(_("Cancel"), href=…,
  variant="secondary")`. `form.hidden_tag()` and `novalidate` kept.

**Scope (decided 3 Nov):** this PR moves every page under `/profile` — view, edit,
the two password pages and the three 2FA pages — so the account journey is on one
design system and `templates/profile/` goes away. The first cut covered view and
edit only, leaving the five below as a follow-up; review asked for the whole
journey in one PR, and the notes below were already the specification.

### `/profile/change-password` and `/profile/set-password` (done in this branch)

- `templates/backoffice/profile/change_password.html` and `set_password.html`,
  the `edit.html` form idiom (`h1.text-display-lg`, a `max-w-2xl` form, primary
  submit + secondary Cancel): `input(type="password", required=true)` ×3 / ×2
  with `autocomplete` through `attrs`; the requirements list
  (`password_help|safe`) under the new-password field in `text-body-sm`, the
  way `public/reset_password.html` places it. `form.hidden_tag()` and
  `novalidate` kept; the design system's show/hide toggle replaces the GOV.UK
  one.
- Retires the last two users of `components/govuk_password_input.html`
  (noted in the public-pages plan as the reason that macro survived phase 3)
  — the macro is deleted with them.

### `/profile/2fa`, `/profile/2fa/setup`, backup codes (done in this branch)

- `2fa_settings.html`: `page_header()` with a back arrow to `/profile` (the old
  bottom *Back to profile* link; same move as the view page), `section()` +
  `<dl>` rows for the status, the row macro shared with the view page in
  `backoffice/profile/_detail_row.html`. The two disclosures stay native
  `<details>` (no disclosure component; the verify-2FA page did the same),
  each wrapping its POST form with an `input()` for the code
  (`inputmode="numeric" pattern="[0-9]{6}" maxlength="6"
  autocomplete="one-time-code"` via `attrs`, no `novalidate` so the browser
  catches a mistyped code) and `button(variant="danger")` for Regenerate /
  Disable; `data-confirm` stays on the disable form. The OAuth-user notice is
  `alert(variant="info")`.
- `2fa_setup.html`: three `section()` steps; the QR `<img>` on
  `--color-page-background` with a `--color-borders-dividers` border, the
  secret in a `text-code` block on `--color-subtle-background-panels`
  (`select-all`, so one click selects it); the warning as
  `alert(variant="warning")`; the backup-codes grid and the Download / Print
  buttons in `backoffice/profile/_backup_codes.html`, shared with the
  regenerated-codes page. The grid keeps `id="backup-codes"` (the download
  handler reads its children); Download / Print are secondary buttons carrying
  `data-download-backup-codes` / `data-print`. The verification field lost its
  `autofocus`: focusing it on load scrolled the page past the QR code, so the
  page opened on step 3. (The public verify page keeps its autofocus; the code
  field is all that page has.)
- `2fa_backup_codes.html`: the GOV.UK success banner becomes
  `alert(variant="success")`, the rest as in setup; *Done* primary in the
  same row.
- The inline `style="…"` colours of the 2FA pages (`#f3f2f1`, `#b1b4b6`,
  `#1d70b8`) are tokens now.
- `src/js/init/document-actions.js`: the `data-print` and
  `data-download-backup-codes` handlers read `e.target.dataset` directly, so a
  click on the label `<span>` the `button()` macro renders missed them. They
  use `closest()` now, as the `data-confirm` handler already did for the same
  reason; `document-actions.test.js` covers both.
- Dropped msgid: the GOV.UK warning text's assistive "Information". No new
  strings.

### What waits for a design source

Everything above uses only what the design system already provides. A Figma
frame would decide: whether *My account* is one page or tabs (Profile /
Security), where *Edit profile* sits (page-header action vs bottom row),
whether the summary rows become a two-column grid or cards, the copy of the
headings and hints, and any illustration or avatar on the page.

## Verification

- `uv run python -m pytest tests/component/test_profile_management.py
  tests/component/test_oauth_flow.py tests/component/test_2fa_flow.py
  tests/e2e/test_profile_management.py tests/unit/test_design_tokens.py
  tests/unit/test_icons.py -q`
- `just build-backoffice`, `just test-js`, `just check`, `just translate-regen`
  + `just translate-check`.
- Keyboard pass per `docs/agent/component_accessibility.md`: the back arrow,
  the account menu, the Remove / Unlink confirm, focus order on edit.

## Session log

- **2026-11-02** — Branch `869-my-account-backoffice` from `origin/main`
  (`8e8268e6`). Inventory and precedent written up (this document). View and
  edit moved onto `backoffice/base_page.html` as `templates/backoffice/profile/`;
  the five remaining `templates/profile/` pages stay GOV.UK until the scope
  question is answered. *My account* opens in the same tab now.
- **2026-11-03** — Scope widened to the whole journey. Change password, set
  password, 2FA settings, 2FA setup and the regenerated backup codes page moved
  onto `backoffice/base_page.html`; `templates/profile/` and
  `components/govuk_password_input.html` deleted. Two shared partials under
  `templates/backoffice/profile/` (`_detail_row.html`, `_backup_codes.html`).
  The print / download click handlers use `closest()`. Component tests pin the
  five pages GOV.UK-free and on the backoffice layout, and the 2FA pages' forms
  and `data-*` hooks; catalogues regenerated.
- **2026-11-03** — Review. Page titles, headings, step headings and field labels
  on the seven pages are in sentence case (`docs/language.md`), including the
  labels of `EditOwnProfileForm`, `ChangeOwnPasswordForm` and `SetPasswordForm`,
  which only these pages render. Five reuse an existing msgid (*My account*,
  *Edit profile*, *Change password*, *Set password*, *Set up two-factor
  authentication*). The Title Case twins remain only outside these pages: the
  legacy `base.html`, the admin user pages, sign-up, password reset and the
  verify-2FA page. The remove-password confirm and the set-password intro said
  Google whichever provider was linked; both name the linked provider now. The
  Hungarian for the 18 new msgids is flagged fuzzy for review: the old
  translations carried over, except *Current password*, whose old entry said
  "new password", and the two strings with the provider placeholder.
