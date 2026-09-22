// ABOUTME: Unit tests for the dialogLeaveGuard Alpine component
// ABOUTME: Covers carrying the dirty flag across re-renders and guarding the close links

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dialogLeaveGuard } from "./dialog-leave-guard.js";

let realLocation;

beforeEach(() => {
  realLocation = window.location;
  delete window.location;
  window.location = { assign: vi.fn(), href: "https://example.org/sources" };
});

afterEach(() => {
  window.location = realLocation;
  vi.restoreAllMocks();
});

/**
 * A guard over a dialog whose hidden dirty input holds `dirtyValue`, with the
 * Alpine magics it reaches for supplied by hand.
 */
function guard(dirtyValue = "") {
  document.body.innerHTML = `
    <input type="hidden" name="dirty" id="dirty" value="${dirtyValue}" />
    <a id="close" href="/sources#focus=row-1">Close</a>`;
  const state = dialogLeaveGuard();
  state.$nextTick = (callback) => callback();
  state.$refs = {
    dirtyInput: document.getElementById("dirty"),
    keepEditingBtn: { focus: vi.fn() },
  };
  state.init();
  return state;
}

/** A click on the close link, as guardLeave() receives it. */
function closeClick() {
  return {
    currentTarget: document.getElementById("close"),
    preventDefault: vi.fn(),
  };
}

describe("dialogLeaveGuard", () => {
  it("starts clean when the server rendered the stored values", () => {
    const state = guard();

    expect(state.editDirty).toBe(false);
  });

  it("starts dirty when the re-render carried the flag back", () => {
    const state = guard("1");

    expect(state.editDirty).toBe(true);
  });

  it("writes the flag to the hidden input so the next re-render carries it", () => {
    const state = guard();

    state.markDialogDirty();

    expect(state.editDirty).toBe(true);
    expect(document.getElementById("dirty").value).toBe("1");
  });

  it("lets a clean dialog close", () => {
    const state = guard();
    const event = closeClick();

    state.guardLeave(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(false);
  });

  it("asks before a dirty dialog closes, and closes to the link's own URL on discard", () => {
    const state = guard();
    state.markDialogDirty();
    const event = closeClick();

    state.guardLeave(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
    expect(state.$refs.keepEditingBtn.focus).toHaveBeenCalled();

    state.discardAndLeave();

    expect(window.location.assign).toHaveBeenCalledWith(
      document.getElementById("close").href,
    );
    expect(window.location.assign.mock.calls[0][0]).toMatch(
      /\/sources#focus=row-1$/,
    );
  });

  it("does not listen on window, so nothing outlives the dialog", () => {
    const listeners = vi.spyOn(window, "addEventListener");

    guard("1");

    expect(listeners).not.toHaveBeenCalled();
  });
});
