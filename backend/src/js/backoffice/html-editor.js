// ABOUTME: Progressive-enhancement entry point for HTML-editing textareas.
// ABOUTME: Mounts the visual or CodeMirror editor over matching textareas, including ones added later.
import { mountCodeEditor } from "./code-editor.js";
import { mountRichEditor } from "./rich-editor.js";

const MOUNTED_ATTR = "data-cm-mounted";
const SELECTOR = "textarea[data-code-editor], textarea[data-rich-editor]";

// Each mounted textarea's editor, so it can be destroyed once the textarea
// leaves the page: otherwise it would go on answering document events meant
// for a textarea re-rendered in its place.
const editors = new Map();

/** The editor mounted over `textarea`, or undefined if there is none. */
export function editorFor(textarea) {
  return editors.get(textarea);
}

function mount(textarea) {
  if (textarea.hasAttribute(MOUNTED_ATTR)) {
    return;
  }
  textarea.setAttribute(MOUNTED_ATTR, "true");
  const rich = textarea.hasAttribute("data-rich-editor")
    ? mountRichEditor(textarea)
    : null;
  editors.set(textarea, rich || mountCodeEditor(textarea));
}

function mountAll(root = document) {
  root.querySelectorAll(SELECTOR).forEach((textarea) => mount(textarea));
}

function destroyRemoved() {
  for (const [textarea, editor] of editors) {
    if (!textarea.isConnected) {
      editor.destroy();
      editors.delete(textarea);
    }
  }
}

function observe() {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.removedNodes.length) {
        destroyRemoved();
      }
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) {
          continue;
        }
        if (node.matches && node.matches(SELECTOR)) {
          queueMicrotask(() => mount(node));
        } else if (node.querySelectorAll) {
          node
            .querySelectorAll(SELECTOR)
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
