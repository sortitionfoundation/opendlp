// ABOUTME: Unit tests for the home page hero demo's player and its pause button
// ABOUTME: Covers showing the button, pausing and playing on, the off-screen hold beside the visitor's, and reduced motion

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { startHeroDemo } from "./hero-demo.js";

// The hooks the player looks for, as templates/public/_hero_demo.html draws them, without the design.
const DEMO = `
  <div class="hero-demo" data-hero-demo>
    <div class="hero-demo__frame" aria-hidden="true">
      <div data-demo-app>
        <section data-scene="projects"><button data-demo="create-project">Create project</button></section>
        <section data-scene="create">
          <input data-demo="title" data-type="Climate" readonly>
          <input data-demo="size" data-type="30" readonly>
          <button data-demo="submit-create">Create project</button>
        </section>
        <section data-scene="targets">
          <input data-demo="min-1" data-type="14" readonly><input data-demo="max-1" data-type="16" readonly>
          <input data-demo="min-2" data-type="12" readonly><input data-demo="max-2" data-type="14" readonly>
          <input data-demo="min-3" data-type="0" readonly><input data-demo="max-3" data-type="3" readonly>
        </section>
        <section data-scene="selection">
          <div data-demo="status-panel">Selected <span data-demo="held">0</span></div>
          <button data-demo="run">Run Selection</button>
          <p data-demo="history-empty">No selection has been run yet.</p>
          <table data-demo="history" hidden></table>
        </section>
        <section data-scene="dashboard"><div class="hero-demo__pie"></div></section>
        <div data-demo="modal" hidden>
          <div data-demo="modal-done" hidden></div>
          <div data-demo="badge-running"></div>
          <div data-demo="badge-done" hidden></div>
          <div data-demo="progress"><div role="progressbar"><div></div></div></div>
        </div>
      </div>
      <svg data-demo="cursor"></svg>
    </div>
    <button type="button" aria-label="Pause the demo" aria-pressed="false" data-hero-demo-toggle hidden></button>
  </div>`;

// With the cursor's moves made instant, the first screen shows for 900ms, then the click on
// Create project takes 400ms: the second screen shows 1300ms in.
const TO_SECOND_SCREEN = 1300;

let observers;

function setUp({ reducedMotion = false } = {}) {
  window.matchMedia = vi.fn(() => ({ matches: reducedMotion }));
  document.body.innerHTML = DEMO;
  const root = document.querySelector("[data-hero-demo]");
  startHeroDemo(root);
  return {
    root,
    toggle: root.querySelector("[data-hero-demo-toggle]"),
    frame: root.querySelector(".hero-demo__frame"),
    scene: () => root.querySelector(".is-active")?.dataset.scene,
    // What the browser reports when the hero scrolls out of view or back.
    onScreen: (isIntersecting) =>
      observers.forEach((callback) => callback([{ isIntersecting }])),
  };
}

// An animation as getAnimations() returns one, in the state given. Like a browser's, its
// pause() lands a frame late, by when it has moved on; setting currentTime pins it.
function animation(playState, currentTime = 120) {
  const a = { playState, currentTime };
  a.pause = vi.fn(() => {
    a.playState = "paused";
    a.currentTime += 16;
  });
  a.play = vi.fn(() => {
    a.playState = "running";
  });
  return a;
}

beforeEach(() => {
  vi.useFakeTimers();
  observers = [];
  window.IntersectionObserver = class {
    constructor(callback) {
      observers.push(callback);
    }
    observe() {}
  };
  // jsdom has no Web Animations: each move of the cursor finishes at once.
  Element.prototype.animate = vi.fn(() => ({
    finished: Promise.resolve(),
    commitStyles() {},
    cancel() {},
  }));
});

afterEach(() => {
  vi.useRealTimers();
  delete window.IntersectionObserver;
  delete window.matchMedia;
  delete Element.prototype.animate;
  document.body.innerHTML = "";
});

