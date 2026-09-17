// ABOUTME: Unit tests for the rowActionsMenu Alpine component
// ABOUTME: Covers the toggle and the Escape handling that must not reach an enclosing dialog

import { describe, expect, it, vi } from "vitest";

import { rowActionsMenu } from "./row-actions-menu.js";

function buildMenu() {
  const state = rowActionsMenu();
  state.$refs = { menuToggle: { focus: vi.fn() } };
  return state;
}

describe("rowActionsMenu", () => {
  it("starts closed and toggles open and shut", () => {
    const state = buildMenu();
    expect(state.open).toBe(false);

    state.toggleMenu();
    expect(state.open).toBe(true);

    state.toggleMenu();
    expect(state.open).toBe(false);
  });

  it("closes on demand", () => {
    const state = buildMenu();
    state.open = true;

    state.closeMenu();

    expect(state.open).toBe(false);
  });

  it("stops Escape at the open menu and hands focus back to the kebab", () => {
    const state = buildMenu();
    state.open = true;
    const event = { stopPropagation: vi.fn() };

    state.closeOnEscape(event);

    expect(state.open).toBe(false);
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(state.$refs.menuToggle.focus).toHaveBeenCalled();
  });

  it("lets Escape through when the menu is already shut", () => {
    const state = buildMenu();
    const event = { stopPropagation: vi.fn() };

    state.closeOnEscape(event);

    expect(event.stopPropagation).not.toHaveBeenCalled();
    expect(state.$refs.menuToggle.focus).not.toHaveBeenCalled();
  });
});
