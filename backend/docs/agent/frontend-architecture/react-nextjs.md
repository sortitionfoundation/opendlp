# Frontend architecture option: React / Next.js

**Status:** advocacy document — one option among several. Read alongside the other
options in this folder before deciding.

**Author's stance:** I am arguing *for* React/Next.js here. But this is the heaviest
option on the table, and a proposal that hides its costs is worthless. So the case
below is the strongest honest case, and the cost section is deliberately unflinching.
By the end you should be able to see clearly why, for a two-person team shipping a
mostly-server-rendered GOV.UK application, this is probably the wrong choice — even
as you see what we'd gain if we took it.

---

## 1. The case for React/Next.js in *this* app

### 1.1 We are already half-way into a client-side app — incoherently

The strongest argument isn't hypothetical. Look at what the backoffice already is.

`templates/backoffice/` is roughly **4,900 lines** of templates that are *not* plain
server-rendered GOV.UK pages. They run on:

- **HTMX** — `hx-post` (~65 uses), `hx-target` (~67), `hx-swap` (~72), plus
  `hx-swap-oob` for out-of-band updates. Modals, tabs, pagination and progress
  dialogs are all server-partial swaps.
- **Alpine.js** (the CSP build) for local component state — dropdowns, tabs, modal
  open/close, search widgets (`x-data` across ~20 templates).
- **Tailwind CSS** — an entirely *separate* design system from the GOV.UK Frontend
  used on the public side, with its own build step (`build:backoffice`).
- **JSON endpoints + hand-written `fetch()`** — e.g. `backoffice.search_users`
  returns a JSON `[{id, label, sublabel}]` array consumed by an autocomplete
  component in `static/backoffice/js/alpine-components.js`.

That is three client-side technologies, a second CSS framework, ad-hoc JSON APIs and
bespoke `fetch()` glue — coordinated by hand. This is the "some JSON endpoints have
crept in with a fair bit of JS combining JSON with templates" problem, and it will
keep growing. Screens like `assembly_selection.html` (463 lines), `assembly_data.html`
(523 lines) and `assembly_registration.html` (1,078 lines) are genuine interactive
applications wearing a template's clothing: progress modals polling a background task,
tabbed data views, inline edits, replacement-selection flows.

The honest framing: **the backoffice already pays a fragmentation tax.** React/Next.js
is one way to pay that cost *once*, coherently, instead of in three overlapping
dialects. (It is not the only way — consolidating on HTMX-plus-a-little-Alpine, or on
a single lightweight island framework, are lighter answers to the same problem. Those
live in the sibling documents.)

### 1.2 Where SPA-grade interactivity genuinely earns its keep

Some screens want real client state, and would be materially better as components:

- **Selection configuration** (`assembly_selection.html`, targets editing in
  `assembly_targets.html` / `targets.py` at 915 lines): editing demographic targets,
  seeing live feasibility/roll-up as you change numbers, running a selection and
  watching progress without a full round-trip. This is a spreadsheet-like editing
  surface — exactly React's sweet spot.
- **Respondent management** (`respondents.py`, 998 lines; `assembly_respondents.html`):
  filter, paginate, bulk status changes, inline edits, search-as-you-type. Today this
  is HTMX swaps plus a JSON search endpoint.
- **Registration form builder** (`assembly_registration.html`, 1,078 lines): a
  genuinely complex authoring UI with a live preview.

For these, a component model with local state, derived values and a typed data layer
is a real ergonomic win over threading state through `hx-target`/`hx-swap-oob` and
Alpine `x-data` islands.

### 1.3 A mature, boring-in-a-good-way testing ecosystem

This is a real strength and deserves a fair hearing. The JS testing stack is
excellent and well-trodden:

- **Vitest / Jest** for fast unit tests of components and pure logic.
- **React Testing Library** for behaviour-focused component tests that assert on
  accessible roles and text, not implementation details — which dovetails with our
  accessibility commitments.
- **Playwright** for end-to-end — and we *already use Playwright* (via
  `pytest-playwright`), so the browser-automation knowledge transfers directly.
