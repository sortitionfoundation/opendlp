# Protecting OpenDLP registration pages from bots

## Threat model (what we're actually defending)

The registration page feeds a two-stage lottery, and we **already cross-check each
submitted address against the list of addresses we mailed**. That check is the real
integrity control: bots don't know which PAF addresses we selected, a random UK address
has a negligible chance of being in our sample, so bot submissions never match and never
reach selection.

So bot protection here is **not** about selection integrity. It's about two operational
harms:

1. **Manual review volume** — every non-matching submission is eyeballed by a human. This
   is the main cost.
2. **Email cost / abuse** — the registration auto-reply lets a bot fire mass emails, or
   repeatedly submit a victim's address to email-bomb them.

Residual integrity caveat: address matching is only as strong as the secrecy of *which*
addresses we picked. It holds against bots and outsiders; it doesn't stop someone holding
several genuinely-invited letters (a social problem, not a bot one).

**Design goal: cut junk volume invisibly, before it reaches the review queue or the
mailer. No user-visible friction in the normal case.**

## Constraints that shape the design

- **Paper is the default channel.** Same QR code + same short URL on every letter
  (printing cost). → The short URL is effectively public and will leak/index.
  **Per-invite tokens are not available for paper jobs.** "Did we invite them" = the
  address match, not the URL.
- **Phone channel → call-centre agents fill in the public form** on people's behalf: many
  submissions, one IP/device, fast. Any naive rate limit / timing / honeypot tuning **will
  block our own staff**.
- **Email jobs are occasional** and *can* carry long unique links — a nice-to-have if
  cheap, not something to rely on generally.
- **GOV.UK design system + EU/UK org** → accessibility and GDPR both matter. CAPTCHA is
  out (excludes the very demographics sortition works to include; reCAPTCHA is a GDPR
  problem; GDS discourages it).

## The call-centre carve-out (do this first)

Give agents a path that bypasses the public bot defences:

- **Recommended: an authenticated internal submission route** (we already have
  flask-login). Bypasses rate limits and bot checks, and gives an audit trail of
  agent-entered registrations.
- Alternative: IP-allowlist the call-centre egress.

Without this, the measures below will lock out staff.

## Recommended layers (all invisible to legitimate users)

1. **Honeypot field + form-timing token + existing CSRF.** Kills the bulk of dumb form
   bots at zero accessibility cost. (Honeypot via `aria-hidden`/off-screen, not a
   `display:none` keyboard trap; piggyback the timing token on the CSRF token we already
   mint at render.)

2. **Rate limiting** — reuse the existing `login_rate_limit_service` / Redis pattern:
   - **Per-IP**, kept *loose* (shared NATs: libraries, care homes, offices), **with the
     call-centre exempted**.
   - **Per-email-address cap** — this is what specifically closes the auto-reply
     email-bomb / cost vector.

3. **CDN/WAF + `noindex`** — Cloudflare (free tier) as a coarse outer filter for known-bad
   IPs and volumetric abuse, plus `X-Robots-Tag: noindex` / robots meta so the leaked
   short URL doesn't get indexed. Cheap, invisible. (Obscurity isn't a control — the URL is
   on thousands of letters — but no reason to advertise it.)

4. **Fold bot signals into the address-match step — the high-value change.** We already
   classify each submission as match / no-match. Add the bot signals to that decision:
   - **No match _and_ tripped a bot signal** (honeypot / impossible timing / rate) →
     **silently drop**: no review, no auto-reply.
   - **No match but looks human** → review queue (today's behaviour).
   - **Match** → straight through.

   This directly attacks the review-volume pain: bots produce non-matching addresses *and*
   trip signals, so they fall into the auto-drop bucket and never cost a review or an
   email.

5. **Tighten the auto-matcher itself** (orthogonal, but the sleeper win). Better
   fuzzy/normalised address matching shrinks the *legitimate-but-mistyped* share of flags —
   which is probably a bigger chunk of the manual queue than spam — and makes the auto-drop
   in (4) safer.

## Optional / situational

6. **Email-job signed links** — cheap with `itsdangerous`: sign a per-recipient token into
   the long URL, validate on load/submit. No schema change if not enforcing single-use
   ("this came from our email" is enough; the address match backstops it). Ship as an
   **opt-in per-assembly flag** for email campaigns. Gates bots out of those jobs entirely.

7. **Invisible challenge (Cloudflare Turnstile / Friendly Captcha / mCaptcha)** —
   back-pocket option for an *active* flood only. Prefer the EU proof-of-work options for
   GDPR; never an image CAPTCHA.

## Roll-out order

1. Call-centre authenticated route (unblocks everything else).
2. Honeypot + timing + per-IP/per-email rate limits.
3. Signal-into-match auto-drop — start as a **low-priority "probably-spam" bucket** you
   spot-check, then promote to silent drop once you trust the signals.
4. `noindex` + CDN.
5. Fuzzy-match improvements (ongoing).
6. Email-job signed links and any challenge only if needed.

## Two decisions to pin down

- **Call-centre path:** authenticated internal route (recommended) or IP allowlist?
- **Auto-drop policy:** silently discard "no match + bot signal", or hold in a spot-check
  bucket first? (Recommend bucket → drop.)
