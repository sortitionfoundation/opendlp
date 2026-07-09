# Frontend Build Pipeline

OpenDLP's frontend assets are built from source by npm before the app can serve them. There is no
single all-in-one bundler; instead three focused tools each own one kind of asset. All of them are
driven through `package.json` scripts and wrapped in `just` targets.

## The three tools

| Tool           | Source                              | Output (built)                          | npm script          |
| -------------- | ----------------------------------- | --------------------------------------- | ------------------- |
| Dart Sass      | `src/scss/`                         | `static/css/application.css`            | `build:sass`        |
| Tailwind CSS   | `static/backoffice/src/main.css`    | `static/backoffice/dist/main.css`       | `build:backoffice`  |
| esbuild        | `static/backoffice/js/src/`         | `static/backoffice/js/dist/`            | `build:js`          |

`npm run build` runs all three. Each tool also has a `watch:*` script for rebuilding on change.

## Built assets are never committed

Every built artifact above is **gitignored** (the `dist/` rule and `static/css/application.css`).
Built output is regenerated wherever the app is assembled:

- **Local dev:** `just run` runs `just build-all` first; `just install` runs `npm run build`.
- **Docker:** the build stage runs `npm install` then `npm run build`.
- **CI:** the `setup-python-env` composite action runs `npm install` then `npm run build`, so both
  the quality/test job and the BDD job have freshly built assets.

Because nothing built is committed, a missing build step shows up as absent CSS/JS at runtime rather
than a merge conflict — if a page looks unstyled or a JS enhancement doesn't run, build the assets.

## `just` targets

```bash
just build-all        # CSS + JS (npm run build)
just build-all-css    # GOV.UK + backoffice CSS
just build-css        # GOV.UK CSS only
just build-backoffice # backoffice Tailwind CSS only
just build-js         # esbuild JS bundles only
just watch-css        # or watch-backoffice / watch-js
just run              # build-all, then run Flask
```

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
