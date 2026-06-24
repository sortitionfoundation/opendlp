<!-- ABOUTME: Research and design options for redacting PII (emails) and secrets from application logs. -->
<!-- ABOUTME: Background for issue #617; captures current state, interception points, and options with pros/cons. -->

# 617 — Log redaction (PII / secrets out of logs)

## Problem

Logs that contain personal data (e.g. email addresses) could be considered a
GDPR breach. We want:

1. **A redaction safety-net** — code that filters email addresses (and ideally
   other sensitive info: API keys, passwords, tokens) out of logs *before they
   are written*, regardless of which log statement produced them.
2. **A deliberate audit** — find our own log messages that contain email
   addresses and change them to log a UUID (`user.id`) instead.

These two are complementary, not either/or. Redaction is the seatbelt that
catches accidents and third-party libraries; the audit is the correct
long-term fix (don't put PII in logs in the first place).

## Decisions (from review)

The options below are kept for context, but the agreed approach after review is:

- **Step 0 — logger consistency: S1.** Standardise on
  `structlog.get_logger(__name__)` everywhere (services *and* blueprints).
  Additionally, bind a per-request `request_id` (and other request context) via
  `structlog.contextvars` in a Flask `before_request` hook.
- **Redaction: Option B** — a structlog `censor_pii` processor. Viable
  *because* Step 0/S1 routes all our logging through structlog. **Hold off
  Option C** (formatter scrub) for now.
- **Audit: Option 1** — replace `user.email` with `user.id` in our log
  statements. The GDPR rationale is recorded below.
- **Console email adapter** — change it to write directly to `sys.stdout`
  instead of via `logger`, so it neither shows up in the email-in-log audit nor
  gets scrubbed by the redactor (it is dev-only and intentionally shows the
  real recipient).
- **Rate-limit-by-email** (`login_rate_limit_service.py:70`) — redact. Leaning
  towards an HMAC hash over simple masking; see that section for the rationale
  and the remaining decision.
- **Secret denylist** — seed from `header_safe()` only. **No** generic
  long-token / high-entropy heuristics, because we legitimately log UUIDs and
  may log password *hashes*, which such heuristics would flag as false
  positives.
- **Dev console** — redact in development too (not just production JSON).
- **Performance** — running a few regexes per log line is acceptable.

## Current state

### Logging architecture (`backend/src/opendlp/logging.py`)

- `structlog` is configured to hand off to **stdlib logging** via
  `structlog.stdlib.ProcessorFormatter.wrap_for_formatter`.
- Both renderers run *inside the stdlib handlers*:
  - prod: `JSONRenderer` via the `json` formatter on the `default` handler.
  - dev: `ConsoleRenderer` via the `console` formatter on the `dev_console`
    handler.
- The root logger sends to exactly one of these two handlers
  (`handler_to_use`).

**Key consequence:** every log record — whether emitted via
`structlog.get_logger()`, stdlib `logging.getLogger()`, or Flask's
`current_app.logger` — ultimately passes through the *same* stdlib
`StreamHandler`. That gives us a single chokepoint where a filter/formatter can
catch 100% of output.

### Logger usage is mixed (this drives the design)

The codebase uses three styles, and crucially the **PII-heavy modules use
stdlib logging**, not structlog:

| Style | Modules |
|---|---|
| stdlib `logging.getLogger(__name__)` | `user_service`, `password_reset_service`, `email_confirmation_service`, `email_send_service`, `login_rate_limit_service`, `adapters/email.py` |
| `structlog.get_logger(__name__)` | `sortition`, `monitoring`, `target_checking` |
| Flask `current_app.logger` | blueprints: `admin.py`, `auth.py`, `profile.py` |

Implication: a redaction approach that only hooks the **structlog processor
chain** would miss most of our actual PII *as the code stands today*. Step 0
(S1) removes that problem by moving everything onto structlog, which is what
makes the chosen Option B viable.

### Confirmed email-in-log sites (the audit target)

| File:line | What's logged |
|---|---|
| `adapters/email.py:110-118` | Console adapter logs full `To:`, `From:`, `Reply-To` + body preview |
| `service_layer/email_confirmation_service.py:139,141,146` | `user.email` |
| `service_layer/password_reset_service.py:320,322,327` | `user.email` |
| `service_layer/user_service.py:1051,1053,1058` | `user.email` for assembly-role emails |
| `service_layer/login_rate_limit_service.py:70` | `email` as a **structured arg** (`"...: %s", email`) |
| `entrypoints/blueprints/admin.py:346,501,503,508` | `form.email.data` / `email_address` |

`login_rate_limit_service.py:70` is notable: the email is a structured
positional arg, not interpolated text. This is the case that separates
"redact the rendered message string" from "redact structured fields" — see
options below.

**Console email adapter (decided):** the `ConsoleEmailAdapter`
(`adapters/email.py:110`) is dev-only, so no production recipient addresses
pass through it. Rather than rely on redaction here (which would actually
*defeat* its purpose — the whole point is to show the developer the real
email), we will change it to write directly to `sys.stdout` instead of through
`logger`. Benefits:

- It no longer appears in the "email-in-log" audit, because it is not a logging
  call.
- It is unaffected by the redactor, so the dev experience (seeing the real
  recipient and body preview) is preserved.

This is a small, self-contained change that should land as part of Step 0 / the
audit.

### Secrets/tokens in logs

No passwords, tokens or secrets are currently interpolated into log messages:

- `password_reset_service` only logs `user.email` (not the token).
- QR-code / 2FA / backup-code sites log `current_user.id`, not secrets.
- `celery/tasks.py:876` logs a *count* of cleaned-up tokens, not the tokens.

Existing partial guard: `GunicornLogger.header_safe()` in `logging.py` already
maintains a denylist of header names (`authorization`, `cookie`, `csrf_token`,
and partials `api-key`, `api_key`, `security-token`) to avoid logging
sensitive request headers. We will **reuse this list as the seed** for a
secrets denylist so there is one source of truth.

**Decided — no generic high-entropy/long-token heuristics.** We legitimately
log UUIDs (all primary keys are UUIDs) and may log password *hashes*; a
generic "long random-looking string → redact" rule would produce false
positives on exactly those. Stick to the name-based denylist for now.

Residual risk for secrets: exception messages / tracebacks, third-party
library logging, and future code. The name-based denylist plus the email regex
covers the realistic cases without the false-positive cost.

## Where redaction can be inserted

Because of the funnel-through-stdlib architecture, there are three candidate
interception points. Their coverage differs:

1. **stdlib `logging.Filter` on the handlers** — sees every record from every
   logger style. Operates on `record.msg` + `record.args` before formatting.
2. **structlog processor** (in `processors=[...]` and `foreign_pre_chain`) —
   sees the structured `event_dict`. Covers structlog calls via the main chain
   and *foreign* (stdlib / third-party) records via `foreign_pre_chain`.
3. **redacting `Formatter`** — sees the fully rendered output line (JSON or
   console string) last, regardless of origin.

## Options — redaction safety-net

### Option A — stdlib `logging.Filter` on the handlers

A `RedactingFilter` added to the `default` and `dev_console` handlers (or to
the root logger). Regex-scrubs `record.msg` and `record.args`.

- **Pros:** single chokepoint covers all three logger styles; minimal change
  to existing `dictConfig`; stdlib-native and easy to unit-test.
- **Cons:** a `Filter` runs *before* formatting, so for the structlog JSON
  path some PII lives inside the wrapped `event_dict` and a naive
  `record.getMessage()` scrub can miss structured fields. Needs care, or pair
  with Option C.
- **Status:** not chosen. Was the forced choice *before* Step 0 because of the
  stdlib-heavy reality; Step 0/S1 removes that constraint and makes Option B
  cleaner.

### Option B — structlog processor ✅ chosen

Insert a `censor_pii` processor into `structlog.configure(processors=[...])`
**and** into `foreign_pre_chain`.

- **Pros:** operates on the structured `event_dict`; can target specific keys
  (e.g. always redact an `email` key) precisely, before rendering; idiomatic
  for structlog; field-aware redaction is more accurate than string regex.
- **Cons (as originally noted):** misses plain stdlib `logging.getLogger()`
  calls, and `foreign_pre_chain` coverage is easy to get wrong.
- **Why it's now viable:** Step 0/S1 moves all of *our* logging onto structlog,
  so the main processor chain covers our PII. Third-party / stdlib records
  (e.g. gunicorn, `requests`) still reach the same handlers and are covered by
  adding the same processor to `foreign_pre_chain`. Implementation note: the
  processor must be registered in **both** places to get full coverage — this
  is the "easy to get wrong" part and should have an explicit test.

### Option C — redacting `Formatter` (scrub final rendered string)

Subclass/wrap the formatter so the fully-rendered line is regex-scrubbed last.

- **Pros:** catches PII no matter how it entered — interpolated, structured, or
  inside an exception traceback; format-agnostic.
- **Cons:** sloppy regex over rendered JSON can corrupt structure; operates on
  strings (slightly more CPU); can't make field-aware decisions.
- **Status:** deferred. Keep as a possible future hardening layer if we find
  PII leaking through tracebacks or paths Option B doesn't see.

### Option D — combination A + C (defense in depth)

- **Pros:** filter handles common interpolated cases cheaply; formatter catches
  anything that slips through, including tracebacks and structlog fields.
  Highest coverage.
- **Cons:** two places to maintain; minor duplication / perf cost.
- **Status:** not chosen for now (superseded by Step 0 + Option B).

**Decision:** **Step 0 (S1) then Option B.** Hold Option C in reserve.

## What to match (regex / denylist strategy)

- **Email:** `[\w.+-]+@[\w-]+\.[\w.-]+` → `[EMAIL_REDACTED]`. Cheap,
  high-value, low false-positive.
- **Sensitive key/value pairs** (API keys, passwords, tokens): a **denylist of
  key names** (`password`, `secret`, `token`, `api_key`, `authorization`,
  `csrf`, `client_secret`, …) seeded from the existing `header_safe()`
  denylist. Because Option B is field-aware, this is primarily a check on
  `event_dict` keys (redact the *value* when the key matches), with a fallback
  regex for `key=value` / `"key": "value"` patterns embedded in message
  strings.
- **No** bearer-token / long-hex/base64 heuristics — see the "no generic
  high-entropy heuristics" decision above (UUIDs and password hashes would be
  false positives).

