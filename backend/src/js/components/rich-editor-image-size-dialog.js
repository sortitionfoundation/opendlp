// ABOUTME: Image size dialog slice for the visual HTML editor, composed into the registration page controller
// ABOUTME: Opens on the editor's image size request event and answers with an image size result event

import { IMAGE_SIZE_RESULT_EVENT } from "../lib/rich-editor-events.js";

export const IMAGE_SIZE_FIELD_ID = "image-size-modal-width";
export const MIN_IMAGE_WIDTH = 20;
export const MAX_IMAGE_WIDTH = 2000;

/**
 * Build the image-size-dialog slice.
 *
 * The editor (src/js/backoffice/rich-editor.js) and this slice never import
 * each other: the editor dispatches IMAGE_SIZE_REQUEST_EVENT on the document
 * with `{editorId, width}`, and the dialog replies with IMAGE_SIZE_RESULT_EVENT
 * carrying `{editorId, action, width}`, where action is "set", "reset" or
 * "cancel". The editor works out the height, and puts focus back in the text
 * whatever the answer.
 *
 * @param {Object} options - configuration
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function richEditorImageSizeDialog(options) {
  var messages = options.messages || {};

  return {
    imageSizeDialogOpen: false,
    imageSizeWidth: "",
    imageSizeEditorId: "",
    imageSizeError: "",

    openImageSizeDialog: function (event) {
      var detail = event.detail || {};
      this.imageSizeEditorId = detail.editorId || "";
      this.imageSizeWidth = detail.width ? String(detail.width) : "";
      this.imageSizeError = "";
      this.imageSizeDialogOpen = true;
      if (this.$nextTick) {
        this.$nextTick(function () {
          var field = document.getElementById(IMAGE_SIZE_FIELD_ID);
          if (field) {
            field.focus();
            field.select();
          }
        });
      }
    },

    answerImageSizeDialog: function (action, width) {
      this.imageSizeDialogOpen = false;
      document.dispatchEvent(
        new CustomEvent(IMAGE_SIZE_RESULT_EVENT, {
          detail: {
            editorId: this.imageSizeEditorId,
            action: action,
            width: width,
          },
        }),
      );
    },

    applyImageSize: function () {
      var text = String(this.imageSizeWidth).trim();
      var width = Number(text);
      if (
        !/^\d+$/.test(text) ||
        width < MIN_IMAGE_WIDTH ||
        width > MAX_IMAGE_WIDTH
      ) {
        this.imageSizeError = messages.imageWidthInvalid || "";
        return;
      }
      this.answerImageSizeDialog("set", width);
    },

    resetImageSize: function () {
      this.answerImageSizeDialog("reset", null);
    },

    cancelImageSize: function () {
      this.answerImageSizeDialog("cancel", null);
    },
  };
}
