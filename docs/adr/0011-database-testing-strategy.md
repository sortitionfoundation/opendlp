# 11. Database testing strategy

Date: 2025-08-28

## Status

Accepted

## Context

Databases slow down tests, but tests that don't hit the database doesn't exercise the full code paths.

SQLite in memory is fast, and exercises **most** of the same code, but not quite the same as production.

Postgresql has fields and options that are unique and we want to use - so if some tests hit
SQLite and some Postgresql we will need wrapper code to handle the differences.

## Decision

Unit tests will not use a database. This means tests that exercise the domain and service layer. They
should be very fast.

Integration tests will use SQLite in memory. They should still be fast and will exercise the generic
database layer code - both ours and the core libraries (`sqlalchemy` in particular).

End-to-end (e2e) tests and BDD tests will use Postgresql. This means our highest level, slowest tests
exercise the same code and services as production.

## Consequences

We need to have wrapper code to fake some Postgresql-specific fields (UUID, JSON) when we are
actually using SQLite.
