# Frontend interactivity: vanilla JS + Alpine.js with JSON routes

**Status:** proposal / decision document
**Audience:** the two of us who maintain OpenDLP
**Recommendation:** deliberately adopt vanilla JS + Alpine.js (CSP build) talking to JSON-returning Flask routes as our approach for _internal, JS-heavy_ interactivity — organised into real JS files, held to Alpine conventions, and covered by JS unit tests plus BDD. Keep server-rendered HTML (and HTMX where it already fits) as the baseline, especially for public pages.

This is not a call to rewrite anything. It is a call to **pave a cowpath we are already walking**, and to stop walking it badly.

---

## 1. What we actually have today

Before arguing, here is the ground truth from the codebase, because the argument rests on it.

**Two front ends, both already carrying Alpine + HTMX.** Both `templates/base.html` (public/GOV.UK, Sass) and `templates/backoffice/base.html` (Tailwind) load the same stack from CDN with a nonce:

- `@alpinejs/csp@3.15.8` (the CSP-safe Alpine build)
- `htmx.org@2.0.7`
- our own external JS: `utilities.js`, `url-utils.js`, `alpine-scroll-manager.js`, and the Alpine component registries.

**We already return JSON, and we already fetch it.** This is the decisive fact. JSON endpoints are not hypothetical — they have crept in and are in production use:

- `backoffice.py` returns `jsonify(results)` for the user-search autocomplete.
- `backoffice_registration.py` has a small JSON API: image upload → `{"image": ...}`, alt-text edit (`Content-Type: application/json`), delete, and a form-skeleton generator returning `{"html": ...}`.
- `static/backoffice/js/alpine-components.js` already contains a genuinely good, accessible `autocomplete` component (WAI-ARIA combobox, debounce, keyboard nav) that `fetch()`es one of those JSON endpoints and renders the results client-side.

So the question is **not** "should we introduce JSON + JS?" We have. The question is whether we keep doing it accidentally or do it on purpose.

**The accidental version is already hurting.** `templates/backoffice/assembly_registration.html` is **1078 lines**, a large chunk of which is an inline `<script nonce>` block of Alpine components doing `fetch()` with `X-CSRFToken` headers against those JSON endpoints. `patterns.html` and `service_docs.html` have the same shape. That inline JS is: untested, uncacheable, not lintable, invisible to any build step, and mixed line-by-line with Jinja. This is the split-brain problem in its worst form — and notice it is a problem we _already own_. The good news is the well-factored counter-examples (`alpine-components.js`) prove we know how to do it right.

**Testing today is Python-only.** We have `pytest-bdd` + Playwright BDD/e2e (`tests/bdd/`, headless in CI), plus unit/component/contract/integration suites. There is **no JS unit test runner and no eslint**. We *do* now have a JS bundler: `package.json`'s `build:js` runs **esbuild**, bundling first-party ES modules from `static/backoffice/js/src/` into a self-hosted, nonce'd IIFE under `dist/` (see [docs/frontend_build.md](../../frontend_build.md); first consumer is the CodeMirror HTML editor). So the build pipeline for authored JS already exists — but every line of the inline `fetch`/Alpine logic above is still currently untestable except through a full browser BDD run.

**Public pages already degrade gracefully.** The public registration flow (`registration.py`) is fully server-rendered form POST — the organiser literally pastes plain HTML with `{{ form_action }}` and `{{ csrf_form_element }}`. No JavaScript is required to register. That constraint is real and we must not break it.

---

## 2. The argument

### 2.1 Pave the cowpath
We have JSON routes, a `fetch`-based accessible Alpine component, and a documented CSP-safe Alpine convention (`docs/frontend_security.md`, `templates/backoffice/patterns.html`, `/backoffice/dev/patterns`). Choosing this approach means **codifying and cleaning what exists**, not importing a new paradigm. The alternative — declaring JSON+JS a mistake and pushing everything back to HTMX/full-page — means throwing away working, accessible code and fighting the grain of the app. Boring-technology instinct (which we share) actually favours "make the thing you already run reliable" over "swap in a different thing."

### 2.2 It fits the two of us
We are two technical people. We are not going to staff a React front end, a design-system team, and a BFF API layer. Alpine is small enough to read in an afternoon; there is no compile-time framework, no JSX, no client router, no virtual DOM to reason about. State lives in `x-data` and in the URL. A JSON endpoint is just a Flask view that returns a dict. The mental model is "server renders the page; small islands of JS fetch small bits of JSON." That is about the least framework a person can adopt while still getting real interactivity.

