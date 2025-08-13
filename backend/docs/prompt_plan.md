# Prompts by claude

I'll create a detailed blueprint for building the OpenDLP project, breaking it down into manageable, testable chunks that build on each other progressively.

## Project Blueprint Overview

### High-Level Architecture Phases

**Phase 1: Foundation (Steps 1-5)**

- Project structure and configuration
- Domain models (plain Python objects)
- Database layer with SQLAlchemy imperative mapping
- Repository pattern implementation
- Unit of Work for transaction management

**Phase 2: Service Layer (Steps 6-7)**

- User management services
- Assembly management services

**Phase 3: Web Application (Steps 8-11)**

- Flask application setup
- Basic authentication
- CLI commands
- Initial web interface

**Phase 4: Advanced Features (Steps 12-15)**

- OAuth integration
- Invite system
- Enhanced dashboard views
- Background task infrastructure

**Phase 5: Integration Features (Steps 16-17)**

- Google Sheets integration
- Selection algorithm implementation

---

## Detailed Implementation Prompts

### Step 1: Project Setup and Configuration ✅ COMPLETED

```text
Create the initial project structure for OpenDLP, a Flask-based Citizens' Assembly management system following Domain-Driven Design principles.

Set up the following:
1. Create directory structure:
   - src/opendlp/domain/ (for plain Python domain objects)
   - src/opendlp/adapters/ (for SQLAlchemy models)
   - src/opendlp/entrypoints/ (for Flask routes)
   - src/opendlp/service_layer/ (for repositories and UoW)
   - tests/unit/, tests/integration/, tests/e2e/

2. Create pyproject.toml with these dependencies:
   - Flask and essential extensions (flask-login, flask-session)
   - SQLAlchemy 2.0+ with PostgreSQL support
   - Redis for session storage
   - Alembic for migrations
   - pytest for testing
   - python-dotenv for configuration

3. Create src/opendlp/config.py with:
   - Configuration class that reads from environment variables
   - Settings for DATABASE_URL, SECRET_KEY, REDIS_URL
   - Testing configuration subclass
   - Development and production configurations

4. Create a justfile with common commands:
   - just test (runs all tests)
   - just db-upgrade (runs migrations)
   - just run (starts development server)

5. Write tests/unit/test_config.py to verify:
   - Configuration loads from environment
   - Test config overrides properly
   - Required settings raise errors if missing

Use modern Python practices (3.12+), type hints throughout, and ensure all configuration is testable without external dependencies.
```

---

### Step 2: Domain Models ✅ COMPLETED

```text
Create the core domain models for OpenDLP as plain Python objects without any framework dependencies.

Implement in src/opendlp/domain/:

1. Create domain/users.py with:
   - User class with attributes: id (UUID), username, email, password_hash, oauth_provider, oauth_id, global_role (enum: admin/global-organiser/user), created_at, is_active
   - UserAssemblyRole class with: id, user_id, assembly_id, role (enum: assembly-manager/confirmation-caller), created_at
   - Methods: User.can_access_assembly(assembly_id), User.has_global_admin(), User.switch_to_oauth(provider, oauth_id)

2. Create domain/assembly.py with:
   - Assembly class with: id (UUID), title, question, gsheet, first_assembly_date, status (enum: active/archived), created_at, updated_at
   - Method to validate assembly data

3. Create domain/user_invites.py with:
   - UserInvite class with: id, code, global_role, created_by, created_at, expires_at, used_by, used_at
   - Methods: is_valid() (checks expiry and usage), use(user_id) (marks as used)

4. Create domain/value_objects.py with:
   - Enums for GlobalRole, AssemblyRole, AssemblyStatus
   - Any shared validation functions

5. Write comprehensive unit tests in tests/unit/domain/:
   - test_users.py: Test user creation, role checking, OAuth switching
   - test_assembly.py: Test assembly creation and validation
   - test_user_invites.py: Test invite validity and usage

All domain models should be plain Python classes with no database dependencies. Use dataclasses or regular classes with __init__ methods. Include proper type hints and validation logic.
```

---

### Step 3: Database Setup with SQLAlchemy

