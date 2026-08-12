/**
 * ABOUTME: Alpine component for the frontend patterns reference page
 * ABOUTME: Holds the toast state and one copy method per documented code sample
 *
 * There is a method per snippet rather than a single copy(name) because the CSP
 * Alpine build forbids string arguments in an @click expression - `copy('url')`
 * will not run. That constraint is itself one of the things this page documents.
 *
 * Usage:
 *   <div x-data="patternsController()" x-cloak>
 *     <button @click="copyUrlSelectCode()">Copy</button>
 *     <div x-show="toast.show" x-transition><span x-text="toast.message"></span></div>
 *   </div>
 */

import {
  FILE_UPLOAD_ROUTE_CODE,
  FILE_UPLOAD_TEMPLATE_CODE,
  INLINE_SELECT_CODE,
  NAVIGATE_SCROLL_CODE,
  PAGINATION_ROUTE_CODE,
  PAGINATION_TEMPLATE_CODE,
  PRESERVE_SCROLL_CODE,
  PROGRESS_BAR_CODE,
  SCROLL_DIRECTIVE_CODE,
  SCROLL_PRESERVE_CODE,
  URL_SELECT_CODE,
} from "./patterns-snippets.js";

const TOAST_DURATION_MS = 3000;

/**
 * Build the patternsController component state.
 *
 * @returns {Object} Alpine component state
 */
export function patternsController() {
  return {
    toast: { show: false, message: "", type: "info" },

    // Demo state for the inline select example on the Form State tab
    demoAssemblyId: "",

    urlSelectCode: URL_SELECT_CODE,
    inlineSelectCode: INLINE_SELECT_CODE,
    fileUploadTemplateCode: FILE_UPLOAD_TEMPLATE_CODE,
    fileUploadRouteCode: FILE_UPLOAD_ROUTE_CODE,
    progressBarCode: PROGRESS_BAR_CODE,
    paginationTemplateCode: PAGINATION_TEMPLATE_CODE,
    paginationRouteCode: PAGINATION_ROUTE_CODE,
    scrollPreserveCode: SCROLL_PRESERVE_CODE,
    preserveScrollCode: PRESERVE_SCROLL_CODE,
    scrollDirectiveCode: SCROLL_DIRECTIVE_CODE,
    navigateScrollCode: NAVIGATE_SCROLL_CODE,

    showToast: function (message, type) {
      var self = this;
      self.toast = { show: true, message: message, type: type };
      setTimeout(function () {
        self.toast.show = false;
      }, TOAST_DURATION_MS);
    },

    copyToClipboard: function (text) {
      var self = this;
      return navigator.clipboard.writeText(text).then(
        function () {
          self.showToast("Copied to clipboard!", "success");
        },
        function () {
          self.showToast("Failed to copy", "error");
        },
      );
    },

    copyUrlSelectCode: function () {
      return this.copyToClipboard(this.urlSelectCode);
    },

    copyInlineSelectCode: function () {
      return this.copyToClipboard(this.inlineSelectCode);
    },

    copyFileUploadTemplateCode: function () {
      return this.copyToClipboard(this.fileUploadTemplateCode);
    },

    copyFileUploadRouteCode: function () {
      return this.copyToClipboard(this.fileUploadRouteCode);
    },

    copyProgressBarCode: function () {
      return this.copyToClipboard(this.progressBarCode);
    },

    copyPaginationTemplateCode: function () {
      return this.copyToClipboard(this.paginationTemplateCode);
    },

    copyPaginationRouteCode: function () {
      return this.copyToClipboard(this.paginationRouteCode);
    },

    copyScrollPreserveCode: function () {
      return this.copyToClipboard(this.scrollPreserveCode);
    },

    copyPreserveScrollCode: function () {
      return this.copyToClipboard(this.preserveScrollCode);
    },

    copyScrollDirectiveCode: function () {
      return this.copyToClipboard(this.scrollDirectiveCode);
    },

    copyNavigateScrollCode: function () {
      return this.copyToClipboard(this.navigateScrollCode);
    },
  };
}
