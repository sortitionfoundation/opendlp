// ABOUTME: Unit tests for the document-level action handlers
// ABOUTME: Covers data-confirm on buttons (click, including inner elements) and on forms (submit)

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { initDocumentActions } from "./document-actions.js";

function click(element) {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true });
  element.dispatchEvent(event);
  return event;
}

// jsdom does not implement form submission, so dispatch the event directly.
function submit(form) {
  const event = new Event("submit", { bubbles: true, cancelable: true });
  form.dispatchEvent(event);
  return event;
}

const CONFIRMING_FORM =
  '<form data-confirm="Disable it?">' +
  '<label for="code">Code</label><input type="text" id="code">' +
  '<button type="submit"><span>Disable</span></button></form>';

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

  it("does not ask for clicks on the fields of a confirming form", () => {
    document.body.innerHTML = CONFIRMING_FORM;
    const confirmSpy = vi.spyOn(window, "confirm");

    const inputEvent = click(document.querySelector("input"));
    const labelEvent = click(document.querySelector("label"));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(inputEvent.defaultPrevented).toBe(false);
    expect(labelEvent.defaultPrevented).toBe(false);
  });

  it("asks once when a confirming form is submitted and cancels it when declined", () => {
    document.body.innerHTML = CONFIRMING_FORM;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    const event = submit(document.querySelector("form"));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(confirmSpy).toHaveBeenCalledWith("Disable it?");
    expect(event.defaultPrevented).toBe(true);
  });

  it("lets a confirming form submit when confirmed", () => {
    document.body.innerHTML = CONFIRMING_FORM;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const event = submit(document.querySelector("form"));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not ask when a form without data-confirm is submitted", () => {
    document.body.innerHTML = "<form><button>Save</button></form>";
    const confirmSpy = vi.spyOn(window, "confirm");

    const event = submit(document.querySelector("form"));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it.each(["hx-post", "data-hx-delete"])(
    "ignores a confirming form that HTMX submits via %s",
    (attribute) => {
      document.body.innerHTML = `<form data-confirm="Disable it?" ${attribute}="/x"><button>Go</button></form>`;
      const confirmSpy = vi.spyOn(window, "confirm");

      const event = submit(document.querySelector("form"));

      expect(confirmSpy).not.toHaveBeenCalled();
      expect(event.defaultPrevented).toBe(false);
    },
  );
});
