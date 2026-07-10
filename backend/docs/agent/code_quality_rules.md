# Code Quality Rules

This document collects code quality rules and patterns to follow, gathered from code review feedback and linting issues.

## Exception Handling

### Never use bare `pass` in exception handlers

**Rule:** Exception handlers should never use a bare `pass` statement. Always log the exception, even if the behavior is to silently continue.

**Why:** Bare `pass` statements make debugging difficult because there's no trace of what happened. Even when silently ignoring an exception is the correct behavior, logging at `debug` level provides observability.

**Bad:**

```python
try:
    value = uuid.UUID(some_param)
except (ValueError, TypeError):
    pass  # No trace of what happened
```

**Good:**

```python
try:
    value = uuid.UUID(some_param)
except (ValueError, TypeError):
    current_app.logger.debug("Invalid UUID parameter: %r", some_param)
```

**Log levels:**

- Use `debug` for expected invalid input that's gracefully handled
- Use `warning` for unexpected but recoverable situations
- Use `error` for failures that affect functionality

## Logging (PII / secrets)

Logs are long-lived and widely accessible, so they must never become a copy of
personal data we would then have to find and blank for a GDPR erasure request.
The `log_redaction.censor_pii` processor is a backstop, not a licence to log
PII — write log calls that are safe before redaction runs.

### Use structlog with structured key/value fields

**Rule:** Use `structlog.get_logger(__name__)`. Pass context as keyword
arguments (`logger.info("event", user_id=str(user.id))`), not interpolated
f-strings. Do not use `logging.getLogger` or `current_app.logger` in new code.

**Why:** Structured fields are filterable, and the redaction processor can
reason about field *names* (it redacts values of sensitive keys). An f-string
collapses everything into one opaque message.

### Never log raw PII

**Rule:** Do not log emails, names, addresses, phone numbers, or any other
personal data of users or registrants/respondents.

- Log `user_id` (a UUID), never the email/name. UUIDs survive a GDPR erasure
  because the row is blanked, not deleted.
- Where no UUID exists yet (e.g. pre-auth, login rate limiting), hash the value
  with `log_redaction.hash_email` instead of logging it.

**Bad:**
```python
logger.info("Login attempt", email=email)
logger.info(f"Sending invite to {invite.email}")
```

**Good:**
```python
logger.info("Login attempt", email_hash=hash_email(email))
logger.info("Sending invite", user_id=str(user.id))
```

### Beware `error=str(e)` and exception messages

**Rule:** Treat exception text as potentially PII-bearing. A respondent name,
address, or email can end up inside a validation/parsing error message (e.g.
CSV import, sortition validation). `censor_pii` scrubs emails and sensitive
keys, but it cannot redact a name or address embedded in free text.

- Prefer logging a stable, controlled message plus structured IDs over dumping
  `str(e)` when the exception may quote user-supplied data.
- The CSV/sheet import and sortition paths are the highest-risk spots — review
  any new `error=str(e)` there with this in mind.

### Use `logger.exception` in catch-all handlers

**Rule:** Inside a catch-all `except Exception` block, use `logger.exception(...)`
so the traceback is captured. Do not pair a `logger.error(...)` with a separate
`logger.exception("stacktrace")` — `logger.exception` already records both the
message (with structured fields) and the traceback in one call.

**Bad:**
```python
except Exception as e:
    logger.error("Upload failed", assembly_id=str(assembly_id), error=str(e))
    logger.exception("stacktrace")
```

**Good:**
```python
except Exception as e:
    logger.exception("Upload failed", assembly_id=str(assembly_id), error=str(e))
```

Specific, expected exceptions (e.g. `except NotFoundError`) where no traceback
is wanted may stay on `logger.error`.

See [docs/personal-data.md](../personal-data.md) for why these rules exist and what else they
constrain, and [docs/agent/617-log-redaction/](617-log-redaction/) for the redaction design.

## Cyclomatic Complexity

### Keep functions under complexity threshold (C901)

**Rule:** Functions should have a cyclomatic complexity of 10 or less (configured in ruff).

**Why:** High complexity makes code harder to understand, test, and maintain.

**Solutions:**

1. Extract helper functions for distinct logical blocks
2. Use early returns to reduce nesting
3. Replace complex conditionals with lookup tables or strategy patterns

**Example refactoring:**

```python
# Before: Complex function with nested conditionals
def process_data(data, option_a, option_b):
    if option_a:
        if data.type == "x":
            # 20 lines of logic
        else:
            # 20 lines of logic
    if option_b:
        # more nested logic
    # ... complexity grows

# After: Extract helper functions
def _process_type_x(data):
    # focused logic

def _process_other_types(data):
    # focused logic

def process_data(data, option_a, option_b):
    if option_a:
        if data.type == "x":
            return _process_type_x(data)
        return _process_other_types(data)
    # cleaner main function
```

## Import Organization

### Keep imports at module level (PLC0415)

**Rule:** All `import` statements should be at the top of the file, not inside functions.

**Why:**

- Imports inside functions hide dependencies
- Makes it harder to see what a module depends on
- Can cause unexpected performance issues (import on every call)

**Exceptions:** Circular import resolution may require local imports, but these should be documented.

## Code Formatting

### Run pre-commit hooks before committing

**Rule:** Always run `just check` before committing to catch formatting issues. Be aware that new files will be ignored by `just check` until they are added to git, as this is mostly running `prek` to run the pre-commit check files over all files.

**Tools configured:**

- `ruff check` - Linting (includes complexity checks)
- `ruff format` - Code formatting
- `DjHTML` - HTML template formatting
- `DjCSS` - CSS formatting
- `DjJS` - JavaScript formatting
- `detect-secrets` - ensure no passwords/secrets committed to the repo
- `mypy` - Type checking
- `deptry` - check dependencies in `pyproject.toml` match what is used in the code
