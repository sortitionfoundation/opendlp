<!-- ABOUTME: Detailed red/green TDD implementation plan for issue #617 log redaction. -->
<!-- ABOUTME: Phased plan covering logger consistency (S1), structlog redaction processor, email->UUID audit, and HMAC hashing. -->

# 617 — Log redaction: implementation plan (TDD)

This plan implements the design agreed in [`research.md`](./research.md). It is
written as a **red/green/refactor TDD** sequence: every behaviour change starts
with a failing test, is made to pass with the minimum implementation, then
refactored.

## Agreed decisions (recap)

- **Step 0 / S1:** all logging via `structlog.get_logger(__name__)` (services
  *and* blueprints). Touching `current_app.logger` in blueprints is **in
  scope**.
- **Redaction: Option B** — a `censor_pii` structlog processor registered in
  both `processors` and `foreign_pre_chain`. Option C deferred.
- **Audit: Option 1** — replace `user.email` with `user.id` (structured
  `user_id=`) in our log statements.
- **Rate-limit-by-email:** log an **HMAC-SHA256 hash** of the email (keyed on
  `SECRET_KEY`), not the raw or masked address. **Confirmed.**
- **Secret denylist:** name-based, seeded from `header_safe()`. No
  high-entropy/long-token heuristics.
- **Console email adapter:** write to `sys.stdout` directly (dev-only), not via
  `logger`.
- **Redact in dev too.**

## Pre-flight findings (verified against current code)

- The per-request `structlog.contextvars` binding **already exists** —
  `add_context_for_structlog` in `entrypoints/flask_app.py:175` already calls
  `clear_contextvars()` then `bind_contextvars(view=…, request_id=…, peer=…)`,
  and `merge_contextvars` is already first in the `structlog.configure`
  processor chain (`logging.py:72`). **No new request-id work is needed** — we
  only verify it and make sure we never bind PII there.
- Loggers to convert to `structlog` (S1):
  - stdlib `logging.getLogger(__name__)`: `service_layer/user_service.py:34`,
    `password_reset_service.py:18`, `email_confirmation_service.py:17`,
    `email_send_service.py:16`, `email_template_service.py:25`,
    `login_rate_limit_service.py:12`, `adapters/email.py:11`.
  - Flask `current_app.logger`: blueprints `admin.py`, `auth.py`, `profile.py`,
    `health.py`, `backoffice_registration.py` (any `current_app.logger.*`).
  - **Leave as-is:** `config.py` module-level `logging.warning(...)` (runs at
    import time, before app config; still caught by `foreign_pre_chain`). Note
    this explicitly so it isn't mistaken for an omission.
- Email-in-log audit sites (all have a `user` with `user.id` except the admin
  invite sites, which are pre-user invite flows):
  - `email_confirmation_service.py:139,141,146` → `user.id`
  - `password_reset_service.py:320,322,327` → `user.id`
  - `user_service.py:1051,1053,1058` → `user.id` (already logs `assembly.id`)
  - `login_rate_limit_service.py:70` → `hash_email(email)`
  - `admin.py:346,501,503,508` → no user UUID (invite-by-email). Log the
    **invite id / object id** where available; otherwise rely on the redaction
    processor as the backstop. Flag any site where no id is available.
- `SECRET_KEY` access: add `config.get_secret_key()` (reads `SECRET_KEY` env
  with the same default as `FlaskBaseConfig`) so `hash_email` works without a
  Flask app context (the service is unit-tested standalone).
- Existing tests that will need updating: `tests/unit/test_email_adapters.py`
  (console adapter currently asserts on `caplog`; switch to `capsys`),
  `tests/unit/test_login_rate_limit_service.py` (assert hash, not raw email).

## New / changed files

