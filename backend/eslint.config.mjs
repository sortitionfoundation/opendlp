// ABOUTME: ESLint flat config for OpenDLP's first-party JavaScript
// ABOUTME: Covers file-based JS quality only - CSP-Alpine attribute rules are a review check

import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      // everything under static/ is build output - see src/js/
      "static/**",
      "htmlcov/**",
      ".venv/**",
      // read-only checkouts of other repos, not ours to lint
      "thirdparty/**",
      "scratchpad/**",
    ],
  },
  js.configs.recommended,
  {
    files: ["src/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
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
    files: ["src/js/**/*.test.js"],
    languageOptions: {
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
