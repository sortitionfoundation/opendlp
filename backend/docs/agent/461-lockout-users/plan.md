# Locking out a compromised user — plan

**Issue:** 461
**Branch:** `461-lockout-users`
**Date:** 2026-08-27
**Status:** Implemented. All open questions answered by Chewie and folded in
(§3, recorded in §6); every item in §4 is done.

---

## 1. Goal

If a user's account is compromised, an admin must be able to lock them out
*completely and immediately* from the admin UI, and re-enabling them must force
a fresh password before they can get back in.

From the story, in scope:

- On **disable**: cancel all active sessions; scramble the password; log the
  action (sysadmin-visible logs only).
- On **enable**: email the user to say the account is live again, with a link to
  the password reset page.

Explicitly out of scope (from the story): showing *who* disabled the account to
other admins, and a free-text "why" comment in the record.

---

## 2. What already exists

### 2.1 The `is_active` flag and its plumbing

| Layer | Where | Behaviour |
|---|---|---|
| Domain | `domain/users.py:46` | `User.is_active` bool, default `True` |
| Domain | `domain/users.py:55-57` | **`is_authenticated` returns `self.is_active`** — this is the load-bearing hack, see below |
| DB | `adapters/orm.py:256` | `is_active` Boolean, not null, default true |
| Service | `user_service.py:479-540` `update_user()` | plain assignment `user.is_active = is_active`; refuses self-deactivation (`:527`) |
| Service | `user_service.py:162` `authenticate_user()` | inactive → `InvalidCredentials` |
| Form | `entrypoints/forms.py:406` | `is_active = BooleanField(_l("Active Account"))` |
| Route | `blueprints/admin.py:140-218` `edit_user()` | passes `form.is_active.data` into `update_user` |
| CLI | `entrypoints/cli/users.py:135` | `users deactivate` sets `user.is_active = False` **directly**, bypassing the service layer |

Guards on `is_active` already exist in `password_reset_service` (3 places) and
`email_confirmation_service` (3 places).

### 2.2 What deactivation actually does today

Chewie's hunch was right, and the answer is "sort of, by accident".

- **Fresh password sign-in: blocked.** `authenticate_user` checks `is_active`.
- **Fresh OAuth sign-in: blocked, but with a lying flash message.**
  `find_or_create_oauth_user` (`user_service.py:321`) never checks `is_active`.
  The callback then calls `login_user(user)` (`auth.py:370`, `:712`) and ignores
  the return value. Flask-Login's `login_user` refuses inactive users and
  returns `False`, so no session is set — but the route still flashes *"Signed
  in successfully"* and redirects to the dashboard, where the user is bounced
  straight back to the login page with "Please sign in". Same pattern in
  `confirm_email` (`auth.py:402`) and `_complete_2fa_login` (`auth.py:217`).
  Not a hole; a confusing one.
- **Existing sessions: suspended, not cancelled.** `login_required` and every
  `require_*` decorator test `current_user.is_authenticated`, which for our
  `User` *is* `is_active`. So an inactive user is bounced off every protected
  route on their next request. But:
  - the session record stays alive in Redis until it expires (7 days);
  - the remember-me cookie stays valid (7 days, `config.py:613`);
  - **re-enabling the account resurrects the old session** — the attacker's
    browser is logged straight back in;
  - `load_user` (`extensions.py:168`) returns the user regardless, so any code
    path that reads `current_user` without a `login_required` decorator (locale
    selection, context processors, templates) still sees a logged-in user.
- **Password: untouched.** Re-enabling restores the old, presumed-compromised
  password.
- **Logging: nothing.** `update_user` emits no log line at all for the
  transition. The route logs only failures.
- **Email on re-enable: does not exist.**

So the three bullets of the story are all genuinely missing, and the "cancelled
sessions" one is the one with a real design decision behind it.

### 2.3 Useful machinery we can reuse

