# Frontend interactivity: the decision and the plan

**Status:** decided. We are going with **vanilla JS + Alpine.js (CSP build) + JSON
routes**, organised into real files and tested —
[vanilla-alpine-json.md](vanilla-alpine-json.md). Public pages stay
server-rendered and work with JavaScript disabled.

**If you are here to do the work, read [plan.md](plan.md).** It is the reviewed
implementation plan: what to build, in what order, what has been signed off, and
the handful of questions still parked pending a team discussion. The rest of this
folder is the reasoning that got us here — useful for understanding *why*, not
needed to start.

## What's in this folder

| Document                                             | What it is                                                                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **[plan.md](plan.md)**                               | **Start here.** The reviewed implementation plan, with decisions recorded and open items flagged.                               |
| [vanilla-alpine-json.md](vanilla-alpine-json.md)     | The option we chose. Still the best description of the shape we're aiming for.                                                  |
| [contract-style-testing.md](contract-style-testing.md) | Background research on stopping server/JS drift in JSON responses. The basis for the "API fixtures" approach in plan.md §4.    |
| [htmx-first.md](htmx-first.md)                       | Not chosen — the case for routing server round-trips through HTMX. Kept for the argument, which still applies to specific pages. |
| [react-nextjs.md](react-nextjs.md)                   | Not chosen — the case for a React/Next.js backoffice.                                                                           |

## Why this exists

The app had grown three overlapping ways to add interactivity — server-rendered
Jinja, HTMX fragments, and Alpine.js components wired to ad-hoc JSON endpoints —
and the JSON-plus-JS style had crept in without a deliberate choice behind it. We
wanted one intentional direction, chosen with the trade-offs on the table.

Three advocacy documents were written to make the **strongest honest case** for one
approach each, having read the code and docs, and each is fair about its own
downsides. They are partisan by design. They remain worth reading before
reopening the question — but the question is not currently open.

## The options as they were put

| Option | Document | One-line pitch | Its own biggest admitted weakness |
|---|---|---|---|
| **Lean into HTMX** | [htmx-first.md](htmx-first.md) | Server round-trips go through HTMX; keep Alpine only for client-only widgets; retire the JSON-plus-JS pattern. | Poor fit for rich, no-round-trip client interactivity; fragment/target-id wiring bugs are invisible to fast tests. |
| **Vanilla / Alpine + JSON** *(chosen)* | [vanilla-alpine-json.md](vanilla-alpine-json.md) | Pave the cowpath we already walk: deliberate JSON routes + Alpine (CSP build) in real files, properly tested. | Two state models to hold in sync; real CSP friction with the Alpine build. |
| **React / Next.js** | [react-nextjs.md](react-nextjs.md) | Pay the backoffice's fragmentation cost once, coherently, with a mature component/testing ecosystem. | A second full application and stack whose maintenance lands on two people forever. |

Note that choosing vanilla/Alpine + JSON does **not** retire HTMX — it stays where
it already earns its place. The decision is about where *new* interactivity goes.

## The constraints all three had to respect

These were the fixed points of the decision, not things any option got to wish
away — and they still bind the implementation. The decision changed which approach
we take, not what it has to satisfy.

- **Public pages — registration above all — must work with JavaScript disabled.**
  Internal/admin pages *may* require JS.
- **Bookmarks, back/forward, and reload must stay honest.** Working proposal:
  modals are transient and need no URL; anything someone would reasonably paste to
  a colleague needs a real, server-renderable URL.
- **Strict CSP** (`strict-dynamic` + per-request nonce, no inline handlers, no
  `eval`) — this is load-bearing for the no-cookie-banner / erasure posture and is
  not up for loosening.
- **GOV.UK design system + accessibility standard** on the public side; a separate
  Tailwind system already in the backoffice.
- **Server-side gettext i18n** (`_()` / `_l()`, `.po`/`.mo`).
- **A two-person technical team** — the scarcest resource is how many mental
  models we have to hold at once.

## Where the advocates agreed

Some conclusions recurred across all three partisan documents regardless of which
approach they argued for — which is why they survived the decision and are now
part of the plan:

- **Keep the public / registration flow server-rendered (Jinja + GOV.UK), no-JS by
  default.** Even the React advocate argued *against* rewriting it. Settled.
- **Vendor Alpine/HTMX off the jsdelivr CDN** into `static/` and serve them with our
  nonce. All three flagged the third-party CDN request as awkward against our
  privacy/supply-chain posture. Now [plan.md](plan.md) §2.
- **URL is the state store; modals are ephemeral unless URL-backed.** The
  bookmark/reload rule was common ground.
- **The two-person team size is the decisive maintainability variable** — cited as a
  point *for* HTMX and vanilla/Alpine, and as the weakness that most likely sinks
  React.
- **We had no JS unit-test runner and no eslint.** (We *do* have an esbuild
  bundler — `build:js` in `package.json`, see
  [docs/frontend_build.md](../../frontend_build.md) — so a bundler was never the
  gap.) Adding **Vitest** and **eslint/prettier** has since been signed off; see
  [plan.md](plan.md) §1 for the full dependency list and §5 for where they run in
  the `just` pipeline.

## Status of the work

The plan is reviewed and mostly signed off, but **nothing in it has been
implemented yet**. A few items are parked pending a team discussion — [plan.md](plan.md)
§11 lists exactly which, and its header calls out what must not be started. New
dependencies remain ask-first per our project rules; the ones already approved are
recorded in plan.md §1 so nobody has to re-litigate them.
