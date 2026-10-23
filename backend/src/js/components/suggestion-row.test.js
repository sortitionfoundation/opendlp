// ABOUTME: Unit tests for the suggestionRow Alpine component
// ABOUTME: Covers one-click accept into the page's inputs, combining comments, and undo

import { beforeEach, describe, expect, it, vi } from "vitest";

import { suggestionRow } from "./suggestion-row.js";

function setUp() {
  document.body.innerHTML = `
    <input id="min" value="5" />
    <input id="max" value="9" />
    <input id="comment" value="" />
    <table><tbody>
      <tr id="min-row" data-apply='{"min": 3}' data-comment-target="comment">
        <td><input id="min-comment" value="Accepted minimum 5 → 3" /></td>
      </tr>
      <tr id="max-row" data-apply='{"max": 6}' data-comment-target="comment">
        <td><input id="max-comment" value="Accepted maximum 9 → 6" /></td>
      </tr>
    </tbody></table>`;
}

function rowState(rowId, commentId) {
  const state = suggestionRow();
  state.$root = document.getElementById(rowId);
  state.$refs = { comment: document.getElementById(commentId) };
  return state;
}

const value = (id) => document.getElementById(id).value;

beforeEach(setUp);

describe("suggestionRow", () => {
  it("writes the suggested number and the comment in one click", () => {
    const state = rowState("min-row", "min-comment");
    state.accept();
    expect(value("min")).toBe("3");
    expect(value("comment")).toBe("Accepted minimum 5 → 3");
    expect(state.accepted).toBe(true);
  });

  it("saves the comment as edited before accepting", () => {
    document.getElementById("min-comment").value = "Too few young men";
    rowState("min-row", "min-comment").accept();
    expect(value("comment")).toBe("Too few young men");
  });

  it("fires input on what it changes, so totals and the leave guard hear", () => {
    const heard = vi.fn();
    document.body.addEventListener("input", heard);
    rowState("min-row", "min-comment").accept();
    expect(heard).toHaveBeenCalledTimes(2);
  });

  it("adds a second suggestion's comment to the first rather than replacing it", () => {
    rowState("min-row", "min-comment").accept();
    rowState("max-row", "max-comment").accept();
    expect(value("comment")).toBe(
      "Accepted minimum 5 → 3; Accepted maximum 9 → 6",
    );
  });

  it("adds to a comment the organiser wrote earlier rather than replacing it", () => {
    document.getElementById("comment").value = "An older reason";
    rowState("min-row", "min-comment").accept();
    expect(value("comment")).toBe("An older reason; Accepted minimum 5 → 3");
  });

  it("puts everything back on undo", () => {
    document.getElementById("comment").value = "An older reason";
    const state = rowState("min-row", "min-comment");
    state.accept();
    state.undo();
    expect(value("min")).toBe("5");
    expect(value("comment")).toBe("An older reason");
    expect(state.accepted).toBe(false);
  });

  it("leaves alone on undo what was typed over after accepting", () => {
    const state = rowState("min-row", "min-comment");
    state.accept();
    document.getElementById("min").value = "4";
    state.undo();
    expect(value("min")).toBe("4");
  });

  it("does nothing the second time it is accepted", () => {
    const state = rowState("min-row", "min-comment");
    state.accept();
    document.getElementById("min").value = "4";
    state.accept();
    expect(value("min")).toBe("4");
  });
});
