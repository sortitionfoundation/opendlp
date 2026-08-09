// ABOUTME: ESLint flat config for OpenDLP's first-party JavaScript
// ABOUTME: Covers file-based JS quality only - CSP-Alpine attribute rules are a review check

import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      "static/js/vendor/**",
      "static/**/dist/**",
      "static/css/**",
      "htmlcov/**",
      ".venv/**",
      // read-only checkouts of other repos, not ours to lint
      "thirdparty/**",
      "scratchpad/**",
    ],
  },
  js.configs.recommended,
  {
    // Files under static/ are served as classic scripts, not modules: their
    // top-level declarations are deliberately globals shared between files.
    files: ["static/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        Alpine: "readonly",
        htmx: "readonly",
      },
    },
    rules: {
      // several handlers swallow an exception deliberately; whether that is
      // justified is a review question, not something the linter can judge
      "no-unused-vars": ["error", { caughtErrors: "none" }],
    },
  },
  {
    files: ["static/backoffice/js/src/**/*.js"],
    languageOptions: {
      sourceType: "module",
    },
  },
  {
    files: ["tests/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
  },
  {
    files: ["*.config.js", "*.config.mjs", "tailwind.config.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
  },
  {
    files: ["tailwind.config.js"],
    languageOptions: {
      sourceType: "commonjs",
    },
  },
];