```text
Set up SQLAlchemy with imperative mapping to keep domain models separate from database concerns.

Create in src/opendlp/adapters/:

1. Create adapters/orm.py with:
   - SQLAlchemy table definitions for users, assemblies, user_assembly_roles, user_invites
   - All tables use UUID primary keys
   - Proper foreign key relationships
   - JSON columns where specified in the spec

2. Create adapters/database.py with:
   - Database connection setup using connection pooling
   - Session factory configuration
   - start_mappers() function that uses map_imperatively() to map domain objects to tables
   - Ensure mapping doesn't modify domain objects

3. Create Alembic configuration:
   - alembic.ini in project root
   - migrations/env.py configured to use our metadata
   - Initial migration creating all tables

4. Write tests/integration/test_orm.py:
   - Test that domain objects can be saved and retrieved
   - Test relationships work correctly
   - Test JSON columns serialize/deserialize properly
   - Use PostgreSQL test database

5. Review docker-compose.yml and docker-compose.localdev.yml for development:
   - PostgreSQL service
   - Redis service
   - Proper volumes for data persistence

The imperative mapping should be completely separate from domain models. Domain models should remain unaware of the database. Include proper indexes for foreign keys and commonly queried fields.
```

---

### Step 4: Repository Pattern ✅ COMPLETED

```text
Implement the Repository pattern to abstract database operations from business logic.

Create in src/opendlp/service_layer/:

1. Create service_layer/repositories.py with:
   - AbstractRepository base class with add(), get(), list() methods
   - UserRepository(AbstractRepository) with:
     * get_by_username(username)
     * get_by_email(email)
     * get_users_for_assembly(assembly_id)
   - AssemblyRepository(AbstractRepository) with:
     * get_active_assemblies()
     * get_assemblies_for_user(user_id)
   - UserInviteRepository(AbstractRepository) with:
     * get_by_code(code)
     * get_valid_invites()

2. Create adapters/sql_repository.py with:
   - SqlAlchemyRepository implementations for each repository
   - Proper query building with filters
   - Lazy loading configuration
   - Error handling for database operations

3. Write tests/integration/test_repositories.py:
   - Test each repository method
   - Test filtering and ordering
   - Test relationships are loaded correctly
   - Test transaction isolation

4. Create service_layer/unit_of_work.py with:
   - AbstractUnitOfWork with __enter__, __exit__, commit, rollback
   - SqlAlchemyUnitOfWork implementation
   - Proper session management
   - Repository initialization in UoW

5. Write tests/integration/test_unit_of_work.py:
   - Test transaction commit and rollback
   - Test multiple operations in one transaction
   - Test isolation between UoW instances

Use dependency injection patterns. Repositories should return domain objects, not SQLAlchemy objects. Include proper error handling and logging.
```

---

### Step 5: User Service Layer

```text
Create the user management service layer with business logic for user operations.

Implement in src/opendlp/service_layer/:

1. Create service_layer/user_service.py with:
   - create_user(uow, username, email, password=None, oauth_provider=None, oauth_id=None, invite_code=None)
   - authenticate_user(uow, username, password)
   - get_user_assemblies(uow, user_id)
   - assign_assembly_role(uow, user_id, assembly_id, role)
   - validate_and_use_invite(uow, invite_code, user_id)

2. Create service_layer/security.py with:
   - hash_password(password) using werkzeug.security
   - verify_password(password, hash)
   - generate_invite_code() for unique codes
   - Password strength validation

3. Create service_layer/exceptions.py with:
   - Custom exceptions: UserAlreadyExists, InvalidCredentials, InvalidInvite, InsufficientPermissions
   - Proper error messages and codes

4. Write tests/unit/test_user_service.py:
   - Test user creation with password
   - Test user creation with OAuth
   - Test authentication success/failure
   - Test invite validation and usage
   - Mock the UoW and repositories

5. Write tests/integration/test_user_service_integration.py:
   - Test full user creation flow with database
   - Test role assignment
   - Test concurrent invite usage
   - Test transaction rollback on errors

Services should handle all business logic, validation, and coordination between repositories. Use the Unit of Work pattern for all database operations. Include comprehensive logging.
```

