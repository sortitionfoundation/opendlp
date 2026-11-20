# 1206 — Site Admin on the backoffice design system

Move the Site Admin pages (`blueprints/admin.py`, `templates/admin/`) from the
GOV.UK `base.html` to `backoffice/base_page.html` and the backoffice components.
The routes keep their URLs, forms and service calls; this is a template change
plus the small route changes listed below.

## Decisions

| #  | Question | Decision |
| -- | -------- | -------- |
| D1 | The index page | Dropped. `/admin/` redirects to the users list. The two list pages carry `tabs` (Users, Invites). |
| D2 | Stat cards | A new `stat_tile` component, with a showcase entry and a test. All ten stats kept. |
| D3 | Confirmations | `alert_dialog` for disable account, enable account and disable 2FA. Revoke invite and clean up keep `data-confirm`. |
| D4 | Editing a user | A separate edit page, restyled. Editing in place is in `docs/agent/future_work/admin_user_inline_edit.md`. |
| D5 | Error summary | Dropped. Errors show beside each field, through `input()` / `radio_group()`. |
| D6 | Wording | Brought into line with `docs/language.md` on this branch, then a translation pass. |

## Navigation

- **List pages** (users, invites): `page_header(title=_("Site Admin"), back_href=Your projects)`
  then `tabs(id="admin-tabs", items=[Users, Invites])`. The tab names are the
  section names; the `<h1>` is "Site Admin".
- **Inner pages** (user, edit user, 2FA audit log, invite, create invite):
  `page_header` with a back arrow to their parent: the list, or the user page
  for edit and audit log. No tabs, so each page has one way back.
- `admin.index` stays as an endpoint and redirects to `admin.list_users`, so the
  account menu link, the legacy header link and bookmarks keep working.
- The account menu's "Switch to Site Admin" loses `target="new"` and its comment
  in `base_page.html`: Site Admin is no longer an old-design page.
- Admin routes that fail keep rendering `errors/500.html`. The error pages are a
  separate piece of work.

## Components

| Need | Component |
| ---- | --------- |
| Page title, back arrow | `page_header` |
| Users / Invites tabs | `tabs` |
| Page panels | `section` |
| Stats | **new** `stat_tile` (D2) |
| Tables | `table`, `table_head`, `table_body`, `table_row`, `table_cell`, `table_cell_custom` |
| Role, status, 2FA tags | `tag` — `admin/_role_tag.html` becomes a wrapper around it |
| Pagination | `pagination`, filters carried in `base_url` |
| Search and filters | `input`, `select`, `button` in a GET form |
| Forms | `input`, `radio_group`, `button` |
| Details lists | `detail_row`, moved from `backoffice/profile/` to `backoffice/components/` |
| Copy code / URL | `copy_button` / `readonly_url_display` from `url_display.html` |
| Audit-log details | `collapsible_section` |
| Confirm dialogs | `alert_dialog` inside `x-data="modal({ initialOpen: false })"` (D3) |
| Empty states | `alert(variant="info")` |
| Flash messages | `floating_alerts`, already in `base_page.html` |

### `stat_tile` (new)

`backoffice/components/stat_tile.html`: `stat_tile(label, value)`. A label and a
large number in a white panel, using design tokens. The number is not a heading.
The tiles sit in a responsive grid that the page provides. Add it to the showcase
and give it a component render test.

## Pages

1. **Users** (`users.html`): six stat tiles; GET form with search, role and
   status filters, an Apply button and a Clear link; table (name, email, role,
   status, 2FA, created, actions); `pagination`; "Export users as CSV" button;
   a note on how to create a user (one msgid with a link placeholder). The
   page's own "Showing X to Y of Z" line goes, since `pagination` prints its own.
2. **User** (`user_view.html`): details in a `section` using `detail_row`; signup
   survey in a second section; actions: Edit user, Disable 2FA (dialog),
   Disable/Enable account (dialog, wording per OAuth or password as now).
3. **Edit user** (`user_edit.html`): first and last name with `input`, role with
   `radio_group`, the note that email cannot be changed, the warning when
   editing yourself, Save changes and Cancel.
4. **2FA audit log** (`user_2fa_audit_log.html`): table with `tag` for the
   action and `collapsible_section` for the details.
5. **Invites** (`invites.html`): four stat tiles; Create invite and Clean up
   expired invites (data-confirm); table with a View link and a revoke button
   (`button(variant="tertiary")`, data-confirm), replacing the inline-styled
   one.
6. **Invite** (`invite_view.html`): details with copy buttons for code and URL;
   the warning text for an active invite; revoke (data-confirm).
7. **Create invite** (`invite_create.html`): role with `radio_group`, email,
   expiry hours, Create invite and Cancel.
8. **Index** (`index.html`): deleted (D1).

## Fixes along the way

- The audit log prints an unknown action raw (`{{ log.action }}`). Map the
  known actions through a labels dict and show an unknown one as a translated
  "Unknown action" tag, logging nothing new.
- `"Error:"` and `aria-label="Page {{ p }}"` are untranslated; both go with the
  GOV.UK markup.
- "To create a user, create/send them an invite code." is two msgids. Becomes
  one, with the link as a placeholder.
- Title Case to sentence case throughout (D6), for example "User Management" to
  "Users", "Create New Invite" to "Create invite", "Save Changes" to "Save
  changes" (reusing the existing msgid). Role names keep their capitals.
  "Site Admin" is a proper noun and stays.

## Tests

- **Component:** `test_admin_user_management.py` and
  `test_admin_invite_management.py` updated for any changed text; a test that
  `/admin/` redirects to the users list; a render test for `stat_tile`; tests
  that the confirm dialogs render for the right users (no disable for yourself,
  no disable 2FA for an OAuth user).
- **`test_legacy_header.py`:** drop the admin cases, since admin is no longer a
  legacy page; keep the error-page cases.
- **e2e:** `tests/e2e/test_admin_*.py` updated for changed text.
- **BDD:** `test_admin_users.py` — the admin steps look for flash messages in
  `#floating-alerts` instead of `.govuk-notification-banner`, and confirm through
  the dialog. Leave the assembly-page steps as they are. Add a scenario that
  disables and re-enables an account through the dialog.
- `just build-all` before the BDD run.

## Order

1. [x] `stat_tile` with showcase and test; move `detail_row` to components.
2. [x] Index redirect, tabs, users list.
3. [x] User page with dialogs, edit user, audit log.
4. [ ] Invites list, invite page, create invite.
5. [ ] Account menu link; `test_legacy_header.py`.
6. [ ] Wording pass, then the `translate-catalogues` skill.
7. [ ] `just check`, `just test-nobdd`, then `just build-all && just test-bdd-headless`.
