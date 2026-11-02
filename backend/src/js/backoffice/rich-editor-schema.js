// ABOUTME: The Tiptap extension list for the visual HTML editor, and template-variable highlighting.
// ABOUTME: Keeps the attributes real intros use so their HTML survives a trip through the editor.
import { Extension, Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyle } from "@tiptap/extension-text-style";
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
  "textStyle",
];

// The blocks the toolbar can align, and the alignments it offers.
export const ALIGNABLE_TYPES = ["paragraph", "heading"];
export const ALIGNMENTS = ["left", "center", "right"];

const ALIGNMENT_DECLARATION = new RegExp(
  `(^|;)\\s*text-align\\s*:\\s*(${ALIGNMENTS.join("|")})\\s*(;|$)`,
  "i",
);

/**
 * An alignable block's style, less the alignment TextAlign keeps as an
 * attribute of its own - kept here as well, it would be written twice. An
 * alignment the toolbar doesn't offer, such as justify, stays in the style.
 */
function styleWithoutAlignment(element) {
  const style = element.getAttribute("style");
  if (style === null) {
    return null;
  }
  const rest = style
    .replace(ALIGNMENT_DECLARATION, "$1")
    .replace(/^\s*;\s*/, "")
    .trim();
  return rest === "" ? null : rest;
}

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
        types: PRESERVED_ATTRIBUTE_TYPES.filter(
          (type) => !ALIGNABLE_TYPES.includes(type),
        ),
        attributes: {
          class: preservedAttribute("class"),
          style: preservedAttribute("style"),
          dir: preservedAttribute("dir"),
        },
      },
      {
        types: ALIGNABLE_TYPES,
        attributes: {
          class: preservedAttribute("class"),
          style: {
            ...preservedAttribute("style"),
            parseHTML: styleWithoutAlignment,
          },
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
 * outside a drag, such as from the Image size dialog, so the shown width is
 * updated here, without redrawing the image. The height is left to the CSS, because an inline height would stop the
 * image keeping its shape when `max-width` narrows it.
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
        if (!update(node, ...rest)) {
          return false;
        }
        const { width } = node.attrs;
        view.element.style.width = width ? `${width}px` : "";
        view.element.style.height = "";
        return true;
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
 * `images` and `tables` leave those nodes out, for an editor that offers
 * neither, such as the auto-reply email's.
 *
 * `resizable` is off for a read-only editor: Tiptap only takes the handles
 * away after the editor changes, and a read-only editor never does.
 *
 * `imageMinWidth` is the narrowest an image can be dragged to, which the page
 * passes in so it matches the Image size dialog; 0 keeps Tiptap's own minimum.
 */
export function createSchemaExtensions({
  images = true,
  imageMinWidth = 0,
  resizable = true,
  tables = true,
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
    TextAlign.configure({ types: ALIGNABLE_TYPES, alignments: ALIGNMENTS }),
    // Keeps a styled <span>, such as one pasted from Google Docs; the toolbar never makes one.
    TextStyle,
    Div,
  ];
  if (tables) {
    extensions.push(
      PlainTable.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    );
  }
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
          ...(imageMinWidth ? { minWidth: imageMinWidth } : {}),
          alwaysPreserveAspectRatio: true,
        },
      }),
    );
  }
  return extensions;
}
