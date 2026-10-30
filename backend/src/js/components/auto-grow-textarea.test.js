// ABOUTME: Unit tests for the autoGrowTextarea Alpine component
// ABOUTME: Covers growing to the text's height on focus and going back to one line on blur

import { beforeEach, describe, expect, it } from "vitest";

import { autoGrowTextarea } from "./auto-grow-textarea.js";

function textareaState(value, scrollHeight, border = 0) {
  document.body.innerHTML = `<textarea id="box" rows="1"></textarea>`;
  const el = document.getElementById("box");
  el.value = value;
  // jsdom does no layout, so the height the text would need is given here,
  // along with the border that offsetHeight counts and clientHeight does not.
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    get: () => scrollHeight,
  });
  Object.defineProperty(el, "offsetHeight", {
    configurable: true,
    get: () => 30 + border,
  });
  Object.defineProperty(el, "clientHeight", {
    configurable: true,
    get: () => 30,
  });
  const state = autoGrowTextarea();
  state.$el = el;
  return state;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("autoGrowTextarea", () => {
  it("grows to the height of its text", () => {
    const state = textareaState("one\ntwo\nthree", 72);
    state.grow();
    expect(state.$el.style.height).toBe("72px");
  });

  it("leaves room for its border, or the last line would be clipped", () => {
    const state = textareaState("one\ntwo\nthree", 72, 2);
    state.grow();
    expect(state.$el.style.height).toBe("74px");
  });

  it("follows the text as it gets shorter", () => {
    const state = textareaState("one\ntwo\nthree", 72);
    state.grow();
    Object.defineProperty(state.$el, "scrollHeight", {
      configurable: true,
      get: () => 24,
    });
    state.grow();
    expect(state.$el.style.height).toBe("24px");
  });

  it("goes back to its one line on blur", () => {
    const state = textareaState("one\ntwo", 48);
    state.grow();
    state.shrink();
    expect(state.$el.style.height).toBe("");
  });

  it("leaves the whole text in its hover title on blur", () => {
    const state = textareaState("a note\nover two lines", 48);
    state.shrink();
    expect(state.$el.title).toBe("a note\nover two lines");
  });
});
