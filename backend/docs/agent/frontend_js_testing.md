# Frontend JavaScript Testing

How we test and lint first-party JavaScript. For browser-level debugging of a running
page see [frontend_testing.md](frontend_testing.md); for the Python test tiers see
[../testing.md](../testing.md).

## The tools

| Tool     | Runs                        | Invoked by                          |
| -------- | --------------------------- | ----------------------------------- |
| Vitest   | `src/js/**/*.test.js`       | `just test-js`, and `just test`     |
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

Next to the code they test, under `src/js/` - `lib/url-utils.js` and `lib/url-utils.test.js`
are siblings.

That works because no test file is an esbuild entry point, so none is ever emitted into
`static/`, copied into the Docker image, or served. It is a property of the layout rather
than a rule someone has to maintain - which matters here, because everything under `static/`
is served to the web in its entirety.

See [../frontend_build.md](../frontend_build.md) for the `lib/` / `components/` / `init/`
split and the entry-point list.

## Testing a component

Source files are ES modules, so a test just imports them. `Alpine.data()` components are
plain factory functions returning the component state, which means a test can call the
factory and drive the returned object directly - no Alpine instance, no DOM mounting:

```javascript
import { modal } from "./modal.js";

const state = modal({ initialOpen: true, canClose: false });
state.close();
expect(state.isOpen).toBe(true);
```

The entry points under `src/js/` do the `Alpine.data(...)` registration and nothing else, so
there is no behaviour hiding in the part that is awkward to test.

Components that touch the DOM get a real one - the Vitest environment is jsdom. Components
that navigate need `window.location` replaced, since jsdom's is not writable:

```javascript
delete window.location;
window.location = { href: "https://example.org/start", reload: vi.fn() };
```

## What ESLint does and does not cover

ESLint checks the quality of `.js` files. It does **not** check CSP-Alpine compliance.

Those are different things. CSP-Alpine forbids arrow functions, template literals and string
arguments to handlers *in Alpine expressions inside HTML attributes*. In an external `.js`
file all of those are perfectly legal and ESLint will rightly say nothing. A green lint run
therefore tells you nothing about whether an `x-data` attribute will work under our CSP.

That check stays manual: follow the patterns in `templates/backoffice/patterns.html` (live at
`/backoffice/dev/patterns`) and see [../frontend_security.md](../frontend_security.md).

## Adding a test

1. Create `<name>.test.js` next to `<name>.js` under `src/js/`.
2. Import from Vitest explicitly - `globals` is off, so there is no ambient `describe`/`it`.
3. Run `just test-js`.

Anything with non-trivial logic - debouncing, state transitions, URL building, parsing -
should have one. Wiring that only makes sense against a real browser belongs in the BDD tier
instead.