### 2.3 It is the right tool where interactivity is genuinely rich
HTMX is excellent and we should keep it where it shines — the targets editor (`targets/*.html`) does category CRUD with `hx-post`/`hx-swap` and it is clean. But some interactions are inherently client-state-heavy: the registration image manager (optimistic UI, alt-text editing, previews), autocomplete comboboxes, multi-step modals whose "can I close yet?" depends on a polled task. Expressing those purely as server round-trips is awkward; a little client state is the honest model. That is exactly where Alpine + JSON earns its keep.

---

## 3. The considerations, honestly

### 3.1 Testing — the part we cannot hand-wave
This approach only pays off if the JS is testable, and today it mostly isn't. Concretely:

- **JS unit tests (new capability — needs a decision).** Propose adding **Vitest** (jsdom environment) as a dev dependency to unit-test the pure logic we already have and keep writing: `url-utils.js` (perfect pure-function target), the autocomplete's debounce/keyboard/aria-id logic, modal open/close/`canClose` transitions, scroll/focus URL manipulation. These are the bugs BDD tests catch slowly and flakily; unit tests catch them in milliseconds. Vitest is the current boring default (Vite-native, Jest-compatible API). **This is a new tool and a new language in the test stack — flag for explicit agreement before adding.** Alternatives: Jest (heavier, still fine) or Node's built-in `node:test` (no dep, but weaker DOM story). Wire it as `npm test` and into `just check`/`just test`.
- **eslint + prettier (new, smaller ask).** Once JS lives in files, lint it. Flag for agreement; low controversy.
- **BDD/e2e stays the top of the pyramid.** `pytest-bdd` + Playwright already drives real browsers headless in CI and already exercises Alpine/HTMX flows (`test_backoffice.py`, `test_scroll_preservation.py`). Client interactions that matter to a user get a BDD scenario. This is our regression net for the "does the island actually work in a browser" question that unit tests can't answer.
- **JSON endpoints are trivially contract-testable in Python.** A route returning `jsonify(...)` is easier to test than one returning HTML — assert on a dict, not on parsed markup. They slot straight into the existing `tests/contract` and Flask test-client integration tests. This is a genuine _advantage_ of the JSON style over server-rendered partials.

Net: unit-test pure JS logic (Vitest), contract-test JSON routes (pytest), BDD-test the integrated flow (Playwright). Every layer has a home.

### 3.2 Maintainability and the split-brain risk
Be honest: this approach asks a developer to hold **two languages and two state models** — Jinja/Python on the server, JS/Alpine reactive state on the client — and to keep any client-rendered markup in sync with server-rendered markup. That is real cognitive load and the strongest argument _against_ going further down this road. HTMX's whole pitch is avoiding exactly this by keeping rendering server-side.

Mitigations we should commit to, or this proposal isn't worth it:

- **Render HTML in one place.** Prefer JSON endpoints that return **data**, with the client rendering from an `x-for` template — _or_ endpoints that return server-rendered HTML fragments (the `{"html": ...}` skeleton pattern, or plain HTMX). Do not do both for the same widget. The failure mode is a card whose layout exists as both a Jinja macro and a JS template string; forbid that by convention.
- **Keep islands small.** Alpine is for a component, not a page controller. The 1078-line `assembly_registration.html` is the anti-pattern; the ~50-line `modal`/`autocomplete` components are the pattern.
- **One place to look.** All component logic in `static/**/js`, registered via `Alpine.data()`, never inline. A reviewer should find behaviour in a `.js` file, not by scrolling a template.

For a two-person team, the deciding factor is that we _already_ carry this load — the split-brain exists in the inline scripts today. Consolidating it into named, tested components is strictly less to hold in your head than 1000-line templates.

### 3.3 The public-page / no-JS constraint
Firm rule, and this approach respects it cleanly because it is _additive_:

- **Public pages (registration especially) must work with JS disabled.** They are server-rendered form POSTs today and must stay that way. Alpine is progressive enhancement only there — e.g. inline validation hints, never a JS-gated submit. The `js-enabled` body class (`base.html`) is the hook: enhancements hang off `.js-enabled`, and the no-JS path is the plain form.
- **Internal admin/backoffice pages MAY require JS.** Organisers using the selection tooling are authenticated staff on modern browsers; requiring JS there is acceptable and lets us build the richer interactions. This is where the JSON+Alpine investment concentrates.

