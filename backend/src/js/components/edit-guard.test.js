// ABOUTME: Tests for the shared unsaved-changes guard
// ABOUTME: Covers the beforeunload backstop, the discard dialog and the link interception

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { editGuard } from "./edit-guard.js";

let realLocation;

beforeEach(() => {
  realLocation = window.location;
  delete window.location;
  window.location = { assign: vi.fn(), href: "https://example.org/edit" };
  document.body.innerHTML = "";
});

afterEach(() => {
  window.location = realLocation;
  vi.restoreAllMocks();
});

/**
 * The guard reaches for Alpine's $nextTick and $refs, which Alpine supplies at
 * runtime. Driving the returned object directly means supplying them here.
 */
function guard(options) {
  const state = editGuard(options);
  state.$nextTick = (callback) => callback();
  state.$refs = { keepEditingBtn: { focus: vi.fn() } };
  return state;
}

/**
 * Put the guard's own click handler to a click on the given markup.
 *
 * The handler is taken off the spy rather than reached through a dispatch,
 * because it is registered on the document for the life of the page: dispatched
 * events would carry between tests, and there is no way to take it back off.
 *
 * @param {Object} state - a guard that has not been initialised yet
 * @param {string} html - the markup to click in, holding one link
 * @param {Object} [overrides] - properties to change on the click
 * @returns {Object} the click the handler saw
 */
function guardedClick(state, html, overrides = {}) {
  const listeners = vi.spyOn(document, "addEventListener");
  state.initEditGuard();
  const handler = listeners.mock.calls.find((c) => c[0] === "click")[1];

  document.body.innerHTML = html;
  const event = Object.assign(
    {
      button: 0,
      defaultPrevented: false,
      target: document.querySelector("a"),
      preventDefault: vi.fn(),
    },
    overrides,
  );
  handler(event);
  return event;
}

describe("the beforeunload backstop", () => {
  it("stays quiet while the page is clean", () => {
    const listeners = vi.spyOn(window, "addEventListener");
    guard().initEditGuard();

    const handler = listeners.mock.calls.find(
      (c) => c[0] === "beforeunload",
    )[1];
    const event = { preventDefault: vi.fn(), returnValue: undefined };
    handler(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("speaks up once there are edits to lose", () => {
    const listeners = vi.spyOn(window, "addEventListener");
    const state = guard();
    state.initEditGuard();
    state.markEditDirty();

    const handler = listeners.mock.calls.find(
      (c) => c[0] === "beforeunload",
    )[1];
    const event = { preventDefault: vi.fn(), returnValue: undefined };
    handler(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.returnValue).toBe("");
  });

  it("stands down once leaving has been agreed to", () => {
    const listeners = vi.spyOn(window, "addEventListener");
    const state = guard();
    state.initEditGuard();
    state.markEditDirty();
    state.allowLeave();

    const handler = listeners.mock.calls.find(
      (c) => c[0] === "beforeunload",
    )[1];
    const event = { preventDefault: vi.fn(), returnValue: undefined };
    handler(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});

describe("guardLeave on a single link", () => {
  it("lets a clean page follow the link", () => {
    const state = guard();
    const event = {
      preventDefault: vi.fn(),
      currentTarget: { href: "/elsewhere" },
    };
    state.guardLeave(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(false);
  });

  it("holds a dirty page back and remembers where it was going", () => {
    const state = guard();
    state.markEditDirty();
    const event = {
      preventDefault: vi.fn(),
      currentTarget: { href: "/elsewhere" },
    };
    state.guardLeave(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
    expect(state.leaveUrl).toBe("/elsewhere");
    expect(state.$refs.keepEditingBtn.focus).toHaveBeenCalled();
  });
});

describe("the discard dialog", () => {
  it("keeps the edits and forgets the destination when closed", () => {
    const state = guard();
    state.openLeaveModal("/elsewhere");
    state.closeLeaveModal();

    expect(state.leaveModalOpen).toBe(false);
    expect(state.leaveUrl).toBe("");
    expect(state.editDirty).toBe(false);
    expect(window.location.assign).not.toHaveBeenCalled();
  });

  it("goes where it was headed, past its own beforeunload, on discard", () => {
    const state = guard();
    state.markEditDirty();
    state.openLeaveModal("/elsewhere");
    state.discardAndLeave();

    expect(window.location.assign).toHaveBeenCalledWith("/elsewhere");
    expect(state.wouldLoseEdits()).toBe(false);
  });

  it("does nothing without a destination", () => {
    const state = guard();
    state.discardAndLeave();

    expect(window.location.assign).not.toHaveBeenCalled();
  });
});

describe("intercepting links across the page", () => {
  it("is not wired up unless the page asks for it", () => {
    const listeners = vi.spyOn(document, "addEventListener");
    guard().initEditGuard();

    expect(listeners.mock.calls.some((c) => c[0] === "click")).toBe(false);
  });

  it("holds back a click that would leave with unsaved edits", () => {
    const state = guard({ guardLinks: true });
    state.markEditDirty();

    const event = guardedClick(state, '<a href="/dashboard">Dashboard</a>');

    expect(event.preventDefault).toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
    expect(state.leaveUrl).toContain("/dashboard");
  });

  it("catches a click on something inside the link", () => {
    const state = guard({ guardLinks: true });
    state.markEditDirty();

    const event = guardedClick(
      state,
      '<a href="/dashboard"><span id="in">Go</span></a>',
      {},
    );
    // The click landed on the span; the guard walked up to the link.
    expect(event.preventDefault).toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(true);
  });

  it("lets every link through while the page is clean", () => {
    const state = guard({ guardLinks: true });

    const event = guardedClick(state, '<a href="/dashboard">Dashboard</a>');

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(false);
  });

  it.each([
    ["a jump within this page", '<a href="#section">Section</a>', {}],
    ["a download", '<a href="/f.csv" download>Get</a>', {}],
    ["a link opening elsewhere", '<a href="/x" target="_blank">New</a>', {}],
    ["an opted-out link", '<a href="/x" data-no-leave-guard>Skip</a>', {}],
    ["a new-tab click", '<a href="/x">X</a>', { metaKey: true }],
    ["a middle click", '<a href="/x">X</a>', { button: 1 }],
    [
      "a click something else already took",
      '<a href="/x">X</a>',
      { defaultPrevented: true },
    ],
  ])("leaves %s alone", (_name, html, overrides) => {
    const state = guard({ guardLinks: true });
    state.markEditDirty();

    const event = guardedClick(state, html, overrides);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.leaveModalOpen).toBe(false);
  });

  it("stops guarding once the user has agreed to leave", () => {
    const state = guard({ guardLinks: true });
    state.markEditDirty();
    state.allowLeave();

    const event = guardedClick(state, '<a href="/dashboard">Dashboard</a>');

    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});
