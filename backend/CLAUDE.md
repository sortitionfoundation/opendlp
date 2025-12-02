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
- `TASK_TIMEOUT_HOURS`: Background task timeout in hours (default: 24)
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

### BDD Testing

The project includes Behavior-Driven Development (BDD) tests using pytest-bdd and Playwright for end-to-end testing:

**BDD Test Structure:**

- `features/` - Gherkin feature files (.feature)
- `tests/bdd/` - BDD test implementation and fixtures
- `tests/bdd/conftest.py` - BDD-specific fixtures including server management
- `tests/bdd/config.py` - Test configuration (URLs, credentials)
- `tests/bdd/shared/ui_shared.py` - Shared step definitions

**Running BDD Tests:**

```bash
# Run BDD tests (shows browser)
just test-bdd

# Run BDD tests headless (for CI)
just test-bdd-headless

# Install development dependencies (including Playwright browsers)
just install-dev
```

**BDD Test Infrastructure:**

- Uses `FlaskTestPostgresConfig` (port 54322) for database isolation
- Auto-starts Flask test server on port 5002 (avoids conflict with dev server on 5000)
- Creates admin user and fresh database state for each test
- Service layer integration for creating test data (invites, users)
- Playwright for browser automation with cross-browser support

**Key BDD Fixtures:**

- `test_database` - PostgreSQL test database setup
- `test_server` - Auto-managed Flask server (session scope)
- `admin_user` - Pre-created admin user for testing
- `user_invite` - Valid invite code generated via service layer
- `clean_database` - Fresh database state per test
- `logged_in_page` - Browser page with admin user logged in

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

### Internationalization (i18n)

All user-facing strings must be wrapped in gettext calls for translation:

- Use `_()` for immediate translation in templates and flash messages
- Use `_l()` for lazy translation in exceptions and class-level definitions
- Import from `opendlp.translations`: `from opendlp.translations import getext as _, lazy_gettext as _l`
- In templates use: `{{ _('Text to translate') }}`
- Support parameters: `_('Hello %(name)s', name=user.name)`

See `docs/translations.md` for translation management workflow.

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

- `compose.yaml`: Full application with PostgreSQL
- `compose.production.yaml`: Full application with PostgreSQL, for production deployment
- `compose.localdev.yaml`: Services only for local development
- `compose.test.yaml`: Services only for local testing

The application runs on port 5005, PostgreSQL on 54321 (mapped from 5432).

## Frontend Testing and Debugging

### Using Playwright MCP Server

When troubleshooting HTML, CSS, and JavaScript issues in the application frontend, use the Playwright MCP server tools:

1. **Accessing frontend pages**:
   - Navigate to `http://localhost:5000/` or the configured port
   - Use `mcp__playwright__browser_navigate` to open pages
   - Use `mcp__playwright__browser_snapshot` to capture the current page state
   - Use `mcp__playwright__browser_console_messages` to view JavaScript console output

2. **Common debugging workflows**:
   - **HTML/CSS issues**: Use `mcp__playwright__browser_snapshot` to inspect the DOM structure
   - **JavaScript errors**: Check `mcp__playwright__browser_console_messages` for error logs
   - **Interactive debugging**: Use `mcp__playwright__browser_evaluate` to run JavaScript in the page context
   - **Network issues**: Monitor API calls with `mcp__playwright__browser_network_requests`

## Frontend Design System

### GOV.UK Design System with Sortition Foundation Branding

This project uses the GOV.UK Frontend framework v5.11.1 with custom Sortition Foundation styling. The design system is built using Sass/SCSS compilation.

**Key Files:**

- `src/scss/application.scss` - Main SCSS file importing govuk-frontend and custom styles
- `src/scss/_sortition.scss` - Sortition Foundation color palette variables
- `static/css/application.css` - Compiled CSS output (never edit directly)

### Build Pipeline

CSS must be built using npm/Sass before running the application:

```bash
# Build CSS once
just build-css
# or: npm run build:sass

# Watch and rebuild CSS on changes
just watch-css
# or: npm run watch:sass

# Build and run application
just run  # Automatically builds CSS first
```

### Sortition Foundation Color Palette

Custom color variables defined in `_sortition.scss`:

```scss
$hot-pink: #e91e63;
$burnt-orange: #ff7043;
$purple-red: #9c27b0;
$blood-red: #c62828;
$sap-green: #4caf50;
$woad-blue: #3f51b5;
$scarlet-red: #f44336;
$saffron-yellow: #ffeb3b;
$buttermilk: #f5f5dc;
$dark-grey: #424242;
$white: #ffffff;
```