- `password_reset_tokens.invalidate_user_tokens(user_id)` and the same on
  `email_confirmation_tokens` (`repositories.py:322`, `:351`).
- `two_factor_service.admin_disable_2fa` (`two_factor_service.py:226`) — clears
  the TOTP secret, deletes the backup codes and writes a `TwoFactorAuditLog`
  row. It is also the house pattern for an admin-initiated security action.
- `user_invites.get_invites_created_by(user_id)` (`repositories.py:157`) and
  `UserInvite.is_valid()`.
- The user-notification email pattern: `send_password_reset_email`
  (`password_reset_service.py:273`) and `send_assembly_role_assigned_email`
  (`user_service.py:1004`) — adapters passed in from the route, templates in
  `templates/emails/*.{txt,html}`, `logger.info(..., user_id=...)` on success.
- `auth.forgot_password` (`auth.py:447`) already does anti-enumeration and rate
  limiting, and refuses inactive and OAuth users.
- The destructive-button pattern: a POST form with `data-confirm` and a
  `govuk-button--warning` submit, as used for "Disable 2FA"
  (`templates/admin/user_view.html:124-130`) and invite revocation.

---

## 3. Design

### 3.1 How to actually cancel sessions — **session epoch on the user**

Three options considered:

| Option | Verdict |
|---|---|
| **A. Session epoch stamped on the user, checked in `load_user`** | **Chosen.** One nullable column. Kills server-side sessions *and* remember-me cookies, and stays killed across a re-enable. |
| B. Scan Redis and delete the user's session keys | Rejected. Flask-Session keys are not indexed by user, so it means walking every key and deserialising it; it does nothing under the `cachelib` backends used in dev/test (`config.py:578`, `:596`); and it leaves the remember-me cookie able to mint a fresh session. |
| C. Rely on today's `is_authenticated == is_active` | Rejected. That is the behaviour described in §2.2 — suspension, not cancellation, and it un-suspends on re-enable. |

**Mechanism.** Add `sessions_invalidated_at: datetime | None` to `User`
(nullable `TZAwareDatetime` column). Carry it through Flask-Login's own id
channel by making `User.get_id()` return `"<uuid>|<epoch>"`, and have
`load_user` split the value, load the user, and return `None` unless the epoch
matches. Flask-Login stores `get_id()`'s output in *both* the session and the
remember-me cookie (`login_manager.py:482` encodes `session["_user_id"]`) and
hands it back to `user_loader`, so this covers both with no extra session key
and no extra `before_request` hook.

Consequences:

- **Everyone is logged out on deploy.** An id already in a session or cookie is
  a bare UUID with no epoch, which `load_user` will reject. Accepted as a
  one-off (Q7): there are few enough users that a single forced re-login is
  cheaper than carrying a compatibility branch forever. `load_user` still has to
  *handle* a bare UUID without raising — it returns `None`.
- `tests/component/conftest.py:104` sets `session["_user_id"] = user.get_id()`
  — it calls `get_id()`, so it keeps working.
- Also make `load_user` return `None` for `is_active == False`, so an inactive
  user is anonymous *everywhere*, not just on decorated routes. That removes the
  reliance on the `is_authenticated == is_active` hack for security (leave the
  property as it is — `login_user` depends on it).

Alternative considered and rejected: derive a Django-style session auth hash
from `password_hash`. Free session invalidation on any password change, but it
does nothing for OAuth-only users (no hash to change) and it silently changes
the behaviour of every ordinary password change. A single explicit column is
clearer.

### 3.2 "Reset the password" — a landmine to avoid

`User.__init__` raises `ValueError` unless there is a `password_hash` **or**
OAuth credentials (`domain/users.py:34`), and `create_detached_copy()` goes back
through `__init__` (`:172`). So setting `password_hash = None` on a
password-only user makes *every detached copy blow up* — `load_user`,
`authenticate_user`, `get_user_by_id`, the admin views. Do not do it.

