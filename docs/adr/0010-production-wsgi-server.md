# 10. Production WSGI server

Date: 2025-08-28

## Status

Accepted

## Context

We need a production WSGI server for production - the `flask run` command is fine for
development but does not scale at all well.

Useful context is that we expect light traffic for the site, so we don't need special
features or high performance. Also we have a preference for mature, boring technologies
unless there is a good reason to deviate from that.

## Decision

We will use gunicorn - a mature boring WSGI server that is production quality.
It is python only, so easy to install and deploy.

## Consequences

We just need to configure it reasonably and put it behind a proxy like apache or nginx.