**Trade-offs:** regex redaction has false negatives (obfuscated/split data) and
false positives (redacting something you wanted intact), plus a small per-line
CPU cost (accepted). Treat it as a net, not a guarantee — which is why the
deliberate audit matters.

## Options — deliberate audit (email → UUID)

### Option 1 — replace `user.email` with `user.id` in our log statements ✅ chosen

e.g. `logger.info("Password reset email sent", user_id=user.id)` (structured,
post-S1).

- **Pros:** no PII at rest in logs — correct GDPR posture; UUIDs still allow
  correlation/debugging back to a user *while the user exists*.
- **Cons:** manual; the `login_rate_limit_service` case has *only* the email
  pre-auth (no UUID available) — handled separately below; loses human
  readability when eyeballing logs.

**GDPR expectation (recorded):** logging `user.id` is GDPR-compatible and
aligns with the project's "right to be forgotten" strategy (see
`backend/CLAUDE.md` → *GDPR and the right to be forgotten*). While a user is
live, the UUID can be used to look up their email; but when a user is
"deleted" we blank their data fields (including email) while keeping the row
and its UUID. After deletion the UUID can **no longer** be used to identify the
person — so historical logs that contain only the UUID are not personal data at
that point. This is exactly the property we want: the log keeps a stable
correlation key without being a durable copy of PII.

