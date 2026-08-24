// ABOUTME: Unit tests for the registrationPageRow Alpine component
// ABOUTME: Covers the actions menu toggle and the delete confirmation's focus handling

import { describe, expect, it, vi } from "vitest";

import { registrationPageRow } from "./registration-page-row.js";

function buildRow() {
  const state = registrationPageRow();
  state.$refs = {
    menuToggle: { focus: vi.fn() },
    keepPageBtn: { focus: vi.fn() },
  };
  state.$nextTick = (fn) => fn();
  return state;
}

describe("registrationPageRow menu", () => {
  it("starts with the menu and the confirmation closed", () => {
    const state = buildRow();

    expect(state.open).toBe(false);
    expect(state.confirmDeleteOpen).toBe(false);
  });

  it("toggles the menu open and shut", () => {
    const state = buildRow();

    state.toggleMenu();
    expect(state.open).toBe(true);

    state.toggleMenu();
    expect(state.open).toBe(false);
  });

  it("closes the menu on demand", () => {
    const state = buildRow();
    state.open = true;

    state.closeMenu();

    expect(state.open).toBe(false);
  });
});

describe("registrationPageRow delete confirmation", () => {
  it("dismisses the menu and opens the dialog", () => {
    const state = buildRow();
    state.open = true;

    state.openConfirmDelete();

    expect(state.open).toBe(false);
    expect(state.confirmDeleteOpen).toBe(true);
  });

  it("focuses the safe action when the dialog opens", () => {
    const state = buildRow();

    state.openConfirmDelete();

    expect(state.$refs.keepPageBtn.focus).toHaveBeenCalled();
  });

  it("closes the dialog and returns focus to the menu button on cancel", () => {
    const state = buildRow();
    state.openConfirmDelete();

    state.cancelConfirmDelete();

    expect(state.confirmDeleteOpen).toBe(false);
    expect(state.$refs.menuToggle.focus).toHaveBeenCalled();
  });

  it("survives a missing ref rather than throwing", () => {
    const state = buildRow();
    state.$refs = {};

    state.openConfirmDelete();
    state.cancelConfirmDelete();

    expect(state.confirmDeleteOpen).toBe(false);
  });
});
