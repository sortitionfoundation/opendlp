# Docker Setup

OpenDLP provides several Docker Compose configurations for different use cases.

## Docker Compose Files

### compose.yaml (Full Development Stack)

Complete application stack for development and testing.

**Services:**

- `app` - Flask application
- `postgres` - PostgreSQL database
- `redis` - Redis for sessions and Celery
- `app_celery` - Celery worker for background tasks
- `app_celery_beat` - Celery beat scheduler

**Ports:**

- Application: `5005` → `5000`
- PostgreSQL: `54321` → `5432`
- Redis: `6379` → `6379`

### compose.production.yaml (Production Deployment)

Production-ready configuration with additional services.

**Additional Services:**

- `postfix` - SMTP relay for email sending

**Configuration:**

- Uses Gunicorn WSGI server
- Production environment variables
- Health checks enabled
- Resource limits configured
- Postfix relay for outbound email

See [docs/postfix_configuration.md](postfix_configuration.md) for email configuration.

### compose.localdev.yaml (Services Only)

Services only for local development when running Flask directly.

**Services:**

- `postgres` - PostgreSQL database
- `redis` - Redis for sessions

**Use case:** Run Flask locally with `just run` while using containerized databases.

### compose.test.yaml (Test Services)

Services for running tests with isolated test databases.

**Services:**

- `postgres_test` - PostgreSQL on port `54322`
- `redis` - Redis for test sessions

**Use case:** Run tests with `just test` using containerized test databases.

## Running with Docker

### Development Mode

Start the full development stack:

```bash
# Start in detached mode
just start-docker

# Start with logs visible (blocking)
just start-docker-b

# Restart after code changes (rebuild + start)
just restart-docker

# Restart with logs visible
just restart-docker-b
```

### Services Only (Local Development)

Run only databases while developing with Flask locally:

```bash
# Start PostgreSQL and Redis
just start-services-docker

# Stop services
just stop-services-docker

# Then run Flask locally
just run
```

### Production Deployment

Deploy the full production stack:

```bash
# Start all services
docker compose -f compose.production.yaml up -d

# View logs
docker compose -f compose.production.yaml logs -f

# Stop all services
docker compose -f compose.production.yaml down

# Stop and remove volumes (data loss!)
docker compose -f compose.production.yaml down -v
```

## Production Services Breakdown

### app (Flask Application)

Main web application running with Gunicorn.

**Configuration:**

- Gunicorn with 4 worker processes
- Handles HTTP requests
- Connects to PostgreSQL and Redis
- Port 5005 exposed to host

**Health check:** HTTP GET to `/health`

### app_celery (Background Worker)

Celery worker for processing background tasks.

**Configuration:**

- Processes selection tasks
- Connects to Redis message broker
- Logs to Docker logs

**Monitoring:**

```bash
docker compose -f compose.production.yaml logs app_celery -f
```

### app_celery_beat (Task Scheduler)

Celery beat scheduler for periodic tasks.

**Configuration:**

- Runs cleanup jobs every 5 minutes
- Detects orphaned tasks
- Monitors task health

**Monitoring:**

```bash
docker compose -f compose.production.yaml logs app_celery_beat -f
```

### postgres (Database)

PostgreSQL database server.

**Configuration:**

- Version: 15
- Port: 54321 (host) → 5432 (container)
- Volume: `postgres_data` for persistence
- Health check: `pg_isready`

**Connection:**

```bash
# Connect via Docker
just psql

# Connect directly (password: abc123)
psql -h localhost -p 54321 -U opendlp -d opendlp
```

### redis (Message Broker)

Redis for session storage and Celery message queue.

**Configuration:**

- Port: 6379
- No persistence (sessions are ephemeral)
- Health check: `redis-cli ping`

### postfix (SMTP Relay) - Production Only

Postfix SMTP relay for sending emails.

**Configuration:**

- Relays emails to upstream SMTP service
- Configured via environment variables
- Internal port 25 (not exposed to host)
- Health check: `postfix status`

See [docs/postfix_configuration.md](postfix_configuration.md) for detailed setup.

## Database Access

### PostgreSQL Shell

```bash
# Via just command (development)
just psql

# Via Docker Compose
docker compose exec postgres psql -U opendlp -d opendlp

# Production
docker compose -f compose.production.yaml exec postgres psql -U opendlp -d opendlp
```

