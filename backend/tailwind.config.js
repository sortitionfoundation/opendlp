/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // Only scan design-system templates (backoffice + migrated public pages) -
    // keep GOV.UK templates separate
    "./templates/backoffice/**/*.html",
    // The visual editor sets its own class names on the editing area.
    "./src/js/backoffice/rich-editor*.js",
    "./templates/public/**/*.html",
  ],
  // NB: Tailwind v4 dropped the JS `safelist` key. The class names built by
  // string concat in Jinja macros (btn--*, and the editor's runtime-only
  // ProseMirror-selectednode / selectedCell) are now kept via an
  // `@source inline(...)` directive in static/backoffice/src/main.css.
  theme: {
    extend: {},
  },
  plugins: [],
};
