# Command Line Interface (CLI)

OpenDLP provides a comprehensive CLI for system administration tasks including user management, invite management, database operations, and Celery task monitoring.

## Installation and Access

The CLI is available as the `opendlp` command after installing the package:

```bash
# Using uv (recommended)
uv run opendlp [COMMAND]

# Or if installed globally
opendlp [COMMAND]
```

## Getting Help

Use `--help` at any level to see available commands and options:

```bash
opendlp --help                    # Show all command groups
opendlp users --help              # Show user commands
opendlp users add --help          # Show detailed options for a specific command
```

## Command Groups

### Users

Manage user accounts in the system.

```bash
# Add a new user
opendlp users add --email user@example.com --password securepass123

# List all users
opendlp users list

# Deactivate a user
opendlp users deactivate user@example.com --confirm

# Reset a user's password
opendlp users reset-password user@example.com --password newpass456
```

**Available commands:**
- `add` - Create a new user with email and password
- `list` - Display all users with their roles and status
- `deactivate` - Disable a user account (requires confirmation)
- `reset-password` - Change a user's password

Use `opendlp users [COMMAND] --help` for detailed options.

### Invites

Manage invite codes for user registration.

```bash
# Generate invite codes
opendlp invites generate --role user --inviter-email admin@example.com --count 5

# List all invite codes
opendlp invites list

# Revoke an invite code
opendlp invites revoke ABC123XYZ --admin-email admin@example.com --confirm

# Clean up expired invites
opendlp invites cleanup --confirm
```

**Available commands:**
- `generate` - Create new invite codes with specified role
- `list` - Show all invite codes with status and expiration
- `revoke` - Invalidate an invite code (admin only)
- `cleanup` - Remove expired invites from database

Use `opendlp invites [COMMAND] --help` for detailed options.

### Database

Manage database schema and test data.

```bash
# Seed database with test data
opendlp database seed --confirm

# Reset database (DANGEROUS - deletes all data)
export ALLOW_RESET_DB=DANGEROUS
opendlp database reset
```

**Available commands:**
- `seed` - Populate database with sample users, invites, and assemblies for development
- `reset` - Drop all tables and recreate schema (requires `ALLOW_RESET_DB=DANGEROUS` environment variable)

**Warning:** The `reset` command permanently deletes all data. It requires explicit confirmation and the `ALLOW_RESET_DB` environment variable set to `DANGEROUS`.

Use `opendlp database [COMMAND] --help` for detailed options.

### Celery

Monitor and manage background task workers.

```bash
# List currently running tasks (always exits 0)
opendlp celery list-tasks

# Check if tasks are running (exits 1 if tasks found)
opendlp celery check-tasks

# Wait for tasks to complete with timeout
opendlp celery wait-tasks --timeout 300
```

**Available commands:**
- `list-tasks` - Show active tasks without blocking (always exits 0, useful for monitoring)
- `check-tasks` - Check for running tasks and fail if any found (useful for deployment gates)
- `wait-tasks` - Wait for all tasks to complete with optional timeout (default: 300s)

**Exit codes:**

For `list-tasks`:
- `0` - Always (regardless of whether tasks are running)
- `2` - Error (connection failure)

For `check-tasks`:
- `0` - No tasks running (safe to proceed)
- `1` - Tasks are running (deployment blocked)
- `2` - Error (no workers or connection failure)

For `wait-tasks`:
- `0` - All tasks completed within timeout
- `1` - Timeout reached with tasks still running
- `2` - Error (no workers or connection failure)

**Deployment script example:**

```bash
#!/bin/bash
# Quick check - fail immediately if tasks running
if ! opendlp celery check-tasks; then
    echo "Tasks are running, waiting up to 5 minutes..."
    if ! opendlp celery wait-tasks --timeout 300; then
        echo "Deployment aborted: tasks still running after timeout"
        exit 1
    fi
fi
# Proceed with deployment...
```

Use `opendlp celery [COMMAND] --help` for detailed options.

## Common Usage Patterns

### Initial Setup

```bash
# Seed the database with test data
opendlp database seed --confirm

# List created users
opendlp users list

# Generate additional invite codes
opendlp invites generate --role user --inviter-email admin@opendlp.example --count 10
```

### User Management

```bash
# Create admin user
opendlp users add --email admin@company.com --password temp123 --role admin

# Reset forgotten password
opendlp users reset-password user@company.com

# Deactivate compromised account
opendlp users deactivate spam@badactor.com --confirm
```

### Deployment Checks

```bash
# Check and wait for background tasks before deploying
opendlp celery check-tasks || opendlp celery wait-tasks --timeout 600 || exit 1

# Or simply wait with timeout
opendlp celery wait-tasks --timeout 600 || exit 1

# Reset development database
export ALLOW_RESET_DB=DANGEROUS
opendlp database reset
opendlp database seed --confirm
```

## Configuration

The CLI uses the same configuration as the web application, loading settings from:

1. Environment variables
2. `.env` file (if present)
3. Default values

Key environment variables:
- `DATABASE_URL` or `DB_HOST`/`DB_PASSWORD` - Database connection
- `REDIS_HOST` - Redis connection (for Celery commands)
- `ALLOW_RESET_DB=DANGEROUS` - Enable database reset command

See [configuration.md](configuration.md) for complete configuration reference.

## Running in Production

In production environments, you may need to specify the virtual environment:

```bash
# Using uv
uv run opendlp [COMMAND]

# Or activate the virtual environment first
source .venv/bin/activate
opendlp [COMMAND]
```

For Docker deployments, you can run CLI commands inside containers:

```bash
# Execute in running container
docker compose -f compose.production.yaml exec app uv run opendlp [COMMAND]

# Or run one-off command
docker compose -f compose.production.yaml run --rm app uv run opendlp [COMMAND]
```

## Further Reading

- [Background Tasks](background_tasks.md) - Celery worker architecture and monitoring
- [Configuration Guide](configuration.md) - Environment variables and settings
- [Testing Strategy](testing.md) - Running tests including CLI integration tests
