---
description: Review the code on this branch against the guidelines in the project docs.
---

## Summary of files changed

!`git diff --stat --merge-base main`

## Instructions

I want you to review the changes on this branch, compared to the main branch. General instructions:

- If the diff is big, consider giving each of the "Things to Check" to a subagent.
- Write up your review in the chat - I will read it and then tell you what to act on. Don't make ANY changes yet.
- You will have to wait for permissions a lot if you cd to the git root before running commands - most commands can be run fine from the backend/ directory.

### Things to Check

- Review `docs/agent/code_quality_rules.md` and check how the changes line up with that
- Review `docs/testing.md` and the tests in this branch
- Review `docs/architecture` and what changed under `src/opendlp/`
- Has anything been added to `config.py` (or removed)? Any new feature flags, or have we cleaned up any? If so, are there examples in `env.example` and explanations in `docs/configuration.md`
- If templates have been added/updated, are we using the Jinja components well? Also review `docs/agent/component_accessibility.md`
- Is most JavaScript in files under `static/js/`? Will it work with CSP restrictions - see `docs/frontend_security.md`
- Does the change touch cookies, sessions, logging of personal data, analytics, third-party scripts, or data retention? If so, check it against `docs/personal-data.md` — especially the "What would change the answer" list. Anything on that list needs a decision, not just a review.

### Do NOT report

- Anything CI already enforces: lint, formatting, type errors
- Generated files - `uv.lock` `package-lock.json` `migrations/versions/*.py` `translations/**/*`
- Test-only code that intentionally violates production rules
