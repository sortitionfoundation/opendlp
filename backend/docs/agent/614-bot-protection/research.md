# Protecting OpenDLP registration pages from bots

## Background

OpenDLP hosts public registration pages as part of a two-stage lottery. The first stage
invites people to register; the second stage picks a broadly representative sample from
those who registered.

The invite channel varies by job:

- **Paper (the usual UK case).** Invites go "to the resident" at an address selected from
  the Postcode Address File. The letter carries a QR code and a short URL you can type in.
  The typed URL must be short, and to keep printing costs down we use the **same QR code
  and URL on every invite** rather than varying them per recipient. The letter also gives a
  **phone number**, answered by a call-centre agent who fills in the web form on the
  caller's behalf.
- **Resident database (some countries).** Where a register of residents exists, we can
  invite **named individuals** at addresses.
- **Door-knocking.** In some contexts the first stage selects points on a map and people go
  out and knock on doors.
- **Email (a few jobs).** We select email addresses from a database and email the invites
  directly. These jobs **could** use long, unique per-recipient URLs.

This document plans how to protect the public registration pages from bots. The
registration links are not publicly advertised, but might still be found and indexed. The
starting ideas were a CAPTCHA or sitting behind a CDN that filters abusive clients. But the
registration page should be **as accessible as possible** so we get the widest possible
range of people signing up — and a CAPTCHA makes the page less accessible. It's also
unclear how good CDNs really are at stopping bots.

One existing mitigation: for **many (but not all)** jobs we have a list of the addresses we
mailed. Today, in a spreadsheet, we check whether the address typed into the form matches
one on that list and flag any that don't. We then manually review the flagged ones — some
are just a different format or a minor typo we can correct. This gives some spam resistance
(really bad addresses don't reach selection), but it costs manual review, so we don't want
loads of bad entries to wade through. Crucially, **this check isn't available for every
job, and it isn't yet built into OpenDLP.**

## Threat model (what we're actually defending)

Where we have a mailed-address list, the cross-check is a strong **integrity** control:
bots don't know which addresses we selected, a random UK address has a negligible chance of
being in our sample, so bot submissions don't match and don't reach selection. But two
caveats matter:

- **It isn't universal.** Some jobs have no address list (e.g. door-knocking, or jobs where
  we simply weren't given one). For those, there is no address backstop, so junk
  registrations land directly in the pool — we need protection that stands on its own.
- **It isn't built yet.** Address matching in OpenDLP is later work (see the roadmap
  below). For now we can't rely on it at all.

So the harms we're defending against are:

1. **Junk registrations polluting the pool** — most acute for jobs with no address list,
   where nothing else filters them out.
2. **Manual review volume** — for jobs _with_ a list, every non-matching submission is
   eyeballed by a human. The main ongoing cost.
3. **Email cost / abuse** — the registration auto-reply lets a bot fire mass emails, or
   repeatedly submit a victim's address to email-bomb them.

Residual integrity caveat even with a list: matching is only as strong as the secrecy of
_which_ addresses we picked. It holds against bots and outsiders; it doesn't stop someone
holding several genuinely-invited letters (a social problem, not a bot one).

**Design goal: cut junk volume invisibly, before it reaches the pool, the review queue, or
the mailer. No user-visible friction in the normal case.**

## Constraints that shape the design

- **Paper is the default channel.** Same QR code + same short URL on every letter (printing
  cost). → The short URL is effectively public and will leak/index. **Per-invite tokens are
  not available for paper jobs.** "Did we invite them" = the address match (where we have
  one), not the URL.
- **Phone channel → call-centre agents fill in the public form** on people's behalf. Volume
  here is **very low**: a typical job sees a few hundred web registrations over a few days,
  with the call-centre handling **under 5%** of them — at peak unlikely to exceed ~10
  submissions an hour, and that would be a busy job. The call-centre also serves many
  clients, not just us, so we want to keep their workflow simple.
- **Email jobs are occasional** and _can_ carry long unique links — a nice-to-have if
  cheap, not something to rely on generally.
- **GOV.UK design system + EU/UK org** → accessibility and GDPR both matter. CAPTCHA is out
  (excludes the very demographics sortition works to include; reCAPTCHA is a GDPR problem;
  GDS discourages it).

## Call-centre handling

Because agent submissions are humans typing one form at a time, they won't trip the
honeypot or timing checks, and at ~10/hour they sit well under any _loosely_ set rate
limit. So the realistic options, simplest first:

1. **No special treatment.** Given the low rate, a loose rate limit shouldn't catch them
   and the invisible checks don't apply to a real person filling the form. Quite possibly
   sufficient.
