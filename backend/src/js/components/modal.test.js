// ABOUTME: Unit tests for the modal Alpine component's open/close state machine
// ABOUTME: Covers the canClose gate and the closeUrl / refreshOnClose branches

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { modal } from "./modal.js";

describe("modal defaults", () => {
  it("starts closed and closeable when given no options", () => {
    const state = modal({});
    expect(state.isOpen).toBe(false);
    expect(state.canClose).toBe(true);
  });

  it("honours initialOpen", () => {
    expect(modal({ initialOpen: true }).isOpen).toBe(true);
  });

  it("treats canClose: false as meaning it, rather than falling back to true", () => {
    expect(modal({ canClose: false }).canClose).toBe(false);
  });
});

describe("modal open and close", () => {
  it("opens", () => {
    const state = modal({});
    state.open();
    expect(state.isOpen).toBe(true);
  });

  it("closes when closing is allowed", () => {
    const state = modal({ initialOpen: true });
    state.close();
    expect(state.isOpen).toBe(false);
  });

  it("refuses to close while canClose is false", () => {
    const state = modal({ initialOpen: true, canClose: false });
    state.close();
    expect(state.isOpen).toBe(true);
  });

  it("closes once setCanClose flips the gate", () => {
    const state = modal({ initialOpen: true, canClose: false });
    state.setCanClose(true);
    state.close();
    expect(state.isOpen).toBe(false);
  });

  it("closeIfAllowed behaves the same as close", () => {
    const state = modal({ initialOpen: true, canClose: false });
    state.closeIfAllowed();
    expect(state.isOpen).toBe(true);
  });
});

describe("modal close side effects", () => {
  let reload;

  beforeEach(() => {
    reload = vi.fn();
    // jsdom's window.location is not writable, so replace it wholesale
    delete window.location;
    window.location = { href: "https://example.org/start", reload };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("navigates to closeUrl when one is configured", () => {
    modal({ initialOpen: true, closeUrl: "/assemblies" }).close();
    expect(window.location.href).toBe("/assemblies");
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads when refreshOnClose is set and there is no closeUrl", () => {
    modal({ initialOpen: true, refreshOnClose: true }).close();
    expect(reload).toHaveBeenCalledOnce();
  });

  it("prefers closeUrl over refreshOnClose", () => {
    modal({
      initialOpen: true,
      closeUrl: "/assemblies",
      refreshOnClose: true,
    }).close();
    expect(window.location.href).toBe("/assemblies");
    expect(reload).not.toHaveBeenCalled();
  });

  it("does nothing to the page when closing is blocked", () => {
    modal({
      initialOpen: true,
      canClose: false,
      closeUrl: "/assemblies",
    }).close();
    expect(window.location.href).toBe("https://example.org/start");
    expect(reload).not.toHaveBeenCalled();
  });
});
