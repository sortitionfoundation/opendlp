// ABOUTME: Unit tests for the clipboard helpers
// ABOUTME: Covers writing an HTML snippet as both HTML and source text, and the text-only fallback

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { writeHtmlToClipboard } from "./clipboard.js";

const SNIPPET = '<img src="/register/x/images/a.png" alt="A logo">';

class FakeClipboardItem {
  constructor(items) {
    this.items = items;
  }
}

let write;
let writeText;

beforeEach(() => {
  write = vi.fn().mockResolvedValue(undefined);
  writeText = vi.fn().mockResolvedValue(undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("writeHtmlToClipboard", () => {
  it("writes the snippet as HTML and as its source text", async () => {
    vi.stubGlobal("ClipboardItem", FakeClipboardItem);
    vi.stubGlobal("navigator", { clipboard: { write, writeText } });

    await writeHtmlToClipboard(SNIPPET);

    expect(writeText).not.toHaveBeenCalled();
    const [items] = write.mock.calls[0];
    expect(items).toHaveLength(1);
    const { "text/html": html, "text/plain": plain } = items[0].items;
    expect(html.type).toBe("text/html");
    expect(await html.text()).toBe(SNIPPET);
    expect(plain.type).toBe("text/plain");
    expect(await plain.text()).toBe(SNIPPET);
  });

  it("copies the source text where the browser can't write HTML", async () => {
    vi.stubGlobal("ClipboardItem", undefined);
    vi.stubGlobal("navigator", { clipboard: { write, writeText } });

    await writeHtmlToClipboard(SNIPPET);

    expect(write).not.toHaveBeenCalled();
    expect(writeText).toHaveBeenCalledWith(SNIPPET);
  });

  it("passes on a refusal from the browser", async () => {
    vi.stubGlobal("ClipboardItem", FakeClipboardItem);
    write.mockRejectedValue(new Error("Denied"));
    vi.stubGlobal("navigator", { clipboard: { write, writeText } });

    await expect(writeHtmlToClipboard(SNIPPET)).rejects.toThrow("Denied");
  });
});
