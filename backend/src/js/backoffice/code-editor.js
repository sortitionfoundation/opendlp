// ABOUTME: CodeMirror 6 HTML editor mounted over a textarea, keeping the textarea in sync.
// ABOUTME: Exports mountCodeEditor() returning a small handle to get, set, insert into, focus and destroy it.
import { basicSetup } from "codemirror";
import { EditorView, keymap } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { indentWithTab } from "@codemirror/commands";
import { html } from "@codemirror/lang-html";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";

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

export function isReadOnly(textarea) {
  return (
    textarea.hasAttribute("readonly") || textarea.dataset.readonly === "true"
  );
}

/**
 * Mount a CodeMirror HTML editor for `textarea`, hiding the textarea.
 *
 * The textarea is kept in sync on every change and on form submit. The editor
 * is inserted straight after the textarea unless `container` is given, in
 * which case it is appended to that element. `onChange(value)` is called after
 * each change the editor writes back.
 */
export function mountCodeEditor(
  textarea,
  { container = null, onChange = null } = {},
) {
  const readOnly = isReadOnly(textarea);

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
          if (onChange) {
            onChange(textarea.value);
          }
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

  const getValue = () => view.state.doc.toString();
  const syncOnSubmit = () => {
    textarea.value = getValue();
  };

  // A required + display:none textarea blocks submit ("not focusable"); the editor
  // keeps the value in sync and server-side validation still guards emptiness.
  const form = readOnly ? null : textarea.form;
  if (!readOnly) {
    textarea.removeAttribute("required");
    if (form) {
      form.addEventListener("submit", syncOnSubmit);
    }
  }

  textarea.style.display = "none";
  if (container) {
    container.appendChild(view.dom);
  } else {
    textarea.parentNode.insertBefore(view.dom, textarea.nextSibling);
  }

  return {
    view,
    getValue,
    setValue(value) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
      });
    },
    focus() {
      view.focus();
    },
    insertAtCursor(text) {
      view.dispatch(view.state.replaceSelection(text));
    },
    destroy() {
      if (form) {
        form.removeEventListener("submit", syncOnSubmit);
      }
      view.destroy();
      view.dom.remove();
    },
  };
}
