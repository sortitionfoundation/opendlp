# Bot protection — implementation plan (recommended layers only)

**STATUS: COMPLETE** — all phases implemented and committed (see git log for branch `614-bot-protection`).

This plan covers the three recommended layers from `research.md`:

1. ✅ Honeypot field + form-timing token (+ existing CSRF)
2. ✅ Rate limiting — per-IP and per-email
3. ✅ `X-Robots-Tag: noindex` header

It does not cover the call-centre path, address-match integration, email-job signed links, or CDN/WAF — those are in the research doc as later or optional work.

**Docs read before writing this plan:** `docs/architecture.md`, `docs/testing.md`, `docs/agent/frontend_design_system.md`, `docs/agent/component_accessibility.md`, `docs/agent/code_quality_rules.md`.

---

## How the form currently works (relevant background)

The registration form HTML is **user-authored** and stored in the database. It is rendered via a Jinja2 sandbox (`render_registration_form`). The sandbox receives a `csrf_form_element` variable — a raw HTML string containing the CSRF hidden input — which the form author includes in their template with `{{ csrf_form_element | safe }}`. This same mechanism is used in both `show_registration_form` and `_rerender_form_with_values`.

The POST route is `@csrf.exempt` and manually calls `validate_csrf()`. Existing CSRF validation failure re-renders the form with the user's values preserved (good UX for people who take time over a public form).

The email field is always submitted under the key `"email"` (enforced by the field definitions and `_create_and_save_respondent`). The client IP is reliably `request.remote_addr` because `ProxyFix(x_for=1)` is already applied in production.

The `registration` blueprint is currently absent from the blueprint-service dependency diagram in `docs/architecture.md` (it is a public-facing blueprint not in the backoffice table). The file change summary below includes updating that diagram.

---

## Layer 1: Honeypot field + form-timing token

### 1a. Honeypot field

**What:** A text input that is invisible to real users. Bots commonly fill every visible input field. If this field has any value on submission, the request is a bot.

**Accessibility requirement:** Must not be a keyboard trap. Use CSS off-screen positioning (`position:absolute; left:-9999px`) rather than `display:none`. Mark the container `aria-hidden="true"` and the input `tabindex="-1"` so screen readers and keyboard users skip it entirely. Use `autocomplete="off"` so browsers don't prefill it.

**Field name:** `_opendlp_ttoken_` — looks to bots like a hidden token they should fill; unique enough that a team grep finds only the honeypot code; the comment and this document explain what it actually is.

**Injection point:** Extend the `csrf_form_element` string (the same string already injected into every form via `{{ csrf_form_element | safe }}`). This means no form template changes are needed for forms that already include the CSRF element.

```html
<!-- added to the csrf_form_element string — _opendlp_ttoken_ is a honeypot field -->
<div
  aria-hidden="true"
  style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden"
>
  <label for="_opendlp_ttoken_">Leave this blank</label>
  <input
    type="text"
    id="_opendlp_ttoken_"
    name="_opendlp_ttoken_"
    tabindex="-1"
    autocomplete="off"
    value=""
  />
</div>
```

**Where the check lives:** At the top of `submit_registration_form`, before CSRF validation:

```python
if request.form.get("_opendlp_ttoken_"):
    # Honeypot filled — silently redirect to thank-you without saving.
    # Log without personal data so we can track hit rate and diagnose edge cases.
    logger.warning("Bot protection: honeypot triggered (IP: %s, slug: %s)", request.remote_addr, url_slug)
    return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)
```

**Decision (Q1):** Silently redirect to thank-you without saving. Bots get no signal that they were blocked. The `autocomplete="off"` and off-screen positioning make accidental fill by a real user extremely unlikely. Logging (without personal data) lets us track hit rate and diagnose any edge cases.

### 1b. Form-timing token

**What:** A signed timestamp generated when the form is rendered. On submission, we verify:

- The token is cryptographically valid (not forged).
- The form was submitted at least `MIN_FILL_SECONDS` after it was rendered (no real person fills a form in under 3 seconds).
- The token is not older than the session lifetime (stale tab).

**Implementation:** Use `itsdangerous.TimestampSigner` (already a Flask transitive dependency via `itsdangerous`). Sign the string `"reg"` with `salt="reg-timing"` and the app's `SECRET_KEY`.