### HTML Template Requirements

All templates must extend `base.html` which includes:

1. **Required CSS classes on body element:**

   ```html
   <body class="govuk-template__body govuk-frontend-supported"></body>
   ```

2. **CSS import (compiled, not CDN):**

   ```html
   <link
     rel="stylesheet"
     href="{{ url_for('static', filename='css/application.css') }}"
   />
   ```

3. **JavaScript initialization:**

   ```html
   <script src="https://cdn.jsdelivr.net/npm/govuk-frontend@5.11.1/dist/govuk/all.bundle.min.js"></script>
   <script>
     document.addEventListener("DOMContentLoaded", function () {
       if (typeof window.GOVUKFrontend !== "undefined") {
         window.GOVUKFrontend.initAll();
       }
     });
   </script>
   ```

### GOV.UK Component Usage

**Common Layout Structure:**

```html
<div class="govuk-width-container">
  <div class="govuk-grid-row">
    <div class="govuk-grid-column-full">
      <!-- Content -->
    </div>
  </div>
</div>
```

**Grid System:**

- `govuk-grid-column-full` - Full width
- `govuk-grid-column-two-thirds` - 2/3 width
- `govuk-grid-column-one-third` - 1/3 width
- `govuk-grid-column-one-half` - 1/2 width

**Typography:**

- `govuk-heading-xl` - Extra large heading
- `govuk-heading-l` - Large heading
- `govuk-heading-m` - Medium heading
- `govuk-heading-s` - Small heading
- `govuk-body` - Body text
- `govuk-body-l` - Large body text
- `govuk-body-s` - Small body text

**Buttons:**

- `govuk-button` - Primary button
- `govuk-button--secondary` - Secondary button
- `govuk-button--start` - Start button with arrow icon
- `govuk-button--white` - Custom white button (Sortition styling)

**Navigation:**

- Mobile-responsive navigation handled by GOV.UK Frontend JavaScript
- Custom styling for Sortition Foundation branding in `application.scss`
- Mobile menu button becomes visible on screens < 48.0625em
- Cross-browser compatibility (Chrome/Firefox differences handled)

**Tags and Status:**

```html
<strong class="govuk-tag govuk-tag--green">Status</strong>
<strong class="govuk-tag govuk-tag--blue">Role</strong>
<strong class="govuk-tag govuk-tag--red">Alert</strong>
```

**Summary Lists (for key-value data):**

```html
<dl class="govuk-summary-list">
  <div class="govuk-summary-list__row">
    <dt class="govuk-summary-list__key">Label</dt>
    <dd class="govuk-summary-list__value">Value</dd>
  </div>
</dl>
```

### Custom Components

**Assembly Cards:**

```html
<div class="assembly-card">
  <h3 class="govuk-heading-m">Title</h3>
  <p class="govuk-body-s">Description</p>
  <dl class="govuk-summary-list">
    <!-- Summary list content -->
  </dl>
</div>
```

**Feature Cards (front page):**

```html
<div class="feature-card">
  <h3 class="govuk-heading-m">Feature Title</h3>
  <p class="govuk-body">Feature description</p>
</div>
```

**Key Details Bars (dashboard):**

```html
<div class="dwp-key-details-bar">
  <div class="dwp-key-details-bar__key-details">
    <dt class="govuk-heading-s">Label</dt>
    <dd class="dwp-key-details-bar__primary">Value</dd>
  </div>
</div>
```

**Hero Section:**

```html
<div class="hero-section govuk-!-padding-top-6 govuk-!-padding-bottom-6">
  <!-- Hero content with burnt-orange background -->
</div>
```

### Accessibility Requirements

- All interactive elements must be keyboard accessible
- Color contrast ratios must meet WCAG standards
- Screen reader compatibility maintained
- Mobile navigation close button hidden but functional for assistive technology
- Focus styles use saffron-yellow highlighting

### Migration Notes

When converting from Bootstrap to GOV.UK:

- Replace Bootstrap grid (`row`, `col-*`) with GOV.UK grid (`govuk-grid-row`, `govuk-grid-column-*`)
- Replace Bootstrap buttons (`btn`, `btn-primary`) with GOV.UK buttons (`govuk-button`)
- Replace Bootstrap cards with custom styled components
- Use GOV.UK spacing utilities (`govuk-!-margin-*`, `govuk-!-padding-*`)
- Ensure all custom styling uses Sortition Foundation color palette
- Test mobile navigation across Chrome and Firefox
- Verify CSS specificity doesn't conflict with GOV.UK base styles
