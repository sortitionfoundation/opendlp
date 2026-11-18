// ABOUTME: Plays the home page hero demo: one cursor works through five simplified backoffice screens
// ABOUTME: (create a project, set targets, run the selection, see the result), on a loop, paused off screen.
//
// The markup is templates/public/_hero_demo.html, the styles the .hero-demo rules in main.css. The script finds every target by its data-demo name and
// reads what to type from data-type, so it carries no words and works at any width and in any language.
// Under prefers-reduced-motion it only sizes the window, and the stylesheet shows the last scene at rest.

const WIDTH = 800;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function startHeroDemo(root) {
  const cursor = root.querySelector('[data-demo="cursor"]');
  const el = (name) => root.querySelector(`[data-demo="${name}"]`);
  const scenes = [...root.querySelectorAll("[data-scene]")];
  let cx = 600;
  let cy = 420;
  let visible = true;
  let scale = 1;

  const fit = () => {
    scale = Math.min(1, root.clientWidth / WIDTH);
    root.style.setProperty("--hero-demo-scale", scale);
  };
  fit();
  window.addEventListener("resize", fit);
  // Reduced motion: the window is sized, and the stylesheet keeps the last scene at rest.
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
      },
      { threshold: 0.2 },
    ).observe(root);
  }
  const whenVisible = async () => {
    while (!visible) await sleep(300);
  };

  const show = (name) =>
    scenes.forEach((s) =>
      s.classList.toggle("is-active", s.dataset.scene === name),
    );

  // The cursor lives in the frame, unscaled; targets live in the scaled app layer.
  const centreOf = (target) => {
    const t = target.getBoundingClientRect();
    const f = root.querySelector(".hero-demo__frame").getBoundingClientRect();
    return [t.left - f.left + t.width * 0.5, t.top - f.top + t.height * 0.55];
  };
  const moveTo = async (target, ms = 700) => {
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
      await whenVisible();
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
          setTimeout(() => p.classList.add("is-drawn"), i * 250),
        );
      await sleep(5000);
      root.classList.add("is-fading");
      await sleep(650);
      root.classList.remove("is-fading");
    }
  };
  run();
}

document.querySelectorAll("[data-hero-demo]").forEach(startHeroDemo);
