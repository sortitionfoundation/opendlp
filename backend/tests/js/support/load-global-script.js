// ABOUTME: Test helper for loading OpenDLP's plain global JavaScript files
// ABOUTME: Evaluates a classic script and hands back the globals it declares

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const staticDir = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../static",
);

/**
 * Load a script from static/ that declares globals rather than exporting them.
 *
 * Files under static/ are served to the browser as classic scripts, so they
 * cannot use `export` without changing how they are loaded. This evaluates one
 * and returns the named declarations, letting it be tested as it actually ships.
 *
 * @param {string} relativePath - path to the script, relative to static/
 * @param {string[]} names - names declared by the script to return
 * @returns {Object} the named declarations, keyed by name
 */
export function loadGlobalScript(relativePath, names) {
  const source = readFileSync(resolve(staticDir, relativePath), "utf8");
  const factory = new Function(`${source}\nreturn { ${names.join(", ")} };`);
  return factory();
}
