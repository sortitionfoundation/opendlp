// ABOUTME: Unit tests for the infoToggletip Alpine component behind the info_icon macro
// ABOUTME: Covers showing and announcing the text, the ways it closes, and placing the bubble in the viewport

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { initDialogEscape } from "../init/dialog-escape.js";
import { infoToggletip } from "./info-toggletip.js";

const TEXT = "Withdrawn people are not counted.";

/**
 * Build a component over real DOM, wired the way the macro wires it. jsdom has
 * no popover support, so the bubble gets stand-in showPopover/hidePopover.
 */
function buildToggletip() {
  document.body.innerHTML = `
    <button type="button" id="before">Before</button>
    <span id="wrapper">
      <button type="button" id="button">i</button>
      <span role="status" id="status"></span>
      <span id="bubble" aria-hidden="true">  ${TEXT}  </span>
    </span>
    <button type="button" id="after">After</button>`;
  const bubble = document.getElementById("bubble");
  bubble.showPopover = vi.fn();
  bubble.hidePopover = vi.fn();
  const state = infoToggletip();
  state.$el = document.getElementById("wrapper");
  state.$refs = { button: document.getElementById("button"), bubble };
  state.init();
  return state;
}

function escapeKey() {
  return { key: "Escape", preventDefault: vi.fn(), stopPropagation: vi.fn() };
}

function setBox(element, box) {
  element.getBoundingClientRect = () => ({
    ...box,
    right: box.left + box.width,
    bottom: box.top + box.height,
  });
}

function setSize(element, width, height) {
  Object.defineProperty(element, "offsetWidth", {
    configurable: true,
    value: width,
  });
  Object.defineProperty(element, "offsetHeight", {
    configurable: true,
    value: height,
  });
}

function setViewport(width, height) {
  Object.defineProperty(document.documentElement, "clientWidth", {
    configurable: true,
    value: width,
  });
  Object.defineProperty(document.documentElement, "clientHeight", {
    configurable: true,
    value: height,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  setViewport(1000, 800);
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("infoToggletip", () => {
  it("starts closed, with nothing announced", () => {
    const state = buildToggletip();

    expect(state.open).toBe(false);
    expect(state.announced).toBe("");
  });

  it("drops the server-rendered title once running", () => {
    // Alpine removes an attribute bound to null.
    expect(infoToggletip().nativeTitle).toBeNull();
  });

  it("shows the bubble on click and announces its text a moment later", () => {
    const state = buildToggletip();

    state.toggle();

    expect(state.open).toBe(true);
    expect(state.$refs.bubble.showPopover).toHaveBeenCalledOnce();
    expect(state.announced).toBe("");
    vi.advanceTimersByTime(100);
    expect(state.announced).toBe(TEXT);
  });

  it("hides the bubble and empties the live region on a second click", () => {
    const state = buildToggletip();
    state.toggle();
    vi.advanceTimersByTime(100);

    state.toggle();

    expect(state.open).toBe(false);
    expect(state.announced).toBe("");
    expect(state.$refs.bubble.hidePopover).toHaveBeenCalledOnce();
  });

  it("does not announce text that was closed before it arrived", () => {
    const state = buildToggletip();
    state.toggle();
    state.toggle();

    vi.advanceTimersByTime(100);

    expect(state.announced).toBe("");
  });

  it("closes on Escape, returns focus to the button, and keeps the key from the dialog", () => {
    const state = buildToggletip();
    state.toggle();
    const event = escapeKey();

    state.closeOnEscape(event);

    expect(state.open).toBe(false);
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(document.activeElement.id).toBe("button");
  });

  it("lets Escape reach the dialog when the bubble is closed", () => {
    const state = buildToggletip();
    const event = escapeKey();

    state.closeOnEscape(event);

    expect(event.stopPropagation).not.toHaveBeenCalled();
  });

  it("an Escape stopped on the toggletip does not close an enclosing dialog", () => {
    initDialogEscape();
    const state = buildToggletip();
    const backdrop = document.createElement("a");
    backdrop.className = "dialog-backdrop--clickable";
    backdrop.href = "#closed";
    const backdropClick = vi.fn((event) => event.preventDefault());
    backdrop.addEventListener("click", backdropClick);
    document.body.appendChild(backdrop);
    state.$el.addEventListener("keydown", (event) => {
      if (event.key === "Escape") state.closeOnEscape(event);
    });
    state.toggle();

    state.$refs.button.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    );

    expect(state.open).toBe(false);
    expect(backdropClick).not.toHaveBeenCalled();
  });

  it("closes on a click outside", () => {
    const state = buildToggletip();
    state.toggle();

    state.close();

    expect(state.open).toBe(false);
    expect(state.$refs.bubble.hidePopover).toHaveBeenCalledOnce();
  });

  it("does nothing on close when already closed", () => {
    const state = buildToggletip();

    state.close();

    expect(state.$refs.bubble.hidePopover).not.toHaveBeenCalled();
  });

  it("closes when focus leaves for another control", () => {
    const state = buildToggletip();
    state.toggle();

    state.closeOnFocusOut({ relatedTarget: document.getElementById("after") });

    expect(state.open).toBe(false);
  });

  it("stays open when focus goes nowhere, leaving that to click.outside", () => {
    const state = buildToggletip();
    state.toggle();

    state.closeOnFocusOut({ relatedTarget: null });

    expect(state.open).toBe(true);
  });

  it("places the bubble centred under the icon", () => {
    const state = buildToggletip();
    setBox(state.$refs.button, { left: 500, top: 100, width: 16, height: 16 });
    setSize(state.$refs.bubble, 200, 40);

    state.toggle();

    expect(state.$refs.bubble.style.left).toBe("408px");
    expect(state.$refs.bubble.style.top).toBe("122px");
  });

  it("keeps the bubble inside the viewport's edges", () => {
    const state = buildToggletip();
    setSize(state.$refs.bubble, 200, 40);

    setBox(state.$refs.button, { left: 2, top: 100, width: 16, height: 16 });
    state.place();
    expect(state.$refs.bubble.style.left).toBe("8px");

    setBox(state.$refs.button, { left: 990, top: 100, width: 16, height: 16 });
    state.place();
    expect(state.$refs.bubble.style.left).toBe("792px");
  });

  it("puts the bubble above the icon when there is no room below", () => {
    const state = buildToggletip();
    setBox(state.$refs.button, { left: 500, top: 770, width: 16, height: 16 });
    setSize(state.$refs.bubble, 200, 40);

    state.place();

    expect(state.$refs.bubble.style.top).toBe("724px");
  });

  it("follows the icon on scroll while open, and stops once closed", () => {
    const state = buildToggletip();
    setSize(state.$refs.bubble, 200, 40);
    setBox(state.$refs.button, { left: 500, top: 100, width: 16, height: 16 });
    state.toggle();

    setBox(state.$refs.button, { left: 500, top: 50, width: 16, height: 16 });
    window.dispatchEvent(new Event("scroll"));
    expect(state.$refs.bubble.style.top).toBe("72px");

    state.close();
    setBox(state.$refs.button, { left: 500, top: 10, width: 16, height: 16 });
    window.dispatchEvent(new Event("scroll"));
    expect(state.$refs.bubble.style.top).toBe("72px");
  });
});
