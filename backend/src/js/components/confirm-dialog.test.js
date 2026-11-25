// ABOUTME: Unit tests for the confirmDialog Alpine component
// ABOUTME: Covers opening and cancelling the confirmation, where the focus goes each time, and its box

import { describe, expect, it, vi } from "vitest";

import { confirmDialog } from "./confirm-dialog.js";

function buildDialog() {
  const state = confirmDialog();
  state.$refs = {
    opener: { focus: vi.fn() },
    safeAction: { focus: vi.fn() },
  };
  state.$nextTick = (fn) => fn();
  return state;
}

describe("confirmDialog", () => {
  it("starts closed", () => {
    expect(buildDialog().isOpen).toBe(false);
  });

  it("opens and focuses the safe action", () => {
    const state = buildDialog();

    state.open();

    expect(state.isOpen).toBe(true);
    expect(state.$refs.safeAction.focus).toHaveBeenCalled();
    expect(state.$refs.opener.focus).not.toHaveBeenCalled();
  });

  it("starts with its box unticked", () => {
    expect(buildDialog().ticked).toBe(false);
  });

  it("unticks a box left ticked by an earlier opening", () => {
    const state = buildDialog();
    state.open();
    state.ticked = true;
    state.cancel();

    state.open();

    expect(state.ticked).toBe(false);
  });

  it("closes on cancel and gives the focus back to the opener", () => {
    const state = buildDialog();
    state.open();

    state.cancel();

    expect(state.isOpen).toBe(false);
    expect(state.$refs.opener.focus).toHaveBeenCalled();
  });

  it("finds the opener while the dialog is still there", () => {
    // Alpine resolves $refs from the element a call came from. cancel() comes
    // from inside the dialog, and once the dialog is gone that element can no
    // longer reach any ref - as this $refs, empty while closed, stands in for.
    const state = buildDialog();
    const refs = state.$refs;
    Object.defineProperty(state, "$refs", {
      get: () => (state.isOpen ? refs : {}),
    });
    state.open();

    state.cancel();

    expect(refs.opener.focus).toHaveBeenCalled();
  });

  it("survives a missing ref rather than throwing", () => {
    const state = buildDialog();
    state.$refs = {};

    state.open();
    state.cancel();

    expect(state.isOpen).toBe(false);
  });
});
