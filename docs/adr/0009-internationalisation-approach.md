# 9. Internationalisation (i18n) approach

Date: 2025-08-28

## Status

Accepted

## Context

We want the site to be readable in many languages, so we need to deal with internationalisation (i18n)
and localisation (l10n).

There are standard approaches to this, including the flask_babel library, which in turn builds on
the pybabel library, which builds on the very mature gettext. These are standard boring technologies.

One important bit of context is that using the `gettext()` and `lazy_gettext()` functions requires
context set up to work at all. This is fine when flask is initialised. But we have domain and
service layer code that we want to exercise without flask. But we still want to have error messages
in that layer of code - so that code needs i18n/l10n but can't **directly** use the functions
from flask_babel.

## Decision

We will use flask_babel (and pybabel and gettext). But we will wrap those functions in some code
that will fallback to just returning the string if the i18n context is not available.

## Consequences

This allows us to continue to exercise domain and service layer code without flask being
involved at all.

It does mean we have to maintain the wrapper code and do good testing to ensure they are
reliable.

## Out of scope

The translation of strings that live in the database - assemblies, RSVP pages etc.
