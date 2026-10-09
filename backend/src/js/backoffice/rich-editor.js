// ABOUTME: Mounts the visual (Tiptap) HTML editor over a textarea, with a Visual/HTML switch.
// ABOUTME: The textarea stays the source of truth; the HTML view is the CodeMirror editor.
import { Editor, Extension } from "@tiptap/core";
import FileHandler from "@tiptap/extension-file-handler";
import { isReadOnly, mountCodeEditor } from "./code-editor.js";
import { formatHtml, roundTripsCleanly } from "./rich-editor-html.js";
import {
  VariableHighlight,
  createSchemaExtensions,
} from "./rich-editor-schema.js";
import { wireToolbar } from "./rich-editor-toolbar.js";
import {
  IMAGE_REQUEST_EVENT,
  INSERT_IMAGE_EVENT,
  LINK_REQUEST_EVENT,
  LINK_RESULT_EVENT,
} from "../lib/rich-editor-events.js";

export const VISUAL = "visual";
export const HTML = "html";
// The formats the image upload route accepts.
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const GOVUK_STYLE_CLASS = "rich-editor--govuk";

function imageSnippet(src, alt) {
  const image = document.createElement("img");
  image.setAttribute("src", src);
  image.setAttribute("alt", alt);
  return image.outerHTML;
}

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
  const imagesAllowed = textarea.dataset.richEditorImages === "true";
  const extensions = createSchemaExtensions({
    images: imagesAllowed,
    resizable: !readOnly,
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

  const editorOnlyExtensions = [VariableHighlight, LinkShortcut];
  if (imagesAllowed) {
    editorOnlyExtensions.push(
      FileHandler.configure({
        allowedMimeTypes: IMAGE_TYPES,
        // An image copied from a web page also carries an <img> pointing at
        // that site; only the uploaded copy should land in the intro.
        consumePasteEvent: true,
        onDrop: (_editor, files, pos) => requestImage(files[0], pos),
        onPaste: (_editor, files) => requestImage(files[0], null),
      }),
    );
  }

  const editor = new Editor({
    element: surface,
    extensions: [...extensions, ...editorOnlyExtensions],
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

  function requestImage(file, pos) {
    document.dispatchEvent(
      new CustomEvent(IMAGE_REQUEST_EVENT, {
        detail: { editorId: textarea.id, file: file || null, pos },
      }),
    );
  }

  // An insert without an editorId comes from the Assets panel, which serves
  // the page's one visual editor.
  function insertImage(event) {
    const { editorId, src, alt, pos } = event.detail;
    if (editorId && editorId !== textarea.id) {
      return;
    }
    if (mode === HTML) {
      codeEditor.insertAtCursor(imageSnippet(src, alt));
      codeEditor.focus();
      return;
    }
    const image = { type: "image", attrs: { src, alt } };
    const chain = editor.chain().focus();
    if (pos === null || pos === undefined) {
      chain.insertContent(image).run();
    } else {
      chain.insertContentAt(pos, image).run();
    }
  }

  document.addEventListener(LINK_RESULT_EVENT, applyLinkResult);
  if (imagesAllowed && !readOnly) {
    document.addEventListener(INSERT_IMAGE_EVENT, insertImage);
  }

  const toolbarControl = toolbar
    ? wireToolbar(toolbar, editor, {
        link: requestLink,
        image: () => requestImage(null, null),
      })
    : null;

  function visualHtml() {
    return editor.isEmpty ? "" : formatHtml(editor.getHTML());
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

  // The editing area previews the content style the page will be rendered with.
  function showContentStyle(style) {
    controls.classList.toggle(GOVUK_STYLE_CLASS, style === "govuk");
  }
  showContentStyle(controls.dataset.contentStyle);
  const styleRadios = document.querySelectorAll(
    `input[data-rich-editor-style-for="${textarea.id}"]`,
  );
  styleRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      if (radio.checked) {
        showContentStyle(radio.value);
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
      document.removeEventListener(INSERT_IMAGE_EVENT, insertImage);
      if (codeEditor) {
        codeEditor.destroy();
      }
      editor.destroy();
    },
  };
}
