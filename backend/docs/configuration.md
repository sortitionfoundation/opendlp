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
