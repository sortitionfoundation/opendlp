// ABOUTME: Progressive-enhancement entry point for HTML-editing textareas.
// ABOUTME: Mounts a CodeMirror editor over any [data-code-editor] textarea, including ones added later.
import { mountCodeEditor } from "./code-editor.js";

const MOUNTED_ATTR = "data-cm-mounted";

function mount(textarea) {
  if (textarea.hasAttribute(MOUNTED_ATTR)) {
    return;
  }
  textarea.setAttribute(MOUNTED_ATTR, "true");
  mountCodeEditor(textarea);
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
