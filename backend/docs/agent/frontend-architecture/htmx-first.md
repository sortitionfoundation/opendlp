# Lean into HTMX for OpenDLP's frontend interactivity

**Status:** proposal / advocacy. Author: exploring agent. Audience: the two of us.

## TL;DR

We already have three ways to add interactivity to a page — server-rendered
Jinja, HTMX fragments, and Alpine components wired to JSON endpoints — and the
third one is the expensive one. This document argues we should **standardise on
HTMX for anything that talks to the server**, keep Alpine only for genuinely
client-only widgets, and delete the ad-hoc "JSON endpoint + JS that stitches
JSON into the DOM" pattern wherever it has crept in. The `targets` blueprint and
the `json-to-htmx` spike branch already show what the good version looks like;
this is mostly about committing to it and cleaning up the rest.

## What I actually found in the code

A quick inventory, because the argument rests on it:

- **HTMX is already a dependency** (`htmx.org@2.0.7`, loaded in both
  `templates/base.html` and `templates/backoffice/base.html`) with one small
  local helper, `static/js/htmx-422-swap.js`, that makes HTMX swap `422`
  validation responses.
- **The `targets` blueprint is the reference pattern.** Forms carry *both* a
  plain `action`/`method="post"` *and* `hx-post`, e.g.
  `templates/backoffice/targets/add_category_form.html`. The route
  (`src/opendlp/entrypoints/blueprints/targets.py`) branches on a one-line
  `_is_htmx()` header check: HTMX requests get an HTML *fragment* back
  (optionally with an `HX-Trigger` header like `categoriesChanged`), everything
  else gets a `redirect` + `flash`. Validation failures return the fragment with
  status `422`. This works with JavaScript switched off.
- **Alpine is used broadly but shallowly.** There are ~82 `x-data` occurrences
  across templates, but `static/js/alpine-components.js` is 9 lines with a single
  `teamSelector`. In other words, most Alpine is inline UI state (modal
  open/close, tabs, dropdowns) — cheap. The costly Alpine is where it fetches
  JSON and re-templates it on the client.
- **JSON endpoints have crept in** (registration "form skeleton", image
  modals, export flows), each paired with hand-written client JS. The
  `json-to-htmx` branch is a worked example of removing them: its commit
  messages describe replacing a `jsonify` GET endpoint with a `-modal` endpoint
  that renders a fragment, dropping the Alpine state and the `jsonify` import,
  and migrating the tests. The branch's net diff is heavily negative
  (thousands of lines deleted) — that deletion is the point.
- **A strict CSP (`strict-dynamic`, nonces, no inline handlers, no `eval`)**
  already caps how much client-side JS we can sanely run. We even run the
  *CSP build* of Alpine, which forbids arrow functions, template literals,
  destructuring, and `console`/`Math`. Heavy client-side JS is swimming against
  this current; HTMX swims with it.
- **Only one test tier runs a browser.** `tests/component/` (Flask client over a
  fake UoW, no Postgres/Redis) and `tests/e2e/` (Flask client over real
  infra) both assert on **server-rendered HTML**. Only `tests/bdd/` drives a real
  browser via Playwright. The migration direction in memory and on the spike
  branch is *away* from heavy e2e toward fast component tests.

That last point is the crux of the testing argument, so let me take the four
required considerations in turn.

## 1. Testing

**HTMX fares unusually well here, because an HTMX endpoint is just a route that
returns HTML.**

- **Unit / component / e2e (fast, no browser):** Our component tier drives the
  *real* Flask routes and services over a fake UoW and asserts on the returned
  markup. An HTMX interaction — "add a category", "open the export modal",
  "rename inline" — is a normal request whose response is a fragment we can
  assert on directly: does it contain the new row, does it return `422` with the
  error text, does it set `HX-Trigger`? All of that is testable in milliseconds
  without a browser. This is exactly the tier we're trying to grow.
- **The JSON+JS alternative is only fully testable in a browser.** When the
  behaviour lives in client JS that fetches JSON and builds DOM, the fast tiers
  can only test the JSON contract; whether the UI actually updates correctly is
  invisible until a Playwright test runs it. Browser tests are our slowest and
  sparsest tier ("not exhaustive"). HTMX moves logic from the untested-fast side
  to the tested-fast side.
