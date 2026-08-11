// ABOUTME: Unsaved-changes guard and close-registration confirmation for the registration page
// ABOUTME: One of the slices composed into registrationPageController

/**
 * Build the edit-guard slice of the registration page controller.
 *
 * Only edit mode can be dirty: markEditDirty() is wired to the editor forms'
 * input/change events, which also catch CodeMirror edits because .cm-content is
 * a contenteditable inside the form and its input events bubble. The stepper and
 * footer navigation are disabled while editing, so in-app leave paths funnel
 * through the Cancel button's guardLeave() and its discard modal; beforeunload
 * is the backstop for browser-level navigation - close tab, reload, back button.
 *
 * @param {Object} options - configuration
 * @param {boolean} options.editMode - whether the page is in edit mode
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationEditGuard(options) {
  return {
    editMode: Boolean(options.editMode),
    editDirty: false,
    leaveModalOpen: false,
    leaveUrl: "",
    leaveGuardSuppressed: false,
    // Closing a registration is terminal - there is no reopen.
    confirmCloseOpen: false,

    init: function () {
      var self = this;
      if (!self.editMode) return;
      window.addEventListener("beforeunload", function (event) {
        if (!self.editDirty || self.leaveGuardSuppressed) return;
        event.preventDefault();
        event.returnValue = "";
      });
    },

    markEditDirty: function () {
      this.editDirty = true;
    },

    // Called on the editor form's submit so Save never trips the beforeunload guard.
    allowLeave: function () {
      this.leaveGuardSuppressed = true;
    },

    // Attached to leave-links (Cancel). Clean state falls through to normal navigation.
    guardLeave: function (event) {
      if (!this.editDirty) return;
      event.preventDefault();
      this.openLeaveModal(event.currentTarget.href);
    },

    openLeaveModal: function (url) {
      var self = this;
      self.leaveUrl = url;
      self.leaveModalOpen = true;
      self.$nextTick(function () {
        if (self.$refs.keepEditingBtn) self.$refs.keepEditingBtn.focus();
      });
    },

    closeLeaveModal: function () {
      this.leaveModalOpen = false;
      this.leaveUrl = "";
    },

    discardAndLeave: function () {
      if (!this.leaveUrl) return;
      this.leaveGuardSuppressed = true;
      window.location.assign(this.leaveUrl);
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
  };
}
