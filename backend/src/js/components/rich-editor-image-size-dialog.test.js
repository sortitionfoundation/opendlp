// ABOUTME: Tests for the visual editor's Image size dialog slice.
// ABOUTME: Checks it opens from the request event's detail, validates the width and answers with the result event.
import { afterEach, describe, expect, it, vi } from "vitest";
import { IMAGE_SIZE_RESULT_EVENT } from "../lib/rich-editor-events.js";
import {
  IMAGE_SIZE_FIELD_ID,
  richEditorImageSizeDialog,
} from "./rich-editor-image-size-dialog.js";

const MESSAGES = { imageWidthInvalid: "Enter a width" };

let listener = null;

function request(detail) {
  return { detail: detail };
}

function listenForResults() {
  const results = vi.fn();
  listener = (event) => results(event.detail);
  document.addEventListener(IMAGE_SIZE_RESULT_EVENT, listener);
  return results;
}

function openDialog(width = 250) {
  const dialog = richEditorImageSizeDialog({ messages: MESSAGES });
  dialog.openImageSizeDialog(request({ editorId: "intro", width: width }));
  return dialog;
}

afterEach(() => {
  if (listener) {
    document.removeEventListener(IMAGE_SIZE_RESULT_EVENT, listener);
    listener = null;
  }
  document.body.innerHTML = "";
});

describe("richEditorImageSizeDialog", () => {
  it("opens with the image's current width", () => {
    const dialog = openDialog(250);
    expect(dialog.imageSizeDialogOpen).toBe(true);
    expect(dialog.imageSizeWidth).toBe("250");
    expect(dialog.imageSizeError).toBe("");
  });

  it("opens empty when the editor knows no width", () => {
    const dialog = openDialog(null);
    expect(dialog.imageSizeWidth).toBe("");
  });

  it("moves focus to the width field once the dialog has rendered", () => {
    document.body.innerHTML = `<input id="${IMAGE_SIZE_FIELD_ID}">`;
    const dialog = richEditorImageSizeDialog({ messages: MESSAGES });
    dialog.$nextTick = (callback) => callback();
    dialog.openImageSizeDialog(request({ editorId: "intro", width: 250 }));
    expect(document.activeElement.id).toBe(IMAGE_SIZE_FIELD_ID);
  });

  it("answers Apply with the width as a number", () => {
    const results = listenForResults();
    const dialog = openDialog();
    dialog.imageSizeWidth = " 120 ";
    dialog.applyImageSize();
    expect(dialog.imageSizeDialogOpen).toBe(false);
    expect(results).toHaveBeenCalledWith({
      editorId: "intro",
      action: "set",
      width: 120,
    });
  });

  it("accepts a number from a number field's x-model", () => {
    const results = listenForResults();
    const dialog = openDialog();
    dialog.imageSizeWidth = 2000;
    dialog.applyImageSize();
    expect(results).toHaveBeenCalledWith(
      expect.objectContaining({ action: "set", width: 2000 }),
    );
  });

  it.each(["", "abc", "12.5", "-50", "19", "2001", "1e3"])(
    "refuses the width %j and stays open",
    (width) => {
      const results = listenForResults();
      const dialog = openDialog();
      dialog.imageSizeWidth = width;
      dialog.applyImageSize();
      expect(dialog.imageSizeDialogOpen).toBe(true);
      expect(dialog.imageSizeError).toBe("Enter a width");
      expect(results).not.toHaveBeenCalled();
    },
  );

  it("answers Original size with a reset", () => {
    const results = listenForResults();
    const dialog = openDialog();
    dialog.resetImageSize();
    expect(dialog.imageSizeDialogOpen).toBe(false);
    expect(results).toHaveBeenCalledWith({
      editorId: "intro",
      action: "reset",
      width: null,
    });
  });

  it("answers Cancel with a cancel", () => {
    const results = listenForResults();
    const dialog = openDialog();
    dialog.cancelImageSize();
    expect(dialog.imageSizeDialogOpen).toBe(false);
    expect(results).toHaveBeenCalledWith({
      editorId: "intro",
      action: "cancel",
      width: null,
    });
  });
});
