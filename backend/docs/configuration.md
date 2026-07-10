# Configuration Guide

Configuration is managed through `src/opendlp/config.py` which loads settings from environment variables.

## Configuration Classes

### FlaskConfig (Development)

Base development configuration with sensible defaults.

**Characteristics:**

- Uses PostgreSQL by default
- Debug mode can be enabled
- Session stored in Redis
- Verbose logging

### FlaskTestConfig (Testing)

Configuration for running tests.

**Characteristics:**

- Uses SQLite in-memory database (fast, no PostgreSQL needed)
- Automatically used when `FLASK_ENV=testing`
- Session stored in Redis (or mock for unit tests)
- Minimal logging

### FlaskProductionConfig (Production)

Production configuration with stricter validation.

**Characteristics:**

- Requires `SECRET_KEY` environment variable
- Requires database configuration
- Debug mode disabled
- Production-grade logging
- Session stored in Redis

## Getting Configuration

Use `get_config()` to get the appropriate configuration based on `FLASK_ENV`:

```python
from opendlp.config import get_config

config = get_config()  # Returns appropriate config based on FLASK_ENV
```

## Required Environment Variables

These environment variables **must** be set in production:

### SECRET_KEY

Flask secret key for session signing and CSRF protection.

```bash
SECRET_KEY=your-long-random-secret-key-here
```

**Security:** Use a cryptographically random string, at least 32 characters. Never commit to version control.

### Database Configuration

**Option 1: DATABASE_URL (recommended)**

```bash
DATABASE_URL=postgresql://user:password@host:port/database  # pragma: allowlist secret
```

**Option 2: Individual variables**

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=opendlp
DB_USER=opendlp
DB_PASSWORD=your-db-password
```

### Redis Configuration

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
```

Redis is used for session storage and Celery task queue.

### Two-Factor Authentication

**Required for 2FA functionality:**

```bash
# Encryption key for storing TOTP secrets (32-byte base64-encoded key)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOTP_ENCRYPTION_KEY=your-base64-encoded-key-here
```

**Security:** This key encrypts TOTP secrets at rest in the database. Must be set before users can enable 2FA. Use a cryptographically secure random key and never commit to version control. If lost, all users with 2FA enabled will need to reset their 2FA setup.

## Optional Environment Variables

### Application Settings

```bash
# Environment: development, testing, production
FLASK_ENV=development

# Enable/disable debug mode
DEBUG=true

# Application URL for generating absolute links
APPLICATION_URL=https://opendlp.example.com
```

### OAuth Configuration

```bash
# Google OAuth
OAUTH_GOOGLE_CLIENT_ID=your-google-client-id
OAUTH_GOOGLE_CLIENT_SECRET=your-google-client-secret
```

See `docs/google_service_account.md` for Google Sheets integration setup.

### Task Configuration

```bash
# Background task timeout in hours (default: 24)
TASK_TIMEOUT_HOURS=24

# Invite expiration in hours (default: 168 = 7 days)
INVITE_EXPIRY_HOURS=168
```

### Registration Page Configuration

```bash
# Maximum size in bytes for a registration page's form HTML
# (default: 204800 = 200 KB, clamped to [1 KB, 10 MB])
REGISTRATION_FORM_HTML_MAX_BYTES=204800

# Maximum size in bytes for a registration page's thank-you HTML
# (default: 51200 = 50 KB, clamped to [1 KB, 10 MB])
REGISTRATION_THANK_YOU_HTML_MAX_BYTES=51200
```

Bot protection for the public registration form is tuneable at runtime via
the variables below (no deployment needed to tighten or loosen limits). See
[docs/bot-protection.md](bot-protection.md) for the full feature description.

