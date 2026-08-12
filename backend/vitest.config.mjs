// ABOUTME: Vitest configuration for the frontend JavaScript unit tests
// ABOUTME: Runs the tests colocated in src/js in a jsdom environment

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/js/**/*.test.js"],
    globals: false,
  },
});