| File | Change |
|---|---|
| `src/opendlp/log_redaction.py` | **new** — denylist constants, email regex, `redact_emails`, `censor_pii` processor, `hash_email` |
| `src/opendlp/config.py` | add `get_secret_key()` |
| `src/opendlp/logging.py` | import + register `censor_pii`; refactor `header_safe` to use shared denylist |
| `src/opendlp/adapters/email.py` | console adapter → `sys.stdout`; logger → structlog |
| `src/opendlp/service_layer/*.py` | S1 logger swap; email→`user.id` audit; rate-limit hash |
| `src/opendlp/entrypoints/blueprints/*.py` | `current_app.logger` → module `structlog` logger; invite audit |
| `tests/unit/test_log_redaction.py` | **new** |
| `tests/unit/test_logging_integration.py` | **new** — end-to-end rendered-output redaction |
| `tests/unit/test_email_adapters.py` | console tests → `capsys` |
| `tests/unit/test_login_rate_limit_service.py` | hash assertions |

## How to run tests (per CLAUDE.md)

```bash
uv run pytest tests/unit/test_log_redaction.py -q      # focused, during TDD
uv run pytest tests/unit -q                            # unit suite
just check                                             # mypy + deptry + lint, before pushing
just test                                              # full suite with coverage
```

Every code file starts with the 2-line `ABOUTME` comment; double quotes; type
hints required (strict mypy); 120-char lines.

---

## Phase 1 — redaction core (pure functions + processor)

Self-contained, no wiring into the logging config yet. Pure functions are the
cheapest place to pin behaviour.

### 1.1 Denylist + email regex + `redact_emails`

**RED** — `tests/unit/test_log_redaction.py`:

```python
def test_redact_emails_replaces_address():
    assert redact_emails("contact a@b.com now") == "contact [EMAIL_REDACTED] now"

def test_redact_emails_handles_multiple_and_plus_addressing():
    out = redact_emails("x@y.com and a.b+tag@sub.example.co.uk")
    assert "@" not in out
    assert out.count("[EMAIL_REDACTED]") == 2

def test_redact_emails_leaves_plain_text_untouched():
    assert redact_emails("no address here") == "no address here"
```

**GREEN** — in `log_redaction.py`:

```python
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
EMAIL_PLACEHOLDER = "[EMAIL_REDACTED]"

def redact_emails(text: str) -> str:
    return EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
```

### 1.2 Sensitive-key matching

**RED**:

```python
@pytest.mark.parametrize("key", ["password", "secret", "token", "api_key",
                                 "Authorization", "client_secret", "csrf_token", "email"])
def test_is_sensitive_key_true(key):
    assert is_sensitive_key(key)

@pytest.mark.parametrize("key", ["email_hash", "user_id", "request_id", "view", "status"])
def test_is_sensitive_key_false(key):
    assert not is_sensitive_key(key)
```

Note the deliberate cases: `email` (exact) is sensitive but `email_hash` is
**not** (so our hashed value survives); `user_id`/`request_id` survive.

**GREEN** — define module constants seeded from the current `header_safe`
denylist, plus `email`/`password`/`secret`/`token`:

```python
SENSITIVE_EXACT = frozenset({"authorization", "cookie", "csrf_token",
                             "password", "secret", "token", "email"})
SENSITIVE_PARTIAL = ("api-key", "api_key", "authorization",
                     "security-token", "secret", "password")

def is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower in SENSITIVE_EXACT:
        return True
    return any(part in lower for part in SENSITIVE_PARTIAL)
```

Care: `SENSITIVE_PARTIAL` must **not** contain `email` or `token`-substrings
that would catch `email_hash`/`request_id`. `token` is exact-only on purpose.
The `email_hash`/`user_id` false-positive cases above guard this.

### 1.3 `censor_pii` processor

**RED** — drive the processor directly with an `event_dict` (this is exactly
how structlog calls it, so no logging machinery needed):

```python
def test_censor_pii_redacts_email_in_message():
    ed = censor_pii(None, "info", {"event": "sent to a@b.com"})
    assert ed["event"] == "sent to [EMAIL_REDACTED]"

def test_censor_pii_redacts_email_in_string_values():
    ed = censor_pii(None, "info", {"event": "x", "to": "a@b.com"})
    assert ed["to"] == "[EMAIL_REDACTED]"

def test_censor_pii_redacts_sensitive_keys_by_name():
    ed = censor_pii(None, "info", {"event": "x", "password": "hunter2", "api_key": "k"})
    assert ed["password"] == "[REDACTED]"
    assert ed["api_key"] == "[REDACTED]"

def test_censor_pii_preserves_non_sensitive_fields():
    ed = censor_pii(None, "info", {"event": "x", "user_id": "uuid", "email_hash": "email#abcd"})
    assert ed["user_id"] == "uuid"
    assert ed["email_hash"] == "email#abcd"

def test_censor_pii_handles_non_string_values():
    ed = censor_pii(None, "info", {"event": "x", "count": 3, "ok": True})
    assert ed["count"] == 3 and ed["ok"] is True
```