```python
# Render time (in show_registration_form and _rerender_form_with_values)
from itsdangerous import TimestampSigner
signer = TimestampSigner(current_app.secret_key, salt="reg-timing")
timing_token = signer.sign(b"reg").decode()

# Validation time (in submit_registration_form)
from itsdangerous import BadSignature, SignatureExpired
try:
    _, ts = signer.unsign(token, max_age=7 * 24 * 3600, return_timestamp=True)
    age_seconds = (datetime.now(UTC) - ts).total_seconds()
    if age_seconds < current_app.config["REGISTRATION_MIN_FILL_SECONDS"]:
        # Too fast — treat as bot
        logger.warning(
            "Bot protection: timing check failed (IP: %s, slug: %s, age: %.1fs)",
            request.remote_addr, url_slug, age_seconds,
        )
        return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)
except SignatureExpired:
    # Stale tab — treat same as expired CSRF token (re-render with message)
except BadSignature:
    # Forged — treat as CSRF failure
```

**Injection:** Add the timing token hidden input to the same `csrf_form_element` string, directly after the CSRF input. This keeps both tokens in a single variable, injected via the existing mechanism.

```html
<input type="hidden" name="_timing_token" value="..." />
```

**Behaviour on failure:**

- Too fast (bot signal): silently redirect to thank-you (same as honeypot), with a warning log.
- Stale (> session lifetime): re-render with the same "form was open too long" message already used for expired CSRF tokens. Preserve submitted values.
- Invalid/forged: re-render with the CSRF error message. Preserve submitted values.

**Decision (Q2):** Minimum fill time is **3 seconds**. Fast enough to be clearly impossible for a human, low enough not to penalise anyone.

### 1c. Refactoring `csrf_form_element` generation

Both `show_registration_form` and `_rerender_form_with_values` currently build the same `f'<input type="hidden" name="csrf_token" ...>'` string inline. With two new elements added, extract a helper:

```python
# src/opendlp/entrypoints/blueprints/registration.py

def _build_security_form_elements() -> str:
    """Build hidden form elements for CSRF, timing, and honeypot bot protection."""
    csrf_input = f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'
    timing_input = f'<input type="hidden" name="_timing_token" value="{_generate_timing_token()}">'
    # _opendlp_ttoken_ is a honeypot field — see docs/bot-protection.md
    honeypot = (
        '<div aria-hidden="true" style="position:absolute;left:-9999px;'
        'width:1px;height:1px;overflow:hidden">'
        '<label for="_opendlp_ttoken_">Leave this blank</label>'
        '<input type="text" id="_opendlp_ttoken_" name="_opendlp_ttoken_" '
        'tabindex="-1" autocomplete="off" value="">'
        '</div>'
    )
    return csrf_input + timing_input + honeypot
```

Pass this as `csrf_form_element=_build_security_form_elements()` in both call sites. The variable name stays the same so no form template changes are needed.

`_generate_timing_token()` is a one-liner using `TimestampSigner` and can live at the top of `registration.py` (it only needs `current_app.secret_key`, not the service layer).

---

## Layer 2: Rate limiting

### 2a. New service module

Create `src/opendlp/service_layer/registration_bot_protection_service.py`.

Modelled exactly on `login_rate_limit_service.py`:

- Same Redis connection helper (`_get_redis` / `RedisCfg.from_env`)
- Same `INCR` + `EXPIRE` pipeline pattern
- Same `RateLimitExceeded` exception from `service_layer.exceptions`
- Same `redis_client` optional parameter for test injection

**Redis key prefixes:**

- `reg_ratelimit:ip:<ip_address>`
- `reg_ratelimit:email:<normalised_email>`

**Two public functions:**

```python
def check_registration_rate_limit(
    ip_address: str,
    email: str,
    max_per_ip: int = DEFAULT_MAX_SUBMISSIONS_PER_IP,
    max_per_email: int = DEFAULT_MAX_SUBMISSIONS_PER_EMAIL,
    ip_window_minutes: int = DEFAULT_IP_WINDOW_MINUTES,
    email_window_minutes: int = DEFAULT_EMAIL_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Raise RateLimitExceeded if either the per-IP or per-email limit is hit."""

def record_registration_submission(
    ip_address: str,
    email: str,
    ip_window_minutes: int = DEFAULT_IP_WINDOW_MINUTES,
    email_window_minutes: int = DEFAULT_EMAIL_WINDOW_MINUTES,
    redis_client: Redis | None = None,
) -> None:
    """Increment both counters. Called on every attempted submission, not just failures."""
```