### Option 2 — redaction-only, leave statements as-is

- **Pros:** zero churn in service code.
- **Cons:** relies entirely on the regex net; the email was assembled in
  memory and could leak via a path the regex misses.
- **Status:** not chosen.

**Decision:** Option 1 for our own code (bounded list — the sites above) **plus**
the redaction net (Option B) for everything else and future code.

### Rate-limit-by-email (`login_rate_limit_service.py:70`)

This logs the email pre-auth, where no `user.id` exists. Options:

- **Partial mask** — e.g. `a****b@gmail.com`. Cheap and somewhat human
  readable, but it still leaks the domain and the first/last local-part
  characters, and for short local parts reveals most of the address. A masked
  but re-identifiable email can still count as personal data under GDPR, so
  this only *reduces* exposure rather than removing it.
- **HMAC hash** (recommended) — `HMAC-SHA256(SECRET_KEY, normalised_email)`,
  truncated (e.g. first 12 hex chars). Not reversible without the secret, but
  *stable*: the same email always yields the same token, so we can still spot
  "many attempts against one account" — which is the actual purpose of this log
  line. Cost: not human readable, and needs the app secret available at that
  call site.

**Recommendation / remaining decision:** use the **HMAC hash**. It satisfies
GDPR better than masking while preserving the correlation we need. Masking is
an acceptable lighter-weight fallback if we decide the residual domain/initial
leakage is fine for this one line — flagging this as the one point that still
needs Hamish's sign-off.

