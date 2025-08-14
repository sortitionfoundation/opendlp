# 4. User fields

Date: 2025-08-14

## Status

Accepted

## Context

We need to decide some details about the User.

- is there a username field, or do we just use the email address as the username?
- How about "name". We could have: first/last name? Full name? Optional preferred name?
  - If we have first/last name then full name is the two together.
  - If both first and last name are blank, then full name can be the email address up to `@`
  - Preferred name could default to first name.

## Decision

How about, for now to make things as simple as possible:

- use email as username
- first name & last name sounds like enough detail to get going
- we aren't writing messages yet so this excellent thinking on what we use there can wait?

## Consequences

Nothing much.
