# 7. Docker usage

Date: 2025-08-28

## Status

Accepted

## Context

Docker is a way to produce containers independent of the wider system they can run in.
Docker compose provides a way to launch a set of related docker containers and link
them together.

Docker can be used:

- for development, testing and production,
- for the main service,
- for supporting services.

We can have a single `Dockerfile` used by multiple `compose.xyz.yaml` files.

### Main service

By using a docker container, installing and building all we need in the build image
and then copying just what is needed for running into the main image, we can get
a small image that contains what we need for the service but no more. Environment
variables can be added via `.env` files, so that secrets and installation specific
settings can be provided to the common shared image.

### Support services

OpenDLP relies on the Postgresql database (for storing data) and Redis (for storing sessions
and other short lived data that does not need backing up).

We want to keep any production data separate from any usage for local development and testing.

For those tests that use Postgresql, we want to always be able to start with a clean database,
but for local development we want data to persist over days and weeks for testing.

## Decision

We have a single Dockerfile with a 2 step build.

We have several docker compose files:

- `compose.yaml`
  - Has the main service, Postgresql and Redis.
  - Postgresql has a persistent named volume for the database data.
- `compose.production.yaml`
  - Has the main service, Postgresql and Redis.
  - Postgresql has a persistent named volume for the database data, separate to other compose files.
  - Adds in `.env.prod` as an **additional** `.env` file, allowing a standard `.env` file
    to be deployed alongside a production-specific `.env.prod` file, which will
    override the standard one.
  - Has a separate network to all other compose files.
- `compose.localdev.yaml`
  - Has Postgresql and Redis. It does **not** have the main service.
  - Postgresql has a persistent named volume for the database data, separate to other compose files.
  - Has a separate network to all other compose files.
  - Intended for use so we can run flask locally, but it has the services it needs on expected ports.
- `compose.test.yaml`
  - Has Postgresql and Redis. It does **not** have the main service.
  - Postgresql has a persistent named volume for the database data, separate to other compose files.
  - Has a separate network to all other compose files.
  - Intended for use so we can run tests locally, but it has the services it needs on expected ports.
    The tests will not affect data used for local development, and vice versa.

## Consequences

What becomes easier or more difficult to do and any risks introduced by the change that will need to be mitigated.

- Could be resource intensive to run multiple copies of Postgresql and Redis - though Hamish is doing fine so far.
- Keeps all environments separate to each other.
- Tests can be run without affecting local dev data. And we don't need to hack the Postgresql container
  to support multiple databases (say `opendlp` and `opendlp_test`).

## To resolve later

- Do we actually need the plain `compose.yaml` file?
- Should the docker images be published anywhere?
