// ABOUTME: Skeleton preview slice of the registration page controller
// ABOUTME: Fetches the generated form markup, holds the plain / GOV.UK styled toggle and writes the choice into the form
import { SET_VALUE_EVENT } from "../lib/code-editor-events.js";

// The form step's HTML textarea, which the chosen skeleton replaces.
var FORM_TEXTAREA_ID = "html_content";

/**
 * Build the skeleton-preview slice of the registration page controller.
 *
 * @param {Object} options - configuration
 * @param {string} options.csrfToken - the CSRF token for the session
 * @param {string} options.skeletonUrl - the route that generates the form skeleton
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationSkeleton(options) {
  var messages = options.messages;

  return {
    skeletonLoading: false,
    skeletonModalOpen: false,
    skeletonHtmlPlain: "",
    skeletonHtmlStyled: "",
    // The accessible version is the one to recommend, so it is shown first.
    skeletonView: "styled",
    skeletonReplaceConfirmOpen: false,

    // Uses fetch directly rather than the lib/json-request helpers: this route
    // reports its problems in the body rather than the status, so the parsed
    // body is the whole answer and an unparsable one has to be an error.
    fetchFormSkeleton: function () {
      var self = this;
      self.skeletonLoading = true;

      return fetch(options.skeletonUrl, {
        method: "GET",
        headers: { "X-CSRFToken": options.csrfToken },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          self.skeletonLoading = false;
          if (data.error) {
            self.showToast(data.error, "error");
            return;
          }
          self.skeletonHtmlPlain = data.html;
          self.skeletonHtmlStyled = data.html_govuk;
          self.skeletonView = "styled";
          self.skeletonModalOpen = true;
        })
        .catch(function () {
          self.skeletonLoading = false;
          self.showToast(messages.skeletonFetchFailed, "error");
        });
    },

    closeSkeletonModal: function () {
      this.skeletonModalOpen = false;
    },

    showPlainSkeleton: function () {
      this.skeletonView = "plain";
    },

    showStyledSkeleton: function () {
      this.skeletonView = "styled";
    },

    // Writing over a form that has HTML loses it, so that asks first. The
    // skeleton modal closes while the question is asked, so only one dialog
    // is ever open; cancelling brings it back as it was.
    useSkeletonAsForm: function () {
      var self = this;
      var textarea = document.getElementById(FORM_TEXTAREA_ID);
      if (!textarea) return;
      if (textarea.value.trim()) {
        self.skeletonModalOpen = false;
        self.skeletonReplaceConfirmOpen = true;
        self.$nextTick(function () {
          if (self.$refs.keepFormBtn) self.$refs.keepFormBtn.focus();
        });
        return;
      }
      self._writeSkeletonToForm(textarea);
    },

    confirmReplaceFormWithSkeleton: function () {
      var textarea = document.getElementById(FORM_TEXTAREA_ID);
      this.skeletonReplaceConfirmOpen = false;
      if (textarea) this._writeSkeletonToForm(textarea);
    },

    cancelReplaceFormWithSkeleton: function () {
      this.skeletonReplaceConfirmOpen = false;
      this.skeletonModalOpen = true;
    },

    // The textarea is written directly too, so the form still carries the
    // skeleton if no editor is mounted over it to answer the event.
    _writeSkeletonToForm: function (textarea) {
      var html =
        this.skeletonView === "plain"
          ? this.skeletonHtmlPlain
          : this.skeletonHtmlStyled;
      textarea.value = html;
      textarea.dispatchEvent(
        new CustomEvent(SET_VALUE_EVENT, { detail: { value: html } }),
      );
      // A replaced value fires no input event, so the unsaved-changes guard
      // is told directly.
      this.markEditDirty();
      this.skeletonModalOpen = false;
    },
  };
}