```bash
# Max registration submissions per source IP per window (default: 30)
REGISTRATION_RATE_LIMIT_PER_IP=30

# IP rate-limit window in minutes (default: 60)
REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES=60

# Max registration submissions per email address per window (default: 5)
REGISTRATION_RATE_LIMIT_PER_EMAIL=5

# Email rate-limit window in minutes (default: 1440 = 24 hours)
REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES=1440

# Minimum seconds between form render and submit; faster submissions are
# treated as bots and silently redirected (default: 3)
REGISTRATION_MIN_FILL_SECONDS=3
```

The form-timing check is additionally gated on the
`REGISTRATION_TIMING_CHECK_ENABLED` config flag (default: on, disabled in
the test config). This is a config-class setting rather than an environment
variable; see [docs/bot-protection.md](bot-protection.md).

### Monitoring

Enable end-to-end selection monitoring (issue #582) by pointing both
of these at a dedicated monitor assembly + system user. Both IDs must
be set together; leaving either unset disables monitoring entirely.

```bash
# UUID of the monitor assembly that receives a heartbeat selection
MONITOR_ASSEMBLY_ID=

# UUID of the system user that "runs" the monitor selection
MONITOR_USER_ID=

# Optional: how old (in minutes) the latest successful run can be before
# /health and /health/monitor_selection report STALE. Default: 120
# MONITOR_HEALTH_MAX_AGE_MINUTES=120
```

See [docs/monitoring.md](monitoring.md) for the full feature
description, provisioning steps, and operator runbook.

### Help Site URLs

External help site URLs linked from base templates (header "Help" link, and the footer
"User Data Agreement" and "Cookies" links):

```bash
# Help site landing page (replaces the in-app support page)
HELP_SITE_HOME=https://docs.sortitionlab.org/help/

# Data agreement page (replaces the in-app user data agreement page)
HELP_SITE_DATA_AGREEMENT=https://docs.sortitionlab.org/data-and-legal/data-agreement/

# Cookies page, linked from the footer of every page including the public
# registration form. Must accurately list the cookies we set - see
# docs/personal-data.md, which is the canonical source of that list.
HELP_SITE_COOKIES=https://docs.sortitionlab.org/data-and-legal/cookies/
```

### Session and cookie lifetimes

`SESSION_COOKIE_*` and `REMEMBER_COOKIE_*` control the only two cookies OpenDLP sets.
Before changing their lifetimes, or adding a cookie, read
[docs/personal-data.md](personal-data.md) — the "no cookie banner" conclusion rests on
what those cookies are for and how long they last.

### Site Banner Configuration

Display a banner at the top of all pages to distinguish demo/staging environments from production:

```bash
# Banner text (if empty, no banner is shown)
SITE_BANNER_TEXT=Demo site - do not use production data

# Banner background colour (CSS colour value, default: yellow)
SITE_BANNER_COLOUR=yellow
```

The banner is hidden by default. When `SITE_BANNER_TEXT` is set, a full-width banner appears below the header on all pages.

### Email Configuration

OpenDLP supports two email adapters:

#### Console Adapter (Development)

Logs emails to console instead of sending them:

```bash
EMAIL_ADAPTER=console
```

#### SMTP Adapter (Production)

Sends emails via SMTP server:

```bash
EMAIL_ADAPTER=smtp

# SMTP server settings
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USE_TLS=true

# SMTP authentication
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password

# Sender information
SMTP_FROM_EMAIL=noreply@example.com
SMTP_FROM_NAME=OpenDLP
```

**Production with Postfix Relay:**

For production deployments using the Postfix container as an SMTP relay, see detailed configuration in [docs/postfix_configuration.md](postfix_configuration.md).

### Translation Settings

```bash
# Comma-separated language codes
SUPPORTED_LANGUAGES=en,es,fr,de

# Default language
BABEL_DEFAULT_LOCALE=en

# Default timezone
BABEL_DEFAULT_TIMEZONE=UTC
```

See [docs/translations.md](translations.md) for translation management workflow.

### Feature Flags

Toggle features per-environment using environment variables with the `FF_` prefix:

```bash
# Enable a feature
FF_MY_FEATURE=true

# Disable a feature (or simply don't set the variable)
FF_MY_FEATURE=false
```

**Naming convention:** Variable names are normalised by stripping the `FF_` prefix and lowercasing. So `FF_MY_FEATURE` becomes `my_feature` in code.

**Supported values:** `true`/`false`, `yes`/`no`, `on`/`off`, `1`/`0` (case-insensitive). Unset variables default to `false`.

**In Python code:**

```python
from opendlp.feature_flags import has_feature

if has_feature("my_feature"):
    # feature-specific logic
    ...
```

**In Jinja templates:**

```jinja
{% if feature('my_feature') %}
  <p>This is only shown when the feature is enabled.</p>
{% endif %}
```

**Known flags:**

| Flag | Default | Purpose |
|------|---------|---------|
| `FF_REGISTRATION_PAGE` | `false` | Enables the public registration page routes (`/register/<slug>`, `/register/<slug>/thank-you`, `/r/<short_slug>`, `/registration-closed`). When unset or `false`, those routes return 404. |

## Environment Files

### Development: `.env`

Create a `.env` file in the project root:

```bash
# .env
FLASK_ENV=development
DEBUG=true
SECRET_KEY=dev-secret-key-change-in-production  # pragma: allowlist secret

DB_HOST=localhost
DB_PORT=54321
DB_NAME=opendlp
DB_USER=opendlp
DB_PASSWORD=abc123

REDIS_HOST=localhost
REDIS_PORT=6379

EMAIL_ADAPTER=console
```

### Production: `.env.prod`

Create a `.env.prod` file for production (never commit this file):

```bash
# .env.prod
FLASK_ENV=production
DEBUG=false
SECRET_KEY=your-cryptographically-secure-secret-key

DATABASE_URL=postgresql://opendlp:secure-password@postgres:5432/opendlp  # pragma: allowlist secret

REDIS_HOST=redis
REDIS_PORT=6379

EMAIL_ADAPTER=smtp
SMTP_HOST=postfix
SMTP_PORT=25
SMTP_USE_TLS=false
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME=OpenDLP

# Upstream SMTP relay (see docs/postfix_configuration.md)
RELAYHOST=smtp.sendgrid.net:587
RELAYHOST_USERNAME=apikey
RELAYHOST_PASSWORD=SG.your-api-key-here
ALLOWED_SENDER_DOMAINS=yourdomain.com

# Two-factor authentication (required if users will enable 2FA)
TOTP_ENCRYPTION_KEY=your-32-byte-base64-encoded-key-here
```

## Configuration Validation

The configuration classes validate required settings at startup:

- `FlaskProductionConfig` raises an error if `SECRET_KEY` is not set
- Database connection is validated on first use
- Redis connection is validated when session storage is accessed

## Accessing Configuration in Code

### In Flask Routes

```python
from flask import current_app

@app.route('/status')
def status():
    debug_mode = current_app.config['DEBUG']
    return {'debug': debug_mode}
```

### In Domain/Service Layer

Pass configuration values as function parameters rather than accessing `current_app` directly:

```python
# Good - explicit dependencies
def send_invite_email(email: str, invite_code: str, smtp_config: SMTPConfig):
    ...

# Avoid - implicit Flask dependency in service layer
def send_invite_email(email: str, invite_code: str):
    smtp_host = current_app.config['SMTP_HOST']  # Bad - couples to Flask
    ...
```

## Security Best Practices

1. **Never commit `.env` or `.env.prod` files** - Add them to `.gitignore`
2. **Use strong SECRET_KEY** - At least 32 random characters
3. **Rotate secrets regularly** - Update SECRET_KEY and database passwords periodically
4. **Use environment-specific secrets** - Different secrets for dev/staging/production
5. **Store production secrets securely** - Use secret management tools (AWS Secrets Manager, HashiCorp Vault, etc.)
