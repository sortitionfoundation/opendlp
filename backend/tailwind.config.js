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
  // Class names built by string concat in Jinja macros never appear as
  // literals in scanned templates, so Tailwind's content-scanner purges
  // their @layer components rules. Safelist keeps them in the output.
  safelist: [
    "btn--primary",
    "btn--secondary",
    "btn--tertiary",
    "btn--danger",
    "btn--icon",
    // Added by ProseMirror to the selected image in the visual editor.
    "ProseMirror-selectednode",
    // Added by Tiptap's table extension to cells selected across in the visual editor.
    "selectedCell",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
