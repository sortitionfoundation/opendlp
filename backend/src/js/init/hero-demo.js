// ABOUTME: Plays the home page hero demo: one cursor works through five simplified backoffice screens
// ABOUTME: (create a project, set targets, run the selection, see the result), on a loop, with a pause button.
//
// The markup is templates/public/_hero_demo.html, the styles the .hero-demo rules in main.css. The script finds every target by its data-demo name and
// reads what to type from data-type, so it carries no words and works at any width and in any language.
// Under prefers-reduced-motion it only sizes the window, and the stylesheet shows the last scene at rest.
//
// Every wait in the timeline is a wait on one pausable clock, so the demo can stop where it is and later play on
// from there. Two things hold the clock: the visitor's pause button, and the hero being off screen. They are separate
// holds, so the hero coming back on screen never undoes the visitor's pause. A hold also pauses the animations
// already running in the frame - a move of the cursor, a click, the pies drawing, the fade between loops - and
// releasing the last hold plays them on.

import { pausableClock } from "../lib/pausable-clock.js";

const WIDTH = 800;

// The two reasons the demo stops.
const VISITOR = "visitor";
const OFFSCREEN = "offscreen";

/**
 * Pause the animations running inside the element, CSS transitions included,
 * and return a function that plays them on.
 */
function freezeAnimations(element) {
  if (typeof element.getAnimations !== "function") return () => {};
  const running = element
    .getAnimations({ subtree: true })
    .filter((animation) => animation.playState === "running");
  running.forEach((animation) => animation.pause());
  // One that has since been cancelled stays cancelled: playing it would start it again.
  return () =>
    running
      .filter((animation) => animation.playState === "paused")
      .forEach((animation) => animation.play());
}

/**
 * Play the demo in root, and wire its pause button.
 *
 * @param {HTMLElement} root the element marked data-hero-demo
 */
