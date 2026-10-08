// ABOUTME: Tests for the CodeMirror HTML editor mounted over a textarea.
// ABOUTME: Covers textarea sync, read-only handling, set/get and teardown.
import { afterEach, describe, expect, it, vi } from "vitest";
import { mountCodeEditor } from "./code-editor.js";

function makeForm(textareaAttrs = "") {
  document.body.innerHTML = `<form><textarea name="html" rows="4" ${textareaAttrs}>&lt;p&gt;Hi&lt;/p&gt;</textarea></form>`;
  const form = document.querySelector("form");
  return { form, textarea: form.querySelector("textarea") };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("mountCodeEditor", () => {
  it("shows the textarea's HTML and hides the textarea", () => {
    const { textarea } = makeForm();
    const editor = mountCodeEditor(textarea);
    expect(editor.getValue()).toBe("<p>Hi</p>");
    expect(textarea.style.display).toBe("none");
    expect(textarea.nextSibling).toBe(editor.view.dom);
  });

  it("writes changes back to the textarea and reports them", () => {
    const { textarea } = makeForm();
    const onChange = vi.fn();
    const editor = mountCodeEditor(textarea, { onChange });
    editor.setValue("<h1>New</h1>");
    expect(textarea.value).toBe("<h1>New</h1>");
    expect(onChange).toHaveBeenCalledWith("<h1>New</h1>");
  });

  it("inserts text at the cursor", () => {
    const { textarea } = makeForm();
    const editor = mountCodeEditor(textarea);
    editor.view.dispatch({ selection: { anchor: 3 } });
    editor.insertAtCursor("X");
    expect(textarea.value).toBe("<p>XHi</p>");
  });

  it("appends to a given container instead of after the textarea", () => {
    const { textarea, form } = makeForm();
    const container = document.createElement("div");
    form.appendChild(container);
    const editor = mountCodeEditor(textarea, { container });
    expect(container.firstChild).toBe(editor.view.dom);
  });

  it("does not let a read-only textarea's editor change the textarea", () => {
    const { textarea } = makeForm("readonly");
    const editor = mountCodeEditor(textarea);
    expect(editor.view.state.readOnly).toBe(true);
    editor.setValue("<p>Changed</p>");
    expect(textarea.value).toBe("<p>Hi</p>");
  });

  it("drops required so the hidden textarea cannot block submit", () => {
    const { textarea } = makeForm("required");
    mountCodeEditor(textarea);
    expect(textarea.hasAttribute("required")).toBe(false);
  });

  it("stops syncing on submit once destroyed", () => {
    const { form, textarea } = makeForm();
    const editor = mountCodeEditor(textarea);
    editor.setValue("<p>Editor</p>");
    editor.destroy();
    textarea.value = "<p>Elsewhere</p>";
    form.dispatchEvent(new Event("submit"));
    expect(textarea.value).toBe("<p>Elsewhere</p>");
    expect(form.querySelector(".cm-editor")).toBeNull();
  });
});
