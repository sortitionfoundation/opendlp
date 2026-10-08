// ABOUTME: Tests for the visual editor toolbar: commands, aria-pressed/aria-disabled state, arrow-key focus.
// ABOUTME: Drives a real Tiptap editor in jsdom with the same schema the page uses.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Editor } from "@tiptap/core";
import { createSchemaExtensions } from "./rich-editor-schema.js";
import { wireToolbar } from "./rich-editor-toolbar.js";

const COMMAND_NAMES = [
  "paragraph",
  "heading1",
  "heading2",
  "heading3",
  "bold",
  "italic",
  "bulletList",
  "orderedList",
  "link",
  "undo",
  "redo",
];

let editor;
let toolbar;

function button(name) {
  return toolbar.querySelector(`[data-command="${name}"]`);
}

function key(target, name) {
  target.dispatchEvent(
    new KeyboardEvent("keydown", { key: name, bubbles: true }),
  );
}

function selectAll() {
  editor.commands.selectAll();
}

beforeEach(() => {
  document.body.innerHTML = `
    <div role="toolbar" data-rich-editor-toolbar>
      ${COMMAND_NAMES.map((name) => `<button type="button" data-command="${name}">${name}</button>`).join("")}
    </div>
    <div id="surface"></div>`;
  toolbar = document.querySelector("[data-rich-editor-toolbar]");
  editor = new Editor({
    element: document.getElementById("surface"),
    extensions: createSchemaExtensions(),
    content: "<p>Hello world</p>",
    injectCSS: false,
  });
});

afterEach(() => {
  editor.destroy();
  document.body.innerHTML = "";
});

describe("wireToolbar commands", () => {
  it.each([
    ["heading1", "<h1>Hello world</h1>"],
    ["heading2", "<h2>Hello world</h2>"],
    ["heading3", "<h3>Hello world</h3>"],
    ["bold", "<p><strong>Hello world</strong></p>"],
    ["italic", "<p><em>Hello world</em></p>"],
    ["bulletList", "<ul><li><p>Hello world</p></li></ul>"],
    ["orderedList", "<ol><li><p>Hello world</p></li></ol>"],
  ])("%s formats the selection", (name, expected) => {
    wireToolbar(toolbar, editor);
    selectAll();
    button(name).click();
    expect(editor.getHTML()).toBe(expected);
  });

  it("turns a heading back into a paragraph", () => {
    editor.commands.setContent("<h2>Title</h2>");
    wireToolbar(toolbar, editor);
    button("paragraph").click();
    expect(editor.getHTML()).toBe("<p>Title</p>");
  });

  it("undoes and redoes", () => {
    wireToolbar(toolbar, editor);
    selectAll();
    button("bold").click();
    button("undo").click();
    expect(editor.getHTML()).toBe("<p>Hello world</p>");
    button("redo").click();
    expect(editor.getHTML()).toBe("<p><strong>Hello world</strong></p>");
  });

  it("hands commands that leave the editor to the given actions", () => {
    const link = vi.fn();
    wireToolbar(toolbar, editor, { link });
    button("link").click();
    expect(link).toHaveBeenCalledOnce();
  });
});

describe("wireToolbar state", () => {
  it("presses the toggles that match the selection", () => {
    editor.commands.setContent("<h2><strong>Title</strong></h2>");
    wireToolbar(toolbar, editor);
    editor.commands.setTextSelection(2);
    expect(button("heading2").getAttribute("aria-pressed")).toBe("true");
    expect(button("bold").getAttribute("aria-pressed")).toBe("true");
    expect(button("heading1").getAttribute("aria-pressed")).toBe("false");
    expect(button("paragraph").getAttribute("aria-pressed")).toBe("false");
  });

  it("follows the selection as it moves", () => {
    editor.commands.setContent("<p>plain</p><h1>big</h1>");
    wireToolbar(toolbar, editor);
    editor.commands.setTextSelection(2);
    expect(button("paragraph").getAttribute("aria-pressed")).toBe("true");
    editor.commands.setTextSelection(9);
    expect(button("heading1").getAttribute("aria-pressed")).toBe("true");
    expect(button("paragraph").getAttribute("aria-pressed")).toBe("false");
  });

  it("marks undo and redo unavailable until there is something to undo or redo", () => {
    wireToolbar(toolbar, editor);
    expect(button("undo").getAttribute("aria-disabled")).toBe("true");
    expect(button("redo").getAttribute("aria-disabled")).toBe("true");
    selectAll();
    button("bold").click();
    expect(button("undo").getAttribute("aria-disabled")).toBe("false");
    button("undo").click();
    expect(button("redo").getAttribute("aria-disabled")).toBe("false");
  });

  it("ignores a click on an unavailable command", () => {
    wireToolbar(toolbar, editor);
    button("redo").click();
    expect(editor.getHTML()).toBe("<p>Hello world</p>");
  });

  it("does not put aria-pressed on commands that are not toggles", () => {
    wireToolbar(toolbar, editor);
    for (const name of ["link", "undo", "redo"]) {
      expect(button(name).hasAttribute("aria-pressed")).toBe(false);
    }
  });
});

describe("wireToolbar keyboard", () => {
  it("gives the toolbar a single Tab stop", () => {
    wireToolbar(toolbar, editor);
    const stops = toolbar.querySelectorAll('[tabindex="0"]');
    expect(stops).toHaveLength(1);
    expect(stops[0]).toBe(button("paragraph"));
  });

  it("moves focus with the arrow keys, wrapping at the ends", () => {
    wireToolbar(toolbar, editor);
    button("paragraph").focus();
    key(button("paragraph"), "ArrowRight");
    expect(document.activeElement).toBe(button("heading1"));
    expect(button("heading1").getAttribute("tabindex")).toBe("0");
    expect(button("paragraph").getAttribute("tabindex")).toBe("-1");
    key(button("heading1"), "ArrowLeft");
    key(button("paragraph"), "ArrowLeft");
    expect(document.activeElement).toBe(button("redo"));
    key(button("redo"), "ArrowRight");
    expect(document.activeElement).toBe(button("paragraph"));
  });

  it("jumps to the first and last buttons with Home and End", () => {
    wireToolbar(toolbar, editor);
    button("paragraph").focus();
    key(button("paragraph"), "End");
    expect(document.activeElement).toBe(button("redo"));
    key(button("redo"), "Home");
    expect(document.activeElement).toBe(button("paragraph"));
  });
});
