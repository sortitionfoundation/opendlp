# Frontend interactivity: implementation plan

**Status:** Phases 1a, 1b and 1c are implemented (§2, §5, §3, §6, §7). Phase 2 onwards is not started; three questions are still with the team.
**Decision this implements:** [vanilla-alpine-json.md](vanilla-alpine-json.md) — vanilla JS + Alpine.js (CSP build) + JSON routes, organised into real files, tested, for internal/backoffice interactivity. Public pages stay server-rendered, no-JS-required.

This document lays out a concrete plan for the workstreams Chewie asked for. Chewie's review answers most of the questions; §11 records what was decided and what is still parked pending a team discussion.

**Done:** Phase 1a (vendoring, §2), Phase 1b (JS tooling, §5), Phase 1c (JSON error handling, §3), plus the doc and review-skill updates those imply (§6, §7). Each section carries a note on what was actually built and where it diverged.

**Not started:** Phase 2 onwards — the API-fixture machinery (§4) and the inline-script migrations (§9).

**Blocked on team discussion (do not start these):** the dev-blueprint question (§8), Vitest test-file placement (§5 — implemented as `tests/js/`, reversible), and whether anything in `service_docs.html`/`dev.py` is load-bearing (§10 Phase 5).

---

## 0. Findings from reviewing the current code

Grounding facts the plan below relies on:

- **The CDN scripts are exactly four `<script>` tags**, all with a nonce already:
  - `templates/base.html:212` — `@alpinejs/csp@3.15.8` from jsdelivr
  - `templates/base.html:216` — `htmx.org@2.0.7` from jsdelivr
  - `templates/base.html:203` and `templates/base_public.html:53` — `govuk-frontend@5.11.1/dist/govuk/all.bundle.min.js` from jsdelivr
  - `templates/backoffice/base.html:33` and `:38` — the same Alpine/htmx CDN tags again