---

### Step 6: Assembly Service Layer

```text
Create the assembly management service layer for handling assembly operations.

Implement in src/opendlp/service_layer/:

1. Create service_layer/assembly_service.py with:
   - create_assembly(uow, title, question, gsheet, first_assembly_date, created_by_user_id)
   - update_assembly(uow, assembly_id, user_id, **updates)
   - get_assembly_with_permissions(uow, assembly_id, user_id)
   - archive_assembly(uow, assembly_id, user_id)
   - get_user_accessible_assemblies(uow, user_id)

2. Update service_layer/permissions.py with:
   - can_manage_assembly(user, assembly) checking global and assembly roles
   - can_view_assembly(user, assembly)
   - require_assembly_permission decorator for services
   - Global role permission checks

3. Write tests/unit/test_assembly_service.py:
   - Test assembly creation
   - Test permission checks for different roles
   - Test assembly updates
   - Mock repositories and UoW

4. Write tests/integration/test_assembly_service_integration.py:
   - Test full assembly lifecycle
   - Test permission enforcement with real users
   - Test listing assemblies for different user roles

5. Create service_layer/invite_service.py with:
   - generate_invite(uow, created_by_user_id, global_role, expires_in_hours=168)
   - list_invites(uow, include_expired=False)
   - revoke_invite(uow, invite_id)

Services should enforce business rules and permissions. Include audit logging for all assembly modifications.
```

---

### Step 7: Flask Application Foundation

```text
Set up the Flask application with proper structure and configuration.

Create in src/opendlp/entrypoints/:

1. Create entrypoints/flask_app.py with:
   - create_app() factory function
   - Configuration loading from config.py
   - Blueprint registration
   - Extension initialization (Flask-Login, Flask-Session)
   - Error handlers for 404, 500, etc.
   - Logging configuration

2. Create entrypoints/extensions.py with:
   - Initialize Flask-Login
   - Initialize Flask-Session with Redis store
   - Initialize Flask-Talisman for security headers
   - Database session management

3. Create entrypoints/blueprints/auth.py with:
   - /login route (GET and POST)
   - /logout route
   - /register route with invite code
   - Basic templates for auth pages

4. Create entrypoints/blueprints/main.py with:
   - / route showing dashboard
   - /assemblies route listing assemblies
   - Login required decorators

5. Write tests/integration/test_flask_app.py:
   - Test app factory creates app
   - Test configuration loads correctly
   - Test blueprints are registered
   - Test error handlers work

6. Create templates/base.html and basic templates:
   - Use Jinja2 template inheritance
   - Include CSS framework (Bootstrap or Tailwind)
   - Flash message support
   - Navigation structure

7. Create entrypoints/wsgi.py:
   - Production WSGI entry point
   - Proper app initialization

Include CSRF protection, secure headers, and proper session management. Ensure all routes use the service layer, not direct database access.
```

---

### Step 8: Authentication Implementation

```text
Implement authentication using Flask-Login and prepare for OAuth.

Enhance authentication in src/opendlp/entrypoints/:

1. Update entrypoints/auth.py with:
   - User loader callback for Flask-Login
   - Login view with username/password
   - Registration view requiring valid invite code
   - Password reset request flow (prepare for email)
   - Remember me functionality

2. Create entrypoints/forms.py with:
   - LoginForm with CSRF protection
   - RegistrationForm with password confirmation
   - Invite code validation in forms
   - Use Flask-WTF for form handling

3. Create entrypoints/decorators.py with:
   - require_global_role(role) decorator
   - require_assembly_role(role) decorator
   - Combined permission decorators

4. Update templates for authentication:
   - templates/auth/login.html
   - templates/auth/register.html
   - templates/auth/password_reset.html
   - Form error display

5. Write tests/e2e/test_auth_flow.py:
   - Test login/logout flow
   - Test registration with valid invite
   - Test registration with invalid/expired invite
   - Test session persistence
   - Test remember me functionality

6. Create entrypoints/api_auth.py with:
   - JSON API endpoints for authentication
   - Token generation preparation (for future API)
   - Proper error responses

Implement proper session management with Redis backend. Include rate limiting for login attempts. Prepare the structure for OAuth addition.
```

