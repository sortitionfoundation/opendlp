# BDD tests cannot see the emails the app sends

## Background

The BDD suite runs the app as a separate server process, with
`EMAIL_ADAPTER=console` (`tests/bdd/conftest.py`). Emails go to that process's
stdout, so a BDD step has no way to check what was sent. One step admits it:

```python
@then("the user should receive a confirmation email")
def _():
    """Check that confirmation email was sent (this would check logs in real implementation)."""
    # In a real implementation, this would check email logs or mock
    # For now, we trust the service layer tests verified email sending
```

(`tests/bdd/shared/email_confirmation_steps.py`). The step always passes. No
BDD scenario can follow a link in an email, so password reset, email
confirmation and the registration auto-reply are not tested end to end.

Found while planning the email and task adapters
([more-adapters/plan.md](../more-adapters/plan.md), option E3). That plan
makes the in-memory `FakeEmailAdapter` the default for every Flask test, but an
in-memory fake cannot cross into the BDD server's process.

## What the change would be

1. A `FileEmailAdapter` in `src/opendlp/adapters/email.py`, chosen by
   `EMAIL_ADAPTER=file`. Each send is written as one JSON (or `.eml`) file to a
   directory named by a new config value, e.g. `EMAIL_FILE_DIR`.
2. Production config refuses `file`, as it refuses `console`.
3. The BDD conftest sets `EMAIL_ADAPTER=file` and a per-run directory under the
   temp dir, and empties it before each scenario.
4. A small helper in the BDD test process reads the directory: "the latest
   email to this address", "the first link in it".
5. The no-op step becomes a real assertion, and new scenarios can follow the
   confirmation and password-reset links.

## Constraints

- CLAUDE.md forbids long-term copies of personal data on disk. A test-only
  directory, emptied per scenario and refused in production, is the same shape
  as the swept download directory that the GDPR section allows. Say so in the
  adapter's docstring, so nobody later points it at a persistent path.
- The adapter must not log the recipient: same rule as everywhere else.
