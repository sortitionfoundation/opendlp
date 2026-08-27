# Account Lockout

What happens when an admin disables a user account, what it deliberately does
not do, and what an operator should check beyond it.

The case this is built for is a **compromised account**: someone else has the
user's password, or their session, and we need them out now.

## Disabling an account

From **Site Admin → Users → (a user) → Disable Account**, or from the CLI:

```bash
opendlp users deactivate user@example.com --admin-email admin@example.com
```

Both go through `user_service.disable_user`, so they do the same thing:

| What | Why |
|---|---|
| Clears the active flag | Blocks every new sign in, password or OAuth |
| Ends **every** session, including remember-me cookies | The attacker's browser stops working on its next request |
| Replaces the password with an unusable one | The password they have is gone for good, even after the account is re-enabled |
| Clears 2FA - TOTP secret and backup codes | The enrolled authenticator may be the attacker's; leaving it would preserve their second factor and lock the real user out after their password reset |
| Invalidates outstanding password reset and email confirmation tokens | A link already in an inbox is another way back in |
| Logs `user.disabled` at warning, with the user id and the admin's id | The record of who did it, for a sysadmin reading the logs |

**No email is sent to the user.** If we suspect a compromise, whoever has the
account may also have the mailbox, and telling them tips our hand.

The password is destroyed, not stashed. There is no undo — the user sets a new
one when the account comes back.

An admin cannot disable their own account.

## Re-enabling an account

From the same page: **Enable Account**. This sets the active flag and emails the
user, and that is all. In particular:

- **The cancelled sessions stay cancelled.** Re-enabling must not bring the
  attacker's browser back to life, so the session epoch is left where the
  lockout put it.
- **The password stays unusable.** The email points the user at
  `/auth/forgot-password`, where they ask for a reset link in the normal way.
  We deliberately do not put a reset token in the email: a token lives one hour,
  and an account re-enabled out of hours would otherwise arrive with a dead link.
- An OAuth-only user is told to sign in with their provider as before — there is
  no password for them to reset.
- If their 2FA was cleared by the lockout, the email says so, and they set it up
  again from their profile.

## What lockout does *not* cover

Worth an operator's attention, because none of it is automatic:

- **OAuth links are left in place.** If the account was compromised *through*
  their Google or Microsoft account, being locked out of OpenDLP does not fix
  that — the provider account needs attention too. Once it is clean, the user
  carries on with the same login.
- **Invites the user created still work.** Someone sitting on a compromised
  admin account can mint an invite code and register a second account, which
  survives the lockout completely. Disabling logs a
  `user.disabled.outstanding_invites` warning with the invite **ids** (never the
  codes, which are credentials) so a sysadmin can revoke them from
  Site Admin → Invites. Deciding which to revoke is a judgement call, so it is
  not automatic.
- **Assembly roles are untouched.** They come back with the account, which is
  usually what you want.

## How sessions are actually cancelled

`User.sessions_invalidated_at` is a timestamp, and `User.get_id()` returns
`"<user id>|<that timestamp>"`. Flask-Login stores that value in both the
session and the remember-me cookie and hands it back to the `user_loader`, which
rejects anything whose epoch no longer matches. So moving the timestamp
invalidates both at once, with no session store to sweep and nothing that a
surviving cookie can do about it.

Two consequences worth knowing:

- Deleting sessions from Redis by hand is neither necessary nor sufficient — the
  remember-me cookie would just mint a fresh one.
- Changing the format of `get_id()` signs everybody out. That is what happened
  when this shipped, and it was deliberate.
