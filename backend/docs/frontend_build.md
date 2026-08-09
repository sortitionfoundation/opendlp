# Frontend Build Pipeline

OpenDLP's frontend assets are built from source by npm before the app can serve them. There is no
single all-in-one bundler; instead a few focused tools each own one kind of asset. All of them are
driven through `package.json` scripts and wrapped in `just` targets.

## The build steps

| Tool           | Source                              | Output (built)                          | npm script          |
| -------------- | ----------------------------------- | --------------------------------------- | ------------------- |
| Dart Sass      | `src/scss/`                         | `static/css/application.css`            | `build:sass`        |
| Tailwind CSS   | `static/backoffice/src/main.css`    | `static/backoffice/dist/main.css`       | `build:backoffice`  |
| esbuild        | `static/backoffice/js/src/`         | `static/backoffice/js/dist/`            | `build:js`          |
| vendor copy    | `node_modules/`                     | `static/js/vendor/`                     | `build:vendor`      |

`npm run build` runs all of them. The first three also have a `watch:*` script for rebuilding on
change; the vendor copy has none, because its sources only change when a dependency is upgraded.

## Third-party JavaScript is vendored, not loaded from a CDN

Alpine (CSP build), htmx and govuk-frontend are npm dependencies. `build:vendor` copies their
prebuilt bundles out of `node_modules/` into `static/js/vendor/`:

| npm package        | Copied from                                    | Served as                        |
| ------------------ | ---------------------------------------------- | -------------------------------- |
| `@alpinejs/csp`    | `dist/cdn.min.js`                              | `js/vendor/alpine-csp.js`        |
| `htmx.org`         | `dist/htmx.min.js`                             | `js/vendor/htmx.js`              |
| `govuk-frontend`   | `dist/govuk/all.bundle.js`                     | `js/vendor/govuk-frontend.js`    |

They are already built, so nothing bundles or minifies them — the step is a plain copy. Templates
load them like any other static file, with a `nonce` and `static_hashes()` cache busting. Serving
them from `'self'` removes a third-party request from every page load and takes jsdelivr out of our
supply chain; it also means the tags need no SRI hash, since there is no third party to pin.

Upgrading one of these libraries is therefore an `npm add` and a rebuild — there is no version
number embedded in a template to keep in sync.

## Built assets are never committed

Every built artifact above is **gitignored** (the `dist/` rule, `static/css/application.css`, and
`static/js/vendor/`).
Built output is regenerated wherever the app is assembled:

- **Local dev:** `just run` runs `just build-all` first; `just install` runs `npm run build`.
- **Docker:** the build stage runs `npm install` then `npm run build`.
- **CI:** the `setup-python-env` composite action runs `npm install` then `npm run build`, so both
  the quality/test job and the BDD job have freshly built assets.

Because nothing built is committed, a missing build step shows up as absent CSS/JS at runtime rather
than a merge conflict — if a page looks unstyled or a JS enhancement doesn't run, build the assets.

## `just` targets

```bash
just build-all        # CSS + JS + vendored JS
just build-all-css    # GOV.UK + backoffice CSS
just build-css        # GOV.UK CSS only
just build-backoffice # backoffice Tailwind CSS only
just build-js         # esbuild JS bundles only
just build-vendor     # copy vendored third-party JS only
just watch-css        # or watch-backoffice / watch-js
just run              # build-all, then run Flask
```

A new build step must be wired into **both** entry points to run everywhere: append it to the
`build` npm script (which is what Docker, CI and `just install` invoke) and give it a `just` recipe
that `build-all` depends on (which is what `just run` and the test targets invoke). Miss one and the
asset is silently absent in half the environments.

## JavaScript: authored ES modules → bundled IIFE

First-party JavaScript that pulls in npm packages is authored as ES modules under
`static/backoffice/js/src/` and bundled by esbuild into a single minified IIFE under
`static/backoffice/js/dist/` (with a source map). The bundle is loaded like any other script — with
a `nonce` and `static_hashes()` cache busting — and served from `'self'`, so it needs no SRI and
adds no third-party CDN dependency. This keeps the strict `'strict-dynamic'` CSP intact (esbuild
output uses no `eval`/`new Function`).

The first consumer is the CodeMirror 6 HTML editor (`html-editor.js`), which progressively enhances
any `textarea[data-code-editor]` into a syntax-highlighted, auto-indenting editor. Existing plain
global scripts under `static/js/` and `static/backoffice/js/` continue to be loaded directly and can
migrate onto the bundler over time.

To add a new bundle: create the entry under `static/backoffice/js/src/`, add matching `build:js` /
`watch:js` esbuild invocations (or extend the existing ones) in `package.json`, and load the built
file from `static/backoffice/js/dist/` in the template.
