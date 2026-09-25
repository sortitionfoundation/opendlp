// ABOUTME: Unit tests for the replacementSuggestions Alpine component
// ABOUTME: Covers accepting one suggestion, accepting all, and hiding suggestions the inputs already match

import { beforeEach, describe, expect, it } from "vitest";

import { replacementSuggestions } from "./replacement-suggestions.js";

const MIN = "min-11111111-1111-1111-1111-111111111111";
const MAX = "max-22222222-2222-2222-2222-222222222222";

function build() {
  document.body.innerHTML = `
    <div id="root">
      <p id="accepted" data-suggestions-accepted="true" hidden>All applied</p>
      <div id="list" data-suggestions-list="true">
        <span id="list-min" data-suggestion-for="${MIN}" data-suggestion-value="1">min 2 to 1</span>
        <button id="accept-min" data-suggestion-for="${MIN}" data-suggestion-value="1">Accept</button>
        <span id="list-max" data-suggestion-for="${MAX}" data-suggestion-value="4">max 3 to 4</span>
        <button id="accept-max" data-suggestion-for="${MAX}" data-suggestion-value="4">Accept</button>
      </div>
      <span id="cell-min" data-suggestion-for="${MIN}" data-suggestion-value="1">Suggested minimum: 1</span>
      <input id="${MIN}" value="2">
      <input id="${MAX}" value="3">
    </div>`;
  const state = replacementSuggestions();
  state.$root = document.getElementById("root");
  state.init();
  return state;
}

function hidden(id) {
  return document.getElementById(id).hidden;
}

describe("replacementSuggestions", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows every suggestion whose input differs from it", () => {
    build();
    expect(hidden("list-min")).toBe(false);
    expect(hidden("cell-min")).toBe(false);
    expect(hidden("list-max")).toBe(false);
    expect(hidden("list")).toBe(false);
    expect(hidden("accepted")).toBe(true);
  });

  it("accepting writes the value into the input and hides that suggestion everywhere", () => {
    const state = build();
    const events = [];
    document
      .getElementById(MIN)
      .addEventListener("input", () => events.push("input"));

    state.accept(document.getElementById("accept-min"));

    expect(document.getElementById(MIN).value).toBe("1");
    expect(events).toEqual(["input"]);
    expect(hidden("list-min")).toBe(true);
    expect(hidden("accept-min")).toBe(true);
    expect(hidden("cell-min")).toBe(true);
    expect(hidden("list-max")).toBe(false);
    expect(hidden("list")).toBe(false);
  });

  it("accepting all fills every input and hides the list", () => {
    const state = build();

    state.acceptAll();

    expect(document.getElementById(MIN).value).toBe("1");
    expect(document.getElementById(MAX).value).toBe("4");
    expect(hidden("list-max")).toBe(true);
    expect(hidden("list")).toBe(true);
    expect(hidden("accepted")).toBe(false);
  });

  it("typing the suggested value by hand hides the suggestion on refresh", () => {
    const state = build();
    document.getElementById(MAX).value = "4";

    state.refresh();

    expect(hidden("list-max")).toBe(true);
    expect(hidden("accept-max")).toBe(true);
    expect(hidden("list-min")).toBe(false);
  });

  it("changing an accepted input away from the suggestion brings it back", () => {
    const state = build();
    state.acceptAll();
    document.getElementById(MIN).value = "0";

    state.refresh();

    expect(hidden("list-min")).toBe(false);
    expect(hidden("list")).toBe(false);
  });

  it("ignores a suggestion whose input is missing", () => {
    document.body.innerHTML = `
      <div id="root">
        <span id="orphan" data-suggestion-for="min-gone" data-suggestion-value="1"></span>
      </div>`;
    const state = replacementSuggestions();
    state.$root = document.getElementById("root");
    state.init();
    state.apply("min-gone", "1");
    expect(hidden("orphan")).toBe(false);
  });
});