- **`govuk-frontend` is already an npm dependency** (`package.json` pins `^5.14.0`) and its built bundle already exists locally at `node_modules/govuk-frontend/dist/govuk/all.bundle.js` — it is not currently used; we still fetch an _older_ version (5.11.1) from the CDN instead. Vendoring this one is a copy step, not a new dependency.
- **`@alpinejs/csp` and `htmx.org` are not npm dependencies at all** — they're pulled from jsdelivr with no local copy. Vendoring these means adding two small npm packages.
- **The three inline `<script nonce>` blocks** the decision doc flags, measured directly:
  - `templates/backoffice/assembly_registration.html:1381-1948` — **567 lines** (file is 1950 lines total, not 1078 — it's grown since the doc was written)
  - `templates/backoffice/service_docs.html:106-828` — **722 lines** (dev-only tool)
  - `templates/backoffice/patterns.html:112-396` — **284 lines** — notable because this page is the _living reference_ for "how to do Alpine right" (`docs/frontend_security.md`, CLAUDE.md both point here), yet it is itself 100% inline, untested script.
- **JSON error handling is already mostly disciplined** in the production blueprints. The pattern in `backoffice_registration.py` and `backoffice.py` is consistently: log the real exception via `structlog` (`logger.exception(..., error=str(e))`), return a translated _generic_ message to the client. The two places a caught exception's `str(e)` reaches the client directly (`backoffice_registration.py:811`, `:908`) are custom domain exceptions (`ImageQuotaExceeded`, `DocumentQuotaExceeded`) whose `__str__` _is_ the curated user-facing message — that's a deliberate, safe use of `str(e)`, not a leak.
- **`dev.py` breaks that discipline in five places.** `_handle_publish_registration_page`, `_handle_unpublish_registration_page`, `_handle_close_registration_page`, `_handle_reopen_registration_page`, and `_handle_submit_registration` each end with a bare `except Exception as e: return {"error": str(e), "error_type": type(e).__name__}` — the raw exception string goes straight into the JSON response, no logging, no translation, no generic-message fallback. `dev_bp` is only registered when `not config.is_production()` (`flask_app.py:137-140`) and is admin-gated, so this isn't an internet-facing leak today — but it's the opposite of the convention we're about to write down, and it sits in the file most likely to get copied as a pattern.
- **These same five handlers have zero test coverage** — `grep` for their names across `tests/` returns nothing, and the route that calls them (`/dev/service-docs/execute`) isn't tested directly either. By contrast, the image/document/email handlers _do_ have component tests (`tests/component/test_dev_image_handlers.py`, `test_dev_document_handlers.py`, `test_dev_email_handlers.py`) that drive the `_handle_*` functions over a `FakeUnitOfWork`. So the dev blueprint already has a working test pattern for about half its handlers — it just wasn't applied uniformly.
- **No JS test runner, no eslint, config exists** — confirmed no `vitest.config.*`, no `.eslintrc*`/`eslint.config.*`, no `*.test.js` anywhere outside `node_modules`.
- **`jsonschema` is not currently a Python dependency** — it appears nowhere in `pyproject.toml` or `uv.lock`. So the Python half of §4 needs `uv add --group dev jsonschema` too; it's not "already available" as §1 originally guessed.
- **The frontend build has exactly one entry point that everything reuses: the `build` npm script.** `package.json`'s `"build": "npm run build:sass && npm run build:backoffice && npm run build:js"` is called by `just install`, by CI (`.github/actions/setup-python-env/action.yml`, which runs `npm install && npm run build`), and by `Dockerfile:85`. Separately, `just build-all` = `build-all-css` (= `build-css` + `build-backoffice`) + `build-js`, and `just test`/`just test-bdd`/`just run` all depend on `build-all`. So a new build step must be added in **both** places to be picked up everywhere: appended to the `build` npm script, and given a `just build-vendor` recipe wired into `build-all`. See §2.
- **`just check` is mostly a prek wrapper** — `uv lock --locked`, then `uv tool run prek run --all-files`, then `mypy`, then `deptry`. `check-ci` is the same but points prek at `../.pre-commit-config-ci.yaml`. The pre-commit configs live at the repo root (one level above `backend/`), so hook `files:` patterns are repo-root-relative (`^backend/templates/...`), and there is already a `- repo: local` hook (`no-strftime-in-templates`) to copy the shape from. Both configs carry a literal `# TODO: consider ... - javascript` comment, so JS linting in prek is a pre-existing intention, not a new idea.
- **"Contract test" is already a taken term in this codebase** (`docs/testing.md` §Contract Tests / `tests/contract/`): it specifically means "fake repo vs SQL repo behave identically." Whatever we build to stop JSON/JS drift must not be called "contract tests" or it'll collide with that meaning in conversation and in `just check` output. See §4.

---

## 1. New dependencies — approved

Chewie has signed off on all of these. Recorded here with the reasoning so the choice is auditable later.

| Dependency                                 | Why                                                                                                                                                                                                                                    | Alternative considered                                                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Vitest** (jsdom env)                     | JS unit tests — the load-bearing new piece per the decision doc. Covers `url-utils.js`, autocomplete debounce/keyboard logic, modal state, and whatever we extract from the inline scripts.                                            | Jest (heavier, same job); `node:test` (no dep, but no jsdom story, worse ergonomics for DOM-touching Alpine components) |
| **eslint + prettier**                      | Lint/format JS once it's out of templates and into files. Runs as prek hooks, not as a bespoke `just check` step — see below.                                                                                                          | Biome (single faster binary, newer/less mature ecosystem)                                                               |
| **`@alpinejs/csp`, `htmx.org`** (npm)      | Needed to vendor them locally instead of jsdelivr (see §2). Same libraries we already run, just as npm packages instead of CDN tags.                                                                                                   | Keep on CDN and accept the supply-chain/privacy surface (all three architecture docs argue against this)                |
| **`ajv`** (JSON Schema validator, JS side) | The JS half of the drift-prevention plan (§4), now confirmed. Validates the imported fixture against the same schema the Python side asserts against.                                                                                  | Skip schema validation, rely on golden fixtures alone (weaker guarantee, no dependency)                                 |
| **`jsonschema`** (Python, dev group)       | The Python half of §4. **Not currently a dependency** (§0) — my earlier "probably already available" was wrong, so this is a fifth new dependency, not a freebie. Chewie has explicitly approved it as a new dependency on that basis. | Hand-rolled shape assertions in pytest (more code, weaker, drifts from the JS side)                                     |

### eslint/prettier run via prek, not as a bespoke `just check` step

Per Chewie: don't bolt these onto `just check` directly — `just check`'s main job is already "run the prek hooks", so JS linting belongs _inside_ the prek config where it gets the same file-scoping, caching, and commit-time enforcement as ruff and djhtml. Both `../.pre-commit-config.yaml` and `../.pre-commit-config-ci.yaml` even carry a standing `# TODO: consider ... - javascript` note in the same place, so this fills an existing gap.

Practically that means:

- Add eslint and prettier hooks to `../.pre-commit-config.yaml`, scoped with `files: ^backend/static/.*\.js$` (repo-root-relative, matching the existing `no-strftime-in-templates` hook), excluding `static/**/dist/` and the new `static/js/vendor/` (§2) — vendored and generated files must not be linted or reformatted.
- **Mirror the change into `../.pre-commit-config-ci.yaml`.** That file is a hand-maintained copy that only omits `detect-secrets`. Chewie is happy for it to stay hand-maintained — it changes infrequently, so the duplication isn't worth automating away. It just means every hook added in Phase 1 (eslint, prettier, and the `djjs` scoping) has to be applied to **both** files in the same commit, and reviewers should check for that.
- Hook mechanics to settle during Phase 1: prefer `- repo: local` hooks with `language: system` invoking the npm scripts (`npm run lint` / `npm run format:check` with `--prefix backend`), since `node_modules/` is already guaranteed by `just install`, `npm install` in CI, and the Dockerfile. The alternative — prek's `language: node` with `additional_dependencies`, or the upstream eslint mirror repo — would install a _second_ copy of eslint at a version independent of `package.json`, which is exactly the drift we're trying to avoid elsewhere. **To verify in Phase 1:** that prek 0.4.x runs `language: system` local hooks with a `working-directory`-equivalent cleanly from the repo root; the fallback if not is a tiny wrapper script in the repo root.

### The `djjs` / prettier split — decided

prettier and the existing `djjs` hook (djHTML's JS indenter) both reformat `.js` files, and `djjs` currently has no `files:`/`exclude:` restriction, so it formats every tracked `.js` file in the repo. **Chewie's call: scope `djjs` to the `templates/` directory — djHTML handles inline JS, prettier owns standalone `.js` files.** That's the right division of labour. Two details to get right when implementing it:

- **Scoping `djjs` to `^backend/templates/` makes it a no-op, and that's fine.** There are currently zero `.js` files anywhere under `templates/` — inline `<script>` blocks live inside `.html` files, and those are already indented by the **`djhtml`** hook, which formats the contents of `<script>`/`<style>` tags itself. So `djjs` isn't what's been maintaining inline JS; `djhtml` is, and that's unaffected by any of this. The scoped `djjs` hook survives as a declaration of intent (and would start working if a standalone `.js` ever lands under `templates/`). Worth a one-line comment in the config saying so, or the next person will delete it as dead config. If the team would rather not carry a hook that matches nothing, dropping `djjs` entirely is behaviourally identical today — flagging the option, not arguing for it.
- **Don't scope prettier to `static/` only.** Once `djjs` stops covering the repo, `backend/tailwind.config.js` — the one tracked `.js` file outside `static/` — would be formatted by nothing at all. Scope prettier as `files: ^backend/.*\.js$` with `exclude:` for `static/**/dist/`, `static/js/vendor/` (§2) and `node_modules/`, so nothing silently falls through the gap. Keep prettier to `.js` for now: `djcss` has the same shape of overlap for stylesheets, and widening prettier to CSS opens a second front this plan doesn't need.

---

## 2. Vendor Alpine, htmx, and govuk-frontend off jsdelivr — ✅ DONE (Phase 1a)

Approved. All three architecture docs agree on this independent of which approach won, and Chewie has confirmed the govuk-frontend version bump that falls out of it (see §11).

**Implemented.** Deviations from the plan below, all minor:

- `govuk-frontend` ships no minified bundle in the npm package — only `dist/govuk/all.bundle.js`. That is what we copy, so the vendored govuk-frontend is unminified where the CDN copy was minified (104 KB vs the CDN's smaller `.min.js`). Alpine and htmx both ship minified builds and we use those.
- The old CDN tags carried `integrity=`/`crossorigin=` attributes; the vendored tags drop them, since SRI pins a third party we no longer have.
- The jsdelivr entries in the CSP `script_src`/`style_src`/`font_src` allowlists (`flask_app.py:219-222`) were **left alone**, as §2.5 said they could be — they are inert under `strict-dynamic` and `style_src`/`font_src` were not in scope here.
- Added `TestVendoredScripts` to `tests/unit/test_csp_nonce.py`: no CDN URL appears in a rendered page, the Alpine/htmx tags point at `static/js/vendor/`, and each vendored file is served. This is the regression net for the `sf-code-review` check in §7.
- `docs/agent/frontend_design_system.md` also carried a stale CDN `<script>` example and was updated alongside the two docs §2.6 lists.

**Plan:**

1. `npm add @alpinejs/csp htmx.org` (pinned to the versions already in use: `3.15.8`, `2.0.7`).
2. Add a `build:vendor` npm script that places:
   - `node_modules/@alpinejs/csp/dist/cdn.min.js` → `static/js/vendor/alpine-csp.js`
   - `node_modules/htmx.org/dist/htmx.min.js` → `static/js/vendor/htmx.js`
   - `node_modules/govuk-frontend/dist/govuk/all.bundle.js` → `static/js/vendor/govuk-frontend.js` (picking up the 5.11.1 → 5.14.0 bump as a side effect — see §11 for scope)
     These are vendor copies, not bundled/minified by esbuild (they're already built); a plain `cp` in the npm script is enough, matching how CSS already imports govuk-frontend via `--load-path=node_modules`.
3. **Wire the new step into every build path** (Chewie's requirement — the failure mode is a container or a CI run that silently ships a page with no interactivity):
   - Append it to the `build` npm script: `"build": "npm run build:sass && npm run build:backoffice && npm run build:js && npm run build:vendor"`. That single change is what makes `Dockerfile:85` (`RUN npm run build`), CI (`.github/actions/setup-python-env/action.yml`, which runs `npm install && npm run build`), and `just install` all pick it up — none of those three need editing.
   - Add a `just build-vendor` recipe (same shape as `build-js`: echo, `npm run build:vendor`, `touch src/opendlp/entrypoints/flask_app.py`) and add it to `build-all`: `build-all: build-all-css build-js build-vendor`. That covers `just run`, `just test`, `just test-bdd` and friends, which all depend on `build-all`.
   - Add `backend/static/js/vendor/` to the repo-root `.gitignore`, alongside the existing build-output entries (`dist/`, `backend/static/css/application.css`), consistent with "nothing built is committed".
   - A Phase 1 acceptance check: `git clean`-equivalent fresh checkout → `npm install && npm run build` → `static/js/vendor/` contains all three files; and `docker compose build` + load a page → Alpine and htmx work.
4. Update the four CDN `<script>` tags in `base.html` / `base_public.html` / `backoffice/base.html` to `{{ url_for('static', filename='js/vendor/...', v=static_hashes(...)) }}`, keeping the existing `nonce`.
5. No CSP header changes needed — `strict-dynamic` already authorises same-origin nonce'd scripts; removing the jsdelivr allowlist entries (currently vestigial per `frontend_security.md`) is a nice-to-have cleanup, not a requirement.
6. Update `docs/frontend_security.md` and `docs/frontend_build.md` to describe vendored Alpine/htmx/govuk-frontend instead of CDN.

**Risk:** none functionally (same code, different origin), but it's the first thing a broken build makes visibly obvious (unstyled page / no interactivity) per the existing "nothing built is committed" tradeoff in `frontend_build.md` — worth calling out in the PR description.

---

## 3. JSON error-handling convention — ✅ DONE (Phase 1c)

Written up as `docs/agent/json_api_conventions.md`, summarised in `docs/frontend_security.md` and `AGENTS.md`, and applied.

**Implemented:**

- `OpenDLPError.user_msg()` returns a generic translated string; a new `CuratedMessage` mixin makes it return `str(self)`, and 13 exception classes opt in (`UserAlreadyExists`, `InvalidCredentials`, `InvalidInvite`, `InsufficientPermissions`, `InvalidResetToken`, `EmailNotConfirmed`, `InvalidConfirmationToken`, `RateLimitExceeded`, `EmailTemplateInvalid`, `ImageQuotaExceeded`, `DocumentQuotaExceeded`, `OAuthError` — and `OAuthStateError` by inheritance). A mixin rather than 13 hand-written methods, so opting in is one word on the class line and visible at a glance.
- Deliberately **not** opted in: `PasswordTooWeak`, `InvalidSelection`, and the whole `NotFoundError` tree. Their messages carry ids and internal detail (`f"Registration page {page.id} has no HTML source"`) or, for `InvalidSelection`, are sometimes `str(e)` from the sortition library. This is the distinction doing real work.
- `RegistrationPageNotReady` defines `user_msg()` directly — the domain must not import the service layer, so it implements the protocol without the mixin, and callers duck-type on the method.
- The two `str(e)` call sites in `backoffice_registration.py` now use `.user_msg()`.
- `_dev_error(exc)` added to `dev.py` as a module-local helper, per §11 row 11. It duck-types on `user_msg` and falls back to the generic message, so an unexpected `ValueError` can't leak either.
- The five handlers narrowed to `except (InsufficientPermissions, NotFoundError, RegistrationPageNotReady, ValueError)`, each now logging via `structlog` before returning. `_handle_submit_registration` lost its `except` entirely: that service reports validation problems in its result rather than raising, so it had nothing specific to catch and anything it does raise is genuinely unexpected.
- Tests: `tests/unit/test_exception_user_msg.py` (28) pins down which exceptions expose their message and that the uncurated ones don't; `tests/component/test_dev_registration_page_handlers.py` (17) covers all five previously untested handlers, including that an unexpected `RuntimeError` still propagates to the route handler rather than being swallowed.
- `just translate-regen` run for the two new strings.

**Deviation worth noting:** the plan said this "wants its own commit" separate from the `dev.py` changes. It landed as one commit — the `dev.py` handlers are the only consumer of `_dev_error`, and `_dev_error` only makes sense given `user_msg()`, so splitting would have left a commit that adds a helper nothing calls.

**The rule:**

- A JSON error response's `"error"` field must be either (a) a translated, curated string you wrote (`_("...")`), or (b) `exc.user_msg()` on a domain exception specifically designed to carry a safe, user-facing message (see below) — never `str(e)` from a bare `except Exception`.
- **Catch narrowly.** Chewie's call: option (a) below is the general principle. Catch the specific exceptions a call can actually raise; let genuinely unexpected ones propagate to a single outer handler that logs and returns a generic message.
- Every `except Exception` branch that does survive and produces a JSON response must log the real error via `structlog` (`logger.exception(...)` or `.error(...)`, with `error=str(e)`) and return a generic, translated message plus an appropriate status code (usually 500). This is already the house style in `backoffice_registration.py` / `backoffice.py`; it just needs to be written down and applied to `dev.py`.
- Envelope shape (already the de facto standard): success is the resource at `2xx`; errors are `{"error": "...", "reason"?: "..."}` at a real status code. Document this as _the_ shape, matching §Migration in `vanilla-alpine-json.md`.

### `user_msg()` — making "safe to show" explicit

Chewie's point: today, "this exception's `str()` is a curated user-facing message" is a fact you can only learn by reading the exception class. `backoffice_registration.py:811` and `:908` pass `str(e)` to the client and are correct; a copy-paste of that line one class over would be a leak. Nothing — not a reviewer skimming, not a grep, not a linter — can tell the two apart.

So: add an explicit `user_msg()` method to the exceptions that carry safe messages.

- Put a default `user_msg()` on `OpenDLPError` in `src/opendlp/service_layer/exceptions.py`. The default must _not_ be `return str(self)` — that would silently make every exception in the tree claim to be user-safe, which is the current problem with extra steps.
- **Decided (Chewie): the default returns a generic translated string** — `_("Something went wrong")` or similar — rather than raising `NotImplementedError`. The reasoning: a class that forgets to override degrades to an unhelpfully vague message, which is annoying; raising would turn a handled error into a 500 with no feedback at all, which is worse. Better too little information than a crash. The vagueness is caught by review instead — a `sf-code-review` check (§7) that new user-facing exception classes override `user_msg()`.
- Worth a comment on the base-class default saying exactly this, so the next person doesn't "improve" it into `str(self)` and quietly undo the whole point.
- Override it on the exceptions that already build a curated message: `ImageQuotaExceeded`, `DocumentQuotaExceeded`, `EmailTemplateInvalid`, `UserAlreadyExists`, and the rest of the `_()`-carrying classes in that module. For most it is literally `return str(self)` — but written _once_, in the class that has earned it, rather than at every call site.
- Then the rule for blueprints becomes mechanically checkable: **a JSON response body never contains `str(e)`; it contains `e.user_msg()` or a literal `_("...")`.** A grep for `str(e)` inside a `jsonify`/dict-return is then a review flag on its own, with no case-by-case judgement needed — which is exactly what makes it worth doing.
- This is a cross-cutting change to `exceptions.py` plus the two call sites in `backoffice_registration.py`. It's small, but it isn't free, and it touches production error paths — so it wants its own commit, with the existing component tests for the quota paths proving the messages are unchanged.

### The dev-only error message — a helper in `dev.py`

Chewie's second point: `dev.py` is used by developers, the full error _is_ in the Flask console output, but in the moment you're looking at the page, not the terminal. Suppressing the raw string without pointing anywhere is worse for the dev than the current leak.

**Decided (Chewie): a helper function local to `dev.py`, not a `dev_msg()` method on the exception hierarchy.** That keeps the dev-only concern in the dev-only file, and avoids giving every production exception a method that production code must never call — a footgun in the opposite direction from the one we're fixing. Shape:

```python
def _dev_error(exc: Exception) -> str:
    """Dev-only error text: the safe message, plus a pointer to where the real one is.

    The full traceback is in the Flask console, but the developer is looking at
    the page, so say so explicitly rather than leaving them at a dead end.
    """
    msg = exc.user_msg() if isinstance(exc, OpenDLPError) else _("Something went wrong")
    return f"{msg} {_('(check the Flask console log for full error details)')}"
```

Two things this buys us beyond tidiness: the `isinstance` check means a non-`OpenDLPError` (a `ValueError` from a service call, say) can't leak its `str()` either, without every handler having to think about it; and the whole dev-only convention is one function, so it can be changed in one place if the wording turns out to be wrong in practice.

Every error response in `dev.py` goes through it, including the outer catch-all in `service_docs_execute` — so the truly-unexpected case gives the dev "something blew up, look at the terminal", which is honest and actionable, rather than either a leaked traceback string or a dead end. The real exception still gets logged via `structlog` at every one of those points; the helper governs what reaches the page, not what reaches the log.

**Fix required:** the five `dev.py` handlers listed in §0 (`_handle_publish_registration_page`, `_handle_unpublish_registration_page`, `_handle_close_registration_page`, `_handle_reopen_registration_page`, `_handle_submit_registration`), applying option (a):

- (a) **Chosen.** Narrow the `except Exception` to the specific exceptions each service call can actually raise (`RegistrationPageNotReady`, `SlugError`, `ValueError`, etc. — to be determined per handler by reading the service functions), return `_dev_error(exc)` for those, and let anything truly unexpected propagate to the outer `except Exception` in `service_docs_execute`, which already logs-and-generic-messages correctly (and which also routes its message through `_dev_error`).
- (b) Rejected: keep a catch-all but change it to `logger.exception(...)` + a generic message. Loses the specific, useful message for the expected failures, which is most of what these handlers hit.

Narrowing means reading each service call to find what it actually raises — which is also what gives the component tests (§7) a concrete target rather than a `pytest.raises(Exception)` shrug.

---

## 4. Preventing server/JS JSON drift

Per `contract-style-testing.md`, the recommendation for "a Flask app with a few JSON endpoints" was **golden fixtures generated by the Python test suite (option 1) + a hand-written JSON Schema validated on both sides (option 2)**. I'm carrying that recommendation forward. Concretely:

1. **Schemas.** One JSON Schema file per JSON response shape, `additionalProperties: false`, required/optional fields marked, enums for status/error codes. Location wasn't settled in review; proceeding with `src/opendlp/schemas/json_api/*.schema.json` unless someone objects, since the schema is a property of the server's API rather than documentation about it, and keeping it in `src/` means it ships with the package and can be loaded by path from both pytest and Vitest without a `../../..` climb. Easy to move later — it's a directory rename plus two path constants. Start with the highest-value ones: the registration image/document upload+list responses, the autocomplete search response, and whatever the pilot migration (§9) ends up touching.
2. **Python side:** a pytest fixture that (a) hits the real endpoint via the Flask test client, (b) asserts the response validates against the schema (`jsonschema.validate`), (c) writes the response body to a fixture file under (proposed) `tests/fixtures/json_api/*.json`, normalising volatile fields (UUIDs, timestamps) the way the fixture doc describes. A CI step (`git diff --exit-code` on the fixtures dir, or just asserting fixtures are up to date within the test itself) fails the build if a fixture goes stale without the JS being updated.
3. **JS side:** Vitest tests `import` the fixture JSON directly — never a hand-typed literal of an API response, per the invariant in `contract-style-testing.md`. A small Vitest helper also validates the imported fixture against the same schema with `ajv`, so schema and fixture can't drift from each other either.
4. **Naming: "API fixtures"** — confirmed by Chewie. Not "contract tests", which is reserved in this repo for fake-vs-SQL repository parity (§0). Use it consistently in the fixture directory name (`tests/fixtures/json_api/`), the docs, and any `just` target, so the two never get conflated in conversation or in CI output.
5. **Where the Python-side test lives:** `tests/component/` fits best (drives real routes over a `FakeUnitOfWork`, no DB needed) rather than a new top-level tier — this is additive to the existing component-test style, not a new testing level.
6. **Dependencies:** `ajv` (npm) and `jsonschema` (`uv add --group dev jsonschema` — it is _not_ currently installed, §0). Both approved in §1.

This is more machinery than "just Vitest," but it's the piece that actually answers the "how do we stop the JSON shape from drifting between server and JS tests" question — a Vitest suite with hand-typed fixtures gives false confidence without it.

---

## 5. JS file organisation and tooling — ✅ TOOLING DONE (Phase 1b)

The tooling half is implemented; the file reorganisation (`components/`, `lib/`, `init/`) happens with the §9 migrations, not before there is anything to put in them.

**Implemented:** Vitest (jsdom) under `just test-js`, which `test-html`/`test-xml`/`test-nobdd` depend on; ESLint (flat config, `eslint.config.mjs`) and Prettier as `- repo: local` prek hooks in both pre-commit configs; `djjs` scoped to `^backend/templates/`. Configs are `.mjs` because `package.json` has no `"type": "module"` and `tailwind.config.js` is CommonJS, so a `.js` config would be loaded as CJS.

**Decisions taken where the plan left room:**

- **Test placement: `tests/js/`, not colocated.** The plan said scaffold colocated pending the team discussion, but colocated collides with the hard constraint it also names — everything under `static/` is web-served, so `static/js/foo.test.js` would be publicly fetchable unless Flask's static handling learned to exclude it. `tests/js/` sidesteps that and matches where every other test in the repo lives. **Still reversible** — it is the `include` glob in `vitest.config.mjs` — but colocating would first need the static-serving exclusion built.
- **Classic scripts are tested as they ship.** Files under `static/js/` are loaded as plain `<script src>` and cannot use `export` without changing how they load. `tests/js/support/load-global-script.js` evaluates one and returns the named declarations, so `url-utils.js` is now covered (25 tests) without touching how it is served.
- **Prek hooks use `language: system` + `npm --prefix backend run …` with `pass_filenames: false`.** Verified working with prek 0.4.12, so the wrapper-script fallback wasn't needed.
- **`no-unused-vars` is configured with `caughtErrors: "none"` for `static/**`.** Several handlers swallow an exception deliberately; whether that is justified is a review question (and CLAUDE.md already requires a comment), not something the linter can judge.

**Findings — two real bugs the linter surfaced on its first run.** Neither is fixed, because Phase 1b is explicitly tooling-only:

1. **`urlSetParam` is defined twice, with different behaviour.** `static/js/url-utils.js:31` and `static/backoffice/js/alpine-components.js:19` both declare a global of that name, and `templates/backoffice/base.html` loads both — so on every backoffice page the second silently overwrites the first. They are not equivalent: the url-utils version has a try/catch fallback and returns an empty input unchanged, the backoffice version resolves against `window.location.origin` and would throw on an empty URL. Whichever page you are on, half the callers are getting an implementation they were not written against. This is exactly the mess §9's move to `lib/` modules exists to end, and it should be resolved there rather than by picking a winner now.
2. **`../.pre-commit-config-ci.yaml` was already missing the `no-strftime-in-templates` hook** — a pre-existing drift between the two configs, predating this work, which means that rule has never been enforced in CI. The header comment warned this would happen. Left alone as an unrelated fix; worth a separate one-line commit.

Following §5 of `vanilla-alpine-json.md` directly:

- `static/js/` (shared) and `static/backoffice/js/` (backoffice) split into `components/` (Alpine.data components), `lib/` (pure helpers — `url-utils.js` is the model), `init/` (Alpine directives/magics/`alpine:init` wiring), and now `vendor/` (§2). ABOUTME headers on every new file per house style.
- Vitest config: jsdom environment. **Test-file placement (colocated `url-utils.js` + `url-utils.test.js`, vs a mirrored `tests/js/` tree) is deferred — Chewie is discussing it with the team.** Everything else in this section can proceed; the Vitest `include` glob is a one-line change once the answer lands, so this does not block Phase 1. Colocated remains my suggestion (commoner Vitest convention, keeps a component's logic and tests together), but it is genuinely a team-taste call, and note the one hard constraint: whatever the layout, `*.test.js` must be excluded from the Flask static-file serving path and from `static_hashes()`, since anything under `static/` is web-served.
- **Where it runs in the `just` pipeline — decided (Chewie): tests under `just test`, linting under `just check`.** Concretely:
  - `npm run test` runs Vitest. Wire it into the `just test` chain — the natural spot is a `just test-js` recipe that `test-html`/`test-nobdd` depend on, or a line in the existing recipes; either way `just test` alone must fail if a JS test fails. It is fast (no browser, no DB) so it should run _first_, before the 10-minute Python suite, so a broken JS test fails in seconds rather than after the full run.
  - Linting goes into `just check` **via prek**, not as a bespoke `just check` line — see §1. `just check` already is, in the main, "run the prek hooks", and putting eslint/prettier there means they also run at commit time for free.
  - Do _not_ also put Vitest in `just check`. My earlier draft suggested both; Chewie's split is cleaner and I agree on reflection — "check = static analysis, test = behaviour" is a boundary worth keeping crisp, and duplicating the run just makes `just check` slower for no new signal.
- eslint config: flat config (`eslint.config.js`, the current default). Note what eslint can and cannot do for us here: CSP-Alpine's restrictions (no arrow functions, no template literals, no string arguments to `@click`) apply to _Alpine expressions in HTML attributes_, not to `.js` files — in an external JS file those constructs are perfectly fine. So eslint covers file-based JS quality only; CSP-Alpine attribute compliance stays a manual/review check against `patterns.html`. Say this explicitly in the docs (§6), or someone will reasonably assume a green lint run means CSP-safe.
- CI: with linting inside prek, CI needs _no_ new lint step — `just check-ci` already runs `prek run --all-files --config ../.pre-commit-config-ci.yaml`, so the eslint/prettier hooks come along automatically **provided they were mirrored into the CI config** (§1). The only genuinely new CI wiring is the Vitest run, which arrives via `just test`. `.github/actions/setup-python-env/action.yml` already does `npm install`, so `node_modules/` is present for both.

---

## 6. Documentation updates — ✅ DONE for phases 1a–1c

Everything below is done except the parts that describe work not yet started (§4's API fixtures, which land in Phase 2). `docs/agent/frontend_js_testing.md` and `docs/agent/json_api_conventions.md` both exist; `AGENTS.md` gained a "JSON responses" section under Development Patterns, the `just test-js` command, and index entries for both new docs.


- **`docs/frontend_security.md`**: replace the CDN Alpine/htmx snippets with vendored-script examples (§2); add the JSON error-handling convention (§3) either inline or as a link to a new doc.
- **`docs/frontend_build.md`**: document the vendor copy step (§2) alongside the existing three tools; note Vitest/eslint as a fourth and fifth tool once approved (§5).
- **New: `docs/agent/frontend_js_testing.md`** (permanent, alongside `frontend_testing.md`) — Vitest conventions, the fixture/schema drift-prevention setup (§4), and where JS tests live. Cross-link from `docs/testing.md`'s BDD section so there's one obvious jumping-off point regardless of which doc someone lands on first.
- **`docs/testing.md`**: add a short "JavaScript testing" pointer section linking to the new doc, and clarify that "contract" is reserved for the fake/SQL meaning while "API fixtures" is the JSON-drift thing (§4).
- **`AGENTS.md`** (not `CLAUDE.md` — `CLAUDE.md` is a symlink to `AGENTS.md`, confirmed by Chewie; edit `AGENTS.md` directly and the symlink follows): add a line under "Development Patterns" pointing at the new JS conventions doc, same as the existing i18n/database-pattern call-outs, so future sessions don't have to rediscover this plan. Also update the two existing `AGENTS.md` references that this work invalidates — the "Testing and Quality" section (Vitest now runs under `just test`) and the JSON error-handling rule (§3's `user_msg()`).
- **`docs/frontend_build.md`**: also record the `build:vendor` → `build` → Dockerfile/CI chain (§2), since the whole point of that wiring is that it's invisible until it breaks.

Note for future sessions: several docs in this repo say "CLAUDE.md" when they mean the file — the symlink means editing either path works, but new edits should target `AGENTS.md` so the content lives with the real file.

---

## 7. `sf-code-review` skill updates — ✅ DONE (Phase 1c)

Six checks added to `.claude/skills/sf-code-review/SKILL.md`'s "Things to Check" list, covering the items below plus the `CuratedMessage` opt-in and the both-places build wiring from §2.

Original list, for reference:

- If JS files changed under `static/js/` or `static/backoffice/js/`: is logic in `Alpine.data()` components, not inline in templates? Does it have a Vitest test if it contains non-trivial logic (debounce, state transitions, URL building)?
- If a JSON-returning route changed shape: was the JSON Schema updated, and did the fixture regenerate (no stale fixture diff)? Flag a hand-typed literal API response in a `.test.js` file as a defect in itself, per the drift-prevention invariant.
- Does any JSON response body contain `str(e)`? Once `user_msg()` exists (§3) this is a bright line, not a judgement call: the body carries `e.user_msg()` or a literal `_("...")`, never `str(e)`. This is exactly the kind of thing review should catch, since it's easy to write by copy-pasting a working example that happens to be safe.
- Does an `except Exception` branch producing a JSON response log via `structlog` and return a generic message? And is the except as narrow as it can be (§3's option (a))?
- Does a new exception class intended for user-facing messages override `user_msg()`?
- Is any new/changed script tag using a CDN URL instead of a vendored copy?
- Did a new npm build script get added without being wired into the `build` script and `just build-all` (§2)?

---

## 8. DEFERRED: should the dev blueprint have tests, and is it a safe pattern to copy?

**Status: deferred — Chewie is discussing this with the team. Do not act on this section.** What follows is the material for that discussion, unchanged.

What this blocks, and what it doesn't:

- **Not blocked:** fixing the five leaky handlers (§3). That's a real bug in a real code path under the rule we're about to write down, and it's the right thing to do whichever way §8 lands. It stays in Phase 1.
- **Not blocked:** the `patterns.html` migration (§9), which was agreed on its own merits.
- **Blocked:** any broader backfill of `dev.py` test coverage, and any "this is / isn't a pattern source" annotation in `dev.py` or the docs. Phase 5's shape depends on the answer.

**What's there today:** `dev.py` is a real, fairly large (1500+ line) blueprint with its own JSON API (`/dev/service-docs/execute`) that exercises most of the service layer, plus the `patterns.html` "living reference" page. It's dev-only (`not config.is_production()`) and admin-gated. Test coverage is partial: image/document/email handlers have component tests; the registration-page-lifecycle handlers and the route itself don't (§0), and that's exactly where the JSON error-handling violation lives (§3) — i.e., the _untested_ corner is also the _unsafe_ corner. That's not a coincidence I'd bet against generalising.

**The question behind the question:** Chewie's framing was "if Claude copies patterns from `dev.py` when writing prod code, how do we make sure it copies the _good_ parts?" Two live options:

- **(a) Bring `dev.py` up to the same bar as production code** — full test coverage, same error-handling discipline, and treat it as a legitimate pattern source. Cost: it's meant to be a low-stakes scratch space for interactive testing; holding it to production standards might blunt that purpose and slow down adding new dev-tool endpoints.
- **(b) Explicitly mark it as _not_ a pattern source** — a comment/doc note ("dev-only, does not follow production error-handling conventions, do not copy verbatim") at the top of `dev.py` and in `docs/agent/frontend_js_testing.md`, and rely on `patterns.html`/`docs/frontend_security.md`/the new JSON conventions doc as the actual canonical examples instead. Cost: `patterns.html` itself is currently the worst offender for "inline, untested script" (§0) — so this only works if the `patterns.html` migration (§9) happens, and happens early.

My instinct is a mix: (b) as the durable answer — `patterns.html` and the JSON conventions doc are the source of truth, not `dev.py` — plus fixing the five leaky handlers regardless (§3, needed either way since it's a real bug in a real code path even if low-severity), without necessarily chasing full test parity across all of `dev.py`. But this is the team's call, not mine to make unilaterally.

---

## 9. Migrating the existing inline scripts

Order agreed by Chewie: `patterns.html` → `assembly_registration.html` → `service_docs.html`. Incremental, per `vanilla-alpine-json.md` §5, smallest/highest-signal first:

**Pilot: `patterns.html` (284 lines) first.** Rationale: it's the smallest of the three, and it's _the documented living reference_ — migrating it first means the reference itself demonstrates the new convention instead of contradicting it (right now `docs/frontend_security.md` and CLAUDE.md point people at a page that's 100% inline script). Low product risk since it's dev-only.

**Then `assembly_registration.html` (567-line inline block)** — the actual production high-value target (`vanilla-alpine-json.md` §2.3 calls out its image manager as the canonical "genuinely stateful" use case). This is the one that most benefits from the drift-prevention machinery in §4 since it's the heaviest JSON-endpoint consumer.

**Then `service_docs.html` (722 lines)** — dev-only, lowest urgency, and its priority partly depends on how §8 gets resolved (if `dev.py` isn't meant to be a pattern source, polishing its UI page is less urgent than the other two). Since §8 is deferred, this one stays parked; the first two are not affected.

For each: lift inline `<script>` into named `Alpine.data()` components under `static/backoffice/js/components/`, unit-test the extracted logic with Vitest, shrink the template to markup + flat `x-data` wiring, regenerate `static_hashes()`/cache-busting automatically (no registration needed per `frontend_security.md`), backfill/confirm BDD coverage for the flow. No behavioural changes in the same PR as the extraction — that's a second pass, only after tests exist to prove behaviour is unchanged.

---

## 10. Proposed phase sequencing

1. **Phase 0 — decisions.** Mostly done (§11). Three items still with the team; none of them block Phase 1.
2. **Phase 1a — vendoring. ✅ DONE.** Vendor Alpine/htmx/govuk-frontend (§2), including the `build` npm script + `just build-all` + `.gitignore` wiring and the fresh-checkout/Docker acceptance check. Update `docs/frontend_security.md` and `docs/frontend_build.md`. Self-contained and shippable on its own.
3. **Phase 1b — JS tooling. ✅ DONE.** Add Vitest (under `just test`) and eslint/prettier (as prek hooks in **both** pre-commit configs), apply the agreed `djjs` scoping (§1), and a first test proving the wiring end to end. Landed with `tests/js/` rather than colocated — see §5 for why, and it remains a one-line change.
4. **Phase 1c — error-handling convention. ✅ DONE.** `user_msg()` on the exception hierarchy with a generic default, the `CuratedMessage` opt-in mixin, both `backoffice_registration.py` call sites switched, `_dev_error()` in `dev.py` with the five handlers narrowed onto it (§3), the convention documented (§6) and the checks added to `sf-code-review` (§7).
5. **Phase 2 — drift-prevention machinery.** Build the API-fixture + schema pipeline (§4) against one existing JSON endpoint (propose: the image upload/list endpoints, since they're the most-cited good example already) before it's needed for the pilot migration, so the pilot isn't also inventing the test infra.
6. **Phase 3 — pilot migration.** `patterns.html` (§9), using the now-proven fixture/schema/Vitest setup.
7. **Phase 4 — production migration.** `assembly_registration.html` image/alt-text manager.
8. **Phase 5 — PARKED pending §8.** `service_docs.html`; any further backfill of `dev.py` test coverage. Not to be started before the team discussion lands.

Each phase is independently shippable and reversible; nothing here requires a big-bang cutover. Phase 1 is split into three because the three parts touch entirely different files and have different review audiences — bundling them would make the vendoring change (the one with real deploy risk) hard to see.

---

## 11. Decisions from Chewie's review

| #   | Question                                              | Decision                                                                                                                                                                                                                                |
| --- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | New dependencies (§1)                                 | **Yes to all six.** Vitest, eslint+prettier, `@alpinejs/csp`+`htmx.org`, `ajv`, and `jsonschema` (separately confirmed once it turned out not to be installed already). eslint/prettier run as **prek hooks**, not a `just check` line. |
| 2   | Drift prevention (§4)                                 | **Confirmed:** golden fixtures + JSON Schema on both sides. Named **"API fixtures"**. Schema location not raised in review — proceeding with `src/opendlp/schemas/json_api/` (§4.1).                                                    |
| 3   | Dev blueprint (§8)                                    | **Deferred** — team discussion.                                                                                                                                                                                                         |
| 4   | Fix the five `dev.py` leaks now                       | **Yes**, via option (a): narrow the excepts. Plus two additions from Chewie — `user_msg()` on domain exceptions, and a "check the Flask console log" hint for dev-only errors (§3).                                                     |
| 5   | Vitest test-file placement                            | **Deferred** — team discussion. Scaffold colocated; one-line change either way.                                                                                                                                                         |
| 6   | Where Vitest runs                                     | **`just test` for tests, `just check` for linting** — and the linting gets there by living in the prek config, since that's the bulk of what `just check` does.                                                                         |
| 7   | Pilot order (§9)                                      | **Confirmed:** `patterns.html` → `assembly_registration.html` → `service_docs.html`.                                                                                                                                                    |
| 8   | govuk-frontend bump                                   | **5.11.1 → 5.14.0 is fine**, fold it into the vendoring change. **govuk-frontend 6.x is explicitly out of scope for this round of work** — it's a much bigger upgrade and needs its own planning.                                       |
| 9   | Anything load-bearing in `dev.py`/`service_docs.html` | **Deferred** — team discussion. Phase 5 stays parked until answered.                                                                                                                                                                    |
| 10  | `user_msg()` default on `OpenDLPError` (§3)           | **Generic translated string**, not `NotImplementedError` — better an unhelpfully vague message than a 500 with no feedback at all. Vagueness is caught by a `sf-code-review` check instead (§7).                                        |
| 11  | Where the dev-only message lives (§3)                 | **A `_dev_error()` helper local to `dev.py`**, not a `dev_msg()` method on the exception hierarchy — keeps the dev-only concern in the dev-only file, and doesn't give production exceptions a method production must never call.       |

### Still open

- **§8 — dev blueprint:** pattern source or not, and how much test coverage it earns. Blocks Phase 5 and the "do not copy this" annotations.
- **§5 — Vitest test-file placement:** colocated or mirrored tree.
- **§10 Phase 5 — is anything in `service_docs.html`/`dev.py` load-bearing** for a real workflow rather than a dev convenience?

That's the whole list — the two §3 sub-questions from the previous round are now answered (see the table rows 10 and 11).

### Pre-commit config decisions

Both of the landmines I flagged in the previous round now have answers:

- **`djjs` vs prettier (§1) — resolved.** Scope `djjs` to `templates/` (inline JS only); prettier owns standalone `.js` files. Two implementation details in §1: scoped that way `djjs` matches nothing today (there are no `.js` files under `templates/` — inline `<script>` blocks are handled by the `djhtml` hook, not `djjs`), so it becomes a statement of intent rather than an active hook; and prettier must be scoped to `^backend/.*\.js$` rather than just `static/`, or `backend/tailwind.config.js` ends up formatted by nothing.
- **`../.pre-commit-config-ci.yaml` stays hand-maintained.** Chewie's call — it changes infrequently, so the duplication is acceptable. The working rule is just: hooks land in both files in the same commit.
