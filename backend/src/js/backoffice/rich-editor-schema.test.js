// ABOUTME: Tests for the visual editor's schema and its template-variable finder.
// ABOUTME: Builds ProseMirror documents from HTML with the same extensions the editor uses.
import { describe, expect, it } from "vitest";
import { generateJSON, getSchema } from "@tiptap/core";
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
    for (const name of ["underline", "strike", "code"]) {
      expect(schema.marks[name]).toBeUndefined();
    }
    for (const name of ["codeBlock", "blockquote", "horizontalRule", "table"]) {
      expect(schema.nodes[name]).toBeUndefined();
    }
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
