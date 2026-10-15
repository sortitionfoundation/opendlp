# Invite-URL signup flow

Agreed direction (Gergő + Hamish, via story
[sc-1053](https://app.shortcut.com/sortitionfoundation/story/1053) review,
2026-10-06): the invite code field disappears from the signup form as a thing
people type, and invites travel as **URLs**. Branch: on top of
`1053-signup-redesign` (which, in its own scope, only *hides* the optional
field — see the note in `templates/public/register.html`).

## Target behaviour

- **Default signup page** (`/auth/register`): no invite-code field at all. With
  open signup the form is just the signup form; with closed signup the page
  explains that an invite link is needed (no manual code entry — see open
  question 1).
- **Arriving via an invite URL** (`/auth/register/<code>`): the invite-code
  field becomes **visible but disabled, pre-filled** with the code — the
  registrant sees why their account will get the invite's role, but cannot
  mistype it. The code is carried to submission (a disabled input does not
  submit: carry it in a hidden input alongside the visible disabled one, or
  re-read it from the URL path on POST — decide in implementation).
- **Email, the same way (probably)**: `UserInvite` already has an optional
  `email` binding. When the invite carries an email, pre-fill the email field
  and disable it too, so the invite can only be redeemed for the address it was
  issued to. When the invite has no email, the field stays editable. (Gergő:
  "I am not sure, maybe the email should act the same way" — confirm before
  building, but the domain model supports it as-is.)
- Invalid/expired/used code in the URL: show the existing validation error and
  (per 1053's interim rule) the field, so the person understands what happened
  and can contact support.

## What already exists (verified on the 1053 branch)

- Route `GET|POST /auth/register/<invite_code>` pre-populates
  `form.invite_code` from the URL (`auth.py:461-477`) — the URL mechanism is
  live today; what's missing is the field chrome (disabled+prefilled) and the
  admin-side URL ergonomics.
- `UserInvite` domain (`domain/user_invites.py`): `code`, `global_role`
  (the "pre-set higher user role"), `created_by`, 7-day default expiry,
  single-use tracking (`used_by`/`used_at`), optional `email`.
- Admin invite management exists (`templates/admin/invites*.html`,
  `admin.list_invites_page` etc.) but is an old-design (GOV.UK) page and does
  not surface a copyable registration URL.

## Work breakdown

1. **Signup page** (frontend, public design system):
   - Remove the interim "hidden unless data/errors" conditional from
     `templates/public/register.html`; replace with: render the field only when
     a code is in play, as a disabled, pre-filled input (plus the hidden
     carrier input) with a hint like "This invite was created for you — the
     code is applied automatically."
   - Same treatment for the email field when the invite carries one.
   - Closed-signup variant: replace the "You need an invite code…" notice's
     instruction to *enter* a code with "you need an invite link".
2. **Backend/process**:
   - POST handling: accept the code from the hidden carrier (or URL path),
     not from user-editable input; everything downstream
     (`_validate_invite_code_field`, role assignment on account creation)
     already keys off the code.
   - Decide whether `/auth/register?invite=<code>` (query) should also work for
     mail clients that mangle path segments; redirect to the canonical path if
     so.
   - DB: no schema change expected — `user_invites` already stores everything
     the URL needs. (If invite links should be revocable/regeneratable
     independent of the code, that would be new, but nothing agreed requires
     it.)
3. **Admin side — invite URL creation feature**:
   - On invite creation (and in the invites list), show the full registration
     URL (`https://<host>/auth/register/<code>`) with a copy-to-clipboard
     button, instead of a bare code to dictate.
   - Optional: "email this invite" action using the invite's bound email.
   - Note: the admin pages are old-design; decide whether this lands in the
     GOV.UK admin or waits for the backoffice admin redesign (sc-413) — a
     copy-URL cell in the existing list is small enough to do now.
4. **Tests**: BDD for arrive-via-URL → disabled prefilled field → successful
   registration with the invite's role; error paths (expired/used code);
   email-bound invite cannot be redeemed with a different email (if 'email the
   same way' is confirmed).

## Open questions

1. Closed signup (FF_OPEN_SIGNUP off): with manual entry gone, is an invite
   URL the *only* way in? (Today's 1053 interim keeps the visible required
   field for closed signup, so nothing breaks before this lands.)
2. Email lock: confirm the "email acts the same way" idea — it changes
   redemption semantics (invite becomes person-bound, not just role-bound).
3. Should an invite URL open a trimmed form (no SSO chooser?) when the invite
   is email-bound — SSO would register a (possibly) different address?