The progressive-enhancement story for a JS-heavy island is: server renders a working (if plainer) control; Alpine upgrades it on load. Where a feature genuinely cannot exist without JS (drag-reorder, live autocomplete), it belongs on an internal page, not a public one.

### 3.4 Bookmarks, back/forward, reloadability
This is where client JS classically goes wrong, and the codebase already shows the right instinct — **URL is the state store**:

- `alpine-scroll-manager.js`'s stated philosophy is "URL-based state (testable, shareable, bookmarkable)"; the tabs/filter components navigate by real `href`/query params (`urlSelect`, `tabsKeyboard`), so back/forward and reload Just Work.
- **Convention: durable state goes in the URL** (query params for filters/tabs/pagination), so a reload or a shared link reproduces the view. Client-only Alpine state is for **ephemeral** UI: is this dropdown open, is this modal showing, what's typed in the search box.
- **Modals are ephemeral.** A modal is transient UI, not a location — except when its open-state is meaningful, in which case drive it from the URL and clear it on close. The existing `modal` component already supports exactly this (`closeUrl` "for server-driven modals whose open state lives in the URL, so closing clears it"). So: decorative/confirm modals are pure client state; a modal that represents "I am editing respondent X" gets a URL.
- We deliberately **avoid** a client-side router and `history.pushState`-driven SPA navigation. Full navigations remain real HTTP navigations. That keeps back/forward, bookmarking, and "just reload it" honest without us writing history-management code.

### 3.5 CSP — the sharp edge, stated plainly
This is the biggest tax and we should not pretend otherwise. Our CSP is `strict-dynamic` + per-request nonce; it forbids inline handlers, `eval`, and `Function()`. To live under it we run the **`@alpinejs/csp` build**, which cannot evaluate arbitrary expressions in attributes. The documented consequences (`docs/frontend_security.md`, `patterns.html`):

- ❌ no arrow functions, template literals, destructuring, or globals (`Math`, `console`) **in Alpine attribute expressions**;
- `x-model` must bind a **flat** property (`x-model="selected"`, not `x-model="form.field"`);
- `@click` handlers **cannot take string arguments** (`@click="doThing()"`, not `@click="doThing('arg')"`);
- AJAX must send `X-CSRFToken`.

