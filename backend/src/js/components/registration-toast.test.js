// ABOUTME: Tests for the toast slice of the registration page controller
// ABOUTME: Covers the auto-dismiss timing and the data-attribute copy button

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registrationToast } from "./registration-toast.js";

const MESSAGES = {
  copied: "Copied to clipboard",
  copyFailed: "Failed to copy to clipboard",
};

function copyButton(text, message) {
  const button = document.createElement("button");
  if (text !== null) button.dataset.copyText = text;
  if (message) button.dataset.copyMsg = message;
  return button;
}

describe("showToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts hidden", () => {
    expect(registrationToast(MESSAGES).toastVisible).toBe(false);
  });

  it("shows the message and its type", () => {
    const state = registrationToast(MESSAGES);

    state.showToast("Image uploaded", "success");

    expect(state.toastVisible).toBe(true);
    expect(state.toastMessage).toBe("Image uploaded");
    expect(state.toastType).toBe("success");
  });

  it("hides itself after three seconds", () => {
    const state = registrationToast(MESSAGES);
    state.showToast("Image uploaded", "success");

    vi.advanceTimersByTime(2999);
    expect(state.toastVisible).toBe(true);

    vi.advanceTimersByTime(1);
    expect(state.toastVisible).toBe(false);
  });

  it("lets an earlier toast's timer cut a later one short", () => {
    // Not a design decision, just what the page has always done: showToast does
    // not cancel the pending timer, so a toast raised 2s after another is hidden
    // 1s later rather than after its own 3s. Pinned as-is because this migration
    // is an extraction - changing it is a separate, deliberate call.
    const state = registrationToast(MESSAGES);
    state.showToast("Image uploaded", "success");

    vi.advanceTimersByTime(2000);
    state.showToast("Image deleted", "success");
    vi.advanceTimersByTime(1000);

    expect(state.toastMessage).toBe("Image deleted");
    expect(state.toastVisible).toBe(false);
  });
});

describe("copyToClipboard", () => {
  let writeText;

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText: writeText } });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("copies the text held on the triggering element", async () => {
    const state = registrationToast(MESSAGES);

    await state.copyToClipboard(copyButton("image.png", ""));

    expect(writeText).toHaveBeenCalledWith("image.png");
  });

  it("confirms with the message the element names", async () => {
    const state = registrationToast(MESSAGES);

    await state.copyToClipboard(copyButton("image.png", "File name copied"));

    expect(state.toastMessage).toBe("File name copied");
    expect(state.toastType).toBe("success");
  });

  it("falls back to the generic confirmation when the element names none", async () => {
    const state = registrationToast(MESSAGES);

    await state.copyToClipboard(copyButton("image.png", ""));

    expect(state.toastMessage).toBe("Copied to clipboard");
  });

  it("does nothing at all when there is no text to copy", async () => {
    const state = registrationToast(MESSAGES);

    await state.copyToClipboard(copyButton(null, ""));

    expect(writeText).not.toHaveBeenCalled();
    expect(state.toastVisible).toBe(false);
  });

  it("reports a clipboard the browser refused", async () => {
    writeText.mockRejectedValue(new Error("Denied"));
    const state = registrationToast(MESSAGES);

    await state.copyToClipboard(copyButton("image.png", ""));

    expect(state.toastMessage).toBe("Failed to copy to clipboard");
    expect(state.toastType).toBe("error");
  });
});
