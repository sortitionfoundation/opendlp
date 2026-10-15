// ABOUTME: Tests for the entry point that mounts editors over HTML-editing textareas.
// ABOUTME: Covers mounting the right editor, mounting textareas added later, and destroying removed ones.
import { afterEach, describe, expect, it } from "vitest";
import { editorFor } from "./html-editor.js";

// The observer reacts after the DOM changes, and mounts in a microtask.
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function richControls(id) {
  return `
    <div data-rich-editor-for="${id}" data-rich-editor-label="Intro" hidden>
      <button type="button" data-rich-editor-mode="visual">Visual</button>
      <button type="button" data-rich-editor-mode="html">HTML</button>
      <p data-rich-editor-notice hidden></p>
      <div data-rich-editor-surface></div>
      <div data-rich-editor-code></div>
    </div>`;
}

async function add(html) {
  const holder = document.createElement("div");
  holder.innerHTML = html;
  document.body.appendChild(holder);
  await settle();
  return holder;
}

afterEach(async () => {
  document.body.innerHTML = "";
  await settle();
});

describe("html-editor", () => {
  it("mounts the code editor over a textarea added to the page", async () => {
    const holder = await add(
      '<textarea id="code" data-code-editor><p>a</p></textarea>',
    );
    const textarea = holder.querySelector("textarea");
    expect(editorFor(textarea).view).toBeDefined();
    expect(holder.querySelector(".cm-editor")).not.toBeNull();
  });

  it("mounts the visual editor when the page has its controls", async () => {
    const holder = await add(
      `${richControls("intro")}<textarea id="intro" data-rich-editor><p>a</p></textarea>`,
    );
    expect(editorFor(holder.querySelector("textarea")).editor).toBeDefined();
  });

  it("falls back to the code editor when a visual editor has no controls", async () => {
    const holder = await add(
      '<textarea id="lonely" data-rich-editor><p>a</p></textarea>',
    );
    expect(editorFor(holder.querySelector("textarea")).view).toBeDefined();
  });

  it("mounts each textarea once", async () => {
    const holder = await add(
      '<textarea id="code" data-code-editor><p>a</p></textarea>',
    );
    holder.appendChild(document.createElement("span"));
    await settle();
    expect(holder.querySelectorAll(".cm-editor")).toHaveLength(1);
  });

  it("destroys the editor of a textarea removed from the page", async () => {
    const holder = await add(
      `${richControls("intro")}<textarea id="intro" data-rich-editor><p>a</p></textarea>`,
    );
    const textarea = holder.querySelector("textarea");
    const rich = editorFor(textarea);

    holder.remove();
    await settle();

    expect(rich.editor.isDestroyed).toBe(true);
    expect(editorFor(textarea)).toBeUndefined();
  });

  it("leaves the editors of textareas still on the page alone", async () => {
    const kept = await add(
      '<textarea id="kept" data-code-editor><p>a</p></textarea>',
    );
    const removed = await add(
      '<textarea id="gone" data-code-editor><p>b</p></textarea>',
    );
    const keptEditor = editorFor(kept.querySelector("textarea"));
    const removedEditor = editorFor(removed.querySelector("textarea"));

    removed.remove();
    await settle();

    expect(removedEditor.view.destroyed).toBe(true);
    expect(keptEditor.view.destroyed).toBe(false);
  });
});