Honest read: this makes Alpine noticeably clunkier than its marketing. You cannot write the terse one-liners Alpine demos show; anything non-trivial must move into an `Alpine.data()` component in an external file (where normal JS — arrow functions and all — is fine again, because that's the file, not an attribute). In practice the CSP build **forces** the discipline this proposal wants anyway: logic in files, templates only wiring flat properties and zero-arg method calls. So the constraint is painful but aligned. The costs are (a) a real learning curve — every new contributor will hit the flat-`x-model`/no-arg-`@click` walls at least once; (b) worse ergonomics than either plain HTMX (no client expressions at all) or non-CSP Alpine; (c) we depend on the CSP build continuing to be maintained. We accept these because loosening the CSP (e.g. `unsafe-eval` for full Alpine) is off the table — it weakens the XSS posture that `docs/personal-data.md` and our no-cookie-banner position quietly depend on.

One cleanup worth noting: we currently load Alpine/HTMX from `cdn.jsdelivr.net`. Under `strict-dynamic` the allowlist is ignored and the nonce is what authorises them, but a third-party CDN is a supply-chain and privacy surface. Prefer **vendoring** these into `static/` (self-hosted, nonce'd) as part of adopting this approach — it also removes a network dependency from page load.

---

## 4. The trade-offs, on the table

| | vanilla + Alpine + JSON (this proposal) | HTMX-only / server-rendered | React/SPA |
|---|---|---|---|
| Moving parts | Medium | Fewest | Most |
| State models to hold | Two (server + client) | ~One (server) | Two, plus a router/store |
| Rich client interactions | Good | Awkward for state-heavy UI | Best |
| CSP friction | Real (CSP Alpine build) | Minimal | Significant (build/nonce plumbing) |
| Server/client template sync risk | Present — must be disciplined | Low | High |
| Fits 2 people | Yes | Yes | No |
| Public no-JS story | Additive/PE, clean | Native | Hard |

We are explicitly choosing the **middle**: more capable than HTMX-alone for the handful of genuinely stateful screens, far less machinery than a SPA, and — critically — the option we are _already_ running. The honest cost is the two-state-model burden and CSP friction; the honest benefit is that we stop maintaining thousand-line inline-script templates and get real tests.

---

## 5. High-level sketch of the changes

Not a plan to execute now — a shape to agree on.

**JS file organisation**
- Everything under `static/js/` (shared) and `static/backoffice/js/` (backoffice). No behavioural logic inline in templates; inline `<script nonce>` limited to tiny bootstrap (the `js-enabled` class) as the CSP doc already says.
- Split the current omnibus registries by concern: `components/` (Alpine.data components: `modal`, `autocomplete`, `tabs`, `imageManager`, …), `lib/` (pure helpers: `url-utils`, formatting), `init/` (directives, magics, `alpine:init` wiring). ABOUTME headers on every file (house rule).

**Build / bundling (already in place)**
- Most JS is served as individual nonce'd `<script>` tags — simple, and fine to keep for plain global scripts. For anything that pulls in npm packages or wants module `import`/`export`, the **esbuild** step already exists: `build:js` bundles `static/backoffice/js/src/*` into a minified, self-hosted IIFE under `dist/`, wired into `npm run build` and the `just build-js` target ([docs/frontend_build.md](../../frontend_build.md)). So there is no new bundler to decide on — extending it to new entry points is the documented pattern. Default position: keep plain files + `static_hashes()` cache-busting for simple scripts, reach for the esbuild pipeline when a script grows npm dependencies or a real import graph. Also vendor Alpine/HTMX locally through the same pipeline (see §3.5).

**JSON API conventions**
- Endpoints intended for `fetch` live in clearly-named views; return either **data** (`jsonify({...})`) or a **rendered fragment** (`{"html": ...}`), never a mix for one widget.
- Consistent envelope: success `2xx` with the resource; errors as `{"error": "...", "reason"?: "..."}` with a real status code — this already exists in `backoffice_registration.py`; document it as _the_ shape.
- All error strings go through `gettext`/`_()` (already done) so JSON errors are translated like everything else.
- Mutating endpoints require `X-CSRFToken`; document the header once, apply everywhere.

**Alpine conventions under CSP**
- Logic in `Alpine.data()` components; templates only wire flat `x-model` props and zero-arg `@click` methods. Enforce via review against `patterns.html`, which stays the living reference (`/backoffice/dev/patterns`).
- Durable state → URL; ephemeral state → `x-data`. Modals ephemeral unless URL-backed via `closeUrl`.

**Testing**
- Add **Vitest** (jsdom) for JS unit tests; start by covering `url-utils`, autocomplete logic, modal state, scroll/focus helpers. **(new dep — needs sign-off.)**
- Add **eslint + prettier** for JS. **(new dep — needs sign-off.)**
- Keep pytest contract/integration tests on every JSON route.
- Add/keep a Playwright BDD scenario for each user-visible interactive flow; JS-requiring features are tested on internal pages only.
- Wire `npm test` (Vitest) + lint into `just check` and `just test` so JS is a first-class citizen of the gate, not an afterthought.

**Migrating the existing ad-hoc JS (incremental, no big-bang)**
1. Lift the inline `<script>` blocks out of `assembly_registration.html`, `service_docs.html`, `patterns.html` into named component files, unchanged in behaviour, then unit-test them.
2. Shrink those templates to markup + flat `x-data` wiring.
3. Regenerate `static_hashes()` / cache-busting for the new files; keep nonce'd tags.
4. Backfill BDD coverage for the flows as they move.
5. Only after the code is in files and tested, refactor for reuse.

None of this reimplements a feature — it relocates and tests code that already runs, which keeps us inside the "smallest reasonable change" rule.

---

## 6. Recommendation

Adopt vanilla JS + Alpine (CSP build) + JSON routes as the deliberate approach for internal, interaction-heavy screens; keep server-rendered HTML (and HTMX) as the default and the whole story for public/no-JS pages. Pay the two-state-model and CSP costs with eyes open, and buy them back with file organisation, JSON-route contract tests, and — the load-bearing new piece — **JS unit testing (Vitest) plus BDD**. The two things that need your explicit yes before I touch anything: **Vitest** and **eslint/prettier**. The esbuild bundler is already in the repo, so it's a pattern to extend rather than a decision to make. Everything else is reorganising and testing code we already ship.
