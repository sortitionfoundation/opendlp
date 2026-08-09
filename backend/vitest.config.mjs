// ABOUTME: Vitest configuration for the frontend JavaScript unit tests
// ABOUTME: Runs tests/js in a jsdom environment so DOM-touching code can be tested

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/js/**/*.test.js"],
    globals: false,
  },
});
