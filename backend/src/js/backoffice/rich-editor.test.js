// ABOUTME: Tests for mounting the visual editor over a textarea and switching Visual/HTML.
// ABOUTME: The controls markup mirrors templates/backoffice/components/rich_editor.html.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GOVUK_STYLE_CLASS,
  HTML,
  VISUAL,
  mountRichEditor,
} from "./rich-editor.js";
import {
  IMAGE_REQUEST_EVENT,
  IMAGE_SIZE_REQUEST_EVENT,
  IMAGE_SIZE_RESULT_EVENT,
  INSERT_IMAGE_EVENT,
  LINK_REQUEST_EVENT,
  LINK_RESULT_EVENT,
} from "../lib/rich-editor-events.js";

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
        <div role="toolbar" data-rich-editor-toolbar>
          <button type="button" data-command="bold">Bold</button>
          <button type="button" data-command="link">Link</button>
          <button type="button" data-command="image">Image</button>
          <button type="button" data-command="imageSize">Image size</button>
        </div>
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
    toolbar: document.querySelector("[data-rich-editor-toolbar]"),
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
    const page = setUp("<!-- note --><p>a</p>");
    const rich = mount(page.textarea);
    expect(rich.mode).toBe(HTML);
    expect(page.surface.hidden).toBe(true);
    expect(page.code.querySelector(".cm-editor")).not.toBeNull();
    expect(page.htmlButton.getAttribute("aria-pressed")).toBe("true");
    expect(page.notice.hidden).toBe(false);
    expect(page.notice.textContent).toBe(OPENS_AS_HTML);
  });

  it("opens a table in HTML mode unless the textarea allows tables", () => {
    const table = "<table><tbody><tr><td><p>a</p></td></tr></tbody></table>";
    const without = setUp(table);
    expect(mount(without.textarea).mode).toBe(HTML);
    expect(without.notice.textContent).toBe(OPENS_AS_HTML);
    mounted.destroy();
    mounted = null;

    const allowed = setUp(table, 'data-rich-editor-tables="true"');
    expect(mount(allowed.textarea).mode).toBe(VISUAL);
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

  it("writes Visual edits laid out one block per line", () => {
    const page = setUp("<p>Hello</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setContent("<h1>Title</h1><ul><li>One</li></ul>");
    expect(page.textarea.value).toBe(
      "<h1>Title</h1>\n<ul>\n  <li>\n    <p>One</p>\n  </li>\n</ul>",
    );
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

describe("mountRichEditor toolbar and links", () => {
  function captureLinkRequests() {
    const requests = [];
    const listener = (event) => requests.push(event.detail);
    document.addEventListener(LINK_REQUEST_EVENT, listener);
    return {
      requests,
      stop: () => document.removeEventListener(LINK_REQUEST_EVENT, listener),
    };
  }

  function answer(detail) {
    document.dispatchEvent(new CustomEvent(LINK_RESULT_EVENT, { detail }));
  }

  it("shows the toolbar in Visual mode only", () => {
    const page = setUp("<p>a</p>");
    mount(page.textarea);
    expect(page.toolbar.hidden).toBe(false);
    page.htmlButton.click();
    expect(page.toolbar.hidden).toBe(true);
    page.visualButton.click();
    expect(page.toolbar.hidden).toBe(false);
  });

  it("points the toolbar's aria-controls target at the editing area", () => {
    const page = setUp("<p>a</p>");
    mount(page.textarea);
    expect(page.surface.querySelector("#intro-visual")).not.toBeNull();
  });

  it("asks for a link with the whole link under the cursor", () => {
    const capture = captureLinkRequests();
    const page = setUp('<p>Go <a href="https://example.org">there</a> now</p>');
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection(6);
    page.toolbar.querySelector('[data-command="link"]').click();
    capture.stop();
    expect(capture.requests).toEqual([
      { editorId: "intro", href: "https://example.org", text: "there" },
    ]);
  });

  it("opens the link dialog on Ctrl/Cmd-K", () => {
    const capture = captureLinkRequests();
    const page = setUp("<p>a</p>");
    const rich = mount(page.textarea);
    rich.editor.view.someProp("handleKeyDown", (handler) =>
      handler(
        rich.editor.view,
        new KeyboardEvent("keydown", { key: "k", ctrlKey: true }),
      ),
    );
    capture.stop();
    expect(capture.requests).toHaveLength(1);
  });

  it("links the selected text when the dialog answers set", () => {
    const page = setUp("<p>Read this</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection({ from: 6, to: 10 });
    answer({ editorId: "intro", action: "set", href: "/info" });
    expect(page.textarea.value).toBe('<p>Read <a href="/info">this</a></p>');
  });

  it("inserts the address as linked text when nothing is selected", () => {
    const page = setUp("<p>See here</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection(5);
    answer({ editorId: "intro", action: "set", href: "https://example.org" });
    expect(page.textarea.value).toBe(
      '<p>See <a href="https://example.org">https://example.org</a>here</p>',
    );
  });

  it("removes the whole link when the dialog answers remove", () => {
    const page = setUp('<p>Go <a href="/x">there</a></p>');
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection(6);
    answer({ editorId: "intro", action: "remove", href: "" });
    expect(page.textarea.value).toBe("<p>Go there</p>");
  });

  it("ignores answers meant for another editor", () => {
    const page = setUp("<p>Read this</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection({ from: 6, to: 10 });
    answer({ editorId: "other", action: "set", href: "/info" });
    expect(page.textarea.value).toBe("<p>Read this</p>");
  });

  it("refuses a javascript: address", () => {
    const page = setUp("<p>Read this</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection({ from: 6, to: 10 });
    answer({ editorId: "intro", action: "set", href: "javascript:alert(1)" });
    expect(page.textarea.value).not.toContain("javascript:");
  });
});

describe("mountRichEditor images", () => {
  function imagesPage(value, textareaAttrs = "") {
    return setUp(value, `data-rich-editor-images="true" ${textareaAttrs}`);
  }

  function captureImageRequests() {
    const requests = [];
    const listener = (event) => requests.push(event.detail);
    document.addEventListener(IMAGE_REQUEST_EVENT, listener);
    return {
      requests,
      stop: () => document.removeEventListener(IMAGE_REQUEST_EVENT, listener),
    };
  }

  function insert(detail) {
    document.dispatchEvent(new CustomEvent(INSERT_IMAGE_EVENT, { detail }));
  }

  function paste(rich, files, html = "") {
    const event = {
      clipboardData: {
        files,
        getData: (type) => (type === "text/html" ? html : ""),
      },
      preventDefault: () => {},
      stopPropagation: () => {},
    };
    let handled = false;
    rich.editor.view.someProp("handlePaste", (handler) => {
      handled = handler(rich.editor.view, event) || handled;
      return handled;
    });
    return handled;
  }

  it("asks for an image to upload when the Image button is pressed", () => {
    const capture = captureImageRequests();
    const page = imagesPage("<p>a</p>");
    mount(page.textarea);
    page.toolbar.querySelector('[data-command="image"]').click();
    capture.stop();
    expect(capture.requests).toEqual([
      { editorId: "intro", file: null, pos: null },
    ]);
  });

  it("asks to upload a pasted image file", () => {
    const capture = captureImageRequests();
    const page = imagesPage("<p>a</p>");
    const rich = mount(page.textarea);
    const file = new File(["x"], "logo.png", { type: "image/png" });
    expect(paste(rich, [file])).toBe(true);
    capture.stop();
    expect(capture.requests).toHaveLength(1);
    expect(capture.requests[0].file).toBe(file);
  });

  it("ignores pasted files that are not images it can upload", () => {
    const capture = captureImageRequests();
    const page = imagesPage("<p>a</p>");
    const rich = mount(page.textarea);
    paste(rich, [new File(["x"], "notes.pdf", { type: "application/pdf" })]);
    paste(rich, [new File(["x"], "anim.gif", { type: "image/gif" })]);
    capture.stop();
    expect(capture.requests).toEqual([]);
  });

  it("does not also paste the web page's own copy of a pasted image", () => {
    const page = imagesPage("<p>a</p>");
    const rich = mount(page.textarea);
    const file = new File(["x"], "logo.png", { type: "image/png" });
    expect(
      paste(rich, [file], '<img src="https://elsewhere.example/logo.png">'),
    ).toBe(true);
    expect(rich.editor.getHTML()).toBe("<p>a</p>");
  });

  it("inserts an uploaded image where it was asked for", () => {
    const page = imagesPage("<p>ab</p>");
    mount(page.textarea);
    insert({
      editorId: "intro",
      src: "/register-assets/images/1.png",
      alt: "Logo",
      pos: 2,
    });
    expect(page.textarea.value).toBe(
      '<p>a<img src="/register-assets/images/1.png" alt="Logo">b</p>',
    );
  });

  it("inserts an image from the Assets panel at the cursor", () => {
    const page = imagesPage("<p>ab</p>");
    const rich = mount(page.textarea);
    rich.editor.commands.setTextSelection(3);
    insert({ editorId: "", src: "/i.png", alt: "Logo", pos: null });
    expect(page.textarea.value).toBe('<p>ab<img src="/i.png" alt="Logo"></p>');
  });

  it("inserts an <img> snippet at the cursor in HTML mode", () => {
    const page = imagesPage("<p>ab</p>");
    mount(page.textarea);
    page.htmlButton.click();
    insert({ editorId: "", src: "/i.png", alt: 'A "quoted" logo', pos: null });
    expect(page.textarea.value).toContain(
      '<img src="/i.png" alt="A &quot;quoted&quot; logo">',
    );
  });

  it("ignores inserts meant for another editor", () => {
    const page = imagesPage("<p>ab</p>");
    mount(page.textarea);
    insert({ editorId: "other", src: "/i.png", alt: "Logo", pos: 1 });
    expect(page.textarea.value).toBe("<p>ab</p>");
  });

  it("ignores inserts when images are not allowed", () => {
    const page = setUp("<p>ab</p>");
    mount(page.textarea);
    insert({ editorId: "intro", src: "/i.png", alt: "Logo", pos: 1 });
    expect(page.textarea.value).toBe("<p>ab</p>");
  });
});

describe("mountRichEditor image size", () => {
  const IMAGE = '<p><img src="/a.png" alt="A" width="250" height="100"></p>';

  function imagesPage(value) {
    return setUp(value, 'data-rich-editor-images="true"');
  }

  function captureSizeRequests() {
    const requests = [];
    const listener = (event) => requests.push(event.detail);
    document.addEventListener(IMAGE_SIZE_REQUEST_EVENT, listener);
    return {
      requests,
      stop: () =>
        document.removeEventListener(IMAGE_SIZE_REQUEST_EVENT, listener),
    };
  }

  function answer(detail) {
    document.dispatchEvent(
      new CustomEvent(IMAGE_SIZE_RESULT_EVENT, { detail }),
    );
  }

  function imagePos(rich) {
    let found = null;
    rich.editor.state.doc.descendants((node, pos) => {
      if (node.type.name === "image") {
        found = pos;
      }
    });
    return found;
  }

  function selectImage(rich) {
    rich.editor.commands.setNodeSelection(imagePos(rich));
  }

  // jsdom never loads images, so give the shown one the natural size a browser would.
  function giveNaturalSize(rich, width, height) {
    const shown = rich.editor.view.dom.querySelector("img[src]");
    Object.defineProperty(shown, "naturalWidth", { value: width });
    Object.defineProperty(shown, "naturalHeight", { value: height });
  }

  function imageAttrs(rich) {
    return rich.editor.state.doc.nodeAt(imagePos(rich)).attrs;
  }

  it("asks for the selected image's size with its current width", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    const capture = captureSizeRequests();
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    capture.stop();
    expect(capture.requests).toEqual([{ editorId: "intro", width: 250 }]);
  });

  it("does not ask when no image is selected", () => {
    const page = imagesPage(IMAGE);
    mount(page.textarea);
    const capture = captureSizeRequests();
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    capture.stop();
    expect(capture.requests).toEqual([]);
  });

  it("asks when an image is double-clicked", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    const capture = captureSizeRequests();
    const pos = imagePos(rich);
    const node = rich.editor.state.doc.nodeAt(pos);
    rich.editor.view.someProp("handleDoubleClickOn", (handle) =>
      handle(
        rich.editor.view,
        pos,
        node,
        pos,
        new MouseEvent("dblclick"),
        true,
      ),
    );
    capture.stop();
    expect(capture.requests).toEqual([{ editorId: "intro", width: 250 }]);
    expect(rich.editor.state.selection.node.type.name).toBe("image");
  });

  it("sets the width, and a height in proportion to the image's natural size", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    giveNaturalSize(rich, 400, 300);
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    answer({ editorId: "intro", action: "set", width: 120 });
    expect(imageAttrs(rich)).toMatchObject({ width: 120, height: 90 });
    expect(rich.editor.state.selection.node.type.name).toBe("image");
    expect(page.textarea.value).toBe(
      '<p><img src="/a.png" alt="A" width="120" height="90"></p>',
    );
  });

  it("sets the width alone when the image has not loaded", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    answer({ editorId: "intro", action: "set", width: 120 });
    expect(imageAttrs(rich)).toMatchObject({ width: 120, height: null });
  });

  it("goes back to the original size on reset", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    answer({ editorId: "intro", action: "reset", width: null });
    expect(page.textarea.value).toBe('<p><img src="/a.png" alt="A"></p>');
  });

  it("changes nothing on cancel", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    answer({ editorId: "intro", action: "cancel", width: null });
    expect(page.textarea.value).toBe(IMAGE);
  });

  it("ignores an answer meant for another editor, or one it did not ask for", () => {
    const page = imagesPage(IMAGE);
    const rich = mount(page.textarea);
    answer({ editorId: "intro", action: "set", width: 120 });
    selectImage(rich);
    page.toolbar.querySelector('[data-command="imageSize"]').click();
    answer({ editorId: "other", action: "set", width: 120 });
    expect(page.textarea.value).toBe(IMAGE);
  });

  it("opens a sized image in Visual mode", () => {
    const page = imagesPage('<p><img src="/a.png" alt="A" width="250"></p>');
    expect(mount(page.textarea).mode).toBe(VISUAL);
  });
});

describe("mountRichEditor content style preview", () => {
  function stylePage(style) {
    const page = setUp("<p>a</p>");
    page.controls.dataset.contentStyle = style;
    page.form.insertAdjacentHTML(
      "beforeend",
      `<input type="radio" name="content_style" value="govuk" data-rich-editor-style-for="intro" ${style === "govuk" ? "checked" : ""}>
       <input type="radio" name="content_style" value="plain" data-rich-editor-style-for="intro" ${style === "plain" ? "checked" : ""}>`,
    );
    return page;
  }

  function choose(value) {
    const radio = document.querySelector(`input[value="${value}"]`);
    radio.checked = true;
    radio.dispatchEvent(new Event("change", { bubbles: true }));
  }

  it("previews the GOV.UK style when the page uses it", () => {
    const page = stylePage("govuk");
    mount(page.textarea);
    expect(page.controls.classList.contains(GOVUK_STYLE_CLASS)).toBe(true);
  });

  it("previews nothing extra for the plain style", () => {
    const page = stylePage("plain");
    mount(page.textarea);
    expect(page.controls.classList.contains(GOVUK_STYLE_CLASS)).toBe(false);
  });

  it("follows the style radios as they change", () => {
    const page = stylePage("govuk");
    mount(page.textarea);
    choose("plain");
    expect(page.controls.classList.contains(GOVUK_STYLE_CLASS)).toBe(false);
    choose("govuk");
    expect(page.controls.classList.contains(GOVUK_STYLE_CLASS)).toBe(true);
  });
});
