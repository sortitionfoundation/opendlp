# 5. Code quality toolchain

Date: 2025-08-28

## Status

Partially superceded by [14. switch from pre-commit to prek](0014-switch-from-pre-commit-to-prek.md)

The non-pre-commit parts of this ADR remain accepted.

## Context

We want to keep the code up to standard and to minimise manually reformatting code.

## Decision

We use [pre-commit](https://pre-commit.com/) to manage pre-commit hooks - so nothing can make it into a
git commit if it isn't up to scratch. See `.pre-commit-config.yaml` for the current
list of checks we run. Most are standard, but of note are:

- `ruff` for python linting and formatting. Chosen as it is fast to run and replaces many other tools.
- `detect-secrets` to scan for any passwords, keys or other secrets to avoid them leaking.

We also have `just check` that runs the pre-commit checks without doing a commit, and
adds a few more checks

- check `uv` lock file is consistent with `pyproject.toml`
- `mypy` for python type checking. Industry standard for now, but consider `ty` in the future.
- `deptry` to look for dependencies in `pyproject.toml` that are not required any more.

As well as being run locally, `just check` is also run by GitHub Actions, as a precaution
for anything slipping through.

## Consequences

This does mean that a little work might need to be done before being able to commit.

But it does mean that the code that is committed has standard formatting, should be free
of common bugs and should not leak secrets.

There is a risk that someone will neglect to set up the pre-commit hooks properly, but the
GitHub Actions should catch that by making the job go red. The risk is also mitigated by
`just install` (which makes it easier to get going) setting up pre-commit hooks.