**Chosen: an unusable password sentinel**, Django's design. Add to the domain:

```python
UNUSABLE_PASSWORD_PREFIX = "!"

def set_unusable_password(self) -> None:
    """Replace the password with a value no input can ever match."""
    self.password_hash = f"{UNUSABLE_PASSWORD_PREFIX}{secrets.token_urlsafe(32)}"

def has_usable_password(self) -> bool:
    return bool(self.password_hash) and not self.password_hash.startswith(UNUSABLE_PASSWORD_PREFIX)
```

and short-circuit in `security.verify_password` so we never depend on what
Werkzeug's `check_password_hash` does with a malformed hash string. The
invariant stays satisfied, the column stays non-empty, nothing else changes.

Rejected: relaxing the domain invariant to allow "no auth method at all". Much
wider blast radius (registration, OAuth link/unlink, `remove_password`,
`remove_oauth`) for no gain here.

`has_usable_password()` then also tells the re-enable email which wording to
use.

### 3.3 What disabling does, in full

`disable_user(uow, user_id, admin_user_id)`:

1. Refuse to disable yourself (the guard currently at `user_service.py:527`
   moves here). Refuse if already inactive — idempotent no-op with a log line.
2. `user.is_active = False`.
3. `user.invalidate_sessions()` — stamp `sessions_invalidated_at`, killing every
   session and remember-me cookie (§3.1).
4. `user.set_unusable_password()` (§3.2).
5. `password_reset_tokens.invalidate_user_tokens(user_id)` and the same for
   `email_confirmation_tokens` — so no outstanding link survives the lockout.
6. **Clear 2FA** (Q1): if `user.totp_enabled and not user.oauth_provider`, call
   `two_factor_service.admin_disable_2fa(uow, user_id, admin_user_id)`, which
   drops the TOTP secret, deletes the backup codes and writes the audit row.
   The guard matters — `admin_disable_2fa` raises `TwoFactorSetupError` when 2FA
   is off or the user is OAuth-based (`two_factor_service.py:254-258`), so it
   cannot be called unconditionally. `user_service` importing `two_factor_service`
   introduces no cycle (that module imports only `totp_service`, domain and
   `unit_of_work`).
   The reasoning: a compromised account is exactly the case where the enrolled
   authenticator may be the *attacker's*, and leaving it in place would both
   preserve their second factor and lock the real user out after their password
   reset.
7. **Warn about outstanding invites** (Q3): look up
   `uow.user_invites.get_invites_created_by(user_id)`, filter to
   `is_valid()`, and if there are any, emit a `warning` log naming the invite
   **ids and count — never the codes**, which are secrets (`admin.py:551-553`
   deliberately logs no code). Do not auto-revoke: invites may be going away
   entirely, so this stays a pointer for a sysadmin rather than new behaviour.
8. Emit the `user.disabled` log event (§3.6).

**No email is sent on disable** (Q4). If we suspect a compromise, the attacker
may still control the mailbox.

**OAuth-only users are not unlinked** (Q2). Being locked out of OpenDLP is the
point; once we know their Google/Microsoft account is clean they carry on using
it. Scrambling the password is a harmless no-op for them, and the re-enable
email says so.

### 3.4 What re-enabling does

`enable_user(uow, user_id, admin_user_id)` sets `is_active = True`, logs, and
returns the detached user. It does **not** clear `sessions_invalidated_at` — the
old sessions must stay dead. The route then sends the email.

**The email links to `auth.forgot_password`, not to a token.**

- No token in the email, so nothing to leak, expire, or replay.
- Reset tokens live one hour (`password_reset_service.py:22`). An admin
  re-enabling an account at 18:00 would otherwise send a link that is dead
  before the user reads it.
- `forgot_password` already handles rate limiting and anti-enumeration.

New templates `templates/emails/account_reenabled.{txt,html}`, following
`user_invite.*`. Two branches, keyed off `has_usable_password()` /
`oauth_provider`:

