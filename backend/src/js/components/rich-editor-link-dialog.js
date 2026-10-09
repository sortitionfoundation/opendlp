// ABOUTME: Link dialog slice for the visual HTML editor, composed into the registration page controller
// ABOUTME: Opens on the editor's link request event and answers with a link result event

import { LINK_RESULT_EVENT } from "../lib/rich-editor-events.js";

export const LINK_URL_FIELD_ID = "link-modal-url";

// An address that works from an email: a web, mail or phone link, or a
// variable that the email fills in with one.
export const ABSOLUTE_LINK_PATTERN = /^(https?:\/\/|mailto:|tel:|\{\{)/i;

/**
 * Build the link-dialog slice.
 *
 * The editor (src/js/backoffice/rich-editor.js) and this slice never import
 * each other: the editor dispatches LINK_REQUEST_EVENT on the document with
 * `{editorId, href, text, absoluteOnly}`, and the dialog replies with LINK_RESULT_EVENT
 * carrying `{editorId, action, href}`, where action is "set", "remove" or
 * "cancel". The editor puts focus back in the text whatever the answer.
 * `absoluteOnly` is set for an email, where a relative address would not work.
 *
 * @param {Object} options - configuration
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function richEditorLinkDialog(options) {
  var messages = options.messages || {};

  return {
    linkDialogOpen: false,
    linkUrl: "",
    linkText: "",
    linkHasExisting: false,
    linkEditorId: "",
    linkError: "",
    linkAbsoluteOnly: false,

    openLinkDialog: function (event) {
      var detail = event.detail || {};
      this.linkEditorId = detail.editorId || "";
      this.linkUrl = detail.href || "";
      this.linkText = detail.text || "";
      this.linkHasExisting = Boolean(detail.href);
      this.linkAbsoluteOnly = Boolean(detail.absoluteOnly);
      this.linkError = "";
      this.linkDialogOpen = true;
      if (this.$nextTick) {
        this.$nextTick(function () {
          var field = document.getElementById(LINK_URL_FIELD_ID);
          if (field) field.focus();
        });
      }
    },

    answerLinkDialog: function (action, href) {
      this.linkDialogOpen = false;
      document.dispatchEvent(
        new CustomEvent(LINK_RESULT_EVENT, {
          detail: { editorId: this.linkEditorId, action: action, href: href },
        }),
      );
    },

    applyLink: function () {
      var href = this.linkUrl.trim();
      if (!href) {
        this.linkError = messages.linkUrlRequired || "";
        return;
      }
      if (this.linkAbsoluteOnly && !ABSOLUTE_LINK_PATTERN.test(href)) {
        this.linkError = messages.linkUrlNotAbsolute || "";
        return;
      }
      this.answerLinkDialog("set", href);
    },

    removeLink: function () {
      this.answerLinkDialog("remove", "");
    },

    cancelLink: function () {
      this.answerLinkDialog("cancel", "");
    },
  };
}