## Step 0 — make logger usage consistent (prerequisite) — S1 chosen

Today three logging styles coexist (see "Logger usage is mixed" above). This
matters for redaction in two ways:

- **Coverage:** the chosen field-aware redactor (Option B) is cleanest if
  everything flows through structlog.
- **The audit:** logging `user.id` as a *structured field*
  (`logger.info("...", user_id=user.id)`) is cleaner and machine-queryable —
  and consistently available only if we standardise the call style.

Standardising first means the redaction layer has one well-defined path to
guard, and later code has one obvious pattern to copy.

### Decision: Option S1 — standardise on `structlog.get_logger(__name__)` everywhere

Convert the stdlib `logging.getLogger(__name__)` module loggers **and** the
blueprint `current_app.logger` calls to a module-level `structlog` logger.

- **Pros:** structured key/value logging throughout (enables field-aware
  redaction via Option B *and* clean `user_id=` audit fields); one idiom for
  new code; aligns with the already-configured structlog stack.
- **Cons / things to verify:** largest diff; need to confirm structlog's
  `merge_contextvars` gives us the request context we'd otherwise get from
  Flask's `current_app.logger`.

(Options S2 "all stdlib" and S3 "structlog for services, keep
`current_app.logger` in blueprints" were considered and not chosen. S2 pushes
toward harder-to-redact string interpolation; S3 leaves two styles and keeps
blueprint email sites on string interpolation.)

### Additional Step 0 task — per-request context via `structlog.contextvars`

Add a Flask `before_request` (and matching teardown) hook that binds a
`request_id` (a fresh UUID per request) plus useful request metadata into
`structlog.contextvars`, following the Flask example in the structlog docs:
<https://github.com/hynek/structlog/raw/refs/heads/main/docs/contextvars.md>.

- The config already includes `structlog.contextvars.merge_contextvars` in the
  processor chain, so anything bound there is automatically attached to every
  log line emitted during the request.
- Pattern: `clear_contextvars()` at request start, then
  `bind_contextvars(request_id=..., ...)`. This gives us request correlation in
  logs without threading an id through call signatures — and pairs well with
  logging `user_id` instead of email for traceability.
- Be careful **not** to bind PII (e.g. email) into contextvars, or it would
  appear on every line; bind `user_id` if anything.

## Proposed shape of the work

0. **Make logger usage consistent (S1)** — convert all stdlib and
   `current_app.logger` usage to module-level `structlog` loggers; add the
   `before_request` `request_id` binding via `structlog.contextvars`. Also
   change `ConsoleEmailAdapter` to write to `sys.stdout` directly.
1. New module `backend/src/opendlp/log_redaction.py`: a `censor_pii` structlog
   processor (Option B) with the email regex + a sensitive-keys denylist seeded
   from `GunicornLogger.header_safe`.
2. Wire the processor into **both** `structlog.configure(processors=[...])` and
   the `foreign_pre_chain` in `logging.py`.
3. Audit + edit the email log sites to use `user.id` / structured `user_id=`
   (and implement the rate-limit-by-email hashing/masking decision).
4. Tests: assert emails/keys are scrubbed across JSON and console renderers,
   and that **both** a structlog call *and* a foreign/stdlib call (via
   `foreign_pre_chain`) are covered.

## Open questions for review

- **Rate-limit-by-email logging** (`login_rate_limit_service.py:70`): confirm
  **HMAC hash** (recommended) vs partial mask `a****b@gmail.com`. This is the
  one remaining open decision.
- **Step 0 scope check:** S1 implies touching the blueprints' `current_app.logger`
  calls. Confirm we're happy to include that in this issue's diff (vs splitting
  the blueprint conversion into a follow-up).

(Resolved in review: logger style = S1; redaction = Option B, defer C; audit =
Option 1 with the GDPR expectation recorded; secret denylist = name-based seed
only, no high-entropy heuristics; redact in dev too; per-line regex cost
acceptable; console adapter → `sys.stdout`.)