2. **Secret-token URL** — e.g. `/register/<slug>?call_centre=<UUID>`. No login; the agent
   just uses a bookmarked link carrying a secret token only they hold. Submissions via that
   token are exempted from rate limits and flagged as call-centre-entered (a useful audit
   signal). Simplest explicit option, and keeps the agents' lives easy.
3. **Authenticated internal route** — strongest audit trail, but adds friction. Whether the
   call-centre is willing to sign in is **an open question to settle with the team**, given
   we're one of many customers they serve.

Recommendation: lean towards option 1 or 2; only pursue authentication (3) if we
specifically want the audit trail and the call-centre is happy with it.

## Recommended layers (all invisible to legitimate users)

These are the core of the **current round of work** — they don't depend on address data.

1. **Honeypot field + form-timing token + existing CSRF.** Kills the bulk of dumb form bots
   at zero accessibility cost. (Honeypot via `aria-hidden`/off-screen, not a
   `display:none` keyboard trap; piggyback the timing token on the CSRF token we already
   mint at render.)

2. **Rate limiting** — reuse the existing `login_rate_limit_service` / Redis pattern:
   - **Per-IP**, kept _loose_ (shared NATs: libraries, care homes, offices), and loose
     enough not to catch the low-rate call-centre.
   - **Per-email rate limit** — closes the auto-reply email-bomb / cost vector. Note this is
     a _low rate limit, not a cap of 1_: we occasionally get a couple (e.g. an elderly pair)
     sharing one email address who both legitimately register, so allow a small number per
     email over the window rather than forbidding repeats.

3. **`noindex`** — `X-Robots-Tag: noindex` / robots meta so the leaked short
   URL doesn't get indexed. Cheap, invisible. (Obscurity isn't a control — the URL is on
   thousands of letters — but no reason to advertise it.)

## Later work (depends on address data, not yet in OpenDLP)

Address data isn't in OpenDLP yet, so the next two items are a **later round** — but worth
scoping now.

4. **Fold bot signals into the address-match step — the high-value change.** Once matching
   exists, each submission would be classified, and we add the bot signals to that decision:
   - **No match _and_ tripped a bot signal** (honeypot / impossible timing / rate) → mark as
     probable spam: no review, no auto-reply.
   - **No match but looks human** → review queue (today's spreadsheet behaviour).
   - **Match** → straight through.

   This directly attacks the review-volume pain: bots produce non-matching addresses _and_
   trip signals, so they fall into the probable-spam bucket and never cost a review or an
   email.

   _Data sketch (for when we get there):_ an `address_match` field with values
   `MATCH` / `NO_MATCH` / `TO_REVIEW`, plus a new `PROBABLY_SPAM` value on `RespondentStatus`.

5. **Tighten the auto-matcher itself** (the sleeper win — and something we'd like). Better
   fuzzy/normalised address matching shrinks the _legitimate-but-mistyped_ share of flags —
   probably a bigger chunk of the manual queue than spam — and makes the bucketing in (4)
   safer.

## Optional / situational

6. **Email-job signed links** — cheap with `itsdangerous`: sign a per-recipient token into
   the long URL, validate on load/submit. No schema change if not enforcing single-use
   ("this came from our email" is enough; the address match backstops it where present).
   Ship as an **opt-in per-assembly flag** for email campaigns. Gates bots out of those jobs
   entirely.

7. **Invisible challenge (Cloudflare Turnstile / Friendly Captcha / mCaptcha)** —
   back-pocket option for an _active_ flood only. Prefer the EU proof-of-work options for
   GDPR; never an image CAPTCHA.

8. **CDN/WAF** — Cloudflare (free tier) as a coarse outer filter for known-bad
   IPs and volumetric abuse. Cheap, invisible.

## Roll-out order

**This round (no address data needed):**

1. Call-centre handling — likely nothing, or the secret-token URL.
2. Honeypot + timing + per-IP / per-email rate limits.
3. `noindex` + CDN.

**Later (once address data lands in OpenDLP):**

4. Signal-into-match bucketing — submissions become a low-priority `PROBABLY_SPAM` bucket we
   spot-check; revisit auto-dropping once we see the volume.
5. Fuzzy-match improvements (ongoing).

**Only if needed:** email-job signed links and any challenge.

## Decisions

- **Call-centre path:** settled direction is to keep it simple — no special treatment or a
  no-auth secret-token URL. Authentication is an open question to raise with the call-centre
  team, only worth it for the audit trail.
- **Probable-spam handling:** start as a spot-check bucket (`PROBABLY_SPAM`), not a silent
  drop, and revisit once we see real volume.
