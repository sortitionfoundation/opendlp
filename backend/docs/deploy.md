# Deployment Guide

## Subpath Deployment

OpenDLP can be deployed under a subpath (e.g., `example.com/opendlp/`) rather than at the domain root.

### Configuration

Set the `APPLICATION_ROOT` configuration variable:

```python
# In your .env file
APPLICATION_ROOT=/opendlp

# Or in environment variables
export APPLICATION_ROOT=/opendlp
```

### Reverse Proxy Configuration

#### Nginx

```nginx
location /opendlp/ {
    proxy_pass http://localhost:5000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Important: Strip the subpath prefix when forwarding
    proxy_set_header X-Script-Name /opendlp;
}
```

#### Apache

```apache
ProxyPreserveHost On
ProxyPass /opendlp/ http://localhost:5000/
ProxyPassReverse /opendlp/ http://localhost:5000/

# Set script name for Flask
ProxyPassReverse /opendlp/ http://localhost:5000/
Header always set X-Script-Name "/opendlp"
```

#### Traefik

```yaml
http:
  routers:
    opendlp:
      rule: "Host(`example.com`) && PathPrefix(`/opendlp`)"
      middlewares:
        - opendlp-stripprefix
      service: opendlp

  middlewares:
    opendlp-stripprefix:
      stripPrefix:
        prefixes:
          - "/opendlp"

  services:
    opendlp:
      loadBalancer:
        servers:
          - url: "http://localhost:5000"
```

### WSGI Configuration

For production WSGI deployment, wrap the Flask app:

```python
# wsgi.py
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from opendlp.entrypoints.flask_app import create_app

application = DispatcherMiddleware(
    None,  # Default app (404 for root)
    {'/opendlp': create_app()}
)
```

Or use `APPLICATION_ROOT` in the Flask app configuration.

### Docker Deployment

When using Docker with subpath deployment:

```dockerfile
# Set environment variable in Dockerfile or docker-compose.yml
ENV APPLICATION_ROOT=/opendlp
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  opendlp:
    build: .
    environment:
      - APPLICATION_ROOT=/opendlp
    labels:
      - "traefik.http.routers.opendlp.rule=Host(`example.com`) && PathPrefix(`/opendlp`)"
      - "traefik.http.middlewares.opendlp-strip.stripprefix.prefixes=/opendlp"
      - "traefik.http.routers.opendlp.middlewares=opendlp-strip"
```

## Required Code Changes

The following changes are needed to support subpath deployment:

### 1. Flask Configuration (config.py)

```python
# Add to FlaskConfig class
def __init__(self) -> None:
    # ... existing config ...
    self.APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/")
```

### 2. URL Generation

All templates and redirects already use `url_for()` which will automatically respect `APPLICATION_ROOT` - no changes needed.

### 3. Static Files

Static file URLs are handled by Flask's `url_for('static', filename='...')` which respects `APPLICATION_ROOT` - no changes needed.

### 4. CSRF and Session Cookies

Flask-WTF and Flask-Session will automatically use the correct cookie path based on `APPLICATION_ROOT` - no changes needed.

## Testing Subpath Deployment

Test subpath deployment locally:

```bash
# Set APPLICATION_ROOT
export APPLICATION_ROOT=/opendlp

# Run Flask development server
uv run flask run

# Test URLs
curl http://localhost:5000/opendlp/
curl http://localhost:5000/opendlp/auth/login
```

## Security Considerations

- Ensure reverse proxy strips the subpath prefix correctly
- Verify that redirects and form actions use absolute URLs
- Check that static files are served with correct paths
- Confirm session cookies have the appropriate path restriction

## Database Migrations

OpenDLP uses Alembic for database schema migrations. The migration configuration is in `alembic.ini` and migration scripts are stored in the `migrations/versions/` directory.

### Running Migrations

Before deploying a new version of the application, run any pending database migrations:

```bash
# Run all pending migrations
uv run alembic upgrade head

# Check current migration status
uv run alembic current

# Show migration history
uv run alembic history
```

### Production Deployment Process

For production deployments, follow this sequence:

1. **Backup the database** (always backup before migrations)
2. **Stop the application** (to prevent concurrent access during migration)
3. **Run migrations**: `uv run alembic upgrade head`
4. **Start the new application version**

```bash
# Example deployment script
#!/bin/bash
set -e

# Backup database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Stop application
docker-compose down opendlp

# Run migrations
uv run alembic upgrade head

# Start new application version
docker-compose up -d opendlp
```

### Migration Rollback

To rollback to a previous migration (use with caution in production):

```bash
# Rollback to specific revision
uv run alembic downgrade <revision_id>

# Rollback one migration
uv run alembic downgrade -1
```

### Creating New Migrations

During development, generate new migrations after model changes:

```bash
# Generate migration from model changes
uv run alembic revision --autogenerate -m "description of changes"

# Create empty migration for manual changes
uv run alembic revision -m "manual migration description"
```

### Docker Deployments

For Docker deployments, run migrations as part of your deployment process:

```yaml
# docker-compose.yml - run migrations before starting app
version: '3.8'
services:
  opendlp:
    build: .
    depends_on:
      - postgres
    command: >
      sh -c "uv run alembic upgrade head &&
             uv run flask run --host=0.0.0.0"
```

Or use an init container:

```yaml
services:
  migrate:
    build: .
    depends_on:
      - postgres
    command: uv run alembic upgrade head
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/opendlp

  opendlp:
    build: .
    depends_on:
      - migrate
    command: uv run flask run --host=0.0.0.0
```

## Further Reading

- [Flask Documentation: Application Dispatching](https://flask.palletsprojects.com/en/3.0.x/patterns/appdispatch/)
- [Werkzeug Middleware](https://werkzeug.palletsprojects.com/en/3.0.x/middleware/)
- [Deploying to a subpath](https://flask.palletsprojects.com/en/3.0.x/config/#APPLICATION_ROOT)
- [Alembic Documentation](https://alembic.sqlalchemy.org/en/latest/)