- **Mock Service Worker (MSW)** for API-boundary contract tests on the frontend.
- **Storybook** for component-level visual/interaction testing and a living
  component catalogue (we already have a `showcase.html` doing this by hand).

For the interactive backoffice screens, component tests in RTL are faster and more
targeted than driving the whole Flask app through Playwright, which is most of what
`tests/bdd/` does today.

### 1.4 Ecosystem, hiring, and routing

- **Talent pool.** React is the default frontend skill. If the team ever grows or
  needs contract help, React is far easier to hire for than "Flask + HTMX + Alpine +
  a bespoke Tailwind design system." (Weigh this honestly against the fact that the
  team is *two people right now* — see §2.2.)
- **Component ecosystem.** Data grids, date pickers, form libraries (React Hook Form
  + Zod), drag-and-drop, charts — mature, typed, accessible options exist off the
  shelf. (Caveat: we cannot use most of them as-is without breaking GOV.UK styling —
  see §2.3.)
- **Routing, bookmarks, back/forward.** This is a genuine SPA strength. A real router
  (Next.js App Router, or TanStack Router) gives us URL-addressable state,
  bookmarkable filtered views, working back/forward, and scroll restoration **for
  free** — the exact things we hand-roll today in `static/js/url-utils.js`,
  `alpine-scroll-manager.js`, `scroll_utils.py`, and the `test_scroll_preservation.py`
  BDD test. Client routing with proper history integration is a solved problem in
  this ecosystem in a way our current stack isn't.

### 1.5 Feasibility: the DDD service layer is a ready-made API seam

The architecture is genuinely well-suited to exposing an API. The service layer
(`src/opendlp/service_layer/`) already contains cohesive, framework-light use-case
functions — `assembly_service`, `registration_submission_service`,
`respondent_service`, `respondent_field_schema_service`, `selection_report`, etc. —
sitting behind a `UnitOfWork` and repositories. Blueprints are thin. Adding a JSON API
is mostly **serialisation over functions that already exist**, not new business logic.
The domain is plain Python and UUID-keyed, so it serialises cleanly. If we were going
to build an API, we're starting from a good place.

And the Node toolchain is **already in the repo**: `package.json` builds SCSS,
Tailwind, and — via **esbuild** — bundles first-party JS (npm-dependency modules
such as the CodeMirror editor) into a self-hosted IIFE bundle, with `govuk-frontend`
already an npm dependency (see [docs/frontend_build.md](../../frontend_build.md)).
We would not be introducing Node, npm packages, or a JS bundler from zero — though
none of that is the same as introducing React's runtime and component model.

---

## 2. The costs — honestly

This is the part that decides it. None of the following is soft-pedalled.

### 2.1 It is a second full application and a second stack

Today there is one application: a Flask app. Adopting React/Next.js means running
**two** — a Python backend/API and a JavaScript frontend — each with its own
dependency tree, lockfile, security-update cadence, build, lint/type-check, test
suite, and deploy target. `mypy` + `ruff` + `pytest` on one side; `tsc` + ESLint +
Vitest on the other. Every feature now potentially touches both.

The service layer being a clean seam makes the API *feasible*; it does not make the
second application *cheap*. Feasible and cheap are different claims.

### 2.2 The two-person team — the biggest weakness, stated plainly

**This is the argument that most likely sinks the proposal, and it should.**

Two technical people cannot cheaply hold two full mental models. Right now, a
context-switch is Python-to-Jinja — same language family, one runtime, one debugger,
one test command (`just test`). After this change, delivering a single vertical
feature means: touch the domain/service layer in Python, design and version a JSON
contract, implement and type it in TypeScript, wire data fetching and cache
invalidation, handle loading/error states, and keep two test suites green. That is a
real multiplier on the cost of *every* change, paid *forever*, not just during the
migration.

The React ecosystem also churns faster than Flask. Someone has to own Next.js major
upgrades, React version bumps, and the build toolchain. With two people, that person
is also the person doing everything else. "Large talent pool" (§1.4) is a benefit only
*if we hire*; until then it's latent, and the day-to-day reality is two people
maintaining twice the surface area.

