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
- If templates compose macros with `{% call %}` blocks: `{{ caller() }}` must never appear inside a nested `{% call %}` block — Jinja shadows `caller` there and it fails only at render time ("No caller defined"). Capture first with `{% set content = caller() %}`. See "Jinja Macro Composition: `caller` Scope" in `docs/agent/frontend_design_system.md`.
- If templates reference CSS custom properties (`var(--color-...)` etc.), each one must be defined in `static/backoffice/tokens/primitive.css` or `semantic.css` — an undefined token has no error, it silently inherits the parent colour (invisible links, uncoloured status banners). Prefer semantic tokens over primitives, and add an alias to `semantic.css` rather than inventing a new name in a template. See "Backoffice design tokens" in `docs/agent/frontend_design_system.md`. `tests/unit/test_design_tokens.py` enforces this; flag any change that weakens or deletes that test.
- Is any hand-written JavaScript being added under `static/` instead of `src/js/`? The rule is absolute: `static/` holds esbuild output and `vendor/` only. A hand-edited file there is overwritten by the next build, and a `.test.js` there would be publicly served. See `docs/frontend_build.md`
- Is most JavaScript in files under `src/js/` rather than inline in a template? Will it work with CSP restrictions - see `docs/frontend_security.md`
- If JS changed under `src/js/`: is the logic in an `Alpine.data()` component rather than inline in a template? Does anything non-trivial (debounce, state transitions, URL building, parsing) have a Vitest test colocated next to it? See `docs/agent/frontend_js_testing.md`. Note that a green ESLint run says nothing about CSP-Alpine attribute compliance - that is still a manual check against `templates/backoffice/patterns.html`
- Was a new esbuild entry point added to `ENTRY_POINTS` in `esbuild.config.mjs`? A new `src/js/` file that no entry point imports is never built and never served
- Is server-side data reaching a bundled component through an `x-data` attribute when it holds user-written text, or more than a couple of short values? It should be a `<script type="application/json">` data block read with `readJsonScript()`, so `|tojson` does the escaping once - see "Passing server data to a bundle" in `docs/frontend_build.md`. A quote or a `</script>` in something a user typed breaks the page otherwise
- Is a user-facing string being written in a `.js` file? It can never be translated: `babel.cfg` extracts from `**.py` and `templates/**.html` only. Pass it in from the template
- Did a JSON-returning route change shape? Then the JSON Schema under `src/opendlp/schemas/json_api/` and the recorded fixture under `tests/fixtures/json_api/` both have to change with it - see `docs/agent/json_api_conventions.md`. A hand-typed literal of an API response in a `.test.js` file is a defect in itself; it should load a fixture via `src/js/test-support/api-fixtures.js`
- Does any JSON response body contain `str(e)`? It must carry a literal `_("...")` or `exc.user_msg()` - see `docs/agent/json_api_conventions.md`. This one is worth grepping for: the safe and unsafe versions are character-for-character identical at the call site. `error=str(e)` inside a `logger.*` call is fine and wanted
- Does a new exception class whose message is meant for a user mix in `CuratedMessage`? Without it `user_msg()` silently returns the generic message
- Is an `except Exception` around a service call as narrow as it could be? A blanket catch turns a bug into a plausible-looking error message. Where one is genuinely needed (usually the outermost route handler), does it log via `structlog` and return a generic message?
- Is any new or changed `<script>` tag pointing at a CDN instead of a vendored copy under `static/js/vendor/`?
- Did a new npm build script get added without being wired into **both** the `build` script in `package.json` and `just build-all`? Missing either means the asset is silently absent in half the environments - see `docs/frontend_build.md`
- Does the change touch cookies, sessions, logging of personal data, analytics, third-party scripts, or data retention? If so, check it against `docs/personal-data.md` — especially the "What would change the answer" list. Anything on that list needs a decision, not just a review.

### Do NOT report

- Anything CI already enforces: lint, formatting, type errors
- Generated files - `uv.lock` `package-lock.json` `migrations/versions/*.py` `translations/**/*`
- Test-only code that intentionally violates production rules