describe("startHeroDemo", () => {
  it("shows the pause button, not pressed, once the demo plays", () => {
    const { root, toggle } = setUp();
    expect(root.classList.contains("is-running")).toBe(true);
    expect(toggle.hidden).toBe(false);
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("leaves the demo at rest and the button hidden for a visitor who prefers reduced motion", async () => {
    const { root, toggle, scene } = setUp({ reducedMotion: true });
    await vi.advanceTimersByTimeAsync(TO_SECOND_SCREEN);
    expect(root.classList.contains("is-running")).toBe(false);
    expect(scene()).toBeUndefined();
    expect(toggle.hidden).toBe(true);
  });

  it("moves on from the first screen", async () => {
    const { scene } = setUp();
    expect(scene()).toBe("projects");
    await vi.advanceTimersByTimeAsync(TO_SECOND_SCREEN);
    expect(scene()).toBe("create");
  });

  it("holds the screen, the typing and the cursor while paused, and plays on when played", async () => {
    const { root, toggle, scene } = setUp();
    const title = root.querySelector('[data-demo="title"]');
    const cursor = root.querySelector('[data-demo="cursor"]');
    // Part way through typing the project title.
    await vi.advanceTimersByTimeAsync(2400);
    expect(scene()).toBe("create");
    expect(title.value).toBe("Clim");

    toggle.click();
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    const held = cursor.style.transform;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(scene()).toBe("create");
    expect(title.value).toBe("Clim");
    expect(cursor.style.transform).toBe(held);

    toggle.click();
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(title.value).toBe("Climate");
    expect(scene()).toBe("targets");
  });

  it("plays on from where it was paused rather than starting the wait again", async () => {
    const { toggle, scene } = setUp();
    // The click on Create project, 100ms in: 300ms of it is left.
    await vi.advanceTimersByTimeAsync(1000);
    toggle.click();
    await vi.advanceTimersByTimeAsync(5_000);
    toggle.click();

    await vi.advanceTimersByTimeAsync(299);
    expect(scene()).toBe("projects");
    await vi.advanceTimersByTimeAsync(1);
    expect(scene()).toBe("create");
  });

  it("keeps the button's name and lets aria-pressed say whether it is paused", () => {
    const { toggle } = setUp();
    toggle.click();
    expect(toggle.getAttribute("aria-label")).toBe("Pause the demo");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    toggle.click();
    expect(toggle.getAttribute("aria-label")).toBe("Pause the demo");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("startHeroDemo off screen", () => {
  it("stops while the hero is off screen and plays on when it is back", async () => {
    const { toggle, scene, onScreen } = setUp();
    onScreen(false);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(scene()).toBe("projects");
    // Scrolling away is not the visitor pausing.
    expect(toggle.getAttribute("aria-pressed")).toBe("false");

    onScreen(true);
    await vi.advanceTimersByTimeAsync(TO_SECOND_SCREEN);
    expect(scene()).toBe("create");
  });

  it("keeps the visitor's pause when the hero leaves the screen and comes back", async () => {
    const { toggle, scene, onScreen } = setUp();
    toggle.click();
    onScreen(false);
    onScreen(true);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(scene()).toBe("projects");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");

    toggle.click();
    await vi.advanceTimersByTimeAsync(TO_SECOND_SCREEN);
    expect(scene()).toBe("create");
  });

  it("waits for the hero to come back when the visitor plays it off screen", async () => {
    const { toggle, scene, onScreen } = setUp();
    onScreen(false);
    toggle.click();
    toggle.click();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(scene()).toBe("projects");

    onScreen(true);
    await vi.advanceTimersByTimeAsync(TO_SECOND_SCREEN);
    expect(scene()).toBe("create");
  });
});

describe("startHeroDemo animations", () => {
  it("pauses the animations running in the frame and plays them on", () => {
    const { toggle, frame } = setUp();
    const moving = animation("running");
    const done = animation("finished");
    frame.getAnimations = vi.fn(() => [moving, done]);

    toggle.click();
    expect(frame.getAnimations).toHaveBeenCalledWith({ subtree: true });
    expect(moving.pause).toHaveBeenCalled();
    expect(done.pause).not.toHaveBeenCalled();

    toggle.click();
    expect(moving.play).toHaveBeenCalled();
    expect(done.play).not.toHaveBeenCalled();
  });

  it("holds an animation at the moment of the pause, not a frame later", () => {
    const { toggle, frame } = setUp();
    const moving = animation("running", 250);
    frame.getAnimations = () => [moving];

    toggle.click();
    expect(moving.currentTime).toBe(250);
  });

  it("does not start again an animation cancelled while paused", () => {
    const { toggle, frame } = setUp();
    const moving = animation("running");
    frame.getAnimations = () => [moving];

    toggle.click();
    moving.playState = "idle";
    toggle.click();
    expect(moving.play).not.toHaveBeenCalled();
  });
});
