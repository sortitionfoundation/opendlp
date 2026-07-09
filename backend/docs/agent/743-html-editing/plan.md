<!--
ABOUTME: Plan for adding syntax highlighting + auto-indent to the HTML-editing textareas
ABOUTME: Covers editor choice, CSP implications, integration approach, and decisions log
-->

# 743 — Syntax highlighting & auto-indent for the HTML-editing textareas

**Status:** Decisions recorded (§6). Editor = **CodeMirror 6**; build path = **Path 1, adopt esbuild
as a JS bundler** (§3a chosen). Detailed build/infra plan in **§7**. Not yet implementing.
**Author:** Claude

## 1. What we want

Add **syntax highlighting** and **auto-indent** to the textareas where organisers hand-write
HTML. These are currently plain `<textarea>` elements styled with a monospace font.

Target textareas (both in `templates/backoffice/assembly_registration.html`):

| Field name           | Section           | Content type | Notes                                |
| -------------------- | ----------------- | ------------ | ------------------------------------ |
| `html_content`       | Registration form | HTML         | `rows=25`, readonly unless `?edit=1` |
| `template_body_html` | Auto-reply email  | Jinja + HTML | `rows=18`, readonly unless `?edit=1` |

There is also a **read-only** skeleton-preview `<textarea>` in the "Form Skeleton" modal
(`x-ref="skeletonTextarea"`) — **decision: this gets read-only highlighting too** (Q6).

Both editable textareas share a pattern worth preserving:

- They live inside a normal `<form method="post">` and are submitted by name. Any editor we add
  **must keep the underlying `<textarea>` in sync** so the existing POST handler is untouched.
- They are `readonly` by default and only editable when the page is in `edit_mode`
  (the `?edit=1` query param / "Edit" CTA). **Decision: we highlight in both view and edit modes** (Q4).
- The email one contains Jinja (`{{ respondent.first_name }}`) mixed into HTML.

## 2. The constraints that actually drive the decision

Read from the frontend security docs and the real CSP config in
`src/opendlp/entrypoints/flask_app.py` (`get_secure_headers`). Load-bearing facts:

1. **Strict CSP, no `unsafe-eval`.** `script-src` is `'self' 'nonce-…' 'strict-dynamic'
https://cdn.jsdelivr.net`. With `'strict-dynamic'` the `cdn.jsdelivr.net` allowlist is _ignored_;
   scripts are trusted by **nonce** (+ SRI `integrity`) and anything they load in turn. There is **no
   `unsafe-eval`**, so any editor that calls `eval()`/`new Function()` at runtime is out.
   → CM6 is clean here (no eval).
2. **Inline styles are allowed.** `style-src` includes `'unsafe-inline'`, so editors that inject
   `<style>`/inline styles are fine.
3. **`worker-src` is not set** → falls back to `script-src`, which does not permit `blob:`. Not an
   issue for CM6 (no worker needed). **Decision: we do NOT change the CSP** (Q2).
4. **No JavaScript bundler in the repo.** Build tooling is the `sass` CLI and the `tailwindcss` CLI
   only. Third-party JS today (Alpine CSP build, htmx, govuk-frontend) is loaded as **single-file
   bundles from jsdelivr** with `nonce` + `integrity`. This is the crux of the §3a sub-decision.
5. **No dark mode.** `static/backoffice/tokens/semantic.css` is a single light `:root` token set.
   The editor needs **one** light theme mapped to the tokens. No dynamic theme-switching.
6. **i18n.** Editors have essentially no visible chrome text. Any _new_ buttons/labels we add go
   through `_()` / `_l()`.

## 3. Editor decision: CodeMirror 6 (Q1)

CM6 it is — modern, actively maintained, CSP-clean by design (no `eval`, no worker). It gives real
HTML language support (auto-indent, close-tags, bracket matching) and read-only via
`EditorState.readOnly` / `EditorView.editable.of(false)`.

_Alternatives considered and rejected for this work: Ace (older architecture — but see the honest
note in §3a), CodeMirror 5 (legacy/sunset track), Monaco (multi-MB, worker-heavy, awkward under
strict CSP). Full pros/cons preserved in git history of this file._

### 3a. How we obtain the CM6 build — **resolved: Path 1 (esbuild)**

Your answers were **B1 (use a prebuilt bundle)** + **load from jsdelivr with SRI (Q3)** + **read-only
highlighting in view mode and in the skeleton modal (Q4, Q6)**. Researching the actual artifacts
turned up a conflict: **those three answers can't all be satisfied by the prebuilt bundle.**

