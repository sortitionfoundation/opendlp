# Bot Protection for Registration Pages

## Overview

Registration pages are the public entry point for citizens' assemblies. They are linked from invitation letters — the same short URL on every letter for printing reasons — which means the URL can be discovered and indexed. This document describes the bot-protection layers that keep junk submissions out of the pool without adding any friction for legitimate users.

## Threat model

The harms we're defending against:

1. **Junk registrations polluting the pool** — most acute for assemblies with no address-list backstop.
2. **Manual review volume** — every non-matching submission costs a human reviewer.
3. **Email cost / abuse** — registration auto-replies let a bot fire mass emails, or email-bomb a victim's address.

Design goal: cut junk volume invisibly before it reaches the pool, review queue, or mailer. No user-visible friction in the normal case. See [research.md](agent/614-bot-protection/research.md) for the full threat analysis including later-round work (address-match integration, call-centre handling).

## Implemented layers

### 1. Honeypot field

A text input (`name="_opendlp_ttoken_"`) is injected into every registration form via the `csrf_form_element` template variable alongside the CSRF and timing-token inputs. It is hidden off-screen using CSS positioning (`position:absolute; left:-9999px`), marked `aria-hidden="true"`, and given `tabindex="-1"` so screen readers and keyboard users skip it entirely. `autocomplete="off"` prevents browser prefill.

If the field is non-empty on POST, the request is silently redirected to the thank-you page without saving. No respondent is created. The bot receives no signal that it was blocked.

### 2. Form-timing token

A signed timestamp (`itsdangerous.TimestampSigner`, salt `reg-timing`, key = Flask `SECRET_KEY`) is generated at form render time and embedded as a hidden input (`name="_timing_token"`). On POST the route verifies:

- The signature is valid (not forged → re-render with CSRF error message).
- The token is not older than 7 days (stale tab → re-render with "form was open too long" message).
- The form was submitted at least `REGISTRATION_MIN_FILL_SECONDS` (default 3 s) after render (too fast → silently redirect to thank-you).

The timing check is gated on its own `REGISTRATION_TIMING_CHECK_ENABLED` flag (CSRF is gated on `WTF_CSRF_ENABLED`). Both default to on and are disabled in the test config, so happy-path tests need not mint tokens; timing tests re-enable just the timing gate without a CSRF round-trip.

### 3. Rate limiting

`registration_bot_protection_service` maintains two Redis counters per submission:

| Dimension | Default limit | Window | Env vars |
| --------- | ------------- | ------ | -------- |
| Per source IP | 30 submissions | 1 hour | `REGISTRATION_RATE_LIMIT_PER_IP` / `REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES` |
| Per email address | 5 submissions | 24 hours | `REGISTRATION_RATE_LIMIT_PER_EMAIL` / `REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES` |

Limits are deliberately loose to avoid false positives from shared NATs (libraries, offices, care homes) and to allow e.g. two people sharing one email address to both register for the same assembly.

On a rate-limit hit the form is re-rendered with the message "Too many registrations from your location. Please try again later." Counters are incremented on every attempt (including syntactically invalid data), so bots still accrue counts even when they generate plausible-looking payloads.

### 4. `X-Robots-Tag: noindex`

A `registration_bp.after_request` hook adds `X-Robots-Tag: noindex` to all responses from the registration blueprint. Each registration template also carries `<meta name="robots" content="noindex">`. Both complement the existing `Disallow /register/` and `Disallow /r/` entries in `robots.txt`.

## Configuration

All limits are tuneable at runtime via environment variables — no deployment needed to tighten or loosen them:

| Env var | Default | Description |
| ------- | ------- | ----------- |
| `REGISTRATION_RATE_LIMIT_PER_IP` | `30` | Max registration attempts per IP per window |
| `REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES` | `60` | IP rate-limit window in minutes |
| `REGISTRATION_RATE_LIMIT_PER_EMAIL` | `5` | Max registration attempts per email per window |
| `REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES` | `1440` | Email rate-limit window in minutes (24 h) |
| `REGISTRATION_MIN_FILL_SECONDS` | `3` | Minimum seconds between form render and submit |

