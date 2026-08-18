// ABOUTME: Tests for the unsaved-changes guard on the registration page controller
// ABOUTME: Covers the beforeunload backstop, the discard modal and the close confirmation

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registrationEditGuard } from "./registration-edit-guard.js";

let realLocation;

beforeEach(() => {
  realLocation = window.location;
  delete window.location;
  window.location = { assign: vi.fn(), href: "https://example.org/edit" };
});

afterEach(() => {
  window.location = realLocation;
  vi.restoreAllMocks();
});

/**
 * The guard reaches for Alpine's $nextTick and $refs, which Alpine supplies at
 * runtime. Driving the returned object directly means supplying them here.
 */
function guard(editMode, listUrl) {
  const state = registrationEditGuard({ editMode: editMode, listUrl: listUrl });
  state.$nextTick = (callback) => callback();
  state.$refs = {
    keepOpenBtn: { focus: vi.fn() },
    keepEditingBtn: { focus: vi.fn() },
  };
  return state;
}

function leaveLink(href) {
  return { preventDefault: vi.fn(), currentTarget: { href: href } };
}

describe("the beforeunload backstop", () => {
  it("is not registered outside edit mode - a read-only page can never be dirty", () => {
    const listen = vi.spyOn(window, "addEventListener");

    guard(false).init();

    expect(listen).not.toHaveBeenCalledWith(
      "beforeunload",
      expect.anything(),
      undefined,
    );
  });

  it("is registered in edit mode", () => {
    const listen = vi.spyOn(window, "addEventListener");

    guard(true).init();

    expect(listen).toHaveBeenCalledWith("beforeunload", expect.any(Function));
  });

  it("lets a clean page unload without prompting", () => {
    const listen = vi.spyOn(window, "addEventListener");
    guard(true).init();
    const handler = listen.mock.calls[0][1];
    const event = { preventDefault: vi.fn(), returnValue: undefined };

    handler(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("prompts when there are unsaved changes", () => {
    const listen = vi.spyOn(window, "addEventListener");
    const state = guard(true);
    state.init();
    const handler = listen.mock.calls[0][1];
    state.markEditDirty();
    const event = { preventDefault: vi.fn(), returnValue: undefined };

    handler(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.returnValue).toBe("");
  });

  it("stays quiet once a save has been allowed through", () => {
    const listen = vi.spyOn(window, "addEventListener");
    const state = guard(true);
    state.init();
    const handler = listen.mock.calls[0][1];
    state.markEditDirty();
    state.allowLeave();
    const event = { preventDefault: vi.fn(), returnValue: undefined };

    handler(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});

describe("guardLeave", () => {
  it("lets a clean page follow the link normally", () => {
    const state = guard(true);
    const event = leaveLink("https://example.org/view");

    state.guardLeave(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(false);
  });

  it("holds a dirty page back and asks about the unsaved changes", () => {
    const state = guard(true);
    state.markEditDirty();
    const event = leaveLink("https://example.org/view");

    state.guardLeave(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
    expect(state.leaveUrl).toBe("https://example.org/view");
  });

  it("focuses Keep editing, so the safe choice is the one under the keyboard", () => {
    const state = guard(true);
    state.markEditDirty();

    state.guardLeave(leaveLink("https://example.org/view"));

    expect(state.$refs.keepEditingBtn.focus).toHaveBeenCalled();
  });
});

describe("the discard modal", () => {
  it("forgets the destination when dismissed", () => {
    const state = guard(true);
    state.markEditDirty();
    state.guardLeave(leaveLink("https://example.org/view"));

    state.closeLeaveModal();

    expect(state.leaveModalOpen).toBe(false);
    expect(state.leaveUrl).toBe("");
  });

  it("navigates on discard, without re-triggering the unload prompt", () => {
    const state = guard(true);
    state.markEditDirty();
    state.guardLeave(leaveLink("https://example.org/view"));

    state.discardAndLeave();

    expect(window.location.assign).toHaveBeenCalledWith(
      "https://example.org/view",
    );
    expect(state.leaveGuardSuppressed).toBe(true);
  });

  it("does nothing when there is no destination to go to", () => {
    const state = guard(true);

    state.discardAndLeave();

    expect(window.location.assign).not.toHaveBeenCalled();
  });
});

describe("closePageGuarded - Esc closes the editor modal", () => {
  const LIST_URL = "https://example.org/registration";

  it("navigates a clean page straight back to the pages list", () => {
    guard(false, LIST_URL).closePageGuarded();

    expect(window.location.assign).toHaveBeenCalledWith(LIST_URL);
  });

  it("does nothing when no list URL was configured", () => {
    guard(false).closePageGuarded();

    expect(window.location.assign).not.toHaveBeenCalled();
  });

  it("diverts a dirty page to the discard modal, aimed at the list", () => {
    const state = guard(true, LIST_URL);
    state.markEditDirty();

    state.closePageGuarded();

    expect(window.location.assign).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
    expect(state.leaveUrl).toBe(LIST_URL);
  });

  it("yields while a nested dialog is open - that Esc press belongs to it", () => {
    const state = guard(false, LIST_URL);
    state.confirmCloseOpen = true;

    state.closePageGuarded();

    expect(window.location.assign).not.toHaveBeenCalled();
  });

  it("yields to the discard modal itself, so Esc there means Keep editing", () => {
    const state = guard(true, LIST_URL);
    state.markEditDirty();
    state.closePageGuarded();

    state.closePageGuarded();

    expect(window.location.assign).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
  });

  it("yields while an asset or skeleton dialog is open", () => {
    [
      "skeletonModalOpen",
      "imageUploadModalOpen",
      "imageDetailsModalOpen",
    ].forEach((flag) => {
      const state = guard(false, LIST_URL);
      state[flag] = true;

      state.closePageGuarded();

      expect(window.location.assign).not.toHaveBeenCalled();
    });
  });
});

describe("the close-registration confirmation", () => {
  it("starts closed", () => {
    expect(guard(false).confirmCloseOpen).toBe(false);
  });

  it("focuses Keep it open, since closing is terminal", () => {
    const state = guard(false);

    state.openConfirmClose();

    expect(state.confirmCloseOpen).toBe(true);
    expect(state.$refs.keepOpenBtn.focus).toHaveBeenCalled();
  });

  it("closes again when cancelled", () => {
    const state = guard(false);
    state.openConfirmClose();

    state.cancelConfirmClose();

    expect(state.confirmCloseOpen).toBe(false);
  });
});