- **BDD/Playwright still has a job — a smaller, sharper one.** HTMX's failure
  modes are wiring errors: an `hx-target="#foo"` pointing at an id that no longer
  exists, a swap that lands in the wrong place. Those are invisible to
  fragment-level tests because both the endpoint and the page render fine in
  isolation. So we keep a **thin layer of browser smoke tests** that a key swap
  actually happens end-to-end. Net effect: fewer, more valuable browser tests,
  more coverage in the fast tiers.

Honest caveat: testing server-rendered fragments means testing *markup*, which
can be brittle if assertions over-fit exact HTML. Convention (assert on stable
ids / visible text / roles, not on class soup) keeps this manageable — and it's
the same discipline our accessibility rules already push us toward.

## 2. Maintainability and the two-person mental model

For a two-person team, **the scarcest resource is the number of mental models we
have to hold at once.** Today an interactive feature can span: a Jinja template,
an Alpine component (inline or in `alpine-components.js`), a JSON route, a
serialisation shape, and the JS that maps JSON back into DOM — plus the CSP
constraints on all of the JS. That's a lot of surface for two people to keep
correct.

HTMX-first collapses that to: **a route that returns HTML, and a template.** The
state of truth is the server and the DOM it renders; there is no parallel
client-side model of the data to keep in sync. The behaviour you read in the
template (`hx-post`, `hx-target`, `hx-swap`) is local and declarative — you can
see what a control does without opening a JS file. That "you can hold the whole
feature in your head" property is worth a lot when the team is small and context
-switches are frequent.

It also matches where our competence and our infrastructure already are: we're a
Flask/Jinja/DDD shop with a rich service layer. HTMX lets the service layer and
Jinja keep doing the work; it doesn't ask us to also become a front-end app team.

The cost side (see §3 and §4) is real: more, smaller template fragments to name
and keep in order, and a mild mental shift to "think in hypermedia." But that's a
*shallower* learning curve than a client-state framework, and it's boring
technology — exactly the kind we said we prefer.

## 3. The no-JS constraint and progressive enhancement

**Requirement:** public pages — above all the registration form — must *work*
without JavaScript. Internal admin pages *may* require JS.

This is where HTMX is not just acceptable but genuinely the right tool, because
**HTMX is progressive enhancement by construction.** The page is real HTML that
works on its own; HTMX intercepts and upgrades it.

- The **public registration form** (`templates/register/form.html`) already
  contains zero `hx-`, `x-data`, `fetch`, or `<script>`. It is a plain server
  -rendered form. An HTMX-first policy *protects* this: HTMX is only ever added
  as enhancement on top of working HTML, so the no-JS guarantee is the default,
  not a thing we have to remember to preserve.
- The **`targets` forms** show the enhancement pattern for pages that do use
  HTMX: `action` + `method="post"` for the browser, `hx-post` for HTMX. JS off →
  a normal POST, a redirect, a flash. JS on → an in-place fragment swap. Same
  route, same validation, two renderings. We should make this dual-attribute
  form the *house style*, not an exception.
- Contrast with the JSON+JS approach, where "no JS" means "no feature." A JSON
  endpoint is not a fallback; you have to build the server-rendered version
  *separately* and keep both alive. HTMX gives you one code path that degrades.

A framing that helps: **public pages = enhancement must be optional; admin
pages = enhancement may be assumed.** HTMX serves both from the same technique —
you simply choose whether to also provide the `action` fallback. For public
flows you always do; for deep admin interactions you may skip it. Nothing about
the approach forces JS onto the public where we've forbidden it.

## 4. Bookmarks, back/forward, and reloadability

This is the area to be most honest about, because it's where "just use HTMX"
hand-waves past real limitations.

The core tension: HTMX can change what's on screen *without changing the URL*. If
you do that and the user reloads or hits back, the swapped-in state is gone.
HTMX offers `hx-push-url` and a history mechanism, but they have sharp edges.

Our proposed rule handles most of it cleanly:

- **Modals are transient and deliberately have no URL.** Opening a modal should
  *not* push history. If you reload, you get the underlying page — which is the
  correct and expected behaviour for a modal. Back/forward should step through
  *pages*, not through "modal open / modal closed." This is a feature, not a
  gap: not pushing a URL is exactly right here.
