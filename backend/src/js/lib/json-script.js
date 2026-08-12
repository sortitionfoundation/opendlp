// ABOUTME: Reads a server-rendered <script type="application/json"> configuration block
// ABOUTME: How a page hands URLs, CSRF tokens and translated strings to a bundled component

/**
 * Parse the JSON data block with the given id.
 *
 * This is how a template passes server-side values - `url_for` URLs, the CSRF
 * token, translated strings, seeded data - to a component that lives in a
 * bundled file and so cannot be rendered through Jinja. A data block keeps the
 * values out of an HTML attribute, where a quote in a display name would break
 * the page.
 *
 * A missing or malformed block yields an empty object rather than throwing, so
 * one bad value cannot take the whole page's interactivity down with it.
 *
 * @param {string} id - the id of the script element
 * @returns {Object} the parsed configuration, or {} if it could not be read
 */
export function readJsonScript(id) {
  const element = document.getElementById(id);
  if (!element) return {};

  try {
    return JSON.parse(element.textContent);
  } catch (err) {
    console.error('Could not parse the JSON data block "' + id + '"', err);
    return {};
  }
}