export function startHeroDemo(root) {
  const cursor = root.querySelector('[data-demo="cursor"]');
  const frame = root.querySelector(".hero-demo__frame");
  const toggle = root.querySelector("[data-hero-demo-toggle]");
  const el = (name) => root.querySelector(`[data-demo="${name}"]`);
  const scenes = [...root.querySelectorAll("[data-scene]")];
  let cx = 600;
  let cy = 420;
  let scale = 1;

  const fit = () => {
    scale = Math.min(1, root.clientWidth / WIDTH);
    root.style.setProperty("--hero-demo-scale", scale);
  };
  fit();
  // A ResizeObserver also catches the frame appearing, e.g. when the showcase opens its tab.
  if ("ResizeObserver" in window) new ResizeObserver(fit).observe(root);
  else window.addEventListener("resize", fit);
  // Reduced motion: the window is sized, and the stylesheet keeps the last scene at rest.
  // Nothing moves, so the pause button stays hidden.
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  let thaw = () => {};
  const clock = pausableClock({
    onChange: (running) => {
      if (!running) {
        thaw = freezeAnimations(frame);
        return;
      }
      thaw();
      thaw = () => {};
    },
  });
  const sleep = (ms) => clock.sleep(ms);

  // The button's name stays "Pause the demo"; aria-pressed says whether it is paused.
  if (toggle) {
    toggle.addEventListener("click", () => {
      const pause = toggle.getAttribute("aria-pressed") !== "true";
      toggle.setAttribute("aria-pressed", String(pause));
      if (pause) clock.hold(VISITOR);
      else clock.release(VISITOR);
    });
    toggle.hidden = false;
  }

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) clock.release(OFFSCREEN);
        else clock.hold(OFFSCREEN);
      },
      { threshold: 0.2 },
    ).observe(root);
  }

  const show = (name) =>
    scenes.forEach((s) =>
      s.classList.toggle("is-active", s.dataset.scene === name),
    );

  // The cursor lives in the frame, unscaled; targets live in the scaled app layer.
  const centreOf = (target) => {
    const t = target.getBoundingClientRect();
    const f = frame.getBoundingClientRect();
    return [t.left - f.left + t.width * 0.5, t.top - f.top + t.height * 0.55];
  };
  const moveTo = async (target, ms = 700) => {
    if (!target) return; // a missing target is skipped rather than stopping the loop
    const [x, y] = centreOf(target);
    const anim = cursor.animate(
      [
        { transform: `translate(${cx}px, ${cy}px)` },
        { transform: `translate(${x}px, ${y}px)` },
      ],
      { duration: ms, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" },
    );
    await anim.finished;
    anim.commitStyles();
    anim.cancel();
    cursor.style.transform = `translate(${x}px, ${y}px)`;
    cx = x;
    cy = y;
  };
  // A click is a small dip of the cursor to the bottom right and back, and the target pressed meanwhile.
  const click = async (target) => {
    if (!target) return;
    cursor.classList.add("is-nudging");
    cursor.style.transform = `translate(${cx + 3}px, ${cy + 3}px)`;
    target.classList.add("is-pressed-btn");
    await sleep(90);
    cursor.style.transform = `translate(${cx}px, ${cy}px)`;
    await sleep(90);
    cursor.classList.remove("is-nudging");
    target.classList.remove("is-pressed-btn");
    await sleep(220);
  };
  const type = async (input, perChar = 55) => {
    if (!input) return;
    const text = input.dataset.type || "";
    input.classList.add("is-typing");
    input.value = "";
    for (const ch of text) {
      input.value += ch;
      await sleep(perChar);
    }
    await sleep(250);
    input.classList.remove("is-typing");
  };
  const reset = () => {
    root.querySelectorAll("[data-type]").forEach((i) => {
      i.value = "";
    });
    el("status-panel").classList.remove("is-done");
    el("held").textContent = "0";
    el("history").hidden = true;
    el("history-empty").hidden = false;
    el("modal").hidden = true;
    el("modal-done").hidden = true;
    el("badge-running").hidden = false;
    el("badge-done").hidden = true;
    el("progress").hidden = false;
    root
      .querySelectorAll(".hero-demo__pie")
      .forEach((p) => p.classList.remove("is-drawn"));
    cx = 600;
    cy = 420;
    cursor.style.transform = `translate(${cx}px, ${cy}px)`;
  };

  const run = async () => {
    root.classList.add("is-running");
    for (;;) {
      reset();
      show("projects");
      await sleep(900);
      await moveTo(el("create-project"));
      await click(el("create-project"));
      show("create");
      await sleep(500);
      await moveTo(el("title"));
      await click(el("title"));
      await type(el("title"));
      await moveTo(el("size"), 500);
      await click(el("size"));
      await type(el("size"), 120);
      await moveTo(el("submit-create"));
      await click(el("submit-create"));
      show("targets");
      await sleep(700);
      for (const row of [1, 2, 3]) {
        await moveTo(el(`min-${row}`), 450);
        await click(el(`min-${row}`));
        await type(el(`min-${row}`), 110);
        await moveTo(el(`max-${row}`), 350);
        await click(el(`max-${row}`));
        await type(el(`max-${row}`), 110);
      }
      await sleep(500);
      show("selection");
      await sleep(700);
      await moveTo(el("run"));
      await click(el("run"));
      el("modal").hidden = false;
      const bar = el("progress").querySelector("[role=progressbar] > div");
      for (let p = 0; p <= 100; p += 4) {
        bar.style.width = `${p}%`;
        await sleep(90);
      }
      el("badge-running").hidden = true;
      el("badge-done").hidden = false;
      el("progress").hidden = true;
      el("modal-done").hidden = false;
      await sleep(1600);
      el("modal").hidden = true;
      el("status-panel").classList.add("is-done");
      el("held").textContent = "30";
      el("history-empty").hidden = true;
      el("history").hidden = false;
      await sleep(2200);
      show("dashboard");
      await sleep(300);
      root
        .querySelectorAll(".hero-demo__pie")
        .forEach((p, i) =>
          sleep(i * 250).then(() => p.classList.add("is-drawn")),
        );
      await sleep(5000);
      root.classList.add("is-fading");
      await sleep(650);
      root.classList.remove("is-fading");
    }
  };
  run();
}

/**
 * Play every hero demo on the page.
 */
export function initHeroDemos() {
  document
    .querySelectorAll("[data-hero-demo]")
    .forEach((root) => startHeroDemo(root));
}