- **The spike already gives modals a no-JS *and* reloadable story without
  abusing history.** The registration modals use a link that is both an
  `hx-get` (fragment into a shared `#image-modal-container`) *and* a plain
  `href` to the same URL; the server renders the full page *with the modal
  already open* when it gets a normal GET (via a `?modal=…` query parameter). So:
  JS on → smooth in-place modal, no history entry; JS off → a real navigation to
  a page that shows the modal. If you *want* a given modal to be
  bookmarkable/reloadable, that mechanism is right there — you give it a real URL
  and let the full-page render own it.
- **Where a "modal" is really a view, give it a real route.** A respondent
  detail, say, that people link to and reload is not a transient modal — it's a
  page (or a panel behind `hx-push-url` that the server can also render on a cold
  GET). The test is simple: *would someone reasonably paste this URL to a
  colleague?* If yes, it needs a permanent URL and a full-page render; if no, a
  URL-less transient swap is correct.

The honest limitations of HTMX history, stated plainly:

- `hx-push-url="true"` updates the address bar, but **restore-on-back only works
  if the URL also renders that state on a full GET.** Push a URL whose server
  route doesn't reproduce the swapped content and back/forward will show stale
  or wrong markup. Push-url is a promise you must keep on the server.
- HTMX snapshots swapped content into `localStorage` to make back/forward feel
  instant. That cache can be **stale** and has size limits; for anything
  sensitive we'd rather it re-fetch. It's tunable (`htmx.config.refreshOnHistoryMiss`,
  disabling history snapshotting per element) but it *is* another behaviour to
  understand.
- Content swapped **without** `hx-push-url` is invisible to the back button.
  That's what we want for modals and inline edits — but it's a foot-gun if
  someone swaps in a whole "screen" and forgets the URL. Hence the rule:
  screen-level navigation pushes a URL and is server-renderable; everything
  smaller does not.

Bottom line: with the "transient swaps don't touch the URL, screen changes get a
real server-renderable URL" discipline, HTMX gives us correct reload/back
behaviour. It does not give it to us *for free* — we have to keep the push-url
promise on the server — but that's a rule, not a rewrite.

## Where HTMX is genuinely the wrong tool (the fair part)

I don't want to oversell this. HTMX is a poor fit for:

- **Rich client-side interactivity with no server round-trip:** drag-and-drop
  reordering, live client-side filtering/sorting of an already-loaded table,
  canvas/drawing, instant keystroke-level feedback. Round-tripping these to the
  server is laggy and chatty. These want real client JS.
- **Complex multi-step client state** (wizards that hold a lot of unsaved state,
  optimistic UI, offline). HTMX has no client data model, by design.
- **Latency-sensitive or high-frequency interactions.** Every HTMX action is a
  request. On our internal admin over a decent connection this is fine; for a
  twitchy public widget it can feel sluggish.
- **The mental shift is real.** "Think in hypermedia — the server returns the new
  state of a piece of the page" is unfamiliar if you've been building SPAs, and
  it pushes complexity into *template fragmentation*: lots of small partials,
  each needing a stable root id that matches its `hx-target`. Misname one and
  you get a silent runtime "target not found" that the fast tests won't catch.
- **Fragment tests are markup tests.** As noted, brittle if undisciplined.

The good news is these exceptions are **islands**, and HTMX + Alpine coexist
happily. The policy isn't "delete all JS" — it's "server round-trips go through
HTMX; keep Alpine (CSP build) for genuinely client-only widgets." Our costly
Alpine today is mostly the JSON-fetching kind, which HTMX replaces; the cheap
Alpine (open/close, tabs) can stay exactly as it is.

Note also we are *not* choosing HTMX over an SPA in a vacuum — the strict CSP,
the two-person team, and the DDD/Jinja codebase already make a heavy SPA an
uphill fight. HTMX is the option that fits the constraints we already have, not
a bet against a realistic React future.

## High-level sketch of the changes

Nothing here is a big-bang rewrite; it's a direction plus cleanup. Roughly in
order:

**Conventions to write down (cheap, do first)**

1. **Promote `_is_htmx()` to a shared helper.** It's currently duplicated in
   `targets.py` and `targets_legacy.py`. One `is_htmx()` in a shared
   entrypoints util, used everywhere.
