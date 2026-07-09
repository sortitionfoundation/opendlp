// ABOUTME: CodeMirror 6 progressive-enhancement initialiser for HTML-editing textareas.
// ABOUTME: Mounts a highlighted editor over any [data-code-editor] textarea, syncing back for form submit.
import { basicSetup } from "codemirror";
import { EditorView, keymap } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { indentWithTab } from "@codemirror/commands";
import { html } from "@codemirror/lang-html";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";

const MOUNTED_ATTR = "data-cm-mounted";

const highlightStyle = HighlightStyle.define([
  { tag: [tags.tagName, tags.angleBracket], color: "#22863a" },
  { tag: tags.attributeName, color: "#6f42c1" },
  { tag: [tags.attributeValue, tags.string], color: "#032f62" },
  { tag: tags.comment, color: "#6a737d", fontStyle: "italic" },
  { tag: [tags.keyword, tags.controlKeyword], color: "#d73a49" },
  { tag: [tags.number, tags.bool], color: "#005cc5" },
  { tag: tags.meta, color: "#6a737d" },
]);

const editorTheme = EditorView.theme({
  "&": {
    fontSize: "0.875rem",
    borderRadius: "0.5rem",
    border: "1px solid var(--color-borders-dividers)",
    backgroundColor: "var(--color-page-background)",
    color: "var(--color-body-text)",
    // Fixed height with an internal scrollbar (set per-instance from the
    // textarea's rows), resizable like the textarea it replaces.
    resize: "vertical",
    overflow: "hidden",
  },
  "&.cm-focused": {
    outline: "2px solid var(--color-primary-action)",
    outlineOffset: "0",
  },
  ".cm-scroller": {
    overflow: "auto",
  },
  ".cm-content": {
    fontFamily:
      "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace",
  },
  ".cm-gutters": {
    backgroundColor: "var(--color-subtle-background-panels)",
    color: "var(--color-secondary-text)",
    border: "none",
  },
});

function labelTextFor(textarea) {
  if (textarea.id) {
    const label = document.querySelector(`label[for="${textarea.id}"]`);
    if (label && label.textContent.trim()) {
      return label.textContent.trim();
    }
  }
  return textarea.getAttribute("aria-label") || "";
}

function mount(textarea) {
  if (textarea.hasAttribute(MOUNTED_ATTR)) {
    return;
  }
  textarea.setAttribute(MOUNTED_ATTR, "true");

  const readOnly =
    textarea.hasAttribute("readonly") || textarea.dataset.readonly === "true";

  const extensions = [
    basicSetup,
    html(),
    syntaxHighlighting(highlightStyle),
    editorTheme,
    EditorView.lineWrapping,
    EditorState.readOnly.of(readOnly),
    EditorView.editable.of(!readOnly),
    keymap.of([
      indentWithTab,
      {
        key: "Escape",
        run: (view) => {
          view.contentDOM.blur();
          return true;
        },
      },
    ]),
  ];

  if (!readOnly) {
    extensions.push(
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          textarea.value = update.state.doc.toString();
        }
      }),
    );
  }

  const view = new EditorView({
    doc: textarea.value || textarea.textContent || "",
    extensions,
  });

  view.contentDOM.setAttribute("role", "textbox");
  view.contentDOM.setAttribute("aria-multiline", "true");
  const label = labelTextFor(textarea);
  if (label) {
    view.contentDOM.setAttribute("aria-label", label);
  }

  const rows = parseInt(textarea.getAttribute("rows"), 10);
  view.dom.style.height = `${(rows > 0 ? rows : 10) * 1.5}em`;

  // A required + display:none textarea blocks submit ("not focusable"); the editor
  // keeps the value in sync and server-side validation still guards emptiness.
  if (!readOnly) {
    textarea.removeAttribute("required");
    const form = textarea.form;
    if (form) {
      form.addEventListener("submit", () => {
        textarea.value = view.state.doc.toString();
      });
    }
  }

  textarea.style.display = "none";
  textarea.parentNode.insertBefore(view.dom, textarea.nextSibling);
}

function mountAll(root = document) {
  root
    .querySelectorAll(`textarea[data-code-editor]:not([${MOUNTED_ATTR}])`)
    .forEach(mount);
}

function observe() {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) {
          continue;
        }
        if (node.matches && node.matches("textarea[data-code-editor]")) {
          queueMicrotask(() => mount(node));
        } else if (node.querySelectorAll) {
          node
            .querySelectorAll("textarea[data-code-editor]")
            .forEach((el) => queueMicrotask(() => mount(el)));
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function init() {
  mountAll();
  observe();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