Note: `record_registration_submission` is called on **every attempt** (not only failures), because bots that generate valid-looking data would otherwise not be counted. The IP and email windows are different lengths, so two separate `EXPIRE` values.

### 2b. Suggested limits

**Decision (Q3):** Use the following defaults. Conservative (loose) to avoid false positives; all are tuneable via env var without a deployment.

| Dimension | Default        | Window   | Env var |
| --------- | -------------- | -------- | ------- |
| Per-IP    | 30 submissions | 1 hour   | `REGISTRATION_RATE_LIMIT_PER_IP` / `REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES` |
| Per-email | 5 submissions  | 24 hours | `REGISTRATION_RATE_LIMIT_PER_EMAIL` / `REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES` |

The per-email limit of 5 over 24h is deliberately not a hard cap of 1, to allow for e.g. two people sharing an email address both registering for the same job.

### 2c. Integration in the route

In `submit_registration_form`, after the honeypot and timing checks, before calling `submit_registration`:

```python
email = request.form.get("email", "").strip().lower()
ip = request.remote_addr or ""

try:
    check_registration_rate_limit(ip, email, ...)
except RateLimitExceeded:
    return _rerender_form_with_values(
        uow, url_slug,
        values=dict(request.form),
        form_errors=[_("Too many registrations from your location. Please try again later.")],
    )

try:
    result = submit_registration(uow, url_slug=url_slug, form_data=request.form)
except ...

# Only reached if submission was attempted (whether valid or not)
record_registration_submission(ip, email, ...)
```

`record_registration_submission` is called after the submission attempt, so we count the attempt regardless of whether validation passed. (A bot sending invalid data still counts toward the rate limit.)

**Decision (Q4):** Rate limit hits show a real error (re-render form with message). A legitimate user who somehow hits the limit needs to know to retry. Bots don't learn anything useful from the message.

### 2d. Config knobs

Add to `FlaskBaseConfig` in `src/opendlp/config.py`:

```python
self.REGISTRATION_RATE_LIMIT_PER_IP: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_PER_IP", "30"))
self.REGISTRATION_RATE_LIMIT_PER_EMAIL: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_PER_EMAIL", "5"))
self.REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES", "60"))
self.REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES: int = int(os.environ.get("REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES", "1440"))
self.REGISTRATION_MIN_FILL_SECONDS: int = int(os.environ.get("REGISTRATION_MIN_FILL_SECONDS", "3"))
```

---

## Layer 3: X-Robots-Tag: noindex

**What:** Adds `X-Robots-Tag: noindex` to registration page responses so that search engine crawlers that follow the short URL don't index it.

**Existing protection:** `static/well-known/robots.txt` already has `Disallow /register/` and `Disallow /r/` (served via `wellknown.py`). The `X-Robots-Tag` header and meta tag are belt-and-braces on top of that — covering crawlers that ignore `robots.txt` or arrive at the URL directly.

**Where:** A `registration_bp.after_request` hook in `registration.py`. This keeps the concern local to the blueprint rather than adding another `endpoint` check to the app-level `add_security_headers` handler.

```python
@registration_bp.after_request
def add_noindex_header(response: Response) -> Response:
    """Prevent search engines indexing registration pages."""
    response.headers["X-Robots-Tag"] = "noindex"
    return response
```

Also add a `<meta name="robots" content="noindex">` tag to `templates/register/form.html`, `templates/register/thank_you.html`, and `templates/register/thank_you_default.html`.

**Decision (Q5):** Apply to all registration blueprint endpoints (including `/r/<short_url>` redirect, `/register/<slug>/assets/<image>`, and `/registration-closed`). The blueprint-level hook covers all of them with no per-endpoint logic needed.

---

## File change summary

