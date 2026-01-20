# OpenDLP Backend

OpenDLP (Open Democratic Lottery Platform) is a Flask web application for supporting Citizens' Assemblies through stratified selection processes. The project follows Domain-Driven Design principles from "Architecture Patterns with Python" with clear separation between domain models, adapters, service layer, and entrypoints.

**Technology Stack:** Flask, SQLAlchemy, PostgreSQL, Redis, following DDD architecture

See the [docs](docs/) folder for many more details.

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

## Getting going

Note that there are more detailed notes in [AGENTS.md](/backend/AGENTS.md) you might want to review.

### Dev tools assumed

The following should all be installed on the machine used for development.

- docker
- [just]() for running commands - read the [justfile](justfile) to see what the various commands do
- npm
- [prek](https://prek.j178.dev/) for pre-commit hook management
- [uv](https://docs.astral.sh/uv/) for python and dependency management

### Setting up the dev environment

In this directory:

```sh
# create the .env file
cp env.example .env
# then edit and review as required.

just install
```

The command `just install` will set up the virtualenv, pre-commit hooks, set up node and a few other things.

### Testing and Quality

```bash
# Start the docker containers relied on for tests
just start-test-docker

# Run all tests with coverage
just test

# Run all tests (without bdd tests)
just test-nobdd

# Run all quality checks (linting, type checking, dependency analysis)
just check
```

### Running the Application

```bash
# Start the docker containers relied on for local services
just start-local-docker

# Local development with Flask
just run

# Flask shell
just flask-shell
```

### Database Access

```bash
# Connect to PostgreSQL (password: abc123)
just psql
```
