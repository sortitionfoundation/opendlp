// ABOUTME: Tests for the visual editor's schema and its template-variable finder.
// ABOUTME: Builds ProseMirror documents from HTML with the same extensions the editor uses.
import { describe, expect, it } from "vitest";
import { Editor, generateJSON, getSchema } from "@tiptap/core";
import {
  createSchemaExtensions,
  findVariableRanges,
} from "./rich-editor-schema.js";

const extensions = createSchemaExtensions();
const schema = getSchema(extensions);

function docFrom(html) {
  return schema.nodeFromJSON(generateJSON(html, extensions));
}

function variablesIn(html) {
  const doc = docFrom(html);
  return findVariableRanges(doc).map(({ from, to }) =>
    doc.textBetween(from, to),
  );
}

describe("findVariableRanges", () => {
  it("finds simple and dotted variables", () => {
    expect(
      variablesIn("<p>{{ x }} and {{assembly.title}}</p><h1>{{ y }}</h1>"),
    ).toEqual(["{{ x }}", "{{assembly.title}}", "{{ y }}"]);
  });

  it("ignores things that only look like variables", () => {
    expect(variablesIn("<p>{ x } {{ }} {{ 1x }} {x}}</p>")).toEqual([]);
  });

  it("finds variables inside formatted text", () => {
    expect(variablesIn("<p><strong>{{ assembly_title }}</strong></p>")).toEqual(
      ["{{ assembly_title }}"],
    );
  });
});

describe("createSchemaExtensions", () => {
  it("only offers headings at levels 1 to 3", () => {
    expect(schema.nodes.heading.attrs.level).toBeDefined();
    expect(docFrom("<h3>a</h3>").firstChild.attrs.level).toBe(3);
    expect(docFrom("<h4>a</h4>").firstChild.type.name).not.toBe("heading");
  });

  it("leaves out the marks and nodes that have no toolbar button", () => {
    expect(schema.marks.code).toBeUndefined();
    expect(schema.nodes.codeBlock).toBeUndefined();
  });

  it("holds the formatting and blocks the toolbar can make", () => {
    for (const name of ["underline", "strike"]) {
      expect(schema.marks[name]).toBeDefined();
    }
    for (const name of [
      "blockquote",
      "horizontalRule",
      "table",
      "tableRow",
      "tableHeader",
      "tableCell",
    ]) {
      expect(schema.nodes[name]).toBeDefined();
    }
  });

  it("keeps a table's border and role, and class and style on its cells", () => {
    const table = docFrom(
      '<table border="0" role="presentation"><tr><td class="c" style="color: red;">a</td></tr></table>',
    ).firstChild;
    expect(table.attrs).toMatchObject({ border: "0", role: "presentation" });
    expect(table.firstChild.firstChild.attrs).toMatchObject({
      class: "c",
      style: "color: red;",
    });
  });

  it("can leave images out", () => {
    expect(schema.nodes.image).toBeDefined();
    expect(
      getSchema(createSchemaExtensions({ images: false })).nodes.image,
    ).toBeUndefined();
  });

  it("keeps class, style and dir on blocks", () => {
    const paragraph = docFrom(
      '<p class="lead" style="color: red;" dir="ltr">a</p>',
    ).firstChild;
    expect(paragraph.attrs).toMatchObject({
      class: "lead",
      style: "color: red;",
      dir: "ltr",
    });
  });
});

describe("Tab in a table", () => {
  function editorWithCursorIn(cell) {
    const editor = new Editor({
      element: document.createElement("div"),
      extensions,
      content: "<table><tr><td>a</td><td>b</td></tr></table>",
      injectCSS: false,
    });
    let position = null;
    editor.state.doc.descendants((node, pos) => {
      if (position === null && node.isText && node.text === cell) {
        position = pos;
      }
    });
    editor.commands.setTextSelection(position);
    return editor;
  }

  // True when the editor handles the key itself, so the browser does not move focus.
  function pressTab(editor) {
    const event = new KeyboardEvent("keydown", {
      key: "Tab",
      cancelable: true,
    });
    return Boolean(
      editor.view.someProp("handleKeyDown", (handle) =>
        handle(editor.view, event),
      ),
    );
  }

  it("moves to the next cell", () => {
    const editor = editorWithCursorIn("a");
    expect(pressTab(editor)).toBe(true);
    expect(editor.state.selection.$from.parent.textContent).toBe("b");
    editor.destroy();
  });

  it("leaves the table from the last cell instead of adding a row, so focus can leave the editor", () => {
    const editor = editorWithCursorIn("b");
    expect(pressTab(editor)).toBe(false);
    expect(editor.getHTML()).not.toContain("</tr><tr>");
    editor.destroy();
  });
});

describe("resizable images", () => {
  function editorWith(content, editable = true) {
    return new Editor({
      element: document.createElement("div"),
      extensions: createSchemaExtensions({ resizable: editable }),
      content,
      editable,
      injectCSS: false,
    });
  }

  function shownImage(editor) {
    return editor.view.dom.querySelector("img[src]");
  }

  function selectImage(editor) {
    editor.state.doc.descendants((node, pos) => {
      if (node.type.name === "image") {
        editor.commands.setNodeSelection(pos);
      }
    });
  }

  it("gives an editable image a handle at each corner", () => {
    const editor = editorWith('<p><img src="/a.png" alt="A"></p>');
    const handles = Array.from(
      editor.view.dom.querySelectorAll("[data-resize-handle]"),
      (handle) => handle.dataset.resizeHandle,
    );
    expect(handles.sort()).toEqual([
      "bottom-left",
      "bottom-right",
      "top-left",
      "top-right",
    ]);
    editor.destroy();
  });

  it("gives a read-only image no handles", () => {
    const editor = editorWith('<p><img src="/a.png" alt="A"></p>', false);
    expect(editor.view.dom.querySelector("[data-resize-handle]")).toBeNull();
    editor.destroy();
  });

  it("shows the saved width and leaves the height to the CSS", () => {
    const editor = editorWith(
      '<p><img src="/a.png" alt="A" width="250" height="100"></p>',
    );
    expect(shownImage(editor).style.width).toBe("250px");
    expect(shownImage(editor).style.height).toBe("");
    editor.destroy();
  });

  it("redraws the image when its size is changed outside a drag", () => {
    const editor = editorWith(
      '<p><img src="/a.png" alt="A" width="250" height="100"></p>',
    );
    selectImage(editor);
    editor.commands.updateAttributes("image", { width: 120, height: 48 });
    expect(shownImage(editor).style.width).toBe("120px");

    selectImage(editor);
    editor.commands.updateAttributes("image", { width: null, height: null });
    expect(shownImage(editor).style.width).toBe("");
    editor.destroy();
  });

  it("keeps width and height out of the editing DOM's attributes but in the saved HTML", () => {
    const editor = editorWith(
      '<p><img src="/a.png" alt="A" width="250" height="100"></p>',
    );
    expect(editor.getHTML()).toBe(
      '<p><img src="/a.png" alt="A" width="250" height="100"></p>',
    );
    editor.destroy();
  });
});
