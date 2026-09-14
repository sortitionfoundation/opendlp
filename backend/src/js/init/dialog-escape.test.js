// ABOUTME: Unit tests for the Escape-key close of fragment dialogs
// ABOUTME: Covers the no-dialog case, single dialog, and topmost-of-several

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { initDialogEscape } from "./dialog-escape.js";

function pressEscape() {
  const event = new KeyboardEvent("keydown", {
    key: "Escape",
    cancelable: true,
  });
  window.dispatchEvent(event);
  return event;
}

describe("initDialogEscape", () => {
  // One shared window per test file, so register the listener exactly once.
  beforeAll(() => {
    initDialogEscape();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("does nothing when no dialog is open", () => {
    const event = pressEscape();

    expect(event.defaultPrevented).toBe(false);
  });

  it("clicks the backdrop of the open dialog", () => {
    document.body.innerHTML =
      '<a class="dialog-backdrop dialog-backdrop--clickable" href="#close"></a>';
    const backdrop = document.querySelector("a.dialog-backdrop--clickable");
    const clicked = vi.fn();
    backdrop.addEventListener("click", (e) => {
      e.preventDefault();
      clicked();
    });

    const event = pressEscape();

    expect(clicked).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it("closes only the topmost dialog when two are stacked", () => {
    document.body.innerHTML =
      '<a id="first" class="dialog-backdrop--clickable" href="#a"></a>' +
      '<a id="second" class="dialog-backdrop--clickable" href="#b"></a>';
    const first = vi.fn();
    const second = vi.fn();
    document.getElementById("first").addEventListener("click", (e) => {
      e.preventDefault();
      first();
    });
    document.getElementById("second").addEventListener("click", (e) => {
      e.preventDefault();
      second();
    });

    pressEscape();

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });

  it("ignores other keys", () => {
    document.body.innerHTML =
      '<a class="dialog-backdrop--clickable" href="#close"></a>';
    const clicked = vi.fn();
    document.querySelector("a").addEventListener("click", (e) => {
      e.preventDefault();
      clicked();
    });

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));

    expect(clicked).not.toHaveBeenCalled();
  });
});