---

### Step 9: CLI Commands

```text
Create CLI commands for system administration using Click.

Create src/opendlp/cli/:

1. Create cli/__init__.py with:
   - Click group for main command
   - Proper context passing
   - Database initialization

2. Create cli/users.py with:
   - add-user command (username, email, role)
   - list-users command with formatting
   - deactivate-user command
   - reset-password command

3. Create cli/invites.py with:
   - generate-invite command with role and expiry
   - list-invites command
   - revoke-invite command

4. Create cli/database.py with:
   - db-init command (create tables)
   - db-upgrade command (run migrations)
   - db-seed command (create test data)

5. Update setup.py or pyproject.toml:
   - Add console_scripts entry point
   - 'opendlp = opendlp.cli:cli'

6. Write tests/unit/test_cli.py:
   - Test command parsing
   - Test output formatting
   - Mock service layer calls

7. Write tests/integration/test_cli_integration.py:
   - Test actual user creation
   - Test invite generation and usage
   - Test database commands

Include proper error handling, colored output for better UX, and confirmation prompts for destructive operations. All commands should use the service layer.
```

---

### Step 10: Dashboard Views

```text
Create the main dashboard and assembly management views.

Implement in src/opendlp/entrypoints/:

1. Create blueprints/dashboard.py with:
   - /dashboard route showing user's assemblies
   - /assemblies/<id> route for assembly details
   - /assemblies/new route for creating assemblies (with permission check)
   - /assemblies/<id>/edit route for editing

2. Create templates/dashboard/:
   - dashboard/index.html with assembly cards/list
   - dashboard/assembly_detail.html with full assembly info
   - dashboard/assembly_form.html for create/edit
   - Responsive design with mobile support

3. Create blueprints/admin.py with:
   - /admin/users route listing all users
   - /admin/users/<id>/roles route for role management
   - /admin/invites route for invite management
   - Admin permission required for all routes

4. Create templates/admin/:
   - admin/users.html with user table
   - admin/user_roles.html for role assignment
   - admin/invites.html for invite management

5. Add static/css/custom.css with:
   - Custom styling for dashboard
   - Status badges for assemblies
   - Responsive grid layouts

6. Write tests/e2e/test_dashboard.py:
   - Test assembly listing for different roles
   - Test assembly creation
   - Test permission enforcement
   - Test responsive design elements

Add proper pagination for lists, search/filter functionality, and loading states. Include JavaScript for dynamic interactions where needed.
```

---

### Step 11: OAuth Integration

```text
Add Google OAuth authentication alongside existing password authentication.

Implement OAuth support:

1. Update entrypoints/oauth.py with:
   - /auth/google route initiating OAuth flow
   - /auth/google/callback handling return
   - Use Authlib or Flask-Dance for OAuth
   - Handle account linking for existing users

2. Update service_layer/user_service.py:
   - find_or_create_oauth_user(uow, provider, oauth_id, email, name)
   - link_oauth_to_existing_user(uow, user_id, provider, oauth_id)
   - Handle email conflicts

3. Update templates/auth/login.html:
   - Add "Sign in with Google" button
   - Explain account options to users

4. Create templates/account/settings.html:
   - Show current auth method
   - Allow switching from password to OAuth
   - Manage connected accounts

5. Update config.py with:
   - OAUTH_GOOGLE_CLIENT_ID
   - OAUTH_GOOGLE_CLIENT_SECRET
   - OAuth redirect URLs

6. Write tests/integration/test_oauth.py:
   - Mock OAuth provider responses
   - Test new user creation via OAuth
   - Test linking OAuth to existing account
   - Test email conflict handling

Ensure invite requirement still applies to OAuth users. Handle edge cases like email changes and account merging.
```

---

### Step 12: Enhanced Invite System