If you read nothing else in this document, read this paragraph: **for a two-person
team, the ongoing maintenance cost is the dominant term, and it points away from
React/Next.js.**

### 2.3 The GOV.UK Design System does not come in a React box

This is a large, concrete, easy-to-underestimate cost.

`govuk-frontend` ships as **Nunjucks macros, HTML and CSS/JS** — not React components.
There is **no official GDS-maintained React port.** Our public side extends `base.html`
with GOV.UK markup and relies on `GOVUKFrontend.initAll()` for progressively-enhanced
behaviour (accordions, error summaries, the header menu, etc.).

To use the design system in React we would have to either:

- adopt a **community React port** (e.g. `govuk-react`, `x-govuk` component sets),
  which **lag the upstream version**, aren't guaranteed to track v5.14+, and shift the
  accessibility guarantee from "GDS tested this" to "a third party approximated it and
  we hope"; or
- **re-implement GOV.UK components in React ourselves** — re-earning the WCAG /
  WAI-ARIA behaviour that `docs/agent/component_accessibility.md` requires, component
  by component, and keeping our copies in sync with upstream security/accessibility
  fixes by hand.

Either path re-litigates work that is currently *free* because we use the real thing.
Accessibility is not a nice-to-have here — the project has an explicit accessibility
standard and a `test_accessibility.py` BDD suite. Re-implementing accessible
components is exactly the kind of work a two-person team should avoid owning.

(There is a nuance in our favour: the **backoffice** is already Tailwind, *not* GOV.UK.
For backoffice-only screens the "duplicate the design system" cost is lower, because
we've already left GOV.UK there. But the public/auth/registration side is pure GOV.UK,
and that is precisely the side with the no-JS constraint below.)

### 2.4 Public pages must work without JavaScript — and this cuts deep

**Constraint:** public pages, and *especially* the registration flow
(`registration.py`, `templates/register/`), must be fully usable with JavaScript
disabled. This is not negotiable — it's an accessibility and reach requirement for
citizens' assembly registration, where we cannot assume anything about the
respondent's device.

A client-rendered SPA fails this by construction: no JS, no page. So the honest
question is whether **Next.js SSR** rescues it. Partially:

- Next.js **can** server-render HTML so the page is *visible* without JS. Good.
- But "visible" is not "works." A React form whose submission is an `onSubmit`
  handler, or whose validation is client-side, is **dead without hydration.** To be
  genuinely no-JS you must lean on **plain HTML `<form method="post">` posting to a
  route that handles it server-side** (Next.js Server Actions / route handlers, or
  posting back to Flask) — i.e. deliberately *avoid* the idiomatic React form
  patterns and practise real progressive enhancement.

That is achievable, but be honest about two things:

1. **You are swimming upstream.** The React/Next default patterns assume JS. Every
   public form and interaction has to be built the un-idiomatic way and *tested with
   JS off*, forever, or it regresses silently. The discipline cost is ongoing.
2. **We get all of this for free today.** Jinja server-rendering plus GOV.UK
   progressive enhancement means registration already works without JS with zero
   special effort. Adopting Next.js means **spending real engineering to claw back a
   property we currently have by default.**

The rational conclusion this pushes toward: if we *did* go React, we would keep the
**public/registration side as server-rendered Jinja + GOV.UK** and only introduce
React behind login. Which is to say — the no-JS constraint alone argues against a
*whole-app* rewrite, and in favour, at most, of a scoped backoffice SPA.

### 2.5 Cross-boundary plumbing we get for free today

Splitting frontend and backend means re-establishing, across an HTTP/JSON boundary,
things that are currently just function calls and Flask extensions:

- **Auth & session.** We use `flask-login` + `flask-session` in Redis. A React client
  needs an auth story across the boundary — session-cookie-with-same-origin (simplest,
  keeps httpOnly cookies) or a token scheme (more moving parts, easy to get wrong).
  OAuth flows currently rely on `SESSION_COOKIE_SAMESITE=Lax`; that interaction has to
  be preserved.
- **CSRF.** `flask-wtf` `CSRFProtect` protects forms today. A JSON API needs CSRF
  tokens threaded to the client and sent back as headers (the backoffice already does
  a bit of this by hand) — consistently, on every mutating call.
