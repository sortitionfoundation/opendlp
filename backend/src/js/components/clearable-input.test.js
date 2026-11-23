// ABOUTME: Unit tests for the clearableInput Alpine component
// ABOUTME: Covers showing the clear button only with text, and clearing with and without resubmitting

import { describe, expect, it, vi } from "vitest";

import { clearableInput } from "./clearable-input.js";

function componentFor(value, { submits = false } = {}) {
  const form = document.createElement("form");
  const wrapper = document.createElement("div");
  if (submits) {
    wrapper.dataset.clearSubmits = "true";
  }
  const field = document.createElement("input");
  field.value = value;
  wrapper.appendChild(field);
  form.appendChild(wrapper);
  document.body.appendChild(form);
  const component = clearableInput();
  component.$root = wrapper;
  return { component, field, form };
}

describe("clearableInput", () => {
  it("shows the clear button for a server-rendered value", () => {
    const { component } = componentFor("smith");
    component.init();
    expect(component.hasText).toBe(true);
  });

  it("hides the clear button while the input is empty", () => {
    const { component } = componentFor("");
    component.init();
    expect(component.hasText).toBe(false);
  });

  it("follows the input as it is typed in", () => {
    const { component, field } = componentFor("");
    component.init();
    field.value = "a";
    component.update();
    expect(component.hasText).toBe(true);
    field.value = "";
    component.update();
    expect(component.hasText).toBe(false);
  });

  it("empties the input and refocuses it", () => {
    const { component, field, form } = componentFor("smith");
    const onSubmit = vi.fn((event) => event.preventDefault());
    form.addEventListener("submit", onSubmit);
    component.init();
    component.clear();
    expect(field.value).toBe("");
    expect(component.hasText).toBe(false);
    expect(document.activeElement).toBe(field);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("resubmits the form when asked to", () => {
    const { component, field, form } = componentFor("smith", { submits: true });
    const onSubmit = vi.fn((event) => event.preventDefault());
    form.addEventListener("submit", onSubmit);
    component.init();
    component.clear();
    expect(field.value).toBe("");
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
