// ABOUTME: Tests for the human-readable byte size formatter
// ABOUTME: Pins the unit boundaries and the non-numeric fallback

import { describe, expect, it } from "vitest";

import { formatBytes } from "./format-bytes.js";

describe("formatBytes", () => {
  it("reports whole bytes below a kilobyte", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("switches to kilobytes at 1024 bytes", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("switches to megabytes at a megabyte", () => {
    expect(formatBytes(1024 * 1024)).toBe("1.00 MB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.00 MB");
  });

  it("returns an empty string for anything that is not a finite number", () => {
    expect(formatBytes(undefined)).toBe("");
    expect(formatBytes(null)).toBe("");
    expect(formatBytes(NaN)).toBe("");
    expect(formatBytes(Infinity)).toBe("");
  });
});