### Database Backup

```bash
# Backup database
docker compose exec postgres pg_dump -U opendlp opendlp > backup.sql

# Restore database
docker compose exec -T postgres psql -U opendlp opendlp < backup.sql
```

### Database Migrations

OpenDLP doesn't currently use database migrations (Alembic/Flask-Migrate). The schema is created from SQLAlchemy models on first run.

## Docker Commands Reference

### View Running Containers

```bash
docker compose ps

# Production
docker compose -f compose.production.yaml ps
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs app -f
docker compose logs app_celery -f

# Production
docker compose -f compose.production.yaml logs -f
```

### Execute Commands in Containers

```bash
# Flask shell
docker compose exec app flask shell

# Python shell
docker compose exec app python

# Bash shell
docker compose exec app bash

# Production
docker compose -f compose.production.yaml exec app flask shell
```

### Rebuild Containers

```bash
# Rebuild without cache
docker compose build --no-cache

# Rebuild specific service
docker compose build app

# Production
docker compose -f compose.production.yaml build --no-cache
```

### Clean Up

```bash
# Stop and remove containers
docker compose down

# Stop and remove containers + volumes (data loss!)
docker compose down -v

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune
```

## Environment Variables for Docker

### Development (.env)

Create `.env` in project root:

```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=opendlp
DB_USER=opendlp
DB_PASSWORD=abc123

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Application
SECRET_KEY=dev-secret-key
FLASK_ENV=development
DEBUG=true
```

### Production (.env.prod)

Create `.env.prod` for production (never commit):

```bash
# Database
DATABASE_URL=postgresql://opendlp:secure-password@postgres:5432/opendlp  # pragma: allowlist secret

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Application
SECRET_KEY=your-cryptographically-secure-secret-key
FLASK_ENV=production
DEBUG=false

# Email (see docs/postfix_configuration.md)
EMAIL_ADAPTER=smtp
SMTP_HOST=postfix
SMTP_PORT=25
SMTP_USE_TLS=false
SMTP_FROM_EMAIL=noreply@yourdomain.com

# Postfix relay
RELAYHOST=smtp.sendgrid.net:587
RELAYHOST_USERNAME=apikey
RELAYHOST_PASSWORD=SG.your-api-key-here
ALLOWED_SENDER_DOMAINS=yourdomain.com
```

See [docs/configuration.md](configuration.md) for complete configuration reference.

## Troubleshooting

### Container Won't Start

Check logs for errors:

```bash
docker compose logs app
```

Common issues:

- Missing environment variables
- Database connection failed
- Port already in use

### Database Connection Errors

Verify PostgreSQL is running:

```bash
docker compose ps postgres
docker compose logs postgres
```

Test connection:

```bash
docker compose exec postgres pg_isready
```

### Redis Connection Errors

Verify Redis is running:

```bash
docker compose ps redis
docker compose logs redis
```

Test connection:

```bash
docker compose exec redis redis-cli ping
# Should return: PONG
```

### Celery Tasks Not Running

Check Celery worker is running:

```bash
docker compose ps app_celery
docker compose logs app_celery -f
```

Check Redis connection:

```bash
docker compose exec app_celery python -c "from opendlp.entrypoints.celery.app import get_celery_app; app = get_celery_app(); print(app.broker_connection())"
```

### Port Already in Use

Change port mapping in `compose.yaml`:

```yaml
ports:
  - "5006:5000" # Use 5006 instead of 5005
```

## Resource Limits

### Development (Optional)

Resource limits are commented out in `compose.yaml` for development flexibility.

### Production (Recommended)

Uncomment and adjust resource limits in `compose.production.yaml`:

```yaml
app:
  mem_limit: 1g
  mem_reservation: 512m
  cpus: 2

app_celery:
  mem_limit: 2g
  mem_reservation: 1g
  cpus: 4
```

Adjust based on:

- Server resources
- Expected load
- Task complexity
- Concurrent users

## Further Reading

- Deployment guide: [docs/deploy.md](deploy.md)
- Configuration: [docs/configuration.md](configuration.md)
- Background tasks: [docs/background_tasks.md](background_tasks.md)
- Email setup: [docs/postfix_configuration.md](postfix_configuration.md)
- Docker Compose documentation: <https://docs.docker.com/compose/>
