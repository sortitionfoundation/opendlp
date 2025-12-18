# 14. switch from pre-commit to prek

Date: 2025-12-18

## Status

Accepted

Supercedes the pre-commit part of [5. Code quality toolchain](0005-code-quality-toolchain.md)

## Context

[prek](https://prek.j178.dev/) is a rust implementation of pre-commit. It is faster, uses uv natively and it has rust versions of common hooks.

## Decision

We switch from pre-commit to prek

## Consequences

It should be fully compatible. The configuration file `.pre-commit-config.yaml` has not changed, so switching back will be cheap if we discover any issues.
