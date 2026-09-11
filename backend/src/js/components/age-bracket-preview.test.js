// ABOUTME: Unit tests for the ageBracketPreview Alpine component
// ABOUTME: Covers label generation, mismatch flagging against target values, and invalid input handling

import { beforeEach, describe, expect, it } from "vitest";

import { ageBracketPreview } from "./age-bracket-preview.js";

function previewState({
  minAge = "16",
  maxAge = "100",
  boundaries = "",
  fallback = "UNKNOWN",
  targetValues = [],
} = {}) {
  document.body.innerHTML = `
    <div id="panel" data-fallback="${fallback}"
         data-target-values='${JSON.stringify(targetValues)}'>
      <input name="min_age" value="${minAge}" />
      <input name="max_age" value="${maxAge}" />
      <input name="boundaries" value="${boundaries}" />
    </div>`;
  const state = ageBracketPreview();
  state.$root = document.getElementById("panel");
  state.init();
  return state;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("ageBracketPreview", () => {
  it("generates the same labels as AgeBracketRule.bracket_labels plus the fallback", () => {
    const state = previewState({ boundaries: "25, 40, 60" });
    expect(state.previewText).toBe(
      "under-16, 16-24, 25-39, 40-59, 60-99, 100+, UNKNOWN",
    );
  });

  it("handles no boundaries as one big bracket", () => {
    const state = previewState();
    expect(state.previewText).toBe("under-16, 16-99, 100+, UNKNOWN");
  });

  it("sorts and dedupes boundaries like the server does", () => {
    const state = previewState({ boundaries: "60; 25, 40, 25" });
    expect(state.previewText).toBe(
      "under-16, 16-24, 25-39, 40-59, 60-99, 100+, UNKNOWN",
    );
  });

  it("flags generated labels the target's values don't contain", () => {
    const state = previewState({
      boundaries: "25",
      targetValues: ["16-24", "25-99"],
    });
    expect(state.mismatchLabels).toBe("under-16, 100+");
  });

  it("stays silent about mismatches when no target is chosen", () => {
    const state = previewState({ boundaries: "25" });
    expect(state.mismatchLabels).toBe("");
  });

  it("clears the preview when a boundary is outside the min/max range", () => {
    const state = previewState({ boundaries: "10" });
    expect(state.previewText).toBe("");
    expect(state.mismatchLabels).toBe("");
  });

  it("clears the preview while the ages are not yet valid numbers", () => {
    const state = previewState({ minAge: "1x" });
    expect(state.previewText).toBe("");
  });

  it("recalculates when inputs change", () => {
    const state = previewState();
    state.$root.querySelector('[name="boundaries"]').value = "30";
    state.recalc();
    expect(state.previewText).toBe("under-16, 16-29, 30-99, 100+, UNKNOWN");
  });
});