**GREEN**:

```python
REDACTED = "[REDACTED]"

def censor_pii(logger, method_name, event_dict):
    for key, value in event_dict.items():
        if is_sensitive_key(key):
            event_dict[key] = REDACTED
        elif isinstance(value, str):
            event_dict[key] = redact_emails(value)
    return event_dict
```

(Signature matches structlog's processor contract; `logger`/`method_name`
unused. Add `# noqa`/typing as the codebase requires — type as
`structlog.types.EventDict` return.)

**REFACTOR:** ensure `log_redaction.py` has the `ABOUTME` header and full type
hints (`EventDict`, `WrappedLogger`, `str`).

---

## Phase 2 — HMAC email hashing

### 2.1 `config.get_secret_key()`

**RED** — `tests/unit/test_config.py`:

```python
def test_get_secret_key_reads_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "abc")
    assert config.get_secret_key() == "abc"

def test_get_secret_key_default(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert config.get_secret_key() == "dev-secret-key-change-in-production"
```

**GREEN** — add `get_secret_key()` mirroring `FlaskBaseConfig.SECRET_KEY`'s
default.

### 2.2 `hash_email`

**RED** — `tests/unit/test_log_redaction.py`:

```python
def test_hash_email_is_stable_and_case_insensitive():
    assert hash_email("A@B.com", secret="k") == hash_email("a@b.com ", secret="k")

def test_hash_email_changes_with_secret():
    assert hash_email("a@b.com", secret="k1") != hash_email("a@b.com", secret="k2")

def test_hash_email_does_not_contain_plaintext():
    out = hash_email("alice@example.com", secret="k")
    assert "alice" not in out and "@" not in out
    assert out.startswith("email#")
```

**GREEN**:

```python
def hash_email(email: str, *, secret: str | None = None) -> str:
    key = (secret if secret is not None else config.get_secret_key()).encode()
    normalised = email.strip().lower().encode()
    digest = hmac.new(key, normalised, hashlib.sha256).hexdigest()
    return f"email#{digest[:12]}"
```

Confirm no import cycle: `log_redaction` → `config` only (config does **not**
import `opendlp.logging`/`log_redaction`).

---

## Phase 3 — wire the processor into logging config

### 3.1 End-to-end redaction (integration)

**RED** — `tests/unit/test_logging_integration.py`. Capture *rendered* output
by attaching a `StreamHandler(StringIO())` using the JSON `ProcessorFormatter`,
then assert across both code paths:

```python
def test_structlog_call_redacts_email(capture_json_handler):
    structlog.get_logger("test").info("sent", to="a@b.com")
    assert "a@b.com" not in capture_json_handler.getvalue()
    assert "[EMAIL_REDACTED]" in capture_json_handler.getvalue()

def test_stdlib_foreign_call_redacts_email(capture_json_handler):
    logging.getLogger("third_party").warning("mail to a@b.com")
    assert "a@b.com" not in capture_json_handler.getvalue()
```

The second test is the important one — it proves `foreign_pre_chain` coverage
(the "easy to get wrong" risk called out in the design). Build a small fixture
that wires a handler with `structlog.stdlib.ProcessorFormatter(processor=JSONRenderer(),
foreign_pre_chain=pre_chain)` exactly as `logging.py` does.

**GREEN** — in `logging.py`:

- import `from opendlp.log_redaction import censor_pii`.
- add `censor_pii` to `pre_chain` (so it runs for `foreign_pre_chain`), placed
  **after** `add_log_level`/`timestamper`.
- add `censor_pii` into `structlog.configure(processors=[...])`, placed
  **after** `PositionalArgumentsFormatter()` (so positional `%s` args are
  already interpolated into `event`) and **before**
  `ProcessorFormatter.wrap_for_formatter`.

### 3.2 Share the denylist with `header_safe`