- password users: "your password was reset when the account was locked; set a
  new one here", plus a note that 2FA needs setting up again if it was cleared;
- OAuth-only users: "sign in with Google/Microsoft as before".

Guard against a blanked email address (GDPR erasure leaves the row with an empty
email) — no address, no send, one log line.

### 3.5 Disable becomes its own action (Q6)

Unticking a checkbox in a form that also edits someone's surname is the wrong
control for something that ends every session and destroys the password. So:

- **Remove `is_active` from `EditUserForm`** (`forms.py:406`) and from
  `user_edit.html`. `update_user` loses its `is_active` parameter along with the
  self-deactivation guard, which moves into `disable_user`. Callers to update:
  `admin.edit_user` (`admin.py:158-166`) and
  `tests/unit/test_user_service.py:724-797`.
- **Two new admin routes**, modelled on `disable_user_2fa` (`admin.py:221-258`):
  - `POST /admin/users/<uuid:user_id>/disable`
  - `POST /admin/users/<uuid:user_id>/enable`
- **Two buttons on `templates/admin/user_view.html`**, in the existing button
  group next to "Disable 2FA": a `govuk-button--warning` "Disable Account" when
  the user is active, a secondary "Re-enable Account" when they are not. Both
  are POST forms with `data-confirm`, matching the house pattern. The disable
  confirmation text must spell out the consequences — sessions ended, password
  destroyed, 2FA cleared.
  - Caveat accepted for consistency: `data-confirm` is JS-only, so with
    scripting off the form submits unconfirmed. That is already true of "Disable
    2FA", which is comparably destructive; a dedicated confirmation page for
    this one action would be inconsistent and is more than "minimal".

The Active/Inactive tag on the view and list pages stays as it is.

### 3.6 Where the logic lives, and logging

New functions in `user_service.py`, called by entrypoints only:

```python
def disable_user(uow, user_id, admin_user_id) -> User
def enable_user(uow, user_id, admin_user_id) -> User   # the caller sends the email
```

The CLI's `users deactivate` must stop mutating `is_active` directly
(`cli/users.py:135`) and call `disable_user`, so there is exactly one
implementation of "lock out". Add a matching `users activate` command? Not
needed for the story — leave it out and note it.

Email adapters are passed into the route-facing call the way
`grant_user_assembly_role` already does (`user_service.py:591-593`), keeping the
UnitOfWork convention intact — only the admin route opens `with uow:`.

Logging: structlog events carrying `user_id` and `admin_user_id` as UUID
strings, and **no email addresses or invite codes** (`docs/personal-data.md`):

| Event | Level | Fields |
|---|---|---|
| `user.disabled` | `warning` | `sessions_invalidated`, `password_scrambled`, `totp_cleared` |
| `user.disabled.outstanding_invites` | `warning` | `invite_count`, `invite_ids` |
| `user.enabled` | `warning` | |
| `user.reenabled_email_sent` / `...email_failed` | `info` / `error` | |

`warning` for the state changes so they stand out in a log search — they are
security events, and the story wants them findable by a sysadmin.

### 3.7 Fix the lying "Signed in successfully"

The other half of "disable fresh sign ins": check `login_user()`'s return value
at the call sites that ignore it (`auth.py:217`, `:352`, `:402`, `:603`, `:712`)
and flash "This account has been disabled. Please contact an administrator."
instead of a success message.

---

## 4. Work breakdown

1. **Domain** — DONE. `sessions_invalidated_at` on `User` (constructor, attribute,
   `create_detached_copy`); `invalidate_sessions()`, `set_unusable_password()`,
   `has_usable_password()`; `get_id()` returning `"<uuid>|<epoch>"`.
2. **Persistence** — DONE. column in `orm.py`; `uv run alembic revision
   --autogenerate -m "add sessions_invalidated_at to users"`. No new table, so
   `_delete_all_test_data()` is untouched.
