# Frontend interactivity: architecture options

**Status:** open decision. This folder collects the material for choosing how
OpenDLP adds web-UI interactivity going forward. It does not record a decision —
that is still ours to make.

## Why this exists

The app has grown three overlapping ways to add interactivity — server-rendered
Jinja, HTMX fragments, and Alpine.js components wired to ad-hoc JSON endpoints —
and the JSON-plus-JS style has crept in without a deliberate choice behind it. We
want one intentional direction, chosen with the trade-offs on the table.

Three advocacy documents follow. Each was written to make the **strongest honest
case** for one approach, having read the code and docs, and each is fair about its
own downsides. They are partisan by design — read all three before deciding.

## The options

| Option | Document | One-line pitch | Its own biggest admitted weakness |
|---|---|---|---|
| **Lean into HTMX** | [htmx-first.md](htmx-first.md) | Server round-trips go through HTMX; keep Alpine only for client-only widgets; retire the JSON-plus-JS pattern. | Poor fit for rich, no-round-trip client interactivity; fragment/target-id wiring bugs are invisible to fast tests. |
| **Vanilla / Alpine + JSON** | [vanilla-alpine-json.md](vanilla-alpine-json.md) | Pave the cowpath we already walk: deliberate JSON routes + Alpine (CSP build) in real files, properly tested. | Two state models to hold in sync; real CSP friction with the Alpine build. |
| **React / Next.js** | [react-nextjs.md](react-nextjs.md) | Pay the backoffice's fragmentation cost once, coherently, with a mature component/testing ecosystem. | A second full application and stack whose maintenance lands on two people forever. |

## The constraints all three had to respect

These are the fixed points of the decision, not things any option gets to wish away:

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

## Where the advocates actually agree

Reading across three partisan documents, some conclusions recur regardless of which
approach they argue for — which makes them worth weighting:

- **Keep the public / registration flow server-rendered (Jinja + GOV.UK), no-JS by
  default.** Even the React advocate argues *against* rewriting it. This looks
  settled whichever direction we pick.
- **Vendor Alpine/HTMX off the jsdelivr CDN** into `static/` and serve them with our
  nonce. All three flag the third-party CDN request as awkward against our
  privacy/supply-chain posture.
- **URL is the state store; modals are ephemeral unless URL-backed.** The
  bookmark/reload rule is common ground.
- **The two-person team size is the decisive maintainability variable** — cited as a
  point *for* HTMX and vanilla/Alpine, and as the weakness that most likely sinks
  React.
- **We currently have no JS unit-test runner and no eslint.** (We *do* have an
  esbuild bundler — `build:js` in `package.json`, see
  [docs/frontend_build.md](../../frontend_build.md) — so a bundler is no longer a
  gap.) Any option that pushes logic into client JS implies adding JS testing
  (Vitest et al.), which needs an explicit decision.

## How to read these

The differences that actually separate the options are: how much client-side state
we take on, how much of our logic lands in the fast (no-browser) test tier versus a
browser tier, and how much new stack we agree to maintain. Weigh those against the
constraints above. Nothing here should be executed before we agree a direction —
and any new dependency (Flask-HTMX, Vitest, eslint/prettier, esbuild, React/Next)
is an ask-first decision per our project rules.