```text
Complete the invite system with full registration flow and management.

Enhance the invite system:

1. Update service_layer/invite_service.py:
   - Add batch invite generation
   - Track invite usage statistics
   - Email invite codes (prepare email service)

2. Create entrypoints/blueprints/registration.py:
   - /register/<invite_code> pre-filled route
   - Multi-step registration wizard
   - Choice between password and OAuth

3. Create templates/registration/:
   - registration/step1_verify.html (check invite)
   - registration/step2_method.html (choose auth)
   - registration/step3_details.html (complete profile)
   - registration/complete.html (success message)

4. Update admin interface:
   - Bulk invite generation
   - Download invite codes as CSV
   - Track invite conversion rates

5. Add invite expiry job:
   - Create cli/jobs.py
   - cleanup-expired-invites command
   - Cron job configuration example

6. Write tests/e2e/test_registration_flow.py:
   - Test complete registration flow
   - Test expired invite handling
   - Test OAuth registration with invite
   - Test invite code in URL

Include proper error messages, user guidance, and analytics tracking for invite usage.
```

---

### Step 13: Background Tasks Infrastructure

```text
Set up background task processing for long-running operations.

Create task infrastructure:

1. Create service_layer/tasks.py with:
   - BaseTask abstract class
   - TaskStatus enum (pending, running, complete, failed)
   - TaskResult storage model
   - Task timeout handling

2. Create adapters/task_queue.py with:
   - Redis-based task queue
   - Task serialization/deserialization
   - Priority queue support
   - Task retry logic

3. Create entrypoints/worker.py:
   - Worker process main loop
   - Task execution with timeout
   - Error handling and logging
   - Graceful shutdown

4. Create service_layer/task_service.py:
   - submit_task(task_type, params, user_id)
   - get_task_status(task_id)
   - cancel_task(task_id)
   - get_user_tasks(user_id)

5. Add task monitoring endpoints:
   - /api/tasks/<id>/status
   - /api/tasks/<id>/cancel
   - WebSocket support for real-time updates (optional)

6. Write tests/integration/test_tasks.py:
   - Test task submission and execution
   - Test timeout handling
   - Test task cancellation
   - Test worker crash recovery

7. Create docker-compose addition:
   - Worker service configuration
   - Proper network setup

Include task progress reporting, result caching, and cleanup of old tasks. Add monitoring and alerting for failed tasks.
```

---

### Step 14: Google Sheets Integration

```text
Implement Google Sheets API integration for data import/export.

Create Google Sheets integration:

1. Create adapters/google_sheets.py with:
   - GoogleSheetsClient class
   - Authentication with service account
   - read_sheet(sheet_id, range) method
   - write_sheet(sheet_id, range, data) method
   - Error handling for API limits

2. Create service_layer/sheets_service.py:
   - import_registrants_from_sheet(uow, assembly_id, sheet_url)
   - export_results_to_sheet(uow, assembly_id, sheet_url)
   - validate_sheet_structure(sheet_url)
   - Auto-detect sheet tabs and columns

3. Create domain/sheet_mapping.py:
   - Column mapping definitions
   - Tab detection logic
   - Data transformation rules
   - Validation rules

4. Update Assembly domain model:
   - Add sheet_config JSON field
   - Store column mappings
   - Track last sync time

5. Create entrypoints/blueprints/sheets.py:
   - /assemblies/<id>/import route
   - /assemblies/<id>/export route
   - /assemblies/<id>/sync-status route
   - Preview before import

6. Write tests/integration/test_sheets.py:
   - Mock Google Sheets API
   - Test data import
   - Test data export
   - Test error handling

7. Add to config.py:
   - GOOGLE_SERVICE_ACCOUNT_KEY
   - API rate limit settings

Include proper error handling for API quotas, data validation, and rollback on import errors.
```

---

### Step 15: Selection Implementation

