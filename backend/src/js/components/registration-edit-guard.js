// ABOUTME: The registration page's share of the unsaved-changes guard, plus its close confirmation
// ABOUTME: One of the slices composed into registrationPageController

import { editGuard } from "./edit-guard.js";

/**
 * Build the edit-guard slice of the registration page controller.
 *
 * The generic half - the dirty flag, the discard dialog, beforeunload - is
 * `editGuard`. What is left here is what only this page has.
 *
 * Only edit mode can be dirty: markEditDirty() is wired to the editor forms'
 * input/change events, which also catch CodeMirror edits because .cm-content is
 * a contenteditable inside the form and its input events bubble. The stepper and
 * footer navigation are disabled while editing, so in-app leave paths funnel
 * through the Cancel button's guardLeave() and its discard modal - which is why
 * this page does not ask editGuard to intercept links for it.
 *
 * The editor renders as a takeover modal over the pages list, so this slice also
 * owns closing that modal: the close X is a guarded link, and Esc goes through
 * closePageGuarded() - both land on options.listUrl.
 *
 * @param {Object} options - configuration
 * @param {boolean} options.editMode - whether the page is in edit mode
 * @param {string} [options.listUrl=""] - the pages list the editor modal closes to
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationEditGuard(options) {
  return Object.assign({}, editGuard(), {
    editMode: Boolean(options.editMode),
    listUrl: options.listUrl || "",
    // Closing a registration is terminal - there is no reopen.
    confirmCloseOpen: false,

    init: function () {
      if (!this.editMode) return;
      this.initEditGuard();
    },

    // Wired to Esc on the page root: closes the editor modal back to the pages
    // list. A nested dialog owns the Esc press while it is open - this handler
    // is registered first (the root initialises before its descendants), so it
    // sees the nested dialog's flag still set and yields; the nested dialog's
    // own handler then closes it. Unsaved edits divert to the discard modal.
    closePageGuarded: function () {
      if (!this.listUrl) return;
      if (
        this.leaveModalOpen ||
        this.confirmCloseOpen ||
        this.skeletonModalOpen ||
        this.imageUploadModalOpen ||
        this.imageDetailsModalOpen ||
        this.documentUploadModalOpen ||
        this.documentDetailsModalOpen
      ) {
        return;
      }
      if (this.editDirty) {
        this.openLeaveModal(this.listUrl);
        return;
      }
      window.location.assign(this.listUrl);
    },

    openConfirmClose: function () {
      var self = this;
      self.confirmCloseOpen = true;
      self.$nextTick(function () {
        if (self.$refs.keepOpenBtn) self.$refs.keepOpenBtn.focus();
      });
    },

    cancelConfirmClose: function () {
      this.confirmCloseOpen = false;
    },
  });
}
