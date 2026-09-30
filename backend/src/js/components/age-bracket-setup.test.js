// ABOUTME: Unit tests for the ageBracketSetup Alpine component
// ABOUTME: Covers the ages worked out from typed starts, the younger-than line, and the Edit and Change toggles

import { beforeEach, describe, expect, it } from "vitest";

import { ageBracketSetup } from "./age-bracket-setup.js";

function setupState({
  starts = ["16", "30", "60"],
  editing = "false",
  changingDate = "false",
} = {}) {
  const rows = starts
    .map(
      (start) => `
        <tr data-age-row>
          <td><input name="bracket_from" value="${start}" /></td>
          <td data-ages></td>
        </tr>`,
    )
    .join("");
  document.body.innerHTML = `
    <div id="root" data-editing="${editing}" data-changing-date="${changingDate}"
         data-range-text="{first} to {last}" data-over-text="{age} and over"
         data-younger-text="Anyone younger than {age} counts as UNKNOWN.">
      <table><tbody>${rows}</tbody></table>
      <input id="day" name="as_of_day" />
    </div>`;
  const state = ageBracketSetup();
  state.$root = document.getElementById("root");
  state.$refs = { asOfDay: document.getElementById("day") };
  state.$nextTick = (callback) => callback();
  state.init();
  return state;
}

function agesShown() {
  return Array.from(document.querySelectorAll("[data-ages]")).map(
    (cell) => cell.textContent,
  );
}

function typeStart(state, index, value) {
  document.querySelectorAll('[name="bracket_from"]')[index].value = value;
  state.recalc();
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("ageBracketSetup", () => {
  it("runs each range up to the next one's start, and leaves the top open", () => {
    setupState();
    expect(agesShown()).toEqual(["16 to 29", "30 to 59", "60 and over"]);
  });

  it("works out the ranges whatever order the rows are in", () => {
    setupState({ starts: ["60", "16", "30"] });
    expect(agesShown()).toEqual(["60 and over", "16 to 29", "30 to 59"]);
  });

  it("shows a one-year range as just that age", () => {
    setupState({ starts: ["16", "17", "18"] });
    expect(agesShown()).toEqual(["16", "17", "18 and over"]);
  });

  it("says who counts as unknown when the lowest range starts above zero", () => {
    const state = setupState();
    expect(state.youngerText).toBe("Anyone younger than 16 counts as UNKNOWN.");
  });

  it("says nothing about the young when a range starts at zero", () => {
    const state = setupState({ starts: ["0", "16"] });
    expect(state.youngerText).toBe("");
  });

  it("updates as a start is typed", () => {
    const state = setupState();
    typeStart(state, 1, "25");
    expect(agesShown()).toEqual(["16 to 24", "25 to 59", "60 and over"]);
    typeStart(state, 0, "18");
    expect(state.youngerText).toBe("Anyone younger than 18 counts as UNKNOWN.");
  });

  it("leaves a blank or non-numeric start without ages, and drops the younger line", () => {
    const state = setupState({ starts: ["16", "", "sixty"] });
    expect(agesShown()).toEqual(["16 and over", "", ""]);
    expect(state.youngerText).toBe("");
  });

  it("drops the younger line when two ranges start at the same age", () => {
    const state = setupState({ starts: ["16", "16"] });
    expect(state.youngerText).toBe("");
  });

  it("starts in whichever mode the server chose", () => {
    const state = setupState({ editing: "true", changingDate: "true" });
    expect(state.editing).toBe(true);
    expect(state.changingDate).toBe(true);
  });

  it("reveals the table and focuses the first start on Edit", () => {
    const state = setupState();
    expect(state.editing).toBe(false);
    state.startEditing();
    expect(state.editing).toBe(true);
    expect(document.activeElement).toBe(
      document.querySelector('[name="bracket_from"]'),
    );
  });

  it("reveals the date inputs and focuses the day on Change", () => {
    const state = setupState();
    expect(state.changingDate).toBe(false);
    state.changeDate();
    expect(state.changingDate).toBe(true);
    expect(document.activeElement).toBe(document.getElementById("day"));
  });
});