What I found about the community prebuilt
[`paul-norman/codemirror6-prebuilt`](https://github.com/paul-norman/codemirror6-prebuilt):

- It's **GitHub-only — not on npm, with no releases and no version tags.** Via jsdelivr you'd have to
  pin to a raw commit SHA (`cdn.jsdelivr.net/gh/paul-norman/codemirror6-prebuilt@<sha>/dist/html.min.js`)
  and hand-generate the SRI hash. Low usage, unclear maintenance — a shaky thing to pin a
  security-sensitive backoffice editor to.
- Its documented options are `dark`, `placeholder`, `focus`, `lineWrapping` — **no read-only /
  non-editable option.** Read-only would require rebuilding it ourselves with the extra extension,
  which defeats the "just use the prebuilt" premise. This directly blocks Q4 and Q6.

So there is **no maintained, versioned, SRI-pinnable CM6 prebuilt on jsdelivr that also supports
read-only.** CM6 is deliberately not shipped as one drop-in UMD file; the supported way to get an
IIFE with the extensions we need is to build it. That forces a choice between four paths.

**Path 1 — Adopt a real JS bundler as project infrastructure (recommended).**
You've flagged that the front-end JS is slowly growing, and the numbers back that up: there's already
**~43 KB of hand-written first-party JS across 6 files** (`static/backoffice/js/alpine-components.js`
is 24 KB on its own), all authored as plain global scripts with **no ES-module `import`/`export`**.
A bundler (I'd reach for **esbuild** for its speed and one-line config; Rollup/Vite are the heavier
alternatives) turns real `@codemirror/*` npm packages — pinned in `package.json` — into a single
minified `static/backoffice/js/dist/*.js`, served from `'self'` with `static_hashes()` cache-busting.
CM6 becomes its **first consumer**, and the existing/growing JS can migrate onto it incrementally.

- ✅ Read-only works (`EditorState.readOnly`) → satisfies Q4 + Q6; CM6 is clean under our CSP.
- ✅ Real, pinned, auditable versions via npm; no third-party CDN dependency; tree-shaking, source
  maps, and modern ES-module authoring for _all_ future JS, not just the editor.
- ✅ Fits the existing precedent — we already run `npx tailwindcss` and `sass` as build steps; this
  adds a sibling `build:js` step and `just` targets alongside them.
- ⚠️ Real infrastructure cost: a new build step contributors must run (or CI must run), a bundler
  config to own, and a migration path for the current global-script JS. Bigger than this feature —
  but you've been heading here anyway, and this is the clean moment to do it.
- ⚠️ Departs from your Q3 "jsdelivr" answer: bundled output is self-hosted from `'self'`, so SRI is
  moot (same-origin) and `static_hashes()` handles cache-busting.

**Path 2 — Minimal one-off CM6 build, no broader bundler adoption.**
Same mechanics as Path 1 but scoped tightly: a single `npx esbuild` invocation that produces just the
CM6 bundle, with none of the existing JS migrated and no commitment to bundling as a general practice.

- ✅ Gets us CM6 + read-only now with the least ceremony.
- ⚠️ Half-measure if we're going to adopt a bundler anyway — we'd likely redo the wiring in Path 1
  later. Really only preferable if you want to defer the infra decision.

**Path 3 — Reconsider Ace after all (no build step at all).**
Ace loads as a classic script from **jsdelivr with real versions + SRI** (exactly your Q3 answer),
needs **no build step**, and supports **read-only natively** — cleanly satisfying Q2, Q3, Q4, Q6, Q7.
It only loses "modern CM6". Flagging it honestly as the zero-infrastructure option rather than quietly
overriding you.

**Path 4 — Use the `paul-norman` prebuilt as originally chosen.**
Only viable if we **drop the read-only requirement** (reverting Q4 + Q6) and accept an unversioned,
low-usage GitHub dependency pinned by commit SHA. **I'd advise against this** for a security-sensitive
admin surface.

**DECISION (Chewie): Path 1 — adopt esbuild as a JS bundler**, with CM6 as its first consumer. This
meets every recorded decision except the literal "jsdelivr" wording of Q3 — the bundled artifact is
self-hosted from `'self'` (arguably better for a bundled artifact; SRI moot at same-origin). Existing
first-party JS is **not** migrated in this ticket — the pipeline is established and the six current
global scripts migrate onto it lazily later. The full build/infra plan is **§7**.

## 4. Integration approach

Progressive enhancement, so the form keeps working even if JS fails:

1. **Keep the `<textarea>`.** Initialise the editor over it and mirror content back into the textarea
   on every change (and on `submit`). The POST handlers (`save_assembly_registration` /
   `save_assembly_registration_email`) stay untouched.
2. **Highlight in both view and edit modes (Q4).** In `edit_mode` the editor is editable; otherwise it
   mounts **read-only** (`EditorState.readOnly` for CM6 / `setReadOnly(true)` for Ace) so viewers get
   highlighting without being able to type. Same treatment for the **skeleton-preview modal**
   textarea (Q6), which is always read-only.
3. **Reusable macro flag (Q7).** Add an opt-in `code_editor=false` parameter to the shared `textarea`
   macro in `templates/backoffice/components/input.html`. **Default off**; when `true` it adds a
   `data-code-editor` attribute (and language hint) that the initialiser hooks. Future HTML fields opt
   in without bespoke wiring. The three target textareas set `code_editor=true`.
4. **No inline handlers.** The initialiser finds `[data-code-editor]` elements on load and mounts
   editors — consistent with the CSP "no inline handlers" rule.
5. **Where the code lives.** A small external initialiser `static/backoffice/js/html-editor.js`, loaded
   with `nonce` + `static_hashes()` via the `{% block head %}` in `backoffice/base.html` (or a
   page-scoped block). The editor library loads per the §3a path we choose (self-hosted `'self'` from
   a bundle for Paths 1–2, jsdelivr + SRI for Path 3/Ace).
6. **Theme** to match `semantic.css` tokens — a single light theme (§2.5).
7. **Jinja (Q5).** For the email template, treating `{{ … }}` as plain text inside HTML highlighting is
   **acceptable** — Jinja-aware highlighting is a _nice-to-have, not required_. We ship plain HTML
   highlighting first; a mixed-mode parser can come later if wanted.
8. **Accessibility.** Per the component-accessibility rules: keyboard-reachable, accessible label tied
   to the field, visible focus indicator, and a sane Tab story (code editors capture Tab for indent —
   provide an Escape-then-Tab escape hatch or documented key to leave the editor). Verify with
   keyboard-only + screen reader.

## 5. Testing

- **BDD/e2e (Playwright, `CI=true`):** load the registration form at `?edit=1`, assert the editor
  mounts, type HTML, submit, and confirm the posted `html_content` round-trips. Repeat for the email
  template. Confirm the read-only view mounts a **non-editable** highlighted editor, and the skeleton
  modal shows highlighted read-only content.
- **CSP regression (main risk):** load the page and assert **zero CSP violations** in the console.
  For Path 3 (Ace), verify the jsdelivr URL carries a correct `integrity` hash.
- **No-JS fallback:** with JS disabled the plain textarea still submits (progressive enhancement).
- **Keyboard/AT smoke test** per the accessibility checklist above.

## 6. Decisions log (from review)

| #   | Question                                | Decision                                                                                                                                                                                    |
| --- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Which editor?                           | **CodeMirror 6**, obtained via **Path 1 — adopt esbuild** (§3a resolved). Prebuilt rejected (no read-only, unversioned). Build plan in §7.                                                  |
| Q2  | Change the CSP?                         | **No.** No CSP change; skip Ace's worker-based validation.                                                                                                                                  |
| Q3  | Vendor vs jsdelivr+SRI?                 | Superseded by the Path 1 decision: CM6 is **bundled by esbuild and self-hosted from `'self'`** (SRI moot at same-origin; `static_hashes()` cache-busts). No third-party CDN for the editor. |
| Q4  | Read-only view: enhance or leave plain? | **Enhance both** view and edit modes. (This is what rules out the read-only-less prebuilt.)                                                                                                 |
| Q5  | Jinja highlighting?                     | **Nice-to-have, not required.** Ship plain HTML highlighting; Jinja-aware later if wanted.                                                                                                  |
| Q6  | Skeleton-preview modal textarea?        | **Add read-only highlighting.**                                                                                                                                                             |
| Q7  | Reusable macro?                         | **Add `code_editor` to the `textarea` macro, default off.**                                                                                                                                 |

**Resolved since review:** editor build path = **Path 1 (esbuild)**; existing JS **not** migrated in
this ticket. Minor implementation details (exact CM6 package set / light-theme mapping) are settled in
§7 and don't need a further decision. The plan is now build-ready pending your sign-off on §7.

## 7. Implementation plan (Path 1 — esbuild bundler)

The guiding principle: the JS pipeline should look like a **sibling of the existing SCSS/Tailwind
pipeline**, not a new kind of thing. Same shape (npm script → `just` target → runs in Docker via
`npm run build`), same output convention (built artifact under a gitignored `dist/`, loaded with
`nonce` + `static_hashes()`).

### 7.1 Source layout & the CM6 bundle

- **New source dir** `static/backoffice/js/src/` for ES-module source (authored, committed).
- **Entry point** `static/backoffice/js/src/html-editor.js` — imports CM6 from npm and _is_ the
  initialiser (finds `[data-code-editor]` elements and mounts editors; no global export needed).
  CM6 packages to add to `package.json` `dependencies` (real, pinned versions):
  - `codemirror` (provides `basicSetup`), `@codemirror/state`, `@codemirror/view`,
    `@codemirror/commands` (for `history` + `indentWithTab`), `@codemirror/lang-html`.
  - A **light theme** built with `EditorView.theme(...)` mapped to `semantic.css` tokens (§2.5) —
    no third-party theme package needed. Read-only via `EditorState.readOnly.of(true)` +
    `EditorView.editable.of(false)` when not in `edit_mode`.
- **Built output** `static/backoffice/js/dist/html-editor.js` (+ `.map`). Under `dist/`, so it is
  **already covered by the existing `dist/` `.gitignore` rule** (verified with `git check-ignore`) —
  matches how `static/backoffice/dist/main.css` and `static/css/application.css` are handled: built,
  never committed. **Do not commit the bundle.**

### 7.2 `package.json`

- Add **`esbuild`** to `devDependencies` (pin a version; esbuild ships per-platform binaries via
  optionalDependencies — `npm install` resolves the right one in the linux image, see 7.4).
- Add scripts, mirroring the sass/tailwind pair:
  ```jsonc
  "build:js":  "esbuild static/backoffice/js/src/html-editor.js --bundle --minify --format=iife --sourcemap --outfile=static/backoffice/js/dist/html-editor.js",
  "watch:js":  "esbuild static/backoffice/js/src/html-editor.js --bundle --sourcemap --format=iife --outfile=static/backoffice/js/dist/html-editor.js --watch",
  ```
- **Fold into the umbrella `build` script** so every existing build path (Docker, `just setup`) picks
  it up for free:
  ```jsonc
  "build": "npm run build:sass && npm run build:backoffice && npm run build:js"
  ```

### 7.3 `justfile`

Add JS targets as siblings of the CSS ones, and introduce the `build-all` umbrella you suggested:

- `build-js:` → `@npm run build:js`
- `watch-js:` → `@npm run watch:js`
- **`build-all: build-all-css build-js`** — one command covering CSS (GOV.UK + backoffice) **and** JS.
- Change **`run: build-all flask`** (currently `run: build-all-css flask`) so local dev always has a
  fresh bundle.
- `setup` already runs `npm install` + the CSS builds; add `@npm run build:js` (or simplest: switch
  those three lines to a single `@npm run build`).

### 7.4 `Dockerfile`

Good news — **the Docker build already runs `npm install` (line ~78) and `npm run build` (line ~85)**
with `node`/`npm` present, then copies `/src/static` into the image. Because 7.2 folds `build:js`
into the `build` script, **the JS bundle builds in Docker automatically with no structural change.**

- Verify esbuild lands in the image: the Dockerfile uses plain `npm install` (not `--production`), so
  `devDependencies` (esbuild) _are_ installed — good. Confirm the platform-specific esbuild binary
  resolves for `linux` inside the image (it will via optionalDependencies; call it out in review).
- The esbuild entry/source is copied in via the existing `COPY . /src`, so nothing extra to copy.
- **Cosmetic:** update the Dockerfile comment that says _"/src/static/ now contains files generated by
  `npm run build:sass`"_ to mention the JS bundle too.

### 7.5 `static_hashes` / template wiring

- **No context-processor change needed.** `static_hashes()` (`context_processors.py:145`) hashes the
  file **on demand** from its path — it does _not_ require pre-registration. (This corrects the
  CLAUDE.md note about "a new JS file needs a new hash in the context processor"; worth fixing that
  line while we're here.)

- Load the initialiser on the registration page (scoped, not global) with nonce + cache-busting:
  ```html
  <script
    nonce="{{ csp_nonce }}"
    src="{{ url_for('static', filename='backoffice/js/dist/html-editor.js',
                          v=static_hashes('backoffice/js/dist/html-editor.js')) }}"
  ></script>
  ```

### 7.6 Application wiring (detail for §4)

- `templates/backoffice/components/input.html` — add `code_editor=false` param to the `textarea`
  macro; when true, emit `data-code-editor` (+ a `data-language="html"` hint). Default off (Q7).
- `templates/backoffice/assembly_registration.html` — set `code_editor=true` on `html_content` and
  `template_body_html`; add `data-code-editor` to the skeleton-modal textarea (Q6). The initialiser
  mounts editable vs read-only from a `data-` flag derived from `edit_mode` (Q4).
- Keep the underlying `<textarea>` and sync on input + submit (§4.1) so POST handlers are untouched.

### 7.7 Docs to update (your third bullet)

- **`docs/agent/frontend_design_system.md`** → "Build Pipeline": add the JS/esbuild step next to
  `build:sass`/`build:backoffice`; document `just build-js` / `just watch-js` / `just build-all`.
- **`docs/frontend_security.md`** → "Adding JavaScript" + "Cache Busting": note that new first-party
  JS is now authored as **ES modules in `static/backoffice/js/src/`**, bundled to `dist/`, and loaded
  with `nonce` + `static_hashes()`; and correct the "needs a new hash in the context processor" line.
- **New doc `docs/frontend_build.md`** (recommended): a single page describing the whole asset
  pipeline now that it's three tools (Dart Sass → GOV.UK CSS, Tailwind → backoffice CSS, esbuild → JS),
  where sources live, where built artifacts go, and that all built assets are gitignored + built in
  Docker/CI/`just setup`. Link it from `CLAUDE.md`.
- **`CLAUDE.md`** (project) → "Development Commands": mention `just build-all` and the JS build; fix
  the stale `static_hashes` note (7.5).

### 7.8 CI / BDD asset build (do not miss)

The BDD server target `run-for-bdd` starts Flask **without building assets**, and the editor e2e test
needs the bundle present. Action: ensure the JS bundle is built before BDD/e2e runs — either the CI
job runs `just setup` / `npm run build` first, or add a build step to the BDD bootstrap. Verify the
CI workflow builds frontend assets (the workflow grep showed no explicit `npm run build`, so this may
already rely on `just setup` — confirm during implementation).

### 7.9 Rollout order (suggested)

1. ✅ **Done** — esbuild + scripts (7.2), justfile targets (7.3), Dockerfile comment (7.4), and the
   full CM6 initialiser bundle (7.1) building via `just build-all`. `just check` green.
2. ✅ **Done** — initialiser: read-only vs editable, textarea sync, light theme, accessibility (§4)
   (implemented up-front in step 1's `html-editor.js` rather than as a separate pass).
3. ✅ **Done** — macro flag + template wiring for all three textareas (7.6).
4. ✅ **Done** — docs (7.7: frontend_build.md added, design-system + security docs updated, AGENTS.md
   linked) and CI/BDD build step (7.8: `setup-python-env` action now runs `npm run build`, so the JS
   bundle is built before BDD).
5. ✅ **Done** — tests (§5): component assertions + a BDD editor-mount scenario, **all executed and
   passing**: 63/63 backoffice BDD scenarios (incl. the new editor mount in real Chromium against
   Postgres/Redis), 19 e2e+component registration tests, 584 component tests. Only `docker` is
   unavailable in the sandbox, so the Dockerfile build path (§7.4) still wants a real `docker build`
   to confirm esbuild's linux binary resolves.

## Sources

- [CodeMirror 6 prebuilt bundles (GitHub-only, no npm/releases, no read-only option)](https://github.com/paul-norman/codemirror6-prebuilt)
- [CodeMirror official bundling example (CM6 is not a single UMD file — build your own IIFE)](https://codemirror.net/examples/bundle/)
- [CM6 read-only via EditorState.readOnly / EditorView.editable](https://codemirror.net/docs/ref/#state.EditorState%5EreadOnly)
- [Ace `useWorker` / CSP worker note (why Ace needs no CSP change with worker off)](https://github.com/ajaxorg/ace/issues/3637)
- [Monaco vs strict CSP issues (why Monaco was ruled out)](https://github.com/keycloak/keycloak/issues/32901)