**RED** — `tests/unit/test_logging.py` (new or existing):

```python
def test_header_safe_uses_shared_denylist():
    log = GunicornLogger.__new__(GunicornLogger)
    assert log.header_safe("X-API-Key") is False
    assert log.header_safe("Authorization") is False
    assert log.header_safe("Accept") is True
```

**GREEN/REFACTOR** — change `GunicornLogger.header_safe` to consult
`log_redaction.is_sensitive_key` (or the shared `SENSITIVE_*` constants) so
there is **one source of truth**. Keep its existing exact set
(`authorization`, `cookie`, `csrf_token`) working — verify these are covered by
the shared constants and adjust the constants if a header name would otherwise
regress.

---

## Phase 4 — Step 0 / S1: logger consistency

Mechanical but wide. Do it as one phase so the redaction guarantees hold for
all our code.

### 4.1 Verify the existing request-id binding (characterisation test)

**RED→GREEN (characterisation):** add a test asserting the contract that
already exists, so a future change can't silently drop it:

```python
def test_request_binds_request_id_contextvars(client):
    # hitting any route binds request_id/view/peer into contextvars
    # assert via a captured log line containing a request_id field
```

If the existing behaviour already satisfies it, this test is green immediately
— that's fine; it locks the contract. **Do not** add PII to this binding.

### 4.2 Swap module loggers to structlog

For each service/adapter module in the pre-flight list:

- replace `import logging` + `logger = logging.getLogger(__name__)` with
  `import structlog` + `logger = structlog.get_logger(__name__)`.
- leave call sites unchanged for now (string messages still work via
  `BoundLogger`); audit conversions happen in Phase 5.

**Test:** the existing unit suites for these modules must stay green
(`uv run pytest tests/unit -q`). Optionally add:

```python
def test_service_logger_is_structlog():
    import opendlp.service_layer.password_reset_service as m
    assert isinstance(m.logger, structlog.stdlib.BoundLogger)
```

### 4.3 Swap blueprint `current_app.logger` to module structlog loggers

In each blueprint, add `logger = structlog.get_logger(__name__)` at module
level and replace `current_app.logger.<level>(...)` calls. Keep messages
identical for now (audit in Phase 5).

**Test:** blueprint/integration tests stay green. Add a focused test for one
converted blueprint that emitting a log does not raise outside an app context
(structlog logger is app-context-independent, unlike `current_app.logger`).

**Note in plan:** `config.py` keeps stdlib `logging.warning` (documented
exception); `foreign_pre_chain` still redacts it.

---

## Phase 5 — audit: email → `user.id` / hashed

### 5.1 Service email sites → `user.id`

**RED** — for each service, a test asserting the rendered log contains the user
id and **not** the email. Reuse the Phase 3 capture fixture. Example for
`password_reset_service`:

```python
def test_password_reset_log_uses_user_id_not_email(capture_json_handler, user):
    send_password_reset_email(...)   # arrange via existing fakes
    out = capture_json_handler.getvalue()
    assert str(user.id) in out
    assert user.email not in out
```

**GREEN** — convert to structured logging, e.g.:

```python
logger.info("Password reset email sent", user_id=str(user.id))
logger.error("Failed to send password reset email", user_id=str(user.id))
logger.error("Error sending password reset email", user_id=str(user.id), error=str(e))
```

Apply the same to `email_confirmation_service` (3 sites), `user_service`
assembly-role emails (3 sites; keep `assembly_id=str(assembly.id)`).

### 5.2 Admin invite sites

These are pre-user (invite-by-email), so no `user.id`. Per design:

- where an invite/object id exists, log it (`invite_id=...`);
- otherwise rely on the redaction processor (the email becomes
  `[EMAIL_REDACTED]`).

**RED** — test that the rendered admin-invite log line does not contain the raw
email (redaction backstop), and contains the invite id when available.

**GREEN** — update `admin.py:346,501,503,508` accordingly. Flag in the PR any
site where no id is available so it is a conscious "redaction-only" choice.

### 5.3 Rate-limit hash

**RED** — `tests/unit/test_login_rate_limit_service.py`:

