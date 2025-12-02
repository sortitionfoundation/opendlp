# OpenDLP Specification

## Project Overview

**Project Name:** OpenDLP (Open Democratic Lottery Platform)

**Purpose:** A web application to support finding representative samples of people to participate in Citizens' Assemblies through stratified selection processes.

**Technology Stack:** Flask, SQLAlchemy, PostgreSQL, Redis, following Domain-Driven Design principles from "Architecture Patterns with Python"

This spec covers laying down the foundations - future specs will cover fleshing out other areas.

## Architecture

### Directory Structure

```
src/
    opendlp/
        adapters/          # SQLAlchemy models and database adapters
        domain/           # Plain Python domain objects
        entrypoints/      # Flask routes and web interface
        service_layer/    # Repository and UnitOfWork classes
tests/
    e2e/                 # End-to-end tests
    integration/         # Integration tests
    unit/                # Unit tests
```

### Design Principles

- Domain models are plain Python objects, testable without Flask/SQLAlchemy
- SQLAlchemy mappings use `map_imperatively()` in adapters
- Service layer provides Repository and UnitOfWork abstractions
- Users/Organisers are separate aggregates from Assembly/Registrants
- Extensive use of JSON columns for flexible data storage
- Use existing flask extensions, particularly for security.

### Development tools

- uv will be used for installing python packages
- Requirements and all python tool settings defined in `pyproject.toml`
- use a justfile for making commands easy to run
- have a docker-compose file for the support services for integration testing

## Core Domain Models

### User

**Location:** `src/opendlp/domain/users.py`

**Attributes:**

- `id`: UUID (primary key)
- `username`: String
- `email`: String
- `password_hash`: String (nullable for OAuth users)
- `oauth_provider`: String (nullable, initially only "google")
- `oauth_id`: String (nullable)
- `global_role`: Enum (admin, global-organiser, user)
- `created_at`: DateTime
- `is_active`: Boolean

**Methods:**

- `can_access_assembly(assembly_id)`: Boolean
- `has_global_admin()`: Boolean
- `switch_to_oauth(provider, oauth_id)`: Updates authentication method

### Assembly

**Location:** `src/opendlp/domain/assembly.py`

**Attributes:**

- `id`: UUID (primary key)
- `title`: String
- `question`: String (policy question for the assembly)
- `gsheet`: String (name/URL of google spreadsheet containing the data)
- `first_assembly_date`: Date
- `status`: Enum (active, archived)
  - note the Enum will be extended later.
- `created_at`: DateTime
- `updated_at`: DateTime

### UserAssemblyRole

**Location:** `src/opendlp/domain/users.py`

**Attributes:**

- `id`: UUID (primary key)
- `user_id`: UUID (foreign key)
- `assembly_id`: UUID (foreign key)
- `role`: Enum (assembly-manager, confirmation-caller)
- `created_at`: DateTime

### UserInvite

**Location:** `src/opendlp/domain/user_invites.py`

**Attributes:**

- `id`: UUID (primary key)
- `code`: String (unique)
- `global_role`: Enum (admin, global-organiser, user)
- `created_by`: UUID (foreign key to User)
- `created_at`: DateTime
- `expires_at`: DateTime (default: 1 week from creation)
- `used_by`: UUID (nullable, foreign key to User)
- `used_at`: DateTime (nullable)

**Methods:**

- `is_valid()`: Boolean
- `use(user_id)`: Marks invite as used

## Database Schema

### Database Rules

- All primary keys are UUIDs
- Foreign keys are regular columns
- Standard fields frequently queried are columns
- Variable data that's read/written as documents is JSON

## User Interface

### Navigation Structure

- **Main Dashboard**: Shows all non-archived assemblies user has access to
- **Assembly Dashboard**: Assembly-specific workspace for detailed management
- **Admin Interface**: User management, invite generation (admin only)

### Permission Model

#### Global Roles

- **admin**: Full system access, user management, all assemblies
- **global-organiser**: Automatic "organiser" role on all assemblies
- **user**: Requires explicit assembly-specific role assignments

#### Assembly-Specific Roles

- **organiser**: Full assembly management (import, selection, confirmation)
- **confirmation-caller**: Limited access to update registrant status and view contact details

### Dashboard Views

#### Main Dashboard

- List of accessible assemblies with summary info:
  - Title, status
  - Quick actions (view, manage)

#### Assembly Dashboard

- Assembly details and configuration
- Selection management (test, run, review results)
- Replacement selection tools
- Background task status

## Core Features

### Stratified Selection

This uses an existing library and reads and writes data from a Google spreadsheet.

#### Test Selection

- Automatically work out which Google spreadsheet tabs to use.
- Uses "legacy" algorithm (fast)
- Shows feasibility analysis
- Displays detailed breakdown:
  - Feature/value combinations
  - Pool size vs targets
  - Achievable numbers
  - Constraint violations

