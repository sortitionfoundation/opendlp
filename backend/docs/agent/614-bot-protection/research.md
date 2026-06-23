# Protecting OpenDLP registration pages from bots

COMMENT: a "Background" section would be useful here, so we're not diving straight in - I'll put in some of what I started the chat with, but feel free to neaten it up.

## Background

OpenDLP hosts public registration pages as part of a two-stage lottery. The first
stage is inviting people to register, the second stage is picking a broadly
representative sample from those who registered.

We normally send invites on paper. In the UK it is "to the resident" at an address selected from the Postcode Address File. The paper invite has a QR code and a URL you can type in. The URL to type in must be short. And to keep printing costs down we use the same QR code on all invites, rather than vary the QR code for each invite. The paper invite also has a phone number you can call - that is answered by a call centre person who will fill in the web form on your behalf.

In some countries there is a database of residents, so we can invite named individuals at addresses.

In other contexts the first stage of the lottery chooses points on a map, and
people go out and knock on doors.

And for a few jobs we select email addresses from a database, so we can directly email the invites. For those jobs we could use long unique URLs.

The idea of this document is to plan how to protect the public registration pages from bots. The links on the registration page will not be publicly advertised, but might still be found and indexed. The initial ideas are to use a CAPTCHA or be behind a CDN that will filter abusive clients. But the registration page should be as accessible as possible, so we get the widest possible range of people signing up. And a CAPTCHA makes the page less accessible. And I don't know how good CDNs are at stopping bots.

One step, is that for many (but **not** all) jobs we have a list of the addresses we have sent the invites too. We have a step (currently implemented in a spreadsheet) where we check if the address typed into the registration form matches an address from our list, and flag any that don't match. We then manually review the flagged addresses - some are just typed in a slightly different format to how we sent it, or have a minor typo that we can see and correct. This gives us some spam resistance - as really bad addresses won't get to the selection round - but we still need to manually review, so we don't want loads of bad entries to review. And this isn't available for all jobs.

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

Residual integrity caveat: address matching is only as strong as the secrecy of _which_
addresses we picked. It holds against bots and outsiders; it doesn't stop someone holding
several genuinely-invited letters (a social problem, not a bot one).

**Design goal: cut junk volume invisibly, before it reaches the review queue or the
mailer. No user-visible friction in the normal case.**

COMMENT: the majority of registration pages will be able to check against an address list, **but not all**. So we also need protection against junk registrations.

## Constraints that shape the design

- **Paper is the default channel.** Same QR code + same short URL on every letter
  (printing cost). → The short URL is effectively public and will leak/index.
  **Per-invite tokens are not available for paper jobs.** "Did we invite them" = the
  address match, not the URL.
- **Phone channel → call-centre agents fill in the public form** on people's behalf: many
  submissions, one IP/device, fast. Any naive rate limit / timing / honeypot tuning **will
  block our own staff**.

COMMENT: the number of registrations through the web is typically a few hundred over a few days, with the call-centre doing less than 5% of them. So their rate is very low. (And the call-centre handles calls for many clients, not just us.)
COMMENT: I'll have to talk to the team about whether the call-centre would be up for having to sign in. We are one of many customers the call-centre serves, so we want to make their lives simple.

- **Email jobs are occasional** and _can_ carry long unique links — a nice-to-have if
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

COMMENT: the call centre is, at peak, unlikely to do more than 10 submissions an hour. 10 call-centre submissions an hour would be a really busy job.

## Recommended layers (all invisible to legitimate users)

1. **Honeypot field + form-timing token + existing CSRF.** Kills the bulk of dumb form
   bots at zero accessibility cost. (Honeypot via `aria-hidden`/off-screen, not a
   `display:none` keyboard trap; piggyback the timing token on the CSRF token we already
   mint at render.)

2. **Rate limiting** — reuse the existing `login_rate_limit_service` / Redis pattern:
   - **Per-IP**, kept _loose_ (shared NATs: libraries, care homes, offices), **with the
     call-centre exempted**.
   - **Per-email-address cap** — this is what specifically closes the auto-reply
     email-bomb / cost vector.

COMMENT: we do occasionally have an elderly couple who share an email address who both register. In that case, both registrations would be legitimate. So the per-email address cap should not be 1. But it certainly can be low - especially as a rate limit.

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

   This directly attacks the review-volume pain: bots produce non-matching addresses _and_
   trip signals, so they fall into the auto-drop bucket and never cost a review or an
   email.

COMMENT: the address data is not yet in OpenDLP, so address matching would be a later step to do, not in the current round of work. But we should scope it out.
COMMENT: in terms of data, I would imagine, when we get there, we'd have an `address_match` field with values MATCH/NO_MATCH/TO_REVIEW - and we could add PROBABLY_SPAM to RespondentStatus

5. **Tighten the auto-matcher itself** (orthogonal, but the sleeper win). Better
   fuzzy/normalised address matching shrinks the _legitimate-but-mistyped_ share of flags —
   which is probably a bigger chunk of the manual queue than spam — and makes the auto-drop
   in (4) safer.

COMMENT: this would be great.

## Optional / situational

6. **Email-job signed links** — cheap with `itsdangerous`: sign a per-recipient token into
   the long URL, validate on load/submit. No schema change if not enforcing single-use
   ("this came from our email" is enough; the address match backstops it). Ship as an
   **opt-in per-assembly flag** for email campaigns. Gates bots out of those jobs entirely.

7. **Invisible challenge (Cloudflare Turnstile / Friendly Captcha / mCaptcha)** —
   back-pocket option for an _active_ flood only. Prefer the EU proof-of-work options for
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

COMMENT: for call centre, given the low rate, could they not need any special treatment? Or another option is that we provide a URL of `/register/slug?call_centre=<UUID>` - so no authentication, but a secret token only they would have access to
COMMENT: auto-drop should be bucket for now and we'll see how the volume goes
