// ABOUTME: Names of the DOM events the CodeMirror HTML editor answers on its textarea.
// ABOUTME: Shared so the Alpine slices can drive the editor without importing its bundle.

// Dispatched on a textarea with `detail.value`: the editor mounted over it
// replaces its whole content with that value.
export const SET_VALUE_EVENT = "code-editor-set-value";