| File                                                               | Change                                                                                                                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/opendlp/entrypoints/blueprints/registration.py`               | Add `_build_security_form_elements()`, timing token generation/validation, honeypot check, rate limit check/record, `add_noindex_header` blueprint after_request hook |
| `src/opendlp/service_layer/registration_bot_protection_service.py` | **New file** — per-IP and per-email rate limiting functions                                                                                                           |
| `src/opendlp/config.py`                                            | Add 5 new config knobs to `FlaskBaseConfig`                                                                                                                           |
| `templates/register/form.html`                                     | Add `<meta name="robots" content="noindex">`                                                                                                                          |
| `templates/register/thank_you.html`                                | Add `<meta name="robots" content="noindex">`                                                                                                                          |
| `templates/register/thank_you_default.html`                        | Add `<meta name="robots" content="noindex">`                                                                                                                          |
| `docs/bot-protection.md`                                           | **New file** — long-term maintained operational docs; cross-links with `docs/frontend_security.md`                                                                    |
| `docs/architecture.md`                                             | Add `registration` blueprint to the blueprint-service dependency diagram and dependency matrix                                                                        |
| `pyproject.toml`                                                   | Add `itsdangerous` as an explicit dependency                                                                                                                         |

No database migration needed for these layers. `itsdangerous` is already a Flask transitive dependency but must be added as an **explicit** dependency in `pyproject.toml` — deptry will flag it otherwise. Add `pyproject.toml` to the file change list above.

---

## Check order in `submit_registration_form`

The checks should run in this order (cheapest/most-reliable first):

1. **Honeypot** — field presence check, no I/O.
2. **CSRF** — already done today, keeps its position.
3. **Timing token** — crypto verify, no I/O.
4. **Rate limits** — two Redis GETs; only reached if the above pass.
5. **`submit_registration()`** — DB write.
6. **`record_registration_submission()`** — two Redis INCRs; called after the attempt.

---

## Testing plan

Tests follow red/green TDD: write the failing test first, then the implementation.

### Unit tests (`tests/unit/service_layer/test_registration_bot_protection_service.py`)

- `check_registration_rate_limit` raises `RateLimitExceeded` when IP limit reached.
- `check_registration_rate_limit` raises `RateLimitExceeded` when email limit reached.
- `check_registration_rate_limit` passes when both are under the limit.
- `record_registration_submission` increments both keys and sets correct TTLs.
- IP and email use separate TTLs (different window lengths).

All using `fakeredis.FakeRedis()` passed as `redis_client`.

### Unit tests for timing token (`tests/unit/entrypoints/test_registration_timing.py`)

- Valid token + age > MIN_FILL_SECONDS → accepted.
- Valid token + age < MIN_FILL_SECONDS → flagged as too fast.
- Expired token (age > max_age) → `SignatureExpired`.
- Tampered token → `BadSignature`.

(These test the helper functions directly, not the full route.)

### Component tests (`tests/component/test_registration_bot_protection.py`)

Full route via the Flask test client with `FakeUnitOfWork` (no real Redis). **Decision (Q6):** Inject `fakeredis.FakeRedis()` by monkeypatching `_get_redis` in `registration_bot_protection_service` via a pytest fixture. This is consistent with the `login_rate_limit_service` test pattern. May be revisited in a later round to align with the `get_flask_uow()` seam style.

- **Happy path is unaffected** — normal submission still works.
- **Honeypot filled** → 302 to thank-you, no respondent created in `FakeUnitOfWork`.
- **Timing too fast** → 302 to thank-you, no respondent created.
- **CSRF still works** — expired token re-renders with error (existing test, ensure it still passes).
- **Rate limit hit (IP)** → 200 re-render with rate limit error message.
- **Rate limit hit (email)** → 200 re-render with rate limit error message.
- **`X-Robots-Tag: noindex`** present on GET /register/<slug>, POST /register/<slug>, and GET /register/<slug>/thank-you.

### E2E tests (`tests/e2e/test_registration_bot_protection.py`)

At least one full round-trip with real Redis: submit a normal registration, confirm it appears in the DB. Marked `requires_redis`. Verifies the happy path is unaffected end-to-end.

### BDD

No new BDD scenarios planned for this layer — these are invisible protections that don't change the user-visible happy path. Existing BDD registration scenarios cover the happy path regression.

---

## Logging

Following `code_quality_rules.md`. **No personal data (email, name, address) is logged anywhere in bot-detection code.** IP address is logged for suspected bots — it is standard security-logging practice, not personal data in this context, and necessary to diagnose any false positives.

| Event                | Level     | Format                                                                  |
| -------------------- | --------- | ----------------------------------------------------------------------- |
| Honeypot triggered   | `warning` | `"Bot protection: honeypot triggered (IP: %s, slug: %s)"`               |
| Timing too fast      | `warning` | `"Bot protection: timing check failed (IP: %s, slug: %s, age: %.1fs)"`  |
| IP rate limit hit    | `warning` | `"Bot protection: IP rate limit exceeded (IP: %s)"`                     |
| Email rate limit hit | `warning` | `"Bot protection: email rate limit exceeded"` — no email address logged |
