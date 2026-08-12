// ABOUTME: esbuild entry-point list and build/watch driver for the first-party JavaScript
// ABOUTME: Bundles src/js/ into static/ - nothing under static/ is hand-written

import { utimes } from "node:fs/promises";
import esbuild from "esbuild";

// Output path (relative to static/, without .js) -> source entry point.
// The output paths are the ones the templates already reference, so adding an
// entry here is all that is needed to ship a new script.
const ENTRY_POINTS = {
  "js/utilities": "src/js/utilities.js",
  "js/alpine-components": "src/js/alpine-components.js",
  "js/alpine-scroll-manager": "src/js/alpine-scroll-manager.js",
  "js/htmx-422-swap": "src/js/htmx-422-swap.js",
  "backoffice/js/alpine-components": "src/js/backoffice/alpine-components.js",
  "backoffice/js/patterns": "src/js/backoffice/patterns.js",
  "backoffice/js/registration-page": "src/js/backoffice/registration-page.js",
  "backoffice/js/service-docs": "src/js/backoffice/service-docs.js",
  "backoffice/js/dist/html-editor": "src/js/backoffice/html-editor.js",
};

// Flask caches static file hashes for cache-busting, so it has to be bounced
// after a rebuild or the browser keeps the old URL. The build recipes in the
// justfile do this too; watch mode needs it after every rebuild.
const FLASK_APP = "src/opendlp/entrypoints/flask_app.py";

async function touchFlaskApp() {
  const now = new Date();
  await utimes(FLASK_APP, now, now);
}

const bounceFlaskPlugin = {
  name: "bounce-flask",
  setup(build) {
    build.onEnd(async (result) => {
      if (result.errors.length === 0) {
        await touchFlaskApp();
      }
    });
  },
};

const watch = process.argv.includes("--watch");

const options = {
  entryPoints: ENTRY_POINTS,
  bundle: true,
  format: "iife",
  sourcemap: true,
  outdir: "static",
  banner: { js: "// generated from src/js/ - do not edit" },
  minify: !watch,
  logLevel: "info",
};

if (watch) {
  const context = await esbuild.context({
    ...options,
    plugins: [bounceFlaskPlugin],
  });
  await context.watch();
} else {
  await esbuild.build(options);
}
