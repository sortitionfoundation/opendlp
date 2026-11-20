// ABOUTME: Unit tests for the pausable clock behind the home page hero demo's timeline
// ABOUTME: Covers waits counting only running time, holds for separate reasons, and the stop and start callbacks

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { pausableClock } from "./pausable-clock.js";

// A wait that records when it resolves, so a test can ask whether it has.
function track(promise) {
  const state = { done: false };
  promise.then(() => {
    state.done = true;
  });
  return state;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("pausableClock", () => {
  it("resolves a wait once its time has run", async () => {
    const clock = pausableClock();
    const wait = track(clock.sleep(500));

    await vi.advanceTimersByTimeAsync(499);
    expect(wait.done).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(wait.done).toBe(true);
  });

  it("freezes a wait while held, and runs only the time left once released", async () => {
    const clock = pausableClock();
    const wait = track(clock.sleep(500));

    await vi.advanceTimersByTimeAsync(300);
    clock.hold("visitor");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(wait.done).toBe(false);

    clock.release("visitor");
    await vi.advanceTimersByTimeAsync(199);
    expect(wait.done).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(wait.done).toBe(true);
  });

  it("starts a wait asked for while held only once released", async () => {
    const clock = pausableClock();
    clock.hold("visitor");
    const wait = track(clock.sleep(100));

    await vi.advanceTimersByTimeAsync(5_000);
    expect(wait.done).toBe(false);
    clock.release("visitor");
    await vi.advanceTimersByTimeAsync(100);
    expect(wait.done).toBe(true);
  });

  it("stays stopped until every reason holding it is released", async () => {
    const clock = pausableClock();
    const wait = track(clock.sleep(100));

    clock.hold("offscreen");
    clock.hold("visitor");
    clock.release("offscreen");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(clock.running).toBe(false);
    expect(wait.done).toBe(false);

    clock.release("visitor");
    expect(clock.running).toBe(true);
    await vi.advanceTimersByTimeAsync(100);
    expect(wait.done).toBe(true);
  });

  it("counts a second hold for the same reason as one", async () => {
    const clock = pausableClock();
    clock.hold("visitor");
    clock.hold("visitor");
    clock.release("visitor");
    expect(clock.running).toBe(true);
    expect(clock.isHeld("visitor")).toBe(false);
  });

  it("ignores the release of a reason that does not hold it", async () => {
    const onChange = vi.fn();
    const clock = pausableClock({ onChange });
    const wait = track(clock.sleep(100));

    clock.release("visitor");
    expect(onChange).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(100);
    expect(wait.done).toBe(true);
  });

  it("says when it stops and when it starts again, once each", () => {
    const onChange = vi.fn();
    const clock = pausableClock({ onChange });

    clock.hold("visitor");
    clock.hold("offscreen");
    expect(onChange.mock.calls).toEqual([[false]]);

    clock.release("visitor");
    expect(onChange.mock.calls).toEqual([[false]]);
    clock.release("offscreen");
    expect(onChange.mock.calls).toEqual([[false], [true]]);
  });

  it("names the reasons that hold it", () => {
    const clock = pausableClock();
    clock.hold("offscreen");
    expect(clock.isHeld("offscreen")).toBe(true);
    expect(clock.isHeld("visitor")).toBe(false);
  });
});