- **CSP.** Our policy is strict: `strict-dynamic` + per-request **nonce**, no
  `unsafe-eval`, no inline handlers (`docs/frontend_security.md`). Next.js *can* run
  under a nonce-based CSP, but it requires deliberate configuration, and any dependency
  that needs `eval`/`Function` is disqualified. This is a solvable-but-fiddly ongoing
  constraint, not a freebie.

### 2.6 Internationalisation has to be re-plumbed

i18n today is server-side gettext: `_()` / `_l()` in Python and Jinja, extracted to
`messages.pot`, compiled to `.po`/`.mo` (we ship a Hungarian catalogue under
`translations/hu/`), regenerated via `just translate-regen`. React can't use that.

We'd introduce a JS i18n layer (`next-intl` / `react-i18next`), which means either
**two parallel translation catalogues and extraction pipelines** (server strings via
Babel/gettext, client strings via a JS extractor) or building a shared pipeline that
feeds both. Translators now have two systems. For strings that appear on both sides
(e.g. shared validation messages) we risk drift. None of this is hard in isolation;
all of it is *more* than the single, working pipeline we have now.

### 2.7 Two deploy targets and more ops

Today: one Flask app (plus Redis/Postgres/Celery already in the picture). After: a
Node runtime for Next.js **as well**, whether as a separate service or a
backend-for-frontend in front of Flask. That's another process to run, monitor, patch,
and reason about in the CSP/session/CSRF chain. For a two-person team, ops surface is
not free.

### 2.8 Rewrite risk

However we phrase it, meaningful chunks of working, tested UI get rebuilt. Every
rewritten screen is a chance to reintroduce a bug we already fixed, or to quietly drop
an accessibility affordance the GOV.UK components gave us. The existing BDD/e2e tests
mitigate this **only** to the extent they're comprehensive — and the brief notes they
aren't exhaustive. Rewrites behind thin tests are where regressions live.

---

## 3. High-level sketch of the technical changes

If, having weighed §2, we still chose this, here is the shape of the work. The
**incremental** path is the only responsible one for a two-person team; the big-bang
path is listed only to be explicitly rejected.

### 3.1 API layer over the service layer

- Add a versioned JSON API (`/api/v1/...`) as a thin Flask blueprint (or a dedicated
  API app) that calls **existing** service-layer functions and serialises domain
  objects. Keep business logic in the service layer; the API is transport only.
- Define response schemas explicitly (Pydantic or marshmallow) and generate an
  **OpenAPI** document — that becomes the shared contract and the source for the
  frontend's TypeScript types and for contract tests. This dovetails with the existing
  `tests/contract/` layer.
- Start with the endpoints the backoffice already needs (search, respondents list,
  targets, selection status) — several already exist informally as JSON routes.

### 3.2 Auth, session, CSRF across the boundary

- **Serve the React app same-origin under Flask** (Flask serves the built assets, or a
  co-located Next server behind the same domain). Same-origin lets us keep the
  existing **httpOnly Redis session cookie** — no bearer-token custody in JS.
- Expose the CSRF token to the client (meta tag / cookie readable by JS) and send it as
  `X-CSRFToken` on every mutating request; validate with the existing `flask-wtf`
  machinery. The backoffice already does a limited version of this.
- Preserve the OAuth `SameSite=Lax` behaviour; test the OAuth round-trip explicitly.

### 3.3 SSR strategy for the no-JS public pages

- **Do not rewrite the public/registration pages in React.** Keep `templates/register/`
  and the auth pages as **Jinja + GOV.UK Frontend**, server-rendered, progressively
  enhanced. This satisfies the no-JS requirement *for free* and keeps the real,
  GDS-maintained accessible components on the highest-stakes pages.
- Confine React to **behind-login backoffice** screens, where JS can be assumed and
  where the interactivity payoff is real.
- If any public page ever genuinely needs React, use Next.js SSR with **plain
  `<form method="post">` progressive enhancement** and add an automated "JS-disabled"
  test for it. Treat that as the exception, not the rule.