3. **Session kill** — DONE. `load_user` parses the composite id, rejects an epoch
   mismatch, a bare UUID, and an inactive user. `verify_password`
   short-circuits the unusable-password sentinel.
4. **Service** — DONE. `disable_user` / `enable_user` per §3.3–3.4; strip `is_active`
   from `update_user` and move the self-deactivation guard; token invalidation;
   2FA clearing; outstanding-invite warning; structlog events.
5. **Email** — DONE. `send_account_reenabled_email` in `user_service.py`;
   `templates/emails/account_reenabled.{txt,html}` with the password/OAuth
   branch; `just translate-regen`.
6. **Entrypoints** — DONE. new `disable`/`enable` admin routes; buttons on
   `user_view.html`; `is_active` out of `EditUserForm` and `user_edit.html`;
   CLI `deactivate` routed through the service; `login_user` return values
   checked (§3.7).
7. **Tests** — DONE.
   - unit: domain methods; `disable_user` / `enable_user` including the
     already-inactive and self-disable branches, the OAuth and no-2FA branches,
     and the invite warning; unusable password never verifies; epoch mismatch;
     update the four `update_user` tests that pass `is_active`;
   - component (`tests/component/test_admin_user_management.py`): disable via
     the real route over `FakeUnitOfWork`; assert the target's client is logged
     out on its next request **and stays logged out after a re-enable**; assert
     the re-enable email was sent and its body links to the forgot-password
     page; assert a non-admin gets 403 on both routes;
   - integration: the Alembic migration and the repository round-trip of the
     new column;
   - e2e (`tests/e2e/test_admin_user_management.py`): admin disables a user,
     that user's live session dies on the next request;
   - BDD (`tests/bdd/test_admin_users.py`): the admin-facing story end to end.
8. **Docs** — DONE. A short `docs/account-lockout.md` (linked from `CLAUDE.md`'s
   documentation list) on what disabling does, what it deliberately does not do
   (OAuth links, invites), and what an operator should check beyond it.

---

## 5. Risks

- **Werkzeug's `check_password_hash` on a malformed hash.** The sentinel
  short-circuit in `verify_password` means we never find out, but verify during
  implementation that nothing else feeds `password_hash` to Werkzeug directly.
- **Disabling is irreversible in one respect**: the old password is gone for
  good, even if the disable was a mistake. That is the intent, and the confirm
  dialog must say so plainly.
- **`get_id()` is now parsed, not just compared.** Anything that stores or
  reconstructs `_user_id` by hand would break; the only place found is
  `tests/component/conftest.py:104`, which goes through `get_id()`.

---

## 6. Decisions (settled)

| # | Question | Decision |
|---|---|---|
| Q1 | Clear 2FA on disable? | **Yes, clear it.** A compromised account is exactly where the enrolled authenticator may be the attacker's. Via `admin_disable_2fa`, guarded (§3.3 step 6). |
| Q2 | OAuth-only users — unlink on disable? | **No (option a).** Being locked out of OpenDLP is enough; once the account is known clean they carry on with the same Google/Microsoft login. |
| Q3 | Revoke unused invites the disabled user created? | **No — log a warning only.** Invites may be going away, so do the minimal thing: a `warning` log with invite ids and count, never the codes. |
| Q4 | Email the user on disable too? | **No.** The attacker may still control the mailbox. |
| Q5 | Turn on Flask-Login `session_protection = "strong"` / revisit cookie lifetimes? | **Out of scope** — separate story logged. |
| Q6 | Checkbox or its own action? | **Its own action (option b).** Drop the `is_active` checkbox entirely; explicit Disable / Re-enable buttons and routes (§3.5). |
| Q7 | `get_id()` format change logs everyone out on deploy | **Accepted as a one-off** — few enough users that a forced re-login beats a permanent compatibility branch. |
