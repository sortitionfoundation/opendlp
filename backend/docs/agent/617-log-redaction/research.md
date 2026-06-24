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
chain** would miss most of our actual PII. Whatever we build must cover stdlib
logging.

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

### Secrets/tokens in logs

No passwords, tokens or secrets are currently interpolated into log messages:

- `password_reset_service` only logs `user.email` (not the token).
- QR-code / 2FA / backup-code sites log `current_user.id`, not secrets.
- `celery/tasks.py:876` logs a *count* of cleaned-up tokens, not the tokens.

Existing partial guard: `GunicornLogger.header_safe()` in `logging.py` already
maintains a denylist of header names (`authorization`, `cookie`, `csrf_token`,
and partials `api-key`, `api_key`, `security-token`) to avoid logging
sensitive request headers. We should **reuse this list as the seed** for a
secrets denylist so there is one source of truth.

Residual risk for secrets: exception messages / tracebacks, third-party
library logging, and future code. So a generic secret-redaction net still has
value even though we have no current offenders.

## Where redaction can be inserted

Because of the funnel-through-stdlib architecture, there are three candidate
interception points. Their coverage differs:

1. **stdlib `logging.Filter` on the handlers** — sees every record from every
   logger style. Operates on `record.msg` + `record.args` before formatting.
2. **structlog processor** (in `processors=[...]` and `foreign_pre_chain`) —
   sees the structured `event_dict`, but only for records going through the
   structlog path; coverage of plain stdlib loggers is subtle/partial.
3. **redacting `Formatter`** — sees the fully rendered output line (JSON or
   console string) last, regardless of origin.

## Options — redaction safety-net

### Option A — stdlib `logging.Filter` on the handlers ✅ recommended

A `RedactingFilter` added to the `default` and `dev_console` handlers (or to
the root logger). Regex-scrubs `record.msg` and `record.args`.

- **Pros:** single chokepoint covers all three logger styles; minimal change
  to existing `dictConfig`; stdlib-native and easy to unit-test.
- **Cons:** a `Filter` runs *before* formatting, so for the structlog JSON
  path some PII lives inside the wrapped `event_dict` and a naive
  `record.getMessage()` scrub can miss structured fields. Needs care, or pair
  with Option C.

### Option B — structlog processor

Insert a `censor_pii` processor into `structlog.configure(processors=[...])`
and `foreign_pre_chain`.

- **Pros:** operates on the structured `event_dict`; can target specific keys
  (e.g. always redact an `email` key) precisely, before rendering; idiomatic
  for structlog.
- **Cons:** **misses plain stdlib `logging.getLogger()` calls** — which is
  exactly where our PII is. `foreign_pre_chain` coverage is easy to get wrong.
  Insufficient on its own here.

### Option C — redacting `Formatter` (scrub final rendered string)

Subclass/wrap the formatter so the fully-rendered line is regex-scrubbed last.

- **Pros:** catches PII no matter how it entered — interpolated, structured, or
  inside an exception traceback; format-agnostic.
- **Cons:** sloppy regex over rendered JSON can corrupt structure; operates on
  strings (slightly more CPU); can't make field-aware decisions.

### Option D — combination A + C (defense in depth)

- **Pros:** filter handles common interpolated cases cheaply; formatter catches
  anything that slips through, including tracebacks and structlog fields.
  Highest coverage.
- **Cons:** two places to maintain; minor duplication / perf cost.

**Recommendation:** **Option A** as the primary mechanism, optionally hardened
with **Option C**. A is the only single-point option that cleanly covers the
stdlib-heavy reality of this codebase.

## What to match (regex / denylist strategy)

- **Email:** `[\w.+-]+@[\w-]+\.[\w.-]+` → `[EMAIL_REDACTED]`. Cheap,
  high-value, low false-positive.
- **Sensitive key/value pairs** (API keys, passwords, tokens): a **denylist of
  key names** (`password`, `secret`, `token`, `api_key`, `authorization`,
  `csrf`, `client_secret`, …) matched against structured fields and
  `key=value` / `"key": "value"` patterns → redact the *value*. Seed the list
  from the existing `header_safe()` denylist.
- **Bearer tokens / long hex/base64 blobs:** optional; higher false-positive
  risk — start conservative or omit initially.

**Trade-offs:** regex redaction has false negatives (obfuscated/split data) and
false positives (redacting something you wanted intact), plus a small per-line
CPU cost. Treat it as a net, not a guarantee — which is why the deliberate
audit matters.

## Options — deliberate audit (email → UUID)

### Option 1 — replace `user.email` with `user.id` in our log statements ✅ recommended

e.g. `logger.info("Password reset email sent to user %s", user.id)`.

- **Pros:** no PII at rest in logs — correct GDPR posture; UUIDs still allow
  correlation/debugging back to a user.
