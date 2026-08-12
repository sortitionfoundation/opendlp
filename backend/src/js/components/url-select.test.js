// ABOUTME: Unit tests for the urlSelect Alpine component
// ABOUTME: Covers URL building with existing query params and the focus-hash restoration marker

import { beforeEach, describe, expect, it } from "vitest";

import { urlSelect } from "./url-select.js";

function selectElement({ focusId = "", focused = false } = {}) {
  document.body.innerHTML = `<select ${focusId ? `data-focus-id="${focusId}"` : ""}></select>`;
  const el = document.querySelector("select");
  if (focused) {
    el.focus();
  }
  return el;
}

beforeEach(() => {
  delete window.location;
  window.location = { href: "https://example.org/start" };
});

describe("urlSelect", () => {
  it("starts on the initial value", () => {
    expect(urlSelect({ baseUrl: "/page", initialValue: "one" }).selected).toBe(
      "one",
    );
  });

  it("appends the parameter with a ? when the base URL has no query", () => {
    const state = urlSelect({ baseUrl: "/page", paramName: "source" });
    state.selected = "csv";
    state.navigate({ target: selectElement() });
    expect(window.location.href).toBe("/page?source=csv");
  });

  it("appends the parameter with an & when the base URL already has a query", () => {
    const state = urlSelect({ baseUrl: "/page?tab=1", paramName: "source" });
    state.selected = "csv";
    state.navigate({ target: selectElement() });
    expect(window.location.href).toBe("/page?tab=1&source=csv");
  });

  it("defaults the parameter name to value", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.selected = "csv";
    state.navigate({ target: selectElement() });
    expect(window.location.href).toBe("/page?value=csv");
  });

  it("encodes the selected value", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.selected = "a b&c";
    state.navigate({ target: selectElement() });
    expect(window.location.href).toBe("/page?value=a%20b%26c");
  });

  it("omits the parameter entirely when nothing is selected", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.navigate({ target: selectElement() });
    expect(window.location.href).toBe("/page");
  });

  it("adds a focus hash when the focused element carries a focus id", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.selected = "csv";
    state.navigate({
      target: selectElement({ focusId: "source-select", focused: true }),
    });
    expect(window.location.href).toBe("/page?value=csv#focus=source-select");
  });

  it("omits the focus hash when the element is not focused", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.selected = "csv";
    state.navigate({
      target: selectElement({ focusId: "source-select", focused: false }),
    });
    expect(window.location.href).toBe("/page?value=csv");
  });

  it("omits the focus hash when the element has no focus id", () => {
    const state = urlSelect({ baseUrl: "/page" });
    state.selected = "csv";
    state.navigate({ target: selectElement({ focused: true }) });
    expect(window.location.href).toBe("/page?value=csv");
  });
});
