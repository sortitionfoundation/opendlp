// ABOUTME: Tests for mounting the visual editor over a textarea and switching Visual/HTML.
// ABOUTME: The controls markup mirrors templates/backoffice/components/rich_editor.html.
import { afterEach, describe, expect, it, vi } from "vitest";
import { HTML, VISUAL, mountRichEditor } from "./rich-editor.js";

const OPENS_AS_HTML = "Opens as HTML message";
const SWITCH_REFUSED = "Switch refused message";

function setUp(value, textareaAttrs = "") {
  document.body.innerHTML = `
    <form>
      <div class="rich-editor" data-rich-editor-for="intro"
           data-rich-editor-label="Intro"
           data-message-opens-as-html="${OPENS_AS_HTML}"
           data-message-switch-refused="${SWITCH_REFUSED}" hidden>
        <button type="button" data-rich-editor-mode="visual" aria-pressed="true">Visual</button>
        <button type="button" data-rich-editor-mode="html" aria-pressed="false">HTML</button>
        <p data-rich-editor-notice role="status" hidden></p>
        <div data-rich-editor-surface></div>
        <div data-rich-editor-code></div>
      </div>
      <textarea id="intro" name="intro_content" data-rich-editor ${textareaAttrs}></textarea>
    </form>`;
  const textarea = document.getElementById("intro");
  textarea.value = value;
  return {
    textarea,
    form: document.querySelector("form"),
    controls: document.querySelector(".rich-editor"),
    notice: document.querySelector("[data-rich-editor-notice]"),
    surface: document.querySelector("[data-rich-editor-surface]"),
    code: document.querySelector("[data-rich-editor-code]"),
    visualButton: document.querySelector('[data-rich-editor-mode="visual"]'),
    htmlButton: document.querySelector('[data-rich-editor-mode="html"]'),
  };
}

let mounted = null;

function mount(textarea) {
  mounted = mountRichEditor(textarea);
  return mounted;
}

afterEach(() => {
  if (mounted) {
    mounted.destroy();
    mounted = null;
  }
  document.body.innerHTML = "";
});

describe("mountRichEditor", () => {
  it("returns null when the page has no controls for the textarea", () => {
    document.body.innerHTML =
      '<textarea id="other" data-rich-editor></textarea>';
    expect(mountRichEditor(document.getElementById("other"))).toBeNull();
  });

  it("opens in Visual mode when the HTML survives the editor", () => {
    const page = setUp("<h1>{{ assembly_title }}</h1>");
    const rich = mount(page.textarea);
    expect(rich.mode).toBe(VISUAL);
    expect(page.controls.hidden).toBe(false);
    expect(page.textarea.style.display).toBe("none");
    expect(page.surface.hidden).toBe(false);
    expect(page.code.hidden).toBe(true);
    expect(page.visualButton.getAttribute("aria-pressed")).toBe("true");
    expect(page.htmlButton.getAttribute("aria-pressed")).toBe("false");
    expect(page.notice.hidden).toBe(true);
  });

  it("names the editing area for assistive technology", () => {
    const page = setUp("<p>a</p>");
    mount(page.textarea);
    const content = page.surface.querySelector("[contenteditable]");
    expect(content.getAttribute("role")).toBe("textbox");
    expect(content.getAttribute("aria-label")).toBe("Intro");
  });

  it("opens in HTML mode, saying why, when the editor would lose something", () => {
    const page = setUp("<table><tr><td>a</td></tr></table>");
    const rich = mount(page.textarea);
    expect(rich.mode).toBe(HTML);
    expect(page.surface.hidden).toBe(true);
    expect(page.code.querySelector(".cm-editor")).not.toBeNull();
    expect(page.htmlButton.getAttribute("aria-pressed")).toBe("true");
    expect(page.notice.hidden).toBe(false);
    expect(page.notice.textContent).toBe(OPENS_AS_HTML);
  });

  it("leaves the textarea untouched until the author edits", () => {
    const html = "<h1>Title</h1>\n<p>Intro</p>\n";
    const page = setUp(html);
    mount(page.textarea);
    expect(page.textarea.value).toBe(html);
  });

  it("writes Visual edits to the textarea and fires a bubbling input event", () => {
    const page = setUp("<p>Hello</p>");
    const onInput = vi.fn();
    page.form.addEventListener("input", onInput);
    const rich = mount(page.textarea);
    rich.editor.commands.setContent("<p>Changed</p>");
    expect(page.textarea.value).toBe("<p>Changed</p>");
    expect(onInput).toHaveBeenCalledTimes(1);
  });

  it("saves an emptied editor as an empty intro", () => {
    const page = setUp("<p>Hello</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.clearContent(true);
    expect(page.textarea.value).toBe("");
  });

  it("refuses to switch to Visual when the HTML would lose something", () => {
    const page = setUp("<p>a</p>");
    const rich = mount(page.textarea);
    page.htmlButton.click();
    page.textarea.value = "<p>a</p><!-- keep me -->";
    page.visualButton.click();
    expect(rich.mode).toBe(HTML);
    expect(page.notice.textContent).toBe(SWITCH_REFUSED);
    expect(page.notice.hidden).toBe(false);
    expect(page.htmlButton.getAttribute("aria-pressed")).toBe("true");
  });

  it("keeps content through Visual, HTML and back to Visual", () => {
    const page = setUp("<p>One</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setContent("<p>Two</p>");
    page.htmlButton.click();
    expect(rich.mode).toBe(HTML);
    expect(page.code.querySelector(".cm-content").textContent).toContain(
      "<p>Two</p>",
    );
    page.visualButton.click();
    expect(rich.mode).toBe(VISUAL);
    expect(page.code.querySelector(".cm-editor")).toBeNull();
    expect(rich.editor.getHTML()).toBe("<p>Two</p>");
  });

  it("carries HTML-mode edits into Visual mode", () => {
    const page = setUp("<p>One</p>");
    const rich = mount(page.textarea);
    page.htmlButton.click();
    page.textarea.value = "<h2>Edited as HTML</h2>";
    page.visualButton.click();
    expect(rich.editor.getHTML()).toBe("<h2>Edited as HTML</h2>");
  });

  it("is read-only when the textarea is", () => {
    const page = setUp("<p>Fixed</p>", "readonly");
    const rich = mount(page.textarea);
    expect(rich.editor.isEditable).toBe(false);
    expect(
      page.surface
        .querySelector("[contenteditable]")
        .getAttribute("contenteditable"),
    ).toBe("false");
  });

  it("highlights template variables without changing the HTML", () => {
    const page = setUp("<p>Welcome to {{ assembly_title }}</p>");
    const rich = mount(page.textarea);
    const highlighted = page.surface.querySelector(".rich-editor__variable");
    expect(highlighted.textContent).toBe("{{ assembly_title }}");
    expect(rich.editor.getHTML()).toBe(
      "<p>Welcome to {{ assembly_title }}</p>",
    );
  });
});
