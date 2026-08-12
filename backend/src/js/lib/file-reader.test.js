// ABOUTME: Tests for reading a chosen file as base64
// ABOUTME: Covers the data-URL prefix strip, an empty choice, and a read that fails

import { describe, expect, it } from "vitest";

import { readFileAsBase64 } from "./file-reader.js";

describe("readFileAsBase64", () => {
  it("resolves with the payload, without the data-URL prefix the reader adds", async () => {
    const file = new File(["hello"], "greeting.txt", { type: "text/plain" });

    const base64 = await readFileAsBase64(file);

    expect(base64).toBe(btoa("hello"));
  });

  it("round-trips bytes that are not valid text", async () => {
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x00, 0xff]);
    const file = new File([bytes], "logo.png", { type: "image/png" });

    const base64 = await readFileAsBase64(file);

    expect(Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))).toEqual(
      bytes,
    );
  });

  it("resolves empty when there is no file, so callers need no null check", async () => {
    expect(await readFileAsBase64(null)).toBe("");
    expect(await readFileAsBase64(undefined)).toBe("");
  });

  it("rejects when the file cannot be read, so the caller can say so", async () => {
    // A Blob the reader will refuse: FileReader rejects a detached/unreadable source.
    const unreadable = {
      // Not a Blob at all - readAsDataURL raises synchronously on the wrong type.
      name: "broken",
    };

    await expect(readFileAsBase64(unreadable)).rejects.toBeDefined();
  });
});
