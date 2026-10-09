// ABOUTME: The Tiptap extension list for the visual HTML editor, and template-variable highlighting.
// ABOUTME: Keeps the attributes real intros use so their HTML survives a trip through the editor.
import { Extension, Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import {
  Table,
  TableCell,
  TableHeader,
  TableRow,
} from "@tiptap/extension-table";
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
  "blockquote",
  "horizontalRule",
  "table",
  "tableRow",
  "tableCell",
  "tableHeader",
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
      {
        types: ["table"],
        attributes: {
          border: preservedAttribute("border"),
          role: preservedAttribute("role"),
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

// Writes a plain <table>: Tiptap's own output adds a <colgroup> and a min-width
// style to every table, which would fill the stored HTML with sizing noise.
const PlainTable = Table.extend({
  renderHTML({ HTMLAttributes }) {
    return ["table", HTMLAttributes, ["tbody", 0]];
  },
  addKeyboardShortcuts() {
    return {
      ...this.parent?.(),
      // Tab moves between cells and leaves the table from its last cell, rather
      // than adding a row, so a keyboard user can always Tab out of the editor.
      Tab: () => this.editor.commands.goToNextCell(),
    };
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
 * The image node, with Tiptap's resize handles.
 *
 * Tiptap's resizable node view ignores a change to `width` or `height` made
 * outside a drag, such as from the Image size dialog, so a size change redraws
 * the node instead. Its inline height would also stop the image keeping its
 * shape when `max-width` narrows it, so the height is left to the CSS.
 */
const ResizableImage = Image.extend({
  addNodeView() {
    const createView = this.parent?.();
    if (!createView) {
      return null;
    }
    return (props) => {
      const view = createView(props);
      view.element.style.height = "";
      const update = view.update.bind(view);
      view.update = (node, ...rest) => {
        const { width, height } = view.node.attrs;
        if (node.attrs.width !== width || node.attrs.height !== height) {
          return false;
        }
        return update(node, ...rest);
      };
      return view;
    };
  },
});

/**
 * The extensions that define what the visual editor can hold.
 *
 * Anything outside this schema is dropped by Tiptap, which is why an intro
 * using it has to stay in HTML mode (see rich-editor-html.js).
 *
 * `resizable` is off for a read-only editor: Tiptap only takes the handles
 * away after the editor changes, and a read-only editor never does.
 */
export function createSchemaExtensions({
  images = true,
  resizable = true,
} = {}) {
  const extensions = [
    StarterKit.configure({
      code: false,
      codeBlock: false,
      trailingNode: false,
      heading: { levels: [1, 2, 3] },
      link: {
        openOnClick: false,
        HTMLAttributes: { target: null, rel: null, class: null },
      },
    }),
    PreservedAttributes,
    Div,
    PlainTable.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
  ];
  if (images) {
    extensions.push(
      ResizableImage.configure({
        inline: true,
        allowBase64: false,
        // Corner handles that keep the image's shape; the Image size dialog is
        // the way to resize without dragging.
        resize: {
          enabled: resizable,
          directions: ["top-left", "top-right", "bottom-left", "bottom-right"],
          minWidth: 20,
          alwaysPreserveAspectRatio: true,
        },
      }),
    );
  }
  return extensions;
}
