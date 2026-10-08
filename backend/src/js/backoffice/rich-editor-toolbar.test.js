// ABOUTME: Tests for the visual editor toolbar: commands, aria-pressed/aria-disabled state, arrow-key focus.
// ABOUTME: Drives a real Tiptap editor in jsdom with the same schema the page uses.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Editor } from "@tiptap/core";
import { createSchemaExtensions } from "./rich-editor-schema.js";
import {
  TOOLTIPS_DISMISSED_CLASS,
  wireToolbar,
} from "./rich-editor-toolbar.js";

const COMMAND_NAMES = [
  "paragraph",
  "heading1",
  "heading2",
  "heading3",
  "bold",
  "italic",
  "bulletList",
  "orderedList",
  "underline",
  "strike",
  "blockquote",
  "horizontalRule",
  "link",
];
const TABLE_ITEMS = [
  "insertTable",
  "addRowAfter",
  "addColumnAfter",
  "deleteRow",
  "deleteColumn",
  "deleteTable",
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
      <button type="button" data-command="table" aria-haspopup="menu" aria-expanded="false" aria-controls="table-menu">table</button>
      <div id="table-menu" role="menu" hidden>
        ${TABLE_ITEMS.map((name) => `<button type="button" role="menuitem" data-command="${name}">${name}</button>`).join("")}
      </div>
      <button type="button" data-command="undo">undo</button>
      <button type="button" data-command="redo">redo</button>
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
    ["underline", "<p><u>Hello world</u></p>"],
    ["strike", "<p><s>Hello world</s></p>"],
    ["blockquote", "<blockquote><p>Hello world</p></blockquote>"],
  ])("%s formats the selection", (name, expected) => {
    wireToolbar(toolbar, editor);
    selectAll();
    button(name).click();
    expect(editor.getHTML()).toBe(expected);
  });

  it("inserts a horizontal rule", () => {
    wireToolbar(toolbar, editor);
    editor.commands.setTextSelection(12);
    button("horizontalRule").click();
    expect(editor.getHTML()).toContain("<p>Hello world</p><hr>");
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

describe("wireToolbar table menu", () => {
  const menu = () => document.getElementById("table-menu");
  const item = (name) => menu().querySelector(`[data-command="${name}"]`);

  function cellsPerRow() {
    return Array.from(
      editor.view.dom.querySelectorAll("tr"),
      (row) => row.children.length,
    );
  }

  it("opens on click, focusing the first item", () => {
    wireToolbar(toolbar, editor);
    button("table").click();
    expect(menu().hidden).toBe(false);
    expect(button("table").getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(item("insertTable"));
  });

  it("opens with the up arrow on its last item", () => {
    wireToolbar(toolbar, editor);
    button("table").focus();
    key(button("table"), "ArrowUp");
    expect(document.activeElement).toBe(item("deleteTable"));
  });

  it("moves between items with the arrow keys, wrapping at the ends", () => {
    wireToolbar(toolbar, editor);
    button("table").click();
    key(item("insertTable"), "ArrowUp");
    expect(document.activeElement).toBe(item("deleteTable"));
    key(item("deleteTable"), "ArrowDown");
    expect(document.activeElement).toBe(item("insertTable"));
    key(item("insertTable"), "End");
    expect(document.activeElement).toBe(item("deleteTable"));
  });

  it("closes on Escape, returning focus to the menu button, and keeps the Escape from a dialog", () => {
    wireToolbar(toolbar, editor);
    const outside = vi.fn();
    document.addEventListener("keydown", outside);
    button("table").click();

    key(item("insertTable"), "Escape");

    document.removeEventListener("keydown", outside);
    expect(menu().hidden).toBe(true);
    expect(button("table").getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(button("table"));
    expect(outside).not.toHaveBeenCalled();
  });

  it("is not part of the toolbar's arrow-key order", () => {
    wireToolbar(toolbar, editor);
    button("table").focus();
    key(button("table"), "ArrowRight");
    expect(document.activeElement).toBe(button("undo"));
  });

  it("inserts a plain two-by-two table and closes", () => {
    wireToolbar(toolbar, editor);
    editor.commands.setTextSelection(12);
    button("table").click();
    item("insertTable").click();
    expect(menu().hidden).toBe(true);
    expect(editor.getHTML()).toContain(
      "<table><tbody><tr><td><p></p></td><td><p></p></td></tr><tr><td><p></p></td><td><p></p></td></tr></tbody></table>",
    );
  });

  it("offers only insert outside a table, and only the edits inside one", () => {
    wireToolbar(toolbar, editor);
    button("table").click();
    expect(item("insertTable").getAttribute("aria-disabled")).toBe("false");
    for (const name of TABLE_ITEMS.slice(1)) {
      expect(item(name).getAttribute("aria-disabled")).toBe("true");
    }
    item("insertTable").click();
    button("table").click();
    expect(item("insertTable").getAttribute("aria-disabled")).toBe("true");
    for (const name of TABLE_ITEMS.slice(1)) {
      expect(item(name).getAttribute("aria-disabled")).toBe("false");
    }
  });

  it("adds and deletes rows and columns, and deletes the table", () => {
    editor.commands.setContent("<table><tr><td>a</td><td>b</td></tr></table>");
    editor.commands.setTextSelection(3);
    wireToolbar(toolbar, editor);
    item("addRowAfter").click();
    expect(cellsPerRow()).toEqual([2, 2]);
    item("addColumnAfter").click();
    expect(cellsPerRow()).toEqual([3, 3]);
    item("deleteColumn").click();
    item("deleteRow").click();
    expect(cellsPerRow()).toEqual([2]);
    item("deleteTable").click();
    expect(editor.getHTML()).not.toContain("<table");
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

  it("reaches the toolbar's current button from the text with Alt+F10, keeping the cursor", () => {
    editor.commands.setContent("<table><tr><td>a</td><td>b</td></tr></table>");
    editor.commands.setTextSelection(9);
    wireToolbar(toolbar, editor);
    button("paragraph").focus();
    key(button("paragraph"), "End");

    editor.view.dom.dispatchEvent(
      new KeyboardEvent("keydown", { key: "F10", altKey: true, bubbles: true }),
    );

    expect(document.activeElement).toBe(button("redo"));
    expect(editor.state.selection.$from.parent.textContent).toBe("b");
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

describe("wireToolbar tooltips", () => {
  function escape(target) {
    const event = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    });
    target.dispatchEvent(event);
    return event;
  }

  it("hides the tooltip on the first Escape without letting it close anything else", () => {
    wireToolbar(toolbar, editor);
    const outside = vi.fn();
    document.addEventListener("keydown", outside);
    button("bold").focus();

    const event = escape(button("bold"));

    document.removeEventListener("keydown", outside);
    expect(toolbar.classList.contains(TOOLTIPS_DISMISSED_CLASS)).toBe(true);
    expect(event.defaultPrevented).toBe(true);
    expect(outside).not.toHaveBeenCalled();
  });

  it("lets a second Escape through to the dialog", () => {
    wireToolbar(toolbar, editor);
    const outside = vi.fn();
    document.addEventListener("keydown", outside);
    escape(button("bold"));

    escape(button("bold"));

    document.removeEventListener("keydown", outside);
    expect(outside).toHaveBeenCalledOnce();
  });

  it("shows tooltips again when focus or the pointer moves to another button", () => {
    wireToolbar(toolbar, editor);
    button("paragraph").focus();
    escape(button("paragraph"));
    key(button("paragraph"), "ArrowRight");
    expect(toolbar.classList.contains(TOOLTIPS_DISMISSED_CLASS)).toBe(false);

    escape(button("heading1"));
    button("bold").dispatchEvent(new MouseEvent("mouseenter"));
    expect(toolbar.classList.contains(TOOLTIPS_DISMISSED_CLASS)).toBe(false);
  });
});