### 3.4 GOV.UK component story in React

- Backoffice is already Tailwind, so React there does **not** need GOV.UK components;
  build backoffice components on the existing Tailwind design tokens (mirroring the
  current `templates/backoffice/components/`), with Storybook as the catalogue
  (replacing the hand-rolled `showcase.html`).
- Keep the public side on real GOV.UK Frontend. **Avoid** committing to a community
  GOV.UK-in-React port; if it's ever unavoidable, budget explicitly for
  accessibility re-verification against `component_accessibility.md`.

### 3.5 Build & deploy

- Reuse the existing Node toolchain — which already runs esbuild for first-party JS
  bundles (`build:js`). React needs a heavier bundler than the current single-entry
  esbuild step: adopt Next.js's build, or Vite if we choose a plain SPA-behind-login
  rather than full Next. Wire `npm run build` into the deploy so Flask serves hashed,
  CSP-nonce-compatible assets (extends the current `static_hashes` cache-busting
  approach that the esbuild `dist/` output already uses).
- If using full Next.js SSR, add the Node runtime to the deployment; otherwise a
  static SPA build served by Flask keeps deployment single-target (this is the lighter
  option and worth preferring).

### 3.6 i18n

- Introduce `next-intl`/`react-i18next` for client strings. Ideally **generate JS
  catalogues from the same gettext `.po` sources** so translators keep one workflow;
  at minimum, document the two pipelines and keep shared strings in one place.

### 3.7 Testing stack

- **Vitest + React Testing Library** for component/unit tests (assert on accessible
  roles/text).
- **MSW** for frontend contract tests against the OpenAPI schema.
- **Playwright** for e2e — extend the existing browser-test knowledge; port the highest
  value `tests/bdd/` journeys.
- Keep **Python** unit/integration/contract tests on the service layer and API.
  Net: we now maintain **two** test pyramids. That's the §2.1 cost showing up in the
  test plan.

### 3.8 Migration path — incremental, never big-bang

1. Stand up the `/api/v1` seam and OpenAPI contract with no UI change.
2. Pick **one** self-contained backoffice screen (e.g. respondent search/list) and
   build it in React, served same-origin, behind login. Prove auth/CSRF/CSP/i18n
   end-to-end on that one screen.
3. Evaluate honestly against the §2 costs **before** converting a second screen. If the
   two-person maintenance tax already bites at one screen, stop — that's real data, not
   failure.
4. Convert the genuinely interactive screens (selection config, targets, registration
   builder) one at a time. Leave simple CRUD and all public pages as Jinja + GOV.UK.
5. A **big-bang rewrite is explicitly out of scope** — it maximises rewrite risk and
   the no-JS problem simultaneously, for a team that cannot absorb either.

---

## 4. Bottom line

React/Next.js would give us a coherent answer to the backoffice's already-real
fragmentation (HTMX + Alpine + Tailwind + ad-hoc JSON), a best-in-class testing and
component ecosystem, first-class routing/bookmarks/history, and a larger hiring pool —
and the clean DDD service layer makes the required API genuinely feasible.

But it is a **second full application and stack** whose **ongoing maintenance cost lands
on two people forever**; it forces us to **re-earn the GOV.UK design system and its
accessibility** outside its native format; it puts the **no-JS registration
requirement**—which we satisfy today for free—**at risk** and makes us spend real effort
to claw it back; and it multiplies our **i18n, CSP, auth/session/CSRF, and deployment**
surface.

The most defensible version of this proposal is **not** "rewrite the app in Next.js."
It is "keep the public/GOV.UK/registration side exactly as it is, add a JSON API over
the service layer, and *consider* a scoped React SPA for the handful of genuinely
app-like backoffice screens." Even that should be entered incrementally, one screen at
a time, with an honest willingness to stop.

For a two-person team maintaining a mostly-server-rendered GOV.UK application, the
weight of §2 most likely exceeds the benefits of §1. This document makes the strongest
case for React/Next.js precisely so that, if we still say no, we're saying it with eyes
open — and if we say a *scoped* yes, we do it in the one shape that isn't reckless.
