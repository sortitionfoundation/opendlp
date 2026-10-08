// ABOUTME: The Tiptap extension list for the visual HTML editor, and template-variable highlighting.
// ABOUTME: Keeps the attributes real intros use so their HTML survives a trip through the editor.
import { Extension, Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export const VARIABLE_PATTERN = /\{\{\s*[A-Za-z_][\w.]*\s*\}\}/g;
export const VARIABLE_CLASS = "rich-editor__variable";

const PRESERVED_ATTRIBUTE_TYPES = [
  "paragraph",
  "heading",
  "bulletList",
  "orderedList",
  "listItem",
  "link",
  "image",
  "div",
];

function preservedAttribute(name) {
  return {
    default: null,
    parseHTML: (element) => element.getAttribute(name),
    renderHTML: (attributes) =>
      attributes[name] === null || attributes[name] === undefined
        ? {}
        : { [name]: attributes[name] },
  };
}

const PreservedAttributes = Extension.create({
  name: "preservedAttributes",
  addGlobalAttributes() {
    return [
      {
        types: PRESERVED_ATTRIBUTE_TYPES,
        attributes: {
          class: preservedAttribute("class"),
          style: preservedAttribute("style"),
          dir: preservedAttribute("dir"),
        },
      },
    ];
  },
});

// Exists only so existing wrappers (the GOV.UK grid row) survive; the toolbar never creates one.
const Div = Node.create({
  name: "div",
  group: "block",
  content: "block+",
  defining: true,
  parseHTML() {
    return [{ tag: "div" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", HTMLAttributes, 0];
  },
});

/** Every `{{ variable }}` in the document's text, as `{from, to}` document positions. */
export function findVariableRanges(doc) {
  const ranges = [];
  doc.descendants((node, pos) => {
    if (!node.isText) {
      return;
    }
    for (const match of node.text.matchAll(VARIABLE_PATTERN)) {
      const from = pos + match.index;
      ranges.push({ from, to: from + match[0].length });
    }
  });
  return ranges;
}

function variableDecorations(doc) {
  return DecorationSet.create(
    doc,
    findVariableRanges(doc).map(({ from, to }) =>
      Decoration.inline(from, to, { class: VARIABLE_CLASS }),
    ),
  );
}

const variableHighlightKey = new PluginKey("variableHighlight");

export const VariableHighlight = Extension.create({
  name: "variableHighlight",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: variableHighlightKey,
        state: {
          init: (_, state) => variableDecorations(state.doc),
          apply: (tr, decorations) =>
            tr.docChanged ? variableDecorations(tr.doc) : decorations,
        },
        props: {
          decorations: (state) => variableHighlightKey.getState(state),
        },
      }),
    ];
  },
});

/**
 * The extensions that define what the visual editor can hold.
 *
 * Anything outside this schema is dropped by Tiptap, which is why an intro
 * using it has to stay in HTML mode (see rich-editor-html.js).
 */
export function createSchemaExtensions({ images = true } = {}) {
  const extensions = [
    StarterKit.configure({
      underline: false,
      strike: false,
      code: false,
      codeBlock: false,
      blockquote: false,
      horizontalRule: false,
      trailingNode: false,
      heading: { levels: [1, 2, 3] },
      link: {
        openOnClick: false,
        HTMLAttributes: { target: null, rel: null, class: null },
      },
    }),
    PreservedAttributes,
    Div,
  ];
  if (images) {
    extensions.push(Image.configure({ inline: true, allowBase64: false }));
  }
  return extensions;
}
