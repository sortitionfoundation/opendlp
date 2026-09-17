// ABOUTME: Unit tests for the document-level action handlers
// ABOUTME: Covers data-confirm, including clicks that land on an element inside the confirming one

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { initDocumentActions } from "./document-actions.js";

function click(element) {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true });
  element.dispatchEvent(event);
  return event;
}

describe("initDocumentActions data-confirm", () => {
  // One shared window per test file, so register the listeners exactly once.
  beforeAll(() => {
    initDocumentActions();
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("asks before acting and cancels the click when declined", () => {
    document.body.innerHTML =
      '<button data-confirm="Unlink it?">Unlink</button>';
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    const event = click(document.querySelector("button"));

    expect(confirmSpy).toHaveBeenCalledWith("Unlink it?");
    expect(event.defaultPrevented).toBe(true);
  });

  it("lets the click through when confirmed", () => {
    document.body.innerHTML =
      '<button data-confirm="Unlink it?">Unlink</button>';
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const event = click(document.querySelector("button"));

    expect(event.defaultPrevented).toBe(false);
  });

  it("asks when the click lands on the button's label rather than the button", () => {
    // The button() macro wraps its text in a span, so that is usually what gets clicked.
    document.body.innerHTML =
      '<button data-confirm="Unlink it?"><span>Unlink</span></button>';
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    const event = click(document.querySelector("span"));

    expect(confirmSpy).toHaveBeenCalledWith("Unlink it?");
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not ask for clicks outside any confirming element", () => {
    document.body.innerHTML =
      '<button data-confirm="Unlink it?">Unlink</button><button id="other">Other</button>';
    const confirmSpy = vi.spyOn(window, "confirm");

    const event = click(document.getElementById("other"));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});
