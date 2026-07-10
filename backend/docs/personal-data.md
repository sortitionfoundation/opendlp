# Personal Data

This is the canonical reference for how OpenDLP handles personal data: cookies, logging,
and the right to erasure. It exists so that the assumptions behind our current legal
position are written down, and so that anyone about to invalidate one of them finds out
before they ship it.

**If you are changing anything to do with cookies, sessions, logging of personal data,
analytics, third-party scripts, or data retention, read [What would change the
answer](#what-would-change-the-answer) first.**

Full reasoning behind the cookie conclusions: [docs/agent/656-cookies/research.md](agent/656-cookies/research.md).

## Why "personal data" and not "user data"

*User* is a domain term here — `domain/users.py` is an aggregate with roles and passwords.
The most sensitive personal data we hold belongs to **registrants**, who are explicitly not
`User`s. "Personal data" is the UK/EU GDPR term of art, and it correctly spans cookies
(device identifiers), log lines, registrants, users, and the IP addresses in our rate-limit
keys.

## Principles

These are standing constraints, not defaults. Changing one is a decision, not a refactor.

- **No advertising, ever.**
- **No analytics that sets a cookie or reads the device.** If analytics is added it must be
  cookieless and self-hosted. See [docs/analytics.md](analytics.md).
- **No third-party cookies. No cross-site or cross-device tracking.**
- **Bot protection stays server-side** — no Turnstile, reCAPTCHA or hCaptcha. See
  [docs/bot-protection.md](bot-protection.md).
- **Never log raw PII.**
- **No long-term copies of personal data that cannot be found and blanked.**

## The EU footing

**People in the EU are a key audience, and the service is hosted in the EU.**

This is the single fact most likely to be forgotten, and the one most likely to cause an
error. An EU establishment engages EU law directly. So:

- The UK Data (Use and Access) Act 2025 relaxations — the *statistical purposes* and
  *appearance* exceptions — are **unavailable to us**.
- Every cookie must clear the narrower EU ePrivacy test, which has only two exceptions:
  transmission, and strictly necessary for a service the user explicitly requested.
- **Any cookie-setting analytics would require prior opt-in consent**, with no UK escape hatch.

Do not reason from ICO guidance alone. It is the more permissive of the two regimes we are
subject to.

## Cookies

**This table is the source of truth.** The public cookies page at
<https://docs.sortitionlab.org/data-and-legal/cookies/> (configured by `HELP_SITE_COOKIES`)
is a copy of it written for a lay audience. **If you change this table, update the published
page too** — nothing fails when they diverge, and an inaccurate cookies page is a compliance
failure in a way that an inaccurate help page is not.

There are exactly two cookies. Both are first-party and `HttpOnly`.

| Cookie | Set by | When | Lifetime | Purpose |
|---|---|---|---|---|
| `session` | Flask-Session | CSRF token generation, `flash()`, `?lang=` selection, 2FA, OAuth start | 7 days | Security (CSRF), sign-in, form messages, language choice |
| `remember_token` | Flask-Login | Only when the user ticks "keep me signed in" | 7 days in production | Persistent login |

Notes:

- `SESSION_TYPE = "redis"` means the session *payload* lives in Redis, but a browser-side
  cookie carrying the session id is still set. Server-side sessions do not avoid the cookie.
- There is **no separate CSRF cookie** — Flask-WTF stores the CSRF secret inside the session.
- There is **no language cookie** — the choice is stored under the `"language"` key inside
  the session.
- No `localStorage`, no `sessionStorage`, no `document.cookie` anywhere in `static/`.
- **`REMEMBER_COOKIE_DURATION` is set to 7 days only in `FlaskProductionConfig`.** Outside
  production the cookie inherits Flask-Login's default of **365 days**. Production is what
  the public sees, so the published page is accurate — but a non-production deployment with
  real people on it would hand out year-long cookies. Worth fixing; see
  [research.md §8.10](agent/656-cookies/research.md).

### We do not need a cookie banner

Every cookie above falls within a statutory exception to the consent requirement, under both
UK and EU law:

- **`session`** is strictly necessary for security (CSRF), authentication, and recording the
  user's own form input. All are expressly exempt.
- **`remember_token`** is *not* strictly necessary — but the checkbox **is** the consent. It
  is a specific, informed, unambiguous, affirmative act, unticked by default. That is textbook
  GDPR-standard consent, and it is why the label names the cookie rather than saying
  "Remember me".
- **The language choice** rides on the `session` cookie. We rely on the argument that a user
  who clicks "Español" has explicitly requested the service of being shown Spanish, which puts
  it back inside *strictly necessary*. This is the one place a lawyer might quibble; the
  reasoning is set out in [research.md §4.1](agent/656-cookies/research.md).

GOV.UK guidance is explicit that an essential-cookies-only service may skip the banner, but
must still have a cookies page linked from the footer. That is what we do — all three footers
(`base.html`, `base_public.html`, `backoffice/components/footer.html`) carry the link.

A banner offering nothing to reject would be consent theatre. The ICO criticises it, and it
would put friction on the public registration form — the one interaction we most need to
succeed, completed by people invited by post who may not be confident internet users.

**Legal sign-off status: not yet obtained.** The analysis in `research.md` is the work of a
careful non-lawyer. Sign-off is a merge gate for issue #656. Do not cite this document as
legal advice.

### The published page is English-only

The docs site is not translated, so a Hungarian- or Spanish-speaking registrant on the public
form gets a footer link to an English page. This is a **deliberate trade**, made to keep legal
copy out of the deploy cycle so a wording fix does not require a release.

It is not a legal defect — the duty is to give "clear and comprehensive information", with no
language mandate, and none of our cookies require consent in the first place. But it is a real
accessibility regression for exactly the audience the public form exists to reach. If the
language mix of registrants ever makes it bite, the remedy is to translate the page, or to
serve it from the app.

## Logging

Logs are long-lived and widely accessible, so they must never become a copy of personal data
we would then have to find and blank for an erasure request.

The principle: **log a stable identifier, never the person.** Log `user_id` (a UUID), which
survives erasure because the row is blanked rather than deleted. Where no UUID exists yet —
pre-auth, login rate limiting — hash the value instead.

`log_redaction.censor_pii` redacts emails and sensitive field names from all log output. It
is a **backstop, not a licence**: it cannot redact a name or address embedded in the free text
of an exception message.

The code-level rules — `structlog.get_logger`, structured key/value fields, `hash_email`, and
the trap in `error=str(e)` — live in
[docs/agent/code_quality_rules.md](agent/code_quality_rules.md#logging-pii--secrets). That is
the right altitude split: this file says what you may do and why, that one says how to write
the log call. Design notes: [docs/agent/617-log-redaction/](agent/617-log-redaction/).

Note that our bot-protection rate-limit keys contain **IP addresses**, which are personal
data. They are retained only for the counter's TTL.

## GDPR and the right to be forgotten

We must support people asking for their details to be deleted, which means we must be able to
find every persistent copy of someone's details easily.

**The strategy is to blank the details but keep the row**, with its unique ID intact. Anything
referring to that ID keeps a valid reference, and learns that the details are gone.

The consequence, which is a hard constraint: **we must not hold copies of personal data in
long-term storage that cannot be easily found and blanked.** In particular, no long-term copies
of uploaded or generated files (CSV, Excel) in the database or on disk. Such files may be held
in memory, written into a data attribute of an HTML page sent to the user, placed in a download
directory that is regularly swept, or cached in Redis.

When adding a table that holds personal data, add a corresponding `DELETE` to
`_delete_all_test_data()` in `tests/conftest.py` and to `delete_all_except_standard_users()` in
`tests/bdd/conftest.py`, respecting foreign-key ordering.

## What would change the answer

**If you are about to do any of the following, this document is now wrong, and you must revisit
[issue #656](agent/656-cookies/research.md) before shipping.**

- Adding **any analytics**, or any third-party script or embed — including a font, a map, a
  video player, or an error reporter such as Sentry.
- Adding **any new cookie**, or any use of `localStorage`, `sessionStorage` or `document.cookie`.
- Making an existing cookie **persistent**, or lengthening its lifetime.
- Using an existing cookie for a **new purpose**. Every purpose must independently qualify for
  an exception — a cookie that is exempt for CSRF is not automatically exempt for anything else.
- Replacing the honeypot bot protection with **Turnstile, reCAPTCHA or hCaptcha**.
- Adding a **dedicated language cookie**, or otherwise changing how the language preference
  persists.
- Writing a `flash()` or a CSRF token into **the front page** (`main.index`). It currently sets
  no cookie for an anonymous visitor, and
  `tests/unit/test_flask_app.py::test_index_sets_no_cookie_for_anonymous_visitor` will fail if
  that changes. That test failing is a signal to think, not a signal to update the assertion.
- Storing personal data anywhere it **cannot be found and blanked** on request.

Most of these need a cookie consent banner, which we do not have and do not want. All of them
need a decision, not a commit.

## Related documentation

- [docs/agent/656-cookies/research.md](agent/656-cookies/research.md) — the full legal analysis
- [docs/analytics.md](analytics.md) — why we have none, and what to do if you add some
- [docs/bot-protection.md](bot-protection.md) — honeypot, timing token, rate limits
- [docs/translations.md](translations.md) — language detection and the session preference
- [docs/agent/code_quality_rules.md](agent/code_quality_rules.md#logging-pii--secrets) — how to write a safe log call
- [docs/configuration.md](configuration.md) — `SESSION_COOKIE_*`, `REMEMBER_COOKIE_*`, `HELP_SITE_COOKIES`
