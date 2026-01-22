# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenDLP (Open Democratic Lottery Platform) is a Flask web application for supporting Citizens' Assemblies through stratified selection processes. The project follows Domain-Driven Design principles from "Architecture Patterns with Python" with clear separation between domain models, adapters, service layer, and entrypoints.

**Technology Stack:** Flask, SQLAlchemy, PostgreSQL, Redis, following DDD architecture

## Architecture

The codebase follows a layered architecture:

```txt
src/opendlp/
    domain/           # Plain Python domain objects (core business logic)
    adapters/         # SQLAlchemy models and database adapters
    service_layer/    # Repository and UnitOfWork abstractions
    entrypoints/      # Flask routes and web interface
```

Key architectural principles:

- Domain models are plain Python objects, testable without Flask/SQLAlchemy
- SQLAlchemy mappings use `map_imperatively()` in adapters
- Users/Organisers are separate aggregates from Assembly/Registrants
- Extensive use of JSON columns for flexible data storage
- Use existing Flask extensions for security (flask-login, flask-session, etc.)

## Project Structure

**Note:** The repository has a monorepo structure. When running Claude from the `backend/` directory:

- The git root and `.git/` directory are in the parent directory (`opendlp/`)
- The `.secrets.baseline` file is also in the parent directory, not in `backend/`
- Git operations and secret scanning use the parent directory context

## First Time Local Setup

If setting up the project from scratch:

```bash
# 1. Create .env file
cp env.example .env

# 2. Install dependencies and set up environment
just install

# 3. Start Docker services (PostgreSQL, Redis)
just start-local-docker

# 4. Run database migrations
just migrate

# 5. Create an admin user (password must be 10+ characters)
uv run opendlp users add --email admin@example.com

# 6. Start the application
just run

# 7. Access at http://localhost:5000
```

### Database Connection (for external DB viewers)

| Setting  | Local Dev | Test DB  |
|----------|-----------|----------|
| Host     | localhost | localhost|
| Port     | 54321     | 54322    |
| User     | opendlp   | opendlp  |
| Password | abc123    | abc123   |
| Database | opendlp   | opendlp  |

Connection string: `postgresql://opendlp:abc123@localhost:54321/opendlp` <!-- pragma: allowlist secret -->

## Development Commands

### Package Management

All Python packages are managed with `uv` - **never use pip, poetry, or other package managers**.

```bash
# Initial setup
uv sync
uv pip install -e .

# Add dependencies
uv add package_name
uv add --group dev package_name  # for dev dependencies
```

### Testing and Quality

```bash
# Run all tests with coverage
just test

# Watch tests on file changes
just watch-tests

# Run all quality checks (linting, type checking, dependency analysis)
just check

# Individual quality tools
uv run mypy                    # Type checking
uv run deptry src              # Check for obsolete dependencies
uv tool run prek run -a        # Run linting
```

See [docs/testing.md](docs/testing.md) for complete testing strategy including BDD tests.

### Running the Application

```bash
# Local development with Flask
just run

# Flask shell
just flask-shell

# Run with Docker
just start-docker         # Detached mode
just start-docker-b       # Blocking mode with logs

# Services only (PostgreSQL for local development)
just start-services-docker
just stop-services-docker
```

See [docs/docker.md](docs/docker.md) for complete Docker setup and deployment guide.

### Database Access

```bash
# Connect to PostgreSQL (password: abc123)
just psql
```

## Configuration

Configuration is managed through `src/opendlp/config.py` which loads from environment variables.

### Key Environment Variables

**Required in production:**

- `SECRET_KEY`: Flask secret key (must be set in production)
- `DATABASE_URL` or `DB_HOST`/`DB_PASSWORD`: PostgreSQL connection
- `REDIS_HOST`: Redis connection for sessions

**Optional:**

- `FLASK_ENV`: development/testing/production (default: development)
- `DEBUG`: true/false (default: false)
- `OAUTH_GOOGLE_CLIENT_ID`/`OAUTH_GOOGLE_CLIENT_SECRET`: Google OAuth
- `TASK_TIMEOUT_HOURS`: Background task timeout in hours (default: 24)
- `INVITE_EXPIRY_HOURS`: Invite expiration (default: 168)
- `EMAIL_ADAPTER`: Email backend type - "console" or "smtp"
- `SMTP_*`: SMTP configuration for email sending

See [docs/configuration.md](docs/configuration.md) for complete configuration reference.

## Core Domain Models