## Logging

Bot-detection events are logged at `WARNING` level. No personal data (email address, name, postal address) is ever logged. IP address is logged for suspected bots as standard security practice.

| Event | Log message |
| ----- | ----------- |
| Honeypot triggered | `Bot protection: honeypot triggered (IP: <ip>, slug: <slug>)` |
| Timing too fast | `Bot protection: timing check failed (IP: <ip>, slug: <slug>, age: <n>s)` |
| IP rate limit exceeded | `Bot protection: IP rate limit exceeded (IP: <ip>)` |
| Email rate limit exceeded | `Bot protection: email rate limit exceeded` |

## Redis keys

Rate-limit counters are stored with the following key patterns:

- `reg_ratelimit:ip:<ip_address>` — TTL = `REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES` × 60 seconds.
- `reg_ratelimit:email:<normalised_email>` — TTL = `REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES` × 60 seconds.

To inspect or reset a counter manually:

```bash
# Check current IP counter
redis-cli GET reg_ratelimit:ip:<ip>

# Reset an IP counter (e.g. to unblock a legitimate user)
redis-cli DEL reg_ratelimit:ip:<ip>

# Reset an email counter
redis-cli DEL reg_ratelimit:email:<email>
```

## Privacy assumptions

The current protection is honeypot + signed timing token + Redis IP counters. It **sets no
cookies and stores nothing on the user's device** — everything is a form field, a response
header, or a server-side counter.

This matters. Replacing it with **Turnstile, reCAPTCHA or hCaptcha** would introduce
third-party cookies and, for reCAPTCHA, a consent requirement — which is unworkable on a form
we need members of the public to complete. If you are considering that, read
[docs/personal-data.md](personal-data.md) first.

Note also that the rate-limit keys above contain **IP addresses and email addresses**, which
are personal data. They are retained only for the counter's TTL.

## The account signup form: Cloudflare Turnstile

The **account signup form** (`/auth/register`) — a different audience from registrants:
people choosing to run or help run an assembly — additionally carries a Cloudflare
Turnstile widget (issue #890). With open signup enabled (`FF_OPEN_SIGNUP`) there is no
invite gate, so the per-IP signup rate limit was the only defence against scripted account
creation; Turnstile adds a challenge the rate limit cannot provide without locking out
shared IPs.

How it is wired:

- **Off by default.** An empty `TURNSTILE_SITE_KEY` renders no widget, loads no
  third-party script, and skips the server-side check entirely.
- The widget (`managed` mode, action `signup`) is embedded in
  `templates/auth/register.html`; the script and challenge iframe are allowed through the
  CSP for `challenges.cloudflare.com` only.
- The route gates on `verify_turnstile_token()` (`adapters/turnstile.py`), the canonical
  server-side siteverify call. It requires `success`, the `signup` action, and a frontend
  hostname listed in `TURNSTILE_HOSTNAMES` — and fails closed on any network error.
  Tokens are single-use; a replayed token is rejected by Cloudflare.
- The OAuth signup routes (`/auth/register/google`, `/auth/register/microsoft`) are not
  gated — the OAuth provider is the bot check there.

| Env var | Default | Description |
| ------- | ------- | ----------- |
| `TURNSTILE_SITE_KEY` | *(empty)* | Public widget sitekey; empty disables the feature |
| `TURNSTILE_SECRET` | *(empty)* | Widget secret used for siteverify; keep out of git |
| `TURNSTILE_HOSTNAMES` | *(empty)* | Comma-separated frontend hostnames accepted from siteverify. Production must never list `localhost` or `127.0.0.1` |

The privacy position — why this widget is acceptable on the signup form and still not on
registration pages, and why **pre-clearance mode must stay off** — is documented in
[docs/personal-data.md](personal-data.md#third-party-scripts-the-turnstile-exception).

## Related documentation

- [Personal Data](personal-data.md) — cookies, logging, and the right to erasure
- [Frontend Security Guidelines](frontend_security.md) — CSP, nonce requirements, and JavaScript patterns
- [research.md](agent/614-bot-protection/research.md) — Full threat model, call-centre handling options, and later-round work (address-match integration, email-job signed links)