```python
def test_rate_limit_log_hashes_email(capture_json_handler, redis_client):
    # arrange counter at the limit, then call check_login_rate_limit(...)
    out = capture_json_handler.getvalue()
    assert "a@b.com" not in out
    assert hash_email("a@b.com") in out
```

**GREEN** — in `login_rate_limit_service.py` (now using structlog):

```python
logger.warning("Login rate limit exceeded for email", email_hash=hash_email(email))
```

Leave the IP line as-is for this issue; add a one-line note that hashing/΅
truncating IP is a possible GDPR follow-up (out of scope here).

---

## Phase 6 — console email adapter → `sys.stdout`

**RED** — rewrite the console tests in `tests/unit/test_email_adapters.py` to
use `capsys` instead of `caplog`:

```python
def test_console_adapter_writes_to_stdout(capsys):
    ConsoleEmailAdapter().send_email(to=["recipient@example.com"], subject="S", text_body="B")
    out = capsys.readouterr().out
    assert "EMAIL (Console):" in out
    assert "recipient@example.com" in out      # real address shown, by design (dev only)

def test_console_adapter_does_not_use_logging(caplog):
    with caplog.at_level(logging.INFO):
        ConsoleEmailAdapter().send_email(to=["recipient@example.com"], subject="S", text_body="B")
    assert "recipient@example.com" not in caplog.text   # not routed through logging
```

Convert all five existing console tests (`test_send_email_logs_*`) from
`caplog` to `capsys`.

**GREEN** — in `ConsoleEmailAdapter.send_email`, replace the `logger.info(...)`
block with `print(<same multi-line body>, file=sys.stdout)` (add `import sys`).
Keep the body/preview formatting identical. The `logger` import in `email.py`
remains (still used by `SMTPEmailAdapter`), now as structlog (Phase 4).

**Why this passes the audit:** the recipient address is intentionally visible
in dev stdout, is **not** a logging call (so it won't be re-flagged by future
log audits), and bypasses the redactor (so dev keeps the real address).

---

## Phase 7 — finalise

1. `just check` — mypy (strict), deptry, ruff/prek. Fix typing on the processor
   (`EventDict`/`WrappedLogger`) and any line-length issues.
2. `just test` — full suite incl. BDD (`CI=true uv run pytest tests/bdd/`).
3. Grep sweep for leftover PII logging and old logger styles:
   - `rg "current_app\.logger" src/` → expect none (except documented).
   - `rg "logging\.getLogger" src/` → expect only `config.py` (documented) and
     `logging.py` internals.
   - `rg "logger\.(info|error|warning).*user\.email" src/` → expect none.
4. Update `research.md` "remaining open decision" note to "resolved: HMAC hash".
5. Consider a short note in `backend/docs/` (or `CLAUDE.md` security section)
   stating the logging rule for future code: *use `structlog.get_logger`; never
   log raw email/PII — log `user_id`; the `censor_pii` processor is a backstop,
   not a license to log PII.*

## Test inventory (summary)

| Test file | Asserts |
|---|---|
| `test_log_redaction.py` | `redact_emails`, `is_sensitive_key`, `censor_pii`, `hash_email` |
| `test_logging_integration.py` | rendered output redacted for **structlog** and **foreign/stdlib** paths |
| `test_config.py` | `get_secret_key()` env + default |
| `test_logging.py` | `header_safe` uses shared denylist |
| `test_email_adapters.py` | console adapter → stdout, not logging |
| `test_login_rate_limit_service.py` | log contains `hash_email`, not raw email |
| existing service tests | unchanged behaviour, email absent / `user_id` present |

## Risks & notes

- **Processor ordering** is the main correctness risk: `censor_pii` must run
  after positional-arg interpolation and be present in **both** the main chain
  and `foreign_pre_chain`. The two Phase 3 integration tests (structlog +
  foreign) are the guard.
- **Over-redaction:** `is_sensitive_key` partial matching could redact an
  unexpected field; the `email_hash`/`user_id`/`request_id` negative tests pin
  the boundary. Add new negative cases if we introduce new structured keys.
- **Performance:** one regex sub per string field per log line; accepted in the
  design. If gunicorn access logs prove hot, revisit (not expected at INFO).
- **Scope kept out:** IP-address hashing, Option C formatter scrub, high-entropy
  secret heuristics — all explicitly deferred.
