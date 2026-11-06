// ABOUTME: Unit tests for the stickyBelowHeader Alpine component
// ABOUTME: Covers sitting under the header, following its height, and doing without one

import { afterEach, describe, expect, it, vi } from "vitest";

import { stickyBelowHeader } from "./sticky-below-header.js";

function setUp({ withHeader = true, headerHeight = 120, ownHeight = 60 } = {}) {
  document.body.innerHTML = `
    ${withHeader ? '<header id="header" data-sticky-header></header>' : ""}
    <section id="heading"></section>`;
  if (withHeader) {
    Object.defineProperty(document.getElementById("header"), "offsetHeight", {
      configurable: true,
      get: () => headerHeight,
    });
  }
  Object.defineProperty(document.getElementById("heading"), "offsetHeight", {
    configurable: true,
    get: () => ownHeight,
  });
  const state = stickyBelowHeader();
  state.$el = document.getElementById("heading");
  return state;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.style.scrollPaddingTop = "";
  document.body.innerHTML = "";
});

describe("stickyBelowHeader", () => {
  it("sits just under the header", () => {
    const state = setUp({ headerHeight: 120 });
    state.init();
    expect(state.$el.style.top).toBe("120px");
  });

  it("keeps a focused field from scrolling in under the header and itself", () => {
    const state = setUp({ headerHeight: 120, ownHeight: 60 });
    state.init();
    expect(document.documentElement.style.scrollPaddingTop).toBe("180px");
  });

  it("moves when the header changes height", () => {
    let resized = null;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback) {
          resized = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    let height = 120;
    const state = setUp();
    Object.defineProperty(document.getElementById("header"), "offsetHeight", {
      configurable: true,
      get: () => height,
    });
    state.init();

    height = 168;
    resized();

    expect(state.$el.style.top).toBe("168px");
    expect(document.documentElement.style.scrollPaddingTop).toBe("228px");
  });

  it("stops watching the header when it goes", () => {
    const disconnect = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {
          disconnect();
        }
      },
    );
    const state = setUp();
    state.init();
    state.destroy();
    expect(disconnect).toHaveBeenCalled();
    expect(document.documentElement.style.scrollPaddingTop).toBe("");
  });

  it("leaves its position to the stylesheet without a header", () => {
    const state = setUp({ withHeader: false });
    state.init();
    expect(state.$el.style.top).toBe("");
  });
});
