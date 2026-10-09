// ABOUTME: Tests for the visual editor's link dialog slice.
// ABOUTME: Checks it opens from the request event's detail and answers with the result event.
import { afterEach, describe, expect, it, vi } from "vitest";
import { LINK_RESULT_EVENT } from "../lib/rich-editor-events.js";
import {
  ABSOLUTE_LINK_PATTERN,
  LINK_URL_FIELD_ID,
  richEditorLinkDialog,
} from "./rich-editor-link-dialog.js";

function request(detail) {
  return { detail: detail };
}

function listenForResults() {
  const results = vi.fn();
  document.addEventListener(LINK_RESULT_EVENT, (event) =>
    results(event.detail),
  );
  return results;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("richEditorLinkDialog", () => {
  it("opens with the link under the cursor", () => {
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.openLinkDialog(
      request({ editorId: "intro", href: "https://example.org", text: "here" }),
    );
    expect(dialog.linkDialogOpen).toBe(true);
    expect(dialog.linkUrl).toBe("https://example.org");
    expect(dialog.linkText).toBe("here");
    expect(dialog.linkHasExisting).toBe(true);
  });

  it("moves focus to the address field once the dialog has rendered", () => {
    document.body.innerHTML = `<input id="${LINK_URL_FIELD_ID}">`;
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.$nextTick = (callback) => callback();
    dialog.openLinkDialog(request({ editorId: "intro", href: "" }));
    expect(document.activeElement.id).toBe(LINK_URL_FIELD_ID);
    document.body.innerHTML = "";
  });

  it("opens empty for a new link, with no Remove option", () => {
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.openLinkDialog(request({ editorId: "intro", href: "", text: "" }));
    expect(dialog.linkUrl).toBe("");
    expect(dialog.linkHasExisting).toBe(false);
  });

  it("answers Apply with the trimmed address", () => {
    const results = listenForResults();
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.openLinkDialog(request({ editorId: "intro", href: "" }));
    dialog.linkUrl = "  https://example.org/x ";
    dialog.applyLink();
    expect(dialog.linkDialogOpen).toBe(false);
    expect(results).toHaveBeenLastCalledWith({
      editorId: "intro",
      action: "set",
      href: "https://example.org/x",
    });
  });

  it("refuses to apply an empty address", () => {
    const results = listenForResults();
    const dialog = richEditorLinkDialog({
      messages: { linkUrlRequired: "Enter a link address" },
    });
    dialog.openLinkDialog(request({ editorId: "intro", href: "" }));
    dialog.linkUrl = "   ";
    dialog.applyLink();
    expect(dialog.linkDialogOpen).toBe(true);
    expect(dialog.linkError).toBe("Enter a link address");
    expect(results).not.toHaveBeenCalled();
  });

  describe("when links must be absolute, as in an email", () => {
    const NOT_ABSOLUTE = "Email links must be full addresses";

    function applyAbsolute(href) {
      const results = listenForResults();
      const dialog = richEditorLinkDialog({
        messages: { linkUrlNotAbsolute: NOT_ABSOLUTE },
      });
      dialog.openLinkDialog(
        request({ editorId: "body", href: "", absoluteOnly: true }),
      );
      dialog.linkUrl = href;
      dialog.applyLink();
      return { dialog, results };
    }

    it.each([
      "https://example.org/x",
      "http://example.org",
      "HTTPS://EXAMPLE.ORG",
      "mailto:team@example.org",
      "tel:+441632960000",
      "{{ assembly.url }}",
    ])("accepts %s", (href) => {
      const { dialog, results } = applyAbsolute(href);
      expect(dialog.linkDialogOpen).toBe(false);
      expect(results).toHaveBeenLastCalledWith({
        editorId: "body",
        action: "set",
        href: href,
      });
    });

    it.each(["/register/x", "www.example.org", "example.org", "#top"])(
      "refuses %s, which would not work from an inbox",
      (href) => {
        const { dialog, results } = applyAbsolute(href);
        expect(dialog.linkDialogOpen).toBe(true);
        expect(dialog.linkError).toBe(NOT_ABSOLUTE);
        expect(results).not.toHaveBeenCalled();
      },
    );

    it("shares one pattern between the check and its tests", () => {
      expect(ABSOLUTE_LINK_PATTERN.test("https://x")).toBe(true);
      expect(ABSOLUTE_LINK_PATTERN.test("/x")).toBe(false);
    });

    it("forgets the rule when the next request does not ask for it", () => {
      const results = listenForResults();
      const dialog = richEditorLinkDialog({ messages: {} });
      dialog.openLinkDialog(
        request({ editorId: "body", href: "", absoluteOnly: true }),
      );
      dialog.openLinkDialog(request({ editorId: "intro", href: "" }));
      dialog.linkUrl = "/register/x";
      dialog.applyLink();
      expect(results).toHaveBeenLastCalledWith({
        editorId: "intro",
        action: "set",
        href: "/register/x",
      });
    });
  });

  it("accepts a relative address when links need not be absolute", () => {
    const results = listenForResults();
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.openLinkDialog(request({ editorId: "intro", href: "" }));
    dialog.linkUrl = "/register/x";
    dialog.applyLink();
    expect(results).toHaveBeenLastCalledWith({
      editorId: "intro",
      action: "set",
      href: "/register/x",
    });
  });

  it("answers Remove and Cancel", () => {
    const results = listenForResults();
    const dialog = richEditorLinkDialog({ messages: {} });
    dialog.openLinkDialog(request({ editorId: "intro", href: "/x" }));
    dialog.removeLink();
    expect(results).toHaveBeenLastCalledWith({
      editorId: "intro",
      action: "remove",
      href: "",
    });
    dialog.openLinkDialog(request({ editorId: "intro", href: "/x" }));
    dialog.cancelLink();
    expect(dialog.linkDialogOpen).toBe(false);
    expect(results).toHaveBeenLastCalledWith({
      editorId: "intro",
      action: "cancel",
      href: "",
    });
  });
});
