# 8. Static file serving

Date: 2025-08-28

## Status

Accepted

## Context

The issue motivating this decision, and any context that influences or constrains the decision.

The application needs to serve static files - primarily CSS, JS and images. The main options are:

### Default web server process

Have the default web server process handle the files. This tends to be inefficient.

### Web server with whitenoise

[whitenoise](https://whitenoise.readthedocs.io/en/latest/) is a python library to efficiently
serve static files for WSGI apps - like flask. It finds all the static files on start up
and uses operating system calls to serve the files without the file content being read by
python. It sets HTTP headers to work nicely with CDNs. See more about [this in the docs](https://whitenoise.readthedocs.io/en/latest/#infrequently-asked-questions).

### External web server

You can use another web server - apache, nginx etc - to serve the static files and only
send requests that need python to the WSGI server. But that means there is an extra server
to run and configure.

## Decision

We are using whitenoise - installing and configuring is simple and done in the main codebase.
No per-installation config is required.

## Consequences

This is only likely to be revisited if we have very high traffic, but that seems unlikely.
