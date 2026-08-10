// ABOUTME: Unit tests for the autoDismissAlert Alpine component
// ABOUTME: Covers the countdown, and pausing and resuming it on pointer enter and leave

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { autoDismissAlert } from "./auto-dismiss-alert.js";

describe("autoDismissAlert", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts visible", () => {
    expect(autoDismissAlert({ duration: 4000 }).show).toBe(true);
  });

  it("hides itself once the duration elapses", () => {
    const state = autoDismissAlert({ duration: 4000 });
    state.init();
    vi.advanceTimersByTime(4000);
    expect(state.show).toBe(false);
  });

  it("is still visible just before the duration elapses", () => {
    const state = autoDismissAlert({ duration: 4000 });
    state.init();
    vi.advanceTimersByTime(3999);
    expect(state.show).toBe(true);
  });

  it("never dismisses when the duration is zero", () => {
    const state = autoDismissAlert({ duration: 0 });
    state.init();
    vi.advanceTimersByTime(60000);
    expect(state.show).toBe(true);
  });

  it("never dismisses when given no options at all", () => {
    const state = autoDismissAlert();
    state.init();
    vi.advanceTimersByTime(60000);
    expect(state.show).toBe(true);
  });

  it("stays visible while paused", () => {
    const state = autoDismissAlert({ duration: 4000 });
    state.init();
    vi.advanceTimersByTime(1000);
    state.pause();
    vi.advanceTimersByTime(60000);
    expect(state.show).toBe(true);
  });

  it("resumes with only the remaining time left to run", () => {
    const state = autoDismissAlert({ duration: 4000 });
    state.init();
    vi.advanceTimersByTime(1000);
    state.pause();
    state.resume();

    vi.advanceTimersByTime(2999);
    expect(state.show).toBe(true);
    vi.advanceTimersByTime(1);
    expect(state.show).toBe(false);
  });

  it("ignores resume when it was never running", () => {
    const state = autoDismissAlert({ duration: 0 });
    state.init();
    state.resume();
    vi.advanceTimersByTime(60000);
    expect(state.show).toBe(true);
  });

  it("ignores a pause when no timer is running", () => {
    const state = autoDismissAlert({ duration: 4000 });
    state.pause();
    expect(state.remaining).toBe(4000);
  });
});