2. **House style for interactive forms:** always carry both `action`/`method`
   *and* `hx-*`. Public flows must keep the plain fallback; admin flows may
   omit it only when a JS requirement is acceptable and documented.
3. **Fragment template convention:** partials live next to their page (e.g.
   `<area>/components/…` or `_partial.html`), and **each fragment has a single
   stable root element whose id is the `hx-target`.** Document that the id is a
   contract.
4. **Response conventions:** `422` for validation fragments (the existing
   `htmx-422-swap.js` already supports this); `HX-Trigger` for "something
   changed, refresh siblings" events; `HX-Redirect` for server-driven
   navigation (already used in `gsheets_legacy.py`).

**Modals**

5. Adopt the spike's pattern as standard: a shared per-page modal container
   (`#…-modal-container`), links that are both `hx-get` and `href`, and a route
   that renders the fragment for HTMX and the **full page with the modal open**
   (via a `?modal=…` query param) for a cold GET. Transient modals push no URL;
   promote to a real route only when the content is bookmark-worthy.

**Retiring JSON + JS**

6. Convert JSON endpoints to fragment endpoints, following the `json-to-htmx`
   branch: replace `jsonify` responses with `render_template` of a partial,
   delete the client JS that mapped JSON→DOM, delete the Alpine state that held
   the fetched data, migrate the tests to assert on the fragment. Land the
   `json-to-htmx` work (or re-derive it) as the first tranche.
7. Leave client-only Alpine alone. Only remove Alpine where it exists to fetch
   and re-template server data.

**Testing conventions**

8. Test fragment endpoints at the **component tier** (fake-UoW Flask client):
   assert response contains the expected ids/visible text, returns `422` with
   error text on invalid input, sets the expected `HX-Trigger`.
9. Keep a **thin BDD/Playwright smoke layer** for the handful of "the swap
   actually wires up in a browser" checks — this is where target-id typos get
   caught.

**Libraries / dependencies — flag before adding (per our rules)**

10. **No new runtime library is required.** Flask + Jinja render fragments
    natively; `is_htmx()` is a one-liner. I'd *avoid* adding `Flask-HTMX` or
    HTMX extension packages unless a concrete need appears — please treat any
    such addition as an ask-first decision.
11. **One thing I'd raise for permission:** we currently load HTMX (and Alpine)
    from `cdn.jsdelivr.net`. That's a third-party request on every page, which
    sits awkwardly with our no-third-party-script / erasure posture in
    `docs/personal-data.md`. I'd propose **vendoring `htmx.min.js` into
    `static/js/`** and serving it with our nonce + cache-busting like our other
    assets. It's not strictly part of "HTMX-first," but adopting HTMX more
    widely raises the stakes of that CDN dependency. We now have the mechanism
    for this: the esbuild step (`build:js` in `package.json`, see
    [docs/frontend_build.md](../../frontend_build.md)) already bundles
    first-party JS from `static/backoffice/js/src/` into a self-hosted, nonce'd,
    `static_hashes()`-busted IIFE under `dist/`, so vendoring a third-party lib
    fits an established pattern. (CSP-wise HTMX 2 is fine under `strict-dynamic`
    as long as we avoid `hx-on`/`js:` eval-style features.)

**i18n and accessibility** stay exactly as they are: fragments are Jinja, so
`_()` / `_l()` work unchanged, and because fragments are server-rendered we keep
full control over ARIA and semantic markup (the modal partials already carry
`role="dialog"`, `aria-modal`, labelled titles). Nothing about HTMX-first
weakens the GOV.UK/accessibility story — if anything it centralises markup on the
server where our accessibility rules already live.

## Recommendation

Commit to **HTMX for server-touching interactivity, Alpine islands for
client-only widgets, and no more JSON-endpoint-plus-JS.** Write down the
conventions above, land the `json-to-htmx` cleanup as the first tranche, vendor
HTMX off the CDN, and keep a thin browser-smoke layer on top of a growing
fast-fragment test tier. It fits our team size, our CSP, our test architecture,
and our no-JS-on-public-pages constraint better than the alternatives — and it
mostly means doing more of what the `targets` blueprint already does well.
