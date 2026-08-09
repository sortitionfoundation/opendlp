# Frontend JavaScript Testing

How we test and lint first-party JavaScript. For browser-level debugging of a running
page see [frontend_testing.md](frontend_testing.md); for the Python test tiers see
[../testing.md](../testing.md).

## The tools

| Tool     | Runs                        | Invoked by                          |
| -------- | --------------------------- | ----------------------------------- |
| Vitest   | `tests/js/**/*.test.js`     | `just test-js`, and `just test`     |
| ESLint   | first-party `.js`/`.mjs`    | `just check` (via a prek hook)      |
| Prettier | first-party `.js`/`.mjs`    | `just check` (via a prek hook)      |

The split is deliberate: **`just test` runs tests, `just check` runs static analysis.**
Vitest is wired in as a dependency of the pytest targets so it runs *first* - a broken JS
test fails in a couple of seconds rather than after the ten-minute Python suite. ESLint and
Prettier live in the prek config rather than as bespoke `just check` lines, so they also run
at commit time.

The prek hooks call the npm scripts (`npm --prefix backend run lint`), so the tool versions
are the ones pinned in `package.json` - there is no second copy installed at a version that
can drift.

## Where tests live

`tests/js/`, mirroring the Python tests rather than sitting next to the source.

The reason is specific to this repo: everything under `static/` is served to the web, so a
colocated `foo.test.js` would be publicly fetchable unless Flask's static handling learned
to exclude it. Keeping tests outside `static/` avoids the question entirely.

## Testing a classic global script

Most of `static/js/` is loaded as plain `<script src>` - classic scripts whose top-level
functions are deliberately globals shared between files. They cannot use `export` without
changing how they are loaded, so `tests/js/support/load-global-script.js` evaluates the file
and returns the declarations you ask for:

```javascript
import { loadGlobalScript } from "./support/load-global-script.js";

const { urlSetParam } = loadGlobalScript("js/url-utils.js", ["urlSetParam"]);
```

This tests the file exactly as it ships. New code extracted from templates should instead be
an `Alpine.data()` component or a module under `lib/`, which can be imported normally.

Because the globals are shared across files, ESLint needs to be told about them: the file
that declares them carries `/* exported name1, name2 */`, and files that use them carry
`/* global name1 */`. Those comments are load-bearing, not decoration.

## What ESLint does and does not cover

ESLint checks the quality of `.js` files. It does **not** check CSP-Alpine compliance.

Those are different things. CSP-Alpine forbids arrow functions, template literals and string
arguments to handlers *in Alpine expressions inside HTML attributes*. In an external `.js`
file all of those are perfectly legal and ESLint will rightly say nothing. A green lint run
therefore tells you nothing about whether an `x-data` attribute will work under our CSP.

That check stays manual: follow the patterns in `templates/backoffice/patterns.html` (live at
`/backoffice/dev/patterns`) and see [../frontend_security.md](../frontend_security.md).

## Adding a test

1. Create `tests/js/<name>.test.js`.
2. Import from Vitest explicitly - `globals` is off, so there is no ambient `describe`/`it`.
3. Run `just test-js`.

Anything with non-trivial logic - debouncing, state transitions, URL building, parsing -
should have one. Wiring that only makes sense against a real browser belongs in the BDD tier
instead.