### Primary Entities

- **User** (`domain/users.py`): Authentication, roles, permissions
- **Assembly** (`domain/assembly.py`): Citizens' assembly configuration
- **UserAssemblyRole** (`domain/users.py`): Assembly-specific permissions
- **UserInvite** (`domain/user_invites.py`): Invite code system

### Key Business Rules

- All primary keys are UUIDs
- Users require valid invites for registration
- Global roles: admin, global-organiser, user
- Assembly roles: organiser, confirmation-caller
- OAuth and password authentication both supported

## Development Patterns

### Code Style

- Follow Black code style (double quotes preferred)
- All code files start with 2-line ABOUTME comment
- Type hints required (`mypy` configured with strict settings)
- Line length: 120 characters (configured in Ruff)
- Don't use `datetime.utcnow()` - instead use `datetime.now(UTC)` - or `opendlp.utils.aware_utcnow` if you need to pass a function with no arguments
- Prefer the empty string as the default for string arguments, rather than `str | None`

### Internationalization (i18n)

All user-facing strings must be wrapped in gettext calls for translation:

- Use `_()` for immediate translation in templates and flash messages
- Use `_l()` for lazy translation in exceptions and class-level definitions
- Import from `opendlp.translations`: `from opendlp.translations import gettext as _, lazy_gettext as _l`
- In templates use: `{{ _('Text to translate') }}`
- Support parameters: `_('Hello %(name)s', name=user.name)`

After adding new translatable strings, regenerate translations with:

```bash
just translate-regen
```

See [docs/translations.md](docs/translations.md) for translation management workflow.

See [docs/sortition_error_translations.md](docs/sortition_error_translations.md) for translating sortition-algorithms library errors and reports.

### Database Patterns

- Foreign keys are regular UUID columns (not SQLAlchemy relationships in domain)
- Standard fields as columns, variable data as JSON
- Use imperative SQLAlchemy mapping in adapters

**Important:** When using imperative SQLAlchemy mapping for mypy compatibility, use ORM table column references in repository implementations instead of domain object attributes:

```python
# ✅ CORRECT - use ORM table columns for filtering/ordering
self.session.query(User).filter(orm.users.c.global_role == role)
self.session.query(Assembly).order_by(orm.assemblies.c.created_at.desc())

# ❌ INCORRECT - mypy cannot type-check domain object attributes
self.session.query(User).filter(User.global_role == role)  # mypy error
self.session.query(Assembly).order_by(Assembly.created_at.desc())  # mypy error
```

This approach maintains the separation between domain objects (plain Python) and persistence (SQLAlchemy) while ensuring full type safety. The SQLAlchemy mypy plugin is enabled via `plugins = ["sqlalchemy.ext.mypy.plugin"]` in pyproject.toml.

### Security

- Use mature Flask extensions: flask-login, flask-session, flask-security
- Store sessions in Redis (flask-session)
- Werkzeug.security for password hashing
- Role-based access control throughout

## Further Documentation

### General Documentation

- [Testing Strategy](docs/testing.md) - Unit, integration, e2e, and BDD testing
- [Configuration Guide](docs/configuration.md) - Detailed environment variables and config classes
- [Background Tasks](docs/background_tasks.md) - Task system architecture and monitoring
- [Docker Setup](docs/docker.md) - Docker Compose configurations and deployment
- [Deployment Guide](docs/deploy.md) - Production deployment and reverse proxy setup
- [Translation Management](docs/translations.md) - i18n workflow for application strings
- [Sortition Error Translations](docs/sortition_error_translations.md) - Translating sortition-algorithms library errors and reports
- [Postfix Email Configuration](docs/postfix_configuration.md) - SMTP relay setup for production
- [Google Service Account Setup](docs/google_service_account.md) - Google Sheets integration credentials
- [Project Specification](docs/spec.md) - Original project specification

### Agent-Specific Documentation

When working on frontend issues, see:

- [Frontend Design System](docs/agent/frontend_design_system.md) - GOV.UK styling and build pipeline
- [GOV.UK Components](docs/agent/govuk_components.md) - Component usage and HTML examples
- [Frontend Testing](docs/agent/frontend_testing.md) - Playwright MCP debugging workflows
- [Migration Notes](docs/agent/migration_notes.md) - Bootstrap to GOV.UK conversion guide

Feature specifications:

- [CSV Upload Feature](docs/agent/csv_upload_feature.md) - Specification for CSV participant data upload
