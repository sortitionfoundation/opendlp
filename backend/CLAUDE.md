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
# or: uv run python -m pytest --tb=short --cov --cov-config=pyproject.toml --cov-report=html

# Watch tests on file changes
just watch-tests

# Run all quality checks (linting, type checking, dependency analysis)
just check

# Individual quality tools
uv run mypy                    # Type checking
uv run deptry src             # Check for obsolete dependencies
uv run pre-commit run -a      # Run linting
```

### Running the Application

```bash
# Local development with Flask
just run
# or: uv run flask run --debug

# Flask shell
just flask-shell

# Run with Docker
just start-docker         # Detached mode
just start-docker-b       # Blocking mode with logs
just restart-docker       # Stop, rebuild, start detached
just restart-docker-b     # Stop, rebuild, start blocking

# Services only (PostgreSQL for local development)
just start-services-docker
just stop-services-docker
```

### Database Access

```bash
# Connect to PostgreSQL (password: abc123)
just psql
```

## Configuration

Configuration is managed through `src/opendlp/config.py` which loads from environment variables:

### Required Environment Variables

- `SECRET_KEY`: Flask secret key (must be set in production)
- `DATABASE_URL` or `DB_HOST`/`DB_PASSWORD`: PostgreSQL connection
- `REDIS_HOST`: Redis connection for sessions

### Optional Environment Variables

- `FLASK_ENV`: development/testing/production (default: development)
- `DEBUG`: true/false (default: false)
- `OAUTH_GOOGLE_CLIENT_ID`/`OAUTH_GOOGLE_CLIENT_SECRET`: Google OAuth
- `SELECTION_TIMEOUT`: Background task timeout in seconds (default: 600)
- `INVITE_EXPIRY_HOURS`: Invite expiration (default: 168)

### Configuration Classes

- `FlaskConfig`: Base development configuration
- `FlaskTestConfig`: Uses SQLite in-memory database
- `FlaskProductionConfig`: Production with stricter validation

Use `get_config()` to get the appropriate configuration based on `FLASK_ENV`.

## Testing Strategy

The project has three levels of testing:

- **Unit tests** (`tests/unit/`): Domain logic, no external dependencies
- **Integration tests** (`tests/integration/`): Database operations, service layer
- **End-to-end tests** (`tests/e2e/`): Complete user workflows

All test output must be pristine to pass. Test configuration is in `pyproject.toml`.

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
- don't use `datetime.utcnow()` - instead use `datetime.now(UTC)` - or `opendlp.utils.aware_utcnow` if you need to pass a function with no arguments
- prefer the empty string as the default for string arguments, rather than `str | None`

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

## Background Tasks

The application includes a background task system for long-running operations like stratified selections:

- Tasks run with configurable timeouts
- Status tracking: running, complete, failed
- Error handling and retry capability
- Located in `service_layer/tasks.py`

## Docker Setup

Two Docker Compose configurations:

- `docker-compose.yml`: Full application with PostgreSQL
- `docker-compose.localdev.yml`: Services only for local development

The application runs on port 5005, PostgreSQL on 54321 (mapped from 5432).
