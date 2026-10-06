// ABOUTME: Unit tests for the charCount Alpine component
// ABOUTME: Covers initial count pickup and updates as the textarea changes

import { beforeEach, describe, expect, it } from "vitest";

import { charCount } from "./char-count.js";

function componentFor(textareaValue) {
  const wrapper = document.createElement("div");
  const textarea = document.createElement("textarea");
  textarea.value = textareaValue;
  wrapper.appendChild(textarea);
  const component = charCount();
  component.$el = wrapper;
  return { component, textarea };
}

describe("charCount", () => {
  let component;
  let textarea;

  beforeEach(() => {
    ({ component, textarea } = componentFor("hello"));
  });

  it("picks up the server-rendered value on init", () => {
    component.init();
    expect(component.count).toBe(5);
  });

  it("follows the textarea as it changes", () => {
    component.init();
    textarea.value = "hello world";
    component.update();
    expect(component.count).toBe(11);
  });

  it("counts zero when there is no textarea", () => {
    const bare = charCount();
    bare.$el = document.createElement("div");
    bare.update();
    expect(bare.count).toBe(0);
  });
});