```text
Implement the selection algorithms for stratified sampling.

Create selection system:

1. Create domain/selection.py with:
   - SelectionParams class
   - SelectionResult class
   - StratificationCriteria class
   - ReplacementConstraints class

2. Create service_layer/selection_service.py:
   - run_test_selection(uow, assembly_id, params)
   - run_full_selection(uow, assembly_id, params, timeout=600)
   - run_replacement_selection(uow, assembly_id, constraints)
   - get_selection_results(uow, selection_id)

3. Create adapters/selection_algorithm.py:
   - Integrate with existing selection library
   - LegacyAlgorithm class (fast, for testing)
   - MaximinAlgorithm class (optimal)
   - Progress callback support

4. Create service_layer/selection_tasks.py:
   - SelectionTask(BaseTask) for background processing
   - Progress reporting
   - Timeout enforcement
   - Result storage

5. Create entrypoints/blueprints/selection.py:
   - /assemblies/<id>/test-selection route
   - /assemblies/<id>/run-selection route
   - /assemblies/<id>/replacements route
   - /selections/<id>/results route

6. Create templates/selection/:
   - selection/test_results.html with feasibility analysis
   - selection/parameters.html for configuration
   - selection/results.html with detailed breakdown
   - selection/replacements.html for replacement flow

7. Write tests/integration/test_selection.py:
   - Test selection with sample data
   - Test timeout handling
   - Test replacement constraints
   - Test result storage

Include comprehensive logging, progress reporting, and error recovery. Store all selection results for audit purposes.
```

---

### Step 16: Integration and Polish

```text
Wire everything together and add polish to the application.

Complete the integration:

1. Create entrypoints/blueprints/api.py:
   - RESTful API endpoints for all services
   - JSON responses for AJAX calls
   - API documentation

2. Add email notifications:
   - Create adapters/email.py
   - Send invite emails
   - Send selection completion notifications
   - Password reset emails

3. Enhance error handling:
   - Custom error pages
   - User-friendly error messages
   - Error tracking/reporting

4. Add data export:
   - CSV export for registrants
   - PDF reports for selections
   - Audit logs export

5. Performance optimizations:
   - Query optimization
   - Caching layer
   - Database indexes
   - Connection pooling

6. Security hardening:
   - Rate limiting
   - Input sanitization
   - Security headers
   - Audit logging

7. Write tests/e2e/test_full_workflow.py:
   - Test complete assembly lifecycle
   - Test user journey from registration
   - Test selection and replacement flow
   - Performance testing

Add monitoring, health checks, and deployment configuration. Include documentation for deployment and operations.
```

---

### Step 17: Production Readiness

```text
Prepare the application for production deployment.

Finalize for production:

1. Create deployment configuration:
   - Dockerfile for application
   - docker-compose.production.yml
   - Kubernetes manifests (optional)
   - nginx configuration

2. Add monitoring:
   - Health check endpoints
   - Metrics collection
   - Log aggregation setup
   - Error tracking (Sentry)

3. Create documentation:
   - README.md with setup instructions
   - API documentation
   - Administrator guide
   - User manual

4. Database migrations:
   - Review all migrations
   - Add migration testing
   - Rollback procedures
   - Backup strategies

5. Security review:
   - Dependency scanning
   - Security checklist
   - Penetration testing prep
   - GDPR compliance check

6. Performance testing:
   - Load testing scripts
   - Database query analysis
   - Cache effectiveness
   - Concurrent user testing

7. Write ops runbook:
   - Common issues and solutions
   - Backup procedures
   - Disaster recovery
   - Scaling guidelines

Ensure zero-downtime deployment capability, proper secrets management, and comprehensive logging.
```

---

## Testing Strategy for Each Step

Each implementation step should follow this testing approach:

1. **Write tests first** (TDD approach)
2. **Unit tests** for business logic (no external dependencies)
3. **Integration tests** for database and external services
4. **End-to-end tests** for complete user workflows
5. **Performance tests** for critical paths
6. **Security tests** for authentication and authorization

## Key Principles Throughout

- **No orphaned code** - Everything connects to previous steps
- **Incremental complexity** - Start simple, add features gradually
- **Always deployable** - Each step produces a working system
- **Test coverage** - Minimum 80% coverage for all new code
- **Documentation** - Update docs with each step
- **Code review ready** - Each step is a logical PR/commit

This approach ensures steady progress while maintaining code quality and system stability throughout the development process.
