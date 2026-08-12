# Frontend Build Pipeline

OpenDLP's frontend assets are built from source by npm before the app can serve them. There is no
single all-in-one bundler; instead a few focused tools each own one kind of asset. All of them are
driven through `package.json` scripts and wrapped in `just` targets.

## The build steps

| Tool           | Source                              | Output (built)                          | npm script          |
| -------------- | ----------------------------------- | --------------------------------------- | ------------------- |
| Dart Sass      | `src/scss/`                         | `static/css/application.css`            | `build:sass`        |
| Tailwind CSS   | `static/backoffice/src/main.css`    | `static/backoffice/dist/main.css`       | `build:backoffice`  |
| esbuild        | `src/js/`                           | `static/js/`, `static/backoffice/js/`   | `build:js`          |
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

## Testing and linting JavaScript

npm also owns the JS test and lint tooling, which builds nothing but shares the same
`node_modules`:

| Tool     | npm script     | Reached through                 |
| -------- | -------------- | ------------------------------- |
| Vitest   | `test`         | `just test-js`, `just test`     |
| ESLint   | `lint`         | `just check`, via a prek hook   |
| Prettier | `format`       | `just check`, via a prek hook   |

See [agent/frontend_js_testing.md](agent/frontend_js_testing.md) for the conventions.

## Built assets are never committed

Every built artifact above is **gitignored** (the `dist/` rule, `static/css/application.css`,
`static/js/vendor/`, and the bundled `static/js/*.js` / `static/backoffice/js/*.js`).
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

**All first-party JavaScript is authored under `src/js/` and nothing under `static/` is
hand-written.** That rule has no exceptions: a hand-edited file under `static/` is silently
overwritten by the next build, and a `*.test.js` there would be publicly served, since `static/` is
web-served in its entirety.

`src/js/` is laid out by role:

| Directory            | Holds                                                                |
| -------------------- | -------------------------------------------------------------------- |
| `src/js/lib/`        | pure helpers with no Alpine or DOM-wiring dependency (`url-utils.js`) |
| `src/js/components/` | `Alpine.data()` component factories, one per file                     |
| `src/js/init/`       | Alpine magics/directives and document-level event wiring              |
| `src/js/backoffice/` | backoffice-only entry points, including the CodeMirror HTML editor    |
| `src/js/*.js`        | the entry points loaded on public pages                               |

Vitest files sit next to the code they test (`url-utils.js` / `url-utils.test.js`). A test file is
never an entry point, so it is never emitted, never copied into the Docker image and never served —
a property of where the file lives rather than a setting someone has to maintain.

esbuild bundles each entry point into an IIFE with a source map and a
`// generated from src/js/ - do not edit` banner. Bundles are loaded like any other script — with a
`nonce` and `static_hashes()` cache busting — and served from `'self'`, so they need no SRI and add
no third-party CDN dependency. This keeps the strict `'strict-dynamic'` CSP intact (esbuild output
uses no `eval`/`new Function`). `build:js` minifies; `watch:js` does not, so the browser shows
readable code while you work.

### Entry points

The entry-point list lives in `esbuild.config.mjs`, keyed by output path:

| Source                                 | Served as                                  |
| -------------------------------------- | ------------------------------------------ |
| `src/js/utilities.js`                  | `static/js/utilities.js`                   |
| `src/js/alpine-components.js`          | `static/js/alpine-components.js`           |
| `src/js/alpine-scroll-manager.js`      | `static/js/alpine-scroll-manager.js`       |
| `src/js/htmx-422-swap.js`              | `static/js/htmx-422-swap.js`               |
| `src/js/backoffice/alpine-components.js` | `static/backoffice/js/alpine-components.js` |
| `src/js/backoffice/html-editor.js`     | `static/backoffice/js/dist/html-editor.js` |
| `src/js/backoffice/patterns.js`        | `static/backoffice/js/patterns.js`         |
| `src/js/backoffice/registration-page.js` | `static/backoffice/js/registration-page.js` |
| `src/js/backoffice/service-docs.js`    | `static/backoffice/js/service-docs.js`     |

To add a bundle: write the entry under `src/js/`, add a line to `ENTRY_POINTS` in
`esbuild.config.mjs`, and load the built path in the template. Both `build:js` and `watch:js` read
that one list, so there is no second place to update.

The last three are **page-specific** entry points, loaded from their own page's `{% block head %}`
rather than from the shared backoffice bundle, so their components do not ship to every backoffice
page. Reach for one when a component belongs to a single page.

A component big enough to want splitting up gets a directory of its own under
`src/js/components/` — `service-docs/` is one file per tab plus a `core.js` they all call
through, and a `controller.js` that merges them. Prefer that to ten files loose in
`components/`, which is meant to read as a list of components rather than of fragments.

### Passing server data to a bundle

A bundled component cannot be rendered through Jinja, so anything only the server knows —
`url_for` routes, the CSRF token, translated strings, seeded data — has to be handed across
explicitly. Two ways, and the choice is about size and trust:

**A few short, trusted values: an `x-data` argument.**

```html
<div x-data="urlSelect({ baseUrl: '{{ url_for('backoffice.view_assembly_data', assembly_id=assembly.id) }}' })">
```

**Anything larger, or anything a user wrote: a JSON data block**, read with `readJsonScript()`
from `src/js/lib/json-script.js`. `templates/backoffice/assembly_registration.html` is the worked
example.

```html
{% set page_data = {"csrfToken": csrf_token(), "images": images, "messages": {...}} %}
<script type="application/json" id="registration-page-data" nonce="{{ csp_nonce }}">{{ page_data|tojson }}</script>
```

```javascript
Alpine.data("registrationPageController", function () {
  return registrationPageController(readJsonScript("registration-page-data"));
});
```

Why the block wins once user input is involved: an organiser writes the image alt text, so a quote
or a `</script>` in a display name would otherwise break the page. `|tojson` escapes `<`, `>`, `&`
and `'`, once, for every value — rather than each one being trusted not to need it. It also keeps
the reading of the configuration in the entry point, leaving the component a plain function of its
options and so testable without a DOM.

Note that `type="application/json"` is not executable, so it is not a CSP inline-script violation
and does not undo the "no inline script" rule.

**Translated strings must come from the template**, whichever way you choose. `babel.cfg` extracts
from `**.py` and `templates/**.html` only, so a string written in a `.js` file is never translated.

### Run `just watch-js` while editing JavaScript

Watch mode rebuilds on every save and then touches
`src/opendlp/entrypoints/flask_app.py`, which restarts Flask. That restart matters:
`static_hashes()` is `@cache`d, so without it a running dev server keeps serving the old
cache-busting URL and the change appears not to have taken effect.

```bash
just watch-js         # alongside watch-css / watch-backoffice
```