#### Full Selection

- Automatically work out which Google spreadsheet tabs to use.
- Uses "maximin" algorithm
- Background task with timeout (default: 10 minutes)

#### Replacement Selection

- Automatically work out which Google spreadsheet tabs to use - different to Test/Full Selection.
- Only selects from `not-selected` pool
- Unlimited replacement selections allowed

### Background Tasks

**Location:** `src/opendlp/service_layer/tasks.py`

#### Task Management

- Selection tasks run in background
- Status tracking: running, complete, failed
- Timeout enforcement (configurable, default 10 minutes)
- Error logging and user notification
- Task retry capability

#### Error Handling

- System logging for all errors
- In-app notifications for organisers
- Algorithm suggestions highlighted when available

### Authentication & Authorization

#### Authentication Methods

- Username/password (local accounts)
- OAuth (Google initially)
- Users choose one method, can migrate later
- All registrations require valid invite

#### Invite System

- Admin-generated invite codes
- Role-specific invites (admin, global-organiser, user)
- 1-week expiration
- Single-use only
- OAuth users still require invites

#### Registration Flow

1. User receives invite URL
2. Choose authentication method (password or OAuth)
3. Complete registration
4. Assembly-specific roles assigned via admin interface

## Technical Implementation

### Package Management

- Use `uv` for all package management
- Requirements defined in `pyproject.toml`

### Database

- PostgreSQL with JSON column support
- SQLAlchemy ORM with imperative mapping
- Alembic for migrations
- Connection pooling and optimization

### Task Queue

- Background task processing for selections
- Task status tracking and monitoring
- Error handling and retry logic
- Progress reporting

### Logging

- Comprehensive logging for all operations
- Error tracking and monitoring
- User action logging

### Security

- Secure password hashing
- OAuth integration (Google)
- Role-based access control
- Input validation and sanitization
- CSRF protection
- Use mature flask extensions for security where possible. In particular use these:
  - flask-login for session management
  - flask-security for auth, registration, password reset
    - this assumes we can make it work with the domain model/adapter split
  - flask-session for server-side sessions - store in redis
  - flask-talisman for secure headers
  - werkzeug.security for password hashing

## CLI Commands

### User Management

```bash
# Add new user
opendlp add-user --username john_doe --email john@example.com --role admin

# List users
opendlp list-users

# Deactivate user
opendlp deactivate-user --username john_doe
```

### System Administration

```bash
# Generate invite
opendlp generate-invite --role organiser --expires-in 168h

# Database migration
opendlp db upgrade

# System health check
opendlp health-check
```

## Testing Strategy

### Unit Tests

- Domain model logic
- Business rule validation
- Status transitions
- Calculation methods
- No external dependencies

### Integration Tests

- Database operations
- Service layer functionality
- Repository patterns
- Task queue integration
- OAuth providers

### End-to-End Tests

- Complete user workflows
- CSV import process
- Selection and replacement flows
- Authentication and authorization
- Background task execution

## Future Enhancements

### Planned Features

- Registrants will move from Google spreadsheet to the database
- Import and export registrants to/from CSV and Google spreadsheet
- Selection and Replacement will be done in the database
- Selection results saved in database
- In-system registration forms
- Advanced user roles and permissions
- Geographic-based access controls
- Read-only client roles
- Statistics-only access roles
- Multiple OAuth providers
- Advanced selection algorithms
- Comprehensive confirmation workflow
- Data export capabilities
- Assembly templates
- Notification system
- Audit reporting

### Technical Improvements

- API endpoints for external integration
- Advanced CSV validation and preview
- Real-time selection progress
- Enhanced error reporting
- Performance optimization
- Caching strategies
- Monitoring and alerting

### Data Deletion

- Support for "right to be forgotten" requests
- Preserve registrant ID and drop-out status
- Delete all personal information:
  - Names, addresses, demographic answers
  - Maintain referential integrity
  - Audit trail of deletions

## Data Privacy & Compliance

### Data Protection

- Minimal data collection
- Secure data storage
- Access logging and monitoring
- Regular security audits
- Compliance with relevant data protection regulations

## Configuration

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Flask secret key
- `OAUTH_GOOGLE_CLIENT_ID`: Google OAuth client ID
- `OAUTH_GOOGLE_CLIENT_SECRET`: Google OAuth client secret
- `TASK_TIMEOUT_HOURS`: Background task timeout (default: 24 hours)
- `INVITE_EXPIRY_HOURS`: Invite expiration (default: 168 hours)
- `REDIS_xyz`: as required
- others as required

### Application Settings

- Selection algorithm timeout
- Invite expiration periods
- Background task configuration
- Logging levels and destinations

This specification provides a comprehensive foundation for implementing OpenDLP v1.0, with clear paths for future enhancements and scalability.
