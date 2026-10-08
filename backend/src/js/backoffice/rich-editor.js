// ABOUTME: Mounts the visual (Tiptap) HTML editor over a textarea, with a Visual/HTML switch.
// ABOUTME: The textarea stays the source of truth; the HTML view is the CodeMirror editor.
import { Editor, Extension } from "@tiptap/core";
import { isReadOnly, mountCodeEditor } from "./code-editor.js";
import { roundTripsCleanly } from "./rich-editor-html.js";
import {
  VariableHighlight,
  createSchemaExtensions,
} from "./rich-editor-schema.js";
import { wireToolbar } from "./rich-editor-toolbar.js";
import {
  LINK_REQUEST_EVENT,
  LINK_RESULT_EVENT,
} from "../lib/rich-editor-events.js";

export const VISUAL = "visual";
export const HTML = "html";

function controlsFor(textarea) {
  return textarea.id
    ? document.querySelector(`[data-rich-editor-for="${textarea.id}"]`)
    : null;
}

/**
 * Mount the visual editor for `textarea`, using the controls the template
 * rendered for it (see templates/backoffice/components/rich_editor.html).
 *
 * The editor opens in Visual mode when the textarea's HTML survives the trip
 * through the editor, and in HTML mode otherwise. Returns null if the page has
 * no controls for the textarea.
 */
export function mountRichEditor(textarea) {
  const controls = controlsFor(textarea);
  if (!controls) {
    return null;
  }
  const readOnly = isReadOnly(textarea);
  const surface = controls.querySelector("[data-rich-editor-surface]");
  const codeContainer = controls.querySelector("[data-rich-editor-code]");
  const notice = controls.querySelector("[data-rich-editor-notice]");
  const modeButtons = controls.querySelectorAll("[data-rich-editor-mode]");
  const toolbar = controls.querySelector("[data-rich-editor-toolbar]");
  const extensions = createSchemaExtensions({
    images: textarea.dataset.richEditorImages === "true",
  });

  let mode = null;
  let codeEditor = null;

  function writeBack(value) {
    if (textarea.value === value) {
      return;
    }
    textarea.value = value;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  const LinkShortcut = Extension.create({
    name: "linkShortcut",
    addKeyboardShortcuts() {
      return {
        "Mod-k": () => {
          requestLink();
          return true;
        },
      };
    },
  });

  const editor = new Editor({
    element: surface,
    extensions: [...extensions, VariableHighlight, LinkShortcut],
    editable: !readOnly,
    injectCSS: false,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": controls.dataset.richEditorLabel || "",
        id: `${textarea.id}-visual`,
        class: "rich-editor__content",
      },
    },
    onUpdate: () => {
      if (mode === VISUAL) {
        writeBack(visualHtml());
      }
    },
  });

  function requestLink() {
    editor.chain().extendMarkRange("link").run();
    const { from, to } = editor.state.selection;
    document.dispatchEvent(
      new CustomEvent(LINK_REQUEST_EVENT, {
        detail: {
          editorId: textarea.id,
          href: editor.getAttributes("link").href || "",
          text: editor.state.doc.textBetween(from, to, " "),
        },
      }),
    );
  }

  function applyLinkResult(event) {
    const { editorId, action, href } = event.detail;
    if (editorId !== textarea.id) {
      return;
    }
    const chain = editor.chain().focus().extendMarkRange("link");
    if (action === "remove") {
      chain.unsetLink().run();
    } else if (action === "set" && href) {
      if (editor.state.selection.empty && !editor.isActive("link")) {
        chain
          .insertContent({
            type: "text",
            text: href,
            marks: [{ type: "link", attrs: { href } }],
          })
          .run();
      } else {
        chain.setLink({ href }).run();
      }
    } else {
      chain.run();
    }
  }

  document.addEventListener(LINK_RESULT_EVENT, applyLinkResult);

  const toolbarControl = toolbar
    ? wireToolbar(toolbar, editor, { link: requestLink })
    : null;

  function visualHtml() {
    return editor.isEmpty ? "" : editor.getHTML();
  }

  function showNotice(message) {
    notice.textContent = message;
    notice.hidden = !message;
  }

  function showMode(next) {
    mode = next;
    surface.hidden = next !== VISUAL;
    codeContainer.hidden = next !== HTML;
    if (toolbar) {
      toolbar.hidden = next !== VISUAL;
    }
    modeButtons.forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.richEditorMode === next),
      );
    });
  }

  function toHtml() {
    if (mode === HTML) {
      return true;
    }
    codeEditor = mountCodeEditor(textarea, {
      container: codeContainer,
      onChange: () =>
        textarea.dispatchEvent(new Event("input", { bubbles: true })),
    });
    showNotice("");
    showMode(HTML);
    return true;
  }

  function toVisual(refusalMessage) {
    if (mode === VISUAL) {
      return true;
    }
    if (!roundTripsCleanly(textarea.value, extensions)) {
      showNotice(refusalMessage);
      return false;
    }
    if (codeEditor) {
      codeEditor.destroy();
      codeEditor = null;
    }
    editor.commands.setContent(textarea.value, { emitUpdate: false });
    if (toolbarControl) {
      toolbarControl.refresh();
    }
    showNotice("");
    showMode(VISUAL);
    return true;
  }

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.richEditorMode === VISUAL) {
        toVisual(controls.dataset.messageSwitchRefused);
      } else {
        toHtml();
      }
    });
  });

  textarea.style.display = "none";
  textarea.removeAttribute("required");
  controls.hidden = false;
  if (!toVisual(controls.dataset.messageOpensAsHtml)) {
    toHtml();
    showNotice(controls.dataset.messageOpensAsHtml);
  }

  return {
    editor,
    get mode() {
      return mode;
    },
    toVisual: () => toVisual(controls.dataset.messageSwitchRefused),
    toHtml,
    getHTML: () => textarea.value,
    destroy() {
      document.removeEventListener(LINK_RESULT_EVENT, applyLinkResult);
      if (codeEditor) {
        codeEditor.destroy();
      }
      editor.destroy();
    },
  };
}
