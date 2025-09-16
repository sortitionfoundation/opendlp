# 12. Background task runner

Date: 2025-09-16

## Status

Accepted

## Context

We need to be able to run the selection as a background task. It can take a while to run - too long to run within a web request.

We also want to see progress updates while it is running - so we need to get updates from the task to the web browser while it is running. And we definitely need to get the final result back to the web browser.

The two major options in the python world are celery and redis-queue. redis-queue is a little simpler but also less capable.

Celery has an `AsyncResult` object that allows data to be sent back from the task to the supervisor. redis-queue does not have such an option. Runner-independent options include sending messages via Redis, or just writing directly to the database from the task runner.

## Decision

We will use celery as the task runner.

## Consequences

There is slightly more set up to do - but adding the task runner to the entrypoints module should not be hard. We need a little extra config and some docker/compose support to have the task runner available.

And once we have it, we can trigger tasks from within the web request cycle. And we can get updates on the task from either the AsyncResult or from the database, as appropriate.