- **Cons:** manual; the `login_rate_limit_service` case has *only* the email
  pre-auth (no UUID available) — there, log a hash of the email or accept
  redaction-only; loses human readability when eyeballing logs.

### Option 2 — redaction-only, leave statements as-is

- **Pros:** zero churn in service code.
- **Cons:** relies entirely on the regex net; the email was assembled in
  memory and could leak via a path the regex misses.

**Recommendation:** Option 1 for our own code (bounded list — ~6 files above)
**plus** the redaction net (Option A) for everything else and future code.

## Step 0 — make logger usage consistent (prerequisite)

Today three logging styles coexist (see "Logger usage is mixed" above). This
matters for redaction in two ways:

- **Coverage:** a field-aware redactor (structlog processor, Option B) only
  works if everything flows through structlog. Right now the PII-heavy modules
  use plain stdlib logging, which is why Option A (a stdlib filter) is forced.
- **The audit:** logging `user.id` as a *structured field* (`logger.info("...",
  user_id=user.id)`) is cleaner and machine-queryable — but only consistently
  available if we standardise the call style.

Standardising first means the redaction layer has one well-defined path to
guard, and later code has one obvious pattern to copy.

### Options for the target style

**Option S1 — standardise on `structlog.get_logger(__name__)` everywhere ✅ recommended**

Convert the stdlib `logging.getLogger(__name__)` module loggers and, where
practical, the blueprint `current_app.logger` calls to a module-level
`structlog` logger.

- **Pros:** structured key/value logging throughout (enables field-aware
  redaction via Option B *and* clean `user_id=` audit fields); one idiom for
  new code; aligns with the already-configured structlog stack.
- **Cons:** largest diff; `current_app.logger` is the conventional Flask idiom
  and some prefer keeping it in request-handling code; need to confirm
  structlog's `merge_contextvars` gives us request context we'd otherwise get
  from Flask.

**Option S2 — standardise on stdlib `logging.getLogger(__name__)` everywhere**

Move the three structlog modules and the blueprints onto stdlib loggers.

- **Pros:** smaller conceptual surface; stdlib filter (Option A) is the natural
  fit; no dependency on structlog call-site idioms.
- **Cons:** loses structured-field logging where we already have it; pushes us
  toward string-interpolated messages, which are exactly what's harder to
  redact and audit. Feels like the wrong direction.

**Option S3 — leave blueprints on `current_app.logger`, standardise the rest on structlog**

Pragmatic middle ground: module/service code uses `structlog`; request handlers
keep `current_app.logger` (which still funnels through the same handlers).

- **Pros:** smaller diff than S1; keeps the idiomatic Flask logger in views;
  redaction net (Option A) still covers blueprints because they hit the same
  handlers.
- **Cons:** two styles persist; blueprint logs stay string-interpolated (so the
  email sites in `admin.py` rely on redaction rather than structured `user_id`).

**Recommendation:** **S1** if we're willing to absorb the diff (best end state
for both redaction and the audit); **S3** as the pragmatic fallback. Either way
the service-layer PII modules (`*_service.py`, `adapters/email.py`) should move
to structlog, since that's where the email sites are.

## Proposed shape of the work

0. **Make logger usage consistent** (Step 0 above) — pick a target style and
   converge the loggers. Do this first so the redaction layer guards a single
   path and the audit can use structured fields.
1. New module `backend/src/opendlp/log_redaction.py`: a `RedactingFilter`
   (and optionally a redacting formatter mixin), with the email regex + a
   sensitive-keys denylist seeded from `GunicornLogger.header_safe`.
2. Wire the filter into the `filters` / `handlers` sections of the
   `dictConfig` in `logging.py`.
3. Audit + edit the ~6 PII log sites to use `user.id` (and decide the
   rate-limit-by-email handling).
4. Tests: assert emails/keys are scrubbed across JSON and console renderers,
   and that both a stdlib-logger call *and* a structlog call are covered.

## Open questions for review

- **Step 0 target style:** S1 (all structlog), S2 (all stdlib), or S3
  (structlog for services, `current_app.logger` for blueprints)? Note: if we
  adopt S1/S2 such that all PII flows through structlog, the **field-aware
  structlog processor (Option B) becomes viable** and could replace or
  complement the stdlib filter (Option A).
- **Rate-limit-by-email logging** (`login_rate_limit_service.py:70`): redact,
  hash, or drop the email? No UUID exists at that point.
- **Secret denylist scope:** start with the `header_safe` seed only, or also
  add generic long-token heuristics (with their false-positive risk)?
- **Belt-and-braces:** ship Option A alone first, or A + C from the start?
- **Dev console:** redact in development too (consistency) or only in
  production JSON logs (developer convenience)?
- **Performance:** acceptable to run a few regexes per log line at INFO volume?
  (Likely yes; worth a sanity check on hot paths like gunicorn access logs.)
